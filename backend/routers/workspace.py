from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from models.database import get_db, Base, engine, WorkspacePackage
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict, Any
from routers.sharepoint import export_workspace_to_sharepoint

router = APIRouter()

class PackageCreate(BaseModel):
    name: str
    client: str
    target_sharepoint_url: str
    data: Dict[str, Any]

class PackageImport(BaseModel):
    name: str
    client: str
    target_sharepoint_url: str

class PackageUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    target_sharepoint_url: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

@router.get("/")
def get_packages(db: Session = Depends(get_db)):
    return db.query(WorkspacePackage).order_by(WorkspacePackage.updated_at.desc()).all()

@router.post("/")
def create_package(pkg: PackageCreate, db: Session = Depends(get_db)):
    db_pkg = WorkspacePackage(
        name=pkg.name,
        client=pkg.client,
        target_sharepoint_url=pkg.target_sharepoint_url,
        data=pkg.data,
        status="Draft"
    )
    db.add(db_pkg)
    db.commit()
    db.refresh(db_pkg)
    return db_pkg

@router.post("/import")
def import_package(pkg: PackageImport, db: Session = Depends(get_db)):
    from routers.sharepoint import import_workspace_from_sharepoint
    try:
        data = import_workspace_from_sharepoint(pkg.target_sharepoint_url, db)
        db_pkg = WorkspacePackage(
            name=pkg.name,
            client=pkg.client,
            target_sharepoint_url=pkg.target_sharepoint_url,
            data=data,
            status="Exported"  # Keep it as exported since it's a historic package
        )
        db.add(db_pkg)
        db.commit()
        db.refresh(db_pkg)
        return db_pkg
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@router.get("/{pkg_id}")
def get_package(pkg_id: int, db: Session = Depends(get_db)):
    pkg = db.query(WorkspacePackage).filter(WorkspacePackage.id == pkg_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg

@router.put("/{pkg_id}")
def update_package(pkg_id: int, pkg_update: PackageUpdate, db: Session = Depends(get_db)):
    pkg = db.query(WorkspacePackage).filter(WorkspacePackage.id == pkg_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    
    if pkg_update.name is not None:
        pkg.name = pkg_update.name
    if pkg_update.client is not None:
        pkg.client = pkg_update.client
    if pkg_update.target_sharepoint_url is not None:
        pkg.target_sharepoint_url = pkg_update.target_sharepoint_url
    if pkg_update.data is not None:
        pkg.data = pkg_update.data
    if pkg_update.status is not None:
        pkg.status = pkg_update.status
        
    db.commit()
    db.refresh(pkg)
    return pkg

@router.post("/{pkg_id}/export")
def export_package(pkg_id: int, db: Session = Depends(get_db)):
    pkg = db.query(WorkspacePackage).filter(WorkspacePackage.id == pkg_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    
    if not pkg.target_sharepoint_url:
        raise HTTPException(status_code=400, detail="No target SharePoint URL provided")
        
    try:
        share_link = export_workspace_to_sharepoint(pkg.target_sharepoint_url, pkg.data, pkg.name, db)
        pkg.status = "Exported"
        pkg.share_link = share_link
        db.commit()
        db.refresh(pkg)
        return pkg
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
