"""Deterministic answers for common pre-qualification questions.

Nothing here calls an AI model. A question's text (plus the question above it, for sub-rows such as
"Design Section" under "Man power") is matched against fixed patterns and answered from the company
database, so the same form fills the same way whether or not Gemini is available.
"""
import re
from typing import Dict, List, Optional


def norm(text: str) -> str:
    t = re.sub(r"[^a-z0-9&/]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


class Facts:
    """Company field values by field_key (non-empty only), with label/alias lookup."""

    def __init__(self, fields):
        self.by_key: Dict[str, str] = {}
        self.fields = []
        for f in fields:
            val = (f.value or "").strip()
            if not val or val.lower() in ("none", "n/a"):
                continue
            self.by_key[f.field_key] = val
            self.fields.append(f)

    def get(self, *keys) -> Optional[str]:
        for k in keys:
            if k in self.by_key:
                return self.by_key[k]
            # field keys such as "type_of_firm_(proprietary_firm__...)" are long: allow a prefix
            for key, v in self.by_key.items():
                if key.startswith(k):
                    return v
        return None

    def num(self, key) -> Optional[int]:
        v = self.get(key)
        if v is None:
            return None
        m = re.search(r"\d[\d,]*", v)
        return int(m.group(0).replace(",", "")) if m else None


def _join(*parts):
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


# (rule name, pattern on the question text, optional pattern the whole context must ALSO match, resolver)
MANPOWER_CTX = r"man ?power|manpower|staff|employee|personnel|strength|labou?r|workforce"

RULES = [
    ("firm_name", r"\bname of (the )?(firm|company|organi[sz]ation|contractor|vendor|supplier|agency)\b|\bfirm name\b|\bfull company name\b|\bname of bidder\b",
     None, lambda f: f.get("registered_name", "company_name")),
    ("registration_no", r"registration ?/ ?incorporation|incorporation (no|number)|company registration (no|number)|business registration",
     None, lambda f: f.get("cin_number", "cin")),
    ("year_established", r"year of (the )?(establishment|incorporation|formation|registration)|established (in|on)\b",
     None, lambda f: f.get("year_of_company_registration_formation", "establishment_year")),
    ("firm_type", r"type of (the )?(firm|organi[sz]ation|entity|company)|constitution of (the )?firm|form of company|nature of (the )?firm",
     None, lambda f: f.get("type_of_firm", "company_type")),
    ("regional_offices", r"regional offices?|branch offices?", None, lambda f: f.get("regional_offices")),
    ("head_office", r"\bhead office\b|\bregistered (office|address)\b|\bcorporate office\b",
     None, lambda f: f.get("registered_address", "address")),
    ("email", r"\be ?-? ?mail\b", None, lambda f: f.get("email")),
    ("website", r"\bwebsite\b|\bweb address\b|\burl\b", None, lambda f: f.get("website")),
    ("contact_name", r"^(contact )?(person )?name$|^name of (the )?contact", r"contact",
     lambda f: f.get("contact_person_1_name")),
    # manpower sub-rows
    ("mp_design", r"\bdesign (section|engineers?|team|staff)\b", MANPOWER_CTX, lambda f: f.get("design_engineers")),
    ("mp_project", r"\bproject (section|managers?|team)\b", MANPOWER_CTX, lambda f: f.get("senior_project_managers")),
    ("mp_quality_safety", r"quality ?(&|and) ?safety", MANPOWER_CTX,
     lambda f: str((f.num("safety_personnel") or 0) + (f.num("quality_personnel") or 0)) if (f.num("safety_personnel") or f.num("quality_personnel")) else None),
    ("mp_quality", r"\bquality (engineers?|personnel|staff)\b", MANPOWER_CTX, lambda f: f.get("quality_personnel")),
    ("mp_safety", r"\bsafety (engineers?|personnel|officers?|staff)\b", MANPOWER_CTX, lambda f: f.get("safety_personnel")),
    ("mp_site", r"\bsite engineers?\b", MANPOWER_CTX, lambda f: f.get("site_engineers")),
    ("mp_supervisors", r"\bsupervisors?\b", MANPOWER_CTX, lambda f: f.get("supervisors")),
    ("mp_skilled_unskilled", r"skilled ?(&|and) ?(un|semi) ?skilled|labou?rs?\b", MANPOWER_CTX,
     lambda f: f.get("total_outsourced_manpower")),
    ("mp_technicians", r"\btechnicians?\b|\bskilled (workers|technicians)\b", MANPOWER_CTX, lambda f: f.get("skilled_technicians")),
    ("mp_planning", r"planning|commercial team", MANPOWER_CTX, lambda f: f.get("planning_commercial_team")),
    ("mp_others", r"^others?\b", MANPOWER_CTX, lambda f: f.get("other_staff")),
    ("mp_total", r"total (in ?house )?(manpower|employees|staff)|staff strength", None, lambda f: f.get("total_inhouse_manpower")),
    # registrations ("P.F.No.", "E.S.I. No." ...): the punctuation is removed before matching, hence "p f no"
    ("pf_no", r"(^| )p f( no)?( |$)|provident fund|(^| )epf( |$)", None, lambda f: f.get("pf_reg_no", "pf_regn_no")),
    ("esi_no", r"(^| )(e s i|esi|esic)( no)?( |$)", None, lambda f: f.get("esi_reg_no")),
    ("tds_no", r"(^| )(t d s|tds|tan)( no)?( |$)", None, lambda f: f.get("tds_no")),
    ("prof_tax", r"profession(al)? tax|(^| )ptrc( |$)", None, lambda f: f.get("ptrc_no")),
    ("msme_no", r"(^| )msme( |$)|udyam", None, lambda f: f.get("msme_reg_no")),
    ("wct_no", r"(^| )w c t( |$)|works contract tax", None, lambda f: f.get("wct_reg")),
    ("litigation", r"litigation|arbitration|arbibation", None, lambda f: f.get("litigation")),
    # manufacturing
    ("mfg_location", r"^location( ?s)?$|manufacturing (unit )?location", r"manufactur|factory|plant",
     lambda f: _join(f.get("mfg_unit_1_location"), f.get("mfg_unit_2_location"))),
]
_COMPILED = [(n, re.compile(p, re.I), re.compile(c, re.I) if c else None, fn) for n, p, c, fn in RULES]


def resolve_by_rules(labels: List[str], group: str, section: str, facts: Facts) -> Optional[str]:
    """First matching rule wins. `labels` are the cell's own labels (nearest first)."""
    own = [norm(l) for l in labels if l]
    context = norm(" ".join(own + [group or "", section or ""]))
    for name, pattern, ctx_pattern, fn in _COMPILED:
        if ctx_pattern is not None and not ctx_pattern.search(context):
            continue
        # the rule must hit the cell's OWN label, so a heading above cannot answer for it
        if not any(pattern.search(l) for l in own):
            continue
        value = fn(facts)
        if value:
            return str(value)
    return None


def contained_alias_match(labels: List[str], facts: Facts) -> Optional[str]:
    """Fallback: a stored label or alias that appears inside the question (longest wins).

    Short single-word aliases are ignored so that a generic word does not claim a question.
    """
    own = [norm(l) for l in labels if l]
    best, best_len = None, 0
    for f in facts.fields:
        candidates = [f.field_label] + list(f.aliases or [])
        for cand in candidates:
            c = norm(cand)
            if len(c) < 8 or " " not in c and len(c) < 12:
                continue
            for l in own:
                if re.search(rf"(^| ){re.escape(c)}( |$)", l) and len(c) > best_len:
                    best, best_len = f.value, len(c)
    return best


def _years_in(label: str):
    nums = re.findall(r"\d{4}|\d{2}", re.sub(r"[^0-9]+", " ", str(label or "")))
    return nums[:2]


def turnover_for_year(year_label: str, facts: Facts) -> Optional[str]:
    """Annual turnover saved under a fiscal-year label ("2022-2023", "2025-26"), whatever the year's spelling."""
    want = _years_in(year_label)
    if len(want) < 2:
        return None
    y1, y2 = want[0][-2:], want[1][-2:]
    for f in facts.fields:
        label_years = _years_in(f.field_label) if re.search(r"\d", f.field_label or "") else []
        if len(label_years) == 2 and label_years[0][-2:] == y1 and label_years[1][-2:] == y2                 and not re.search(r"[a-z]{4}", re.sub(r"fy|year", "", (f.field_label or "").lower())):
            return f.value
    return None
