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

> **Before you follow any of this: the machine serving the pilot today does not
> have the layout described below.** `/opt/smartmatch/app` is not on it, the
> `pilot-vm` GitHub environment is empty, and a push to `deploy` consequently
> deploys nothing. What the rest of this document describes is a design that was
> specified, reviewed and merged but **never bootstrapped onto a machine**. It is
> not wrong, and nothing in it has been retracted; it is unbuilt. The instance
> actually answering `https://pilot.plated.blog` is described in
> [What is actually on the VM today](#what-is-actually-on-the-vm-today), and the
> procedure that works today is
> [Deploying a merged commit today](#deploying-a-merged-commit-today-end-to-end).
> Whether the runbook should be corrected to match the machine, or the machine
> bootstrapped to match the runbook, is
> [an open decision](#the-gap-and-the-decision-it-needs) for the program owner.
> This document does not make that decision, and neither should a reader who
> lands here in a hurry.

---

## What is actually on the VM today

Two sessions independently inspected the running instance on 9 September 2026
and reported the same machine. This section records what they reported, set
beside what this repository claims about each point, so a reader can see exactly
where the two agree and where they do not.

**On the standard of evidence.** Nothing below was verified from inside a
checkout: a worktree cannot reach the VM, and no command in this repository can
tell you what is installed on a machine. So each machine-side statement is
labelled an *observation* and attributed to those two sessions, while every
repository-side statement beside it is cited by `file:line` so that half can be
re-checked without trusting anybody. Where neither source settles a question,
this section says the answer is unknown rather than choosing the likelier one —
[ADR-0011](../architecture/decisions/ADR-0011-accountable-numbers.md)'s first
rule, that a value with no evidence renders as `unknown` and never as a
confident-looking zero, is a rule about prose here as much as it is about
metrics.

### The checkout lives in a home directory, not `/opt/smartmatch/app`

**Observed:** the appliance runs `docker compose` out of
`~dannybrook02_gmail_com/src/IA-Smart-Match-Revamped`, checked out on `main`.
`/opt/smartmatch/app` does not exist on the instance.

**What the repository says:** `scripts/vm/deploy.sh:80-81` defaults `STATE_DIR`
to `/opt/smartmatch` and `APP_DIR` to `${STATE_DIR}/app`, and
`scripts/vm/deploy.sh:129-132` refuses to proceed at all — exit code 3, with the
message "is not a git checkout; run scripts/vm/bootstrap_vm.sh first" — when
`$APP_DIR/.git` is absent. `scripts/vm/smartmatch.service:31` sets
`WorkingDirectory=/opt/smartmatch/app` and `scripts/vm/smartmatch.service:29`
runs the unit as `User=smartmatch`. The script and the unit agree with each
other and disagree with the machine: run against the VM as observed,
`scripts/vm/deploy.sh` exits 3 before it changes anything. That is the script
behaving correctly. Its very first prerequisite check is the one that fails.

This home-directory layout is not undocumented in this repository — it is simply
documented somewhere else. It is the layout
[`classroom-vm-cloudflare-tunnel.md`](classroom-vm-cloudflare-tunnel.md)
instructs an operator to build at its lines 125-135: `mkdir -p ~/src && cd
~/src`, `git clone`, `git checkout main`, `docker compose up --build -d`. That
same guide supplies the layout with its own boot-time unit at lines 160-179,
`smartmatch-compose.service`, whose `WorkingDirectory` is
`/home/YOUR_USER/src/IA-Smart-Match-Revamped` and whose `ExecStart` is a plain
`docker compose up -d`. The VM was stood up from that guide rather than from
this one, and the entire discrepancy follows from that single fact. Two
operations documents describe two different machines; only one of them was
built.

**Unknown:** which boot-time unit, if any, is installed on the instance now.
Neither session reported a unit file, and no artifact in this repository can
answer it. If the machine survives a reboot it has something; whether that
something is `smartmatch-compose.service` from the classroom guide, a hand-rolled
variant, or nothing at all is not established here. Someone with IAP access can
settle it in one command (`systemctl list-units 'smartmatch*'`), and this
paragraph should be replaced with the answer rather than a guess.

### The `pilot-vm` environment is empty, so pushing to `deploy` deploys nothing

**Observed:** the `pilot-vm` GitHub environment holds none of `GCP_PROJECT_ID`,
`GCP_ZONE`, `GCE_INSTANCE`, `SMARTMATCH_PUBLIC_URL`,
`GCP_WORKLOAD_IDENTITY_PROVIDER` or `GCP_DEPLOY_SERVICE_ACCOUNT`, and the GCP
project contains no Workload Identity pools whatsoever.

**What the repository says:** those are exactly the six variables
[`deploy.yml`](../../.github/workflows/deploy.yml) enumerates in its header at
lines 42-47 and then tests for in its first job step,
`.github/workflows/deploy.yml:114-135`. That step is deliberately placed *before*
authentication — its own comment explains why, at lines 116-117: an unset
variable would otherwise surface as an opaque `400` from an API three steps
later. With the environment empty, the loop at lines 121-126 emits an
`::error::` for each of the first four names, the two explicit checks at lines
127-134 add the remaining two, and line 135 exits non-zero. The job stops there.
Nothing that follows runs: not the Workload Identity Federation exchange at
lines 137-188, not the `gcloud compute ssh` at lines 199-205, not the Cloudflare
Access probe at lines 246-304.

The consequence is worth stating in plain words because it is the fact most
likely to mislead someone: **a push to `deploy` today produces a workflow run
that goes red at its last job, and changes nothing anywhere.** It does not
partially deploy, it does not deploy an older commit, and it does not touch the
VM — the VM is never contacted, because the credential that would contact it is
never minted.

The reported failure shape corroborates this precisely. One real run was
observed with all ten build-and-verify jobs green and only the final `deploy`
job red. Ten is the number this repository produces:
`.github/workflows/deploy.yml:85-89` calls `build.yml` and `verify.yml` as
reusable workflows rather than copying them, `build.yml` contributes four jobs
(`images` at line 74 over a two-entry matrix declared at line 83, plus
`compose-smoke` at line 240 and `pilot-e2e` at line 357), and `verify.yml`
contributes six (`python`, `isolation`, `audit`, `web`, `supply-chain` and
`secrets`, at lines 46, 129, 219, 240, 346 and 394). Four and six is ten, all of
which pass because none of them needs the VM or a cloud credential, followed by
one that cannot.

The absence of Workload Identity pools in the project is the deeper half of the
same finding. Even with all six variables filled in, `deploy.yml:159-171` would
exchange the GitHub OIDC token at Google STS against a provider that does not
exist, and the guard at lines 169-170 would report that the exchange was
refused. Setting the variables is therefore necessary and not sufficient; the
pool, the provider with its repository-scoped attribute condition, and the
deployment service account described in
[the environment section below](#github-environment-pilot-vm) all have to be
created first.

### The instance is `smartmatch` in `us-west2-c`

**Observed:** the instance name is `smartmatch` and its zone is `us-west2-c`.

**What the repository says:** every document and comment names something else.
`.github/workflows/deploy.yml:43-44` gives `us-west1-a` and `smartmatch-pilot`
as the example values for `GCP_ZONE` and `GCE_INSTANCE`; the create command in
[Standing the VM up](#1-create-the-instance) below creates `smartmatch-pilot` in
`us-west1-a`; `classroom-vm-cloudflare-tunnel.md:88-89` does the same; and
`scripts/vm/bootstrap_vm.sh:6-7` recommends that name and zone in its header
while stating, correctly, that nothing in the script creates the instance.

None of those repository lines is a claim about what exists — they are examples
and recommendations, and the workflow's are explicitly labelled as such. But a
reader who copies `gcloud compute ssh smartmatch-pilot --zone=us-west1-a` out of
any of them reaches nothing, and the error they get back does not say "the name
in the docs is an example." So: the instance to name in an IAP command is
`smartmatch`, and the zone is `us-west2-c`.

**Unknown:** the GCP project id. No session reported it and nothing in this
repository records it; `GCP_PROJECT_ID`'s appearances are all placeholder
examples. `gcloud config get-value project` on a workstation already configured
for this work is the shortest route to it.

### Ports are loopback-only, and the API is on 8080

**Observed:** the VM publishes `api` on `127.0.0.1:8080`, `worker` on `8081`,
`web` on `5173` and `db` on `5432`, all bound to loopback.

**What the repository says:** these are exactly the bindings in the base compose
file, and they are the one point on which every source in this repository
already agrees with the machine. `docker-compose.yml:457` publishes
`127.0.0.1:8080:8080` for `api`, `docker-compose.yml:527` publishes
`127.0.0.1:8081:8080` for `worker`, `docker-compose.yml:691` publishes
`127.0.0.1:5173:5173` for `web`, and `docker-compose.yml:210` publishes
`127.0.0.1:5432:5432` for `db`. `docker-compose.vm.yml:19-24` states, as its
third and last change, that it deliberately does *not* touch the published
ports, precisely because the base file has already confined them to loopback and
"an override that published `0.0.0.0` here would undo that in one line."
[`containers.md`](containers.md) tabulates the same four bindings in its
published-ports section.

The API port is worth calling out on its own because it is a standing source of
confusion rather than a defect. The appliance's API answers on **8080**, not the
**8000** that [`local-dev-walkthrough.md`](local-dev-walkthrough.md) uses. Those
are two different ways of running the API, not a contradiction:
`local-dev-walkthrough.md:193` runs it as a host process on 8000 via `make
run-api`, and `apps/web/legacy-frontend/vite.config.ts:19-23` defaults the dev
server's `/api` and `/v1` proxy to `http://127.0.0.1:8000` to match that path.
On the VM the proxy target is supplied explicitly instead:
`docker-compose.yml:684` sets `SMARTMATCH_API_PROXY_TARGET: "http://api:8080"`,
which resolves the API by compose service name inside the network and never goes
near either loopback port. `hosted-synthetic-pilot-guide.md:38` and
`local-dev-walkthrough.md:286-295` both already document the split; this
paragraph exists so that an operator reading *this* file does not have to find
one of them first.

### The `web` service has no build stage, so the VM serves a dev server

**Observed:** `docker compose build web` prints "No services to build", and
restarting the stack picks up frontend changes without any rebuild. The VM
therefore serves a development build.

**What the repository says:** this is correct, expected, and designed.
`docker-compose.yml:666-669` declares `web` with `image:` — a digest-pinned
`node:20-bookworm-slim` — and no `build:` key at all, which is why compose
reports it has nothing to build. Compare the eight services that *do* build:
`migrate`, `seed`, `seed-principals`, `seed-logins`, `api`, `worker`,
`scheduler` and `seed-review` carry `build:` stanzas at
`docker-compose.yml:227`, `263`, `317`, `372`, `420`, `476`, `554` and `603`.
The frontend is not one of them.

What `web` runs instead is Vite's dev server:
`docker-compose.yml:676-679` gives it the command `[ -x node_modules/.bin/vite ]
|| npm ci; exec npm run dev -- --host 0.0.0.0`, and
`docker-compose.yml:692-693` bind-mounts `./apps/web/legacy-frontend` straight
into `/app`. A `git checkout` on the VM therefore changes the files the running
dev server is already watching, which is exactly why a restart — or in many
cases nothing at all — suffices for a frontend change.
[`containers.md`](containers.md)'s "Deliberately absent" table says the same
thing from the other direction, listing "A production build of the frontend" as
absent because "`web` runs `vite dev`", gated behind `ALLOW_CLOUD_DEPLOY=false`
and a real deploy target.

The reason the public hostname works at all through a dev server is
`apps/web/legacy-frontend/vite.config.ts:39` and `:57`, which add
`pilot.plated.blog` to `allowedHosts` for the `server` and `preview`
configurations. That line arrived in commit `d5ffcb05`, "fix: allow
pilot.plated.blog host for Cloudflare-tunneled dev server", whose message
records the symptom it fixed: Vite's dev-server host check rejected the `Host`
header the tunnel forwards, and the stakeholder link answered "Blocked request".
That commit is on `main`, and it is in-repository corroboration both of the
public hostname and of the fact that what sits behind the tunnel is a dev server
rather than a built bundle.

### `/api/health` reports `dev`, so it cannot tell you which commit is deployed

**Observed:** `/api/health` reports release `"dev"` rather than a commit SHA.

**What the repository says:** `dev` is the literal in `.env.example:52`
(`SMARTMATCH_RELEASE=dev`). Compose substitutes `${SMARTMATCH_RELEASE:-...}`
from the project directory's `.env` before either default applies, so a VM whose
`.env` was copied from `.env.example` — the ordinary thing to do, and what
`local-dev-walkthrough.md:65` and `hosted-synthetic-pilot-guide.md:191` both
instruct — reports `dev` regardless of which compose files are in play. The two
defaults that `dev` displaces are `compose-dev` at `docker-compose.yml:433` and
`:481`, and `vm-unknown` at `docker-compose.vm.yml:49` and `:54`; the latter's
comment says it exists to keep "a hand-run `docker compose up` on the VM honest
rather than letting it claim a release it does not have."

The observation and the repository agree, then, and the mechanism is ordinary
compose variable substitution rather than a bug. But the consequence is the one
operational fact in this section that costs the most: **you cannot learn which
commit the VM is running by asking the VM's health endpoint.** The value it
returns is a fixed string that a checkout on any commit reports identically.

Two downstream properties fall with it. `scripts/compose_health.sh:94-108`
resolves the release it expects in the same order compose does — shell
environment, then `./.env`, then the `compose-dev` default — and its comment
explains that the VM path is supposed to export the deployed git SHA, which "is
what makes a half-applied deployment (new checkout, old containers still
running) a failure rather than a green stack". With `dev` on both sides of that
comparison the check passes and detects nothing. And the workflow step at
`.github/workflows/deploy.yml:286-304`, which insists the public URL serve a
`release` equal to the SHA the VM recorded, could never pass against `dev` even
if the environment were configured — though it would never be reached, because
the config gate stops the job first.

To find out what the VM is running today, ask git on the VM (`git -C
~/src/IA-Smart-Match-Revamped rev-parse HEAD`), and treat the answer as
describing the checkout rather than the containers, since a checkout can be
ahead of the images built from it. The
[decision section](#the-gap-and-the-decision-it-needs) below returns to this:
recording the deployed SHA is one of the properties the scripted path has and
the hand-run path does not.

### The public URL is a Cloudflare Tunnel to `pilot.plated.blog`

**Observed:** the public URL is `https://pilot.plated.blog`, fronted by a
Cloudflare Tunnel.

**What the repository says:** `apps/web/legacy-frontend/vite.config.ts:35-39`
names that hostname in a comment attributing it to "the Cloudflare Tunnel
fronting the classroom pilot VM" and cross-referencing
`classroom-vm-cloudflare-tunnel.md`, which is the guide that sets the tunnel up
(its Part 2, lines 185-231) and puts Cloudflare Access in front of it (its Part
3, lines 234-253). The tunnel token is not in this repository and must not be:
`classroom-vm-cloudflare-tunnel.md:18-19` and this file's own tunnel section say
so, and `scripts/vm/deploy.sh:56-63` records that the deployment path reads no
secret of any kind. The VM's `.env` holds real credential values and is
referenced here by name only.

**Unknown from the repository:** whether a Cloudflare Access policy is currently
attached to `pilot.plated.blog`, and who is on its allowlist. Both guides
require Access — `classroom-vm-cloudflare-tunnel.md:250-252` is blunt that
skipping it hands the demo to anyone who guesses the hostname — but neither
session reported the policy's state, and a repository cannot observe a
Cloudflare configuration. Anyone treating that link as protected should confirm
it in the Zero Trust dashboard rather than infer it from these documents.

---

## Deploying a merged commit today, end to end

This is the procedure that works against the machine as it stands. It is a
hand-run procedure with none of the safety properties of
[`scripts/vm/deploy.sh`](../../scripts/vm/deploy.sh); those are inventoried in
[the next section](#the-gap-and-the-decision-it-needs), and a reader should know
what they are giving up before using this.

**1. Merge to `main`.** `main` is what the VM tracks, as observed. Pushing to
`deploy` is not part of this path and accomplishes nothing towards it; see
[the empty environment above](#the-pilot-vm-environment-is-empty-so-pushing-to-deploy-deploys-nothing).

**2. Open a shell on the VM over IAP.** The instance has no public SSH.

```bash
gcloud compute ssh smartmatch --zone us-west2-c --tunnel-through-iap
```

Add `--project` if your `gcloud` default is not already the right one; the
project id is
[not recorded in this repository](#the-instance-is-smartmatch-in-us-west2-c).

**3. Fast-forward the checkout.**

```bash
cd ~/src/IA-Smart-Match-Revamped
git fetch origin
git status --porcelain          # expect empty; see the warning below
git checkout -B main origin/main
```

The `git status` line is not part of the observed procedure — it is added here
because `git checkout -B` moves the branch pointer regardless of local edits,
and a tracked file modified on the VM means the SHA you are about to read back
does not describe what is running. `scripts/vm/deploy.sh:228-235` refuses
outright in that situation and explains why in the same words. On this path
nothing refuses for you, so look before you move.

**4. Bring the stack up.**

```bash
docker compose up -d
```

Two things about this command deserve attention, because neither is obvious and
both change what "deploying" means on this path.

*It does not rebuild the backend.* `docker compose up -d` reuses whatever images
already exist. `api`, `worker`, `scheduler` and the five one-shot services all
build from `Dockerfile.api` or `Dockerfile.worker` (`docker-compose.yml:227`,
`263`, `317`, `372`, `420`, `476`, `554`, `603`), so a merged commit touching
`services/` or `python/` is checked out but **not running** until the images are
rebuilt. Add `--build`, or run `docker compose build api worker` first, whenever
the change is not purely frontend. A frontend change is the case where a plain
`up -d` genuinely suffices, for the bind-mount-and-dev-server reason
[given above](#the-web-service-has-no-build-stage-so-the-vm-serves-a-dev-server) —
and `docker compose build web` printing "No services to build" is that same fact
reported correctly, not a failure.

*It runs migrations.* The `migrate` one-shot runs as part of `up`, and
`docker-compose.yml`'s `service_completed_successfully` conditions hold `api`
and `worker` back until it exits `0`. That ordering is the compose file's own
contract and holds on this path exactly as it does on the scripted one. What
does *not* hold on this path is the database backup that
`scripts/vm/deploy.sh:267-321` takes before letting any migration run. There is
no dump. Migrations in this repository are forward-only by policy — see
[`deploy-runbook.md`](deploy-runbook.md), which is the authority on that and on
what to do when a revision fails part-way — so a migration that does real damage
on this path leaves nothing to work from.

**Unknown:** whether the observed command includes `-f docker-compose.yml -f
docker-compose.vm.yml`. The reported command was a plain `docker compose up -d`,
which uses the base file alone; the scripted path composes both
(`scripts/vm/deploy.sh:95`), as does the systemd unit
(`scripts/vm/smartmatch.service:38`). The release value cannot settle it, because
`.env` overrides both files' defaults
[as described above](#apihealth-reports-dev-so-it-cannot-tell-you-which-commit-is-deployed).
The difference that matters if the override is absent is
`docker-compose.vm.yml:39-67`: without it, no long-running service carries
`restart: unless-stopped`, so the stack does not come back by itself after a
reboot or a crash unless a systemd unit brings it back. `docker inspect -f
'{{.HostConfig.RestartPolicy.Name}}' <container>` answers this on the VM in one
command, and the answer belongs in this document.

**5. Confirm what is serving.**

```bash
docker compose ps
curl -sS http://127.0.0.1:8080/api/health
curl -sS http://127.0.0.1:8081/health
git -C ~/src/IA-Smart-Match-Revamped rev-parse HEAD
```

Expect `api`, `worker`, `scheduler` and `web` running, and `migrate` plus the
seed one-shots exited `0`. Read the deployed commit from `git rev-parse`, not
from the health payload's `release` field, which reports `dev` on this machine
for the reason
[given above](#apihealth-reports-dev-so-it-cannot-tell-you-which-commit-is-deployed).
`scripts/compose_health.sh` can be run here as well and most of its checks are
meaningful, but its release comparison is not — it compares `dev` against `dev`
and passes.

**6. Confirm the public surface.** Open `https://pilot.plated.blog` in a
browser. This is the only step that exercises the Cloudflare Tunnel, the Access
policy in front of it, and the dev server's `allowedHosts` list together. A
"Blocked request" response is the Vite host check, and means the hostname is
missing from `apps/web/legacy-frontend/vite.config.ts:39`; a Cloudflare error
page instead means the tunnel or the Access application, neither of which lives
in this repository.

---

## The gap, and the decision it needs

There are two coherent end states here, and this repository currently describes
one while operating the other. **Choosing between them is the program owner's
call, and this document deliberately does not make it.** What follows is the
material needed to decide.

### What the scripted path has that the hand-run path does not

Every item is a concrete behavior of
[`scripts/vm/deploy.sh`](../../scripts/vm/deploy.sh), cited so the claim can be
checked rather than taken on faith. None of these exists on the hand-run path;
that is the whole of the trade-off.

| Property | Where it lives | What its absence costs |
|---|---|---|
| **One deployment at a time** | `deploy.sh:142-150` re-execs the script under `flock` on `${STATE_DIR}/deploy.lock`, waiting up to 1800s | Two operators, or an operator and a reboot, can interleave a checkout and a migration |
| **Refuses a dirty tree** | `deploy.sh:228-235` exits `2` and prints the modified files | The recorded SHA stops describing what is running, silently |
| **Refuses a non-fast-forward** | `deploy.sh:258-265`, an explicit `git merge-base --is-ancestor` check, named separately from `git pull --ff-only` so the message says the protected branch was rewritten | A rewritten branch quietly rewrites the VM's history to match |
| **A backup before every migration** | `deploy.sh:267-321` starts the database if it is stopped, waits for it to report healthy, then `pg_dump --clean --if-exists` piped through `gzip`; a failed dump exits `2` and nothing migrates | A destructive revision leaves nothing to work from. This is the single largest difference |
| **Bounded backup retention** | `deploy.sh:449-462` keeps the most recent 14 dumps | Either no dumps at all, or a 30 GB disk that fills and takes the appliance down |
| **Build before replace** | `deploy.sh:345-346` builds images as a separate step before `up`, so a failed build leaves the previous release serving | A broken build can stop a working service |
| **Migrate exactly once, and verified** | `deploy.sh:358-372` runs `up -d --remove-orphans` and then asserts `migrate` is `exited` with exit code `0`, dumping its last 200 log lines otherwise | A migration failure is discoverable only by reading `docker compose ps` by hand |
| **No volume is ever removed** | `deploy.sh:32-34` states it and `tests/unit/test_vm_deploy_script.py` asserts it: `docker compose down -v` cannot appear in the file | Nothing structural stops the one command that discards the database |
| **A bounded health suite gates success** | `deploy.sh:430-441` runs `scripts/compose_health.sh --wait --timeout` with `SMARTMATCH_RELEASE` set to the deployed SHA | "It came up" replaces "it is serving the code we deployed" |
| **Automatic application rollback** | `deploy.sh:375-419` checks out the previous SHA, rebuilds, re-runs health, records the result — and still exits non-zero so the job fails even though the VM recovered | A failed deployment leaves the failure serving until a human notices |
| **The deployed SHA is recorded** | `deploy.sh:215-222` writes `SMARTMATCH_RELEASE=<sha>` to `${STATE_DIR}/release.env`, which `scripts/vm/smartmatch.service:36` reads on boot and `docker-compose.vm.yml:46-54` feeds to the API | `/api/health` cannot answer "which commit is this", which is the situation the VM is in today |
| **A redacted log and machine-readable metadata per deployment** | `deploy.sh:107-115` filters anything credential-shaped out of everything printed; `deploy.sh:194-209` writes a JSON file recording outcome, failure stage, previous and deployed SHA, backup file, and whether it rolled back | No deployment history beyond shell scrollback |

Two properties are *not* on that list and should not be claimed for either path.
The script never downgrades a migration and never restores the backup it takes
(`deploy.sh:41-54`) — the rollback is an application rollback against an
already-migrated schema. And nothing in either path reaches the VM from the
public internet; both go through IAP.

### The two options

**Option A — correct the runbook to match the machine.** Accept the
home-directory checkout on `main`, hand-run deployments over IAP, and no
automatic gate. Demote the `/opt/smartmatch` design in this document to a
recorded intent, make `classroom-vm-cloudflare-tunnel.md` the layout of record,
and treat the properties in the table above as knowingly absent for a synthetic
pilot carrying no real data. Cheapest, and it leaves an unbacked-up migration
path on a machine a stakeholder is looking at.

**Option B — bootstrap the machine to match the runbook.** Run
`scripts/vm/bootstrap_vm.sh` on the instance to create `/opt/smartmatch`, its
`smartmatch` service user, and its `backups/`, `logs/` and `deployments/`
directories; install the deploy key read-only; move the existing database volume
onto that layout; install `scripts/vm/smartmatch.service`; create the Workload
Identity pool, provider and deployment service account; and fill the six
`pilot-vm` variables and two Cloudflare Access secrets. Every property in the
table then applies to every deployment, and pushing to `deploy` means something.
Costs real setup work in GCP, plus a database move between two locations on the
same disk — itself an operation that wants a backup first.

Some of the work is shared either way: naming the instance and zone correctly in
these documents, and deciding whether `/api/health` should report a commit SHA
on this machine, are worth doing under Option A too.

**What must not happen is a third state where the documents describe Option B
and the machine runs Option A without saying so.** That is the state this
section exists to end, and it is the one that produced a green-looking workflow
badge over a deployment that deployed nothing.

Nothing in this repository has been deleted or disabled to write this.
`scripts/vm/deploy.sh`, the `deploy` branch, and `.github/workflows/deploy.yml`
are all intact and are all correct code for the machine they describe.
`origin/deploy` exists and is an ancestor of `origin/main`, five commits behind
it as of this writing, so the branch is real and merely stale rather than
abandoned. The gap is not a defect in any of those three artifacts; it is a
bootstrap step that was never performed.

---

## The intended design (not bootstrapped)

Everything from here to the end of this document describes the `/opt/smartmatch`
design under Option B. It is accurate as a specification of what
`scripts/vm/bootstrap_vm.sh`, `scripts/vm/deploy.sh`,
`scripts/vm/smartmatch.service` and `.github/workflows/deploy.yml` do, and it is
what a reader should follow if the decision above lands on Option B. It is
**not** a description of the machine currently serving `pilot.plated.blog` — for
that, see
[What is actually on the VM today](#what-is-actually-on-the-vm-today).

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
