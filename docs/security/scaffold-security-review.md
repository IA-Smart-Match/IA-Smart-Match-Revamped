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

### S-002 — No rate limiting or budget enforcement in the request path

v1.1 §3.4 specifies a three-layer scheme (Cloud Armor → PostgreSQL transactional
limiter → budget reservation). The Foundation scaffold implements the *tables*
(`tenant_budget`, `concurrency_lease`) and proves the transactional pattern works
(`test_transactional_budget_reservation_cannot_exceed_the_ceiling`), but no
middleware enforces limits.

**Residual risk:** low today — the API exposes only health and a static
unsubscribe page, neither of which consumes provider budget. Rises to **high**
the moment any command endpoint ships. **Owner:** engineering, R1. Must land in
the same release as the first command resource.

### S-003 — Dependencies are not pinned to a lock file

`make setup` and CI install from unpinned specifiers. A compromised or
newly-broken upstream release would be picked up silently.

**Residual risk:** medium. **Owner:** engineering, before-live gate. Resolution:
generate a lock file (`uv.lock` or `requirements.txt` with hashes) and switch CI
to a frozen install.

### S-004 — No dependency vulnerability or license scanning yet

Deferred to the before-live gate set per v1.1 §4.1 staging. Blocked on S-003:
scanning unpinned dependencies produces results that do not correspond to what
actually gets installed.

**Residual risk:** medium. **Owner:** engineering, before-live.

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
