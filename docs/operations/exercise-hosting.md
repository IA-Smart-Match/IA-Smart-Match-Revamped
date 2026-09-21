# Hosting the class exercise on the pilot VM

**Last updated:** 2026-09-21
**Scope this document covers:** `SMARTMATCH_PRODUCT_SCOPE=class_exercise`
**Sibling of:** [`vm-deploy.md`](vm-deploy.md), which covers the CBA appliance
and is unchanged by anything here.

Design spec §17 asks for "a stable address on the pilot VM path running with
`SMARTMATCH_PRODUCT_SCOPE=class_exercise`". This file is the operator procedure
for that. It makes **no production-readiness claim**: `ALLOW_CLOUD_DEPLOY=false`
still holds, and the gates in [`vm-deploy.md`](vm-deploy.md)'s "Before any of
this becomes production" are all still open.

**A separate file rather than a section of `vm-deploy.md`, because
`docs/operations/` is already one-file-per-topic** —
`classroom-vm-cloudflare-tunnel.md`, `pilot-dataset-rebuild.md`,
`deploy-runbook.md`, `containers.md` — and `vm-deploy.md` is past 1,000 lines
about a different product scope. The two link to each other.

**The hostname is not decided.** Everywhere below, `<EXERCISE_HOST>` is a
**PLACEHOLDER (OQ-CE-06)**. The owner's decision of 2026-09-21 fixes the
*shape* — a **subdomain on the pilot VM**, its own origin, so an exercise cookie
is never sent to a CBA route — and not the name. Do not substitute a real
hostname into this file; substitute it in your shell.

---

## Read this first: three things you cannot do today

| Gap | Why | Consequence |
|---|---|---|
| **No compose service runs this scope** | `SMARTMATCH_PRODUCT_SCOPE` appears in **no** `.yml` file in this repository (verified by grep across `docker-compose.yml`, `docker-compose.vm.yml`, `docker-compose.demo.yml`) | There is no second `api` service to start. Standing the exercise up needs a compose change that is **not** in this repository yet. No YAML is invented here. |
| **The Vite dev server rejects a new hostname** | `apps/web/legacy-frontend/vite.config.ts:53` sets `allowedHosts: ["pilot.plated.blog"]` and nothing else | `<EXERCISE_HOST>` served through that dev server answers **"Blocked request"** until the host is added there. That is a code change, owned by the frontend track. |
| **No proxy rate-limit config is in the repository** | The only documented front door is a dashboard-managed Cloudflare Tunnel (`vm-deploy.md:78-87`); there is no nginx/Caddy/Traefik config checked in | The per-client limit for the instructor login has to be built in the Cloudflare dashboard by hand, and cannot be reviewed in git. See [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06-open). |

Everything below is still worth doing in order; step 1 tells you what the
process must be, and the gaps tell you what you must build to get one.

---

## 1. What runs

### One process per scope, not a flag on the CBA one

`SMARTMATCH_PRODUCT_SCOPE` is read once at process start
(`services/api/smartmatch_api/config.py:36-40` sets `env_prefix="SMARTMATCH_"`;
`:57` declares the field) and decides the **route table** of that process
(`services/api/smartmatch_api/main.py:318-654`). It is not a per-request
switch and cannot be one. So the exercise is a **second API process** —
its own container, its own port — beside the CBA API, not a toggle on it.

Set it to the literal `class_exercise`
(`python/smartmatch_domain/smartmatch_domain/product_scope.py:107`). Unset
means `cba` (`product_scope.py:112`), which serves **no exercise route at all**.

### Which routers this scope mounts

Seven, all under `/v1/exercise`, all gated on `Capability.CLASS_EXERCISE`:

| Router | Prefix | Mounted at |
|---|---|---|
| `exercise_public` | `/v1/exercise` | `main.py:593` |
| `exercise_workspace` | `/v1/exercise` | `main.py:603` |
| `exercise_instructor.login_router` | `/v1/exercise/instructor` | `main.py:622` |
| `exercise_instructor.router` | `/v1/exercise/instructor` | `main.py:623` |
| `exercise_matching` | `/v1/exercise/workspaces/current` | `main.py:635` |
| `exercise_results` | `/v1/exercise/workspaces/current` | `main.py:647` |
| `exercise_instructor_refresh` | `/v1/exercise/instructor` | `main.py:654` |

### No CBA authenticated router is registered

ADR-0025 D1, implemented at `main.py:281-315`: the five principal-bearing
infrastructure routers (`jobs`, `redrive`, `engagement`, `review.router`,
`review.unit_router`) ride `Capability.AUTHENTICATED_LOGIN`, which this scope
does not have. `get_current_principal` is **unreachable**, not bypassed — and
`app.state.token_verifier` is set to `None` rather than left unset
(`main.py:230-239`), so nothing is sitting on the app state waiting to be
misused. Every CBA route answers 404 in this process.

`make imports` enforces the other half: an exercise router may not import
`smartmatch_authz` or any tenant-scoped repository (ADR-0025 D2).

---

## 2. Environment variables

| Name | Required? | Example shape (never a real value) | What breaks when missing |
|---|---|---|---|
| `SMARTMATCH_PRODUCT_SCOPE` | **Yes** | `class_exercise` | Defaults to `cba`. Every `/v1/exercise/...` path answers **404** and the process silently serves the wrong product. |
| `SMARTMATCH_EXERCISE_WORKSPACE_SECRET` | **Yes** | 43 URL-safe chars from `token_urlsafe(32)` | **The process does not boot.** `main.py:696-697` calls `require_exercise_workspace_secret` at import; `config.py:268-283` raises, naming the variable and the length and quoting no part of the value. Minimum **32 characters** (`workspace_token.py:87`). |
| `SMARTMATCH_EXERCISE_COOKIE_SECURE` | **Yes on the HTTPS VM** (owner decision, 2026-09-21) | `true` | Unset, the *workspace* cookie follows the edition — off in `dev` — and `docker-compose.vm.yml` pins `SMARTMATCH_EDITION=dev` while the site is HTTPS, so the classroom's cookie ships **without `Secure`** (`exercise_dependencies.py:346-359`). The *instructor* cookie defaults to `Secure` regardless (`:452`). |
| `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` | No — but the instructor page is shut without it | 16+ characters, owner-supplied | Unset (or unusable) means every instructor login attempt is refused with the same sentence a wrong passcode gets (`exercise_dependencies.py:498-516`). Team routes keep working — deliberately, so a missing passcode cannot take a classroom down. |
| `SMARTMATCH_DATABASE_URL` | **Yes** | `postgresql+psycopg://<EXERCISE_DB_ROLE>:<EXERCISE_DB_PASSWORD>@db:5432/smartmatch` | No database. Point it at the **restricted role** from [§3](#3-the-database-role), not at the owner role. |
| `SMARTMATCH_DB_HIDE_PARAMETERS` | Leave **empty** | *(empty)* | Empty means hidden, which is the default and the only correct value on a shared host. Setting `false` puts every bound value of every failed statement — including the withheld "true interests" column, ADR-0025 D6 — into the server log (`engine.py:236`, `.env.example:82-104`). |

### Generating the two secrets

```bash
# Workspace secret. 32-char minimum is enforced; token_urlsafe(32) gives 43.
python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Instructor passcode. 12-char minimum after stripping; 16 bytes is comfortable.
python -c 'import secrets; print(secrets.token_urlsafe(16))'
```

The passcode floor is `MINIMUM_INSTRUCTOR_PASSCODE_LENGTH`, which is
`MINIMUM_PASSWORD_LENGTH = 12`
(`instructor_session.py:112`, `pilot_credentials.py:114`). The value is
**stripped before it is measured and before it is compared**
(`instructor_session.py:137-160`), so a trailing newline pasted into a deploy
console does not become a permanent lockout — but a value that is long enough
only *before* stripping is refused.

### Sharing and rotating the passcode — OQ-CE-07, OPEN

The register's safe default, restated at `config.py:146-148`: **one environment
variable per deployment, shared out of band and rotated after the spring run.**
Out of band means not in this repository, not in a ticket, not in a chat
channel that outlives the class. Rotation is: change the variable, restart the
exercise API process. Live instructor sessions are **not** ended by a passcode
rotation — they are signed with the workspace secret, not the passcode.

### What rotating the workspace secret does

It is the blunt instrument that stands in for revocation (`.env.example:159-165`):

1. **Every team's cookie stops working.** A team re-enters its team number and
   gets the same workspace back — the workspace row is keyed on
   `(dataset_id, team_number)`, not on the cookie.
2. **Every live instructor session dies**, because the session key is a
   labelled derivation of the same secret
   (`instructor_session.py:117-118`).

That is the only lever. There is no per-session revocation — see
[§8](#8-known-limits).

---

## 3. The database role

Owner decision, 2026-09-21: a **dedicated role with `GRANT` on `exercise_*`
tables only**. This is the real ADR-0025 D2 control — the import-linter rule
stops an exercise router from *importing* a tenant-scoped repository; this stops
the process from *reading a CBA table at all*, whatever code it runs.

**Migrations do not run as this role.** Alembic revision `0037` calls
`op.create_table` eight times (`db/migrations/versions/0037_exercise_tables.py`
lines 116, 138, 171, 193, 243, 272, 307, 346) and needs `CREATE` on the schema,
which this role must never have. Run `migrate` as the owner role
(`smartmatch`), exactly as the compose stack already does; the runtime role only
reads and writes rows.

### The grant

Run as the database owner. `smartmatch` is the database and the owner role in
`docker-compose.yml:211-213`.

```sql
-- 1. The role. Password comes from your secret store, never from this file.
CREATE ROLE "<EXERCISE_DB_ROLE>" LOGIN PASSWORD '<EXERCISE_DB_PASSWORD>';

-- 2. Reach the database and see the schema. No CREATE.
GRANT CONNECT ON DATABASE smartmatch TO "<EXERCISE_DB_ROLE>";
GRANT USAGE  ON SCHEMA   public       TO "<EXERCISE_DB_ROLE>";

-- 3. Exactly the privileges the code uses, per table.
GRANT SELECT, INSERT, UPDATE         ON exercise_dataset         TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT                 ON exercise_profile         TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT                 ON exercise_event           TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, UPDATE, DELETE ON exercise_team_workspace  TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, DELETE         ON exercise_profile_overlay TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, DELETE         ON exercise_saved_setting   TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, DELETE         ON exercise_result_run      TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT                 ON exercise_result_unlock   TO "<EXERCISE_DB_ROLE>";
```

Where each privilege comes from, so the list can be re-derived rather than
trusted:

| Table | Statements in `smartmatch_persistence/exercise/` |
|---|---|
| `exercise_dataset` | `sa.insert`, `sa.update` (`dataset_repository.py`) |
| `exercise_profile`, `exercise_event` | `sa.insert` only — ingest writes them once |
| `exercise_team_workspace` | `pg_insert ... on_conflict_do_nothing` (`workspace_repository.py:272-282`), `sa.update` (`:541-544`), `sa.delete` on re-point (`instructor_repository.py:699-702`) |
| `exercise_profile_overlay`, `exercise_saved_setting`, `exercise_result_run` | `insert`, plus `sa.delete` in the reset walk (`workspace_repository.py:535-540`, `instructor_repository.py:531-535`) |
| `exercise_result_unlock` | `pg_insert ... on_conflict_do_nothing` (`instructor_repository.py:459-466`) — no `UPDATE` |

**No sequence grants are needed.** Every primary key is a `UUID` the
application generates or a natural composite key — `schema.py:119`, `:235`,
`:343`, `:386` are `sa.Column("id", _UUID, primary_key=True)` with no server
default, and the other four tables use composite `PrimaryKeyConstraint`s
(`0037_exercise_tables.py:155`, `:180`, `:254`, `:352`). There is no `SERIAL`,
no `IDENTITY` and no `CREATE SEQUENCE` in the revision.

### Prove the role cannot read a CBA table

Connect **as the new role** and run this. It must fail.

```sql
-- Expect: ERROR: permission denied for table user_account
SELECT count(*) FROM user_account;
```

And this, which lists every table the role can read — the result must contain
only `exercise_` names:

```sql
SELECT table_name
FROM information_schema.table_privileges
WHERE grantee = '<EXERCISE_DB_ROLE>' AND privilege_type = 'SELECT'
ORDER BY table_name;
```

If a non-`exercise_` name appears, a `GRANT ... ON ALL TABLES IN SCHEMA public`
was run somewhere. Revoke it; the per-table list above is the whole grant.

---

## 4. HTTPS and cookies

Two cookies, both set from one policy dataclass with different name and path
(`exercise_dependencies.py:328-453`):

| Cookie | Name | Path | `HttpOnly` | `SameSite` | `Secure` |
|---|---|---|---|---|---|
| Team workspace | `exercise_workspace` | `/v1/exercise` | `true` | `lax` | from `SMARTMATCH_EXERCISE_COOKIE_SECURE`; unset falls back to "edition is not dev" |
| Instructor session | `exercise_instructor` | `/v1/exercise/instructor` | `true` | `lax` | from the same variable; unset defaults to **`true`** |

Both are session cookies — no `max_age`, no `expires`
(`exercise_workspace.py:180-190`, `exercise_instructor.py:333-342`). The
instructor path is deliberately **narrower**, so a team's browser on a matching
screen never carries the instructor cookie.

`SameSite=Lax` is the first cross-site defence. The second is the
`X-Exercise-Request` header, required on every state-changing exercise route
(`exercise_dependencies.py:240-256`): a cross-origin page cannot add a custom
header without a CORS preflight, and this application configures no permissive
CORS.

### The frontend must call `/v1/exercise/...` literally

A cookie with `Path=/v1/exercise` is sent **only** to request paths under
`/v1/exercise`. A frontend that calls `/api/v1/exercise/...` — or any other
prefix — gets **no cookie**, and every authenticated-by-cookie route answers as
if the team had never entered. The failure looks like "the app logged me out",
not like a routing bug.

So the reverse proxy in front of `<EXERCISE_HOST>` must route, to the exercise
API process:

* `/v1/exercise` and everything under it — **without rewriting the path**;
* the static frontend for everything else.

The existing Vite dev server already proxies `/v1` unrewritten to the API
(`vite.config.ts:62-67`), which is the shape to copy. What it does **not** have
is `<EXERCISE_HOST>` in `allowedHosts` (`vite.config.ts:53`) — see the gaps
table at the top.

---

## 5. Rate limiting belongs at the proxy (OQ-CE-06, OPEN)

The instructor login has an in-process limiter today, and it is a **marked
placeholder** (`services/api/smartmatch_api/exercise_rate_limit.py:1`, whose
first line is the word `PLACEHOLDER`). What it is:

* 10 attempts per client address per 5-minute window
  (`exercise_rate_limit.py:74`, `:85`);
* 60 attempts across all callers per window (`:82`);
* at most 1,024 tracked addresses, oldest window evicted (`:89`).

What it is **not**:

* **Not shared between processes.** Two API workers are two counters; N workers
  multiply the allowance by N.
* **Not durable.** A restart forgets every counter.
* **Not a sliding window.** A caller can spend a full allowance at the end of
  one window and another at the start of the next.
* **Not proxy-aware.** It reads the socket's client address and parses **no**
  `X-Forwarded-For` (`exercise_rate_limit.py:35-41`). Behind a proxy, every
  request looks like one client — the proxy — so the per-client bound collapses
  into the global one.

That last point is the requirement: **per-client rate limiting has to happen at
the reverse proxy**, because the proxy is the only hop that knows the real
client address.

**The configuration is a gap.** The only front door documented for this VM is a
Cloudflare Tunnel whose hostname mapping is dashboard-managed and checked into
nothing (`vm-deploy.md:78-87`). There is no nginx, Caddy or Traefik config in
this repository to add a `limit_req` zone to. So the requirement, stated so it
can be built and reviewed by hand:

| Setting | Value | Why |
|---|---|---|
| Path | `POST <EXERCISE_HOST>/v1/exercise/instructor/login` | The one unauthenticated guessing surface |
| Counting key | client IP | The app cannot do this; the proxy can |
| Budget | 10 requests / 5 minutes / IP | Matches `INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT` so the two bounds do not disagree |
| Action | block, with the same refusal the app gives | A different response teaches an attacker where the limit lives |

In Cloudflare terms that is a **Rate Limiting Rule** on the Zero Trust/WAF side
for that hostname and path. It cannot be expressed in this repository today, and
this document does not pretend otherwise. OQ-CE-06 stays **OPEN**; when it is
answered, `exercise_rate_limit.py` is deleted and the dependency comes off the
route, which the module's own docstring already anticipates.

---

## 6. Performance budget

Design spec §17: **under 5 seconds to first interactive in Chrome on a
classroom machine, measured on the deployed address, not locally.**

**No claim is made here that this passes.** It has not been measured.

How to measure:

1. On a **classroom machine** (not a developer laptop), open Chrome.
2. DevTools → **Performance** → check *Disable cache*, throttling **No
   throttling** (the classroom network is the condition under test, not a
   simulated one).
3. Load `https://<EXERCISE_HOST>/` from a cold profile. Record **Time to
   Interactive** from the trace summary.
4. Repeat three times; record all three, not the best one.
5. Record the Chrome version and the machine, because the number means nothing
   without them.

Where to record it: the table below, in this file, as a dated row. A number in
a chat message is a number nobody can find in March.

| Date | Address | Machine / Chrome version | TTI run 1 / 2 / 3 | Under 5 s? |
|---|---|---|---|---|
| — | — | — | **not measured** | **unknown** |

Two things already known to affect it, so they are not a surprise on the day:
the frontend on this VM is a **Vite dev server with the checkout bind-mounted**,
not a production bundle (`vm-deploy.md:341-366`), and a dev server's first load
is not a built bundle's first load.

---

## 7. Day-of-class runbook

All seven steps are instructor-page actions; every one needs a live instructor
session (the passcode) and sends `X-Exercise-Request`.

1. **Upload the data file.** `POST /v1/exercise/instructor/datasets` with a raw
   `text/csv` **body** — `Content-Type: text/csv`, the file's bytes, **no
   multipart form** (`exercise_instructor.py:373-383`, owner decision
   2026-09-21). Do this before the room fills; it creates the dataset every
   later step is keyed on.
2. **Confirm the teams.** `GET /v1/exercise/instructor/workspaces`
   (`exercise_instructor.py:615-616`) lists the teams that have entered. Teams
   are **1-6** — a CHECK constraint, not a convention
   (`ck_exercise_team_workspace_team_number`). A team appears only after it has
   entered its number at `POST /v1/exercise/workspaces`.
3. **Unlock each event as it happens.** `POST
   /v1/exercise/instructor/events/{event_key}/unlock`
   (`exercise_instructor.py:557-558`), one per event, when the class reaches it.
   Unlocking twice is not an error — the insert is
   `on_conflict_do_nothing` and the route says the same sentence either way
   (`instructor_repository.py:459-466`).
4. **Refresh all, once, after the first round.** `POST
   /v1/exercise/instructor/refresh-all`
   (`exercise_instructor_refresh.py:90-91`). **All or nothing**: every team is
   refreshed in one transaction, so a refusal for one team rolls back all of
   them and nothing is half applied
   (`exercise_instructor_refresh.py:119-123`). Teams that have not chosen how
   to ask are not visited; teams that have already refreshed have had their
   one refresh. Pressing it again after a refusal starts from where it started.
5. **Reset one team if it needs it.** `POST
   /v1/exercise/instructor/workspaces/{team_number}/reset`
   (`exercise_instructor.py:690-691`). It deletes that workspace's overlay,
   saved settings and result runs and regenerates its seed
   (`workspace_repository.py:526-545`). **One team, and nothing else** — there
   is no team-facing reset; PR #186 removed it on the owner's ruling of
   2026-09-19.
6. **Expect the results screen to refuse.** While **OQ-CE-03** is open the
   simulated-results rule ships no coefficients, so `POST
   /v1/exercise/workspaces/current/events/{event_key}/results` answers **409**
   with one plain sentence:

   > The results rule has no confirmed coefficients yet (OQ-CE-03).

   (`simulation.py:421-422`, surfaced by `exercise_results_run.py:122-129`.)
   **This is expected, not a fault of the deployment.** Say so before the class
   presses the button. Everything upstream of results — entry, lists, saved
   settings, comparison, CSV export — works.
7. **Log out.** `POST /v1/exercise/instructor/logout`
   (`exercise_instructor.py:293-294`) clears the instructor cookie on that
   browser. It is the only clean end to a session — see the next section for
   what it is not.

---

## 8. Known limits

1. **No session revocation.** The instructor session is a stateless signed
   cookie with a **12-hour** TTL (`instructor_session.py:105`). Logging out
   clears the cookie in *that* browser; it does not invalidate the token. A
   copied cookie stays good until it expires. The only lever that ends every
   session everywhere is **rotating `SMARTMATCH_EXERCISE_WORKSPACE_SECRET`**,
   which also ends every team's cookie. Owner decision, 2026-09-21: this stands
   for the pilot.
2. **The login limiter is in-process.** Per process, per process lifetime,
   fixed windows, no `X-Forwarded-For` — see [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06-open).
   It is usable only because the VM runs one API container.
3. **`hide_parameters` does not suppress PostgreSQL's own `DETAIL:` line
   (B-11).** SQLAlchemy's `[parameters: ...]` is withheld, but a CHECK or NOT
   NULL refusal composes `DETAIL: Failing row contains (…)` server-side, which
   no SQLAlchemy setting can remove (`.env.example:100-103`). That is why the
   exercise repositories refuse to render the driver's exception at all and
   answer a fixed refusal sentence instead. **B-11 is recorded and unresolved**
   at [`docs/architecture/decisions/adr-backlog.md:250`](../architecture/decisions/adr-backlog.md).
4. **Connection pool: 20 + 10 per process, queueing at 30.** `DEFAULT_POOL_SIZE
   = 20`, `DEFAULT_MAX_OVERFLOW = 10`, `DEFAULT_POOL_TIMEOUT = 30` seconds
   (`engine.py:38`, `:46`, `:50`), all overridable by
   `SMARTMATCH_DB_POOL_SIZE` / `SMARTMATCH_DB_MAX_OVERFLOW` /
   `SMARTMATCH_DB_POOL_TIMEOUT` (`engine.py:206-208`). A request holds its
   connection for its whole lifetime, so **30 concurrent requests** is the
   ceiling for one process before callers queue for up to 30 seconds. Six teams
   fit comfortably. **The arithmetic that matters is the database's**: the
   `postgres:16` image default is `max_connections = 100`, and the existing API
   and worker already budget `(20+10) + (20+10) = 60` (`engine.py:25-37`).
   A *third* process at the same defaults takes that to 90 against a ceiling of
   100 minus 3 superuser-reserved. **Size the exercise process's pool down
   explicitly** — it serves six teams, not a campus — rather than letting it
   take the default.
5. **`web` is a dev server, so restart is not rebuild.** `web` has no `build:`
   stanza and bind-mounts the checkout (`vm-deploy.md:341-366`). A frontend
   change is live on `git checkout`; a *backend* change is not, which is why
   compose on this VM needs **both** `-f docker-compose.yml -f
   docker-compose.vm.yml` **and** `--build` (`vm-deploy.md:525-558`): omitting
   the override strips the restart policies, and omitting `--build` reuses stale
   images.

---

## 9. Open questions

| ID | Question | Status | Where it bites here |
|---|---|---|---|
| **OQ-CE-06** | "Where does the site live and what is its stable address?" — owner Danny. The 2026-09-21 decision fixes the *shape* (a subdomain on the pilot VM) and not the name, and `exercise_rate_limit.py` carries the same id for the edge-limiting half | **OPEN** | `<EXERCISE_HOST>` is unresolved everywhere in this file; the proxy rate-limit rule in [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06-open) cannot be checked into git |
| **OQ-CE-07** | "How is the instructor passcode set and shared with Ann and Dr. Lin?" — owner Danny + Ann | **OPEN** | [§2](#2-environment-variables) documents the register's safe default — one env var, out of band, rotated after the spring run — and closes nothing |
| **OQ-CE-09** | "What license line goes on the opening screen?" — owner Ann; none shown until she provides the sentence | **OPEN — by Nov 20** | Nothing in this document adds or removes a license line; the opening screen ships without one |
| **B-11** | "Error text never carries bound values" as a repository-wide invariant. PostgreSQL's `DETAIL: Failing row contains (…)` sits below the layer `hide_parameters` operates on | **RECORDED 2026-09-19, unresolved** — [`docs/architecture/decisions/adr-backlog.md:250`](../architecture/decisions/adr-backlog.md) | [§8](#8-known-limits) item 3 |

Also open and load-bearing for the runbook: **OQ-CE-03** (the simulation
coefficients), which is why step 6 of [§7](#7-day-of-class-runbook) expects a
refusal.

The register at
[`docs/plans/open-questions/class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md)
is the authority on every row above. This file records how each one shows up to
an operator; it does not decide any of them.
