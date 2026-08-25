from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import pandas as pd
import io
import re

from models.database import get_db, SubContractor
from pydantic import BaseModel

router = APIRouter()

class SubContractorBase(BaseModel):
    name: str
    address: Optional[str] = None
    work_description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    years_active: Optional[str] = None
    source_document: Optional[str] = None
    notes: Optional[str] = None

class SubContractorCreate(SubContractorBase):
    pass

class SubContractorResponse(SubContractorBase):
    id: int
    created_at: datetime
    last_updated: datetime

    class Config:
        from_attributes = True

@router.get("/", response_model=List[SubContractorResponse])
def get_subcontractors(search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(SubContractor)
    if search:
        query = query.filter(
            (SubContractor.name.ilike(f"%{search}%")) |
            (SubContractor.work_description.ilike(f"%{search}%"))
        )
    return query.order_by(SubContractor.id).all()

@router.post("/", response_model=SubContractorResponse)
def create_subcontractor(subc: SubContractorCreate, db: Session = Depends(get_db)):
    db_subc = SubContractor(**subc.model_dump())
    db.add(db_subc)
    db.commit()
    db.refresh(db_subc)
    return db_subc

@router.put("/{sub_id}", response_model=SubContractorResponse)
def update_subcontractor(sub_id: int, subc: SubContractorCreate, db: Session = Depends(get_db)):
    db_subc = db.query(SubContractor).filter(SubContractor.id == sub_id).first()
    if not db_subc:
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    
    update_data = subc.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_subc, key, value)
        
    db_subc.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(db_subc)
    return db_subc

@router.delete("/{sub_id}")
def delete_subcontractor(sub_id: int, db: Session = Depends(get_db)):
    db_subc = db.query(SubContractor).filter(SubContractor.id == sub_id).first()
    if not db_subc:
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    db.delete(db_subc)
    db.commit()
    return {"ok": True}

@router.post("/import-csv")
async def import_subcontractors_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from utils import enforce_upload_size
    contents = await file.read()
    enforce_upload_size(len(contents))

    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith(".xlsx") or file.filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel.")
            
        # Clean columns
        df.columns = df.columns.str.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    imported = 0
    skipped = 0

    # Ensure required columns exist, mapping loosely
    col_mapping = {}
    for col in df.columns:
        c_lower = col.lower()
        if "name" in c_lower and "sub" in c_lower: col_mapping["name"] = col
        elif "address" in c_lower: col_mapping["address"] = col
        elif "work" in c_lower and "description" in c_lower: col_mapping["work_description"] = col
        elif "contact" in c_lower: col_mapping["contact_details"] = col

    for _, row in df.iterrows():
        # Need at least a name
        name = row.get(col_mapping.get("name", ""), "")
        if pd.isna(name) or not str(name).strip():
            continue
            
        name = str(name).strip()
        
        # Check if already exists
        exists = db.query(SubContractor).filter(SubContractor.name.ilike(name)).first()
        if exists:
            skipped += 1
            continue
            
        address = row.get(col_mapping.get("address", ""), "")
        address = str(address).strip() if not pd.isna(address) else None
        
        work_desc = row.get(col_mapping.get("work_description", ""), "")
        work_desc = str(work_desc).strip() if not pd.isna(work_desc) else None
        
        contact_str = row.get(col_mapping.get("contact_details", ""), "")
        contact_str = str(contact_str).strip() if not pd.isna(contact_str) else ""
        
        contact_name = None
        contact_phone = None
        contact_email = None
        notes = []

        if contact_str:
            # Simple regex to parse "Name - Phone - Email"
            parts = [p.strip() for p in re.split(r'[-\n]', contact_str) if p.strip()]
            
            for part in parts:
                if "@" in part:
                    emails = [e.strip() for e in part.split("/") if e.strip()]
                    if not contact_email and emails:
                        contact_email = emails[0]
                        if len(emails) > 1:
                            notes.append(f"Additional emails: {', '.join(emails[1:])}")
                elif re.search(r'\d{6,}', part):
                    if not contact_phone:
                        contact_phone = part
                    else:
                        notes.append(f"Additional phone: {part}")
                else:
                    if not contact_name:
                        contact_name = part
                    else:
                        notes.append(f"Extra contact info: {part}")

        if not contact_name and not contact_phone and not contact_email and contact_str:
            notes.append(f"Raw contact: {contact_str}")

        subc = SubContractor(
            name=name,
            address=address,
            work_description=work_desc,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            notes="\n".join(notes) if notes else None,
            source_document=file.filename
        )
        db.add(subc)
        imported += 1
        
    db.commit()
    
    return {"imported": imported, "skipped": skipped, "message": "Import successful"}
