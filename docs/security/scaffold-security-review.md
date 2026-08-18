# Scaffold security review

**Reviewed:** 17 August 2026 · Foundation scaffold
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
| Worker cannot be invoked unauthenticated | Identity stub raises unconditionally | 4 worker boundary tests |
| Scraped contacts cannot be emailed | Lifecycle state machine with no path to `ACTIVE_CANDIDATE` except via `CONSENTED` | 20 consent tests, incl. a graph-property assertion |
| Legacy anti-patterns cannot return | 12-rule scanner in CI | 25 scanner self-tests |
| Domain cannot acquire IO | import-linter forbidden contracts | Verified non-vacuous by deliberate violation |

---

## Findings

### S-001 — Worker task authentication is a stub (accepted, fails closed)

`services/worker/smartmatch_worker/main.py::_verify_task_identity` raises
unconditionally: `401` without credentials, `501` with them. No request can reach
command dispatch.

This is deliberate. Real verification means checking an OIDC token signature
against Google's public keys, validating the audience against the service's
deployed URL, and checking the service account against an allowlist — none of
which is meaningful before the service has a URL and an identity. A permissive
placeholder would become an unauthenticated entry point the moment a handler was
added.

**Residual risk:** none while unimplemented. **Owner:** engineering, R1.

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
- Container images — none built.

---

## Statement

No live provider was called, no live data was accessed or imported, no cloud
resource was created or changed, and no production readiness is claimed. Pushes
were made only to the designated feature branch.
