"""Which documents a form question asks for, and a Workspace folder holding them.

Deterministic: a question is matched to document kinds by keyword patterns, and each kind is matched
to File Cabinet files by their name / category. No AI call, so it behaves the same without Gemini.
"""
import re
import uuid
from typing import Dict, List

from sqlalchemy.orm import Session

from models.database import ProjectFile, WorkspacePackage


def _n(text) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&]+", " ", str(text or "").lower())).strip()


# key, folder name, regex on the QUESTION text, regex on the FILE (name + category + type)
DOC_KINDS = [
    ("incorporation", "Incorporation & company constitution",
     r"incorporation|memorandum|articles of association|\bmoa\b|\baoa\b|constitution", r"incorporation|memorandum|articles"),
    ("gst", "GST registration", r"\bgst", r"\bgst\b|\bprc\b|\brc \d{2}aabch|\brc_\d{2}aabch|prc \d{2}aabch"),
    ("pan", "PAN card", r"\bpan\b|permanent account", r"pan card|pan india operations"),
    ("msme", "MSME / Udyam", r"msme|udyam", r"msme|udyam"),
    ("pf", "PF registration", r"\bpf\b|provident fund|\bepf", r"\bpf registration|pf reg"),
    ("esi", "ESI registration", r"\besi\b|\besic\b|employees state", r"\besic? registration|esic registration|\besi reg"),
    ("professional_tax", "Professional tax", r"professional tax|\bptrc\b|\bptec\b|\bpt (reg|cert)", r"\bpt reg|pt certificate|\bpt cert"),
    ("shop_est", "Shop & Establishment", r"shop (&|and) establishment|shops? act|trade licen[sc]e",
     r"shop (&|and) establishment|shop licen"),
    ("iso_9001", "ISO 9001 (quality)", r"9001|\bqms\b|quality management system|quality (certificat|accreditation)|quality system",
     r"\b9001\b"),
    ("iso_14001", "ISO 14001 (environment)", r"14001|\bems\b|environment(al)? management|environmental certificat", r"\b14001\b"),
    ("iso_45001", "ISO 45001 / OHSAS (safety)", r"45001|ohsas|18001|occupational health|safety management system|safety accreditation",
     r"45001|ohsas|safety accreditations?"),
    ("quality_docs", "Quality assurance", r"quality assurance|qa manual|quality (policy|manual|plan)|qa/qc",
     r"quality (policy|management plan|manual)"),
    ("safety_docs", "Health, safety & environment", r"health (&|and) safety|safety (policy|plan|programme|program|manual)|\bhse\b|\behs\b",
     r"\bhse\b|\behs\b|safety (policy|manual|induction)|health (&|and) saf|safe work method"),
    ("balance_sheet", "Balance sheets & financial statements",
     r"balance sheet|audited|financial statement|profit (&|and) loss|annual report|financial (status|capacity)|turn ?over",
     r"balance sheet|\bbs fy|provisional financial|financial statement"),
    ("itr", "Income tax clearance", r"income tax|\bitr\b|\bitcc\b|tax clearance", r"income tax clearance|\bitr\b"),
    ("solvency", "Solvency certificate", r"solvency", r"solvency"),
    ("insurance", "Insurance", r"insurance", r"insurance"),
    ("org_chart", "Organisation chart & key personnel",
     r"org(ani[sz]ation)?(al)? chart|organi[sz]ation structure|key personnel|key staff", r"org chart|organi[sz]ation chart"),
    ("plant_equipment", "Plant & equipment", r"plant (&|and) (machin|equip)|equipment list|machinery", r"plant (&|and) machin|machinary|equipment"),
    ("completion_certs", "Completion certificates & appreciation",
     r"completion certificate|performance certificate|appreciation|recommendation|reference letter|certificate of satisfaction",
     r"completion|appreciation"),
    ("work_orders", "Work orders / LOA", r"work order|\bloa\b|letter of award|purchase order|\bwo\b", r"\bloa\b|work order"),
    ("manpower", "Manpower & staff", r"man ?power|staff (list|strength)|employee (list|details)|labou?r (histogram|details)|muster roll|wage",
     r"manpower|employee list|labour histogram|muster roll|wage register"),
    ("company_profile", "Company profile & credentials",
     r"company profile|company credentials|credentials|brochure|capability statement|\bprofile\b", r"htl profile|new htl profile"),
    ("policies", "Company policies", r"code of (ethics|conduct)|modern slavery|policy on|\bcsr\b|\besg\b|sustainab|anti.?bribery",
     r"code of ethics|modern slavery|supplier code|esg|policy on"),
    ("statutory", "Statutory registrations", r"statutory|labou?r (licen[sc]e|welfare)|\bmlwf\b|\blwf\b|contract labou?r|clra|workmen",
     r"mlwf|wcp|licen[sc]e"),
    ("project_list", "Project lists & references", r"list of (major |completed |ongoing |on.going )?projects|client list|reference list",
     r"projects done|list of major projects|client reference|all ongoing projects"),
]
_COMPILED = [(k, name, re.compile(q, re.I), re.compile(f, re.I)) for k, name, q, f in DOC_KINDS]

_ASK_RE = re.compile(r"\benclos|\battach|\bphoto ?copy|\bcopy of|\bcertificate|\bcertificates\b|\bchart\b|\bbalance sheet|\bclearance|\bsolvency|\binsurance|"
                     r"\bpolicy\b|\bmanual\b|\bprofile\b|\blicen[sc]e|\bdeclaration\b|\baudited\b", re.I)


def doc_kinds_for(question: str) -> List[str]:
    """Document kinds a question text asks for, in definition order."""
    q = _n(question)
    return [k for k, _name, qre, _f in _COMPILED if qre.search(q)]


def asks_for_document(question: str) -> bool:
    """Is this question asking for a document (rather than a typed value)?"""
    q = str(question or "")
    return bool(doc_kinds_for(q)) and bool(_ASK_RE.search(q))


def _file_text(f: ProjectFile) -> str:
    return _n(f"{f.name} {f.category} {f.doc_type}")


def files_for_kind(kind: str, files: List[ProjectFile]) -> List[ProjectFile]:
    fre = next((fr for k, _n_, _q, fr in _COMPILED if k == kind), None)
    if not fre:
        return []
    hits = [f for f in files if fre.search(_file_text(f))]
    # real files first (the placeholder entries in the Documents list have no file or link)
    hits.sort(key=lambda f: (0 if (f.filename or f.sharepoint_link) else 1, -(f.id or 0) if kind == "balance_sheet" else 0, f.name or ""))
    return hits


def build_documents_package(db: Session, client_name: str, form_id: int, attached: List[Dict]) -> Dict:
    """Create a Draft Workspace package with one folder per document kind the form asked for.

    attached: [{"cell": "Sheet!D45", "question": "..."}] for every cell filled with "Attached".
    Returns a summary: package id/name, how many folders/files, and the document kinds with no file yet.
    """
    kinds_wanted: Dict[str, List[str]] = {}
    for a in attached:
        for k in doc_kinds_for(a.get("question", "")):
            kinds_wanted.setdefault(k, []).append(a["cell"])
    if not kinds_wanted:
        return {"package_id": None, "folders": 0, "files": 0, "missing": [], "kinds": []}

    all_files = db.query(ProjectFile).filter(ProjectFile.source_module == "project_file").all()
    placeholders = db.query(ProjectFile).filter(ProjectFile.source_module == "document").all()
    pool = all_files + [d for d in placeholders if d.filename or d.sharepoint_link]

    folders, items, missing, summary = [], [], [], []
    used = set()
    for kind, name, _q, _f in _COMPILED:
        if kind not in kinds_wanted:
            continue
        matched = files_for_kind(kind, pool)
        # a file serves the first folder that claims it; no duplicates across folders
        matched = [m for m in matched if m.id not in used] or matched[:0]
        if not matched:
            # the placeholder entry (no file) tells the user what to upload
            missing.append(name)
            summary.append({"kind": kind, "folder": name, "files": 0, "cells": kinds_wanted[kind]})
            continue
        folder_id = str(uuid.uuid4())
        folders.append({"id": folder_id, "name": name, "parentId": None})
        for m in matched:
            used.add(m.id)
            items.append({"id": str(uuid.uuid4()), "folderId": folder_id,
                          "file": {"id": m.id, "name": m.name, "category": m.category}})
        summary.append({"kind": kind, "folder": name, "files": len(matched), "cells": kinds_wanted[kind]})

    if not items:
        return {"package_id": None, "folders": 0, "files": 0, "missing": missing, "kinds": summary}

    pkg = WorkspacePackage(
        name=f"{client_name} - PQ documents (form {form_id})",
        client=client_name,
        target_sharepoint_url="",
        data={"folders": folders, "items": items, "missing": missing, "source_form_id": form_id},
        status="Draft",
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return {"package_id": pkg.id, "name": pkg.name, "folders": len(folders), "files": len(items),
            "missing": missing, "kinds": summary}
