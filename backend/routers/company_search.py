from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List
from models.database import get_db, CompanyField, FinancialRecord, ProjectReference

router = APIRouter()

@router.get("/search")
def search_company_data(
    q: Optional[str] = None,
    type: Optional[str] = None,  # "field" | "financial" | "project"
    category: Optional[str] = None,
    year: Optional[str] = None,
    db: Session = Depends(get_db)
):
    results = {"fields": [], "financials": [], "projects": []}
    
    # 1. Search CompanyFields
    if not type or type == "field":
        query = db.query(CompanyField)
        if category:
            query = query.filter(CompanyField.category == category)
        if q:
            search_str = f"%{q}%"
            query = query.filter(
                or_(
                    CompanyField.field_label.ilike(search_str),
                    CompanyField.value.ilike(search_str),
                    CompanyField.aliases.ilike(search_str)
                )
            )
        fields = query.all()
        for f in fields:
            f_dict = {col.name: getattr(f, col.name) for col in f.__table__.columns}
            f_dict["_source_type"] = "field"
            results["fields"].append(f_dict)
            
    # 2. Search FinancialRecords
    if not type or type == "financial":
        query = db.query(FinancialRecord)
        if category:
            query = query.filter(FinancialRecord.category == category)
        if year:
            query = query.filter(FinancialRecord.fiscal_year == year)
        if q:
            search_str = f"%{q}%"
            query = query.filter(
                or_(
                    FinancialRecord.metric_label.ilike(search_str),
                    FinancialRecord.value.ilike(search_str)
                )
            )
        financials = query.all()
        for f in financials:
            f_dict = {col.name: getattr(f, col.name) for col in f.__table__.columns}
            f_dict["_source_type"] = "financial"
            results["financials"].append(f_dict)
            
    # 3. Search ProjectReferences
    if not type or type == "project":
        query = db.query(ProjectReference)
        if q:
            search_str = f"%{q}%"
            query = query.filter(
                or_(
                    ProjectReference.project_name.ilike(search_str),
                    ProjectReference.client_name.ilike(search_str),
                    ProjectReference.location.ilike(search_str),
                    ProjectReference.consultant.ilike(search_str),
                    ProjectReference.pmc.ilike(search_str)
                )
            )
        projects = query.all()
        for p in projects:
            p_dict = {col.name: getattr(p, col.name) for col in p.__table__.columns}
            p_dict["_source_type"] = "project"
            results["projects"].append(p_dict)
            
    # Add counts
    results["counts"] = {
        "fields": len(results["fields"]),
        "financials": len(results["financials"]),
        "projects": len(results["projects"])
    }
    
    return results

@router.get("/financial-records")
def get_financial_records(
    category: Optional[str] = None,
    year: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(FinancialRecord)
    if category:
        query = query.filter(FinancialRecord.category == category)
    if year:
        query = query.filter(FinancialRecord.fiscal_year == year)
    return query.all()

@router.get("/project-references")
def get_project_references(
    region: Optional[str] = None,
    status: Optional[str] = None,
    client: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProjectReference)
    if region:
        query = query.filter(ProjectReference.region == region)
    if status:
        query = query.filter(ProjectReference.status == status)
    if client:
        query = query.filter(ProjectReference.client_name == client)
    return query.all()
