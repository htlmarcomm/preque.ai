# PreQue AI — Pre-Qualification Form Automation
**HTL Aircon Internal Tool · v1.1 (bug-fix release)**

> **Upgrading an existing install?** Read [`UPGRADE_NOTES.md`](./UPGRADE_NOTES.md)
> first — it explains exactly what changed, what was deliberately left out, and how
> to apply this on top of your existing `preque.db` / `uploads/` without losing
> anything.

---

## What it does

1. **Upload** an Excel pre-qual form or a screenshot of a client's online portal
2. **AI fills** all fields automatically from HTL's company database
3. **You fill** any unknown fields (saved for future use)
4. **Download** the filled Excel or copy-paste answers for portal forms
5. **Document checklist** tells you exactly which files to attach

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React + Vite + TailwindCSS |
| Backend | FastAPI + SQLite (SQLAlchemy) |
| AI | GPT-4o via GitHub Models (vision) + deterministic fuzzy/geometry matching |
| Files | openpyxl (Excel), Pillow (images) |

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- An Anthropic/GitHub Models API key for GPT-4o access

---

### 1. Backend

```bash
cd backend

# Copy and fill in your API key
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=ghp_... (GitHub Models token)

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# OR: venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# If upgrading an existing install with data already seeded, run the additive patch:
python patch_v2_fixes.py

# Start the API server
uvicorn main:app --reload --port 8000
```

The API runs at http://localhost:8000
Swagger docs at http://localhost:8000/docs

---

### 2. Frontend

```bash
cd frontend

# Copy env file
cp .env.example .env

# Install and start
npm install
npm run dev
```

App runs at http://localhost:5173

**Note:** `frontend/src/App.jsx` imports `./assets/htl-logo.png`. If this file isn't
already present in `frontend/src/assets/`, either copy your existing logo file in, or
temporarily swap the import for any placeholder image.

---

### 3. First-time setup in the app (fresh installs only — skip if upgrading)

1. Place `company_seed.json` in `backend/seed_data/` (gitignored — it holds real
   company-identifying data like GSTIN/PAN/contact numbers, so it's distributed
   out-of-band, not committed; ask an admin for a copy).
2. Go to **Company Data** → click "Load HTL Data" — seeds all HTL Aircon fields from `backend/seed_data/company_seed.json`
3. Go to **Documents** → click "Load Document List" — seeds the default document registry
4. Add SharePoint links to each document so they appear in output checklists
5. Done! Go to **Fill Form** and upload your first pre-qual form

---

## Folder Structure

```
preque-app/
├── UPGRADE_NOTES.md          ← read this before upgrading an existing install
├── backend/
│   ├── main.py                    ← FastAPI app entry point
│   ├── requirements.txt
│   ├── .env                       ← API key (do NOT commit)
│   ├── patch_v2_fixes.py          ← additive-only patch for existing installs
│   ├── preque.db                  ← SQLite database (yours — not in this zip)
│   ├── models/
│   │   └── database.py            ← SQLAlchemy models (unchanged schema)
│   ├── routers/
│   │   ├── agent.py               ← AI form processing (fill-project-table: fixed)
│   │   ├── forms.py               ← core fill pipeline (bug fixes live here)
│   │   ├── documents.py           ← Document management (MSME doc type added)
│   │   ├── company_data.py        ← Company DB CRUD + seed data
│   │   ├── company_search.py, project_files.py, project_data.py,
│   │   │   project_picker.py, subcontractors.py, workspace.py,
│   │   │   sharepoint.py, google.py, search.py  ← all unmodified
│   ├── services/
│   │   ├── field_matcher.py       ← Pass 1 fuzzy match (candidate-walk fix)
│   │   ├── vector_store.py, doc_extractor.py  ← unmodified
│   └── uploads/
│       ├── forms/, documents/, project_files/, outputs/  ← yours — not in this zip
│
└── frontend/
    ├── src/
    │   ├── App.jsx                ← Routing + sidebar (unmodified)
    │   ├── lib/api.js              ← API client (unmodified)
    │   ├── contexts/FillFormContext.jsx
    │   └── pages/
    │       ├── FillForm.jsx        ← Main workflow (unmodified — already
    │       │                          supports the picker flow the fixes feed into)
    │       ├── CompanyDB.jsx, Documents.jsx, ProjectFiles.jsx, Workspace.jsx,
    │       │   SubContractors.jsx, ProjectHistory.jsx, DocumentSearch.jsx,
    │       │   FormHistory.jsx     ← all unmodified
```

---

## How to update company data

**Option A — In the app:** Go to Company Data → click any field → edit inline

**Option B — Import Excel:** Go to Company Data → "Import Excel" → upload a spreadsheet with columns: Field Label | Value | Document Link

**Option C — API:** POST to `/api/company/fields` with JSON body

---

## Deploying (optional)

### Backend on Render
1. Create a Web Service → point to `/backend`
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add env var: `OPENAI_API_KEY`
5. Use a persistent disk for `/uploads` and the SQLite DB

### Frontend on Vercel / Netlify
1. Point to `/frontend`
2. Build: `npm run build`
3. Set `VITE_API_URL` to your Render backend URL

---

## Additional system dependencies (one-time install)

```bash
# Ubuntu/Debian (for Excel → image rendering)
sudo apt-get install -y libreoffice poppler-utils

# Mac
brew install libreoffice poppler

# Windows
# Install LibreOffice from libreoffice.org
# Install poppler from: https://github.com/oschwartz10612/poppler-windows
```
