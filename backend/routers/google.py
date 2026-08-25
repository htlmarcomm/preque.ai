from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.database import get_db, FilledForm
from routers.forms import OUTPUT_DIR, UPLOAD_DIR
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os, io, re, openpyxl
from routers.forms import write_filled_excel

router = APIRouter()

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_google_drive_service():
    creds_path = "google-credentials.json"
    if not os.path.exists(creds_path):
        raise ValueError(f"Google credentials file '{creds_path}' not found in the backend directory.")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

@router.post("/export-form/{form_id}")
def export_form_to_google_sheets(form_id: int, db: Session = Depends(get_db)):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form: raise HTTPException(404, "Form not found")
    
    orig_path = os.path.join(UPLOAD_DIR, form.original_filename)
    if not os.path.exists(orig_path): raise HTTPException(404, "Original file not found")
    
    # Check if filled file is already generated, if not generate it
    out_path = os.path.join(OUTPUT_DIR, f"filled_{form_id}_{form.original_filename}")
    if not os.path.exists(out_path):
        with open(orig_path, "rb") as f:
            original_bytes = f.read()
        wb = openpyxl.load_workbook(io.BytesIO(original_bytes))
        sheet_name = wb.sheetnames[0]
        cell_fills = {}
        for key, value in (form.filled_data or {}).items():
            cell = key.split("!", 1)[1] if "!" in key else key
            if re.match(r'^[A-Z]{1,3}\d+$', cell):
                cell_fills[cell] = value
        filled_bytes = write_filled_excel(original_bytes, sheet_name, cell_fills)
        with open(out_path, "wb") as f:
            f.write(filled_bytes)
    
    try:
        service = get_google_drive_service()
    except Exception as e:
        raise HTTPException(500, f"Google Drive setup failed: {str(e)}")
        
    try:
        file_metadata = {
            'name': f"{form.client_name} - Pre-Qualification Form",
            'mimeType': 'application/vnd.google-apps.spreadsheet'
        }
        media = MediaFileUpload(out_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()

        # Anyone with the link can view. NOT 'writer' -- these exports contain
        # GSTIN/PAN/financials, so leaving them world-editable indefinitely is
        # a needless risk. If a specific recipient needs edit access, share
        # that explicitly from Drive rather than opening it to anyone.
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        service.permissions().create(fileId=file.get('id'), body=permission).execute()
        
        return {"link": file.get('webViewLink')}
    except Exception as e:
        raise HTTPException(500, f"Google Drive upload failed: {str(e)}")
