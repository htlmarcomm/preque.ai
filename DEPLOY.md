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
persistent volume. **Oracle Cloud's Always Free tier** (this guide's main
path) is genuinely free forever with generous specs, but it's a raw VM, not
a one-click platform — you're managing Docker and networking yourself.
Railway/Render are simpler but not free on an ongoing basis (an alternative
section below covers Railway if you change your mind later).

## 1. Required environment variables

Set these on the hosting platform (not in a committed file):

| Variable | Value | Notes |
|---|---|---|
| `OPENAI_API_KEY` | your Gemini key | from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — free tier, no card |
| `API_ACCESS_KEY` | a random secret | `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Every `/api/*` request must send this as `X-API-Key`. |
| `DATABASE_URL` | `sqlite:///./uploads/preque.db` | puts the DB **inside** the uploads folder so one volume covers both — see step 5 |

Optional, only if you use SharePoint export/import (`backend/routers/sharepoint.py`):
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`. Read the note in
the Known limitations section below before turning this on for a public
deployment.

The frontend needs `API_ACCESS_KEY`'s value baked in at **build time** (it's
a static bundle, not a server) — see step 5.

## 2. Create the Oracle Cloud account and VM

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
   A card is required for identity verification, but Always Free resources
   are never billed.
2. **Compute → Instances → Create Instance**.
3. **Image**: Canonical Ubuntu (latest LTS, e.g. 24.04).
4. **Shape**: click Edit → change to **Ampere → VM.Standard.A1.Flex** → set
   it to the max Always Free allowance, **4 OCPUs / 24GB memory**. (This is
   an ARM64 machine, not the usual x86 — the Dockerfile's base images all
   support ARM64, so this should just work, but flag it to me if a package
   fails to build and we'll debug it together.)
5. **Add SSH keys**: let Oracle generate a key pair and download the
   private key (or paste your own public key if you already have one).
6. Under **Networking**, keep the default VCN and confirm "Assign a public
   IPv4 address" is checked.
7. Create the instance and note its **public IP address**.

## 3. Open the firewall (two layers — both need it)

Oracle has a cloud-level firewall (Security List) *and* the VM's own OS
firewall. Traffic needs to pass both.

1. In the console: **Networking → Virtual Cloud Networks** → your VCN →
   **Security Lists → Default Security List → Add Ingress Rules**.
   Add a rule: source `0.0.0.0/0`, TCP, destination port `80` (and `443` if
   you set up HTTPS later — see step 7).
2. SSH into the VM: `ssh -i /path/to/downloaded-key.key ubuntu@<PUBLIC_IP>`
3. Oracle's Ubuntu images also block ports at the OS level by default:
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo netfilter-persistent save
   ```

## 4. Install Docker and get the code

Still inside the SSH session:

```bash
sudo apt update
sudo apt install -y docker.io git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
exit   # log out so the docker group membership takes effect
ssh -i /path/to/downloaded-key.key ubuntu@<PUBLIC_IP>   # log back in

git clone https://github.com/Anushre2005/Preque.ai.git
cd Preque.ai
```

## 5. Build and run

```bash
docker build -t prequeai --build-arg VITE_API_KEY=YOUR_KEY_HERE .

docker run -d --name prequeai \
  -p 80:8000 \
  -v prequeai_data:/app/backend/uploads \
  -e OPENAI_API_KEY=YOUR_GEMINI_KEY \
  -e API_ACCESS_KEY=YOUR_KEY_HERE \
  -e DATABASE_URL=sqlite:///./uploads/preque.db \
  --restart unless-stopped \
  prequeai
```

Use the same value for `YOUR_KEY_HERE` in both places (the build arg and
`API_ACCESS_KEY`) — it's what `VITE_API_KEY` on the frontend and
`API_ACCESS_KEY` on the backend check against each other. `-v prequeai_data`
creates a Docker-managed volume that survives container restarts/rebuilds —
this is what makes the database and uploads persistent here, no separate
"volume" step needed like on a PaaS.

## 6. Verify

- `http://<PUBLIC_IP>/api/health` → `{"status": "PreQue Automation API running"}` (no key needed)
- `http://<PUBLIC_IP>/` → the actual app loads
- Try Fill Form end-to-end once with a real form before handing the link to the team

## 7. HTTPS (do this before sharing the link with anyone)

Right now traffic is plain HTTP — the API key and every bit of company data
travel unencrypted. The simplest fix is [Caddy](https://caddyserver.com/),
which gets you automatic HTTPS with one line, but it needs a real domain
name pointed at the VM's IP (a free subdomain from a provider like DuckDNS
works fine). Once you have one:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
echo "your-domain.duckdns.org {
    reverse_proxy localhost:80
}" | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```
Then add an ingress rule for port 443 (step 3) and use `https://your-domain...`
going forward. Ask me if you want a hand with this part specifically.

## Alternative: Railway (not free, but a one-click platform)

If the VM approach ever feels like too much upkeep, Railway does all of
steps 2–7 for you through a UI, for roughly $5+/month:

1. Sign up at [railway.app](https://railway.app), **New Project → Deploy
   from GitHub repo** → select `Anushre2005/Preque.ai`. It auto-detects the
   root `Dockerfile`.
2. **Variables** tab: add `OPENAI_API_KEY`, `API_ACCESS_KEY`, `DATABASE_URL`
   from the table above.
3. **Settings → Build → Build Args**: add `VITE_API_KEY` set to the same
   value as `API_ACCESS_KEY`, then redeploy.
4. **Settings → Volumes → New Volume**, mount path `/app/backend/uploads`.
5. **Settings → Networking → Generate Domain** for a public HTTPS URL
   (Railway handles HTTPS for you automatically — no Caddy/domain step
   needed here).

## Known limitations, read before sharing the link widely

- **The API key is not a secret once deployed.** It's baked into the
  frontend's JS bundle (step 5), so anyone who opens browser devtools on
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
