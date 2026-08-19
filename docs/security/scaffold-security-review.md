# Scaffold security review

**Reviewed:** 17 August 2026 · Foundation scaffold
**Amended:** 19 August 2026 — Wave B (`2cdc5a8`, `2564d33`, `b0a6a48`): worker
command execution, real OIDC task-identity verification, and the re-drive
command. See S-001, the posture table below, and the notes added to S-006 and
S-008.
**Scope:** the target repository as committed. Not a review of a deployed system —
nothing is deployed.

---

## Posture summary

The scaffold's security properties are **structural** wherever possible:
enforced by types, database constraints, or CI gates rather than by convention or
review vigilance. Where a control is not yet implemented, the code fails closed
rather than defaulting open.

| Property | Mechanism | Verified by |
|---|---|---|
| Tenant isolation | Composite `(tenant_id, id)` keys and composite FKs | 11 integration tests against live PostgreSQL |
| Deny-by-default authorization | Pure policy returning denial for every non-allowed path | 29 authz tests, 21 of them negative |
| No caller-selected identity | `Principal.tenant_id` derived server-side; no endpoint accepts it | Contract test asserts `/auth/mock-login` → 404 |
| Suspension denies reads as well as writes | Authorization on every job route, suspension checked first | 3 integration tests (added after review finding S-006) |
| Classroom cannot reach live providers | Registry raises before credential checks; config validator rejects at boot | 16 provider-isolation tests |
| Worker refuses task delivery without a verified caller | Real OIDC verification (signature, issuer, audience, expiry, service-account allowlist); ships with no signature backend, so it fails closed exactly as the stub did | 31 worker-execution integration tests + 4 worker-boundary contract tests |
| A duplicate Cloud Tasks delivery cannot execute a job twice | Conditional `dispatched -> running` claim (`JobRepository.claim`); a losing delivery is acknowledged and runs nothing | Covered within the worker-execution tests above, e.g. `test_a_duplicate_delivery_is_acknowledged_without_executing_twice` |
| Scraped contacts cannot be emailed | Lifecycle state machine with no path to `ACTIVE_CANDIDATE` except via `CONSENTED` | 20 consent tests, incl. a graph-property assertion |
| Legacy anti-patterns cannot return | 12-rule scanner in CI | 25 scanner self-tests |
| Domain cannot acquire IO | import-linter forbidden contracts | Verified non-vacuous by deliberate violation |

---

## Findings

### S-001 — Worker task authentication: real verification, shipped unconfigured (RESOLVED as far as this repository can resolve it)

Superseded by `2cdc5a8` (J6). `services/worker/smartmatch_worker/identity.py`
replaces the unconditional-raise stub with a real verifier that checks, in
order: the token's **signature** against a resolved JWKS key, that the **issuer**
is Google, that the **audience** matches this service's configured URL, that the
token is **currently valid** (`exp`/`iat`/`nbf`, with a bounded clock-skew
leeway), and that the **service account** in the `email` claim is on an explicit
allowlist. `alg: none` and the `HS*`/`dir` family are rejected unconditionally
before any backend is consulted — the algorithm-confusion and unsigned-token
bypasses cannot be reached by wiring in a permissive backend. Tests
(`tests/integration/test_worker_execution.py`) supply a real local key pair and
assert the signature check actually runs, that the algorithm is pinned by the
resolved key rather than by the token's own header, and that a tampered payload,
a wrong-audience token, and `alg: none` are each rejected.

**The one thing that is not implemented, named precisely rather than hidden:**
verifying an RS256 signature needs an asymmetric-cryptography primitive, and
`requirements/runtime.txt` — hash-pinned, and regenerating that lock was out of
scope for J6 — contains none: no `cryptography`, no `pyjwt`, no `google-auth`.
Rather than hand-roll RSA verification (exactly the kind of code whose bugs are
silent and total), the signature primitive is an injected `SignatureVerifier`
port, and `build_task_verifier` ships **no default implementation of it**. With
no backend, no `SMARTMATCH_TASK_AUDIENCE`, or no
`SMARTMATCH_TASK_SERVICE_ACCOUNTS` — any one of the three — it returns an
`UnconfiguredTaskVerifier`, which raises `401` with no credential and `501` with
one, refusing every request. **This is not a stub that pretends to verify.** It
is the same real verifier class, checked at every call, refusing because a
required collaborator is absent rather than because verification was never
written. The practical effect for today's deployment is identical to the
scaffold's stub: no request can reach command dispatch, because nothing has
supplied a signature backend, an audience, or an allowlist.

Deploying real verification from here requires three separate, deliberate acts,
none of which is done in this repository: adding a vetted asymmetric-crypto
dependency to the hash-pinned lock, configuring `SMARTMATCH_TASK_AUDIENCE` and
`SMARTMATCH_TASK_SERVICE_ACCOUNTS` for the deployed service, and wiring a JWKS
source that fetches and caches Google's published keys.

**Residual risk:** none while unconfigured — the failure mode is unchanged from
the pre-Wave-B stub. **Owner:** engineering, before this service is deployed.

### S-002 — Rate limiting **(RESOLVED)**

v1.1 §3.4 specifies a three-layer scheme (Cloud Armor → PostgreSQL transactional
limiter → budget reservation). Layer 2 is now implemented in
`smartmatch_persistence.rate_limit` and enforced on the command path, shipping in
the same commit as the first command resource as this finding required.

Counters are PostgreSQL rows incremented by a single `INSERT ... ON CONFLICT DO
UPDATE` with a guard on the SET clause, so there is no read-then-write window in
which two instances both observe room. `test_the_counter_is_shared_across_sessions`
asserts the property that matters: an in-process counter would let each Cloud Run
instance permit the full quota independently.

**Remaining:** layer 1 (Cloud Armor) requires deployed infrastructure; layer 3
(budget reservation) ships with the first paid provider call in R4. Neither is
reachable today — no endpoint spends provider budget.

### S-003 — Dependency pinning **(RESOLVED)**

`requirements/runtime.txt` and `requirements/dev.txt` are compiled from `.in`
files with `--generate-hashes`, and both `make setup` and CI install with
`--require-hashes`. A compromised or newly-published upstream artifact fails the
hash check rather than being installed silently.

CI also recompiles the locks and fails if they differ from what is committed, so
a `.in` edited without running `make lock` cannot leave CI installing something
other than what the author intended.

Verified by a clean frozen install into an empty virtualenv, not only by the
files existing.

### S-004 — Dependency vulnerability scanning **(RESOLVED)**

The `audit` job runs `pip-audit --strict` against `requirements/runtime.txt`.
Auditing the lock rather than a fresh resolve means the result describes exactly
what gets installed. Current result: no known vulnerabilities.

**Remaining:** license-policy checking and SBOM generation stay in the
before-live gate set. Neither blocks anything today.

### S-006 — Job reads were authenticated but never authorized **(RESOLVED)**

Found by code review, and it contradicted a claim made earlier in this document.

`get_job` and `stream_job_events` scoped by tenant and stopped there. Neither
invoked the authorization policy, so a **suspended account retained full read
access** to job status and event payloads, and any authenticated tenant member
could read any job in the tenant.

This document previously asserted that suspension "fails local authorization
independent of IdP token revocation". That was true only of routes that call the
policy. The claim has been narrowed to what the code enforces, and the job routes
now authorize before reading, with suspension checked first and unconditionally.

**Residual, and deliberately not hidden:** the `job` table has no owning org
unit, so job reads cannot be scoped to a subtree the way `/imports` scopes its
unit. Authorization is actor-or-oversight-role within the tenant, meaning a
coordinator in one department can read another department's job. Closing that
requires a `job.owning_unit_id` column and an expand-phase migration.
**Owner:** engineering, R1.

**Extended by the re-drive command (`b0a6a48`).** `POST /v1/jobs/{id}/redrive`
and `/abandon` (`services/api/smartmatch_api/routers/redrive.py`) carry the same
gap for the same reason: the route cannot call `smartmatch_authz.assert_allowed`
because there is no `owning_unit_path` to match it against, so it applies the
policy's own rules by hand — suspension, tenant match, explicit deny, then
role — over a job with no unit. A coordinator in one department can therefore
re-drive, and re-run the side effects of, another department's job, not only
read it. The router's own module docstring names this rather than papering over
it. The fix is the same one: `job.owning_unit_id`.

### S-007 — Resource grants bypassed role requirements **(RESOLVED)**

The explicit-allow path in `smartmatch_authz.policy.evaluate` returned before
`required_roles` was consulted, so a principal holding any `resource_grant` allow
row satisfied a role-gated operation. A guest reviewer with a single event grant
could submit imports.

A grant conveys access to a resource, not authority to perform any operation on
it. `ResourceGrant` carries no role, so a bare grant now cannot satisfy a
role-gated operation, and the denial carries a distinct
`resource_grant_lacks_required_role` reason so the gap stays visible rather than
silent. Which roles a grant *should* convey is open policy-matrix work (A4).

### S-008 — Conflicting requests consumed no quota **(RESOLVED)**

The rate-limit increment was still uncommitted when `IdempotencyConflictError`
propagated, and the request-scoped session rolled it back — so an unbounded
stream of 409-producing requests cost nothing. The increment is now committed
before the error propagates.

**Applied proactively in the re-drive command (`b0a6a48`).** `redrive_job` and
`abandon_job` commit before re-raising both an idempotency conflict and a
`RedriveConflictError`/`InvalidTransitionError` from a job that cannot be
re-driven — the same pattern, applied where a second command was written rather
than being found there as a second instance of the defect.

### S-005 — Legacy repository contains committed local databases

Not a target finding, but worth recording: the legacy tracks `data/demo.db` and
`data/smartmatch.db`. These were **not** inspected for contents beyond confirming
their existence, and **not** copied. If they contain real contact data, that is a
legacy-repository privacy question with an owner outside this migration.

**Residual risk:** none for the target. **Owner:** legacy repository owner /
privacy. **Action:** flagged for the data owner; out of scope here.

---

## Controls verified present

### Secrets

- No credentials in the repository. `.gitignore` blocks `.env`, `*.pem`, `*.key`,
  and service-account JSON patterns.
- The scanner's `hard-coded-credential` rule matches both bare and quoted key
  forms (`api_key = "…"` and `"api_key": "…"`), the latter being how credentials
  most often actually get committed. This gap was found by the scanner's own
  self-test and fixed.
- CI runs gitleaks over full history.
- No secret was read, written, or transmitted during the migration.

### Authorization

The negative-test suite covers every case the verification matrix names:
anonymous, wrong role, wrong tenant, wrong resource, expired membership,
suspended account. Beyond those:

- **Suspension short-circuits.** The suspended-principal test gives the principal
  a covering membership *and* an explicit allow grant, so it proves suspension
  wins rather than merely coinciding with denial.
- **Explicit deny beats inheritance**, and beats a conflicting allow.
- **Label-boundary containment.** `OrgPath` stores a tuple, not a string, so
  `iawest.cpp.eng` does not cover `iawest.cpp.english`. A `startswith`
  implementation grants access there; the test asserts it does not.
- **Denials do not leak existence.** The error handler returns a stable reason
  code and a generic message, never whether the resource exists.

### Tenant isolation

Enforced by composite foreign keys, not application discipline. Integration tests
attempt three real cross-tenant writes (membership → user, job_event → job,
outbox → job) and PostgreSQL rejects all three. A same-tenant control write
confirms the constraint is not simply blocking everything.

### Classroom isolation

Four of the five v1.1 §3.3 mechanisms are outside the application (absent
credentials, VPC egress policy, deployment policy, project separation). The
application implements the fifth — configuration validation — in two places:

- `Settings._validate_isolation` refuses to boot a classroom edition that has
  fixture providers disabled or that carries any provider credential.
- `build_email_provider` / `build_route_matrix_provider` raise before any
  credential check, so a classroom deployment that somehow acquired a key still
  cannot construct a live client.

Finding a credential in a classroom environment is treated as a **deployment
defect and fails**, rather than being ignored.

---

## Not reviewed

- Deployed infrastructure — nothing is deployed.
- Terraform — only empty environment skeletons exist.
- Frontend — `apps/web` contains no application.
- Crawler / SSRF threat model — deferred to R3 with the research pipeline; no
  crawl code exists in the target.
- Container images — built and proven to run (`docs/operations/containers.md`),
  but not scanned and not deployed. No registry, no running instance.

---

## Statement

No live provider was called, no live data was accessed or imported, no cloud
resource was created or changed, and no production readiness is claimed. Pushes
were made only to the designated feature branch.
