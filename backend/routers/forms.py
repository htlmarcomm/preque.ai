from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from models.database import get_db, FilledForm
from openai import OpenAI
import openpyxl, io, os, json, re, base64, tempfile, subprocess, shutil
from datetime import datetime
from routers.project_files import read_excel_preview

router = APIRouter()
UPLOAD_DIR = "uploads/forms"
OUTPUT_DIR = "uploads/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://models.inference.ai.azure.com",
)
VISION_MODEL = "gpt-4o"

# â”€â”€ Prompts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SHEET_CLASSIFY_PROMPT = """You are looking at ONE sheet/tab from a multi-sheet Excel Pre-Qualification form for HTL Aircon Pvt Ltd, a MEP contractor.

The sheet name is: "{sheet_name}"

Below is the cell map for JUST this sheet:
{cell_map}

Decide what kind of sheet this is:

1. "FILLABLE" — it has labelled fields/questions (with or without sub-headings) that need company data filled into adjacent/nearby empty cells. This includes forms with a heading followed by sub-fields (e.g. "Annual Turnover" as heading, then "2022-23", "2023-24" as sub-rows each needing a value).
2. "INFO_ONLY" — it is pure instructional text, a cover letter, declaration, index/table of contents, terms & conditions, or auto-calculated/summary sheet with no genuine blank answer cells belonging to HTL (e.g. project background text, an "Instructions to Bidders" page, or a sheet that is entirely a client-side summary/recommendation table with no HTL input required).

Respond with ONLY one word: FILLABLE or INFO_ONLY"""


FILL_SYSTEM_PROMPT = """You are an expert form filler working for HTL Aircon Pvt Ltd, a MEP contractor.

You are filling ONE SPECIFIC SHEET from a multi-sheet Excel Pre-Qualification form. Stay focused only on this sheet — do not invent data for sheets you cannot see.

You will receive:
1. An image of this one Excel sheet (exactly as a human would see it)
2. A cell map for THIS SHEET ONLY — every cell shown as [COORD]='value', [COORD]=EMPTY, or [COORD]='--- Section: <Name> ---'
3. HTL Aircon's company data (Structured as a JSON object grouped by categories like "General", "Financials", etc.)

Your task — act like a human filling this one tab:
- Look at the image and the '--- Section: ... ---' markers in the cell map to understand which section you are in (e.g. Financial Info, General Info).
- Use this section context to navigate the structured JSON COMPANY DATA. For example, if you are in a "Financial" section, prioritize looking inside the "Financials" category of the JSON and match the correct Fiscal Year.
- If a field explicitly asks you to "attach", "enclose", or "provide a copy of" a certificate, license, or document (e.g. 'Attach PAN', 'Enclose GST', 'Upload ISO'), output the exact string "Attached". Do NOT output the actual registration number unless the cell specifically asks for the number itself.
- Use the cell map to find the EXACT coordinates of each empty answer cell ON THIS SHEET
- Match each empty answer cell to what it's asking using visual context. Pay close attention to headings followed by sub-headings/sub-rows — each sub-row is usually a distinct field that needs its own value (e.g. a "Annual Turnover" heading with sub-rows "FY 2022-23", "FY 2023-24", "FY 2024-25" each need their own figure; a "Contact Details" heading with sub-rows "Name", "Designation", "Phone" each need a different value).
- Fill each matched cell with the correct value from company data

Return ONLY a JSON object: {"D6": "HTL Aircon Pvt Ltd", "D8": "1996", ...}

Rules:
- Cell addresses must be exact (e.g. "D6") — get them from the cell map, not the image
- Be smart about matching: "Name of the firm" = Company Name, "GST No" = GSTIN, etc.
- For sub-rows under a heading, fill each sub-row's own adjacent cell — never repeat the same value into every sub-row unless they're genuinely asking for the same thing
- Cells belonging to a repeating list of DIFFERENT past projects or DIFFERENT past clients (e.g. "Client Reference -1", "-2", "-3" or a numbered project history table) are handled by a separate picker UI, not by you. If the cell map marks such rows as "(Reserved for project/reference picker)" leave them alone — do not guess a value for them, and never repeat one single company fact (like our own contact person) across what are clearly slots for several different external clients/projects.
- Skip cells where you have no matching data for THIS sheet — do not guess or fabricate
- Do NOT fill section headers, serial numbers, or label cells
- Do NOT fill cells that are clearly informational text, instructions, or declarations with no blank to answer
- Return ONLY the JSON, no markdown, no explanation"""

COLUMN_CLASSIFY_PROMPT = """Analyze this Excel cell map for a sheet named '{sheet_name}'.
Some forms have specific columns reserved for the vendor to fill in, while other columns are strictly for the client's internal use (like "remarks by evaluator", "docs verified", "internal use only", etc.).

Look at the header rows (usually row 1 to 5).
Determine which columns are meant for us (the vendor filling the form) versus which are strictly reserved for the client/evaluator.
If there is no clear distinction, or all columns seem fillable, just return empty lists.

Return a JSON object with this exact structure:
{{
  "fillable_columns": ["B", "D"],
  "reserved_columns": ["E", "F", "G"]
}}

CELL MAP:
{cell_map}
"""

TABLE_DETECT_PROMPT = """Analyze this Excel cell map for a sheet named '{sheet_name}'.
Determine if this sheet contains a repeating table where each row represents ONE PROJECT
(a list of client engagements/jobs). This includes two distinct kinds of tables:

TYPE "project_reference": each row asks for CLIENT CONTACT/REFERENCE details tied to a
past project — columns like client name, contact person, designation, phone, email — used
so a form reviewer can call a past client for a reference.

TYPE "project_details": each row asks for PROJECT-level facts — project name, location,
client name, area, contract value/amount, start/completion dates, "scope of work". If the table asks for project value, scope, duration, or area, classify it as "project_details" (Major Work) even if it ALSO asks for a client contact person.

CRITICAL: The form might use different terminology instead of "Projects" or "References". 
Look for headers or preceding text like:
- "Major work done"
- "Ongoing projects"
- "Projects completed"
- "Past performance"
- "Experience Record"
If the table asks for details like "Project Cost", "Duration of Project", "Scope of Work", "Location", "Client Name", treat it as a project table regardless of the exact heading.

Look for consecutive numbered cells in a single column (e.g. [C7]='1', [C8]='2') indicating
table rows, or clear repeating column headers suggesting a project list.

Also scan any nearby text (instructions, headings, notes near the table) for an explicit
maximum row count instruction, e.g. "list only 10 projects at max", "top 5 projects",
"maximum 3 references" — extract that number if present, else null.

Return JSON:
{{
  "is_project_table": true,
  "table_type": "project_reference" | "project_details",
  "subheading": "The exact heading text found (e.g. 'Major work done', 'Past Experience'), or null",
  "start_row": 7,
  "max_rows": 10,
  "mapping": {{
    "project_name": "D",
    "client_name": "E",
    "location": "F",
    "area_sqft": "G",
    "amount": "H",
    "start_date": "I",
    "completion_date": "J",
    "contact_name": "K",
    "contact_designation": "L",
    "contact_phone": "M",
    "contact_email": "N",
    "scope_of_work": "O"
  }}
}}
Only include mapping keys for columns that actually exist as headers in this sheet — do not
invent columns. Map any column asking for "Scope of Work" to the "scope_of_work" key.
If not a project table, return {"is_project_table": false}.

CELL MAP:
{cell_map}
"""


def _clean(val) -> str:
    if val is None: return ""
    s = str(val).strip().replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'\s+', ' ', s)[:100]


def _merge_continuation_cells(ws) -> set:
    """
    Returns the set of (row, col) tuples that are NON-ANCHOR continuations of a merged
    cell range (e.g. for a B8:C8 merge, this returns {(8, 3)} for C8, but not B8).

    FIX (P0 -- silent label corruption): these cells must never be treated as a real,
    independent, fillable cell. openpyxl reports their .value as always None, which
    previously made build_sheet_cell_map mark them "[COORD]=EMPTY" -- a completely
    reasonable-looking fill target to both Pass 1 (fuzzy alias match) and GPT-4o
    vision. But write_filled_excel_multi's merge-handling logic redirects any write
    aimed at one of these cells to the merge's TOP-LEFT ANCHOR -- which is exactly
    where the field's own label text lives. The result: filling what looks like a
    normal blank answer cell silently overwrites and destroys the form's own label
    (e.g. writing "1996" into what looked like an empty cell next to "Year of
    Establishment" actually replaced the words "Year of Establishment" with "1996").
    Excluding these coordinates from the cell map entirely means neither Pass 1 nor
    vision will ever propose filling them in the first place.
    """
    continuations = set()
    for merged_range in ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                if (r, c) != (min_row, min_col):
                    continuations.add((r, c))
    return continuations


def build_sheet_cell_map(ws, ws_formulas=None) -> tuple[str, set[str]]:
    """Build a compact cell map for a single worksheet, only including cells with values and adjacent empty cells.
    Returns (cell_map_str, protected_cells_set)."""
    filled_cells = {}
    protected_cells = set()
    real_max_r = 0
    real_max_c = 0
    merge_continuations = _merge_continuation_cells(ws)

    if ws_formulas:
        for v_row, f_row in zip(ws.iter_rows(), ws_formulas.iter_rows()):
            for v_cell, f_cell in zip(v_row, f_row):
                if f_cell.data_type == 'f':
                    protected_cells.add(v_cell.coordinate)
                if v_cell.value is not None:
                    real_max_r = max(real_max_r, v_cell.row)
                    real_max_c = max(real_max_c, v_cell.column)
                    filled_cells[(v_cell.row, v_cell.column)] = _clean(v_cell.value)
    else:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    real_max_r = max(real_max_r, cell.row)
                    real_max_c = max(real_max_c, cell.column)
                    filled_cells[(cell.row, cell.column)] = _clean(cell.value)
                
    if not filled_cells:
        return "", protected_cells
        
    if ws.max_row > real_max_r or ws.max_column > real_max_c:
        print(f"[TRIM] '{ws.title}': reported {ws.max_row}x{ws.max_column}, using real {real_max_r}x{real_max_c}")
        
    max_r = min(ws.max_row, real_max_r + 2)
    max_c = min(ws.max_column, real_max_c + 2)

    # Detect horizontal merged cells as potential section headers
    section_headers = {}
    for merged_range in ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        if max_col > min_col and max_row == min_row: # Horizontal merge
            if (min_row, min_col) in filled_cells:
                text_val = filled_cells[(min_row, min_col)]
                if len(text_val) < 150:
                    section_headers[(min_row, min_col)] = text_val
        
    relevant_empty = set()
    for (r, c) in filled_cells.keys():
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = r + dr, c + dc
                if 1 <= nr <= max_r and 1 <= nc <= max_c:
                    # FIX: never surface a merge-continuation cell as "EMPTY" -- see
                    # _merge_continuation_cells docstring above.
                    if (nr, nc) not in filled_cells and (nr, nc) not in merge_continuations:
                        relevant_empty.add((nr, nc))
                        
    rows_to_output = set(r for r, c in filled_cells.keys()) | set(r for r, c in relevant_empty)
    
    lines = []
    for r in sorted(list(rows_to_output)):
        cols_in_row = set(c for r_f, c in filled_cells.keys() if r_f == r) | \
                      set(c for r_e, c in relevant_empty if r_e == r)
        if not cols_in_row:
            continue
            
        parts = []
        for c in sorted(list(cols_in_row)):
            cell = ws.cell(row=r, column=c)
            coord = cell.coordinate
            if (r, c) in section_headers:
                parts.append(f"[{coord}]='--- Section: {section_headers[(r, c)]} ---'")
            elif (r, c) in filled_cells:
                parts.append(f"[{coord}]='{filled_cells[(r, c)]}'")
            else:
                parts.append(f"[{coord}]=EMPTY")
        lines.append(" ".join(parts))
        
    return "\n".join(lines), protected_cells


# ──── Deterministic vertical-block repeating-table detector (no AI call needed) ────

FIELD_KEYWORDS = {
    "client_name": ["client name", "client referance", "client reference", "customer name"],
    "project_name": ["project name", "name of project"],
    "location": ["location"],
    "area_sqft": ["area (sqft)", "area sqft", "area"],
    "amount": ["project cost", "contract value", "project value", "value in lacs", "value"],
    "duration": ["duration"],
    "scope_of_work": ["scope of work", "scope"],
    "contact_name": ["contact person name", "concern person", "contact person"],
    "contact_designation": ["designation"],
    "contact_phone": ["contact details", "contact no", "phone", "mobile"],
    "contact_email": ["email"],
    "start_date": ["start date"],
    "completion_date": ["completion date", "end date"],
}


def _guess_field_key(sub_label: str):
    low = sub_label.lower()
    for key, kws in FIELD_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                return key
    return None


def _col_letter(idx: int) -> str:
    name = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def detect_vertical_repeating_blocks(ws) -> list[dict]:
    label_merges = []
    for mr in ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = mr.bounds
        if max_row > min_row:
            anchor = ws.cell(row=min_row, column=min_col)
            if anchor.value:
                label_merges.append({
                    "min_row": min_row, "max_row": max_row,
                    "min_col": min_col, "max_col": max_col,
                    "text": str(anchor.value).strip()
                })

    def strip_trailing_number(s: str) -> str:
        return re.sub(r'[\s\-\u2013_:]*\d+\s*$', '', s).strip().lower()

    groups: dict = {}
    for lm in label_merges:
        key = strip_trailing_number(lm["text"])
        if key:
            groups.setdefault(key, []).append(lm)

    detected = []
    for key, members in groups.items():
        if len(members) < 2: continue
        members.sort(key=lambda m: m["min_row"])
        rows_per_block = members[0]["max_row"] - members[0]["min_row"] + 1
        sub_label_col = members[0]["max_col"] + 1
        sub_labels = {}
        for offset in range(rows_per_block):
            r = members[0]["min_row"] + offset
            cell = ws.cell(row=r, column=sub_label_col)
            if cell.value:
                sub_labels[offset] = str(cell.value).strip()

        field_row_offsets = {}
        for offset, sub_label in sub_labels.items():
            fk = _guess_field_key(sub_label)
            if fk and fk not in field_row_offsets:
                field_row_offsets[fk] = offset
        
        answer_col_idx = sub_label_col + 1
        contact_ish = {"contact_name", "contact_phone", "contact_email", "contact_designation"}
        project_ish = {"amount", "scope_of_work", "project_name", "duration", "area_sqft", "location"}
        
        if any(k in field_row_offsets for k in project_ish):
            table_type = "project_details"
        else:
            table_type = "project_reference"

        detected.append({
            "subheading": members[0]["text"],
            "table_type": table_type,
            "layout": "vertical",
            "block_start_rows": [m["min_row"] for m in members],
            "rows_per_block": rows_per_block,
            "answer_column": _col_letter(answer_col_idx),
            "field_row_offsets": field_row_offsets,
        })
    return detected


def excel_to_all_sheet_maps(file_bytes: bytes) -> tuple[dict, dict, dict, dict]:
    wb_values = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    wb_formulas = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    maps = {}
    protected = {}
    states = {}
    vertical_blocks = {}
    for sheet_name in wb_values.sheetnames:
        ws = wb_values[sheet_name]
        ws_formulas = wb_formulas[sheet_name] if sheet_name in wb_formulas.sheetnames else None
        m, p = build_sheet_cell_map(ws, ws_formulas)
        maps[sheet_name] = m
        protected[sheet_name] = p
        states[sheet_name] = ws.sheet_state
        try:
            vertical_blocks[sheet_name] = detect_vertical_repeating_blocks(ws)
        except Exception as e:
            print(f"[WARN] Vertical-block detection failed for '{sheet_name}': {e}")
            vertical_blocks[sheet_name] = []
    return maps, protected, states, vertical_blocks


# Keep old name working for anything else that imports it (single-sheet, first sheet)
def excel_to_cell_map(file_bytes: bytes) -> tuple[str, str]:
    wb_values = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    wb_formulas = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws = wb_values.active
    ws_formulas = wb_formulas.active
    m, _ = build_sheet_cell_map(ws, ws_formulas)
    return ws.title, m



SECTION_KEYWORDS = {
    "General Information": (
        "general information", "company information", "basic information", "company profile",
        "organization details", "organisation details", "contact details", "statutory details",
        "vendor details", "supplier details", "contractor details"
    ),
    "Financial Info": (
        "financial", "finance", "turnover", "annual turnover", "balance sheet", "p&l",
        "profit", "loss", "net worth", "assets", "liabilities", "working capital",
        "solvency", "banker", "income tax", "itr", "revenue"
    ),
    "Customer References": (
        "customer reference", "customer references", "client reference", "client references",
        "reference details", "client contact", "contact person"
    ),
    "Major Work Done / Projects Done": (
        "major work done", "major works done", "major projects", "projects done",
        "project details", "project history", "past projects", "completed projects",
        "ongoing projects", "past performance", "experience record", "work done",
        "scope of work", "project cost", "contract value"
    ),
    "Certificates / Licenses / Attachments": (
        "certificate", "certificates", "license", "licenses", "licence", "licences",
        "attachment", "attachments", "documents", "document list", "enclosure",
        "annexure", "upload", "attached"
    ),
}


def infer_company_section(text: str, default: str = "General Information") -> str:
    low = (text or "").lower()
    for section, keywords in SECTION_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            return section
    return default


def build_workbook_form_json(file_bytes: bytes, sheet_maps: dict | None = None) -> dict:
    """
    Build a real JSON structure from the uploaded Excel workbook. This complements
    the compact text cell map: it keeps the sheet/section/field nesting so both
    deterministic matching and GPT can search the right company-data section first.
    """
    if sheet_maps is None:
        sheet_maps, _, _, _ = excel_to_all_sheet_maps(file_bytes)

    workbook = {
        "format": "preque_openpyxl_form_structure_v1",
        "lookup_order": [
            "Use the field's section first",
            "If missing, search every other company-data section before leaving blank",
        ],
        "sheets": {},
    }

    for sheet_name, cell_map in sheet_maps.items():
        sections = {}
        current_section = "General Information"
        row_tokens = {}
        for coord, val in re.findall(r"\[([A-Z]+\d+)\]=(EMPTY|'[^']*')", cell_map):
            row = int(re.search(r"\d+", coord).group(0))
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            row_tokens.setdefault(row, []).append({"cell": coord, "value": val})

        candidates = {}
        try:
            from services.field_matcher import extract_candidates_from_map
            candidates = extract_candidates_from_map(cell_map)
        except Exception:
            candidates = {}

        for row in sorted(row_tokens):
            tokens = row_tokens[row]
            filled_texts = [t["value"] for t in tokens if t["value"] and t["value"] != "EMPTY"]
            row_text = " ".join(filled_texts)
            detected_section = infer_company_section(row_text, current_section)
            if detected_section != current_section and filled_texts:
                current_section = detected_section

            section_obj = sections.setdefault(current_section, {
                "name": current_section,
                "rows": [],
                "fillable_fields": [],
            })
            section_obj["rows"].append({
                "row": row,
                "text": row_text,
                "cells": tokens[:],
            })

            for token in tokens:
                if token["value"] != "EMPTY":
                    continue
                labels = candidates.get(token["cell"], [])
                local_text = " ".join(labels + filled_texts)
                field_section = infer_company_section(local_text, current_section)
                sections.setdefault(field_section, {
                    "name": field_section,
                    "rows": [],
                    "fillable_fields": [],
                })["fillable_fields"].append({
                    "cell": token["cell"],
                    "labels": labels,
                    "row_context": row_text,
                    "section": field_section,
                })

        workbook["sheets"][sheet_name] = {
            "sheet_name": sheet_name,
            "sections": list(sections.values()),
        }

    return workbook


def _form_fields_by_cell(sheet_form_json: dict | None) -> dict:
    fields = {}
    if not sheet_form_json:
        return fields
    for section in sheet_form_json.get("sections", []):
        for field in section.get("fillable_fields", []):
            cell = field.get("cell")
            if cell:
                fields[cell] = field
    return fields


def _is_attachment_only_request(labels: list[str], section: str = "") -> bool:
    text = " ".join([section] + [str(label) for label in labels if label]).lower()
    if not text:
        return False
    asks_for_attachment = any(token in text for token in [
        "attach", "attachment", "attached", "enclosed", "enclosure", "upload",
        "submit", "provide copy", "copy of", "supporting document"
    ])
    mentions_document = any(token in text for token in [
        "certificate", "license", "licence", "registration", "document", "annexure"
    ])
    asks_for_identifier = any(token in text for token in [
        "number", "no.", "no ", "date", "valid", "expiry", "issued", "authority",
        "name of", "details of", "gst no", "pan no"
    ])
    return (asks_for_attachment or mentions_document) and not asks_for_identifier


def _match_financial_record(labels: list[str], section: str, db: Session) -> str | None:
    from models.database import FinancialRecord
    try:
        from rapidfuzz import fuzz
    except Exception:
        fuzz = None

    text = " ".join([section] + [str(label) for label in labels if label]).lower()
    if not text:
        return None

    financial_hint = infer_company_section(text) == "Financial Info"
    financial_hint = financial_hint or any(token in text for token in [
        "turnover", "net worth", "assets", "liabilities", "profit", "loss",
        "working capital", "revenue", "balance sheet", "solvency"
    ])
    if not financial_hint:
        return None

    def norm(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', ' ', str(s or '').lower()).strip()

    norm_text = norm(text)
    best = None
    best_score = 0
    for record in db.query(FinancialRecord).all():
        if not record.value:
            continue
        metric = norm(record.metric_label or record.metric_key or "")
        if not metric:
            continue
        metric_score = fuzz.token_set_ratio(norm_text, metric) if fuzz else (100 if metric in norm_text else 0)
        
        # Smart keyword detection for common typos and variations
        if ("turnover" in norm_text or "turn over" in norm_text or "revenue" in norm_text) and "turnover" in metric:
            metric_score = 100
        elif ("profit" in norm_text) and "profit" in metric:
            metric_score = 100
        elif ("worth" in norm_text) and "worth" in metric:
            metric_score = 100
        elif ("asset" in norm_text) and "asset" in metric:
            metric_score = 100
        elif ("liabilit" in norm_text) and "liabilit" in metric:
            metric_score = 100

        year_match = False
        for variant in _fiscal_year_variants(record.fiscal_year or ""):
            if norm(variant) and norm(variant) in norm_text:
                year_match = True
                break
        score = metric_score + (35 if year_match else 0)
        if score > best_score:
            best = record
            best_score = score

    if not best:
        return None

    has_year_hint = bool(re.search(r'\b(?:fy\s*)?\d{2,4}\s*[-/]\s*\d{2,4}\b', text, re.IGNORECASE))
    best_year_match = any(norm(variant) in norm_text for variant in _fiscal_year_variants(best.fiscal_year or ""))
    if has_year_hint and not best_year_match:
        return None
    if best_score < (105 if has_year_hint else 88):
        return None

    unit_str = f" {best.unit}" if best.unit else ""
    return f"{best.value}{unit_str}"


def _match_company_context_value(labels: list[str], section: str, company_context: dict) -> str | None:
    try:
        from rapidfuzz import fuzz
    except Exception:
        fuzz = None

    def norm(text: str) -> str:
        return re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()

    query = norm(" ".join([section] + [str(label) for label in labels if label]))
    if not query:
        return None

    def iter_leaves(value, path: str = ""):
        if isinstance(value, dict):
            for key, nested in value.items():
                next_path = f"{path} {key}".strip()
                yield from iter_leaves(nested, next_path)
        elif isinstance(value, list):
            for item in value:
                yield from iter_leaves(item, path)
        else:
            leaf_value = str(value or "").strip()
            if leaf_value:
                yield path, leaf_value

    best_value = None
    best_score = 0
    section_order = []
    if section and section in company_context:
        section_order.append(section)
    section_order.extend([name for name in company_context.keys() if name not in section_order and name != "Lookup Guidance"])

    for section_name in section_order:
        section_data = company_context.get(section_name)
        for path, leaf_value in iter_leaves(section_data, section_name):
            candidate = norm(path)
            if not candidate:
                continue
            score = fuzz.token_set_ratio(query, candidate) if fuzz else (100 if candidate in query or query in candidate else 0)
            leaf_norm = norm(leaf_value)
            if leaf_norm and (leaf_norm in query or query in leaf_norm):
                score += 10
            if section_name and norm(section_name) in query:
                score += 5
            if score > best_score:
                best_score = score
                best_value = leaf_value

    if best_score >= 80:
        return best_value
    return None

def _find_libreoffice() -> str:
    import shutil as _shutil, platform, glob
    lo = _shutil.which("libreoffice") or _shutil.which("soffice")
    if lo: return lo
    if platform.system() == "Windows":
        candidates = glob.glob(r"C:\Program Files\LibreOffice*\program\soffice.exe") + \
                     glob.glob(r"C:\Program Files (x86)\LibreOffice*\program\soffice.exe")
        for p in candidates:
            if os.path.exists(p): return p
    elif platform.system() == "Darwin":
        for p in ["/Applications/LibreOffice.app/Contents/MacOS/soffice",
                  "/opt/homebrew/bin/libreoffice"]:
            if os.path.exists(p): return p
    raise RuntimeError(
        "LibreOffice not found. Install from https://libreoffice.org\n"
        "Or set LIBREOFFICE_PATH in your .env file."
    )


def excel_to_images_per_sheet(file_bytes: bytes, filename: str) -> tuple[dict, str]:
    """
    Render each sheet of the Excel workbook to its own PNG image(s) via LibreOffice + pdf2image.
    Returns ({sheet_name: [image_paths]}, tmpdir)

    Strategy: split the workbook into one temp .xlsx per sheet (openpyxl copy),
    convert each to PDF individually so page-to-sheet mapping is exact, then rasterize.
    """
    import platform
    lo_path = os.getenv("LIBREOFFICE_PATH") or _find_libreoffice()
    tmpdir = tempfile.mkdtemp()

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    sheet_names = wb.sheetnames

    lo_profile = os.path.join(tmpdir, "lo_profile")
    os.makedirs(lo_profile, exist_ok=True)
    profile_uri = "file:///" + lo_profile.replace("\\", "/")

    env = os.environ.copy()
    if platform.system() == "Windows":
        env["PATH"] = os.path.dirname(lo_path) + os.pathsep + env.get("PATH", "")

    images_by_sheet = {}

    for sheet_name in sheet_names:
        # Build a single-sheet workbook copy so LibreOffice renders exactly this tab.
        single_wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
        for other in list(single_wb.sheetnames):
            if other != sheet_name:
                del single_wb[other]

        # Ensure the sheet is visible before saving, as a workbook cannot have only hidden sheets
        single_wb[sheet_name].sheet_state = 'visible'

        safe_sheet = re.sub(r'[^\w\-]', '_', sheet_name)
        xlsx_path = os.path.join(tmpdir, f"{safe_sheet}.xlsx")
        single_wb.save(xlsx_path)
        single_wb.close()

        sheet_outdir = os.path.join(tmpdir, safe_sheet)
        os.makedirs(sheet_outdir, exist_ok=True)

        result = subprocess.run(
            [lo_path, "--headless", "--norestore", "--nofirststartwizard",
             f"-env:UserInstallation={profile_uri}",
             "--convert-to", "pdf", "--outdir", sheet_outdir, xlsx_path],
            capture_output=True, text=True, timeout=120, env=env
        )
        if result.returncode != 0:
            print(f"[WARN] LibreOffice failed for sheet '{sheet_name}': {result.stderr or result.stdout}")
            images_by_sheet[sheet_name] = []
            continue

        pdfs = [f for f in os.listdir(sheet_outdir) if f.endswith(".pdf")]
        if not pdfs:
            images_by_sheet[sheet_name] = []
            continue

        from pdf2image import convert_from_path
        pages = convert_from_path(os.path.join(sheet_outdir, pdfs[0]), dpi=150)
        paths = []
        for i, page in enumerate(pages):
            p = os.path.join(sheet_outdir, f"page_{i}.png")
            page.save(p, "PNG")
            paths.append(p)
        images_by_sheet[sheet_name] = paths

    wb.close()
    return images_by_sheet, tmpdir


def classify_sheet(sheet_name: str, cell_map: str) -> str:
    """Ask GPT-4o (text-only, cheap) whether a sheet needs filling or is informational."""
    if not cell_map.strip():
        return "INFO_ONLY"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": SHEET_CLASSIFY_PROMPT.format(
                    sheet_name=sheet_name,
                    cell_map=cell_map[:6000]  # keep classification call cheap
                )
            }]
        )
        raw = response.choices[0].message.content.strip().upper()
        return "FILLABLE" if "FILLABLE" in raw else "INFO_ONLY"
    except Exception as e:
        print(f"[WARN] Classification failed for '{sheet_name}': {e} — defaulting to FILLABLE")
        return "FILLABLE"


def classify_sheet_columns(sheet_name: str, cell_map: str) -> tuple[list[str], list[str]]:
    """Ask GPT-4o to identify which columns are for internal client use vs vendor use."""
    if not cell_map.strip():
        return [], []
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": COLUMN_CLASSIFY_PROMPT.format(
                    sheet_name=sheet_name,
                    cell_map=cell_map[:6000]
                )
            }]
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        return data.get("fillable_columns", []), data.get("reserved_columns", [])
    except Exception as e:
        print(f"[WARN] Column classification failed for '{sheet_name}': {e} — defaulting to all columns fillable")
        return [], []


def detect_repeating_table(sheet_name: str, cell_map: str) -> dict:
    """Ask GPT-4o-mini if this sheet is a repeating table (like Project History)."""
    if not cell_map.strip():
        return {"is_project_table": False}
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": TABLE_DETECT_PROMPT.format(
                    sheet_name=sheet_name,
                    cell_map=cell_map[:6000]
                )
            }]
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[WARN] Table detection failed for '{sheet_name}': {e}")
        return {"is_project_table": False}



PROJECT_TABLE_FIELDS = {
    "project_name", "client_name", "location", "area_sqft", "amount",
    "start_date", "completion_date", "duration", "scope_of_work",
    "contact_name", "contact_designation", "contact_phone", "contact_email"
}


def normalize_detected_table_info(table_info: dict, cell_map: str) -> dict:
    if not table_info or not table_info.get("is_project_table"):
        return table_info or {"is_project_table": False}

    mapping = table_info.get("mapping") or {}
    normalized = {}
    for key, value in mapping.items():
        key_s = str(key or "").strip()
        val_s = str(value or "").strip()
        if re.match(r'^[A-Z]{1,3}$', key_s) and val_s:
            guessed = _guess_field_key(val_s)
            if guessed:
                normalized[guessed] = key_s
        elif key_s in PROJECT_TABLE_FIELDS and re.match(r'^[A-Z]{1,3}$', val_s):
            normalized[key_s] = val_s

    if normalized:
        table_info["mapping"] = normalized

    subheading_text = str(table_info.get("subheading") or "").lower()
    mapped_keys = set((table_info.get("mapping") or {}).keys())
    project_markers = SECTION_KEYWORDS["Major Work Done / Projects Done"]
    reference_markers = SECTION_KEYWORDS["Customer References"]
    project_keys = {"project_name", "location", "area_sqft", "amount", "duration", "scope_of_work", "start_date", "completion_date"}
    contact_keys = {"contact_name", "contact_designation", "contact_phone", "contact_email"}

    if any(marker in subheading_text for marker in project_markers):
        table_info["table_type"] = "project_details"
    elif any(marker in subheading_text for marker in reference_markers):
        table_info["table_type"] = "project_reference"
    elif len(mapped_keys & project_keys) >= len(mapped_keys & contact_keys):
        table_info["table_type"] = "project_details"

    return table_info

def ai_fill_sheet(
    sheet_name: str,
    b64_images: list[str],
    cell_map: str,
    company_context: dict,
    protected_cells: set[str] = None,
    reserved_cols: list[str] = None,
    fillable_cols: list[str] = None,
    sheet_form_json: dict | None = None
) -> dict:
    """Fill ONE sheet using its own image(s) + its own cell map. Returns {cell_address: value}."""
    if not b64_images or not cell_map.strip():
        return {}

    all_fills = {}
    seen_cells = set()

    for i, b64 in enumerate(b64_images):
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}
            },
            {
                "type": "text",
                "text": (
                    f"SHEET NAME: {sheet_name}\n\n"
                    f"CELL MAP (exact coordinates for every cell on THIS SHEET):\n"
                    f"{cell_map}\n\n"
                    f"OPENPYXL FORM STRUCTURE JSON (sections and fillable cells for THIS SHEET):\n"
                    f"{json.dumps(sheet_form_json or {}, indent=2)}\n\n"
                    f"COMPANY DATA JSON (already grouped by section):\n{json.dumps(company_context, indent=2)}\n\n"
                    "Look at the image to understand this sheet visually. "
                    "Use the cell map to get exact cell coordinates for THIS SHEET ONLY. "
                    "Return JSON mapping cell addresses to values for ALL fillable fields on this sheet."
                )
            }
        ]
        try:
            response = openai_client.chat.completions.create(
                model=VISION_MODEL,
                max_tokens=4000,
                messages=[
                    {"role": "system", "content": FILL_SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ]
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            page_fills = json.loads(raw)
            new_fills = {}
            for k, v in page_fills.items():
                k = k.strip()
                if not re.match(r'^[A-Z]{1,3}\d+$', k) or not v or k in seen_cells:
                    continue
                if protected_cells and k in protected_cells:
                    continue
                
                col_letter = re.match(r'^([A-Z]+)', k).group(1)
                if reserved_cols and col_letter in reserved_cols:
                    continue
                if fillable_cols and reserved_cols and col_letter not in fillable_cols:
                    continue
                    
                new_fills[k] = str(v)
                
            seen_cells.update(new_fills.keys())
            all_fills.update(new_fills)
            print(f"  [GPT-4o] Sheet '{sheet_name}' page {i+1}: filled {len(new_fills)} cells")

        except json.JSONDecodeError as e:
            print(f"  [GPT-4o] Sheet '{sheet_name}' page {i+1}: JSON parse error — {e}")
        except Exception as e:
            print(f"  [GPT-4o] Sheet '{sheet_name}' page {i+1}: Error — {e}")

    return all_fills


def ai_fill_workbook(
    file_bytes: bytes,
    filename: str,
    company_context: dict,
    db: Session,
    workbook_form_json: dict | None = None
) -> tuple[dict, dict, str, dict, dict, list]:
    from services.field_matcher import FieldMatcher, extract_candidates_from_map
    try:
        matcher = FieldMatcher(db)
    except Exception as e:
        print("Could not load matcher:", e)
        matcher = None

    sheet_maps, protected_cells_by_sheet, sheet_states, vertical_blocks_by_sheet = excel_to_all_sheet_maps(file_bytes)
    if workbook_form_json is None:
        workbook_form_json = build_workbook_form_json(file_bytes, sheet_maps)

    sheet_status = {}
    sheet_column_policies = {}
    fillable_sheets = []
    for sheet_name, cmap in sheet_maps.items():
        state = sheet_states.get(sheet_name, 'visible')
        if state in ('hidden', 'veryHidden'):
            status = 'INFO_ONLY'
            print(f"[Classify] '{sheet_name}' is {state} -> skipping classification, marking INFO_ONLY")
        else:
            status = classify_sheet(sheet_name, cmap)
            print(f"[Classify] '{sheet_name}' -> {status}")
            
        sheet_status[sheet_name] = status
        
        if status == "FILLABLE":
            fillable_sheets.append(sheet_name)
            f_cols, r_cols = classify_sheet_columns(sheet_name, cmap)
            sheet_column_policies[sheet_name] = {"fillable": f_cols, "reserved": r_cols}
            print(f"[Classify Columns] '{sheet_name}' -> fillable: {f_cols}, reserved: {r_cols}")

    if not fillable_sheets:
        return {}, sheet_status, "", {}, {}, []

    images_by_sheet, tmpdir = excel_to_images_per_sheet(file_bytes, filename)

    all_fills = {}
    fill_sources = {}
    match_summary = {"alias_matched": 0, "ai_guessed": 0, "sheets_skipped_vision_call": []}
    pending_project_tables = []

    try:
        for sheet_name in fillable_sheets:
            cmap = sheet_maps[sheet_name]
            resolved_cells = {}
            policy = sheet_column_policies.get(sheet_name, {})
            reserved_cols = policy.get("reserved", [])
            fillable_cols = policy.get("fillable", [])
            sheet_form_json = (workbook_form_json or {}).get("sheets", {}).get(sheet_name, {})
            fields_by_cell = _form_fields_by_cell(sheet_form_json)
            
            def is_allowed_col(coord):
                col_letter = re.match(r'^([A-Z]+)', coord).group(1)
                if reserved_cols and col_letter in reserved_cols:
                    return False
                if fillable_cols and reserved_cols and col_letter not in fillable_cols:
                    return False
                return True

            if sheet_name not in protected_cells_by_sheet:
                protected_cells_by_sheet[sheet_name] = set()

            vblocks = vertical_blocks_by_sheet.get(sheet_name, [])
            for vb in vblocks:
                print(f"  [Vertical Table Mode] '{sheet_name}' section '{vb['subheading']}' -> "
                      f"{len(vb['block_start_rows'])} repeating blocks detected deterministically "
                      f"(type={vb['table_type']})")
                pending_project_tables.append({
                    "sheet_name": sheet_name,
                    "table_type": vb["table_type"],
                    "subheading": vb["subheading"],
                    "layout": "vertical",
                    "answer_column": vb["answer_column"],
                    "block_start_rows": vb["block_start_rows"],
                    "rows_per_block": vb["rows_per_block"],
                    "field_row_offsets": vb["field_row_offsets"],
                    "available_row_count": len(vb["block_start_rows"]),
                    "max_rows": None,
                })
                for block_start in vb["block_start_rows"]:
                    for offset in range(vb["rows_per_block"]):
                        protected_cells_by_sheet[sheet_name].add(f"{vb['answer_column']}{block_start + offset}")

            if not vblocks:
                table_info = normalize_detected_table_info(detect_repeating_table(sheet_name, cmap), cmap)
                if table_info.get("is_project_table"):
                    print(f"  [Table Mode] '{sheet_name}' is a Project Table. Adding to pending_project_tables.")
                    start_row = table_info.get("start_row", 1)
                    mapping = table_info.get("mapping", {})
                    
                    available_rows = []
                    first_col = next(iter(mapping.values())) if mapping else None
                    if first_col:
                        r = start_row
                        while f"[{first_col}{r}]=EMPTY" in cmap:
                            available_rows.append(r)
                            r += 1
                    
                    pending_project_tables.append({
                        "sheet_name": sheet_name,
                        "table_type": table_info.get("table_type", "project_details"),
                        "subheading": table_info.get("subheading"),
                        "start_row": start_row,
                        "mapping": mapping,
                        "available_row_count": len(available_rows),
                        "max_rows": table_info.get("max_rows")
                    })
                    
                    for r in available_rows:
                        for c_letter in mapping.values():
                            protected_cells_by_sheet[sheet_name].add(f"{c_letter}{r}")

            if matcher:
                candidates = extract_candidates_from_map(cmap)
                for coord, labels in candidates.items():
                    if coord in protected_cells_by_sheet.get(sheet_name, set()):
                        continue
                    if not is_allowed_col(coord):
                        continue
                    field_context = fields_by_cell.get(coord, {})
                    context_labels = list(dict.fromkeys(
                        labels +
                        field_context.get("labels", []) +
                        [field_context.get("row_context", ""), field_context.get("section", "")]
                    ))
                    section = field_context.get("section", "")

                    if _is_attachment_only_request(context_labels, section):
                        resolved_cells[coord] = "Attached"
                        fill_sources[f"{sheet_name}!{coord}"] = "attachment_default"
                        match_summary["alias_matched"] += 1
                        continue

                    financial_value = _match_financial_record(context_labels, section, db)
                    if financial_value:
                        resolved_cells[coord] = financial_value
                        fill_sources[f"{sheet_name}!{coord}"] = "financial_match"
                        match_summary["alias_matched"] += 1
                        continue

                    context_value = _match_company_context_value(context_labels, section, company_context)
                    if context_value:
                        resolved_cells[coord] = context_value
                        fill_sources[f"{sheet_name}!{coord}"] = "context_match"
                        match_summary["alias_matched"] += 1
                        continue

                    best_match = None
                    for label in context_labels:
                        m = matcher.match(label, threshold=88)
                        if m and (not best_match or m.score > best_match.score):
                            best_match = m
                    if best_match:
                        resolved_cells[coord] = best_match.value
                        fill_sources[f"{sheet_name}!{coord}"] = "alias_match"
                        match_summary["alias_matched"] += 1

            protected_set = protected_cells_by_sheet.get(sheet_name, set())
            filtered_cmap_lines = []
            for line in cmap.split('\n'):
                for coord in resolved_cells.keys():
                    line = re.sub(fr'\[{coord}\]=EMPTY', f"[{coord}]='(Already Answered)'", line)
                
                def remove_reserved(m):
                    coord = m.group(1)
                    if not is_allowed_col(coord):
                        return ""
                    if coord in protected_set:
                        return "[" + coord + "]='(Reserved for project/reference picker)'"
                    return m.group(0)
                line = re.sub(r'\[([A-Z]+\d+)\]=EMPTY', remove_reserved, line)
                line = re.sub(r'\s+', ' ', line).strip()
                
                if line:
                    filtered_cmap_lines.append(line)
            filtered_cmap = "\n".join(filtered_cmap_lines)

            if "EMPTY" not in filtered_cmap:
                print(f"[Pass1] Sheet '{sheet_name}' fully resolved without vision call")
                match_summary["sheets_skipped_vision_call"].append(sheet_name)
                all_fills[sheet_name] = resolved_cells
                continue

            b64_images = []
            for path in images_by_sheet.get(sheet_name, []):
                with open(path, "rb") as f:
                    b64_images.append(base64.standard_b64encode(f.read()).decode("utf-8"))
            
            ai_fills = ai_fill_sheet(
                sheet_name, b64_images, filtered_cmap, company_context,
                protected_cells=protected_cells_by_sheet.get(sheet_name, set()),
                reserved_cols=reserved_cols,
                fillable_cols=fillable_cols,
                sheet_form_json=sheet_form_json
            )
            
            for k in ai_fills.keys():
                fill_sources[f"{sheet_name}!{k}"] = "gpt4o_vision"
            match_summary["ai_guessed"] += len(ai_fills)

            all_fills[sheet_name] = {**resolved_cells, **ai_fills}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    combined_map = "\n".join(
        f"--- SHEET: {sn} ---\n{sheet_maps[sn]}" for sn in fillable_sheets
    )
    return all_fills, sheet_status, combined_map, match_summary, fill_sources, pending_project_tables


def write_filled_excel_multi(original_bytes: bytes, sheet_fills: dict) -> bytes:
    """
    Write filled values back to their correct sheets, preserving all formatting.
    sheet_fills: {sheet_name: {cell_addr: value}}
    """
    wb = openpyxl.load_workbook(io.BytesIO(original_bytes))
    for sheet_name, fills in sheet_fills.items():
        if sheet_name not in wb.sheetnames:
            print(f"[WARN] Sheet '{sheet_name}' not found in workbook — skipping")
            continue
        ws = wb[sheet_name]
        protected_cells = {c.coordinate for row in ws.iter_rows() for c in row if c.data_type == 'f'}
        
        for addr, value in fills.items():
            if addr in protected_cells:
                print(f"[SKIP] {sheet_name}!{addr} is a formula cell, not overwriting")
                continue
            try:
                cell = ws[addr]
                if type(cell).__name__ == 'MergedCell':
                    anchor_cell = None
                    for merged_range in ws.merged_cells.ranges:
                        if cell.coordinate in merged_range:
                            top_left = merged_range.coord.split(':')[0]
                            anchor_cell = ws[top_left]
                            break
                    anchor_is_blank = anchor_cell is not None and (
                        anchor_cell.value is None or str(anchor_cell.value).strip() == ""
                    )
                    if anchor_is_blank:
                        anchor_cell.value = value
                    else:
                        anchor_desc = f"{anchor_cell.coordinate}='{anchor_cell.value}'" if anchor_cell else "unknown"
                        print(f"[SKIP] {sheet_name}!{addr} is a merged-cell remnant whose anchor "
                              f"already holds label text ({anchor_desc}) -- refusing to overwrite it")
                else:
                    cell.value = value
            except Exception as e:
                print(f"[WARN] Could not write {sheet_name}!{addr}: {e}")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def write_filled_excel(original_bytes: bytes, sheet_name: str, cell_fills: dict) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(original_bytes))
    ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
    for addr, value in cell_fills.items():
        try:
            ws[addr] = value
        except Exception as e:
            print(f"[WARN] Could not write {addr}: {e}")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _fiscal_year_variants(fy: str) -> list[str]:
    variants = {fy}
    m = re.match(r'^FY\s*(\d{2})-(\d{2})$', fy.strip())
    if m:
        y1, y2 = m.groups()
        variants.add(f"20{y1}-20{y2}")
        variants.add(f"20{y1}-{y2}")
        variants.add(f"FY 20{y1}-{y2}")
        variants.add(f"{y1}-{y2}")
        variants.add(f"FY {y1}-{y2}")
    m2 = re.match(r'^(\d{4})-(\d{4})$', fy.strip())
    if m2:
        y1, y2 = m2.groups()
        variants.add(f"FY{y1[-2:]}-{y2[-2:]}")
        variants.add(f"FY {y1[-2:]}-{y2[-2:]}")
        variants.add(f"{y1[-2:]}-{y2[-2:]}")
    return list(variants)


def build_company_context(db) -> dict:
    from models.database import CompanyField, FinancialRecord, ProjectReference, ProjectFile
    def _clean_dict_value(value):
        if value is None: return ""
        if isinstance(value, str): return value.strip()
        return value

    def _project_ref_payload(ref: ProjectReference) -> dict:
        return {
            "project_name": _clean_dict_value(ref.project_name),
            "client_name": _clean_dict_value(ref.client_name),
            "region": _clean_dict_value(ref.region),
            "location": _clean_dict_value(ref.location),
            "area_sqft": _clean_dict_value(ref.area_sqft),
            "consultant": _clean_dict_value(ref.consultant),
            "pmc": _clean_dict_value(ref.pmc),
            "project_sector": _clean_dict_value(ref.project_sector),
            "project_type": _clean_dict_value(ref.project_type),
            "project_value": _clean_dict_value(ref.project_value),
            "status": _clean_dict_value(ref.status),
            "start_date": _clean_dict_value(ref.start_date),
            "end_date": _clean_dict_value(ref.end_date),
            "client_rep_name": _clean_dict_value(ref.client_rep_name),
            "client_rep_designation": _clean_dict_value(ref.client_rep_designation),
            "client_rep_email": _clean_dict_value(ref.client_rep_email),
            "client_rep_phone": _clean_dict_value(ref.client_rep_phone),
            "certifications": _clean_dict_value(ref.certifications),
        }

    fields = db.query(CompanyField).all()
    financials = db.query(FinancialRecord).all()
    references = db.query(ProjectReference).all()
    documents = db.query(ProjectFile).filter(ProjectFile.source_module == "document").all()

    ctx = {
        "General Information": {},
        "Financial Info": {},
        "Customer References": [],
        "Major Work Done / Projects Done": [],
        "Certificates / Licenses / Attachments": [],
        "Lookup Guidance": "Search the named section first. If the answer is not there, search the full company data across every section before leaving the cell blank.",
    }

    for field in fields:
        if not field.value:
            continue
        section_name = "General Information"
        label = field.field_label or ""
        category = (field.category or "").lower()
        label_lower = label.lower()
        if "financial" in category or any(token in label_lower for token in ["turnover", "balance sheet", "profit", "loss", "assets", "liability", "ebitda", "income", "revenue"]):
            section_name = "Financial Info"
        elif any(token in label_lower for token in ["certificate", "license", "licence", "attachment", "document", "upload"]):
            section_name = "Certificates / Licenses / Attachments"
        if isinstance(ctx[section_name], list):
            ctx[section_name].append({
                "label": label,
                "value": field.value,
                "document_link": field.document_link or "",
                "category": field.category or "",
            })
        else:
            ctx[section_name][label] = field.value

    if financials:
        for f in financials:
            if not f.value:
                continue
            unit_str = f" {f.unit}" if f.unit else ""
            for variant_year in _fiscal_year_variants(f.fiscal_year):
                ctx["Financial Info"].setdefault(variant_year, {})
                ctx["Financial Info"][variant_year][f.metric_label] = f"{f.value}{unit_str}"
        ctx["Financials"] = ctx["Financial Info"]

    for ref in references:
        payload = _project_ref_payload(ref)
        contact_ready = any(payload.get(key) for key in ("client_rep_name", "client_rep_designation", "client_rep_email", "client_rep_phone"))
        project_ready = any(payload.get(key) for key in ("project_name", "client_name", "location", "area_sqft", "project_value", "start_date", "end_date"))

        if contact_ready:
            ctx["Customer References"].append(payload)
        if project_ready:
            ctx["Major Work Done / Projects Done"].append(payload)

    for doc in documents:
        ctx["Certificates / Licenses / Attachments"].append({
            "name": doc.name,
            "doc_type": doc.doc_type,
            "tags": doc.tags or [],
            "has_file": bool(doc.filename),
            "sharepoint_link": doc.sharepoint_link or "",
        })

    return ctx


def get_doc_checklist(text: str, db) -> list:
    from models.database import ProjectFile
    docs = db.query(ProjectFile).filter(ProjectFile.source_module == "document").all()
    # FIX (P1): removed the hardcoded client-specific LOA names ("Taj Hotel LOA",
    # "UBS LOA", "German Consulate LOA") that used to be blindly attached to every
    # single client's checklist whenever the word "completion" appeared anywhere in
    # the form -- nonsensical for any client other than the ones those LOAs actually
    # belong to. Those now map to the generic, reusable doc types instead. Added an
    # "msme" trigger (there was previously no way to ever surface this even though
    # many vendor forms explicitly ask for it), and a working "bank statement"
    # trigger so that DOC_TYPES's existing "Bank Statement" entry is reachable at
    # all (it previously had no trigger word pointing to it -- dead code).
    trigger_map = {
        "gst": ["GST Registration Certificate"],
        "pan": ["Company PAN Card"],
        "msme": ["MSME Registration Certificate"],
        "udyam": ["MSME Registration Certificate"],
        "incorporation": ["Certificate of Incorporation"],
        "iso": ["ISO 45001 Certificate"],
        "turnover": ["Balance Sheet FY 2023-24","Balance Sheet FY 2022-23","Balance Sheet FY 2021-22"],
        "balance": ["Balance Sheet FY 2023-24","Balance Sheet FY 2022-23"],
        "pf": ["PF Registration Certificate"],
        "esi": ["ESI Registration Certificate"],
        "insurance": ["Insurance Certificate"],
        "solvency": ["Solvency Certificate"],
        "quality": ["ISO 45001 Certificate","Quality Policy Document"],
        "organisation": ["Organisation Chart"],
        "organization": ["Organisation Chart"],
        "equipment": ["Plant & Equipment List"],
        "safety": ["EHS Safety Programme"],
        "ohsas": ["EHS Safety Programme"],
        "income tax": ["ITR Certificate"],
        "bank statement": ["Bank Statement"],
        "banker credit": ["Bank Statement"],
        "completion certificate": ["Project Completion Certificate"],
        "appreciation": ["Client Appreciation Letter"],
        "work order": ["Work Order / LOA"],
        "loa": ["Work Order / LOA"],
    }
    mentioned = {"GST Registration Certificate","Company PAN Card","Certificate of Incorporation"}
    tl = text.lower()
    for trigger, docs_list in trigger_map.items():
        if trigger in tl:
            mentioned.update(docs_list)
    checklist, seen = [], set()
    for doc in docs:
        if doc.name in mentioned and doc.name not in seen:
            seen.add(doc.name)
            checklist.append({
                "id": doc.id, "name": doc.name, "doc_type": doc.doc_type,
                "has_file": bool(doc.filename),
                "sharepoint_link": doc.sharepoint_link,
                "download_url": f"/api/documents/download/{doc.id}" if doc.filename else None
            })
    return checklist


# â”€â”€ Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/history")
def get_form_history(db: Session = Depends(get_db)):
    forms = db.query(FilledForm).order_by(FilledForm.created_at.desc()).limit(50).all()
    return {"forms": [{k: v for k, v in f.__dict__.items() if not k.startswith("_")} for f in forms]}


@router.get("/{form_id}")
def get_form(form_id: int, db: Session = Depends(get_db)):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form: raise HTTPException(404, "Form not found")
    return {k: v for k, v in form.__dict__.items() if not k.startswith("_")}


@router.post("/{form_id}/save-answers")
def save_human_answers(form_id: int, answers: dict, db: Session = Depends(get_db)):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form: raise HTTPException(404, "Form not found")
    merged = dict(form.filled_data or {})
    merged.update(answers)
    form.filled_data = merged
    form.unknown_fields = [f for f in (form.unknown_fields or []) if f not in answers]
    db.commit()
    return {"updated": len(answers), "remaining_unknown": len(form.unknown_fields)}


def _rebuild_filled_bytes(form) -> bytes:
    """Reconstruct sheet_fills from stored 'Sheet!Cell' keys and write to original file."""
    orig_path = os.path.join(UPLOAD_DIR, form.original_filename)
    if not os.path.exists(orig_path):
        raise HTTPException(404, "Original file not found")
    with open(orig_path, "rb") as f:
        original_bytes = f.read()

    sheet_fills = {}
    for key, data in (form.filled_data or {}).items():
        value = data.get("value") if isinstance(data, dict) else data
        if "!" in key:
            sheet_name, cell = key.split("!", 1)
        else:
            # legacy single-sheet data â€” fall back to first sheet
            wb_tmp = openpyxl.load_workbook(io.BytesIO(original_bytes), read_only=True)
            sheet_name = wb_tmp.sheetnames[0]
            wb_tmp.close()
            cell = key
        if re.match(r'^[A-Z]{1,3}\d+$', cell):
            sheet_fills.setdefault(sheet_name, {})[cell] = value

    return write_filled_excel_multi(original_bytes, sheet_fills)


@router.get("/{form_id}/download")
def download_filled_form(form_id: int, db: Session = Depends(get_db)):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form: raise HTTPException(404, "Form not found")
    filled_bytes = _rebuild_filled_bytes(form)
    out_path = os.path.join(OUTPUT_DIR, f"filled_{form_id}_{form.original_filename}")
    with open(out_path, "wb") as f:
        f.write(filled_bytes)
    return FileResponse(out_path, filename=f"filled_{form.original_filename}")


@router.get("/{form_id}/preview")
def preview_filled_form(form_id: int, db: Session = Depends(get_db)):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form: raise HTTPException(404, "Form not found")
    filled_bytes = _rebuild_filled_bytes(form)
    out_path = os.path.join(OUTPUT_DIR, f"filled_{form_id}_{form.original_filename}")
    with open(out_path, "wb") as f:
        f.write(filled_bytes)

    try:
        data = read_excel_preview(out_path)
        return {"form_id": form_id, "name": form.original_filename, "sheets": data}
    except Exception as e:
        raise HTTPException(500, f"Could not generate preview: {str(e)}")









