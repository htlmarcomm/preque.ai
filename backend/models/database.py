from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./preque.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CompanyField(Base):
    __tablename__ = "company_fields"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), index=True)  # e.g. "basic_info", "financial", "manpower"
    field_key = Column(String(200), unique=True, index=True)
    field_label = Column(String(300))
    value = Column(Text)
    document_link = Column(Text)  # SharePoint link or local path
    notes = Column(Text)
    aliases = Column(JSON, default=list)  # alternate labels/synonyms
    confidence = Column(String(20), default="verified")  # verified, learned, unverified
    last_verified = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)


# DEPRECATED — merged into ProjectFile (source_module="document"). Kept for rollback
# safety only; do not write to this table.
class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300))
    doc_type = Column(String(100))  # e.g. "GST Certificate", "PAN Card"
    filename = Column(String(300))
    sharepoint_link = Column(Text)
    tags = Column(JSON)  # list of tags for matching
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class FilledForm(Base):
    __tablename__ = "filled_forms"
    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(200))
    form_type = Column(String(50))  # "excel" or "image"
    original_filename = Column(String(300))
    filled_data = Column(JSON)   # {field_label: value}
    unknown_fields = Column(JSON)  # fields that needed human input
    doc_checklist = Column(JSON)  # list of docs to attach
    fill_sources = Column(JSON, default=dict)  # "Sheet!Cell" -> "alias_match" | "gpt4o_vision" | "human"
    pending_project_tables = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), index=True)  # "project_file" or "document"
    source_id = Column(Integer, index=True)
    sheet_or_page = Column(String(100))
    chunk_index = Column(Integer)
    text = Column(Text)
    parent_text = Column(Text, nullable=True)
    embedding = Column(JSON, nullable=True)  # list of floats
    created_at = Column(DateTime, default=datetime.utcnow)

class SubContractor(Base):
    __tablename__ = "subcontractors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    address = Column(Text, nullable=True)
    work_description = Column(Text, nullable=True)
    contact_name = Column(String(200), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(200), nullable=True)
    years_active = Column(String(50), nullable=True)
    source_document = Column(String(300), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class FinancialRecord(Base):
    __tablename__ = "financial_records"
    id = Column(Integer, primary_key=True, index=True)
    fiscal_year = Column(String(20), index=True)       # e.g. "FY25-26", "2019"
    metric_key = Column(String(100), index=True)        # e.g. "total_assets", "ehs_policy_defined"
    metric_label = Column(String(300))                  # e.g. "Total Assets", "Is EH&S Policy Defined?"
    value = Column(Text)                                 # numeric or qualitative, always stored as text
    unit = Column(String(50), nullable=True)             # "₹ Cr", "%", or null for qualitative
    category = Column(String(100))                       # "Balance Sheet" | "P&L" | "Turnover" | "EHS & Compliance" | "Certifications"
    source = Column(String(200), nullable=True)           # e.g. "Reference.XLSX", "FY25-26 statement provided by user"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProjectReference(Base):
    __tablename__ = "project_references"
    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(300), index=True)
    client_name = Column(String(300), index=True)
    region = Column(String(100), index=True)              # "Mumbai" | "Pune" | "Delhi" | "Bangalore-Chennai-Hyderabad"
    location = Column(String(200))
    area_sqft = Column(String(50))
    consultant = Column(String(300))
    pmc = Column(String(200))
    project_sector = Column(String(100))
    project_type = Column(Text)
    project_value = Column(String(50))
    status = Column(String(50))                            # "Completed" | "Ongoing"
    start_date = Column(String(50))
    end_date = Column(String(50))
    client_rep_name = Column(String(200), nullable=True)
    client_rep_designation = Column(String(200), nullable=True)
    client_rep_email = Column(String(200), nullable=True)
    client_rep_phone = Column(String(50), nullable=True)
    certifications = Column(String(200), nullable=True)    # e.g. "LEED", "SEZ", "LEED & SEZ"
    source_file = Column(String(200), default="Reference.XLSX")
    created_at = Column(DateTime, default=datetime.utcnow)

class ProjectFile(Base):
    __tablename__ = "project_files"
    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(300), index=True)
    client          = Column(String(200), index=True)
    category        = Column(String(100))
    doc_type        = Column(String(100), nullable=True)
    source_module   = Column(String(50), default="project_file")
    filename        = Column(String(300))
    sharepoint_link = Column(Text)
    tags            = Column(JSON)
    sheet_names     = Column(JSON)
    row_count       = Column(Integer)
    uploaded_at     = Column(DateTime, default=datetime.utcnow)
    notes           = Column(Text)

class WorkspacePackage(Base):
    __tablename__ = "workspace_packages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), index=True)
    client = Column(String(200), index=True)
    target_sharepoint_url = Column(Text)
    share_link = Column(Text)
    status = Column(String(50), default="Draft")  # Draft, Exported
    data = Column(JSON)  # Stores { folders: [], items: [] }
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProjectDataRecord(Base):
    __tablename__ = "project_data_records"
    id = Column(Integer, primary_key=True, index=True)
    source_file = Column(String(300), index=True)       # original uploaded filename
    source_sheet = Column(String(200), index=True)       # sheet name within that file
    row_number = Column(Integer)                          # row index within that sheet (1-based, for tracing back)
    primary_label = Column(String(500), nullable=True)    # best-guess human-readable label for this row (see task 4)
    data = Column(JSON)                                    # {normalized_column_key: raw_cell_value} — the FULL row, whatever columns existed
    search_text = Column(Text)                             # lowercase concatenation of every value in this row, for fast text search
    row_hash = Column(String(64), unique=True, index=True) # sha256 of source_file+source_sheet+row_number+data, prevents duplicate re-import
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class ProjectDataColumn(Base):
    __tablename__ = "project_data_columns"
    id = Column(Integer, primary_key=True, index=True)
    column_key = Column(String(200), unique=True, index=True)   # normalized snake_case key
    display_label = Column(String(300))                          # original header text as first seen
    first_seen_file = Column(String(300))
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    times_seen = Column(Integer, default=1)                       # incremented every time this column appears in a new import

class ProjectDataSheet(Base):
    __tablename__ = "project_data_sheets"
    id = Column(Integer, primary_key=True, index=True)
    source_file = Column(String(300), index=True)
    source_sheet = Column(String(200), index=True)  # exact original sheet name, preserved as-is
    column_order = Column(JSON)   # ordered list of {"key": normalized_key, "display_label": original_header_text}
    row_count = Column(Integer, default=0)
    parser_used = Column(String(50))  # "tabular" | "vertical_block" | "bulleted_cell"
    first_uploaded_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
