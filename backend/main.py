from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from routers import company_data, company_search, forms, documents, agent, project_files, workspace, google, search, subcontractors, project_data, project_picker
from models.database import engine, Base
from auth import require_api_key

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PreQue Automation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every /api/* route requires the shared X-API-Key header (see auth.py) --
# previously nothing in this app required any credential at all.
api_auth = [Depends(require_api_key)]

app.include_router(company_data.router, prefix="/api/company", tags=["Company Data"], dependencies=api_auth)
app.include_router(company_search.router, prefix="/api/company", tags=["Company Search"], dependencies=api_auth)
app.include_router(forms.router, prefix="/api/forms", tags=["Forms"], dependencies=api_auth)
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"], dependencies=api_auth)
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"], dependencies=api_auth)
app.include_router(project_files.router, prefix="/api/project-files", tags=["Project Files"], dependencies=api_auth)
app.include_router(workspace.router, prefix="/api/workspace", tags=["Workspace"], dependencies=api_auth)
app.include_router(google.router, prefix="/api/google", tags=["Google Integration"], dependencies=api_auth)
app.include_router(search.router, prefix="/api/search", tags=["Search"], dependencies=api_auth)
app.include_router(subcontractors.router, prefix="/api/subcontractors", tags=["Subcontractors"], dependencies=api_auth)
app.include_router(project_data.router, prefix="/api/project-data", tags=["Project Data"], dependencies=api_auth)
app.include_router(project_picker.router, prefix="/api/project-picker", tags=["Project Picker"], dependencies=api_auth)

@app.get("/")
def root():
    return {"status": "PreQue Automation API running"}
