# Container images

**Scope:** how to build and run the two service images, what configuration each
reads, and what is deliberately absent.

Nothing here is deployed, and nothing in this document should be read as a claim
that either service is production-ready. The migration contract sets
`ALLOW_CLOUD_DEPLOY=false`. What these images provide is a packaging artifact
that is *exercised* — built, started, and probed in CI — rather than assumed to
work.

---

## Building

```
docker build -f Dockerfile.api    -t smartmatch-api:local    .
docker build -f Dockerfile.worker -t smartmatch-worker:local .
```

Both images are ~354 MB. They are near-identical by design; the differences are
marked `DIFFERENCE n of 3` in `Dockerfile.worker` and amount to which service
package is installed, which module is imported, and which health path is probed.

## Running

`PORT` selects the listening port and defaults to 8080. Cloud Run supplies it,
so nothing may assume a fixed port.

```
docker run --rm -p 8080:8080 smartmatch-api:local
docker run --rm -p 8081:8080 smartmatch-worker:local
```

| Service | Health endpoint | Response |
|---|---|---|
| API | `GET /api/health` | `{"status":"ok","release":"dev"}` |
| Worker | `GET /health` | `{"status":"ok"}` |

The API's health response carries a release identifier and deliberately no
dependency or topology detail — not the database host, not the queue, not which
providers are configured (v1.1 §1.11). Readiness, which does check dependencies,
is a separate private endpoint and is not part of the public surface.

## Configuration

Every setting is read from a `SMARTMATCH_`-prefixed environment variable at
startup (`services/api/smartmatch_api/config.py`). **None is required** to start
the scaffold: the defaults run against fixtures and a local database, which is
the only safe default.

| Variable | Default | Notes |
|---|---|---|
| `SMARTMATCH_EDITION` | `dev` | `classroom` triggers boot-time isolation validation |
| `SMARTMATCH_DATABASE_URL` | local PostgreSQL | Not read by the health endpoints |
| `SMARTMATCH_USE_FIXTURE_PROVIDERS` | `true` | Stays true until the corresponding release gate opens |
| `SMARTMATCH_RELEASE` | `dev` | Identifies a running instance without exposing topology |
| `PORT` | `8080` | Supplied by Cloud Run |

Configuration arrives at run time, never at build time. That is what allows one
image to be correct in more than one environment; an image with configuration
baked in is unsafe to move between them.

A classroom edition that carries a provider credential, or that has fixture
providers disabled, **fails to boot** rather than failing closed later under
load. That is deliberate: finding a credential in a classroom environment is a
deployment defect, not something to tolerate.

---

## The local scheduler and loopback task queue (compose only)

`docker-compose.yml` adds a `seed` one-shot service, a `scheduler` sidecar, and
five new environment variables so that a queued import can be driven to
completion on a developer's machine with **no manual dispatch step**. This
section documents that mechanism in full: what each piece is, every setting it
reads, how it fails, and — repeatedly, because this is the point most likely
to be misread — what it is not.

**This is a developer appliance. It is not a cloud queue, and it is not an
institutional pilot deployment.** Nothing described here is provisioned,
scanned, signed, monitored, or reachable from outside one developer's own
compose network. `ALLOW_CLOUD_DEPLOY=false` is unaffected by any of it.

### Why this exists

Before this addition, exercising `POST /operations/dispatch` on the compose
worker required a human to run a dispatch curl by hand after every import —
the worker's task and dispatch endpoints are unauthenticated infrastructure
until real OIDC verification lands (finding S-001), so they were reachable but
nothing ever called them automatically. The `scheduler` sidecar removes that
manual step by playing the part Cloud Scheduler will eventually play: it calls
`POST /operations/dispatch` on a fixed interval, the same route Cloud
Scheduler is designed to call, so the compose stack exercises the real
worker-side dispatch boundary rather than bypassing it.

### The pieces

| Piece | What it is | What it is not |
|---|---|---|
| `seed` service | A one-shot container running `tools/seed_pilot.py` against the API image, creating one synthetic `coordinator` principal and org unit so the smoke path in `INSTALL.md` has something to authenticate as and import into. | Not an account system. Refuses to run unless `SMARTMATCH_EDITION=dev` and `SMARTMATCH_USE_FIXTURE_PROVIDERS=true` (the script's own gate). |
| `SMARTMATCH_DEV_PRINCIPALS` (API) | Maps one fixed bearer token to the subject `seed` created, via `FixtureTokenVerifier`. Boot-time validation (`services/api/smartmatch_api/config.py`) refuses to start with this set under any edition but `dev`. | Not authentication. No password, no expiry, no revocation — a finite, explicitly configured set of test principals only. |
| `SMARTMATCH_DEV_TASK_BEARER_TOKEN` / `SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN` (worker) | Two separate dev-only bearer verifiers, one for `POST /tasks/execute`, one for `POST /operations/dispatch`. Deliberately different values — the worker refuses startup if they are equal, and refuses either being set under an edition other than `dev`. | Not a substitute for Cloud Tasks/Cloud Scheduler OIDC (`task_audience`, `scheduler_audience`, and the two service-account allowlists, all still unset here — see the `worker` service comment in `docker-compose.yml`). Those stay unconfigured and therefore fail-closed (401/501) in this stack, exactly as they do without any of this addition. |
| Loopback task queue (`SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED`, `SMARTMATCH_LOCAL_TASK_TARGET_URL`) | A `LocalPostgresHttpTaskQueue` inside the worker process. `enqueue()` does not deliver anything itself — it only validates that the durable outbox row is already committed `dispatched`. A separate delivery pump then reads that committed row and `POST`s `{tenant_id, job_id}` back to the worker's own `/tasks/execute`, using the task bearer token above. | Not `FixtureTaskQueue` (which loses work in process memory) and not a call directly into `TaskExecutor` — delivery goes over the real HTTP boundary, through the real verifier, exactly as Cloud Tasks would call it. Not Cloud Tasks: no durability guarantee beyond "this one PostgreSQL row committed", no retry-with-backoff policy beyond what the pump implements, and it accepts no tenant-controlled URL, header, or credential — the target is fixed at `http://127.0.0.1:<PORT>/tasks/execute`. |
| `scheduler` service (`SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN`) | A sidecar built from `Dockerfile.worker`, running `python -m smartmatch_worker.local_scheduler`. Every two seconds it `POST`s to the fixed compose address `http://worker:8080/operations/dispatch` using the scheduler bearer token. Exits without sending a request unless `SMARTMATCH_EDITION=dev` and its own token are both set. | Not Cloud Scheduler. No job is provisioned, no OIDC token is minted, nothing here is reachable outside this compose network, and its target address is a hardcoded module constant, not something an environment variable can redirect. |

### The flow, end to end

```
scheduler sidecar
  -> POST /operations/dispatch [scheduler bearer token]
  -> ScheduledPass (the real dispatcher composition: J9 sweep + J12 reclaim + J1 dispatch)
  -> LocalPostgresHttpTaskQueue.enqueue() validates the row is already committed dispatched
  -> delivery pump reads that durable PostgreSQL row
  -> POST /tasks/execute [task bearer token — a DIFFERENT value from the scheduler token]
  -> worker creates review_item row(s)
  -> API reads pending_review_items via GET /v1/units/{unit_id}/metrics
```

The queue never delivers ahead of the durable commit: `enqueue()` only
validates that PostgreSQL already shows the row `dispatched`, so a synchronous
"deliver during enqueue" race — which would repeatedly see the row not yet
committed and answer `503` — cannot happen. This mirrors why the real
production design (Cloud Tasks after the dispatcher's own transaction commits)
is shaped the way it is; the loopback queue keeps that ordering rather than
shortcutting it.

### Failure behavior

Every one of these failure directions is fail-closed, matching the existing
worker posture (`POST /tasks/execute` → `401` without credentials, `501` with
credentials but no queue) rather than introducing a new permissive path:

- Either dev bearer token configured outside `SMARTMATCH_EDITION=dev` fails
  the worker or API at **startup**, not at request time.
- The task and scheduler bearer tokens configured equal to each other fails
  worker startup — a task-scoped credential and a dispatch-scoped one must
  stay distinguishable, the same reason Cloud Tasks and Cloud Scheduler use
  separate audiences in the real design.
- `SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED=true` without a task bearer token, or
  without `SMARTMATCH_LOCAL_TASK_TARGET_URL`, fails startup rather than
  silently running with a partial local configuration.
- `SMARTMATCH_LOCAL_TASK_TARGET_URL` supplied while the queue is disabled
  fails startup as contradictory configuration, rather than being silently
  ignored.
- The target URL must be plain `http`, host `127.0.0.1` or `::1`, path
  exactly `/tasks/execute`, with no userinfo, query, fragment, or redirect
  following — anything else fails startup.
- The delivery pump retries connection errors and `5xx` while the durable job
  stays `dispatched`. It treats `401`, `403`, `400`, `404`, and `501` as
  configuration/contract errors: it logs clearly and leaves the job visible
  rather than fabricating a completion it did not actually reach.
- The `scheduler` sidecar retries network errors and `5xx` on its own POST,
  exits on an authentication or configuration response, never logs the
  bearer token, and stops cleanly on `SIGTERM`.
- `seed` refuses to run — and prints why on stderr — unless
  `SMARTMATCH_EDITION=dev` and `SMARTMATCH_USE_FIXTURE_PROVIDERS=true`, and it
  refuses (rather than silently changing) an existing tenant, org unit,
  account, or membership that disagrees with the identity it was asked to
  seed.

### The loopback restriction, restated

`SMARTMATCH_LOCAL_TASK_TARGET_URL` cannot be pointed anywhere but this
worker's own `127.0.0.1`/`::1`. That is not an oversight to relax later — a
local task queue that could be redirected to an arbitrary host, with a
tenant- or caller-controlled URL, path, header, or credential, would be a
server-side request forgery primitive wearing a developer-convenience
costume. The restriction stays even though nothing in this compose network is
reachable from outside the developer's own machine, because the code path is
the same code path a future misconfiguration could expose.

### Process and restart behavior

`seed` and `migrate` are one-shot: they run to completion and exit, and
`restart: "no"` means a crash leaves them stopped rather than retried in a
loop. `api`, `worker`, and `scheduler` are long-lived. The `scheduler` sidecar
has no restart policy of its own in `docker-compose.yml` — like `api` and
`worker`, an unhandled crash simply stops the container; `docker compose up`
again restarts the whole appliance if that happens. None of the three
long-lived containers persist any queue state of their own: every durable fact
the loop above depends on lives in the `db` service's `outbox_record` and
`job` tables, which is what makes `docker compose down -v` a clean reset
rather than one that could leave a task queue holding stranded work no
container remembers.

---

## The decisions worth explaining

### The dependency install is two steps, not one

`--require-hashes` is all-or-nothing: it demands a recorded hash for *every*
requirement in the invocation. A local source directory has no published
artifact and therefore no hash, so adding the four workspace packages to the
hash-verified command makes it fail outright. The only ways to make a single
command pass are to drop the flag or to invent a hash — both of which remove the
control from the dependencies that legitimately have one.

So third-party dependencies install from `requirements/runtime.txt` with
`--require-hashes` (the same control as `make setup` and CI, security finding
S-003), and the workspace packages install separately with `--no-deps`.
`--no-deps` matters: the dependency set is already installed exactly, and
letting pip resolve again could pull an unpinned replacement to satisfy a
version range.

### The workspace packages are installed non-editable

`make setup` installs them with `-e` so local edits take effect immediately.
That is a development affordance. An editable install is a `.pth` file pointing
at a source tree, which in an image means the source tree has to ship and the
installed package changes silently if anything mutates it. A shipped artifact
contains built packages.

### `CMD` is exec-form invoking `sh -c ... exec`

Not the same as shell-form `CMD`. Shell form leaves `/bin/sh` as PID 1, and the
shell forwards nothing — SIGTERM on a rolling restart never reaches uvicorn, the
container survives until the grace period expires, and every in-flight request
is killed. The `exec` replaces the shell with uvicorn so uvicorn *is* PID 1. The
shell is needed for exactly one thing: expanding `${PORT}`, which exec form
cannot do.

No `--reload` (a development affordance that also breaks signal handling) and no
`--workers`: concurrency is a Cloud Run service setting and scaling is
horizontal, so a second process per container competes for the same CPU
allocation and doubles the connection pool for nothing.

### The base image is pinned by digest

A tag is a moving pointer; `python:3.11-slim-bookworm` names a different image
every few weeks. A build pinned to a tag is not reproducible, and a compromised
or merely broken upstream rebuild is picked up silently. The readable tag stays
in a comment beside the digest.

### The virtualenv is root-owned and the process is not root

The application user (uid 10001) can read and execute `/opt/venv` but cannot
write to it, so a process compromise cannot rewrite an installed package and
persist across a restart. The only directory the user owns is its home. The uid
is numeric and fixed because the number is what the kernel and any mounted
volume actually see.

---

## Verified behavior

Checked against the built images, not read off the Dockerfiles:

| Property | Result |
|---|---|
| API health | `200` · `{"status":"ok","release":"dev"}` |
| Worker health | `200` · `{"status":"ok"}` |
| Runs as non-root | `uid=10001(smartmatch) gid=10001(smartmatch)` |
| Virtualenv immutable to app user | `touch /opt/venv/CANARY` → `Permission denied` |
| No environment file or credential in the image | none found |
| Worker still fails closed | `POST /tasks/execute` → `401` without credentials, `501` with |
| Graceful shutdown on SIGTERM | API stopped in 1s, worker in 0s, clean shutdown log |

That last pair matters most. The worker's task endpoint is unauthenticated
infrastructure until real OIDC verification lands (security finding S-001), and
it must fail closed *inside a container* and not only under pytest — the
container is what would actually run. And the SIGTERM result is what
distinguishes a correct `CMD` from the shell-form mistake, which no functional
test would catch.

`.github/workflows/build.yml` asserts all of these on every build, plus two
this table does not cover: that no development tooling or test suite leaked into
the runtime stage, and that no `.git` directory reached the image.

---

## Deliberately absent

| Absent | Why | Introduced |
|---|---|---|
| Image publication to a registry | No destination exists or is owned, and no credential binding has been decided | When a registry and a release policy exist |
| Deployment | `ALLOW_CLOUD_DEPLOY=false` | Not scheduled here |
| Image scanning, signing, provenance attestation | Listed as before-scale (R3+) gates | R3 |
| A database in the build | The health endpoints do not touch one; a container cannot reach the host's `localhost` anyway | — |

`build.yml` authenticates to nothing, tags for no registry, pushes nowhere, and
requests no permission beyond `contents: read`. The reasoning, and the
conditions that would have to be met before a push step belongs there, are
recorded in that file's header rather than duplicated here.
