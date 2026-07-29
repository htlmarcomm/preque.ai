from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from models.database import get_db, ProjectReference, ProjectDataRecord, ProjectDataSheet
from typing import Optional
import re

router = APIRouter()

@router.get("/references")
def get_references(
    search: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProjectReference)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ProjectReference.project_name.ilike(search_term),
                ProjectReference.client_name.ilike(search_term),
                ProjectReference.location.ilike(search_term)
            )
        )
    if region:
        query = query.filter(ProjectReference.region == region)
    if status:
        query = query.filter(ProjectReference.status == status)
        
    results = query.order_by(
        ProjectReference.status.desc(),
        ProjectReference.end_date.desc()
    ).limit(200).all()
    
    return [
        {
            "id": p.id,
            "label": f"{p.project_name or 'Unknown'} — {p.client_name or 'Unknown'}",
            "project_name": p.project_name,
            "client_name": p.client_name,
            "location": p.location,
            "consultant": p.consultant,
            "pmc": p.pmc,
            "project_sector": p.project_sector,
            "project_type": p.project_type,
            "project_value": p.project_value,
            "region": p.region,
            "status": p.status,
            "client_rep_name": p.client_rep_name,
            "client_rep_designation": p.client_rep_designation,
            "client_rep_email": p.client_rep_email,
            "client_rep_phone": p.client_rep_phone,
            "start_date": p.start_date,
            "end_date": p.end_date,
        }
        for p in results
    ]


@router.get("/details")
def get_details(
    search: Optional[str] = None,
    source_file: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProjectDataRecord)
    
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(ProjectDataRecord.search_text.ilike(search_term))
    if source_file:
        query = query.filter(ProjectDataRecord.source_file == source_file)
        
    records = query.order_by(ProjectDataRecord.uploaded_at.desc()).limit(200).all()
    
    # Pre-fetch sheet schemas to compute labels efficiently
    # We only need the column_order for the sheets these records belong to
    sheet_keys = {(r.source_file, r.source_sheet) for r in records}
    sheets_info = {}
    for sf, ss in sheet_keys:
        sheet = db.query(ProjectDataSheet).filter(
            ProjectDataSheet.source_file == sf,
            ProjectDataSheet.source_sheet == ss
        ).first()
        if sheet:
            sheets_info[(sf, ss)] = sheet.column_order or []
            
    # Currency guard regex from corruption fix
    currency_guard = re.compile(r'^\d+\.?\d*\s*(cr|crore|lakh|lac|inr|l)?$', re.IGNORECASE)

    response = []
    for r in records:
        data = r.data or {}
        col_order = sheets_info.get((r.source_file, r.source_sheet), [])
        
        # 1. Try to find a column related to project name
        label = None
        for col in col_order:
            k = col.get("key", "").lower()
            dl = col.get("display_label", "").lower()
            if "project" in k or "name" in k or "project" in dl or "name" in dl:
                val = data.get(k)
                if val and isinstance(val, str) and val.strip():
                    val = val.strip()
                    if not currency_guard.match(val):
                        label = val
                        break
        
        # 2. Fallback: first non-empty string that passes guard
        if not label:
            for col in col_order:
                k = col.get("key", "")
                val = data.get(k)
                if val and isinstance(val, str) and val.strip():
                    val = val.strip()
                    if not currency_guard.match(val):
                        label = val
                        break
                        
        # 3. Ultimate fallback
        if not label:
            label = f"{r.source_sheet} row {r.row_number}"
            
        response.append({
            "id": r.id,
            "label": label,
            "source_file": r.source_file,
            "source_sheet": r.source_sheet,
            "data": data
        })
        
    return response
