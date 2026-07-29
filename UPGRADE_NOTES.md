# PreQue — v1.1 Upgrade Notes (bug-fix release)

## Read this before copying anything over your existing install

This zip is **code only**. It does **not** contain, and will **never overwrite**:
- `backend/preque.db` (your live database — all Company Data, Financials, Project
  References, SubContractors, Project History, Workspace packages, Document Chunks,
  everything)
- `backend/uploads/` (your File Cabinet's actual files, form uploads, outputs)
- `backend/.env` / `backend/google-credentials.json` (your API keys and Google/OneDrive
  credentials)
- `frontend/src/assets/htl-logo.png` (a binary image file that wasn't part of the
  text content I had available to work from)

**How to apply this update safely:**

1. **Back up first regardless.** Copy your whole `preque-app/` folder somewhere safe
   (or at minimum `backend/preque.db` and `backend/uploads/`) before touching anything.
2. Copy this zip's `backend/` and `frontend/` folders **on top of** your existing
   `backend/` and `frontend/` folders, but do **not** delete your existing folders
   first — just overwrite matching files. This preserves:
   - `backend/preque.db` (not present in this zip, so it's untouched)
   - `backend/uploads/*` (not present in this zip, so it's untouched)
   - `backend/.env`, `backend/google-credentials.json` (not present in this zip)
   - `frontend/src/assets/htl-logo.png` (not present in this zip — copy your existing
     one back in if your file manager happened to remove it; it's the only file the
     app needs that isn't included here)
3. Run the additive-only patch script once, from `backend/`, with your existing
   `preque.db` in place:
   ```bash
   cd backend
   python patch_v2_fixes.py
   ```
   This only **adds** a new "MSME Registration No." field and **appends** two new
   aliases to your existing "Registered Address" field if they aren't already
   there — it never deletes or overwrites anything else. Safe to run more than once.
4. Reinstall dependencies (a couple of new ones were added — `msal`, `requests`,
   `pandas` — needed by `routers/sharepoint.py` and CSV import, which were already
   imported in your original code but missing from `requirements.txt`):
   ```bash
   pip install -r requirements.txt --upgrade
   ```
5. Start the backend and frontend exactly as before — nothing about how you run
   the app changed:
   ```bash
   # backend/
   uvicorn main:app --reload --port 8000
   # frontend/
   npm install && npm run dev
   ```

Your Company Data, File Cabinet, Project History, Project References, SubContractors,
Workspace packages, and OneDrive/SharePoint connection logic (`routers/sharepoint.py`,
`routers/workspace.py`) are **unmodified** — same database models, same table names,
same columns, same API routes. Nothing about how existing data is stored or read has
changed.

---

## What was deliberately left OUT of this zip, and why

- **Destructive one-off scripts** (`fix_db.py`, `fix_db2.py`, `reset_project_data.py`,
  `dedupe.py`, and the various `migrate_*.py` / `seed_*.py` / `import_*.py` /
  `check*.py` / `test_*.py` scripts) were **not** included. Several of these
  literally call `Base.metadata.drop_all()` or bulk-delete rows — they were one-time
  tools you already ran against your live data historically. Given you explicitly
  asked for all existing data to be preserved, re-including them (where a future
  accidental run could wipe tables) was the wrong tradeoff. If you need any specific
  one of them again, tell me and I'll hand you just that one.
- **`package-lock.json`** — not included; run `npm install` fresh instead of relying
  on the lockfile (standard practice, and avoids shipping 900+ lines of hash pins).
- **`frontend/src/assets/htl-logo.png`, `alembic/versions/*`, misc SVG assets** —
  omitted to keep this response's scope manageable; none of them affect app
  behavior, and your existing copies are untouched by this zip regardless.

---

## What was actually fixed (see prior message for the full write-up)

**P0 — Silent label-corruption bug (`routers/forms.py`)**
`build_sheet_cell_map` now excludes merged-cell continuation cells from ever being
marked as a fillable "EMPTY" cell in the first place (`_merge_continuation_cells`).
`write_filled_excel_multi` also got a defense-in-depth check: it will now refuse to
write into a merged cell's anchor if that anchor already holds real label text,
instead of silently overwriting it. Proven bug (I actually corrupted a test copy of
your Logos Group form and showed the label getting destroyed) — now closed at two
layers.

**P0 — Same value stamped into every "Customer Reference" row (`routers/forms.py`,
`routers/agent.py`)**
New `detect_vertical_repeating_blocks()` deterministically finds repeating
vertical-block tables (like "Client Referance -1/-2/-3...") purely from merged-cell
geometry — **no AI call needed**. Every cell belonging to a detected block is now
reserved for the project-reference/project-details picker UI you already have, and
excluded from Pass 1 and GPT-4o vision entirely, so one company fact can no longer
get silently repeated across slots meant for different external clients.

**P1 — Repeating-table architecture couldn't represent vertical-block forms**
`agent.py`'s `fill-project-table` endpoint now branches on a new `"layout": "vertical"`
flag and fills each block by row-offset within a single answer column, alongside the
original column-per-field horizontal layout it already supported for grid-style forms.

**P1 — Financial year format mismatch**
`build_company_context()` now populates every common spelling of each fiscal year
("FY23-24", "2023-2024", "23-24", ...) into the context sent to GPT-4o vision, purely
additive — nothing in the database changed.

**P1 — Document checklist gaps**
Added `"MSME Registration Certificate"` to `DOC_TYPES` (`routers/documents.py`) and a
matching trigger word. Removed the hardcoded client-specific `"Taj Hotel LOA"` /
`"UBS LOA"` / `"German Consulate LOA"` entries from the generic `"completion"`
trigger (they now map to the reusable generic doc types instead), and added a working
`"bank statement"` trigger so that `DOC_TYPES`'s existing entry is reachable at all.

**P2 — Candidate-label false-positive risk / minor noise**
`extract_candidates_from_map()` (`services/field_matcher.py`) now walks past
merge-continuation gaps to find the real label a few columns/rows over (recovering
matches that the corruption fix would otherwise have made Pass 1 miss), and ignores a
small stoplist of generic header words ("Remarks", "Sr No", "Particulars", ...) so
they can't get misused as a label for unrelated blank cells.

**Bonus, not from the original bug list:** added "head office"/"head office address"
as aliases on your existing `address` CompanyField (fixes the specific D11 miss found
during testing), applied via `patch_v2_fixes.py` for existing installs.

## What is still unverified

I don't have network access to `models.inference.ai.azure.com` in the environment I
built this in, so the actual GPT-4o vision fill quality, sheet classification, and
the AI-based horizontal table detector were never re-tested end-to-end after these
changes — only the deterministic, non-AI parts (cell mapping, Pass 1 matching, vertical
block detection, write-back) were directly tested. Please run a real form through
your live server and let me know what you see; I'm glad to keep iterating from there.
