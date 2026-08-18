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
