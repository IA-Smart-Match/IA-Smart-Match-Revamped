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

**The address: `exercise.plated.blog`** — owner decision, 2026-09-21
(OQ-CE-06, owner Danny). A **second public hostname on the existing Cloudflare
Tunnel**, serving the exercise scope only. Its own origin is the point: an
exercise cookie is scoped to that host and is never sent to a CBA route on
`pilot.plated.blog`, and vice versa.

**No Cloudflare Access policy is applied to it** — also the owner's decision of
2026-09-21, and the one thing here that differs from the sibling host. What
stands in for it is [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06). See
[§4a](#4a-the-tunnel-and-why-there-is-no-access-policy) for what that trades
away and why it is acceptable for this scope and not for the other one.

---

## Read this first: three things you cannot do today

| Gap | Why | Consequence |
|---|---|---|
| ~~No compose service runs this scope~~ **Closed.** | `docker-compose.exercise.yml` (a THIRD `-f` file, loaded only when named) defines an `api-exercise` service running `SMARTMATCH_PRODUCT_SCOPE=class_exercise`, gated behind the `exercise` compose profile, bound to `127.0.0.1:8090`, with its own restart policy and `SMARTMATCH_EXERCISE_COOKIE_SECURE=true` pinned in the same file. `docker-compose.yml` and `docker-compose.vm.yml` are untouched — an earlier version of this lived inside `docker-compose.yml` and broke `docker compose up` for the whole CBA stack (Compose evaluates required-secret interpolation for every service in a loaded file, profile or no profile). `tests/unit/test_exercise_compose_service.py` pins its shape. | Steps 7-10 and 18 of [§9](#9-deploy-and-verify-checklist) are runnable by an operator; see that section for the exact commands. |
| **The Vite dev server rejects `exercise.plated.blog`** | `apps/web/legacy-frontend/vite.config.ts:53` is `allowedHosts: ["pilot.plated.blog"]` — one host, and it is the other one | `exercise.plated.blog` served through that dev server answers **"Blocked request"**, exactly as `pilot.plated.blog` did before commit `d5ffcb05` fixed it there. `"exercise.plated.blog"` must be added to that array. Code change, frontend track. |
| **No proxy rate-limit config is in the repository** | The only front door is a dashboard-managed Cloudflare Tunnel (`vm-deploy.md:87-96`); there is no nginx/Caddy/Traefik config checked in | The per-client limit on the instructor login has to be built in the Cloudflare dashboard by hand, and cannot be reviewed in git. With no Access policy on this host, that rule is the **only** edge protection. See [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06). |

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
| `SMARTMATCH_EXERCISE_COOKIE_SECURE` | **Yes on the HTTPS VM** (owner decision, 2026-09-21) | `true` | Unset, the *workspace* cookie follows the edition — off in `dev` — and `SMARTMATCH_EDITION: dev` is pinned in the **base** compose file, at `docker-compose.yml:292` (`api`) and `:339` (`worker`), not in the VM override. The site is HTTPS, so the classroom's cookie would ship **without `Secure`** (`exercise_dependencies.py:346-359`). The *instructor* cookie defaults to `Secure` regardless (`:452`). |
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
(`instructor_session.py:137-164`, the strip and the length test at `:163-164`),
so a trailing newline pasted into a deploy
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
GRANT SELECT, INSERT, UPDATE, DELETE ON exercise_profile_overlay TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, UPDATE, DELETE ON exercise_saved_setting   TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT, DELETE         ON exercise_result_run      TO "<EXERCISE_DB_ROLE>";
GRANT SELECT, INSERT                 ON exercise_result_unlock   TO "<EXERCISE_DB_ROLE>";
```

### `ON CONFLICT DO UPDATE` needs `UPDATE` even when nothing conflicts

The two `UPDATE`s on `exercise_profile_overlay` and `exercise_saved_setting`
are the ones a reader is most likely to drop, so they get their own paragraph.
PostgreSQL checks **both** `INSERT` and `UPDATE` privilege before it executes
an `INSERT ... ON CONFLICT DO UPDATE` statement, whether or not a row actually
conflicts. The check runs at executor start-up, so a cached plan does not skip
it either — there is no "it worked once" path through this. A
role holding only `INSERT` does not fail "sometimes, under contention" — it
fails **every time**, which takes out `POST
/v1/exercise/workspaces/current/refresh` and `POST
/v1/exercise/instructor/refresh-all` (overlay) and every save of a named
setting (saved setting).

`ON CONFLICT DO NOTHING` is the opposite case and needs `INSERT` alone, which
is why `exercise_team_workspace`'s entry upsert and `exercise_result_unlock`
contribute no `UPDATE` of their own.

### Every statement, and the privilege it needs

Re-derived by grepping `pg_insert`, `on_conflict_do_update`,
`on_conflict_do_nothing`, `sa.insert`, `sa.update`, `sa.delete` and
`with_for_update` across
`python/smartmatch_persistence/smartmatch_persistence/exercise/*.py`. One row
per statement, so the grant above can be rebuilt rather than trusted.

| Statement | Table | Privilege |
|---|---|---|
| `dataset_repository.py:391` `sa.insert(exercise_dataset)` | `exercise_dataset` | INSERT |
| `dataset_repository.py:401` `sa.insert(exercise_profile)` | `exercise_profile` | INSERT |
| `dataset_repository.py:406` `sa.insert(exercise_event)` | `exercise_event` | INSERT |
| `instructor_repository.py:436` `sa.update(exercise_dataset)` | `exercise_dataset` | UPDATE |
| `instructor_repository.py:460-462` `pg_insert(...).on_conflict_do_nothing` | `exercise_result_unlock` | INSERT |
| `instructor_repository.py:531-535` `sa.delete(child)`, three children | `exercise_profile_overlay`, `exercise_saved_setting`, `exercise_result_run` | DELETE |
| `instructor_repository.py:675-677` `sa.select(...).with_for_update()` | `exercise_team_workspace` | SELECT **+ UPDATE** (a row lock needs `UPDATE` beside `SELECT`) |
| `instructor_repository.py:681-686` `sa.select(...).with_for_update()` | `exercise_team_workspace` | SELECT + UPDATE |
| `instructor_repository.py:699-702` `sa.delete(exercise_team_workspace)` | `exercise_team_workspace` | DELETE |
| `instructor_repository.py:709` `sa.update(exercise_team_workspace)` | `exercise_team_workspace` | UPDATE |
| `results_repository.py:432` `sa.insert(exercise_result_run)` | `exercise_result_run` | INSERT |
| `results_repository.py:473` `sa.update(exercise_team_workspace)` | `exercise_team_workspace` | UPDATE |
| `results_repository.py:553` `sa.update(exercise_team_workspace)` | `exercise_team_workspace` | UPDATE |
| `results_repository.py:650-656` `pg_insert(...).on_conflict_do_update` | `exercise_profile_overlay` | INSERT **+ UPDATE** |
| `settings_repository.py:386-398` `pg_insert(...).on_conflict_do_update` | `exercise_saved_setting` | INSERT **+ UPDATE** |
| `settings_repository.py:436` `sa.delete(exercise_saved_setting)` | `exercise_saved_setting` | DELETE |
| `workspace_repository.py:272-282` `pg_insert(...).on_conflict_do_nothing` | `exercise_team_workspace` | INSERT |
| `workspace_repository.py:449-452` `sa.update(table)` — the token-hash repair | `exercise_team_workspace` | UPDATE |
| `workspace_repository.py:535-540` `sa.delete(child)`, three children | `exercise_profile_overlay`, `exercise_saved_setting`, `exercise_result_run` | DELETE |
| `workspace_repository.py:543` `sa.update(table)` — reset regenerates the seed | `exercise_team_workspace` | UPDATE |
| every repository read (`sa.select`) | all eight | SELECT |
| `sa.select(sa.func.pg_advisory_xact_lock(...))` (e.g. `instructor_repository.py:668`) | none | none — see below |

**Advisory locks need no grant.** The exercise repositories serialize with
`pg_advisory_xact_lock`, which is a function, not a table: `EXECUTE` on it is
granted to `PUBLIC` by default, so nothing above covers it and nothing needs
to. The warning is in the other direction — **a hardening pass that runs
`REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_catalog FROM PUBLIC` would break
every workspace write**, because every write path takes one of these locks
first. If someone proposes that hardening, this role needs `EXECUTE ON
FUNCTION pg_advisory_xact_lock(bigint)` granted back explicitly.

**No sequence grants are needed.** Every primary key is a `UUID` the
application generates or a natural composite key — `schema.py:119`, `:235`,
`:343`, `:386` are `sa.Column("id", _UUID, primary_key=True)` with no server
default, and the other four tables use composite `PrimaryKeyConstraint`s
(`0037_exercise_tables.py:155`, `:180`, `:254`, `:352`). There is no `SERIAL`,
no `IDENTITY` and no `CREATE SEQUENCE` in the revision.

### Prove the role cannot read a CBA table

Three checks. Run them after every change to the grant, and before the class.

**Which role to connect as differs per check, and it matters.** Check 1 is a
behavioural test and must run **as the new role**. Checks 2 and 3 are cleaner
run **as the owner role**: `information_schema.tables` is itself filtered to
what the *current* user can see, so running them as the restricted role hides
precisely the rows the check exists to find. `has_table_privilege` takes the
role as an argument, so the owner can ask the question on the new role's
behalf and get the whole picture.

**1. The spot check.** Connect **as the new role**. It must fail.

```sql
-- Expect: ERROR: permission denied for table user_account
SELECT count(*) FROM user_account;
```

**2. The exhaustive check.** This is the one that matters, and it asks
PostgreSQL what the role can *effectively* do rather than what was written in a
`GRANT`:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND has_table_privilege(
        '<EXERCISE_DB_ROLE>',
        format('%I.%I', table_schema, table_name),
        'SELECT'
      )
ORDER BY table_name;
```

**`has_table_privilege` rather than `information_schema.table_privileges`.**
The privileges view lists grants *made to this grantee by name*, and so misses
three ways a role ends up able to read a table anyway: a grant made to
`PUBLIC`, a `ALTER DEFAULT PRIVILEGES` rule that fires on tables created later,
and privileges inherited through `GRANT <other_role> TO <EXERCISE_DB_ROLE>`. A
query that misses those reports a clean result on a role that can read
everything, which is the worst possible answer from a check like this.
`has_table_privilege` resolves all three.

**Expected result: only `exercise_` names — eight of them.**

* **A non-`exercise_` name is a failure.** Find where it came from — usually a
  `GRANT ... ON ALL TABLES IN SCHEMA public`, a `PUBLIC` grant, or a role
  membership — revoke it, and re-run. The per-table list above is the whole
  grant.
* **`alembic_version` is the one name to expect and still not accept.** It is
  not an `exercise_` table and this role has no business reading it: migrations
  run as the owner, not as this role ([above](#3-the-database-role)). If it
  appears, it arrived through a `PUBLIC` or all-tables grant — which means
  other tables almost certainly came with it. Treat its presence as a signal to
  re-check the whole result, not as a harmless exception to wave through.

**3. And confirm the role CAN do what it needs.** A too-narrow grant fails in
the classroom, not in this check, so verify the positive direction too:

```sql
SELECT table_name,
       has_table_privilege('<EXERCISE_DB_ROLE>', format('%I.%I', table_schema, table_name), 'SELECT') AS sel,
       has_table_privilege('<EXERCISE_DB_ROLE>', format('%I.%I', table_schema, table_name), 'INSERT') AS ins,
       has_table_privilege('<EXERCISE_DB_ROLE>', format('%I.%I', table_schema, table_name), 'UPDATE') AS upd,
       has_table_privilege('<EXERCISE_DB_ROLE>', format('%I.%I', table_schema, table_name), 'DELETE') AS del
FROM information_schema.tables
WHERE table_schema = 'public' AND table_name LIKE 'exercise\_%'
ORDER BY table_name;
```

It must match the grant block above exactly:

| `table_name` | `sel` | `ins` | `upd` | `del` |
|---|---|---|---|---|
| `exercise_dataset` | t | t | t | f |
| `exercise_event` | t | t | f | f |
| `exercise_profile` | t | t | f | f |
| `exercise_profile_overlay` | t | t | **t** | t |
| `exercise_result_run` | t | t | f | t |
| `exercise_result_unlock` | t | t | f | f |
| `exercise_saved_setting` | t | t | **t** | t |
| `exercise_team_workspace` | t | t | t | t |

The two bold `upd` cells are the `ON CONFLICT DO UPDATE` ones. If either reads
`f`, refresh and saved settings are broken and no other check in this document
will tell you.

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

So the reverse proxy in front of `exercise.plated.blog` must route, to the exercise
API process:

* `/v1/exercise` and everything under it — **without rewriting the path**;
* the static frontend for everything else.

The existing Vite dev server already proxies `/v1` unrewritten to the API
(`vite.config.ts:62-67`), which is the shape to copy. What it does **not** have
is `exercise.plated.blog` in `allowedHosts` (`vite.config.ts:53`) — see the gaps
table at the top.

---

## 4a. The tunnel, and why there is no Access policy

### Adding the hostname

`exercise.plated.blog` is a **second public hostname on the tunnel that already
exists**, not a second tunnel. The tunnel is
`smartmatch-classroom-pilot`, built by
[`classroom-vm-cloudflare-tunnel.md`](classroom-vm-cloudflare-tunnel.md) Part 2,
and `cloudflared` is already installed and running on the VM as a service. **No
new token, no second `cloudflared service install`, no change on the VM.**

The steps are the ones that guide's Part 2 §1 step 4 already describes
(`classroom-vm-cloudflare-tunnel.md:230-234`), applied a second time to the
same tunnel:

1. Cloudflare Zero Trust → **Networks** → **Tunnels** → open
   `smartmatch-classroom-pilot`.
2. Add a **Public hostname**: subdomain `exercise`, the same zone as
   `pilot.plated.blog`, type **HTTP**, URL the exercise process's loopback
   origin on the VM.
3. Save. Creating the public hostname in the dashboard normally adds the CNAME
   `exercise.plated.blog` → `<tunnel-id>.cfargotunnel.com`
   (`classroom-vm-cloudflare-tunnel.md` Part 2 step 3). If it did not, add it
   there; that guide is the authority on the DNS half.

**The loopback port is `127.0.0.1:8090`** — `docker-compose.yml`'s
`api-exercise` service, distinct from the CBA API's `127.0.0.1:8080` and
`web`'s `127.0.0.1:5173` (`vm-deploy.md:319-329`). Point the hostname at that
origin. This mapping is dashboard-managed and lives in no file in this
repository (`vm-deploy.md:87-96`), exactly as `pilot.plated.blog`'s does.

### No Cloudflare Access policy on this host

Owner decision, 2026-09-21. This is a deliberate difference from
`pilot.plated.blog`, and
[`classroom-vm-cloudflare-tunnel.md`](classroom-vm-cloudflare-tunnel.md) Part 3
says the opposite for *that* host — "if you skip Access, anyone who guesses the
hostname gets the demo. Do not skip it." Both are right, for different
products, and the difference is worth stating rather than leaving a reader to
find the contradiction:

| | `pilot.plated.blog` (CBA) | `exercise.plated.blog` (this scope) |
|---|---|---|
| What is behind it | Seeded CBA portals with real-shaped student and speaker records | Six team workspaces over **fictional** rows (ADR-0025 D2) |
| Login | None of its own — Access **is** the door | None **by design**: no CBA authenticated router is mounted (ADR-0025 D1), so there is no account to protect |
| Credential in the product | Fixture bearer tokens, emptied on the VM | One: the instructor passcode |
| Edge protection | Cloudflare Access allowlist | The passcode, plus the rate-limit rule in [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06) |

Why an Access wall is the wrong tool here, stated plainly: the exercise is a
classroom activity that thirty participants open on their own laptops within a
few minutes of each other, with no accounts. An email allowlist in front of it
is a second sign-in for a product whose whole design is that it has none, and
the first five minutes of the class would be spent on Cloudflare's login
instead of the exercise.

**What that trades away, said without softening it:** anyone who learns
`exercise.plated.blog` can open the team surface, enter a team number and see
that team's workspace. The data is invented and there is no account to
compromise, which is what makes the trade acceptable *for this scope*. The
instructor surface is the part that is actually defended, by two things:

* the passcode (`SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE`), with PBKDF2 in
  front of every attempt; and
* the rate-limit rule at the proxy, which is **the only edge protection this
  host has** and is therefore not optional — see the next section.

This is not a production-readiness claim about either host.
`ALLOW_CLOUD_DEPLOY=false` is unchanged.

---

## 5. Rate limiting belongs at the proxy (OQ-CE-06)

The path to limit is `POST /v1/exercise/instructor/login` — the literal
`"/login"` on `login_router` at
`services/api/smartmatch_api/routers/exercise_instructor.py:192-193`, under the
router prefix `/v1/exercise/instructor` (`:155`). It is the one unauthenticated
guessing surface in the product.

It has an in-process limiter today, and that limiter is a **marked
placeholder** (`services/api/smartmatch_api/exercise_rate_limit.py:1`, whose
first line is the word `PLACEHOLDER`). What it is:

* 10 attempts per client address per 5-minute window
  (`exercise_rate_limit.py:75`, `:85`);
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

**With no Access policy on this host ([§4a](#4a-the-tunnel-and-why-there-is-no-access-policy)),
this rule is the only edge protection `exercise.plated.blog` has.** It is not
optional, and it is not in git: the front door is a dashboard-managed
Cloudflare Tunnel (`vm-deploy.md:87-96`) and there is no nginx, Caddy or
Traefik config in this repository to add a `limit_req` zone to. So the rule is
specified here, concretely enough to be built and reviewed by hand:

| Setting | Value |
|---|---|
| Rule type | Cloudflare **Rate Limiting Rule** (WAF), on the zone serving `exercise.plated.blog` |
| Match | `http.host eq "exercise.plated.blog" and http.request.method eq "POST" and http.request.uri.path eq "/v1/exercise/instructor/login"` |
| Counting key | **client IP** — the app parses no `X-Forwarded-For`, so the proxy is the only hop that can do this |
| Budget | **10 requests / 5 minutes** per IP — deliberately equal to `INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT` (`exercise_rate_limit.py:75`) and `INSTRUCTOR_LOGIN_WINDOW` (`:85`), so the two bounds cannot disagree |
| Action | **Block**, 429, with a response indistinguishable from the app's own refusal — a different page tells an attacker exactly where the limit lives |
| Scope check | The rule must match **only** that path. A rate limit on all of `exercise.plated.blog` would throttle thirty laptops loading the exercise at the same moment, which is the normal start of a class. |

Do **not** put a matching rule on `pilot.plated.blog`; that host has Access in
front of it and a different threat model.

**Verify it by hand before the class** from a machine that is not the
classroom's: send 11 `POST`s with a wrong passcode and confirm the 11th is
refused by Cloudflare rather than by the application. Nothing in this
repository can test a dashboard rule.

OQ-CE-06's address half is **decided** (2026-09-21); this rule is the part that
is still to be applied. When it is, `exercise_rate_limit.py` is deleted and the
dependency comes off the route, which the module's own docstring already
anticipates.

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
3. Load `https://exercise.plated.blog/` from a cold profile. Record **Time to
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
not a production bundle (`vm-deploy.md:350-375`), and a dev server's first load
is not a built bundle's first load.

---

## 7. Day-of-class runbook

Steps 1-7 are instructor-page actions; every one needs a live instructor
session (the passcode) and sends `X-Exercise-Request`. Step 0 needs neither.

0. **Is it up?**

   ```bash
   curl -sS https://exercise.plated.blog/api/health
   # {"status":"ok","release":"..."}
   ```

   The `release` value is whatever `SMARTMATCH_RELEASE` the exercise process
   was given; do not read anything into it until the compose change that
   creates that process decides what to pass.

   `/api/health` is declared on the application itself, **outside** the
   scope-filtered router table (`main.py:704-706`, after the
   `routers_for(get_settings())` loop at `:700-701`), so it is served in this
   scope exactly as it is in the CBA one. It **touches no database and needs no
   cookie** — it reads `settings.release` and returns (`main.py:713-714`). That
   is what makes it the right probe: a green answer proves the process and the
   tunnel hostname, and proves nothing about the database or the grant. Use the
   checks in [§3](#3-the-database-role) for those.

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
   fixed windows, no `X-Forwarded-For` — see [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06).
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
   stanza and bind-mounts the checkout (`vm-deploy.md:350-375`). A frontend
   change is live on `git checkout`; a *backend* change is not, which is why
   compose on this VM needs **both** `-f docker-compose.yml -f
   docker-compose.vm.yml` **and** `--build` (`vm-deploy.md:534-567`): omitting
   the override strips the restart policies, and omitting `--build` reuses stale
   images.

---

## 9. Deploy and verify checklist

**Read [§0](#read-this-first-three-things-you-cannot-do-today) before you run
this.** The compose gap that used to block steps 7-10 and 18 is **closed**:
`docker-compose.exercise.yml`'s `api-exercise` service runs
`SMARTMATCH_PRODUCT_SCOPE=class_exercise` behind the `exercise` compose
profile, loaded as a third `-f` file alongside `docker-compose.yml` and
`docker-compose.vm.yml`. Steps 7-10 and 18 below give the exact commands. The other two gaps
in [§0](#read-this-first-three-things-you-cannot-do-today) — the Vite
`allowedHosts` entry and the dashboard-managed rate-limit rule — are
unaffected by this and remain open; steps that depend on them are still
marked accordingly.

This is an operator procedure, not a proof of readiness. Nothing here has been
run. See [§9b](#9b-what-this-checklist-does-not-prove).

Evidence table template — copy this into a dated entry when you run the
checklist for real:

| Step | Result | Date | SHA | Operator |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| … |  |  |  |  |

### Pre-flight

1. **Confirm the branch and SHA `deploy` will fast-forward to.**
   ```bash
   git -C /opt/smartmatch/app fetch origin
   git rev-parse origin/deploy origin/main
   ```
   Pass: the two SHAs match, or `origin/main` is a fast-forward ahead of
   `origin/deploy` (the shape [`promote.yml`](../../.github/workflows/promote.yml)
   requires — it refuses a non-fast-forward push). Fail: `origin/deploy` has
   diverged; resolve before promoting, per
   [`vm-deploy.md`](vm-deploy.md#promoting-a-commit-to-the-vm).

2. **Confirm the migration head is `0041_batch_speaker_request`.**
   ```bash
   grep -L 'down_revision = "0041_batch_speaker_request"' /dev/null; \
   grep -rl 'down_revision = "0041_batch_speaker_request"' db/migrations/versions/*.py
   ```
   Pass: the second command prints **nothing** — no later revision points back
   at `0041_batch_speaker_request`, so it is the head
   (`db/migrations/versions/0041_invitation_batch_speaker_request.py` sets its own
   `down_revision = "0040_booking_cancellation"`; the file name is longer than the
   revision id because `alembic_version` is `varchar(32)`). Fail: a revision is
   printed — the head has moved past `0041`; re-derive this step against the new file
   before continuing, since the tables the grant in [§3](#3-the-database-role)
   depends on may have changed shape.

3. **Confirm every required env var is present — names only, never values.**
   ```bash
   for v in SMARTMATCH_PRODUCT_SCOPE SMARTMATCH_EXERCISE_WORKSPACE_SECRET \
            SMARTMATCH_EXERCISE_COOKIE_SECURE SMARTMATCH_DATABASE_URL; do
     printf '%s: %s\n' "$v" "$([ -n "${!v:-}" ] && echo present || echo MISSING)"
   done
   ```
   Names come from [§2](#2-environment-variables); every one there marked
   **Yes** must print `present`. `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` is
   not required to boot but must be `present` before the day-of-class runbook
   in [§7](#7-day-of-class-runbook) can do anything instructor-facing. Fail:
   any required name prints `MISSING` — the process will not boot
   (`main.py:696-697`) or will boot into the wrong scope silently
   (`SMARTMATCH_PRODUCT_SCOPE` unset defaults to `cba`, serving no exercise
   route at all).

### DB role

4. **BLOCKED on nothing — this can run today.** Create the restricted role and
   verify it per [§3](#3-the-database-role) in full: the `CREATE ROLE` /
   `GRANT` block, then all three verification queries (the spot check, the
   exhaustive `has_table_privilege` check, and the positive-privilege table).
   Pass: the exhaustive check returns exactly the eight `exercise_*` names and
   the positive check matches the table in §3 exactly, including both bold
   `upd` cells. Fail: any other criterion in §3's own pass/fail language — do
   not re-derive it here, §3 is the authority.

### Env / secrets

5. **Generate the two secrets** using the commands in
   [§2](#2-environment-variables) ("Generating the two secrets"). Store both
   out of band — not in this repository, not in a ticket, not in a chat
   channel that outlives the class (OQ-CE-07). Pass: `SMARTMATCH_EXERCISE_WORKSPACE_SECRET`
   is at least 32 characters and `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` is
   at least 12 characters **after stripping** whitespace
   (`instructor_session.py:112,163-164`).

6. **`SMARTMATCH_EXERCISE_COOKIE_SECURE=true` is already pinned** for you —
   `docker-compose.exercise.yml` hard-sets it on the `api-exercise` service,
   per [§4](#4-https-and-cookies) and the owner decision, 2026-09-21. Nothing
   to set by hand. Pass: the workspace cookie (`exercise_workspace`) carries
   `Secure` on a response from `https://exercise.plated.blog`. **VERIFY ON
   VM** — cannot be checked before the process exists.

### Compose up

7. **Bring `api-exercise` up with all three files, the `exercise` profile,
   and a rebuild.** `docker-compose.exercise.yml` holds the service itself
   and is not loaded by any command that omits it — that is deliberate: an
   earlier version of this service lived directly in `docker-compose.yml`
   and broke the default `docker compose up` for the whole CBA stack, because
   Compose evaluates its required secrets (`${VAR:?message}`) for every
   service in a loaded file regardless of profile. Keeping it in its own file
   is what makes `-f docker-compose.yml -f docker-compose.vm.yml up` — the
   ordinary CBA command — unaffected. The required secrets
   ([§2](#2-environment-variables)) must already be exported or in the VM's
   `.env` before this runs, or compose refuses to start the container:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.vm.yml \
     -f docker-compose.exercise.yml --profile exercise \
     up -d --build api-exercise
   docker compose -f docker-compose.yml -f docker-compose.vm.yml \
     -f docker-compose.exercise.yml ps
   ```
   `migrate` does not need re-running here on its own — it already ran (or
   will run) as part of the normal CBA `up`, and `api-exercise` shares that
   same database and migration head ([§0](#read-this-first-three-things-you-cannot-do-today)
   step 2). Pass: `docker compose ps` shows `api-exercise` as `Up`. Omitting
   `docker-compose.exercise.yml` means the service is never defined at all;
   omitting `--build` reuses a stale image; omitting `--profile exercise`
   means the service is defined but never started — none is a valid partial
   run.

8. **Size the exercise process's connection pool down explicitly** before
   first boot, per [§8](#8-known-limits) item 4 — do not let it take the
   default `20 + 10`. Set `SMARTMATCH_EXERCISE_DB_POOL_SIZE` and
   `SMARTMATCH_EXERCISE_DB_MAX_OVERFLOW` (`.env.example` documents both,
   mapped by `docker-compose.exercise.yml` to this container's
   `SMARTMATCH_DB_POOL_SIZE` / `SMARTMATCH_DB_MAX_OVERFLOW`) before the `up`
   in step 7. Pass: the values are set to something smaller than the
   existing `(20+10) + (20+10) = 60` CBA budget leaves room for against the
   database's `max_connections = 100`.

### Tunnel hostname

9. **Add the `exercise.plated.blog` public hostname** to the existing
   `smartmatch-classroom-pilot` tunnel, per [§4a](#4a-the-tunnel-and-why-there-is-no-access-policy),
   pointing it at `http://127.0.0.1:8090` — the loopback origin
   `docker-compose.exercise.yml`'s `api-exercise` service publishes. No new tunnel, no
   new `cloudflared service install`. Pass: Cloudflare Zero Trust → Networks →
   Tunnels → `smartmatch-classroom-pilot` lists a public hostname for
   `exercise.plated.blog` pointing at `127.0.0.1:8090`. **VERIFY ON VM** —
   this is a dashboard action with no file in this repository to check it
   against.

10. **Apply the rate-limit rule** in [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06)
    on the zone serving `exercise.plated.blog` — Cloudflare Rate Limiting
    Rule, `POST /v1/exercise/instructor/login`, 10 requests / 5 minutes per
    client IP, action Block. This is the **only** edge protection this host
    has ([§4a](#4a-the-tunnel-and-why-there-is-no-access-policy)) — do not skip
    it because §9 step 9 feels done. Do **not** apply a matching rule to
    `pilot.plated.blog`.

### Smoke tests

Steps 11-16 need step 9 (and, for the instructor ones, an instructor session)
to be live. All are **VERIFY ON VM** until then.

11. **Health.**
    ```bash
    curl -sS https://exercise.plated.blog/api/health
    ```
    Pass: `{"status":"ok","release":"..."}`. This proves the process and the
    tunnel hostname, and nothing about the database or the grant
    (`main.py:704-706,713-714`, [§7](#7-day-of-class-runbook) step 0). Use
    step 4 above for the database side.

12. **Exercise entry page loads at the exercise hostname.**
    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' https://exercise.plated.blog/
    ```
    Pass: `200`.

13. **Scope isolation, direction one — a CBA route is NOT reachable on the
    exercise hostname.**
    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' https://exercise.plated.blog/v1/jobs
    ```
    Pass: `404`. ADR-0025 D1 means the five principal-bearing CBA routers are
    never registered in the `class_exercise` scope process
    (`main.py:281-315`) — this is a route-table property, not a firewall rule,
    so this check exercises the real guarantee.

14. **Scope isolation, direction two — an exercise route is NOT reachable on
    the pilot hostname.**
    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' https://pilot.plated.blog/v1/exercise/public
    ```
    Pass: `404` (or an Access challenge if it is reached before routing, which
    also counts as "not reachable" — either way the CBA process must never
    answer as the exercise scope). The CBA process has
    `SMARTMATCH_PRODUCT_SCOPE` unset/`cba`, so none of the seven exercise
    routers in [§1](#which-routers-this-scope-mounts) are mounted there.

15. **Instructor route refuses without the passcode.**
    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' \
      -X POST https://exercise.plated.blog/v1/exercise/instructor/login \
      -H 'Content-Type: application/json' -H 'X-Exercise-Request: 1' \
      -d '{"passcode":"wrong-passcode-value"}'
    ```
    Pass: a refusal status (401/403 — confirm the exact code against
    `exercise_instructor.py` when the process is live; do not guess it here),
    the **same sentence** a missing passcode gets
    (`exercise_dependencies.py:498-516`).

16. **Rate limiting answers 429 under burst.** Send 11 `POST`s with a wrong
    passcode from a machine that is not the classroom's own; confirm the 11th
    is refused by Cloudflare (429), not by the application. This is the check
    [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06) itself specifies —
    nothing in this repository can execute a dashboard rule, so this remains a
    by-hand step even after the compose change lands.

17. **Cookie carries `Secure`/`HttpOnly`/`SameSite`.**
    ```bash
    curl -sSI https://exercise.plated.blog/v1/exercise/public/something | grep -i set-cookie
    ```
    Pass, against [§4](#4-https-and-cookies)'s table: `exercise_workspace` has
    `HttpOnly`, `SameSite=Lax`, and `Secure` (from
    `SMARTMATCH_EXERCISE_COOKIE_SECURE=true`, step 6). `exercise_instructor`
    (path `/v1/exercise/instructor`) defaults to `Secure` even if that variable
    is unset.

### Rollback

18. **Roll back exactly as `vm-deploy.md` describes for the CBA appliance** —
    this document adds no second rollback mechanism. A failed health check on
    the exercise process should be treated the same way `deploy.sh`'s existing
    health gate treats a CBA failure: do not promote past a red health check,
    and use the pre-migration backup `deploy.sh` already takes
    (`vm-deploy.md`'s "A backup before every migration" row) to restore if a
    migration on shared infrastructure went wrong. There is no exercise-only
    rollback because there is no exercise-only backup — the database is
    shared. A compose-level rollback of the service itself is just
    `docker compose -f docker-compose.yml -f docker-compose.vm.yml
    -f docker-compose.exercise.yml --profile exercise stop api-exercise`
    (or the full three-file `up -d --build api-exercise` from step 7 again
    on the prior SHA) — it is `-f docker-compose.exercise.yml --profile
    exercise` on top of, not a replacement for, the ordinary
    `deploy.sh` rollback path. **VERIFY ON VM**: `scripts/vm/deploy.sh` is
    not part of this track and was not changed here — confirm by hand
    whether its health gate already covers a profile-gated service before
    relying on it to catch an `api-exercise` failure automatically.

### Post-class teardown / reset

19. **Reset a single team's workspace** with `POST
    /v1/exercise/instructor/workspaces/{team_number}/reset`
    ([§7](#7-day-of-class-runbook) step 5) if a team needs a clean run
    mid-class. There is no team-facing reset and no bulk reset endpoint (PR
    #186, owner ruling 2026-09-19) — reset teams one at a time.

20. **End of day: rotate `SMARTMATCH_EXERCISE_WORKSPACE_SECRET`** per
    [§2](#2-environment-variables) ("What rotating the workspace secret
    does") if the class is fully over and no re-entry is expected — this ends
    every team's cookie and every live instructor session in one action. Do
    **not** rotate it between class sessions on the same day; a team that
    re-enters expects its same workspace back.

21. **Rotate `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` after the spring run**,
    per OQ-CE-07's recorded safe default ([§2](#2-environment-variables),
    "Sharing and rotating the passcode"). Restart the exercise process after
    changing it; this does not end live instructor sessions (they are signed
    with the workspace secret, not the passcode).

22. **Nothing here removes the exercise tables or the exercise DB role.**
    Teardown of the process itself (stopping the container, removing the
    tunnel hostname) is out of scope for this checklist — it is a compose and
    dashboard action with no data-safety concern of its own, unlike anything
    touching the database.

## 9a. Promote dry run

[`promote.yml`](../../.github/workflows/promote.yml) is `workflow_dispatch`
only — an operator runs it by hand with a `source_ref` input (default `main`)
— specifically so "merge to main" and "deploy to the VM" stay two distinct,
human-decided events. It does two things: fast-forward-only pushes the
resolved SHA to `deploy` (`git push origin "${SOURCE_SHA}:refs/heads/deploy"`,
which fails loudly on a non-fast-forward rather than forcing it), then
dispatches [`deploy.yml`](../../.github/workflows/deploy.yml) against
`deploy` via `gh workflow run deploy.yml --ref deploy`. `deploy.yml` in turn
runs `build` and `verify`, authenticates to GCP over OIDC, reaches the VM
through IAP/OS Login, and runs `scripts/vm/deploy.sh` there.

**What a dry run can show without deploying, and how:**

* **What would be promoted**, without pushing anything:
  ```bash
  git fetch origin
  git log --oneline origin/deploy..origin/main
  git rev-parse origin/main
  ```
  This is exactly what promote.yml's "Resolve and sanity-check the source
  commit" step computes (`git rev-parse --verify "${SOURCE_REF}^{commit}"`)
  and what the fast-forward push would move `deploy` to — read-only.

* **Whether the push would be a fast-forward or would be refused**: `git
  merge-base --is-ancestor origin/deploy origin/main && echo
  fast-forward-ok || echo would-be-refused`.

* **What `deploy.yml` would run, without triggering it**: read the workflow
  file itself (already done for this checklist — see the summary above) or
  `gh workflow view deploy.yml` for its current definition on `main`. There is
  no `--dry-run` flag on `workflow_dispatch` for either workflow; "would run"
  here means "read the script", not "execute with side effects suppressed."

**Do not run `gh workflow run promote.yml` or `gh workflow run deploy.yml`**
as part of this checklist — that deploys. Capture evidence of a dry run as:
the `git log --oneline origin/deploy..origin/main` output, the fast-forward
check result, and the date/SHA — in the evidence table above.

## 9b. What this checklist does not prove

* **No real students ran it.** Every step above, where marked, is either
  unexecuted or executed by the documenting agent's own repo inspection, not
  by an operator on the VM against real traffic.
* **The dataset is a synthetic/placeholder layout, not a graded one.**
  OQ-CE-01 (the synthetic dataset's exact shape) is **OPEN** — the CSV upload
  in [§7](#7-day-of-class-runbook) step 1 accepts whatever raw CSV is handed
  to it; nothing here asserts that shape matches what the class actually
  needs.
* **The matching coefficients are a placeholder.** OQ-CE-03/04 are **OPEN** —
  [§7](#7-day-of-class-runbook) step 6 documents that the results endpoint
  answers `409` by design until they are confirmed. This is expected, not a
  deployment defect, and remains true after this checklist passes.
* **Engineering did not execute this.** An operator must run it for real, on
  the VM, and record the date, the deployed SHA, and their name in the
  evidence table in [§9](#9-deploy-and-verify-checklist) before the "Deployed
  & reachable" row can move past "checklist ready, operator run pending."
* **The compose change is in this repository but has not been run.** Steps
  7-10 and 18 of §9 are now written against `docker-compose.exercise.yml`'s
  `api-exercise` service and `tests/unit/test_exercise_compose_service.py`
  pins its shape, but no `docker compose --profile exercise up` has been run
  against it on the VM or anywhere else, and this document makes no claim
  that it has. `docker` was unavailable in the environment that added the
  service, so `docker compose ... config` was not run either — the unit test
  is the only automated evidence this repository has for it.

---

## 10. Open questions

| ID | Question | Status | Where it bites here |
|---|---|---|---|
| **OQ-CE-06** | "Where does the site live and what is its stable address?" — owner Danny. `exercise_rate_limit.py` carries the same id for the edge-limiting half | **Address decided 2026-09-21** (`exercise.plated.blog`, second hostname on the existing tunnel, no Access policy); **rate-limit rule still to be applied at the proxy** | The rule in [§5](#5-rate-limiting-belongs-at-the-proxy-oq-ce-06) is specified here but lives in the Cloudflare dashboard, not in git. This file does not edit the register; the dated OQ-CE-06 line is another agent's change. |
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
