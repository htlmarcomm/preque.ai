from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from models.database import get_db, CompanyField
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import openpyxl, io, json, os
from utils import normalize_field_key

router = APIRouter()

# ── Schemas ──────────────────────────────────────────────────────────────
class FieldCreate(BaseModel):
    category: str
    field_key: str
    field_label: str
    value: Optional[str] = ""
    document_link: Optional[str] = ""
    notes: Optional[str] = ""
    aliases: Optional[List[str]] = []

class FieldUpdate(BaseModel):
    value: Optional[str] = None
    document_link: Optional[str] = None
    notes: Optional[str] = None
    field_label: Optional[str] = None
    category: Optional[str] = None
    aliases: Optional[List[str]] = None

# ── CATEGORIES ────────────────────────────────────────────────────────────
CATEGORIES = [
    "Company Identity", "Address & Contact", "Contact Persons",
    "Registration & Legal", "Manpower", "Infrastructure",
    "Financial", "Business Profile & Capability", "Compliance"
]

@router.get("/categories")
def get_categories():
    return {"categories": CATEGORIES}

# ── ALL FIELDS ────────────────────────────────────────────────────────────
@router.get("/fields")
def get_all_fields(category: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(CompanyField)
    if category:
        q = q.filter(CompanyField.category == category)
    fields = q.order_by(CompanyField.category, CompanyField.id).all()
    return {"fields": [f.__dict__ for f in fields]}

@router.post("/fields")
def create_field(data: FieldCreate, db: Session = Depends(get_db)):
    existing = db.query(CompanyField).filter(CompanyField.field_key == data.field_key).first()
    if existing:
        raise HTTPException(400, f"Field key '{data.field_key}' already exists")
    field = CompanyField(**data.dict())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field.__dict__

@router.put("/fields/{field_id}")
def update_field(field_id: int, data: FieldUpdate, db: Session = Depends(get_db)):
    field = db.query(CompanyField).filter(CompanyField.id == field_id).first()
    if not field:
        raise HTTPException(404, "Field not found")
    for k, v in data.dict(exclude_none=True).items():
        setattr(field, k, v)
    field.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(field)
    return field.__dict__

@router.delete("/fields/{field_id}")
def delete_field(field_id: int, db: Session = Depends(get_db)):
    field = db.query(CompanyField).filter(CompanyField.id == field_id).first()
    if not field:
        raise HTTPException(404, "Field not found")
    db.delete(field)
    db.commit()
    return {"deleted": field_id}

# ── BULK DATA ─────────────────────────────────────────────────────────────
@router.get("/dump")
def dump_all(db: Session = Depends(get_db)):
    """Returns all company data as flat key:value dict for agent use."""
    fields = db.query(CompanyField).all()
    result = {}
    for f in fields:
        result[f.field_key] = {
            "label": f.field_label,
            "value": f.value or "",
            "category": f.category,
            "document_link": f.document_link or ""
        }
    return result

# ── IMPORT FROM EXCEL ─────────────────────────────────────────────────────
@router.post("/import-excel")
async def import_from_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import re as _re
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    ws = wb.active
    imported = 0
    skipped = 0
    errors = []

    # Collect all rows to auto-detect whether column A is a serial-number column.
    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        return {"imported": 0, "updated": 0, "errors": []}

    # Heuristic: if > 60% of non-empty column-A values are purely numeric,
    # treat column A as a serial-number column and shift label/value to B/C.
    col_a_vals = [str(r[0]).strip() for r in all_rows if r and r[0] is not None]
    numeric_count = sum(1 for v in col_a_vals if _re.fullmatch(r'\d+', v))
    has_serial_col = len(col_a_vals) > 0 and (numeric_count / len(col_a_vals)) > 0.6

    # Also skip common header words in the first row
    HEADER_WORDS = {"field", "label", "sr", "sr.", "sr no", "s.no", "s no", "sl",
                    "sl.", "sl no", "no.", "sno", "serial", "particulars", "description",
                    "parameter", "details", "item", ""}

    current_section = "Basic Info"

    for row in all_rows:
        if not row:
            continue

        # Determine label_col and value_col based on serial-number detection
        if has_serial_col:
            if len(row) < 2 or row[1] is None:
                continue
            raw_label = str(row[1]).strip()
            raw_value = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
            doc_link = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        else:
            if row[0] is None:
                continue
            raw_label = str(row[0]).strip()
            raw_value = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            doc_link = str(row[2]).strip() if len(row) > 2 and row[2] else ""

        if not raw_label:
            continue

        # Skip header rows
        if raw_label.lower().strip() in HEADER_WORDS:
            continue

        # Detect section-header rows: label present but value is empty and the
        # label looks like a section title (e.g. all-caps, or ends with colon,
        # or is a known category-style phrase).
        if not raw_value:
            label_lower = raw_label.lower()
            looks_like_section = (
                raw_label.isupper() or
                raw_label.endswith(":") or
                any(kw in label_lower for kw in [
                    "general information", "financial", "contact", "address",
                    "registration", "legal", "manpower", "infrastructure",
                    "compliance", "business profile", "capability", "identity",
                    "project", "reference", "certification", "bank",
                ])
            )
            if looks_like_section:
                current_section = raw_label.strip().rstrip(":")
                continue

        field_key = normalize_field_key(raw_label)
        if not field_key or _re.fullmatch(r'\d+', field_key):
            # Pure-numeric keys are serial numbers that slipped through, skip
            continue

        try:
            existing = db.query(CompanyField).filter(CompanyField.field_key == field_key).first()
            if existing:
                existing.value = raw_value
                existing.document_link = doc_link
                existing.last_updated = datetime.utcnow()
                skipped += 1
            else:
                db.add(CompanyField(
                    category=current_section,
                    field_key=field_key,
                    field_label=raw_label,
                    value=raw_value,
                    document_link=doc_link
                ))
                db.flush()  # catch IntegrityError per-row, not at the end
                imported += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Row '{raw_label}': {str(e)[:120]}")
            continue

    db.commit()
    result = {"imported": imported, "updated": skipped}
    if errors:
        result["errors"] = errors[:10]  # return first 10 errors max
    return result

@router.post("/import-projects")
async def import_projects_from_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from models.database import ProjectReference
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    imported = 0
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        headers = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(h).strip().lower() if h else "" for h in row]
                continue
                
            if not any(row):
                continue
                
            row_data = {}
            for h, val in zip(headers, row):
                if not h: continue
                val_str = str(val).strip() if val is not None else ""
                if "project name" in h or "name of project" in h: row_data["project_name"] = val_str
                elif "client" in h and "rep" not in h: row_data["client_name"] = val_str
                elif "region" in h: row_data["region"] = val_str
                elif "location" in h: row_data["location"] = val_str
                elif "area" in h: row_data["area_sqft"] = val_str
                elif "consultant" in h: row_data["consultant"] = val_str
                elif "pmc" in h: row_data["pmc"] = val_str
                elif "sector" in h: row_data["project_sector"] = val_str
                elif "type" in h: row_data["project_type"] = val_str
                elif "value" in h: row_data["project_value"] = val_str
                elif "status" in h: row_data["status"] = val_str
                elif "start" in h: row_data["start_date"] = val_str
                elif "end" in h or "completion" in h: row_data["end_date"] = val_str
                elif "rep" in h or "representative" in h:
                    import re
                    if re.search(r'name|designation|email|contact', val_str, re.IGNORECASE) and (":" in val_str or "\n" in val_str):
                        name_m = re.search(r'Name\s*[:\-]?\s*(.*?)(?:Designation|$)', val_str, re.IGNORECASE | re.DOTALL)
                        if name_m: row_data["client_rep_name"] = name_m.group(1).strip()
                        
                        desig_m = re.search(r'Designation\s*[:\-]?\s*(.*?)(?:Email|$)', val_str, re.IGNORECASE | re.DOTALL)
                        if desig_m: row_data["client_rep_designation"] = desig_m.group(1).strip()
                        
                        email_m = re.search(r'Email(?: ID)?\s*[:\-]?\s*(.*?)(?:Contact|$)', val_str, re.IGNORECASE | re.DOTALL)
                        if email_m: row_data["client_rep_email"] = email_m.group(1).strip()
                        
                        phone_m = re.search(r'Contact(?: Number)?\s*[:\-]?\s*(.*)', val_str, re.IGNORECASE | re.DOTALL)
                        if phone_m: row_data["client_rep_phone"] = phone_m.group(1).strip()
                    else:
                        row_data["client_rep_name"] = val_str
                elif "designation" in h: row_data["client_rep_designation"] = val_str
                elif "email" in h: row_data["client_rep_email"] = val_str
                elif "phone" in h or "contact" in h: row_data["client_rep_phone"] = val_str
                elif "cert" in h: row_data["certifications"] = val_str
    
            if not row_data.get("project_name"):
                continue
                
            # check if exists
            existing = db.query(ProjectReference).filter(ProjectReference.project_name == row_data["project_name"]).first()
            if existing:
                for k, v in row_data.items():
                    setattr(existing, k, v)
            else:
                row_data["source_file"] = file.filename
                db.add(ProjectReference(**row_data))
            imported += 1
            
    db.commit()
    return {"imported": imported}

# ── SEED FROM HTL DATA ────────────────────────────────────────────────────
@router.post("/seed")
def seed_htl_data(db: Session = Depends(get_db)):
    """Seed DB with deduplicated HTL pre-qual data."""
    existing = db.query(CompanyField).count()
    if existing > 0:
        return {"message": "DB already seeded", "count": existing}

    seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed_data", "company_seed.json")
    if not os.path.exists(seed_path):
        raise HTTPException(
            500,
            "Seed data file not found at backend/seed_data/company_seed.json. "
            "This file holds company-identifying data (GSTIN, PAN, contact numbers) "
            "and is intentionally gitignored -- ask an admin for a copy."
        )
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        db.add(CompanyField(**item))
    db.commit()
    return {"seeded": len(data)}
