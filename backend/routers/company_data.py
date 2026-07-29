from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from models.database import get_db, CompanyField
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import openpyxl, io, json
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
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    ws = wb.active
    imported = 0
    skipped = 0
    for row in ws.iter_rows(values_only=True):
        if not row or not row[0]:
            continue
        field_label = str(row[0]).strip()
        value = str(row[1]).strip() if row[1] is not None else ""
        doc_link = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        if field_label.lower() in ("field", "label", ""):
            continue
        field_key = normalize_field_key(field_label)
        existing = db.query(CompanyField).filter(CompanyField.field_key == field_key).first()
        if existing:
            existing.value = value
            existing.document_link = doc_link
            existing.last_updated = datetime.utcnow()
            skipped += 1
        else:
            db.add(CompanyField(
                category="Basic Info",
                field_key=field_key,
                field_label=field_label,
                value=value,
                document_link=doc_link
            ))
            imported += 1
    db.commit()
    return {"imported": imported, "updated": skipped}

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

    data = [
    {
        "category": "Company Identity",
        "field_key": "company_name",
        "field_label": "Company Name",
        "value": "HTL Aircon Pvt Ltd",
        "aliases": [
            "contractor name",
            "name of firm",
            "organization name",
            "supplier name"
        ]
    },
    {
        "category": "Company Identity",
        "field_key": "brand_name",
        "field_label": "Brand Name",
        "value": "HTL",
        "aliases": [
            "trade name"
        ]
    },
    {
        "category": "Company Identity",
        "field_key": "company_type",
        "field_label": "Company Type",
        "value": "Private Limited Company",
        "aliases": [
            "nature of firm",
            "type of entity"
        ]
    },
    {
        "category": "Company Identity",
        "field_key": "establishment_year",
        "field_label": "Establishment Year",
        "value": "1996",
        "aliases": [
            "founded",
            "year of establishment",
            "year started"
        ]
    },
    {
        "category": "Company Identity",
        "field_key": "incorporation_date",
        "field_label": "Incorporation Date",
        "value": "16/01/1996",
        "aliases": [
            "date of incorporation",
            "registration date"
        ]
    },
    {
        "category": "Address & Contact",
        "field_key": "website",
        "field_label": "Website",
        "value": "https://www.htlaircon.com",
        "aliases": [
            "Company Website",
            "URL",
            "web address"
        ]
    },
    {
        "category": "Address & Contact",
        "field_key": "address",
        "field_label": "Registered Address",
        "value": "38, Nand Ghanshyam Industrial Estate, Off Mahakali Caves Rd, Next to Sun Pharma, Behind Paper Box office, Andheri East, Mumbai",
        "aliases": [
            "address",
            "correspondence address",
            "mailing address",
            "office address",
            "head office",
            "head office address"
        ]
    },
    {
        "category": "Address & Contact",
        "field_key": "telephone",
        "field_label": "Telephone No.",
        "value": "022-42174747",
        "aliases": [
            "Telephone Number",
            "landline",
            "phone",
            "tel"
        ]
    },
    {
        "category": "Address & Contact",
        "field_key": "fax",
        "field_label": "Fax No.",
        "value": "022-42174748 / 49",
        "aliases": [
            "Fax Number",
            "fax number"
        ]
    },
    {
        "category": "Address & Contact",
        "field_key": "email",
        "field_label": "Email",
        "value": "sachin.baraskar@htlaircon.com",
        "aliases": [
            "contact email",
            "e-mail",
            "email address"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_1_name",
        "field_label": "Contact Person 1 \u2013 Name",
        "value": "Mr. Sachin Baraskar",
        "aliases": [
            "Contact Person 1 - Name",
            "Contact Person 1 Name",
            "authorized signatory",
            "contact person"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_1_designation",
        "field_label": "Contact Person 1 \u2013 Designation",
        "value": "MEP Head - PAN India",
        "aliases": [
            "Contact Person 1 - Designation",
            "Contact Person 1 Designation",
            "designation"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_1_mobile",
        "field_label": "Contact Person 1 \u2013 Mobile",
        "value": "85399 83333",
        "aliases": [
            "Contact Person 1 - Mobile",
            "Contact Person 1 Mobile",
            "cell phone",
            "mobile"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_2_name",
        "field_label": "Contact Person 2 \u2013 Name",
        "value": "Mr. Arun Kumar",
        "aliases": [
            "Contact Person 2 - Name",
            "Contact Person 2 Name"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_2_designation",
        "field_label": "Contact Person 2 \u2013 Designation",
        "value": "AGM",
        "aliases": [
            "Contact Person 2 - Designation",
            "Contact Person 2 Designation"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "contact_person_2_mobile",
        "field_label": "Contact Person 2 \u2013 Mobile",
        "value": "98922 37561",
        "aliases": [
            "Contact Person 2 - Mobile",
            "Contact Person 2 Mobile"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "director_name",
        "field_label": "Director Name",
        "value": "Lavinder Singh Duggal",
        "aliases": [
            "MD",
            "director",
            "managing director"
        ]
    },
    {
        "category": "Contact Persons",
        "field_key": "din",
        "field_label": "DIN",
        "value": "01733700",
        "aliases": [
            "director identification number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "cin",
        "field_label": "CIN No.",
        "value": "U29306MH2007PTC173671",
        "aliases": [
            "CIN",
            "CIN Number",
            "CIN no",
            "company identification number",
            "corporate identity number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "gstin",
        "field_label": "GSTIN",
        "value": "27AABCH9057L1Z4",
        "aliases": [
            "GST no",
            "GST number",
            "GST registration",
            "GSTIN no"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "pan",
        "field_label": "PAN No.",
        "value": "AABCH9057L",
        "aliases": [
            "PAN",
            "PAN Number",
            "PAN number",
            "permanent account number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "msme_reg_no",
        "field_label": "MSME Registration No.",
        "value": "",
        "aliases": [
            "MSME No",
            "MSME No.",
            "MSME Registration Number",
            "Udyam Registration Number",
            "Udyam No"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "esi_reg_no",
        "field_label": "ESI Registration No.",
        "value": "35000074410000999",
        "aliases": [
            "ESI Registration Number",
            "ESI no",
            "ESIC number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "pf_reg_no",
        "field_label": "PF Registration No.",
        "value": "MH/PF/APP/211388/ENF VIII/1006",
        "aliases": [
            "EPF no",
            "PF Registration Number",
            "PF number",
            "provident fund"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "tds_no",
        "field_label": "TDS No.",
        "value": "MUMH11736E",
        "aliases": [
            "TAN",
            "TDS Number",
            "tax deduction account number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "ptrc_no",
        "field_label": "PTRC No.",
        "value": "27770637930P",
        "aliases": [
            "PTRC Number",
            "profession tax registration"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "ptec_no",
        "field_label": "PTEC No.",
        "value": "99861614598P",
        "aliases": [
            "PTEC Number"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "wct_reg",
        "field_label": "WCT Registration No.",
        "value": "",
        "aliases": [
            "WCT Registration Number",
            "WCT no",
            "works contract tax"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "iso_certified",
        "field_label": "ISO Certified",
        "value": "Yes",
        "aliases": [
            "ISO Certified?",
            "ISO certification",
            "quality certification"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "design_engineers",
        "field_label": "Design Engineers",
        "value": "11",
        "aliases": [
            "technical designers"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "senior_project_managers",
        "field_label": "Senior Project Managers",
        "value": "22",
        "aliases": [
            "senior PMs",
            "sr project managers"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "planning_commercial_team",
        "field_label": "Planning / Commercial Team",
        "value": "10",
        "aliases": [
            "commercial team",
            "planning team"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "site_engineers",
        "field_label": "Site Engineers",
        "value": "25",
        "aliases": [
            "field engineers"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "supervisors",
        "field_label": "Supervisors",
        "value": "30",
        "aliases": []
    },
    {
        "category": "Manpower",
        "field_key": "safety_personnel",
        "field_label": "Safety Personnel",
        "value": "25",
        "aliases": [
            "EHS staff",
            "safety engineers"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "quality_personnel",
        "field_label": "Quality Personnel",
        "value": "5",
        "aliases": [
            "QA/QC staff"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "skilled_technicians",
        "field_label": "Skilled Technicians",
        "value": "140",
        "aliases": [
            "skilled workers",
            "technicians"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "total_inhouse_manpower",
        "field_label": "Total In-House Manpower",
        "value": "600",
        "aliases": [
            "staff strength",
            "total employees",
            "total staff"
        ]
    },
    {
        "category": "Manpower",
        "field_key": "total_outsourced_manpower",
        "field_label": "Total Outsourced Manpower",
        "value": "2000",
        "aliases": [
            "contract labour",
            "outsourced workers"
        ]
    },
    {
        "category": "Infrastructure",
        "field_key": "mfg_unit_1_location",
        "field_label": "Manufacturing Unit 1",
        "value": "Murbad, Maharashtra",
        "aliases": [
            "Manufacturing Unit 1 - Location",
            "Manufacturing Unit 1 Location",
            "factory",
            "workshop"
        ]
    },
    {
        "category": "Infrastructure",
        "field_key": "mfg_unit_2_location",
        "field_label": "Manufacturing Unit 2",
        "value": "Taloja, Maharashtra",
        "aliases": [
            "Manufacturing Unit 2 - Location",
            "Manufacturing Unit 2 Location"
        ]
    },
    {
        "category": "Financial",
        "field_key": "bank_guarantee_limit",
        "field_label": "Bank Guarantee Limit (\u20b9 Crore)",
        "value": "76",
        "aliases": [
            "BG limit",
            "Bank Guarantee Limit (\u20b9 Cr)",
            "bank guarantee capacity"
        ]
    },
    {
        "category": "Financial",
        "field_key": "banker_credit_limit",
        "field_label": "Banker Credit Limit (\u20b9 Crore)",
        "value": "21",
        "aliases": [
            "Banker Credit Limit (\u20b9 Cr)",
            "credit limit",
            "working capital limit"
        ]
    },
    {
        "category": "Financial",
        "field_key": "litigation",
        "field_label": "Any Litigation / Arbitration",
        "value": "NA",
        "aliases": [
            "Litigation & Arbitration Cases",
            "Litigation and Arbitration Cases",
            "arbitration",
            "court cases",
            "legal disputes",
            "pending litigation"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "primary_scope",
        "field_label": "Primary Scope of Work",
        "value": "MEP \u2013 Electrical, HVAC, PHE, Fire Fighting, IBMS",
        "aliases": [
            "Scope of Work / Services",
            "business activity",
            "nature of work",
            "services offered",
            "type of work"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "major_consultants",
        "field_label": "Major Consultants Worked With",
        "value": "JLL, CBRE, Cushman & Wakefield, Hill International, SC Consultants, Epicons, Ecofirst",
        "aliases": [
            "consultants",
            "list of consultants"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "major_architects",
        "field_label": "Major Architects Worked With",
        "value": "As per attached profile",
        "aliases": [
            "architects"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "major_pmcs",
        "field_label": "PMCs Worked With",
        "value": "JLL, CBRE, Cushman & Wakefield",
        "aliases": [
            "Major PMCs Worked With",
            "PMC",
            "project management consultants"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "major_suppliers",
        "field_label": "Major Suppliers",
        "value": "Daikin, Erlab, MRC",
        "aliases": [
            "equipment suppliers",
            "material suppliers"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "awards",
        "field_label": "Awards & Recognition",
        "value": "LOA - Taj Hotel, LOA - UBS, LOA - German Consulate, Excellence in Business Award",
        "aliases": [
            "Awards & Recognitions",
            "Awards and Recognition",
            "Awards and Recognitions",
            "achievements",
            "certificates of appreciation",
            "recognitions"
        ]
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "foreign_tie_ups",
        "field_label": "Foreign Tie-Ups",
        "value": "None",
        "aliases": [
            "Tie-up with Indian/Foreign Partners",
            "collaborations",
            "foreign tie-ups",
            "joint venture"
        ]
    },
    {
        "category": "Registration & Legal",
        "field_key": "iso_standard",
        "field_label": "ISO Standard",
        "value": "ISO 45001",
        "aliases": []
    },
    {
        "category": "Manpower",
        "field_key": "other_staff",
        "field_label": "Others (specify)",
        "value": "150",
        "aliases": []
    },
    {
        "category": "Business Profile & Capability",
        "field_key": "sectors_served",
        "field_label": "Sectors Served",
        "value": "Commercial, Hospitality, Data Centers, Residential, Industrial, Healthcare",
        "aliases": []
    },
    {
        "category": "Compliance",
        "field_key": "ehs_system",
        "field_label": "EHS System Implementation",
        "value": "As attached in PDF Format",
        "aliases": []
    },
    {
        "category": "Compliance",
        "field_key": "quality_assurance",
        "field_label": "Quality Assurance Methodology",
        "value": "As attached in Profile",
        "aliases": []
    },
    {
        "category": "Compliance",
        "field_key": "solvency_certificate",
        "field_label": "Solvency Certificate from Banker",
        "value": "As attached in File",
        "aliases": []
    }
]

    for item in data:
        db.add(CompanyField(**item))
    db.commit()
    return {"seeded": len(data)}
