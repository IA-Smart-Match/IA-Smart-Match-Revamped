# The synthetic pilot VM, and the `deploy` branch

One `e2-medium` VM running the same `docker compose` appliance a developer runs
locally, updated automatically on every push to a protected `deploy` branch.

**It is synthetic, and it is not production.** `SMARTMATCH_EDITION=dev`, fixture
providers, seeded data, the compose-only bearer tokens, and the legacy frontend.
There is no identity provider and no login: the frontend authenticates with the
same fixture bearer token the `curl` steps in [`INSTALL.md`](../../INSTALL.md)
use. There is no real user, no live provider credential, and no production data,
and `ALLOW_CLOUD_DEPLOY=false` is unchanged by anything described here. The gates
that must close before this becomes a production deployment are at the bottom of
this file.

What the VM *is* for: a URL a stakeholder can open, that always reflects the
`deploy` branch, without anyone installing Docker.

---

## The pieces

| Piece | What it is |
|---|---|
| `scripts/vm/bootstrap_vm.sh` | Prepares a fresh Ubuntu 24.04 VM. Idempotent. |
| `scripts/vm/deploy.sh` | The only thing that changes what the VM runs. |
| `scripts/vm/smartmatch.service` | systemd unit; brings the stack up after Docker on every boot. |
| `docker-compose.vm.yml` | Override: `restart: unless-stopped`, and the release SHA. |
| `.github/workflows/deploy.yml` | Runs `build` and `verify`, then invokes `deploy.sh` over IAP. |
| `scripts/compose_health.sh` | The bounded health suite, the same one `./smartmatch.sh health` runs. |

The deployment logic lives on the VM, not in the workflow, so that an operator
can run exactly what CI runs — `sudo -u smartmatch
/opt/smartmatch/app/scripts/vm/deploy.sh` — when something has gone wrong and
GitHub is not the right tool.

---

## Standing the VM up

### 1. Create the instance

The recommended baseline, unchanged:

```bash
gcloud compute instances create smartmatch-pilot \
  --zone=us-west1-a \
  --machine-type=e2-medium \
  --boot-disk-size=30GB \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --no-address \
  --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
  --metadata=enable-oslogin=TRUE
```

`--no-address` is deliberate. The instance has no external IP: administration is
IAP + OS Login, and the application's only public surface is a Cloudflare Tunnel.
Egress for `apt` and `docker build` goes through Cloud NAT, which must exist in
the subnet before the bootstrap will work.

Allow IAP's range to reach SSH, and nothing else:

```bash
gcloud compute firewall-rules create allow-iap-ssh \
  --direction=INGRESS --action=allow --rules=tcp:22 \
  --source-ranges=35.235.240.0/20
```

### 2. Bootstrap it

```bash
gcloud compute ssh smartmatch-pilot --zone=us-west1-a --tunnel-through-iap
sudo ./bootstrap_vm.sh
```

It installs Git, Docker Engine, Compose v2, the PostgreSQL 16 client tools, and
`cloudflared`; creates the unprivileged `smartmatch` user, `/opt/smartmatch` and
its `backups/`, `logs/`, and `deployments/` directories; generates a deploy key;
clones the `deploy` branch and only that branch; and installs and enables the
systemd unit.

It stops for two things it will not do for you.

**The deploy key.** It prints the public half once. Add it to the repository as a
deploy key with **read-only** access — `Settings → Deploy keys → Add deploy key`,
with *Allow write access* unchecked. A VM that can push is a VM that can rewrite
the branch it deploys from. Re-print it with `sudo ./bootstrap_vm.sh
--show-deploy-key`; the private half never leaves the VM and is never printed.

**The Cloudflare Tunnel.** `cloudflared` is installed and left unconfigured. Get
the named tunnel's token out-of-band and, on the VM:

```bash
sudo cloudflared service install <token>
```

Point the tunnel at `http://127.0.0.1:5173` and put a **Cloudflare Access**
policy in front of the hostname. The appliance has no login of its own — Access
is the only thing between the public internet and a stakeholder's view of it.

The token is never committed, never stored as a GitHub secret, never passed
through a workflow, and never echoed into a log. The two Cloudflare secrets the
deployment workflow *does* hold are Access **service-token** credentials, which
authorize a probe and nothing else.

### 3. Deploy for the first time

```bash
sudo -u smartmatch /opt/smartmatch/app/scripts/vm/deploy.sh
```

Identical to every later deployment. There is no separate first-run path.

---

## What a deployment does

`scripts/vm/deploy.sh`, in order, under a `flock` so two deployments cannot
interleave:

1. **Refuses** a dirty working tree. Tracked files modified on the VM mean the
   deployed SHA does not describe what is running, and every other guarantee is
   written in terms of that SHA.
2. **Refuses** a non-fast-forward update. If `origin/deploy` is not a descendant
   of what the VM has, the protected branch was rewritten, and the deployment
   stops rather than rewriting the VM's history to match.
3. **Backs up** the database with `pg_dump`, timestamped, before anything
   migrates. A failed dump stops the deployment.
4. **Fast-forwards** with `git pull --ff-only origin deploy` and reads the
   deployed SHA back out of git rather than assuming it.
5. **Builds** the images. A build failure leaves the previous release serving.
6. **Recreates** the changed services with `docker compose up -d
   --remove-orphans`, which runs the one-shot `migrate` service exactly once and,
   through the compose file's own `service_completed_successfully` conditions,
   does not start the API or worker until it has exited 0.
7. **Health-checks** with the full bounded suite, including that `/api/health`
   reports the SHA just deployed.
8. **Rolls the application back** on any failure: the previous commit, rebuilt,
   re-health-checked — and the script still exits nonzero, so the GitHub job
   fails even though the VM recovered.

It writes a log to `/opt/smartmatch/logs/deploy-<stamp>.log` and metadata to
`/opt/smartmatch/deployments/deploy-<stamp>.json`. Everything it prints passes
through a redaction filter, because that log is printed by a CI job.

### Two things it will never do

**It never removes a volume.** `docker compose down -v` does not appear in it, in
the systemd unit, or in either launcher, and
`tests/unit/test_launcher_parity.py` asserts that it never will. That command is
the one that discards the database.

**It never undoes a migration.** Migrations are forward-only. The rollback in
step 8 is an *application* rollback — the previous code against the
already-migrated schema — which is safe precisely because every revision must be
compatible with the release before it. See
[`deploy-runbook.md`](deploy-runbook.md), which is the authority on migration
policy and on what to do when a revision fails part-way. The backup exists so
that a human has something to work from; restoring it is a deliberate, manual,
logged decision.

---

## Branch protection

`deploy` must be configured with:

* Require a pull request before merging, with at least one approval.
* Require the `build` and `verify` status checks to pass.
* No force pushes, and no deletions.

The last one is not a formality. `scripts/vm/deploy.sh` refuses a
non-fast-forward update, so a force push to `deploy` does not corrupt the VM —
it *stops all deployments* until a human resolves it. Protecting the branch is
what keeps that from happening in the first place.

---

## GitHub environment `pilot-vm`

Variables — identifiers, deliberately not secrets, because a failed deployment
whose error message is redacted is a failed deployment nobody can debug:

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | `smartmatch-pilot-1234` |
| `GCP_ZONE` | `us-west1-a` |
| `GCE_INSTANCE` | `smartmatch-pilot` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `deployer@<project>.iam.gserviceaccount.com` |
| `SMARTMATCH_PUBLIC_URL` | `https://<host>` |

Secrets — exactly two, and neither is a cloud credential:

| Secret | What it is |
|---|---|
| `CLOUDFLARE_ACCESS_CLIENT_ID` | Access service token, for the post-deployment probe |
| `CLOUDFLARE_ACCESS_CLIENT_SECRET` | its secret half |

There is **no service-account JSON key**. GitHub mints a short-lived OIDC token,
Workload Identity Federation exchanges it, and the resulting access token expires
in an hour. The provider's attribute condition must name this repository, so a
token minted by any other repository is refused at the exchange.

The deployment service account needs:

* `roles/iap.tunnelResourceAccessor` — to reach the VM at all
* `roles/compute.osLogin` (or `osAdminLogin`) — to authenticate as a Linux user
* `roles/compute.viewer` — to resolve the instance

and the federated principal needs `roles/iam.serviceAccountTokenCreator` on it.

---

## Concurrency

The deployment workflow serializes on a single never-cancelling group. Cancelling
mid-run could kill `deploy.sh` between its migration and its health check,
leaving the VM in a state no later run reasons about. Queued pushes wait, and
each one then fast-forwards to whatever `deploy` currently points at — so three
rapid pushes converge on the newest commit rather than replaying three
intermediate ones.

`build` and `verify` are called by the deployment workflow rather than copied,
and both switch off `cancel-in-progress` on `refs/heads/deploy` for the same
reason.

---

## Operating it

```bash
# Everything below runs on the VM, over IAP.
gcloud compute ssh smartmatch-pilot --zone=us-west1-a --tunnel-through-iap

sudo -u smartmatch /opt/smartmatch/app/scripts/vm/deploy.sh    # deploy by hand
cd /opt/smartmatch/app && ./smartmatch.sh status               # what is running
cd /opt/smartmatch/app && ./smartmatch.sh health               # the same suite CI runs
cd /opt/smartmatch/app && ./smartmatch.sh logs api             # one service's logs

ls -t /opt/smartmatch/logs | head                              # recent deployments
cat /opt/smartmatch/deployments/$(ls -t /opt/smartmatch/deployments | head -1)
ls -lh /opt/smartmatch/backups                                 # the dumps
```

`systemctl status smartmatch` shows the boot-time unit. It runs `docker compose
... up -d --remove-orphans` and stops with `... stop` — never `down`, and never
`-v`.

### When a deployment fails

The job output is the deployment log, redacted. Read it top-down: the script
names the stage it stopped at and, for the common refusals, what to do about it.
The metadata file records `outcome`, `failure_stage`, `previous_sha`,
`deployed_sha`, and whether it rolled back.

If it rolled back and the rollback was healthy, the VM is serving the previous
release and there is no emergency — fix the commit and push again. If the
rollback itself was unhealthy, the log says so explicitly, and that is the case
that needs a person.

---

## Before any of this becomes production

The VM stays on `SMARTMATCH_EDITION=dev`, fixture providers, synthetic data, and
the legacy frontend until every one of these closes. None of them are closed
today.

* Explicit approval to change `ALLOW_CLOUD_DEPLOY`.
* Institutional JWKS identity, and the removal of the browser-embedded fixture
  bearer credentials.
* Worker signature verification completed, with separate Cloud Tasks and Cloud
  Scheduler OIDC identities (open item F5 / finding S-001).
* The local queue and scheduler sidecars replaced by Cloud Tasks and Cloud
  Scheduler.
* Isolated Cloud Run, Cloud SQL 16, Secret Manager, Artifact Registry, storage,
  monitoring, alerts, backups, and Terraform state.
* Container image scanning, signing, provenance attestations, and immutable
  SHA image tags — the before-scale gates listed at the bottom of
  [`.github/workflows/verify.yml`](../../.github/workflows/verify.yml).
* The held legacy frontend replaced by the approved production UI.

When they do close, `deploy` stays the protected branch and the *deployment
mechanism* changes: build-once/publish-once immutable images, a migration job,
a Cloud Run rollout, external smoke tests, and traffic rollback to the preceding
revision instead of a VM `git pull`. Forward-only migration behavior is
preserved, and the dispatcher heartbeat, rescue, failure, and lag alerts already
specified in [`deploy-runbook.md`](deploy-runbook.md) §J8/§J9 are implemented
rather than deferred again.
