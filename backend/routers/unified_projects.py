"""Unified project database -- the single place the deck app picks projects from."""
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from models.database import get_db, UnifiedProject
from services import unified_projects as svc

router = APIRouter()

COLUMNS = ["id", "project_name", "client_name", "third_party", "sector", "scope", "city", "location", "area_sqft",
           "value_cr", "start_date", "end_date", "year", "status", "pmc", "consultant", "architect", "manager",
           "contact_name", "contact_designation", "contact_email", "contact_phone", "description", "record_level",
           "sources", "selected_for_deck"]


def _row(p):
    return {c: getattr(p, c) for c in COLUMNS}


def _filtered(db, q, sector, city, scope, status, year_from, year_to, min_value, max_value, level, selected, pmc, keep_unknown_year=False):
    qs = db.query(UnifiedProject)
    if level != "all":
        qs = qs.filter(UnifiedProject.record_level == level)
    if q:
        like = f"%{q}%"
        qs = qs.filter(or_(UnifiedProject.project_name.ilike(like), UnifiedProject.client_name.ilike(like),
                           UnifiedProject.third_party.ilike(like), UnifiedProject.location.ilike(like),
                           UnifiedProject.pmc.ilike(like)))
    if scope:   # scope may hold several values ("Chiller, Fitout")
        qs = qs.filter(UnifiedProject.scope.ilike(f"%{scope}%"))
    for col, val in ((UnifiedProject.sector, sector), (UnifiedProject.city, city),
                     (UnifiedProject.pmc, pmc)):
        if val:
            qs = qs.filter(col == val)
    if status:   # one status or a comma list, e.g. "Completed,Unknown"
        qs = qs.filter(UnifiedProject.status.in_([x.strip() for x in status.split(",") if x.strip()]))
    if year_from:
        cond = UnifiedProject.year >= year_from
        qs = qs.filter(or_(cond, UnifiedProject.year.is_(None)) if keep_unknown_year else cond)
    if year_to:
        qs = qs.filter(UnifiedProject.year <= year_to)
    if min_value is not None:
        qs = qs.filter(UnifiedProject.value_cr >= min_value)
    if max_value is not None:
        qs = qs.filter(UnifiedProject.value_cr <= max_value)
    if selected is not None:
        qs = qs.filter(UnifiedProject.selected_for_deck.is_(selected))
    return qs


@router.get("/")
def list_projects(
    q: Optional[str] = None, sector: Optional[str] = None, city: Optional[str] = None, scope: Optional[str] = None,
    status: Optional[str] = None, pmc: Optional[str] = None, year_from: Optional[int] = None,
    year_to: Optional[int] = None, min_value: Optional[float] = None, max_value: Optional[float] = None,
    level: str = "project", selected: Optional[bool] = None, sort: str = "value_desc", keep_unknown_year: bool = False,
    page: int = 1, page_size: int = Query(50, le=500), db: Session = Depends(get_db),
):
    qs = _filtered(db, q, sector, city, scope, status, year_from, year_to, min_value, max_value, level, selected, pmc, keep_unknown_year)
    total = qs.count()
    order = {"value_desc": UnifiedProject.value_cr.desc().nullslast(), "area_desc": UnifiedProject.area_sqft.desc().nullslast(),
             "year_desc": UnifiedProject.year.desc().nullslast(), "name": UnifiedProject.project_name.asc()}.get(sort)
    rows = qs.order_by(order, UnifiedProject.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_row(p) for p in rows]}


@router.get("/filter-options")
def filter_options(level: str = "project", db: Session = Depends(get_db)):
    def distinct(col):
        qs = db.query(col).filter(col.isnot(None))
        if level != "all":
            qs = qs.filter(UnifiedProject.record_level == level)
        return sorted(v[0] for v in qs.distinct())
    return {c.key: distinct(c) for c in (UnifiedProject.sector, UnifiedProject.city, UnifiedProject.scope,
                                         UnifiedProject.status, UnifiedProject.pmc, UnifiedProject.year)}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    P = UnifiedProject
    return {
        "projects": db.query(func.count(P.id)).filter(P.record_level == "project").scalar(),
        "client_rollups": db.query(func.count(P.id)).filter(P.record_level == "client_rollup").scalar(),
        "selected_for_deck": db.query(func.count(P.id)).filter(P.selected_for_deck.is_(True)).scalar(),
        "total_value_cr": db.query(func.sum(P.value_cr)).filter(P.record_level == "project").scalar() or 0,
    }


class SelectBody(BaseModel):
    ids: List[int]
    selected: bool = True


@router.post("/select")
def select(body: SelectBody, db: Session = Depends(get_db)):
    n = db.query(UnifiedProject).filter(UnifiedProject.id.in_(body.ids)).update(
        {"selected_for_deck": body.selected}, synchronize_session=False)
    db.commit()
    return {"updated": n}


@router.post("/clear-selection")
def clear_selection(db: Session = Depends(get_db)):
    db.query(UnifiedProject).update({"selected_for_deck": False})
    db.commit()
    return {"ok": True}


@router.get("/deck")
def deck_feed(ids: Optional[str] = None, db: Session = Depends(get_db)):
    """Projects the deck app should render: explicit `ids` (comma-separated) or whatever is currently selected."""
    qs = db.query(UnifiedProject)
    if ids:
        qs = qs.filter(UnifiedProject.id.in_([int(i) for i in ids.split(",") if i.strip().isdigit()]))
    else:
        qs = qs.filter(UnifiedProject.selected_for_deck.is_(True))
    return {"projects": [_row(p) for p in qs.order_by(UnifiedProject.value_cr.desc().nullslast()).all()]}


class ExportBody(BaseModel):
    ids: Optional[List[int]] = None


@router.post("/export")
def export_xlsx(body: ExportBody, db: Session = Depends(get_db)):
    import openpyxl
    qs = db.query(UnifiedProject)
    if body.ids:
        qs = qs.filter(UnifiedProject.id.in_(body.ids))
    else:
        qs = qs.filter(UnifiedProject.record_level == "project")
    cols = [c for c in COLUMNS if c not in ("sources", "selected_for_deck")]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Unified Projects"
    ws.append([c.replace("_", " ").title() for c in cols] + ["Sources"])
    for p in qs.order_by(UnifiedProject.value_cr.desc().nullslast()).all():
        ws.append([getattr(p, c) for c in cols] + ["; ".join(f"{s['file']} / {s['sheet']}" for s in (p.sources or []))])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="unified_projects.xlsx"'})


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db)):
    """Re-read every source file and regenerate the table (deck selections are preserved)."""
    return svc.rebuild(db)
