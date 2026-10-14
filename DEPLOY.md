# Deploying PreQue AI on Oracle Cloud (Always Free)

One container serves both the API and the built frontend from the same
origin (see `Dockerfile` and `backend/main.py`'s `serve_spa`), so there is no
separate frontend host and no CORS to configure.

It needs a real container host (LibreOffice to render Excel sheets, a
persistent disk for the SQLite database and uploads), so Vercel/Netlify
cannot run it. Oracle's Always Free Arm VM can, at no cost.

## 1. Settings the app needs

Passed to the container as environment variables (never committed):

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | your Gemini key from aistudio.google.com/apikey |
| `JWT_SECRET` | long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `INITIAL_ADMIN_USERNAME` | `admin` (created on first start if no users exist) |
| `INITIAL_ADMIN_PASSWORD` | the password you want for that admin |
| `DATABASE_URL` | `sqlite:///./uploads/preque.db` (keeps the DB on the same volume as uploads) |

## 2. Create the VM (Oracle console)

1. **Compute > Instances > Create instance**.
2. **Image:** Canonical Ubuntu 24.04 (or 22.04).
3. **Shape:** Edit > Ampere > `VM.Standard.A1.Flex`, **4 OCPUs / 24 GB**.
   If it says "out of capacity", retry later or in another availability domain.
4. **SSH keys:** let Oracle generate a key pair and download the private key.
5. Keep "Assign a public IPv4 address" ticked. Create it and note the **public IP**.

## 3. Open port 80 (two layers)

1. Console: **Networking > Virtual cloud networks** > your VCN > **Security
   lists** > Default > **Add ingress rules**: source `0.0.0.0/0`, TCP, port `80`
   (add `443` too if you set up HTTPS below).
2. On the VM (step 4), Oracle's Ubuntu image also blocks ports by default:
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo apt install -y iptables-persistent && sudo netfilter-persistent save
   ```

## 4. Connect, install Docker, get the code

From a terminal on your computer (PowerShell works):

```bash
ssh -i path\to\downloaded.key ubuntu@PUBLIC_IP
```

On the VM:

```bash
sudo apt update && sudo apt install -y docker.io git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
exit
```

Connect again with the same `ssh` command (so the docker group applies), then:

```bash
git clone https://github.com/htlmarcomm/preque.ai.git
cd preque.ai
```

If the repository is private, GitHub asks for a username and a personal
access token (Settings > Developer settings > Tokens) instead of a password.

## 5. Build and run

The first build takes 15-25 minutes (LibreOffice and the search model are big).

```bash
docker build -t preque .

docker run -d --name preque --restart unless-stopped \
  -p 80:8000 \
  -v preque_data:/app/backend/uploads \
  -e OPENAI_API_KEY='YOUR_GEMINI_KEY' \
  -e JWT_SECRET='YOUR_LONG_RANDOM_STRING' \
  -e INITIAL_ADMIN_USERNAME=admin \
  -e INITIAL_ADMIN_PASSWORD='YOUR_ADMIN_PASSWORD' \
  -e DATABASE_URL=sqlite:///./uploads/preque.db \
  preque
```

The `preque_data` volume holds the database and every upload and survives
restarts and rebuilds. The unified project register fills itself on first start.

## 6. Check it

- `http://PUBLIC_IP/api/health` shows `{"status":"PreQue Automation API running"}`
- `http://PUBLIC_IP/` shows the sign-in page; log in as the admin above.
- Run Fill Form once with a real form before sharing the link.

## 7. Updating later

```bash
cd ~/preque.ai && git pull
docker build -t preque . && docker rm -f preque
# then the same docker run command as step 5
```

## 8. Backing up

```bash
docker run --rm -v preque_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/preque-backup-$(date +%F).tar.gz -C /data .
```

Copy the `.tar.gz` off the VM now and then (`scp`).

## 9. HTTPS (before sharing the link widely)

Plain HTTP sends logins and company data unencrypted. Get a free domain (for
example a DuckDNS subdomain) pointed at the VM's IP, then:

```bash
sudo apt install -y caddy
echo "your-name.duckdns.org {
    reverse_proxy localhost:80
}" | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Add an ingress rule for port 443 (step 3) and open it in `iptables` the same
way as port 80. Use `https://your-name.duckdns.org` from then on.

## Notes

- **Login:** every `/api/*` route needs a user token from `/api/auth/login`.
  Nothing secret is built into the frontend.
- **Gemini free tier** has a daily limit shared by everyone using the app.
  When it runs out the screenshot-reading step returns fewer fields; project
  tables and the keyword matcher still work.
- **SharePoint export/import** uses the app's Azure credentials for any URL
  typed in; only turn on `AZURE_*` settings if that Azure app is narrowly scoped.
- **Deck App button** in the sidebar opens the separate deck app; to point it
  elsewhere, build the frontend with `VITE_DECK_APP_URL` set.
