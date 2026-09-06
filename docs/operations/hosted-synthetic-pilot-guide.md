# Hosted synthetic click-through — operator guide

**Date:** 2026-09-03  
**Audience:** program owner (Danny Tran) standing up a demo for stakeholders such as Dr. Wang.  
**Posture:** synthetic data only. Not production. Not live student data. `ALLOW_CLOUD_DEPLOY` remains **false**.

This document answers three questions:

1. How do I run the whole repo on this machine?
2. How do I give someone a **link** (and what Google Cloud can and cannot do today)?
3. Do I need Google **Identity Platform** (IdP) so Dr. Wang can click through?

Companion docs (do not duplicate): [`INSTALL.md`](../../INSTALL.md), [`containers.md`](containers.md), [`deploy-runbook.md`](deploy-runbook.md), [`a1b-gcp-console-guide.md`](../decisions/a1b-gcp-console-guide.md), [`f5-deploy-target-note-2026-09-03.md`](../decisions/f5-deploy-target-note-2026-09-03.md).

---

## Bottom line

| Goal | What to do now | What is not ready |
|---|---|---|
| Run the backend + import/review/metrics smoke path | `docker compose up --build -d` then `scripts/compose_smoke.sh` (or the curl sequence in `INSTALL.md`) | Matching scores, outreach send, Calendar API, crawler |
| Let Dr. Wang click a **UI** | Compose API + **legacy frontend** on Vite, with fixture bearer token | New product UI (`apps/web` is on hold); many legacy screens still 404 / fallback identities |
| Share a **HTTPS link** | Run the stack locally, then a **tunnel** (Cloudflare Tunnel or ngrok) to the Vite port | Terraform apply, Cloud Run, Artifact Registry push |
| Google login / “real” institutional sign-in | Fill A1b worksheet Part 1, then engineering implements JWKS (not in tree) | Identity Platform tenant exists; **code still only accepts fixture tokens** |
| Deploy the app itself on GCP | Wait for F5 modules + S-001 OIDC; first target is the **classroom** project | `infra/terraform` is a non-applyable skeleton; CI builds images and pushes nowhere |

**IdP is not required for a synthetic click-through.** It is required for a Google-account login that the API actually verifies. Those are different milestones.

---

## What “the entire repo” actually boots

Compose brings up **database + migrate + seed + API + worker + scheduler**. It does **not** start the frontend.

| Process | Local address | Role |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | Schema + seed |
| API | `127.0.0.1:8080` (compose) or `:8000` (`make run-api`) | HTTP product API |
| Worker | `127.0.0.1:8081` | Dispatch + task execute (dev bearers only) |
| Scheduler sidecar | no published port | Emulates Cloud Scheduler every ~2s |
| Legacy UI | `http://127.0.0.1:5173` | Vite; **not** in compose |

Compose publishes ports on **loopback only** (`127.0.0.1`). That is why a colleague on another network cannot hit `:8080` until you add a tunnel. It is also why a tunnel must run **on the same machine** as Docker.

The Vite proxy in `apps/web/legacy-frontend/vite.config.ts` targets **`http://127.0.0.1:8000`**, which matches `make run-api`, **not** compose’s `:8080`. If you use compose, change both `/api` and `/v1` `target` values to `http://127.0.0.1:8080` for that demo (revert afterward; do not commit a demo-only port unless product agrees).

---

## Path A — run it on Windows (recommended for Friday)

Prerequisites: **Docker Desktop** (Linux engine), **Node 20+**, Git. Python 3.11 is only required if you skip Docker and use `make` (WSL/Linux). Python **3.13 does not work**.

### 1. Backend appliance

From the repo root:

```powershell
docker compose up --build -d
docker compose ps
```

Expect `api`, `worker`, and `scheduler` **running/healthy**; `migrate` and `seed` **exited 0**.

Health:

```powershell
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8081/health
```

API should look like `{"status":"ok","release":"compose-dev"}`.

### 2. Prove import → review (no UI)

Git Bash / WSL: `scripts/compose_smoke.sh`  
Or follow `INSTALL.md` “Smoke-testing the full import path”.

Compose maps bearer token `compose-api` → subject `compose-pilot-coordinator` (seeded coordinator). That is **not** a password. Anyone with the URL and that token is the coordinator.

### 3. Legacy frontend (click-through)

```powershell
cd apps\web\legacy-frontend
npm ci
```

Create `apps/web/legacy-frontend/.env.local` (gitignored; never commit):

```
VITE_SMARTMATCH_BEARER_TOKEN=compose-api
VITE_SMARTMATCH_UNIT_ID=<uuid from step below>
```

Recover the unit id:

```powershell
docker compose exec -T db psql "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch" -tAc "select id from org_unit where path = 'pilot'"
```

Paste that UUID into `VITE_SMARTMATCH_UNIT_ID`. Restart Vite after changing env (Vite bakes `VITE_*` at start).

Point `vite.config.ts` proxies at `:8080` if using compose, then:

```powershell
npm run dev
```

Open `http://localhost:5173`. Authenticated `/v1` calls use the bearer above. Login **role cards** and `mockLogin` are not this API; they 404. Do not ask Dr. Wang to “pick a portal role” as if it were real authorization — roles come from seeded membership.

### 4. Share a link (same day, no Cloud Run)

Keep compose + Vite running. In a second terminal, create a tunnel to **5173** (the UI). The Vite proxy then reaches the API on loopback.

**Cloudflare Tunnel (quick tunnel, no account required for a throwaway URL):**

```powershell
cloudflared tunnel --url http://127.0.0.1:5173
```

Send Dr. Wang the `https://….trycloudflare.com` URL. Treat it as a **demo secret**: it exposes the fixture coordinator token baked into the frontend build.

**ngrok** is the same idea: `ngrok http 5173`.

Rules:

- Synthetic data only. No real student spreadsheets.
- Stop the tunnel when the session ends.
- Do not bind compose ports to `0.0.0.0` “to make GCP easier” — that publishes unauthenticated worker task routes on your LAN. Tunnel the UI instead.

This is **not** a GCP deployment. It is a hosted *session* of your laptop.

**24/7 for Wang (still not Cloud Run):** a classroom GCE VM running the same
compose stack, plus a **named Cloudflare Tunnel** and **Access** email
allowlist — [`classroom-vm-cloudflare-tunnel.md`](classroom-vm-cloudflare-tunnel.md).

---

## Path B — Google Cloud as people imagine it (not runnable from this repo yet)

Architecture intent (v1.1): four **separate GCP projects** (`dev`, `staging`, `classroom`, `prod`). Stakeholder synthetic demo belongs in **`classroom`** when F5 lands — see the F5 note. Classroom is fixtures-only, no provider secrets, no promotion to prod.

What exists in-repo:

| Piece | State |
|---|---|
| `infra/terraform/envs/*/main.tf` | Comment-only skeletons. `make infra-check` **fails the build** if real resources appear. **Do not `terraform apply`.** |
| Container images | Built in CI; **not pushed** to Artifact Registry |
| Cloud Run `PORT=8080` | Images listen on `PORT`; no service is deployed |
| Cloud SQL / Cloud Tasks / Cloud Scheduler | Not provisioned. Compose **emulates** Tasks/Scheduler with bearers that **refuse to boot** unless `SMARTMATCH_EDITION=dev` |

`ALLOW_CLOUD_DEPLOY=false` is a standing constraint, not a missing checkbox in `.env`. Flipping a local env var does not create a registry, OIDC, or SQL instance.

When F5 + S-001 actually land, the cloud path is roughly:

1. Separate **classroom** GCP project (synthetic only).
2. Enable APIs listed under [GCP APIs](#gcp-apis).
3. Artifact Registry + Cloud Run (API + worker) + Cloud SQL Postgres 16.
4. Secret Manager for `SMARTMATCH_DATABASE_URL` (never a committed `.env`).
5. Cloud Tasks queue + Cloud Scheduler job with **distinct** OIDC audiences/allowlists (`SMARTMATCH_TASK_*` vs `SMARTMATCH_SCHEDULER_*`).
6. Worker signature backend (today the OIDC verifier **refuses every delivery** without one).
7. Only then: a stable `https://….run.app` URL.

Until that work merges, Path A is the only honest “link.”

---

## Identity Platform (IdP) — required for Wang click-through?

**IdP** here means **Google Cloud Identity Platform** (Firebase-compatible OIDC): users sign in with Google; the API verifies a JWT against the tenant’s JWKS; the server looks up role from `user_account` / membership. It is **not** “turning on GCP so the site has a URL.” Hosting and login are separate.

| Question | Answer |
|---|---|
| Does Dr. Wang need Google login to click import / metrics / coordinator screens on **synthetic** data? | **No.** Fixture bearer `compose-api` + seeded coordinator is enough for API-backed screens that exist. |
| Does program direction want a **single standard login** (no “choose your portal”)? | **Yes** (G1 worksheet). That is P2 / A1b, not a compose feature. |
| Can Identity Platform do that today if you fill the console? | **Not in this codebase.** The API uses `FixtureTokenVerifier` only. There is **no** committed JWKS verifier. `SMARTMATCH_JWKS_*` appears in the A1b console guide as **future** settings; `services/api/smartmatch_api/config.py` does **not** read them. |
| Is the GCP IdP tenant already created? | **Yes** (recorded 2026-09-02). Worksheet Part 1 (issuer, audience, JWKS, client ID, redirects, approval) is still **unfilled**. Agents must not invent those URLs. |
| After you fill the worksheet, are you done? | **No.** Engineering still implements A1–A4 (verifier, frontend OIDC redirect, remove `iaw_session` fallbacks). Then a feature-flagged JWKS path can accept real Google tokens. |

### What you should do in GCP for IdP (human, this week)

Follow [`a1b-gcp-console-guide.md`](../decisions/a1b-gcp-console-guide.md) in the **dev/test** Identity Platform project (not prod SSO). Then transcribe exact values into [`a1b-idp-configuration-worksheet.md`](../decisions/a1b-idp-configuration-worksheet.md) §1.1–1.4, sign the approval block, and commit the worksheet. That unblocks the JWKS implementation; it does **not** by itself log Dr. Wang in.

For a Friday UI demo, skip waiting on IdP. Use Path A. Tell Wang: this is a **synthetic coordinator session**, not IA West SSO.

---

## `.env` inventory — what `.env.example` has vs what the code reads

Copy `.env.example` → `.env` for **host** `make run-api` / `make run-worker`. Compose **ignores** `.env` for the values it hard-sets in `docker-compose.yml`.

### In `.env.example` (enough for host API)

| Variable | Needed for local API? | Notes |
|---|---|---|
| `SMARTMATCH_EDITION` | Yes (keep `dev`) | Non-dev refuses `SMARTMATCH_DEV_PRINCIPALS` |
| `SMARTMATCH_DATABASE_URL` | Yes | Default matches compose/native Postgres |
| `SMARTMATCH_USE_FIXTURE_PROVIDERS` | Yes (`true`) | Setting `false` does **not** enable live providers; construction fails |
| `SMARTMATCH_DEV_PRINCIPALS` | Yes for authenticated API without compose | JSON `{"token":"subject"}`; must match `make seed-pilot` subject. Compose already sets `{"compose-api":"compose-pilot-coordinator"}` |
| `SMARTMATCH_EMAIL_API_KEY` | Leave empty | Outreach (G4) not implemented |
| `SMARTMATCH_ROUTES_API_KEY` | Leave empty | Routes adapter not live |
| `SMARTMATCH_RELEASE` | Optional | Health payload only |

You are **not** missing live SendGrid/Google Maps keys. Empty is correct.

### Used by compose/worker, **absent** from `.env.example`

These are set in `docker-compose.yml` for the appliance. Add them to a host `.env` only if you run the worker **without** compose:

| Variable | Default / compose value | Purpose |
|---|---|---|
| `SMARTMATCH_DEV_TASK_BEARER_TOKEN` | `compose-task` | `POST /tasks/execute` in `dev` only |
| `SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN` | `compose-sched` | `POST /operations/dispatch` in `dev` only; **must differ** from the task token |
| `SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN` | same as scheduler token | Sidecar only |
| `SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED` | `true` in compose | Loopback queue |
| `SMARTMATCH_LOCAL_TASK_TARGET_URL` | `http://127.0.0.1:8080/tasks/execute` | Must be loopback HTTP, path exactly `/tasks/execute` |
| `PORT` | `8080` in images | Cloud Run injects this |
| `SMARTMATCH_COLUMN_CONTRACT_PATH` | set in worker image | Path to `columns.yaml` |

### Cloud / OIDC — unset on purpose (fail-closed)

Do **not** put real values in a local `.env` until S-001/F5 exist. Unset means refuse, which is correct.

| Variable | Consumed? | Status |
|---|---|---|
| `SMARTMATCH_TASK_AUDIENCE` | Worker yes | Empty → OIDC path 401/501 |
| `SMARTMATCH_TASK_SERVICE_ACCOUNTS` | Worker yes | Empty allowlist = nobody |
| `SMARTMATCH_SCHEDULER_AUDIENCE` | Worker yes | Separate from task audience |
| `SMARTMATCH_SCHEDULER_SERVICE_ACCOUNTS` | Worker yes | Separate allowlist |
| `SMARTMATCH_JWKS_ISSUER` / `_AUDIENCE` / `_URI` / `_ALGORITHMS` / `_ENABLED` | **Documented for A1b, not in API Settings** | Filling them today does nothing |
| `SMARTMATCH_SPEND_CEILING_JOB` / `_TENANT_DAY` / `_TENANT_MONTH` | Worker yes | All three required to enable paid extraction; leave unset |

### Frontend (not in `.env.example` at all)

| Variable | Where | Purpose |
|---|---|---|
| `VITE_SMARTMATCH_BEARER_TOKEN` | `apps/web/legacy-frontend/.env.local` | Maps to API fixture token (`compose-api` on compose) |
| `VITE_SMARTMATCH_UNIT_ID` | same | Metrics/unit-scoped UI |

There is no `VITE_GOOGLE_CLIENT_ID` wired. OAuth client ID belongs in the A1b worksheet, then in a future A2 implementation.

---

## GCP APIs

### For Identity Platform only (do this; hosting is separate)

In the **dev/test** project that already has the tenant:

- Identity Platform API  
- Identity Toolkit API (often enabled with Identity Platform)

Then create the OAuth **Web** client and redirect URIs as in the A1b console guide (`http://localhost:5173/...` plus the tunnel hostname **if** you later do real OIDC against a tunneled UI).

### For a future classroom Cloud Run deploy (do **not** enable hoping the repo will deploy)

When F5 exists, classroom project typically needs:

- Cloud Run Admin  
- Artifact Registry  
- Cloud SQL Admin  
- Cloud Tasks  
- Cloud Scheduler  
- Secret Manager  
- IAM / Service Usage  

Plus Identity Platform **if** A1b is in that same project (product may keep IdP in the existing tenant project and point classroom Cloud Run at that issuer — record the choice on the worksheet; do not invent it).

**Do not enable** Calendar API, Maps/Routes, Gmail/SendGrid, or crawl-related APIs for this pilot. G4/G5/G3 live paths are gated; classroom must not hold those credentials.

---

## What Dr. Wang can vs cannot click (honest)

**Can (if Path A works and the screen calls a real `/v1` route):** health, import command, metrics (empty/zero funnel until pipeline writers exist), review decision via API (UI may or may not expose it yet).

**Cannot, regardless of GCP:** live matching scores (registry approved; scorers M2–M3 not built), outreach send (G4), Google Calendar (G5), live crawl, rewards ledger APIs, production SSO, “the new SmartMatch UI.”

If a button looks real and 404s, that is the legacy frontend vs this contract — OpenAPI wins.

---

## Safety

- Never commit `.env`, `.env.local`, OAuth client secrets, or service-account JSON.  
- Never import live student CSVs.  
- Never set `SMARTMATCH_EDITION` to `staging`/`classroom`/`production` on compose; seed, local queue, and fixture principals will refuse to start.  
- A public tunnel + baked `compose-api` token is a **demo**, not an access-control model.
