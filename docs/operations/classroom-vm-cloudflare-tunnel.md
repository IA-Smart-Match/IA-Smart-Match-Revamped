# Classroom GCE VM + Cloudflare Tunnel (synthetic demo)

**What this is:** a small Google Compute Engine VM in the **classroom** GCP
project running `docker compose`, with **Cloudflare Tunnel** (`cloudflared`)
giving Dr. Wang a stable `https://` hostname. Cloudflare **Access** sits in
front so the link is not a public anonymous website.

**What this is not:** F5 Cloud Run, Cloud SQL, Cloud Tasks, Terraform apply, or
`ALLOW_CLOUD_DEPLOY=true`. The VM still runs **`SMARTMATCH_EDITION=dev`**
(seed, loopback task queue, fixture bearers). Anyone who passes Access and
holds `compose-api` is the seeded coordinator.

**When to use:** Wave 3 `P-COMPOSE-PILOT` merged (or you accept running Vite
yourself until then) and stakeholders need the stack **up for days** without
your laptop.

Do **not** commit tunnel tokens, `config.yml` with credentials, or a VM
`.env` into this repository.

---

## What you need before Console

| Item | Why |
|---|---|
| A **classroom** GCP project (synthetic only; not prod) | Isolation (v1.1 §3.2). Create one if it does not exist yet. |
| Billing enabled on that project | GCE will not create otherwise. |
| A **domain on Cloudflare** (even a cheap one) | Named tunnels need a hostname in a Cloudflare zone. `trycloudflare.com` changes on restart — do not use it for 24/7. |
| Cloudflare account with that zone | Tunnel + Access live here, not in GCP. |
| GitHub access to clone this repo on the VM | Private clone via deploy key or `gh auth`. |
| Wang’s email | Cloudflare Access allowlist. |

---

## Architecture

```
Wang's browser
  → https://pilot.YOURDOMAIN  (Cloudflare edge + Access login)
  → named Tunnel (outbound from VM only)
  → 127.0.0.1:<UI-port> on the GCE VM
  → compose API/worker/Postgres on loopback
```

The VM should **not** have firewall rules opening 80, 443, 8080, or 8081 to
`0.0.0.0/0`. `cloudflared` dials **out**. SSH via **IAP** (or your IP only).

**UI port**

| Until `P-COMPOSE-PILOT` | After that PR |
|---|---|
| Vite `5173` (run `npm run dev` or `preview` on the VM; proxy `/v1` to API `8080`) | Whatever INSTALL/compose documents as the frontend service — still **loopback**, still only that port in the tunnel |

Never put the **worker** (`8081`) in a Tunnel ingress rule.

---

## Part 1 — GCP VM

### 1. Enable APIs

In the classroom project:

```bash
gcloud config set project YOUR_CLASSROOM_PROJECT_ID
gcloud services enable compute.googleapis.com iap.googleapis.com
```

### 2. Firewall: SSH via IAP only

```bash
gcloud compute firewall-rules create allow-ssh-iap \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=smartmatch-pilot
```

Do **not** add `allow-http` / `allow-https` for this demo.

### 3. Create the VM

`e2-small` (2 GB) is tight for Postgres + API + worker + scheduler + Node.
Use **e2-medium** (2 vCPU, 4 GB) and **30 GB** disk.

```bash
gcloud compute instances create smartmatch-pilot \
  --zone=us-west1-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-balanced \
  --tags=smartmatch-pilot \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --metadata=enable-oslogin=TRUE
```

Adjust zone if you prefer. OS Login is optional; you can use a project SSH
key instead.

### 4. SSH

```bash
gcloud compute ssh smartmatch-pilot --zone=us-west1-a --tunnel-through-iap
```

### 5. Install Docker and Git on the VM

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and SSH back in so `docker` works without sudo.

### 6. Clone and start compose

```bash
mkdir -p ~/src && cd ~/src
git clone https://github.com/YOUR_ORG/IA-Smart-Match-Revamped.git
cd IA-Smart-Match-Revamped
git checkout main   # or the SHA that contains Wave 3 compose
docker compose up --build -d
docker compose ps
curl -sS http://127.0.0.1:8080/api/health
```

`migrate` and `seed` should exit 0; `api`, `worker`, `scheduler` should be
healthy.

**Until the frontend is in compose**, on the same VM:

```bash
# Node 20 from NodeSource or nvm — skip if compose already serves the UI
cd ~/src/IA-Smart-Match-Revamped/apps/web/legacy-frontend
# Point vite.config.ts proxy targets at http://127.0.0.1:8080 (compose API).
# .env.local: VITE_SMARTMATCH_BEARER_TOKEN=compose-api
# VITE_SMARTMATCH_UNIT_ID=$(docker compose -f ~/src/IA-Smart-Match-Revamped/docker-compose.yml exec -T db \
#   psql "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" -tAc "select id from org_unit where path = 'pilot'")
npm ci
# keep this process up — systemd unit or tmux until compose owns the UI
npx vite --host 127.0.0.1 --port 5173
```

Do **not** bind Vite or compose published ports to `0.0.0.0`. Tunnel to
`127.0.0.1` only.

Restart compose after reboot:

```bash
sudo tee /etc/systemd/system/smartmatch-compose.service >/dev/null <<'EOF'
[Unit]
Description=SmartMatch synthetic compose stack
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/YOUR_USER/src/IA-Smart-Match-Revamped
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now smartmatch-compose.service
```

Replace `YOUR_USER` with the Linux user that owns the clone.

---

## Part 2 — Cloudflare Tunnel (named, 24/7)

Use a **dashboard / token** tunnel so you do not store credentials in git.

### 1. Create the tunnel

1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels** → **Create**.
2. Name: `smartmatch-classroom-pilot`.
3. Environment: **Debian** / copy the install command **or** only the **token**
   (`eyJ…`). You will run it on the GCE VM.
4. **Public hostname**
   - Subdomain: `pilot` (example)
   - Domain: your Cloudflare zone
   - Type: HTTP
   - URL: `http://127.0.0.1:5173` (or the compose UI port after Wave 3)
5. Save.

### 2. Install `cloudflared` on the VM as a service

On the VM, run the Debian install Cloudflare shows, **or**:

```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
sudo cloudflared service install 'PASTE_TUNNEL_TOKEN_HERE'
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

The token is a secret. Store it in a password manager, not in the repo.

Confirm in Zero Trust that the tunnel is **healthy**.

### 3. DNS

Creating the public hostname in the dashboard usually adds a CNAME
`pilot.YOURDOMAIN` → `<tunnel-id>.cfargotunnel.com`. If it did not:

```bash
# only if you used a locally created tunnel instead of the dashboard token
cloudflared tunnel route dns smartmatch-classroom-pilot pilot.YOURDOMAIN
```

Wait for DNS. Open `https://pilot.YOURDOMAIN` from a browser — you should
reach the UI **after** Access (next part), or a Cloudflare error until Access
is attached.

---

## Part 3 — Cloudflare Access (required for this demo)

The fixture bearer is not access control. Put **Access** on the same hostname.

1. Zero Trust → **Access** → **Applications** → **Add an application** → **Self-hosted**.
2. Application name: `SmartMatch synthetic pilot`.
3. Public hostname: `pilot.YOURDOMAIN` (same as the tunnel).
4. Policy: **Allow**
   - Include → **Emails** → your address and Dr. Wang’s.
   - Optional: one-time PIN / Google login (this is **Cloudflare’s** login, not
     SmartMatch A1b / Identity Platform).
5. Session duration: hours or a day, not weeks.
6. Save.

Wang’s flow: open the URL → Cloudflare email/Google challenge → then the
synthetic coordinator UI.

If you skip Access, anyone who guesses the hostname gets the demo. Do not skip
it.

---

## Part 4 — What to send Wang

- URL: `https://pilot.YOURDOMAIN`
- “This is a **synthetic** coordinator session, not IA West SSO. Cloudflare
  Access is only the door to the demo.”
- If the UI still needs a token in env, that is already baked on the VM; he
  should not need `compose-api` unless you left it out of `.env.local`.

---

## Hygiene

| Do | Do not |
|---|---|
| Keep compose ports on `127.0.0.1` | Publish 8080/8081 on the VM external IP |
| Tunnel **only** the UI | Ingress the worker or Postgres |
| Synthetic seed only | Import live student CSVs |
| Stop or snapshot the VM when the pilot week ends | Leave an unattended public Access-less hostname |
| `gcloud compute instances stop smartmatch-pilot` to save money | Assume this VM is production |

```bash
gcloud compute instances stop smartmatch-pilot --zone=us-west1-a
gcloud compute instances start smartmatch-pilot --zone=us-west1-a
```

After start, systemd should bring compose and `cloudflared` back. Confirm
tunnel **healthy** in Zero Trust.

---

## Failures

| Symptom | Check |
|---|---|
| Tunnel down | `sudo journalctl -u cloudflared -n 80`; VM have outbound HTTPS? |
| 502 from Cloudflare | UI process not listening on the ingress port; `ss -lntp \| grep 5173` (or compose UI) |
| Access loop | Application hostname ≠ tunnel hostname |
| API 401 in UI | `.env.local` / compose frontend missing `compose-api`; Vite still proxying to `:8000` |
| Compose unhealthy after reboot | `smartmatch-compose.service` WorkingDirectory and user |
| Disk full | `docker system df`; 30 GB fills with images |

---

## Cost (order of magnitude)

e2-medium in `us-west1` is a few tens of USD/month if left 24/7; stop the VM
when idle. Cloudflare Tunnel + Access on a free/zero-trust plan is typically
enough for a handful of users. GCP egress is small if only a few stakeholders
click.

---

## Related

- Stakeholder vs Cloud Run: [`hosted-synthetic-pilot-guide.md`](hosted-synthetic-pilot-guide.md)
- Classroom vs `dev`: [`../decisions/f5-deploy-target-note-2026-09-03.md`](../decisions/f5-deploy-target-note-2026-09-03.md)
- Compose appliance: [`containers.md`](containers.md), `docker-compose.yml`
