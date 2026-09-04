from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from routers import company_data, company_search, forms, documents, agent, project_files, workspace, google, search, subcontractors, project_data, project_picker
from models.database import engine, Base
from auth import require_api_key, client_ip

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PreQue Automation API", version="1.0.0")

# SECURITY FIX: no rate limiting existed anywhere -- someone holding the
# (frontend-embedded, effectively public) API key could hammer any endpoint
# without limit. This throttles per source IP regardless of whether the key
# they're using is valid, which the auth.py lockout alone doesn't cover
# (that one only throttles INVALID keys). key_func reuses auth.py's
# client_ip so both defenses agree on who "one client" actually is behind
# Railway/Caddy's proxy, instead of slowapi's default (which would see only
# the proxy's own IP and rate-limit everyone as a single client).
limiter = Limiter(key_func=client_ip, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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

# Always available, unauthenticated (registered directly on `app`, not
# through one of the api_auth-gated routers above) -- this is what the
# Docker HEALTHCHECK and any platform health-checker actually probes, and
# it works whether or not a built frontend is bundled.
@app.get("/api/health")
def health():
    return {"status": "PreQue Automation API running"}


# Serve the built frontend (frontend/dist, copied to backend/static in the
# Docker image) from the same origin as the API in production. This is
# entirely optional -- in local dev, backend/static doesn't exist, so none
# of this registers and the Vite dev server on :5173 is used instead, as
# before. Registered LAST so it can never shadow an /api/* route: FastAPI
# matches routes in registration order, and every router above was already
# added by this point.
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(FRONTEND_DIST):
    # FIX (found by actually testing this, not just reading it): a plain
    # `@app.get("/")` health-check endpoint used to live where this block
    # is now. Since it was registered before this catch-all, it permanently
    # shadowed "/" -- visiting the deployed app's root URL showed raw JSON
    # instead of the React app. Moved that check to /api/health above so
    # "/" is free for the SPA to actually own here.
    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        index_path = os.path.join(FRONTEND_DIST, "index.html")
        if not full_path:
            return FileResponse(index_path)
        # Path traversal guard: resolve and confirm the requested file is
        # still inside FRONTEND_DIST before ever serving it -- full_path
        # comes straight from the URL and a request like
        # "/../../backend/.env" would otherwise walk right out of the
        # intended static directory.
        candidate = os.path.normpath(os.path.join(FRONTEND_DIST, full_path))
        if os.path.commonpath([candidate, FRONTEND_DIST]) == FRONTEND_DIST and os.path.isfile(candidate):
            return FileResponse(candidate)
        # Any other unmatched path (a client-side route like /history,
        # /company, etc.) falls back to index.html so React Router can
        # handle it -- this is the standard SPA-hosting pattern.
        return FileResponse(index_path)
else:
    # No frontend bundled (e.g. plain local dev, `uvicorn main:app` without
    # having built into backend/static) -- keep "/" answering with a plain
    # status so hitting the bare API root isn't just a 404.
    @app.get("/")
    def root():
        return {"status": "PreQue Automation API running"}
