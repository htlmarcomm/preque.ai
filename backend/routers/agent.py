from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from models.database import get_db, CompanyField, FilledForm
from routers.forms import (
    ai_fill_workbook, write_filled_excel_multi,
    build_company_context, get_doc_checklist,
    openai_client, VISION_MODEL, UPLOAD_DIR,
    excel_to_all_sheet_maps, build_workbook_form_json
)
from typing import Optional
import os, json, base64, re, shutil
from datetime import datetime
from services.vector_store import VectorStore

router = APIRouter()

RAG_FALLBACK_THRESHOLD = 0.75

SCREENSHOT_FILL_PROMPT = """You are filling in a Pre-Qualification portal form for HTL Aircon Pvt Ltd.

Look at this screenshot of an online form. For every visible empty field:
- Understand what it is asking
- Find the matching value from the sectioned company data
- Search the most relevant section first, then search the full company data if the answer is not in that section
- Return a JSON array of {label, value} pairs

Example:
[
  {"label": "Company Name", "value": "HTL Aircon Pvt Ltd"},
  {"label": "GST Number", "value": "27AABCH9057L1Z4"}
]

Skip fields you have no data for.
If a field only asks for attachments, certificates, or licenses and does not name a specific document, use "Attached".
Return ONLY the JSON array, no markdown."""


def _get_adjacent_label_factory(cell_label_map):
    def get_adjacent_label(coord):
        match = re.match(r'^([A-Z]+)(\d+)$', coord)
        if not match: return coord
        col_str, row_str = match.groups()
        row = int(row_str)
        col_idx = 0
        for char in col_str:
            col_idx = col_idx * 26 + (ord(char) - ord('A') + 1)
        for i in range(1, min(col_idx, 5)):
            left_col_idx = col_idx - i
            left_col_str = ""
            temp = left_col_idx
            while temp > 0:
                temp, remainder = divmod(temp - 1, 26)
                left_col_str = chr(65 + remainder) + left_col_str
            left_coord = f"{left_col_str}{row}"
            if left_coord in cell_label_map:
                return cell_label_map[left_coord]
        return coord
    return get_adjacent_label


@router.post("/process-excel")
def process_excel_form(
    client_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Fill a (possibly multi-sheet) Excel form like a human would, sheet by sheet:
    1. Build a cell map PER SHEET
    2. Classify each sheet as FILLABLE (has blank fields to fill) or INFO_ONLY
       (cover letters, declarations, auto-calculated summaries â€” left untouched)
    3. Render only FILLABLE sheets to images (one sheet = one set of images)
    4. Send each FILLABLE sheet's image + its own cell map to GPT-4o, so cell
       coordinates never leak across sheets
    5. Write values back to the exact sheet + cell they belong to
    Works for single-sheet OR multi-sheet (e.g. 13-tab) forms alike.
    """
    file_bytes = file.file.read()
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as f:
        f.write(file_bytes)

    company_context = build_company_context(db)
    workbook_form_json = build_workbook_form_json(file_bytes)
    structure_name = f"{safe_name}.form_structure.json"
    structure_path = os.path.join(UPLOAD_DIR, structure_name)
    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(workbook_form_json, f, indent=2, ensure_ascii=False)

    print(f"[1/2] Building per-sheet cell maps + classifying sheets for: {file.filename}")
    try:
        sheet_fills, sheet_status, combined_cell_map, match_summary, fill_sources, pending_project_tables = ai_fill_workbook(
            file_bytes, file.filename, company_context, db, workbook_form_json=workbook_form_json
        )
    except Exception as e:
        raise HTTPException(500, f"Could not process Excel: {str(e)}")

    total_filled_cells = sum(len(f) for f in sheet_fills.values())
    if total_filled_cells == 0 and not pending_project_tables:
        raise HTTPException(
            400,
            "GPT-4o could not fill any fields across any sheet. "
            "Check company data is seeded and the form has recognizable fillable fields."
        )
    print(f"[2/2] Filled {total_filled_cells} cells across {len(sheet_fills)} sheet(s)")

    # Build human-readable display + figure out unknown fields, sheet by sheet
    filled_data = {}
    unknown_fields_objs = []
    total_empty_cells = 0

    for sheet_name, cmap_section in [
        (sn, sec) for sn, sec in (
            (s.split(" ---\n", 1)[0], s)
            for s in combined_cell_map.split("--- SHEET: ")[1:]
        )
    ] if combined_cell_map else []:
        cmap_text = cmap_section.split(" ---\n", 1)[1] if " ---\n" in cmap_section else ""
        cell_label_map = {}
        for line in cmap_text.split("\n"):
            matches = re.findall(r"\[([A-Z]+\d+)\]='([^']*)'", line)
            for coord, val in matches:
                cell_label_map[coord] = val
        get_adjacent_label = _get_adjacent_label_factory(cell_label_map)

        fills = sheet_fills.get(sheet_name, {})
        for cell, value in fills.items():
            label = get_adjacent_label(cell)
            filled_data[f"{sheet_name}!{cell}"] = {
                "label": f"{sheet_name} â€” {label}" if label else f"Cell {cell}",
                "value": value
            }

        all_empty = re.findall(r'\[([A-Z]+\d+)\]=EMPTY', cmap_text)
        total_empty_cells += len(all_empty)
        raw_unknown = [c for c in all_empty if c not in fills]
        for c in raw_unknown:
            lbl = get_adjacent_label(c)
            tagged = f"{sheet_name} â€” {lbl}" if lbl else f"Cell {c}"
            if lbl and lbl != c and tagged not in [u["label"] for u in unknown_fields_objs] and lbl not in [u["label"].split(" â€” ")[-1] for u in unknown_fields_objs]:
                unknown_fields_objs.append({"label": tagged, "cell": f"{sheet_name}!{c}"})

    unknown_fields_objs = unknown_fields_objs[:15]
    
    # PASS 3: RAG Fallback
    vs = VectorStore()
    enriched_unknown = []
    for field_obj in unknown_fields_objs:
        # field string is usually "SheetName â€” FieldLabel"
        field = field_obj["label"]
        label_only = field.split(" â€” ")[-1] if " â€” " in field else field
        
        results = vs.search(db, query=label_only, top_k=3)
        suggestion = None
        source = None
        if results and results[0]["score"] > RAG_FALLBACK_THRESHOLD:
            top_match = results[0]
            suggestion = top_match["text"]
            # To get source name, we need to query the original file based on source_type and source_id.
            # But just keeping it simple and adding the ID or querying later. Let's query it.
            from models.database import ProjectFile, ProjectReference
            if top_match["source_type"] == "project_file":
                pf = db.query(ProjectFile).filter(ProjectFile.id == top_match["source_id"]).first()
                if pf: source = f"{pf.filename or pf.name}, {top_match['sheet_or_page']}"
            elif top_match["source_type"] == "document":
                doc = db.query(ProjectFile).filter(ProjectFile.id == top_match["source_id"], ProjectFile.source_module == "document").first()
                if doc: source = f"{doc.filename or doc.name}, {top_match['sheet_or_page']}"
            elif top_match["source_type"] == "reference":
                ref = db.query(ProjectReference).filter(ProjectReference.id == top_match["source_id"]).first()
                if ref: source = f"Project Reference: {ref.project_name}"
        
        enriched_unknown.append({
            "label": field,
            "suggested_answer": suggestion,
            "suggested_source": source,
            "cell": field_obj["cell"]
        })

    doc_checklist = get_doc_checklist(combined_cell_map, db)

    stored_fills = {}
    for sheet_name, fills in sheet_fills.items():
        for cell, value in fills.items():
            stored_fills[f"{sheet_name}!{cell}"] = filled_data[f"{sheet_name}!{cell}"]

    sheets_summary = {
        sn: ("Filled" if status == "FILLABLE" and sheet_fills.get(sn) else
             "Skipped (info only)" if status == "INFO_ONLY" else
             "No fields matched")
        for sn, status in sheet_status.items()
    }

    form = FilledForm(
        client_name=client_name,
        form_type="excel",
        original_filename=safe_name,
        filled_data=stored_fills,
        unknown_fields=enriched_unknown,
        doc_checklist=doc_checklist,
        fill_sources=fill_sources,
        pending_project_tables=pending_project_tables
    )
    db.add(form); db.commit(); db.refresh(form)

    return {
        "form_id": form.id,
        "client_name": client_name,
        "total_fields": total_empty_cells,
        "auto_filled": total_filled_cells,
        "unknown_count": len(enriched_unknown),
        "filled_data": filled_data,
        "unknown_fields": enriched_unknown,
        "doc_checklist": doc_checklist,
        "sheets_processed": sheets_summary,
        "match_summary": match_summary,
        "ai_used": "OpenPyXL section JSON + Deterministic Fuzzy/Financial/Attachment Match + Deterministic Vertical-Table Detection + RAG Fallback + GPT-4o vision",
        "pending_project_tables": pending_project_tables,
        "form_structure_json": structure_name
    }


@router.post("/process-image")
def process_image_form(
    client_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Screenshot of portal â†’ GPT-4o reads it visually â†’ returns label:value pairs."""
    file_bytes = file.file.read()
    content_type = file.content_type or "image/jpeg"
    company_context = build_company_context(db)
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

    response = openai_client.chat.completions.create(
        model=VISION_MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:{content_type};base64,{b64}",
                    "detail": "high"
                }},
                {"type": "text", "text": (
                    f"{SCREENSHOT_FILL_PROMPT}\n\n"
                    f"COMPANY DATA:\n{json.dumps(company_context, indent=2)}"
                )}
            ]
        }]
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        pairs = json.loads(raw)
        filled_data = {p["label"]: p["value"] for p in pairs if p.get("label") and p.get("value")}
    except Exception:
        filled_data = {}

    doc_checklist = get_doc_checklist(" ".join(filled_data.keys()), db)

    form = FilledForm(
        client_name=client_name,
        form_type="image",
        original_filename=file.filename,
        filled_data=filled_data,
        unknown_fields=[],
        doc_checklist=doc_checklist
    )
    db.add(form); db.commit(); db.refresh(form)

    return {
        "form_id": form.id,
        "client_name": client_name,
        "total_fields": len(filled_data),
        "auto_filled": len(filled_data),
        "unknown_count": 0,
        "filled_data": filled_data,
        "unknown_fields": [],
        "doc_checklist": doc_checklist,
        "ai_used": "GPT-4o vision (GitHub Models)"
    }


@router.post("/save-learned-answer")
def save_learned_answer(
    field_label: str = Form(...),
    answer: str = Form(...),
    form_id: Optional[int] = Form(None),
    save_to_db: bool = Form(True), # Kept for API compatibility
    db: Session = Depends(get_db)
):
    from models.database import CompanyField
    from utils import normalize_field_key
    
    key = normalize_field_key(field_label)
    existing = db.query(CompanyField).filter(CompanyField.field_key == key).first()
    
    if existing:
        existing.value = answer
        existing.confidence = "learned"
        existing.usage_count = (existing.usage_count or 0) + 1
        existing.last_updated = datetime.utcnow()
    else:
        db.add(CompanyField(
            category="Learned", 
            field_key=key,
            field_label=field_label, 
            value=answer,
            confidence="learned",
            usage_count=1,
            aliases=[]
        ))
    db.commit()

    if form_id:
        form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
        if form:
            merged = dict(form.filled_data or {})
            merged[field_label] = {"label": "Manual Answer", "value": answer}
            form.filled_data = merged
            # Remove from unknown fields if it exists (check cell or label)
            form.unknown_fields = [f for f in (form.unknown_fields or []) if (f.get("cell") if isinstance(f, dict) else f) != field_label]
            db.commit()

    return {"saved": True, "field": field_label}


from pydantic import BaseModel
from typing import List

class FillProjectTableRequest(BaseModel):
    sheet_name: str
    table_type: str
    selected_ids: List[int]

@router.post("/forms/{form_id}/fill-project-table")
def fill_project_table(
    form_id: int,
    req: FillProjectTableRequest,
    db: Session = Depends(get_db)
):
    form = db.query(FilledForm).filter(FilledForm.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    pending_tables = form.pending_project_tables or []
    target_table = None
    target_idx = -1
    for i, pt in enumerate(pending_tables):
        if pt.get("sheet_name") == req.sheet_name:
            target_table = pt
            target_idx = i
            break
            
    if not target_table:
        raise HTTPException(status_code=404, detail=f"No pending project table found for sheet '{req.sheet_name}'")

    table_fills = {}

    # FIX (P0/P1): branch for the new deterministic "vertical block" layout (each
    # record's fields are stacked across rows in a single answer column) alongside
    # the pre-existing "horizontal" layout (one column per field, one row per
    # record). See detect_vertical_repeating_blocks() in routers/forms.py.
    if target_table.get("layout") == "vertical":
        answer_col = target_table["answer_column"]
        block_start_rows = target_table["block_start_rows"]
        field_row_offsets = target_table["field_row_offsets"]

        rows_to_fill = min(len(req.selected_ids), len(block_start_rows))
        ids_to_fill = req.selected_ids[:rows_to_fill]

        if req.table_type == "project_reference":
            from models.database import ProjectReference
            refs = db.query(ProjectReference).filter(ProjectReference.id.in_(ids_to_fill)).all()
            ref_dict = {r.id: r for r in refs}
            ordered_refs = [ref_dict[i] for i in ids_to_fill if i in ref_dict]

            field_value_map = {
                "client_name": lambda r: r.client_name,
                "project_name": lambda r: r.project_name,
                "location": lambda r: r.location,
                "area_sqft": lambda r: r.area_sqft,
                "amount": lambda r: r.project_value,
                "start_date": lambda r: r.start_date,
                "completion_date": lambda r: r.end_date,
                "contact_name": lambda r: r.client_rep_name,
                "contact_designation": lambda r: r.client_rep_designation,
                "contact_phone": lambda r: r.client_rep_phone,
                "contact_email": lambda r: r.client_rep_email,
            }
            for ref, block_start in zip(ordered_refs, block_start_rows):
                for field_key, offset in field_row_offsets.items():
                    getter = field_value_map.get(field_key)
                    if getter:
                        val = getter(ref)
                        if val:
                            row_num = block_start + offset
                            table_fills[f"{req.sheet_name}!{answer_col}{row_num}"] = val

        elif req.table_type == "project_details":
            from models.database import ProjectDataRecord
            records = db.query(ProjectDataRecord).filter(ProjectDataRecord.id.in_(ids_to_fill)).all()
            rec_dict = {r.id: r for r in records}
            ordered_records = [rec_dict[i] for i in ids_to_fill if i in rec_dict]

            def _find_value(rec_data, m_key):
                m_key = m_key.lower()
                if m_key == "area_sqft": look_for = ["area", "sqft", "size"]
                elif m_key == "amount": look_for = ["value", "billing", "contract", "amount", "cost"]
                elif m_key == "location": look_for = ["location", "branch"]
                elif m_key == "start_date": look_for = ["start"]
                elif m_key == "completion_date": look_for = ["end", "completion"]
                elif m_key == "duration": look_for = ["duration"]
                elif m_key == "scope_of_work": look_for = ["scope"]
                else: look_for = [m_key]

                for dk, dv in rec_data.items():
                    dk_lower = dk.lower()
                    if any(lf in dk_lower for lf in look_for) and dv and isinstance(dv, str) and dv.strip():
                        return dv.strip()
                return None

            for rec, block_start in zip(ordered_records, block_start_rows):
                for field_key, offset in field_row_offsets.items():
                    val = _find_value(rec.data or {}, field_key)
                    if val:
                        row_num = block_start + offset
                        table_fills[f"{req.sheet_name}!{answer_col}{row_num}"] = val

        rows_available = len(block_start_rows)

    else:
        # --- Original "horizontal" layout: one column per field, one row per record ---
        start_row = target_table.get("start_row", 1)
        mapping = target_table.get("mapping", {})

        # Need to re-read the sheet's cell map to get fresh available_rows
        # (since the original pass didn't fill anything here)
        orig_path = os.path.join(UPLOAD_DIR, form.original_filename)
        if not os.path.exists(orig_path):
            raise HTTPException(404, "Original file not found")

        with open(orig_path, "rb") as f:
            file_bytes = f.read()

        sheet_maps, _, _, _ = excel_to_all_sheet_maps(file_bytes)
        cmap = sheet_maps.get(req.sheet_name, "")

        available_rows = []
        first_col = next(iter(mapping.values())) if mapping else None
        if first_col:
            r = start_row
            while f"[{first_col}{r}]=EMPTY" in cmap:
                available_rows.append(r)
                r += 1

        if not available_rows:
            available_rows = list(range(start_row, start_row + len(req.selected_ids)))

        # Cap selection to available rows
        rows_to_fill = min(len(req.selected_ids), len(available_rows))
        ids_to_fill = req.selected_ids[:rows_to_fill]

        if req.table_type == "project_reference":
            from models.database import ProjectReference
            refs = db.query(ProjectReference).filter(ProjectReference.id.in_(ids_to_fill)).all()
            # Preserve selection order
            ref_dict = {r.id: r for r in refs}
            ordered_refs = [ref_dict[i] for i in ids_to_fill if i in ref_dict]

            for ref, row_num in zip(ordered_refs, available_rows):
                if "project_name" in mapping and ref.project_name: table_fills[f"{req.sheet_name}!{mapping['project_name']}{row_num}"] = ref.project_name
                if "client_name" in mapping and ref.client_name: table_fills[f"{req.sheet_name}!{mapping['client_name']}{row_num}"] = ref.client_name
                if "location" in mapping and ref.location: table_fills[f"{req.sheet_name}!{mapping['location']}{row_num}"] = ref.location
                if "area_sqft" in mapping and ref.area_sqft: table_fills[f"{req.sheet_name}!{mapping['area_sqft']}{row_num}"] = ref.area_sqft
                if "amount" in mapping and ref.project_value: table_fills[f"{req.sheet_name}!{mapping['amount']}{row_num}"] = ref.project_value
                if "start_date" in mapping and ref.start_date: table_fills[f"{req.sheet_name}!{mapping['start_date']}{row_num}"] = ref.start_date
                if "completion_date" in mapping and ref.end_date: table_fills[f"{req.sheet_name}!{mapping['completion_date']}{row_num}"] = ref.end_date
                if "contact_name" in mapping and ref.client_rep_name: table_fills[f"{req.sheet_name}!{mapping['contact_name']}{row_num}"] = ref.client_rep_name
                if "contact_designation" in mapping and ref.client_rep_designation: table_fills[f"{req.sheet_name}!{mapping['contact_designation']}{row_num}"] = ref.client_rep_designation
                if "contact_phone" in mapping and ref.client_rep_phone: table_fills[f"{req.sheet_name}!{mapping['contact_phone']}{row_num}"] = ref.client_rep_phone
                if "contact_email" in mapping and ref.client_rep_email: table_fills[f"{req.sheet_name}!{mapping['contact_email']}{row_num}"] = ref.client_rep_email

        elif req.table_type == "project_details":
            from models.database import ProjectDataRecord
            records = db.query(ProjectDataRecord).filter(ProjectDataRecord.id.in_(ids_to_fill)).all()
            rec_dict = {r.id: r for r in records}
            ordered_records = [rec_dict[i] for i in ids_to_fill if i in rec_dict]

            # Helper to find value based on mapping key
            def _find_value(rec_data, m_key):
                m_key = m_key.lower()
                if m_key == "area_sqft": look_for = ["area", "sqft", "size"]
                elif m_key == "amount": look_for = ["value", "billing", "contract", "amount"]
                elif m_key == "location": look_for = ["location", "branch"]
                elif m_key in ["start_date", "completion_date"]: look_for = ["start"] if "start" in m_key else ["end", "completion"]
                else: look_for = [m_key]

                for dk, dv in rec_data.items():
                    dk_lower = dk.lower()
                    if any(lf in dk_lower for lf in look_for) and dv and isinstance(dv, str) and dv.strip():
                        return dv.strip()
                return None

            for rec, row_num in zip(ordered_records, available_rows):
                for m_key, m_col in mapping.items():
                    val = _find_value(rec.data or {}, m_key)
                    if val:
                        table_fills[f"{req.sheet_name}!{m_col}{row_num}"] = val

        rows_available = len(available_rows)

    # Merge into filled_data
    filled_data = dict(form.filled_data or {})
    filled_data.update(table_fills)
    form.filled_data = filled_data
    
    # Remove from pending_tables
    pending_tables.pop(target_idx)
    # Re-assign to trigger SQLAlchemy JSON mutation detection
    form.pending_project_tables = list(pending_tables)
    
    db.commit()
    
    return {
        "filled_cells": len(table_fills),
        "remaining_pending_tables": pending_tables,
        "rows_filled": min(len(req.selected_ids), rows_available),
        "rows_available": rows_available
    }


