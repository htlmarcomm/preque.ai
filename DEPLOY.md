# Deploying PreQue AI

One container serves both the API and the built frontend from the same
origin (see `Dockerfile` and `backend/main.py`'s `serve_spa`) — no separate
frontend host, no CORS to configure in production.

## Why this needs a real container host, not a "static site" platform

This app depends on:
- **LibreOffice**, installed at the OS level, to render each Excel sheet to
  an image for the GPT-vision fill step (`backend/routers/forms.py`)
- **A persistent disk** for the SQLite database and every uploaded file
  (forms, documents, project registers) — nothing here is in an external
  database or object storage

That rules out purely serverless/static hosts (Vercel, Netlify, Cloudflare
Pages) — they don't give you a real filesystem or let you install system
packages. You need a platform that runs your `Dockerfile` and gives you a
persistent volume. **Railway** and **Render** both fit (this guide uses
Railway); a plain VPS (DigitalOcean/Hetzner) works too if you'd rather
manage the box yourself.

## 1. Required environment variables

Set these on the hosting platform (not in a committed file):

| Variable | Value | Notes |
|---|---|---|
| `OPENAI_API_KEY` | your Gemini key | from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — free tier, no card |
| `API_ACCESS_KEY` | a random secret | `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Every `/api/*` request must send this as `X-API-Key`. |
| `DATABASE_URL` | `sqlite:///./uploads/preque.db` | puts the DB **inside** the uploads folder so one volume covers both — see step 3 |

Optional, only if you use SharePoint export/import (`backend/routers/sharepoint.py`):
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`. Read the note in
the Known limitations section below before turning this on for a public
deployment.

The frontend needs `API_ACCESS_KEY`'s value baked in at **build time** (it's
a static bundle, not a server) — see step 4.

## 2. Deploy on Railway

1. Sign up / log in at [railway.app](https://railway.app).
2. **New Project → Deploy from GitHub repo** → select `Anushre2005/Preque.ai`.
3. Railway will detect the root `Dockerfile` automatically. If it doesn't,
   set the build method to "Dockerfile" in the service's Settings.
4. In the service's **Variables** tab, add `OPENAI_API_KEY`, `API_ACCESS_KEY`,
   and `DATABASE_URL` from the table above.
5. In **Settings → Networking**, click "Generate Domain" to get a public
   `https://....up.railway.app` URL.

## 3. Add the persistent volume

Without this, every redeploy wipes the database and every uploaded file.

1. In the service, go to **Settings → Volumes → New Volume**.
2. Mount path: `/app/backend/uploads`
3. That's it — `DATABASE_URL=sqlite:///./uploads/preque.db` (step 1) puts the
   database inside this same mounted directory, so one volume persists
   everything.

## 4. Bake the API key into the frontend build

The frontend is a static bundle — it can't read a server-side environment
variable at runtime, so the key has to be set at **build time** via the
Dockerfile's `VITE_API_KEY` build arg (see `Dockerfile`, stage 1).

In Railway: **Settings → Build → Build Args**, add `VITE_API_KEY` with the
same value you set for `API_ACCESS_KEY` in step 1. Trigger a redeploy after
adding it (build args only apply to the build that follows).

## 5. Verify

- `https://your-app.up.railway.app/api/health` → `{"status": "PreQue Automation API running"}` (no key needed)
- `https://your-app.up.railway.app/` → the actual app loads
- Try Fill Form end-to-end once with a real form before handing the link to the team

## Known limitations, read before sharing the link widely

- **The API key is not a secret once deployed.** It's baked into the
  frontend's JS bundle (step 4), so anyone who opens browser devtools on
  the live site can read it. It stops casual/opportunistic access, not a
  determined person. There's no per-user login — treat the link as "known
  to anyone who can reach the site," not private. If that's not acceptable,
  this needs real per-user auth, which is a separate, bigger piece of work.
- **No per-user data isolation.** Anyone holding the key can see, edit, or
  delete any team member's forms and company data. This is the intended
  model for a small shared internal tool — flagging it so it's a deliberate
  choice, not a surprise.
- **SharePoint export/import trusts whatever URL is typed into it**, using
  this app's own Azure service-principal credentials with no allowlist. If
  you configure `AZURE_CLIENT_ID`/`AZURE_TENANT_ID`/`AZURE_CLIENT_SECRET`,
  understand that anyone with the API key can point those credentials at
  any SharePoint site the Azure app has access to — scope that Azure app's
  permissions narrowly before turning this on for a public deployment.
- **Gemini's free tier is 1,500 requests/day.** Generous, but shared across
  your whole team once this is "always on" — a busy day of form-filling
  could exhaust it. If that happens, Fill Form's AI step degrades to the
  deterministic keyword matcher only (still works, just fills fewer fields)
  rather than failing outright.
