import re
from typing import Optional, List, Dict
from dataclasses import dataclass
from sqlalchemy.orm import Session
from models.database import CompanyField
try:
    from rapidfuzz import fuzz
except ImportError:
    pass  # Will be handled gracefully

@dataclass
class MatchResult:
    field_key: str
    field_label: str
    value: str
    matched_alias: str
    score: float

def normalize_label(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, remove noise words."""
    if not text:
        return ""
    # Lowercase
    t = text.lower()
    # Remove noise words using regex to match whole words
    t = re.sub(r'\b(no\.?|number|details)\b', ' ', t)
    # Remove other noise characters
    for w in [":", "*", "-"]:
        t = t.replace(w, " ")
    # Strip punctuation and collapse whitespace
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

class FieldMatcher:
    def __init__(self, db: Session):
        self.db = db
        
        # Note: CompanyField now also includes learned answers (category="Learned", confidence="learned").
        # Fuzzy alias matching will therefore match against previously-learned field labels.
        # This is a feature improvement, not a bug.
        self.fields = self.db.query(CompanyField).all()
        self.index = {}  # normalized_alias_or_label -> CompanyField
        
        for field in self.fields:
            # Add main label
            norm_label = normalize_label(field.field_label)
            if norm_label:
                self.index[norm_label] = field
            
            # Add aliases
            if field.aliases:
                for alias in field.aliases:
                    norm_alias = normalize_label(alias)
                    if norm_alias:
                        self.index[norm_alias] = field

    def match(self, form_label: str, threshold: int = 85) -> Optional[MatchResult]:
        if not form_label:
            return None
        
        norm_form_label = normalize_label(form_label)
        if not norm_form_label:
            return None
        
        best_score = 0
        best_match_key = None
        best_field = None
        
        for index_key, field in self.index.items():
            score = fuzz.token_sort_ratio(norm_form_label, index_key)
            if score > best_score:
                best_score = score
                best_match_key = index_key
                best_field = field
                
        if best_score >= threshold and best_field:
            # Increment usage count
            best_field.usage_count = (best_field.usage_count or 0) + 1
            self.db.commit()
            
            return MatchResult(
                field_key=best_field.field_key,
                field_label=best_field.field_label,
                value=best_field.value or "",
                matched_alias=best_match_key,
                score=best_score
            )
        return None

    def match_batch(self, form_labels: List[str], threshold: int = 85) -> Dict[str, MatchResult]:
        results = {}
        for label in form_labels:
            m = self.match(label, threshold)
            if m:
                results[label] = m
        return results

def extract_candidates_from_map(cell_map: str, max_hops: int = 4) -> Dict[str, List[str]]:
    """
    Parse cell_map string and return empty_coord -> [label_left, label_above].

    IMPORTANT (fix): this now walks up to `max_hops` columns left / rows above to find
    a real label, skipping over gaps left by merged-cell continuations that
    build_sheet_cell_map deliberately omits from the map. Previously this only ever
    looked at the immediate neighbor, which meant merge-remnant cells (which used to
    incorrectly appear as fillable EMPTY cells) were the ones getting matched -- and
    writing into them corrupted the form's own labels (see write_filled_excel_multi).
    Now that those remnants never appear in the map at all, the true answer cell one
    or two columns further over needs to keep walking past the gap to find its label.
    A generic-noise stoplist also prevents column headers like "Remarks" from being
    used as a label for unrelated blank cells that merely happen to sit near them.
    """
    STOP_LABELS = {
        "remarks", "remark", "sr no", "sr no.", "s no", "s.no", "s.no.",
        "particulars", "particular", "details", "description", "notes", "note",
    }

    grid = {}
    pattern = re.compile(r"\[([A-Z]+)(\d+)\]=(EMPTY|'.*?')")
    for match in pattern.finditer(cell_map):
        col, row_str, val = match.groups()
        row = int(row_str)
        if val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        grid[(col, row)] = val

    def get_col_index(c):
        idx = 0
        for char in c:
            idx = idx * 26 + (ord(char) - ord('A') + 1)
        return idx

    def get_col_name(idx):
        name = ""
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            name = chr(65 + rem) + name
        return name

    ROMAN_HEADING_RE = re.compile(r'^[IVXLCDM]{1,4}\s*[\.\)\-:]')

    def is_usable_label(val: str) -> bool:
        if not val or val == "EMPTY":
            return False
        s = val.strip()
        # FIX (P0 -- section headers getting overwritten): build_sheet_cell_map now
        # wraps detected section headers as "--- Section: <name> ---" in the map so
        # GPT-4o vision can use them for navigation. But that wrapper text is a
        # structural marker, not a real field label -- if it were ever used as the
        # "nearby label" for an adjacent blank cell, Pass 1 or the context matcher
        # could match on it and overwrite the header's own cell. Never treat it as
        # a usable label.
        if s.startswith("--- Section:") and s.endswith("---"):
            return False
        # Not every heading gets wrapped as a "--- Section: ... ---" marker -- only
        # ones detected via a horizontal cell merge. A heading like
        # "V. QUALITY CERTIFICATION/AUTHORIZATION/LICENSE AVAILABLE" that happens to
        # sit in a single unmerged cell slips through that check, and its mention of
        # "license"/"certification" can trip the attachment-detection heuristic for
        # an unrelated adjacent blank cell. Catch these structurally instead: roman
        # numeral headings, and long mostly-uppercase banner text.
        if ROMAN_HEADING_RE.match(s):
            return False
        letters = [c for c in s if c.isalpha()]
        if len(s) > 20 and letters and (sum(1 for c in letters if c.isupper()) / len(letters)) > 0.85:
            return False
        return s.lower() not in STOP_LABELS

    def find_label_left(col_idx, row):
        for hop in range(1, max_hops + 1):
            probe_idx = col_idx - hop
            if probe_idx < 1:
                return None
            probe_col = get_col_name(probe_idx)
            val = grid.get((probe_col, row))
            if val is None:
                continue  # merge-continuation gap we intentionally excluded -- keep walking
            if val == "EMPTY":
                return None  # a genuine blank cell breaks the chain
            return val if is_usable_label(val) else None
        return None

    def find_label_above(col, row):
        for hop in range(1, max_hops + 1):
            probe_row = row - hop
            if probe_row < 1:
                return None
            val = grid.get((col, probe_row))
            if val is None:
                continue
            if val == "EMPTY":
                return None
            return val if is_usable_label(val) else None
        return None

    candidates = {}
    for (col, row), val in grid.items():
        if val == "EMPTY":
            coord = f"{col}{row}"
            labels = []
            col_idx = get_col_index(col)
            left_val = find_label_left(col_idx, row)
            if left_val:
                labels.append(left_val)
            above_val = find_label_above(col, row)
            if above_val:
                labels.append(above_val)
            if labels:
                candidates[coord] = labels
    return candidates
