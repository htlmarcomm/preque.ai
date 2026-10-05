"""Builds the unified project database from every project source.

Sources (earlier sources win on conflicting fields, later ones only fill blanks):
  1. HTL_Sector_Wise_Register.xlsx   (data_sources/)  -- project-level master
  2. File Cabinet "Project Registry" files (uploads/project_files/)
  3. HTL_Projects_Consolidated.xlsx  (data_sources/)  -- client-level rollup
"""
import glob
import os
import re
from datetime import datetime, date

import openpyxl

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data_sources")
CABINET_DIR = os.path.join(BASE, "uploads", "project_files")

# order matters: first matching keyword wins
SECTORS = [
    ("data c", "Data Centres"), ("datacent", "Data Centres"), ("data", "Data Centres"),
    ("cowork", "Coworking"),
    ("bfsi", "Corporate - BFSI"), ("it", "IT / GCC / Technology"), ("gcc", "IT / GCC / Technology"),
    ("tech", "IT / GCC / Technology"),
    ("corporate", "Corporate Offices"), ("consult", "Corporate Offices"),
    ("retail", "Retail & Luxury"), ("luxury", "Retail & Luxury"),
    ("hospitality", "Hospitality & Hotels"), ("hotel", "Hospitality & Hotels"),
    ("pharma", "Pharma & Biotech"), ("biotech", "Pharma & Biotech"),
    ("hospital", "Healthcare & Hospitals"), ("health", "Healthcare & Hospitals"),
    ("educat", "Education & Institutions"), ("institution", "Education & Institutions"),
    ("govt", "Government & Infrastructure"), ("infra", "Government & Infrastructure"),
    ("government", "Government & Infrastructure"),
    ("industrial", "Industrial & Manufacturing"), ("manufactur", "Industrial & Manufacturing"),
    ("residential", "Residential"), ("logistic", "Logistics & Warehousing"), ("warehous", "Logistics & Warehousing"),
    ("lobby", "Commercial / Other"), ("commercial", "Commercial / Other"), ("other", "Commercial / Other"),
]
CITY_ALIASES = [
    ("bglr", "Bengaluru"), ("bangalore", "Bengaluru"), ("bengaluru", "Bengaluru"), ("blr", "Bengaluru"),
    ("hyd", "Hyderabad"), ("delhi", "Delhi"), ("ncr", "Delhi"), ("gurgaon", "Delhi"), ("gurugram", "Delhi"),
    ("noida", "Delhi"), ("mumbai", "Mumbai"), ("pune", "Pune"), ("chennai", "Chennai"),
    ("ahmedabad", "Ahmedabad"), ("gujrat", "Gujarat"), ("guj", "Gujarat"), ("cbd", "Mumbai"), ("thane", "Mumbai"),
]
SCOPE_ALIASES = {"nv": "NVRV", "nvrv": "NVRV", "vrv": "VRV", "chiller": "Chiller", "chilled water": "Chiller",
                 "fitout": "Fitout", "fit-out": "Fitout", "services": "Services", "hvac": "HVAC", "mep": "MEP",
                 "refrigeration": "Refrigeration", "refrigeratn": "Refrigeration"}


def _s(v):
    if v is None:
        return None
    t = str(v).replace("\xa0", " ").strip()
    return t if t and t not in ("-", "NA", "N/A", "None", "nan") else None


def norm(t):
    t = (t or "").lower()
    t = re.sub(r"\(closed\)|\bm/?s\b\.?-?", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def norm_sector(t):
    t = (_s(t) or "").lower()
    if not t:
        return None
    if "data" in t and "centre" in t or "datacent" in t:
        return "Data Centres"
    for k, v in SECTORS:
        if re.search(r"\b" + re.escape(k), t):
            return v
    return "Commercial / Other"


def norm_city(t):
    t = (_s(t) or "").lower()
    if not t:
        return None
    for k, v in CITY_ALIASES:
        if k in t:
            return v
    return None   # not a recognised city (e.g. a building name) -- caller keeps it as `location`


SCOPE_ALIASES.update({"non vrv": "NVRV", "revamp": "Revamp", "others": "Others", "casual jobs": "Casual Jobs"})
KNOWN_SCOPES = set(SCOPE_ALIASES.values())


def norm_scope(t):
    """'Non VRV, VRV' -> 'NVRV, VRV'. Unknown parts (e.g. a manager name in the category column) are dropped."""
    parts = []
    for part in re.split(r"[,/+&]", _s(t) or ""):
        part = part.strip()
        if not part:
            continue
        v = SCOPE_ALIASES.get(part.lower(), part.title())
        if v in KNOWN_SCOPES and v not in parts:
            parts.append(v)
    return ", ".join(parts) or None


def parse_date(v):
    if v is None:
        return None
    d = None
    if isinstance(v, (datetime, date)):
        d = v
    else:
        t = str(v).strip()
        for f in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
            try:
                d = datetime.strptime(t, f)
                break
            except ValueError:
                pass
    return d.strftime("%Y-%m-%d") if d and 2000 <= d.year <= 2035 else None   # typos like 1905 are dropped


def parse_area(v):
    """-> sqft float; handles '2.5L Sq.ft', '4 lakh St.ft', '40k Sq.ft', '0.8 Lac Sq.ft'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) or None
    t = str(v).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    n = float(m.group(1))
    if re.search(r"\d\s*(l\b|lac|lakh|lk)", t):
        n *= 1e5
    elif re.search(r"\d\s*k\b", t):
        n *= 1e3
    return n or None


def to_cr(v, unit):
    """unit (for bare numbers): 'lakh' | 'inr' | 'cr'. Text with Cr/Lakh/Million overrides it."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        t = str(v).lower().replace(",", "").replace("₹", "")
        m = re.search(r"(\d+(?:\.\d+)?)", t)
        if not m:
            return None
        n = float(m.group(1))
        if "cr" in t:
            return n or None
        if "million" in t:
            return n / 10 or None
        if "lakh" in t or re.search(r"\dl\b", t):
            return n / 100 or None
    if not n:
        return None
    if unit == "lakh" and n > 50000:   # > Rs 500 Cr in lakhs: the cell is really raw INR (mixed units inside "lakh" sheets)
        unit = "inr"
    return {"lakh": n / 100, "inr": n / 1e7, "cr": n}[unit]


def _close_dates(a, b, days=60):
    if not a or not b:
        return True
    try:
        return abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days) <= days
    except ValueError:
        return a == b


def _grid(path, sheet):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if sheet not in wb.sheetnames:
        return []
    return list(wb[sheet].iter_rows(values_only=True))


def _dicts(rows, hdr_idx=0):
    if len(rows) <= hdr_idx:
        return
    hdr = [(_s(h) or "").lower() for h in rows[hdr_idx]]
    for r in rows[hdr_idx + 1:]:
        if any(v not in (None, "") for v in r):
            yield {h: v for h, v in zip(hdr, r) if h}


def _col(d, *needles):
    for k, v in d.items():
        if all(n in k for n in needles):
            return v
    return None


def _num(v):
    return v if v not in (None, "", 0, 0.0) else None


# --- source readers: each yields normalized dicts ---------------------------

def read_register_sheet(path, sheet, unit):
    rows = _grid(path, sheet)
    if not rows:
        return
    first = [(_s(h) or "").lower() for h in rows[0]]
    if not any("project" in h or "end user" in h for h in first):
        return
    src = dict(file="HTL_Sector_Wise_Register.xlsx", sheet=sheet.strip())
    for d in _dicts(rows):
        name = _s(_col(d, "project")) or _s(_col(d, "end user"))
        if not name:
            continue
        end_user = _s(_col(d, "end user")) or _s(_col(d, "developer"))
        val = _num(_col(d, "contract value at end")) or _num(_col(d, "contract value at start")) \
            or _num(_col(d, "contract value"))
        sec_raw = _s(_col(d, "job sector")) or _s(_col(d, "sector"))
        yield dict(
            project_name=name, client_name=end_user, third_party=_s(_col(d, "third party")),
            sector_raw=sec_raw, sector=norm_sector(sec_raw or sheet),
            scope=norm_scope(_col(d, "category")), city=norm_city(_col(d, "branch") or _col(d, "territory")),
            area_sqft=parse_area(_col(d, "area")), value_cr=to_cr(val, unit),
            start_date=parse_date(_col(d, "start date")), end_date=parse_date(_col(d, "end date")),
            pmc=_s(_col(d, "pmc")), consultant=_s(_col(d, "consultant")),
            architect=_s(_col(d, "architect")), manager=_s(_col(d, "manager")) or _s(_col(d, "business head")),
            source=src,
        )


# Sheets headed "(In Lakhs)" hold lakhs; the rest hold raw INR.
LAKH_SHEETS = ["All Projects", "Corporate", "Commercial", "Hospitality", "Coworking", "Data Centre", "Educational",
               "Govt. & Infra", "Industrial", "Residential", "Lobby", "Pharma", "Hospital"]
INR_SHEETS = ["Delhi PROJECTS ", "projects done with CBRE ", "PGH1", "guj", "Others", "Developers"]


def read_register(path):
    for s in LAKH_SHEETS:
        yield from read_register_sheet(path, s, "lakh")
    for s in INR_SHEETS:
        yield from read_register_sheet(path, s, "inr")
    for d in _dicts(_grid(path, "jll")):
        name = _s(_col(d, "end user"))
        if name:
            yr = _col(d, "start year")
            yield dict(project_name=name, client_name=name, sector_raw=_s(_col(d, "sector")),
                       sector=norm_sector(_col(d, "sector")), city=norm_city(_col(d, "branch")),
                       value_cr=to_cr(_col(d, "contract value"), "lakh"), year=int(yr) if yr else None,
                       source=dict(file="HTL_Sector_Wise_Register.xlsx", sheet="jll"))
    # client reference contacts: project/client carried down over person rows
    last = {}
    for r in _grid(path, "Client Ref")[2:]:
        if len(r) < 8 or not (r[4] or r[6]):
            continue
        if _s(r[2]):
            last = {"project": _s(r[2]), "client": _s(r[3])}
        if last:
            phone = _s(r[7])
            yield dict(project_name=last["project"], client_name=last["client"], contact_name=_s(r[4]),
                       contact_designation=_s(r[5]), contact_email=_s(r[6]),
                       contact_phone=re.sub(r"\.0$", "", phone) if phone else None,
                       status="Ongoing", contact_only=True,
                       source=dict(file="HTL_Sector_Wise_Register.xlsx", sheet="Client Ref"))
    for d in _dicts(_grid(path, "png")):
        name = _s(d.get("project"))
        if name:
            yield dict(project_name=name, location=_s(d.get("location")),
                       city=norm_city(d.get("location")), area_sqft=parse_area(d.get("area in sqft")),
                       value_cr=to_cr(d.get("executed value in inr"), "cr"), scope=norm_scope(d.get("scope of work")),
                       start_date=parse_date(d.get("start date")),
                       status="Ongoing" if "ongoing" in str(d.get("completion date")).lower() else None,
                       end_date=parse_date(d.get("completion date")),
                       source=dict(file="HTL_Sector_Wise_Register.xlsx", sheet="png"))


def _cab(pattern):
    m = glob.glob(os.path.join(CABINET_DIR, pattern))
    return m[0] if m else None


def read_cabinet():
    # Project related details
    p = _cab("*Project related details.xlsx")
    if p:
        src = dict(file="Project related details.xlsx", sheet="Sheet1")
        for d in _dicts(_grid(p, "Sheet1")):
            name = _s(d.get("project name"))
            if name:
                yield dict(project_name=name, description=_s(_col(d, "brief")), contact_name=_s(_col(d, "contact reference")),
                           pmc=_s(_col(d, "pmc")), value_cr=to_cr(_col(d, "total contract"), "cr"),
                           area_sqft=parse_area(_col(d, "project area")),
                           status="Ongoing" if "ongoing" in str(_col(d, "year of completion")).lower() else None,
                           source=src)
    # Client Reference Details
    p = _cab("*Client Reference Details.xlsx")
    if p:
        sh = openpyxl.load_workbook(p, read_only=True).sheetnames[0]
        src = dict(file="Client Reference Details.xlsx", sheet=sh.strip())
        for d in _dicts(_grid(p, sh), 1):
            name = _s(d.get("project"))
            if name:
                yield dict(project_name=name, location=_s(d.get("location")), city=norm_city(d.get("location")),
                           area_sqft=parse_area(d.get("area in sqft")), value_cr=to_cr(d.get("executed value in inr"), "cr"),
                           start_date=parse_date(d.get("start date")), scope=norm_scope(d.get("scope of work")),
                           contact_name=_s(_col(d, "representative with")), contact_phone=_s(_col(d, "contact no")),
                           contact_email=_s(_col(d, "email")),
                           status="Ongoing" if "ongoing" in str(d.get("completion date")).lower() else None,
                           source=src)
    # List of Major Projects (vertical key/value blocks)
    p = _cab("*List of Major Projects.xlsx")
    if p:
        src = dict(file="List of Major Projects.xlsx", sheet="Sheet1")
        cur = None
        for r in _grid(p, "Sheet1"):
            key = (_s(r[2]) or "") if len(r) > 2 else ""
            val = _s(r[3]) if len(r) > 3 else None
            if re.match(r"project-\d+", key.lower()):
                if cur:
                    yield cur
                cur = dict(project_name=val, status="Ongoing", source=src)
            elif cur is not None:
                k = key.lower()
                if k.startswith("size"):
                    cur["area_sqft"] = parse_area(val)
                elif k.startswith("billing"):
                    cur["value_cr"] = to_cr(val, "cr")
                elif k.startswith("pmc"):
                    cur["pmc"] = val
                elif k.startswith("location"):
                    cur["location"] = val
                    cur["city"] = norm_city(val)
                elif k.startswith("client"):
                    cur["contact_name"] = val
        if cur:
            yield cur
    # HTL All Ongoing Projects
    p = _cab("*HTL All Ongoing Projects.xlsx")
    if p:
        src = dict(file="HTL All Ongoing Projects.xlsx", sheet="VRV")
        for r in _grid(p, "VRV")[2:]:
            if len(r) >= 7 and _s(r[2]):
                yield dict(project_name=_s(r[2]), scope="VRV", start_date=parse_date(r[3]), end_date=parse_date(r[4]),
                           value_cr=to_cr(r[5], "inr"), status=(_s(r[6]) or "").title() or None, source=src)
        for d in _dicts(_grid(p, "HVAC"), 1):
            name = _s(_col(d, "name of project"))
            if name:
                rem = (_s(d.get("remark")) or "").lower()
                yield dict(project_name=name, client_name=_s(_col(d, "name of client")),
                           area_sqft=parse_area(_col(d, "area")), value_cr=to_cr(_col(d, "contract value"), "cr"),
                           scope="HVAC", pmc=_s(d.get("pmc")),
                           status="Ongoing" if "ongoing" in rem else ("Completed" if "handed" in rem else None),
                           source=dict(file="HTL All Ongoing Projects.xlsx", sheet="HVAC"))
        for d in _dicts(_grid(p, "MEP")):
            name = _s(d.get("project name"))
            if name:
                yield dict(project_name=name, client_name=_s(d.get("client name")), location=_s(d.get("location")),
                           city=norm_city(d.get("location")), scope="MEP", start_date=parse_date(d.get("wo date")),
                           value_cr=to_cr(_col(d, "wo value"), "inr"), status="Ongoing",
                           source=dict(file="HTL All Ongoing Projects.xlsx", sheet="MEP"))
    # Work done with other PMC: bullet lists, one project per line
    p = _cab("*Work done with other PMC.xlsx")
    if p:
        pmc = None
        seen = set()
        for r in _grid(p, "Sheet1")[2:]:
            if _s(r[0]):
                pmc = _s(r[0])
            loc = _s(r[2]) if len(r) > 2 else None
            for line in re.split(r"[\n\r]+", str(r[1] or "")):
                t = re.sub(r"^[\s•⁠\t]+", "", line).strip(" \t⁠")
                if not t or re.match(r"^\d+\.\s*[A-Za-z /]+$", t) or t.lower().startswith("specialty") or (pmc, loc, t) in seen:
                    continue
                seen.add((pmc, loc, t))
                yield dict(project_name=t, pmc=pmc, city=norm_city(loc), location=loc, status="Completed",
                           source=dict(file="Work done with other PMC.xlsx", sheet="Sheet1"))


def read_consolidated(path):
    for d in _dicts(_grid(path, "Consolidated Master"), 2):
        name = _s(d.get("client name"))
        if not name:
            continue
        yield dict(project_name=name, client_name=name, sector_raw=_s(d.get("sector")), sector=norm_sector(d.get("sector")),
                   city=norm_city(d.get("city")), scope=norm_scope(_col(d, "scope")), area_sqft=parse_area(d.get("area (sq.ft.)")),
                   value_cr=to_cr(d.get("total value (₹)"), "inr"), pmc=_s(d.get("stakeholder")),
                   description=_s(_col(d, "project name")), location=_s(d.get("location")),
                   record_level="client_rollup",
                   source=dict(file="HTL_Projects_Consolidated.xlsx", sheet="Consolidated Master"))


# --- merge -------------------------------------------------------------------

FILL_FIELDS = ["client_name", "third_party", "sector", "sector_raw", "scope", "city", "location", "area_sqft", "value_cr",
               "start_date", "end_date", "year", "status", "pmc", "consultant", "architect", "manager", "contact_name",
               "contact_designation", "contact_email", "contact_phone", "description"]


def build_records():
    reg = os.path.join(DATA_DIR, "HTL_Sector_Wise_Register.xlsx")
    con = os.path.join(DATA_DIR, "HTL_Projects_Consolidated.xlsx")
    merged, by_name, by_value, stats = {}, {}, {}, {"rows_read": 0}
    STOP = {"pvt", "ltd", "limited", "private", "india", "the", "and", "project", "projects", "phase", "floor", "centre",
            "center", "mumbai", "pune", "delhi", "closed", "services", "interiors", "construction"}

    def tokens(*texts):
        return {w for t in texts for w in norm(t).split() if len(w) >= 4 and w not in STOP}

    def add(rec):
        stats["rows_read"] += 1
        name = norm(rec.get("project_name"))
        if not name:
            return
        level = rec.get("record_level", "project")
        v = rec.get("value_cr")
        key = f"{level}|{name}|{rec.get('start_date') or ''}|{round(v, 1) if v else ''}"
        hit = merged.get(key)
        if not hit and level == "project":
            # same name, no conflicting start date / value -> same project
            for k in by_name.get(name, []):
                c = merged[k]
                if _close_dates(c["start_date"], rec.get("start_date")) and \
                   (not c["value_cr"] or not v or abs(c["value_cr"] - v) <= max(0.06, 0.01 * v)):
                    hit = c
                    break
        if not hit and level == "project" and v:
            # same contract value (within 1%) and a shared distinctive word in name/client -> same project, different spelling
            tk = tokens(rec.get("project_name"), rec.get("client_name"))
            for b in (round(v, 0) - 1, round(v, 0), round(v, 0) + 1):
                for k in by_value.get(b, []):
                    c = merged[k]
                    if c["value_cr"] and abs(c["value_cr"] - v) <= max(0.06, 0.01 * v) and                        _close_dates(c["start_date"], rec.get("start_date")) and                        tk & tokens(c["project_name"], c["client_name"]):
                        hit = c
                        break
                if hit:
                    break
        if hit:
            for f in FILL_FIELDS:
                if hit.get(f) in (None, "") and rec.get(f) not in (None, ""):
                    hit[f] = rec[f]
            if rec["source"] not in hit["sources"]:
                hit["sources"].append(rec["source"])
            return
        r = {f: rec.get(f) for f in FILL_FIELDS}
        r.update(project_name=rec["project_name"], record_level=level, sources=[rec["source"]], dedupe_key=key)
        merged[key] = r
        if level == "project":
            by_name.setdefault(name, []).append(key)
            if v:
                by_value.setdefault(round(v, 0), []).append(key)

    contacts = []
    if os.path.exists(reg):
        for rec in read_register(reg):
            if rec.pop("contact_only", False):
                contacts.append(rec)
            else:
                add(rec)
    for rec in read_cabinet():
        add(rec)
    for rec in contacts:
        add(rec)
    if os.path.exists(con):
        for rec in read_consolidated(con):
            add(rec)

    out = list(merged.values())
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for r in out:
        sd = r.get("start_date")
        r["year"] = r.get("year") or (int(sd[:4]) if sd else None)
        if r.get("status") and r["status"].lower().replace("-", "") == "ongoing":
            r["status"] = "Ongoing"
        if not r.get("status"):
            ed = r.get("end_date")
            r["status"] = "Completed" if ed and ed < today else "Unknown"
    stats["unified_rows"] = len(out)
    return out, stats


def rebuild(db):
    from models.database import UnifiedProject
    out, stats = build_records()
    keep = {p.dedupe_key for p in db.query(UnifiedProject).filter(UnifiedProject.selected_for_deck.is_(True)).all()}
    db.query(UnifiedProject).delete()
    for r in out:
        db.add(UnifiedProject(**r, selected_for_deck=r["dedupe_key"] in keep))
    db.commit()
    stats["by_level"] = {}
    for r in out:
        stats["by_level"][r["record_level"]] = stats["by_level"].get(r["record_level"], 0) + 1
    return stats
