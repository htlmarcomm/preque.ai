from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from models.database import get_db, ProjectFile, DocumentChunk
from pydantic import BaseModel
from typing import Optional, List
import os, shutil, logging
from services.doc_extractor import extract_text, chunk_text
from services.vector_store import VectorStore
from utils import sanitize_filename

router = APIRouter()
UPLOAD_DIR = "uploads/project_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
logger = logging.getLogger(__name__)

class DocumentCreate(BaseModel):
    name: str
    doc_type: str
    sharepoint_link: Optional[str] = ""
    tags: Optional[List[str]] = []

class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    doc_type: Optional[str] = None
    sharepoint_link: Optional[str] = None
    tags: Optional[List[str]] = None

# FIX (P1): added "MSME Registration Certificate" -- the Logos Group PQ form test
# revealed the form explicitly asks for an MSME/Udyam registration number and there
# was previously no doc type anywhere that could ever represent it, so it could never
# be checklisted no matter what the form said.
DOC_TYPES = [
    "Certificate of Incorporation",
    "GST Certificate",
    "Company PAN Card",
    "MSME Registration Certificate",
    "Memorandum of Association",
    "Articles of Association",
    "ISO Certificate",
    "Quality Policy",
    "Organisation Chart",
    "Plant & Equipment List",
    "Solvency Certificate",
    "Insurance Certificate",
    "Project Completion Certificate",
    "Client Appreciation Letter",
    "Safety Programme",
    "Balance Sheet",
    "ITR / Income Tax Clearance",
    "PF Registration Certificate",
    "ESI Registration Certificate",
    "Bank Statement",
    "Work Order / LOA",
    "Other"
]

@router.get("/types")
def get_doc_types():
    return {"types": DOC_TYPES}

@router.get("/")
def list_documents(doc_type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ProjectFile).filter(ProjectFile.source_module == "document")
    if doc_type:
        q = q.filter(ProjectFile.doc_type == doc_type)
    docs = q.order_by(ProjectFile.doc_type, ProjectFile.name).all()
    result = []
    for d in docs:
        item = {k: v for k, v in d.__dict__.items() if not k.startswith("_")}
        if d.filename:
            item["download_url"] = f"/api/documents/download/{d.id}"
        result.append(item)
    return {"documents": result}

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    name: str,
    doc_type: str,
    sharepoint_link: Optional[str] = "",
    tags: Optional[str] = "",
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    filename = None
    dest = None
    if file:
        safe_name = sanitize_filename(file.filename)
        dest = os.path.join(UPLOAD_DIR, safe_name)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        filename = safe_name

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    doc = ProjectFile(
        name=name,
        category="Company Compliance Data",
        doc_type=doc_type,
        source_module="document",
        filename=filename,
        sharepoint_link=sharepoint_link,
        tags=tag_list
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    if dest:
        try:
            pages = extract_text(dest)
            chunks = chunk_text(pages)
            for chunk in chunks:
                doc_chunk = DocumentChunk(
                    source_type="document",
                    source_id=doc.id,
                    sheet_or_page=chunk["sheet_or_page"],
                    chunk_index=chunk["chunk_index"],
                    text=chunk["text"]
                )
                db.add(doc_chunk)
            db.commit()
            background_tasks.add_task(VectorStore().embed_missing, db)
        except Exception as e:
            logger.warning(f"Failed to extract text for document {doc.id}: {e}")
            
    return {k: v for k, v in doc.__dict__.items() if not k.startswith("_")}

@router.put("/{doc_id}")
def update_document(doc_id: int, data: DocumentUpdate, db: Session = Depends(get_db)):
    doc = db.query(ProjectFile).filter(ProjectFile.id == doc_id, ProjectFile.source_module == "document").first()
    if not doc:
        raise HTTPException(404, "Document not found")
    for k, v in data.dict(exclude_none=True).items():
        setattr(doc, k, v)
    db.commit()
    db.refresh(doc)
    return {k: v for k, v in doc.__dict__.items() if not k.startswith("_")}

@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(ProjectFile).filter(ProjectFile.id == doc_id, ProjectFile.source_module == "document").first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.filename:
        path = os.path.join(UPLOAD_DIR, doc.filename)
        if os.path.exists(path):
            os.remove(path)
    db.delete(doc)
    db.commit()
    return {"deleted": doc_id}

@router.get("/download/{doc_id}")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    doc = db.query(ProjectFile).filter(ProjectFile.id == doc_id, ProjectFile.source_module == "document").first()
    if not doc or not doc.filename:
        raise HTTPException(404, "File not found")
    path = os.path.join(UPLOAD_DIR, doc.filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing from disk")
    return FileResponse(path, filename=doc.filename)

@router.post("/seed")
def seed_documents(db: Session = Depends(get_db)):
    existing = db.query(ProjectFile).filter(ProjectFile.source_module == "document").count()
    if existing > 0:
        return {"message": "Documents already seeded", "count": existing}
    docs = [
        ("Certificate of Incorporation", "Certificate of Incorporation", ["legal", "registration"]),
        ("GST Registration Certificate", "GST Certificate", ["legal", "tax", "gst"]),
        ("Company PAN Card", "Company PAN Card", ["legal", "tax", "pan"]),
        ("MSME / Udyam Registration Certificate", "MSME Registration Certificate", ["legal", "msme", "udyam"]),
        ("Memorandum of Association", "Memorandum of Association", ["legal"]),
        ("Articles of Association", "Articles of Association", ["legal"]),
        ("ISO 45001 Certificate", "ISO Certificate", ["quality", "iso", "certification"]),
        ("Quality Policy Document", "Quality Policy", ["quality"]),
        ("Organisation Chart", "Organisation Chart", ["manpower", "structure"]),
        ("Plant & Equipment List", "Plant & Equipment List", ["technical", "equipment"]),
        ("Solvency Certificate", "Solvency Certificate", ["financial", "bank"]),
        ("Insurance Certificate", "Insurance Certificate", ["compliance", "insurance"]),
        ("Balance Sheet FY 2023-24", "Balance Sheet", ["financial", "turnover"]),
        ("Balance Sheet FY 2022-23", "Balance Sheet", ["financial", "turnover"]),
        ("Balance Sheet FY 2021-22", "Balance Sheet", ["financial", "turnover"]),
        ("ITR Certificate", "ITR / Income Tax Clearance", ["tax", "financial"]),
        ("PF Registration Certificate", "PF Registration Certificate", ["compliance", "pf"]),
        ("ESI Registration Certificate", "ESI Registration Certificate", ["compliance", "esi"]),
        ("Taj Hotel LOA", "Work Order / LOA", ["awards", "appreciation"]),
        ("UBS LOA", "Work Order / LOA", ["awards", "appreciation"]),
        ("German Consulate LOA", "Work Order / LOA", ["awards", "appreciation"]),
        ("EHS Safety Programme", "Safety Programme", ["safety", "ehs"]),
        ("Client List – Completed Projects", "Other", ["clients", "projects"]),
    ]
    for name, doc_type, tags in docs:
        db.add(ProjectFile(
            name=name,
            category="Company Compliance Data",
            doc_type=doc_type,
            source_module="document",
            tags=tags,
            sharepoint_link=""
        ))
    db.commit()
    return {"seeded": len(docs)}
