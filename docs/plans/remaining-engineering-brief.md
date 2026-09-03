# Remaining engineering brief — for follow-on planning

**Audience:** A planning agent who has **not** seen prior orchestration chats.
**Purpose:** Produce an implementation plan for work still open on branch
`friday-deliverable-828`. This document is planning input only — it does not
authorize implementation.
**Repo:** `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped`
**As of:** 2026-09-03 (G1 closed; M1 landed; decision blockers recorded in
`docs/decisions/`)

**Recent commits (relevant):**

| Commit | Summary |
|---|---|
| `4edcec2` | Wave 3C — legacy portal wired to accountable metrics API |
| `aea10e6` | Docs honesty — pilot-data README + metrics authz docstring aligned |
| `6fcb03a` | Orchestrator handoff superseded by 828 deliverable state |

**Supersedes for context:** [`orchestrator-handoff.md`](orchestrator-handoff.md) —
environmental blockers, standing constraints, and “what Dr. Wang can/cannot be
shown.”

---

## Standing constraints (do not override without explicit user consent)

From [`orchestrator-handoff.md`](orchestrator-handoff.md) §Standing constraints
(carry forward; confirm with user if unsure):

- `ALLOW_REMOTE_PUSH=false`, `ALLOW_CLOUD_DEPLOY=false`,
  `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`
- No production credentials, no live PII, no live provider calls
- **Never declare production readiness** — nothing is deployed
- **Do not open a pull request** unless the user explicitly asks
- **Nothing has been pushed** on this branch at handoff time — CI has not run
  against these commits locally

---

## Local gates vs CI (environmental — planner must account for)

### `make check` vs PostgreSQL integration proof

[`Makefile`](../../Makefile):

- `make check` runs `test`, which is **`pytest tests/ -m "not integration"`**
  — unit, golden, authz, and contract tests **without** a database.
- `make test-integration` / `make test-all` require PostgreSQL.
- `make migrate-check` requires PostgreSQL (empty DB → `alembic upgrade head`).

[`orchestrator-handoff.md`](orchestrator-handoff.md) §Blocker 1: no local
PostgreSQL in the handoff environment; **Wave 0 transaction fix** and **migration
`0009` engagement constraints** are proven only on CI
(`.github/workflows/verify.yml`: `postgres:16` service, full `pytest tests/`).

**Planning implication:** Green `make check` locally does **not** prove
integration contracts (`tests/contract/test_metrics.py`,
`tests/integration/test_engagement_schema_constraints.py`, migration `0009`
behavioural tests). First push + CI green is the merge gate.

### `npm ci` / `tsc` on DrvFs (`/mnt/c`)

[`orchestrator-handoff.md`](orchestrator-handoff.md) §Blocker 3: `npm ci` fails
on Windows DrvFs (`ENOTEMPTY`, `ENOENT` on `node_modules`). Workaround: install
on WSL-native filesystem and symlink `node_modules` into
`apps/web/legacy-frontend/`. Wave 3D/3C typecheck was run natively; **`vite
build` was not run locally** — CI web job does `install → typecheck → build →
audit`.

---

## What is already done — do not re-plan

### Wave 3C (`4edcec2`) — provenance wiring in legacy-frontend

Fence was `apps/web/legacy-frontend/src/app/pages/**` (per handoff). **Landed:**

| Area | Files / behaviour |
|---|---|
| Typed metrics client | `apps/web/legacy-frontend/src/lib/api.ts` — `fetchUnitMetrics`, `fetchMetricDrillDown` |
| Metric mapping | `apps/web/legacy-frontend/src/lib/metrics.ts` — `unknown` ≠ `0`, funnel metric names |
| Hook | `apps/web/legacy-frontend/src/app/hooks/useUnitMetrics.ts` |
| Pages | `Dashboard.tsx`, `Pipeline.tsx` consume registered metrics |
| Funnel UI | `PipelineFunnelTiles.tsx`, `MetricDrilldownSheet.tsx` |
| Site banner | `Layout.tsx` — `SyntheticDataBanner` (“development-only…not the product”) |
| Contract test | `tests/unit/test_metrics_openapi_contract.py` |

Backend register and routes (Wave 1A+2B, `6baf40e`):

- Domain register: `python/smartmatch_domain/smartmatch_domain/metrics.py`
  — `METRIC_REGISTER`, `PIPELINE_UNKNOWN_REASON` (“S12 Pipeline persistence is
  not started”)
- API: `services/api/smartmatch_api/routers/metrics.py` — owning queries,
  `_pipeline_funnel_rows_v1` returns honest unknown until S12

**Honest current behaviour (intentional):** Pipeline funnel metrics return
`value: null` with `unknown_reason` citing S12; drill-down returns `[]`. Do
**not** “fix” by fabricating counts. [`orchestrator-handoff.md`](orchestrator-handoff.md)
§Remaining work: “Pipeline funnel metrics resolve to unknown because S12's
persistence is not started.”

**Post-3C doc fix (`aea10e6`):** `metrics.py` docstring now accurately states
metrics are **intentionally ungated** (see item 4 below).

---

## Reference map (planner should read these)

| Topic | Primary sources |
|---|---|
| Handoff / constraints | [`orchestrator-handoff.md`](orchestrator-handoff.md) |
| Frontend inventory & Fix #1–#16 | [`frontend-migration.md`](frontend-migration.md) §4 |
| Stakeholder audit → backlog | [`stakeholder-audit-integration.md`](stakeholder-audit-integration.md) |
| Dr. Wang test log classification | [`stakeholder-test-log-audit.md`](../architecture/review/stakeholder-test-log-audit.md) |
| Accountable numbers | [ADR-0011](../architecture/decisions/ADR-0011-accountable-numbers.md) |
| Minimum disclosure / connect | [ADR-0014](../architecture/decisions/ADR-0014-disclosure-consent.md) |
| Event temporal model | [ADR-0010](../architecture/decisions/ADR-0010-event-temporal-model.md) |
| Event identity + tags (G3) | [ADR-0012](../architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md) |
| Points / rewards schema | [ADR-0013](../architecture/decisions/ADR-0013-attendance-derived-engagement.md), [`engagement-model.md`](../architecture/engagement-model.md) |
| Matching gate G1 | [`critical-path-matching-gate.md`](critical-path-matching-gate.md) |
| Backlog D/S/M IDs | [`remaining-foundation-r1-work.md`](remaining-foundation-r1-work.md) |
| Pilot column contract | [`columns.yaml`](../pilot-data/columns.yaml), [`pilot-data/README.md`](../pilot-data/README.md) |

---

## Eight remaining items (classified)

Legend:

- **Engineering** — can be planned and executed once dependencies exist
- **Blocked** — engineering cannot close without an external gate or upstream work
- **Human decision** — requires a named stakeholder / program owner before code

---

### 1. Matching / scoring — registry approved; engine not built

**Classification:** **Engineering** — gate **G1 / D1 closed 2026-09-03** (Danny
Tran @dangt). **M1 landed.** M2–M10 remain build work.

**Current state:**

- `python/smartmatch_domain/smartmatch_domain/factor_registry.py`:
  - `REGISTRY_STATUS = "approved"` (G1 closed 2026-09-03)
  - Approved 2-factor Stage B set: `topic_relevance` 0.70, `travel_burden` 0.30
  - `assert_registry_approved()` no-ops when status is `"approved"`
  - **No scorer implementations** — `topic_relevance` and `travel_burden` are
    declared but not computed (M2, M4)
- Legacy defect documented in module header: 9 declared factors, 7 computed,
  max score **0.90** — porting legacy scores is **forbidden**
  ([`critical-path-matching-gate.md`](critical-path-matching-gate.md) §1b).

**Tests locking behaviour:**

- `tests/unit/test_factor_registry.py::test_registry_is_approved_after_g1` —
  passes since G1 closed
- `tests/unit/test_forbidden_scanner.py` — archived caller-chosen-role patterns

**Frontend surfaces still dark / dishonest if wired early:**

- `apps/web/legacy-frontend/src/app/pages/AIMatching.tsx` — mock ranks (H10)
- `Opportunities.tsx` “Run matcher” → `/ai-matching` (B31)
- [`frontend-migration.md`](frontend-migration.md): no truthful scores until M8
  `match_run` persistence exists

**What “done” looks like (remaining engineering):**

1. ~~Written approval of factor list, weights, golden cases~~ — **done** (G1
   worksheet ratified 2026-09-03)
2. ~~Q6 answered~~ — `historical_conversion` and `student_interest` dropped
3. ~~`REGISTRY_STATUS == "approved"`~~ — **M1 done**
4. **M2–M10** per [`remaining-foundation-r1-work.md`](remaining-foundation-r1-work.md)
   — implement `topic_relevance` + `travel_burden`, eligibility, CP-SAT,
   `match_run` persistence (M8), explanations (M9), scenario comparison (M10);
   W5 control center after M8

**Dependencies / gates:** M1 done → M2, M4 (parallel) → M6 → M7 → M8–M10.
D2 (ELI tuning), D3 (route-matrix provider) block subsets of tuning, not G1.

**Risks:**

- Do not characterize against legacy engine (enshrines 10% deflation)
- Do not display scores without registry version + provenance “heuristic score”
- Golden cases must distinguish unknown vs zero (ADR-0011)

**Not closable without human:** None for G1 — closed. Ongoing weight governance
after G1 is a program-owner concern, not an engineering blocker.

---

### 2. Crawler / event pipeline (R3 build; G3 for live crawl)

**Classification:** **Engineering** for domain prep and R3 implementation.
**R3 threat model signed 2026-09-03** (`docs/decisions/r3-signing-decisions-2026-09-03.md`).
**Live production crawl (S6a) deferred** in synthetic pilot. Gate **G3** still
blocks eval-set approval and live crawl activation.

**Current state:**

- [ADR-0012](../architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md):
  deterministic event key (host org unit + normalized title + resolved date
  window); `unresolved` → no identity key; closed tag vocabulary; quarantine
  unmapped tags
- [ADR-0010](../architecture/decisions/ADR-0010-event-temporal-model.md): precision
  enum; crawler must map extracted dates (Fix #4 temporal half)
- `python/smartmatch_domain/smartmatch_domain/events.py` — domain contract for
  S3–S5; “actual terms deferred to S5 behind gate G3”
- Legacy crawler **archived** — `MM-A08` in migration manifest; do not port
  `CrawlerFeed.tsx` / `POST /api/crawler/start`
  ([`frontend-migration.md`](frontend-migration.md) B27–B28, deliberate non-ports)
- `attendance_record.event_id` has **no FK** — no `event` table yet
  ([`orchestrator-handoff.md`](orchestrator-handoff.md) backlog)

**Tests:**

- `tests/unit/test_events.py` — domain behaviour (entity key, quarantine)
- No HTTP crawler routes in OpenAPI

**What “done” looks like (R3, post-G3):**

1. Crawler threat model signed (SSRF, DNS rebinding, egress) per ADR-0003 / MM-A08
2. S3 event temporal columns on wire
3. S4 deterministic entity-resolution key in persistence
4. S5 closed vocabulary + human review queue for quarantined tags
5. `event` table + FK from `attendance_record.event_id`
6. Extraction writes provenance as field, never in title (ADR-0012)

**Dependencies:** G3 → R3; S3 before S4/S5; ADR-0010 + ADR-0012

**Risks:**

- Rebuilding crawler without output constraints reproduces Fix #4 (dupes, title
  leakage, open-ended tags)
- Do not render quarantined tags or `unresolved` dates in publishable lists
  (H21, [`frontend-migration.md`](frontend-migration.md) Fix #4)

**Not closable without human:** G3 approval + security review of crawl design;
program owner for vocabulary growth process.

---

### 3. Shippable rewards catalog (D6 budget owner)

**Classification:** **Blocked** on human decision **D6** (name budget owner).
**D7 earning rate decided 2026-09-03:** 100 points per verified attendance
(calibration N=3 and reward bands remain tentative in `pilot-decisions.md`).

**Current state — schema done, catalog not:**

- Migration `db/migrations/versions/0009_engagement_schema.py`
- `python/smartmatch_persistence/smartmatch_persistence/schema.py` —
  `reward_item.budget_owner_id NOT NULL`, `reward_item.funded NOT NULL`
- [ADR-0013](../architecture/decisions/ADR-0013-attendance-derived-engagement.md) §
  “A catalog item with a real fulfilment cost needs a named budget owner and a
  funded balance”
- Legacy defect: `studentRewardsCatalog.ts` costs 2,500–45,000 vs 25 pts/event
  (Fix #15) — 100+ events for cheapest item

**Tests locking schema (integration — needs Postgres):**

- `tests/unit/test_engagement_schema.py` — nullability, composite FK
- `tests/integration/test_engagement_schema_constraints.py` —
  `test_reward_item_rejects_a_null_budget_owner`,
  `test_reward_item_rejects_a_null_funded_state`,
  `test_reward_item_accepts_a_named_owner_and_a_funded_balance`

**What “done” looks like:**

1. D6: named `user_account` as `budget_owner_id` for each listable item
2. D7: 100 pts/event recorded (2026-09-03); calibration N and bands still tentative
3. S8 listing API + S9 `redemption` command (requested → approved → fulfilled |
   denied | expired)
4. Frontend: retire `studentRewardsCatalog.ts` / `studentPoints.ts` (H12–H15,
   B11)

**Dependencies:** S6 attendance → S7 ledger fold → S8/S9; D6 before **shipping**
catalog ([`remaining-foundation-r1-work.md`](remaining-foundation-r1-work.md))

**Risks:**

- Do not list unfunded or unowned items (schema refuses — do not weaken)
- Do not use browser formula for points (ADR-0013)
- Progress bars only toward **reachable** rewards (engagement-model §4)

**Not closable without human:** D6 owner identity. D7 partial (100 pts/event only).

---

### 4. Metrics role-gating vs ungated (human decision; ADR-0014)

**Classification:** **Human decision** (product/security). Code is **honest and
intentional** today; not a bug to paper over.

**Current state:**

- `services/api/smartmatch_api/routers/metrics.py::_authorize_unit_read` —
  `assert_allowed` with **no `required_roles`** (lines 142–165, docstring cites
  `INTENTIONALLY_UNGATED_OPERATIONS`)
- `services/api/smartmatch_api/routers/imports.py` — same unit load but
  `required_roles=_IMPORT_ROLES` (`frozenset({"admin", "coordinator"})`, line ~70)
- `tests/authz/test_policy_matrix.py`:
  - `INTENTIONALLY_UNGATED_OPERATIONS = frozenset({"metrics.read", "metrics.drill_down"})`
  - `test_an_intentionally_ungated_operation_admits_any_active_membership`
  - Completeness meta-tests ensure undeclared ungated ops fail CI

**ADR-0014 relevance:** Drill-down returns **underlying rows** (e.g. pending
`review_item.row_data`). Minimum-disclosure policy may require role gate on
drill-down even if aggregates are open — **not decided**.

[`orchestrator-handoff.md`](orchestrator-handoff.md) §Blocker 2: *“Any active
membership at the unit, of any role, can read unit metrics and drill into the
underlying rows… should be chosen, not inherited by accident.”*

**Tests:**

- Authz matrix (above)
- `tests/contract/test_metrics.py` — drill-down count equals aggregate for
  `pending_review_items` (integration)

**What “done” looks like (after decision):**

- **Option A — keep ungated:** Document decision in ADR or policy note; matrix
  unchanged
- **Option B — gate:** Add `required_roles` to `metrics.py` (e.g. mirror
  `_IMPORT_ROLES` or narrower set); update `INTENTIONALLY_UNGATED_OPERATIONS` and
  matrix rows; add negative tests for wrong role

**Dependencies:** None for engineering — **decision first**

**Risks:**

- Weakening to “any authenticated user” without unit membership (current code
  still requires unit-scoped membership via `assert_allowed`)
- Over-gating blocks coordinator dashboards
- Under-gating exposes import row payloads to low-privilege roles (ADR-0014)

**Not closable without human:** Explicit call on metrics.read / metrics.drill_down
role requirements.

---

### 5. `board_role` on professional vs unit relationship (Dr. Wang / columns.yaml)

**Classification:** **Human decision** (Dr. Wang). Engineering has a **holding
position** only.

**Current state:**

[`columns.yaml`](../pilot-data/columns.yaml) `open_questions` (first item):

> *“STILL OPEN -- needs Dr. Wang. Whether "board_role" belongs on a
> *professional* record at all, or is really a property of that person's
> relationship to a specific unit/chapter…”*

Ratified contract lists `board_role` under `professionals.optional` as holding
position — moving it later is a **schema change**, not a rename.

**Not wired to import path yet:**

[`columns.yaml`](../pilot-data/columns.yaml) header: *“still not wired into
application code: smartmatch_worker.handlers calls validate_columns with
required=(), optional=()”* — see `handlers.py` ~570.

**Tests:**

- `docs/pilot-data/verify_fixtures.py` + fixtures under `docs/pilot-data/fixtures/`
- `tests/unit/test_ingest.py` — illustrative, not yet bound to `columns.yaml`

**What “done” looks like:**

1. Dr. Wang decides: flat professional field **vs** unit-relationship record
2. Update `columns.yaml`, fixtures, and (when wired) worker `validate_columns` args
3. If relationship model: new table/column contract + migration (expand-phase)

**Dependencies:** Dr. Wang answer before schema commitment; connect
`columns.yaml` → worker is separate engineering task (J10 import execution)

**Risks:**

- Treating holding position as final answer → wrong pilot imports
- `mockData.ts` Specialist shape is evidence of orphan frontend only
  ([`pilot-data/README.md`](../pilot-data/README.md))

**Not closable without human:** Dr. Wang workshop on data model.

---

### 6. Optional event URL / contact fields (Dr. Wang)

**Classification:** **Human decision** (Dr. Wang). Fields declared optional;
no fixture exercises them.

**Current state:**

[`columns.yaml`](../pilot-data/columns.yaml) `open_questions` (second item) —
`"Public URL"`, `"Point(s) of Contact (published)"`,
`"Contact Email / Phone (published)"`: personal data; pilot collection must be
**deliberate**, not inherited from mock.

Events `optional` in ratified contract includes all three.
[`pilot-data/README.md`](../pilot-data/README.md) §Open questions mirrors this.

**Frontend:**

- `Opportunities.tsx` `mapEventToOpportunity` uses `event["Public URL"]` when
  present (line ~68) — still loads from legacy `/api/data/*` paths, not pilot import

**What “done” looks like:**

1. Dr. Wang: collect or drop each field for pilot
2. If dropped: remove from `columns.yaml` optional + update README
3. If collected: fixtures demonstrating valid/invalid rows; consent/minimization
   review (published contact = PII)

**Dependencies:** Dr. Wang; D8 if contact fields imply disclosure policy

**Risks:**

- Importing published emails/phones without policy (ADR-0014 contact vs
  disclosure distinction)
- Rendering scraped contact in UI without consent path

**Not closable without human:** Dr. Wang on whether pilot collects these fields.

---

### 7. Frontend login — caller-chosen role cards (stakeholder Fix #7)

**Classification:** **Engineering** (UI + A1b auth) — backend already enforces
correct behaviour.

**Current state:**

**Backend (done):**

- MM-A01 archived — `tests/integration/test_command_path.py` asserts the
  caller-selected identity route (`POST /auth/MM-A01`) → **404**
- `tests/contract/test_me.py` — caller cannot pick tenant/user/role
- `tests/unit/test_forbidden_scanner.py` — scans for forbidden patterns

**Frontend (still violates Fix #7 in UX):**

- `apps/web/legacy-frontend/src/app/pages/LoginPage.tsx`:
  - `ROLES` array with canned emails (lines 12–41)
  - Role picker cards UI (lines 102+): *“Select a role to explore…pre-loaded
    demo data”*
  - `handleLogin` no longer POSTs — shows error *“Sign-in is not connected yet”*
    (lines 55–64) — **cards remain**
- `LandingPage.tsx` may still pass `?role=` (H24 in frontend-migration)

[`frontend-migration.md`](frontend-migration.md) Fix #7: *“No caller-chosen role”*
— **Still in the UI**; backend COVERED.

**What “done” looks like:**

1. Remove role cards, demo emails, `?role=` preselect (H01, B02, H24)
2. Wire OIDC / Identity Platform (**A1b** — live JWKS); bearer on API calls
3. Principal from `GET /v1/me` / verified token — no `sessionStorage` role blob
4. Unauthenticated → login; no default identities (`stu-001`, etc.)

**Dependencies:** A1b auth infrastructure; W2 generated client (target app under
`apps/web/`, not legacy copy) per [`frontend-migration.md`](frontend-migration.md)
Phase 1

**Risks:**

- Restoring `mockLogin` or role-in-body POST
- Login that appears to succeed without server agreement

**Not closable without human:** A1b IdP configuration / institutional SSO (ops).

---

### 8. Two “opportunities” pages must agree (Fix #5) — blocked on S12 / S1

**Classification:** **Blocked** on **S12** (funnel persistence + owning query)
and **S1** (metric register entry for “opportunities” with drill-down contract).

**Current state — structural disagreement still present:**

| Surface | What it shows | Source |
|---|---|---|
| `/opportunities` (`Opportunities.tsx`) | Merged CSV events + crawler rows; fabricated crawler `date: "See link for details"`, `role: "Guest speaker"` (H21) | Client-side `fetchEvents` + crawler APIs (legacy `/api/data/*`, missing on new API) |
| Dashboard / Pipeline | Funnel stages via **registered** `pipeline_*` metrics; values **unknown** until S12 | Wave 3C — `useUnitMetrics`, `METRIC_REGISTER` |
| Dashboard copy | Still says “active opportunities” in prose; links to `/opportunities` | `Dashboard.tsx` ~617, 677 |

[ADR-0011](../architecture/decisions/ADR-0011-accountable-numbers.md) Fix #5:
*“Two pages both labelled ‘opportunities’, showing different totals”* — rule 2
(one canonical name) + rule 3 (one owning query).

[`frontend-migration.md`](frontend-migration.md) Fix #5: *“One metric name, one
query, both views subscribe (S1)”* — backend **No**.

**Tests:**

- `tests/contract/test_metrics.py::test_pipeline_unknown_is_null_with_an_empty_drill_down` — pipeline metrics honest-unknown
- No `opportunities` metric in `METRIC_REGISTER` yet
- ADR-0011 rule 4: drill-down count === aggregate (contract test pattern exists for `pending_review_items`)

**What “done” looks like:**

1. Register a canonical **opportunities** metric (written definition — not the
   word alone; ADR-0011: e.g. events in match pool above score floor, excluding
   `unresolved` dates)
2. S12 pipeline persistence → `_pipeline_funnel_rows_v1` backed by real storage
3. `/opportunities` and dashboard/pipeline subscribe to **same** metric(s) or
   clearly distinct registered names (variants get own definitions)
4. Remove crawler fabrication (H21); no unresolved dates in lists (ADR-0010)
5. Clicking N returns exactly N rows (Fix #12 / S1)

**Dependencies:** S12 → funnel metrics; M8 if definition includes score floor;
S3–S5 for event list quality; Wave 3C drill-down UI is template

**Risks:**

- Client-side merge of CSV + crawler recreates #5
- Fabricating opportunity counts while S12 pending
- MetricCard `href` navigation instead of same-query drill-down (B30 — partially
  addressed in 3C for funnel, not opportunities)

**Not closable without human:** Written metric definition for “opportunities”
(stakeholder/product); may overlap M8 if score floor is in definition.

---

## Suggested planning order (dependencies only — not a schedule)

```
Human parallel track:
  D6 (rewards owner) | G3 eval set (live crawl) | metrics authz decision | Dr. Wang columns (5,6)
  ~~D1/G1~~ closed 2026-09-03 | D7 100 pts/event recorded | R3 threat model signed

Engineering (not decision waits):
  M2+M4 → M6 → M7 → M8–M10 (matching) — G1 closed, M1 done
  S12 + opportunities metric (8) after metric definition
  R3/S4/S5 build — threat model signed; no crawl code yet
  S8/S9 catalog after D6 (3)
  Login cleanup + A1b (7) — can proceed in parallel on legacy or new app shell
  columns.yaml → worker wiring — after Dr. Wang (5,6)
  pipeline_record write path — funnel currently structural zero

Deferred by design (synthetic pilot):
  G2 live student data | G4 outreach | G5 Calendar | S6a production crawl |
  S8/S9 rewards ledger | F5 cloud Terraform apply

Immediate ops (user consent):
  git push friday-deliverable-828 → confirm CI green (integration proof)
```

---

## What Dr. Wang can be shown today (from handoff)

**Can:** server-assigned identity path; live import → quarantine; column contract
with named findings; metrics that admit unknown **with reason** + definition +
drill-down for `pending_review_items`; rewards schema refusing unowned reward.

**Cannot:** truthful matching scores (M2–M8 not built); live crawler-fed events
(S6a deferred); shippable rewards catalog (D6).

---

## Gaps / not found in-repo (planner should not invent)

| Gap | Notes |
|---|---|
| **Fix #2 and Fix #14** | [`frontend-migration.md`](frontend-migration.md) §4.1 — “Cannot plan” without test log rows (Q7) |
| **Architecture v1.1 §1.5 full text** | `columns.yaml` cites F-28 — section not in tree; ratified `columns.yaml` is pilot contract, not full v1.1 |
| **`columns.yaml` → worker wiring** | Ratified but `handlers.py` still `validate_columns(..., required=(), optional=())` — no ticket id beyond J10/import execution |
| **Named G1 / D6 owners** | G1: Danny Tran @dangt (closed 2026-09-03). D6: still unnamed. |
| **Metrics authz decision record** | Documented as open in handoff; no ADR amendment choosing gate vs ungated |
| **A1b live JWKS / IdP config** | Authn fixture exists; production OIDC not in tree |
| **Event `read` HTTP API** | No route for events/pipeline/opportunities lists on OpenAPI — only metrics, imports, jobs |
| **Vitest / Playwright in legacy-frontend** | Zero test files; CI tests new `apps/web/` when scaffolded (W1) |
| **Classroom reset tooling** | Mentioned in stakeholder audit — no backlog id |
| **FERPA-aware definition** | Q35 / D8 — not defined in repository |

---

## Quick file index for implementers

| Concern | Path |
|---|---|
| Factor registry / G1 gate | `python/smartmatch_domain/smartmatch_domain/factor_registry.py` |
| Metric register | `python/smartmatch_domain/smartmatch_domain/metrics.py` |
| Metrics HTTP + authz | `services/api/smartmatch_api/routers/metrics.py` |
| Import role gate | `services/api/smartmatch_api/routers/imports.py` |
| Authz policy matrix | `tests/authz/test_policy_matrix.py` |
| Engagement schema | `db/migrations/versions/0009_engagement_schema.py`, `schema.py` |
| Event domain (S3–S5) | `python/smartmatch_domain/smartmatch_domain/events.py` |
| Pilot columns | `docs/pilot-data/columns.yaml` |
| Login UI | `apps/web/legacy-frontend/src/app/pages/LoginPage.tsx` |
| Opportunities UI | `apps/web/legacy-frontend/src/app/pages/Opportunities.tsx` |
| Wave 3C metrics UI | `useUnitMetrics.ts`, `PipelineFunnelTiles.tsx`, `metrics.ts` |
| OpenAPI contract | `contracts/openapi/smartmatch.json` |

---

*End of brief. Update this file when a human decision closes or when CI push
proves integration state.*
