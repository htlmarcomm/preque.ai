from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from models.database import get_db, Base, engine, DocumentChunk, ProjectFile
from pydantic import BaseModel
from typing import Optional
import openpyxl, io, os, json, logging, zipfile
from datetime import datetime
from services.doc_extractor import extract_text, chunk_text
from services.vector_store import VectorStore
from utils import sanitize_filename, enforce_upload_size

router = APIRouter()
FILES_DIR = "uploads/project_files"
os.makedirs(FILES_DIR, exist_ok=True)
logger = logging.getLogger(__name__)

CATEGORIES = [
    "Project Registry", 
    "Client Specific Data", 
    "Company General Data", 
    "Company Financial Data",
    "Company Compliance Data",
    "Employee Details",
    "Company Reports",
    "Project Completion Certificate and Appreciation",
    "Safety and HSE",
    "Policies"
]

class FileUpdate(BaseModel):
    name:             Optional[str] = None
    client:           Optional[str] = None
    category:         Optional[str] = None
    sharepoint_link:  Optional[str] = None
    tags:             Optional[list] = None
    notes:            Optional[str]  = None

def read_excel_preview(filepath: str) -> dict:
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    preview = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        headers = []
        header_set = False
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            cleaned = [str(v).strip() if v is not None else "" for v in row]
            if not any(cleaned):
                continue
            if not header_set:
                headers = cleaned
                header_set = True
            else:
                rows.append(cleaned)
            if i > 5000:
                break
        preview[sheet_name] = {
            "headers": headers,
            "rows": rows[:5000],
            "total_rows": len(rows)
        }
    wb.close()
    return preview

def _extract_and_index(dest: str, source_id: int, db: Session):
    """
    Runs text extraction + chunking + embedding for an uploaded/attached
    file, off the request path.

    FIX (P0 -- a single malformed file could hang the ENTIRE backend for
    every user): this used to run synchronously inside the upload request,
    inside a try/except. That catches a clean failure (extract_text raising),
    but a corrupt/malformed PDF doesn't fail cleanly -- pdf2image's fallback
    shells out to poppler's pdftoppm, which can hang indefinitely on garbage
    input rather than erroring. Since this ran inline in an `async def`
    route with no `await`/executor offload, that hang blocked the single
    asyncio event loop thread -- not just that one request, but every other
    request the backend was serving, including /api/health. Reproduced
    directly: a fake "test file" saved with a .pdf extension hung the whole
    server past the point even a health check would respond, until the
    process was killed. Moving it to a background task means a hang here
    only leaves that one file's search-indexing incomplete -- the actual
    upload/attach response the user is waiting on already went out.
    """
    try:
        pages = extract_text(dest)
        chunks = chunk_text(pages)
        for chunk in chunks:
            db.add(DocumentChunk(
                source_type="project_file", source_id=source_id,
                sheet_or_page=chunk["sheet_or_page"], chunk_index=chunk["chunk_index"], text=chunk["text"]
            ))
        db.commit()
        VectorStore().embed_missing(db)
    except Exception as e:
        logger.warning(f"Failed to extract/index text for project file {source_id}: {e}")


@router.get("/categories")
def get_categories():
    return {"categories": CATEGORIES}

@router.get("/")
def list_files(
    client:   Optional[str] = None,
    category: Optional[str] = None,
    search:   Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(ProjectFile)
    if client:   q = q.filter(ProjectFile.client.ilike(f"%{client}%"))
    if category: q = q.filter(ProjectFile.category == category)
    if search:
        q = q.filter(
            ProjectFile.name.ilike(f"%{search}%") |
            ProjectFile.client.ilike(f"%{search}%") |
            ProjectFile.notes.ilike(f"%{search}%")
        )
    files = q.order_by(ProjectFile.uploaded_at.desc()).all()
    return {"files": [
        {k: v for k, v in f.__dict__.items() if not k.startswith("_")}
        for f in files
    ]}

@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    name:            str  = Form(...),
    client:          str  = Form(""),
    category:        str  = Form("Company General Data"),
    sharepoint_link: str  = Form(""),
    tags:            str  = Form(""),
    notes:           str  = Form(""),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    filename   = None
    sheet_names = []
    row_count  = 0
    dest = None
    if file:
        safe = sanitize_filename(file.filename)
        dest = os.path.join(FILES_DIR, safe)
        contents = await file.read()
        enforce_upload_size(len(contents))
        with open(dest, "wb") as f:
            f.write(contents)
        filename = safe
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
            sheet_names = wb.sheetnames
            ws = wb.active
            row_count = ws.max_row or 0
            wb.close()
        except Exception:
            pass
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    pf = ProjectFile(
        name=name, client=client, category=category,
        filename=filename, sharepoint_link=sharepoint_link,
        tags=tag_list, sheet_names=sheet_names,
        row_count=row_count, notes=notes
    )
    db.add(pf)
    db.commit()
    db.refresh(pf)
    
    if dest:
        background_tasks.add_task(_extract_and_index, dest, pf.id, db)

    return {k: v for k, v in pf.__dict__.items() if not k.startswith("_")}


@router.put("/{file_id}")
def update_file(file_id: int, data: FileUpdate, db: Session = Depends(get_db)):
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf: raise HTTPException(404, "File not found")
    for k, v in data.dict(exclude_none=True).items():
        setattr(pf, k, v)
    db.commit(); db.refresh(pf)
    return {k: v for k, v in pf.__dict__.items() if not k.startswith("_")}

@router.post("/{file_id}/attach-file")
async def attach_file(file_id: int, background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Attaches an actual file to an EXISTING File Cabinet entry that currently
    has neither a file nor a SharePoint link -- e.g. the placeholder rows
    seeded from the default document list (name + category + tags, but no
    file ever uploaded). Without this there was no way to add the real file
    to that row short of deleting it and creating a new one from scratch,
    losing whatever tags/notes/category were already set on it.
    """
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf: raise HTTPException(404, "File not found")
    if pf.filename:
        raise HTTPException(400, "This entry already has a file attached. Delete it first if you want to replace it.")

    safe = sanitize_filename(file.filename)
    dest = os.path.join(FILES_DIR, safe)
    contents = await file.read()
    enforce_upload_size(len(contents))
    with open(dest, "wb") as f:
        f.write(contents)

    pf.filename = safe
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
        pf.sheet_names = wb.sheetnames
        pf.row_count = wb.active.max_row or 0
        wb.close()
    except Exception:
        pass
    db.commit(); db.refresh(pf)

    background_tasks.add_task(_extract_and_index, dest, pf.id, db)

    return {k: v for k, v in pf.__dict__.items() if not k.startswith("_")}


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db)):
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf: raise HTTPException(404, "File not found")
    if pf.filename:
        p = os.path.join(FILES_DIR, pf.filename)
        if os.path.exists(p): os.remove(p)
    db.delete(pf); db.commit()
    return {"deleted": file_id}

@router.get("/{file_id}/preview")
def preview_file(file_id: int, db: Session = Depends(get_db)):
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf: raise HTTPException(404, "File not found")
    if not pf.filename:
        raise HTTPException(400, "No file uploaded — only SharePoint link stored")
    path = os.path.join(FILES_DIR, pf.filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing from disk")
    try:
        data = read_excel_preview(path)
        return {"file_id": file_id, "name": pf.name, "sheets": data}
    except Exception as e:
        raise HTTPException(500, f"Could not read Excel: {str(e)}")

@router.get("/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db)):
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf or not pf.filename: raise HTTPException(404, "File not found")
    path = os.path.join(FILES_DIR, pf.filename)
    if not os.path.exists(path): raise HTTPException(404, "File missing")
    return FileResponse(path, filename=pf.filename)

# Route lives at the router root ("/download-all"), not under "/{file_id}/...",
# so it can't collide with download_file above regardless of registration
# order -- the path shapes are different, not the same prefix with a
# different suffix.
@router.get("/download-all")
def download_all_files(
    client:   Optional[str] = None,
    category: Optional[str] = None,
    search:   Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Zips every File Cabinet entry that has an actual uploaded file (skips
    SharePoint-link-only entries -- there's no local file to zip for those)
    and streams it back as one .zip. Accepts the same client/category/search
    filters as the list endpoint, so "download all" respects whatever the
    user currently has filtered/searched for, not literally every file in
    the system regardless of view.
    """
    q = db.query(ProjectFile)
    if client:   q = q.filter(ProjectFile.client.ilike(f"%{client}%"))
    if category: q = q.filter(ProjectFile.category == category)
    if search:
        q = q.filter(
            ProjectFile.name.ilike(f"%{search}%") |
            ProjectFile.client.ilike(f"%{search}%") |
            ProjectFile.notes.ilike(f"%{search}%")
        )
    files = q.filter(ProjectFile.filename.isnot(None)).order_by(ProjectFile.category, ProjectFile.name).all()
    if not files:
        raise HTTPException(404, "No downloadable files match the current filters.")

    buf = io.BytesIO()
    # Duplicate display names (two files both called "Insurance Certificate",
    # a common real-world case since `name` isn't unique) would silently
    # overwrite each other inside the zip otherwise -- number any repeat.
    used_names = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pf in files:
            path = os.path.join(FILES_DIR, pf.filename)
            if not os.path.exists(path):
                continue  # DB row survives a missing file on disk elsewhere in this router; skip rather than 500 the whole batch
            ext = os.path.splitext(pf.filename)[1]
            base = sanitize_filename(pf.name or pf.filename) or "file"
            base = os.path.splitext(base)[0]
            category_dir = (pf.category or "Uncategorized").replace("/", "-")
            arcname = f"{category_dir}/{base}{ext}"
            n = used_names.get(arcname, 0)
            if n:
                arcname = f"{category_dir}/{base} ({n}){ext}"
            used_names[f"{category_dir}/{base}{ext}"] = n + 1
            zf.write(path, arcname)

    buf.seek(0)
    zip_filename = f"file_cabinet_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )

# FIX (P0 -- stored XSS via file upload): serving an arbitrary uploaded file
# "inline" lets the browser render it in this API's own origin using
# whatever content-type it guesses from the extension. Upload has no file-type
# restriction, so a file named e.g. "x.html" or "x.svg" containing
# <script>...</script> would execute when this endpoint is hit directly (the
# frontend's own extension whitelist for the preview button is client-side
# only -- it doesn't stop someone from hitting this URL directly). Only ever
# render inline for types that can't contain executable content; everything
# else is forced to download instead.
INLINE_SAFE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.get("/{file_id}/view")
def view_file_inline(file_id: int, db: Session = Depends(get_db)):
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not pf or not pf.filename: raise HTTPException(404, "File not found")
    path = os.path.join(FILES_DIR, pf.filename)
    if not os.path.exists(path): raise HTTPException(404, "File missing")
    ext = os.path.splitext(pf.filename)[1].lower()
    if ext not in INLINE_SAFE_EXTENSIONS:
        return FileResponse(path, filename=pf.filename)
    return FileResponse(path, content_disposition_type="inline")

@router.post("/add-sharepoint")
def add_sharepoint_link(
    name:            str = Form(...),
    client:          str = Form(""),
    category:        str = Form("Company General Data"),
    sharepoint_link: str = Form(...),
    tags:            str = Form(""),
    notes:           str = Form(""),
    db: Session = Depends(get_db)
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    pf = ProjectFile(
        name=name, client=client, category=category,
        sharepoint_link=sharepoint_link, tags=tag_list, notes=notes
    )
    db.add(pf); db.commit(); db.refresh(pf)
    return {k: v for k, v in pf.__dict__.items() if not k.startswith("_")}
