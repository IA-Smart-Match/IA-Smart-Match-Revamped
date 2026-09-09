# Pipeline synthetic production caller — task-card implementation plan

- **Plan id:** `2026-09-03-pipeline-synthetic-caller`
- **Branch:** `pilot/pipeline-synthetic-caller` (worktree `smartmatch-wt-pipeline-caller`, based on `origin/main` @ `02ed018`)
- **Authorization:** `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §1 and §4, plus the coordinator rulings of 2026-09-03 recorded in §1.1 below
- **Migration required:** **Yes — exactly one revision**, `0016_pipeline_record_provenance.py`, revision id `0016_pipeline_provenance`, down-revision `0015_remove_ledger_reversal`. See Decision 3.
- **Task cards:** 8
- **Execution model:** subagent-driven — one fresh implementer per card. Each card is self-contained; every table, column, constraint, function signature and test path it needs is inlined here verbatim. No card may go looking for "the authorization doc" or "the metrics doc".

---

## 0. The problem, in one paragraph

`smartmatch_persistence.pipeline.PipelineRepository` has **no production caller**. A repo-wide grep returns only its own module, one docstring reference at `python/smartmatch_domain/smartmatch_domain/pipeline.py:24`, and `tests/integration/test_pipeline_record_writers.py`. Consequently every `pipeline_funnel_rows_v1` metric (`pipeline_matched`, `pipeline_contacted`, `pipeline_confirmed`, `pipeline_attended`, `pipeline_member_inquiry`) is a permanent **measured zero** for every unit in the compose appliance. This plan wires the coordinator review-accept path — the one path the compose stack already drives end to end (`scripts/compose_smoke.sh`) — to `PipelineRepository`, on synthetic data only, and makes every row it writes **say in the database** that it is synthetic.

---

## 1. Global Constraints (binding on every card)

### 1.1 The authorization, quoted verbatim, and the rulings layered on it

From `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` **§4 Pipeline production caller (item 6)**, quoted in full:

> **Authorized:** Wire **synthetic** import and review-decision paths to call `PipelineRepository` for stakeholder demo, subject to:
>
> 1. G1 registry approval (D1 sign-off) before `matched_at` semantics represent real matching.
> 2. Professional identity: import creates or links `user_account` per professional (Choice A).
> 3. `attendance_record` write path: minimal synthetic writer for Attended-stage CHECK constraints in demo seed flow.
>
> Production live-data callers remain blocked until G2 closes.

And §1's scope boundary, quoted verbatim:

> ### This authorizes
>
> - End-to-end **click-through** stakeholder demos on **synthetic data only**, persisted in PostgreSQL (not client-side mocks).
> - Implementation of product paths (import → review → pipeline → metrics → matching shortlist → coordinator flows) using dev fixtures, seed data, and compose appliance.
>
> ### This does NOT waive
>
> - Legal FERPA, records, or privacy obligations for **live** student data (G2, D8).
>
> **Posture:** Development-only synthetic pilot until a separate public-release planning gate reopens G2–G5 and D3–D5.

**Layered session authority (coordinator rulings, 2026-09-03).** Two requirements binding on this branch do **not** appear in the ratified §4 text above:

- the provenance string `synthetic / coordinator-accepted`, and
- the phrase "review-accept of in-list professionals" as the permitted `record_matched` call site.

Both come from the program owner's direct instruction in this session, which is legitimate authority layered on the decision record. They stand and are binding here.

> **ACTION FOR THE RATIFIER:** `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §4 **should be amended** to record the provenance string `synthetic / coordinator-accepted` and the "review-accept of in-list professionals" call site, so that the gap between the ratified text and what this branch is held to does not persist unnoticed. This is flagged in the PR description. No card in this plan edits that decision record — amending a ratified decision is the ratifier's act, not an implementer's.

### 1.2 The provenance string — persisted, not merely logged

Exactly this string, character for character, defined once and never re-spelled:

```
synthetic / coordinator-accepted
```

It is **stored in the database**, in `pipeline_record.matched_provenance` (`NOT NULL`, CHECK-constrained to a closed vocabulary — Card 1). It is additionally emitted on the structured log line the provisioning service writes, because a log line is useful for operations; but the log is not the record. A provenance that lives only in a log rotates away, and a `pipeline_record` row asserts that a match occurred — `matched_at` is `NOT NULL` precisely because "a record exists because a match does". Once the real matching engine lands on `pilot/match-engine-m2-m7` (PR #12) and writes rows beside these, nothing in a log-only design would distinguish a synthetic row from an engine row, and the D5 retention table keeps pipeline and match evidence for **one year**. A stored value that asserts more than it can support is the defect class the factor registry exists to prevent. Hence the column.

### 1.3 Never a fabricated score

After Card 1, `PipelineRepository.record_matched`'s full signature is:

```python
def record_matched(
    self,
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    subject_id: uuid.UUID,
    opportunity_event_id: uuid.UUID,
    matched_at: datetime,
    matched_provenance: str,
) -> PipelineRecordRow: ...
```

There is **no score, confidence, or rank parameter, and none may be added.** `matched_provenance` is a required keyword argument with **no default**, so no caller anywhere can write a `pipeline_record` row without saying where the match came from.

No card may add a score parameter, add a score column, compute a score, or store one anywhere. The identifiers `score`, `match_score`, `confidence`, `rank`, `ranking`, and `weight` must not appear in any file this plan creates, in any capacity, including comments. `tools/scan_forbidden.py` rule `fabricated-score` already fails any `.py` line matching `(score|confidence|match_score)\s*=\s*(0\.\d+|[1-9]\d*)\s*(#.*)?$`; this plan's rule is stricter than the scanner and is enforced by explicit tests in Cards 1 and 5.

### 1.4 The `pipeline_record` constraints — inviolable, enumerated

From `db/migrations/versions/0011_pipeline_record.py`, plus the one constraint Card 1 adds. **None of these may be weakened, dropped, made deferrable, or worked around.** Constraints 1–9 are reproduced verbatim from `0011` and **`0016` must not touch any of them**.

1. `ck_pipeline_record_stage_prefix`
   ```
   (contacted_at IS NULL OR matched_at IS NOT NULL)
   AND (confirmed_at IS NULL OR contacted_at IS NOT NULL)
   AND (attended_at IS NULL OR confirmed_at IS NOT NULL)
   AND (member_inquiry_at IS NULL OR attended_at IS NOT NULL)
   ```
2. `ck_pipeline_record_stage_order`
   ```
   (contacted_at IS NULL OR contacted_at >= matched_at)
   AND (confirmed_at IS NULL OR confirmed_at >= contacted_at)
   AND (attended_at IS NULL OR attended_at >= confirmed_at)
   AND (member_inquiry_at IS NULL OR member_inquiry_at >= attended_at)
   ```
3. `ck_pipeline_record_attendance_evidence`
   ```
   (attended_at IS NULL) = (attended_attendance_id IS NULL)
   ```
4. `uq_pipeline_record_subject_opportunity` on `(tenant_id, subject_id, opportunity_event_id)` — the idempotency key of `record_matched`.
5. `pipeline_record_pkey` on `(id)`.
6. FK `(tenant_id, owning_unit_id) -> (org_unit.tenant_id, org_unit.id)` `ON DELETE RESTRICT`.
7. FK `(tenant_id, subject_id) -> (user_account.tenant_id, user_account.id)` `ON DELETE RESTRICT` — **this is the constraint that makes an orphan `subject_id` unstorable**, and it is why Choice A identity (Card 3) must run before any `record_matched` call.
8. FK `(tenant_id, attended_attendance_id) -> (attendance_record.tenant_id, attendance_record.id)` `ON DELETE RESTRICT`.
9. `matched_at` is `NOT NULL` with `server_default now()`.
10. **NEW, added by Card 1:** `ck_pipeline_record_matched_provenance` —
    ```
    matched_provenance IN ('synthetic / coordinator-accepted', 'match-engine')
    ```
    and `matched_provenance` is `NOT NULL` with **no server default**.

Neighbouring constraints this plan writes against, also not to be weakened:

- `attendance_record`: `ck_attendance_record_method` = `method IN ('qr_scan','coordinator_entry','import')`; `uq_attendance_record_subject_event` on `(tenant_id, subject_id, event_id)`; `uq_attendance_record_tenant_id` on `(tenant_id, id)`; FKs to `org_unit` and `user_account`, both `ON DELETE RESTRICT`.
- `review_item`: `ck_review_item_status` = `status IN ('pending','accepted','rejected')`; `ck_review_item_decision_evidence` = `(status = 'pending') = (decided_at IS NULL) AND (decided_at IS NULL) = (decided_by IS NULL)`.
- `user_account`: `uq_user_account_external_subject` on `(external_subject)` — **globally unique, not per tenant**; `uq_user_account_tenant_id` on `(tenant_id, id)`; `email` is `NOT NULL`.
- `professional_unit_relationship`: `professional_unit_relationship_pkey` on `(tenant_id, professional_id, unit_id)`; `board_role` `NOT NULL`; FK `(tenant_id, unit_id) -> (org_unit.tenant_id, org_unit.id)` `ON DELETE RESTRICT`. **No `effective_from` / `effective_to` columns may be added** (P9 Gate A §2, current-state only for pilot).

### 1.5 Synthetic-only boundary

- No live data. No live provider call. No network egress from any new code path.
- Every synthetic email is on the `.invalid` reserved TLD. Every synthetic external subject is prefixed `synthetic-professional:`.
- No new code path may run outside the compose/dev appliance without the same `SMARTMATCH_EDITION=dev` guard `tools/seed_pilot.py` already applies (see Card 7).
- G2 is not closed. Nothing in this plan may be presented as a live-data caller.
- The real matching engine is landing separately on `pilot/match-engine-m2-m7` (PR #12). **Do not import from it, depend on it, reference it, or duplicate any of it.** No card may create a module whose name suggests a matcher. Card 1 reserves the `'match-engine'` provenance value as a *slot* for that branch to write into; reserving a slot is not depending on the branch, and no card may write that value.

### 1.6 Authorization: unchanged

- **No new route.** This plan adds zero HTTP endpoints.
- **No unauthenticated caller.** `PipelineRepository` is reached only from inside `POST /v1/review-items/{review_item_id}/decision`, after `charge_quota(...)` and after `assert_allowed(...)` have both already run in `services/api/smartmatch_api/routers/review.py::decide_review_item`.
- `_REVIEW_ROLES = frozenset({"admin", "coordinator"})` in `routers/review.py` **must not change**.
- `REVIEW_DECISION_RATE_LIMIT = RateLimit(operation="review.decide", max_requests=60, window=timedelta(minutes=1))` **must not change**.
- The `assert_allowed(...)` call in `decide_review_item` — its `Resource(resource_type="org_unit", resource_id=str(unit.id), tenant_id=str(principal.tenant_id), owning_unit_path=OrgPath.parse(unit.path))`, its `at=utc_now()`, and its `required_roles=_REVIEW_ROLES` — must be byte-identical after Card 6 as before it.
- `tests/authz/test_policy_matrix.py` derives its rows from the routes in `services/api/smartmatch_api`. Because no route is added and no authorizer or role set changes, **that file must not need editing**. If an implementer finds themselves editing it, they have exceeded their card: stop and report.

### 1.7 Do-not-touch file list

No card may create or modify any of:

- `python/smartmatch_domain/smartmatch_domain/pipeline.py`
- `python/smartmatch_domain/smartmatch_domain/metrics.py`
- `services/api/smartmatch_api/routers/metrics.py`
- `tests/authz/test_policy_matrix.py`
- `docs/decisions/**` — including the authorization record §1.1 says should be amended; amending it is the ratifier's act
- `docker-compose.yml`
- `requirements/*.txt`, `requirements/*.in`, `pyproject.toml`
- `infra/**`, `contracts/**`
- anything under `apps/`

**Card 1 only** may touch `db/migrations/versions/**`, `python/smartmatch_persistence/smartmatch_persistence/schema.py`, `python/smartmatch_persistence/smartmatch_persistence/pipeline.py`, `tests/integration/test_pipeline_record_writers.py`, `tests/integration/test_pipeline_record_constraints.py`, `tests/integration/test_metrics_storage_binding.py`, and `tests/integration/test_check_constraints.py`. Those seven paths are closed to **every other card**.

### 1.8 No new dependency

This plan adds **no** third-party dependency. Every module it writes uses only `uuid`, `logging`, `dataclasses`, `datetime`, `typing`, `collections.abc`, `argparse`, `sqlalchemy`, `alembic`, and existing first-party packages. If any card believes it needs a new dependency, that is a design error: stop and report rather than running `make lock`. (The worktree `.venv` is Python 3.12; CI and both Dockerfiles are Python 3.11, so a lock regenerated here would be wrong.)

### 1.9 House style and gates

- Python target `py311`. `from __future__ import annotations` at the top of every new module.
- `ruff format` (line length 100) and `ruff check` with `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`, `ignore = ["B008"]`. Note `extend-exclude = ["clients/typescript", "db/migrations/versions"]` — migration files are excluded from ruff, but write them in house style anyway.
- `mypy --strict` over `python/` and `services/`.
- Immutability: new value types are `@dataclass(frozen=True, slots=True)`.
- Repositories take a `Session` per call and **never commit** — transaction boundaries belong to the caller. This is the standing convention in `jobs.py`, `review.py`, `redrive.py`, `pipeline.py`, and every new repository in this plan follows it.
- Docstrings: this repository writes long, argumentative module docstrings that state *why*, and state what a module does **not** do as well as what it does. Match that register. Migration docstrings in `db/migrations/versions/` are especially long-form — read `0011_pipeline_record.py` and `0013_review_decision.py` before writing `0016`.
- `tools/scan_forbidden.py` also fails on `load_fixture(`, `demo_mode`, `DEMO_MODE`, and `if demo`. Do not use any of them.
- import-linter contracts: `smartmatch_domain` must not import `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `pydantic_settings`, `httpx`, `requests`, `google`, `boto3`, `os`, `pathlib`, `socket`, `subprocess`, `smartmatch_providers`. `smartmatch_persistence` must not import `fastapi`, `starlette`, `httpx`, `requests`, `subprocess`, `smartmatch_providers`. Layering: `smartmatch_persistence` -> `smartmatch_providers` -> `smartmatch_authz` -> `smartmatch_domain`, outer may use inner, **never the reverse** (so `smartmatch_domain` may not import the provenance vocabulary from `smartmatch_persistence`; the two are pinned equal by test instead — Card 2).
- Integration tests carry `pytestmark = pytest.mark.integration` and are skipped without a live database.

### 1.10 Silent zero is a defect

Anywhere this plan can produce "nothing happened" as an outcome, that outcome must be **visible**, never indistinguishable from success. Specifically: an in-list events accept that finds no linked professionals logs a `WARNING`; the demo seed tool exits non-zero when it advanced zero journeys; and the compose smoke script asserts a positive count rather than merely a successful HTTP status. Each is a requirement on its card, not advice.

---

## 2. Design decisions (made here, not deferred)

### Decision 1 — the caller lives in a shared application-service module inside the API service, called from the review router

**Module:** `services/api/smartmatch_api/pipeline_provisioning.py`
**Call site:** `services/api/smartmatch_api/routers/review.py::decide_review_item`, after `ReviewRepository.decide` has returned `transitioned=True`, before `session.commit()`.

Why, having checked what compose actually runs. `docker-compose.yml` starts `db`, `migrate`, `seed`, `api`, `worker`, `scheduler`. The review decision is served **entirely by `api`**: `routers/review.py`'s own module docstring states the route "is not shaped as a command" and that "A review decision has no such external effect to queue: it is one conditional `UPDATE` against a row already in this database". There is no worker leg to hook. Putting the caller in `smartmatch_worker.handlers` would require inventing a new command type, a new dispatch, and — because a command is submitted through a route — potentially a new authorized operation, which §1.6 forbids and which the session directive explicitly steers away from ("prefer existing import/review commands"). Putting the whole policy inline in the router body would mix HTTP concerns with provisioning policy in a handler already carrying quota, authorization, and three error branches. A separate module in the API service keeps the router thin, gives the policy one testable entry point, and stays inside the layering contract (the API service may import `smartmatch_persistence` and `smartmatch_domain`; `routers/review.py` already imports `ReviewRepository` directly).

It is *not* placed in `smartmatch_persistence` because the decision "which journeys does accepting this row open" is application policy, not storage, and `smartmatch_persistence` is storage-only by contract.

### Decision 2 — identity is created at review-accept, NOT at import. **A reviewer must read this as deliberate, not as an oversight.**

**Accepted by coordinator ruling, 2026-09-03.** §4 item 2 says "import creates or links `user_account` per professional (Choice A)". This plan creates the account at **review-accept** instead.

Why. Architecture v1.1 §1.5, restated in `python/smartmatch_persistence/smartmatch_persistence/review.py`'s own module docstring, is that "a validated import produces review items, **not verified records**". Creating a `user_account` for every quarantined row would manufacture real accounts for rows a coordinator subsequently rejects — verified records produced from unreviewed input, which is precisely the defect the quarantine exists to prevent. The invariant the program owner actually named is **"no orphan `subject_id` exists"**, and creating the account at accept preserves it exactly, because the `pipeline_record` that names that subject is written in the same transaction, at the same moment, and constraint 7 in §1.4 (`FK (tenant_id, subject_id) -> user_account ON DELETE RESTRICT`) makes the alternative unstorable anyway. Accept is the terminal step of the same import→review path §4 authorizes. Taking the literal reading would trade a real architectural rule for a word.

No card may "fix" this back to import-time creation.

### Decision 3 — one migration, and why it is unavoidable

**One revision.** `db/migrations/versions/0016_pipeline_record_provenance.py`, revision id `0016_pipeline_provenance`, down-revision `0015_remove_ledger_reversal` (the current head — `db/migrations/versions/0015_remove_unauthorized_ledger_reversal.py`, verified 2026-09-03).

Why it is unavoidable, having first tried to avoid it. Everything *else* this plan needs already exists: `pipeline_record` (0011), `attendance_record` (0009), `professional_unit_relationship` (0012), `review_item.decided_at`/`decided_by` (0013), `import_batch`/`review_item` (0008), `user_account` (0003/0007). Every primary key this plan writes is a caller-supplied UUID, so deterministic `uuid5` derivation needs no schema support. The plan's first draft therefore proposed no migration and carried provenance on a log line.

That is not survivable, for the reason §1.2 gives: `pipeline_record` has no provenance or source column, `matched_at` is `NOT NULL` with the comment "a record exists because a match does", and a row written by a coordinator's synthetic acceptance therefore asserts a match occurred with nothing in the database recording that it was synthetic. When the engine branch (PR #12) writes rows beside these and M8 adds `match_run`, the two become indistinguishable, and D5 retains both for a year. A log line is not evidence. So the column is the migration this plan spends.

Scope discipline: `0016` adds **one column and one CHECK** and touches nothing else on the table. Constraints 1–9 in §1.4 are not modified, not recreated, and not renamed.

### Decision 4 — the provenance vocabulary, and why these two strings

`ck_pipeline_record_matched_provenance` admits exactly two values:

| Value | Meaning |
|---|---|
| `synthetic / coordinator-accepted` | A coordinator accepted a synthetic, in-list opportunity row in the pilot appliance. **No matching engine ran.** `matched_at` is the moment of that acceptance and asserts nothing about fit. |
| `match-engine` | The row was produced by the matching engine (G1 / M1–M10, landing on `pilot/match-engine-m2-m7`). Reserved slot; **no code in this plan writes it.** |

Why the first value is spelled with a space and a slash rather than as a tidy `snake_case` token: it is the exact string the program owner directed, it is the exact string `SYNTHETIC_MATCH_PROVENANCE` carries, and it is the exact string the log line emits. One spelling, in the constant, in the column, and in the log, cannot drift. A second, tidier spelling for the database would be a second source of truth for the same fact — the defect ADR-0011 rule 4 names.

Why the second value exists now, before any engine writes it: so M8 has a slot to write into and the engine branch needs no migration of its own to become storable. Reserving it is not depending on that branch.

**Adding a member later is a new revision, never an edit to `0016`.** The migration's own docstring must say so. A CHECK edited in place silently changes what every already-stored row was validated against.

### Decision 5 — server default: none, and the backfill that makes that safe

`matched_provenance` is `NOT NULL` with **no server default.** A default would let a future caller omit provenance and still write a row — exactly what §1.3's "no caller can write a row without saying where the match came from" forbids. `record_matched` requires the argument; the database refuses the row without it; there is no third path.

Can rows exist at migration time? In principle no environment has any: `pipeline_record` has never had a production caller (that absence is this plan's whole premise), CI builds a fresh database, `docker compose down -v` discards the volume, and every integration test that writes the table has an autouse cleanup fixture deleting its rows. But "in principle no rows" is not a thing a migration may assume about a developer's laptop, so `0016` upgrades in three statements rather than one:

1. `op.add_column("pipeline_record", sa.Column("matched_provenance", sa.Text(), nullable=True))`
2. `op.execute("UPDATE pipeline_record SET matched_provenance = 'synthetic / coordinator-accepted' WHERE matched_provenance IS NULL")` — any stray pre-existing row was, by construction, not engine-produced; a comment in the migration must say exactly that, and must say the statement is expected to affect zero rows in every environment that matters.
3. `op.alter_column("pipeline_record", "matched_provenance", nullable=False)`

then `op.create_check_constraint(...)`. No `server_default` is set at any point, so none remains afterwards.

### Decision 6 — what accepting a review item actually provisions

The compose smoke path imports the `professionals` dataset (`scripts/compose_smoke.sh` stage 4: `{"dataset": "professionals", "rows": [{"name": "Ada Lovelace", "metro_region": "Portland"}]}`). The `professionals` contract (`docs/pilot-data/columns.yaml`) declares `required: [name, metro_region]`, `optional: [company, title, expertise_tags, initials, pronouns]` — **no email column**, and no `board_role` (removed by P9 Gate A). The `events` contract declares `required: ["Event / Program", "Category"]`.

One accepted row is never a match on its own: a journey needs a subject *and* an opportunity. The rule this plan implements:

- **Accepting a `professionals` review item** → derive a stable synthetic `subject_id`, ensure a `user_account` row exists for it (Choice A), and link it to the batch's `owning_unit_id` in `professional_unit_relationship` with `board_role = "synthetic_pilot_participant"`. No journey is opened (there is no opportunity yet).
- **Accepting an `events` review item whose `category` is IN_LIST** → derive a stable synthetic `opportunity_event_id`, then call `PipelineRepository.record_matched` once for **each professional already linked to that same unit** in `professional_unit_relationship`, ordered by `professional_id`, capped at `MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT = 50`, with `matched_provenance=SYNTHETIC_MATCH_PROVENANCE`. **If zero professionals are linked, log a `WARNING`** (§1.10).
- **Any other dataset, or an `events` row whose category is OUT_OF_LIST or ABSENT** → provision nothing. Return an empty outcome.

In-list is decided by the single ratified implementation `smartmatch_domain.metrics.shape_opportunity_category(category) is OpportunityCategoryShape.IN_LIST`. Do **not** re-implement the rule. The row key is `"category"` (lowercase): `smartmatch_worker.handlers._normalize_row` runs every submitted header through `smartmatch_domain.ingest.normalize_header`, which lower-cases and joins on `_`, so the ratified column `"Category"` is stored in `review_item.row_data` as `"category"`.

`professional_unit_relationship` (migration `0012`) is the join that makes this work and it already exists with no writer. Using it is what lets an events accept find the unit's professionals without inventing a table.

### Decision 7 — idempotency when a coordinator accepts the same professional twice

Four independent layers, in order:

1. **`ReviewRepository.decide` is a conditional `UPDATE ... WHERE status = 'pending'`.** A second decision on the same `review_item` matches zero rows, the router raises `409 review_item_already_decided`, and provisioning is never reached. This alone makes a literal double-accept of one item impossible.
2. **Every derived identifier is a `uuid5`, not a `uuid4`.** The same tenant + unit + professional name always yields the same `subject_id`; the same tenant + review item always yields the same `opportunity_event_id`. Re-running provisioning — from a replayed import that produced a *second* review item for the same person, or from a re-seeded demo — targets the same rows rather than creating parallel ones.
3. **Every insert this plan adds uses `ON CONFLICT ... DO NOTHING` against a named constraint** and then reads the row back: `user_account_pkey`, `professional_unit_relationship_pkey`, `uq_attendance_record_subject_event`.
4. **`record_matched` is already idempotent** on `uq_pipeline_record_subject_opportunity` (`ON CONFLICT DO NOTHING`, then read back), and raises `ConflictingOwningUnitError` if a journey already exists under a different `owning_unit_id` rather than silently absorbing the mismatch.

The whole provisioning runs inside the router's existing single transaction and is committed once by the router's existing `session.commit()`, so a failure anywhere rolls the decision back with it. `record_matched`'s docstring notes it **assumes READ COMMITTED**; the API session is PostgreSQL default READ COMMITTED and no card may change the isolation level.

Consequence worth stating: because two imports of "Ada Lovelace" into the same unit derive the same `subject_id`, accepting both produces **one** `user_account`, **one** relationship row, and — for a later events accept — **one** journey. That is intended, not a bug to be worked around by adding entropy to the derivation.

**Provenance under idempotency (read this).** `record_matched` conflicts on `uq_pipeline_record_subject_opportunity` and does **not** update the existing row, so the provenance of a journey is written **once, by whichever call created it**, and a later call naming a different provenance does not overwrite it. Card 1 must state this explicitly in `record_matched`'s docstring, and must **not** add an `ON CONFLICT DO UPDATE` that would let a synthetic re-accept relabel an engine-produced row (or the reverse). If a row's provenance ever needs to change, that is a deliberate, separate operation and no card in this plan provides one.

### Decision 8 — proving the funnel non-zero end to end

Two independent proofs, both required:

1. **In-process HTTP proof** (Card 8, `tests/integration/test_pipeline_funnel_end_to_end.py`): drive the *real* `POST /v1/review-items/{id}/decision` route through a `TestClient` with a real bearer token and a real `coordinator` membership — the same `_make_client` / `_register_coordinator` shape `tests/integration/test_pipeline_record_writers.py` already uses — then read `GET /v1/units/{unit_id}/metrics` and `GET /v1/units/{unit_id}/metrics/{name}/drill-down` and assert `pipeline_matched >= 1`, `opportunities >= 1`, `unknown_reason is None`, and aggregate == `len(rows)` for each. No assertion in that test may call `PipelineRepository` to obtain a number — they must arrive through the metrics routes, which is ADR-0011 rule 4.
2. **Compose appliance proof** (Card 8, `scripts/compose_smoke.sh`): extend the existing script with new stages that import an `events` row, accept it, and poll `pipeline_matched` to `1` against the running stack. This is the "deployed-in-compose path" acceptance criterion discharged against actual containers rather than an in-process app.

`opportunities_rows_v1` is a separate note: it reads `review_item` rows with `status = 'accepted'` whose `row_data["category"]` is IN_LIST, joined to `import_batch` for unit scoping. It becomes non-zero from the *existing* review-accept route the moment an in-list `events` row is accepted — no new writer is needed for it. Card 8 asserts it anyway, because "the funnel and the opportunity count both move from the same accept" is the demo claim being made.

---

## 3. Cross-card interface contract

Pinned signatures. A card that **produces** one of these must emit it exactly as written; a card that **consumes** one may rely on exactly this and nothing more.

### Produced by Card 1 — `smartmatch_persistence.pipeline` (modified)

```python
MATCH_PROVENANCE_SYNTHETIC_COORDINATOR: Final[str] = "synthetic / coordinator-accepted"
MATCH_PROVENANCE_MATCH_ENGINE: Final[str] = "match-engine"
MATCH_PROVENANCE_VALUES: Final[frozenset[str]] = frozenset(
    {MATCH_PROVENANCE_SYNTHETIC_COORDINATOR, MATCH_PROVENANCE_MATCH_ENGINE}
)


@dataclass(frozen=True, slots=True)
class PipelineRecordRow:
    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    subject_id: uuid.UUID
    opportunity_event_id: uuid.UUID
    matched_at: datetime
    matched_provenance: str
    contacted_at: datetime | None
    confirmed_at: datetime | None
    attended_at: datetime | None
    member_inquiry_at: datetime | None
    attended_attendance_id: uuid.UUID | None


class PipelineRepository:
    def record_matched(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
        matched_at: datetime,
        matched_provenance: str,
    ) -> PipelineRecordRow: ...
```

`matched_provenance` is validated against `MATCH_PROVENANCE_VALUES` in Python before any statement is issued, raising `ValueError`, for the same reason `advance_stage` checks its own preconditions in application code: a caller gets a catchable error naming the argument rather than an `IntegrityError` naming a constraint they may not recognize. The database CHECK remains the backstop.

`PipelineRecordRow.matched_provenance` is placed **immediately after `matched_at`** — the field it qualifies — and `_to_row` reads it from the row. `advance_stage`, `PipelineStageOutcome`, `get`, `_read_by_id`, `_read_by_journey`, and every existing error class are otherwise **unchanged**.

### Produced by Card 2 — `smartmatch_domain.synthetic_pilot`

```python
SYNTHETIC_MATCH_PROVENANCE: Final[str] = "synthetic / coordinator-accepted"
SYNTHETIC_BOARD_ROLE: Final[str] = "synthetic_pilot_participant"
SYNTHETIC_ATTENDANCE_METHOD: Final[str] = "coordinator_entry"
MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT: Final[int] = 50

SYNTHETIC_PROFESSIONAL_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "6f2a1c34-9d5b-4e18-8a70-2b6c4d9e1f03"
)
SYNTHETIC_OPPORTUNITY_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "1c8e7b52-3a40-4f96-b1d7-5e0a92c647db"
)


def synthetic_professional_subject_id(
    *, tenant_id: uuid.UUID, unit_id: uuid.UUID, name: str
) -> uuid.UUID: ...


def synthetic_professional_external_subject(subject_id: uuid.UUID) -> str: ...


def synthetic_professional_email(subject_id: uuid.UUID) -> str: ...


def synthetic_opportunity_event_id(
    *, tenant_id: uuid.UUID, review_item_id: uuid.UUID
) -> uuid.UUID: ...
```

Exact derivations:

- `synthetic_professional_subject_id` returns `uuid.uuid5(SYNTHETIC_PROFESSIONAL_NAMESPACE, f"{tenant_id}:{unit_id}:{name.strip().casefold()}")`. Raises `ValueError` if `name.strip()` is empty.
- `synthetic_professional_external_subject` returns `f"synthetic-professional:{subject_id}"`.
- `synthetic_professional_email` returns `f"professional-{subject_id}@synthetic.invalid"`.
- `synthetic_opportunity_event_id` returns `uuid.uuid5(SYNTHETIC_OPPORTUNITY_NAMESPACE, f"{tenant_id}:{review_item_id}")`.

`SYNTHETIC_MATCH_PROVENANCE` **must equal** `smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`. The layering contract forbids `smartmatch_domain` importing `smartmatch_persistence`, so the two literals are pinned equal by a test in Card 2 rather than by an import. That test is the control; do not "simplify" it away.

### Produced by Card 3 — `smartmatch_persistence.professionals`

```python
class ProfessionalIdentityRepository:
    def ensure_account(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        external_subject: str,
        email: str,
    ) -> bool: ...

    def link_to_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        unit_id: uuid.UUID,
        board_role: str,
    ) -> bool: ...

    def professional_ids_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        limit: int,
    ) -> tuple[uuid.UUID, ...]: ...
```

`ensure_account` returns `True` when *this call's* insert created the row, `False` when it already existed. `link_to_unit` likewise. `professional_ids_for_unit` returns ids ordered by `professional_id` ascending, at most `limit` of them; raises `ValueError` if `limit < 1`. Neither method commits.

### Produced by Card 4 — `smartmatch_persistence.attendance`

```python
ATTENDANCE_METHODS: Final[frozenset[str]] = frozenset({"qr_scan", "coordinator_entry", "import"})


class AttendanceRepository:
    def record_attendance(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
        method: str,
    ) -> uuid.UUID: ...
```

Returns the `attendance_record.id` — freshly inserted, or the one an earlier call already wrote for this `(tenant_id, subject_id, event_id)`. Raises `ValueError` if `method not in ATTENDANCE_METHODS`. Does not commit.

### Produced by Card 5 — `smartmatch_api.pipeline_provisioning`

```python
@dataclass(frozen=True, slots=True)
class ProvisionOutcome:
    professional_subject_id: uuid.UUID | None = None
    opportunity_event_id: uuid.UUID | None = None
    journeys_opened: tuple[uuid.UUID, ...] = ()


def provision_on_accept(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    dataset: str,
    row_data: Mapping[str, Any],
    accepted_at: datetime,
) -> ProvisionOutcome: ...
```

`journeys_opened` holds `pipeline_record.id` values. `accepted_at` must be timezone-aware (it is the router's `now = utc_now()`); `provision_on_accept` passes it straight through as `matched_at`. Does not commit.

### Consumed from existing code (do not re-derive)

```python
# smartmatch_domain.metrics
def shape_opportunity_category(category: str | None) -> OpportunityCategoryShape: ...


# OpportunityCategoryShape.IN_LIST / .OUT_OF_LIST / .ABSENT


# smartmatch_domain.pipeline
class PipelineStage(StrEnum):
    MATCHED = "matched"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    ATTENDED = "attended"
    MEMBER_INQUIRY = "member_inquiry"


# smartmatch_persistence.pipeline — unchanged by this plan
class PipelineRepository:
    def advance_stage(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        record_id: uuid.UUID,
        stage: PipelineStage,
        reached_at: datetime,
        attended_attendance_id: uuid.UUID | None = None,
    ) -> PipelineStageOutcome: ...
```

---

## 4. Ordering and dependencies

```
Card 1 (migration 0016 + record_matched provenance)  ── must land first, alone
   |
   +--> Card 2 (domain constants)   ─┐
   +--> Card 3 (professional ids)   ─┼─> Card 5 (provisioning) ─> Card 6 (router) ─┐
   +--> Card 4 (attendance writer)  ─┘                                              ├─> Card 8 (e2e + smoke)
   |                                                                                |
   +--> Cards 2,3,4 ──────────────────> Card 7 (dev-only demo seed tool) ───────────┘
```

- Card **1 must be merged before any other card starts.** It changes a required argument on `record_matched`; a card written against the old signature will not compile against the new one.
- Cards **2, 3, 4** are independent of each other and may run in parallel once 1 is merged.
- Card **5** requires 1, 2 and 3 merged.
- Card **6** requires 5 merged.
- Card **7** requires 1, 2, 3 and 4 merged. It does not require 5 or 6.
- Card **8** requires 6 and 7 merged.

Each card is independently reviewable and independently green: after every card, `make check` must pass and `make test-integration` must pass against a live database.

---

## 5. How to bring up PostgreSQL for integration tests

Do this once per working session, from the worktree root. The `integration` pytest marker requires a live PostgreSQL 16.

```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller
docker compose up -d db
until docker compose exec -T db pg_isready -U smartmatch -d smartmatch >/dev/null 2>&1; do sleep 1; done
make migrate
make test-integration
```

Notes an implementer must know:

- `docker-compose.yml` publishes `127.0.0.1:5432`. A natively installed PostgreSQL publishes the same port. **Pick one.** If `docker compose up -d db` fails to bind, run `sudo service postgresql stop` first, or use `make db-up` (the native path) instead of the container.
- `SMARTMATCH_DATABASE_URL` defaults to `postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch` in both `Makefile:9` and `tests/integration/conftest.py`, so no configuration is needed once the container is up.
- `make migrate` runs `cd db && ../.venv/bin/alembic upgrade head` from the host `.venv`. That `.venv` is Python 3.12 while CI is 3.11; that is fine for running migrations and tests, and is **not** fine for regenerating locks (see §1.8).
- After Card 1, a database migrated before that card must be brought forward: re-run `make migrate`. `make migrate-check` verifies the whole chain applies cleanly from empty.
- Teardown when finished: `docker compose down -v` (discards the data volume).
- For the full appliance (Card 8's compose stage): `docker compose up --build -d`, then `scripts/compose_smoke.sh`, then `docker compose down -v`.

---

## 6. Task cards

### Card 1 — Persist match provenance: migration `0016`, schema mirror, and a required `record_matched` argument

**Fence.** May create or modify **only**:
- `db/migrations/versions/0016_pipeline_record_provenance.py` (create)
- `python/smartmatch_persistence/smartmatch_persistence/schema.py` (modify)
- `python/smartmatch_persistence/smartmatch_persistence/pipeline.py` (modify)
- `tests/integration/test_pipeline_record_constraints.py` (modify)
- `tests/integration/test_pipeline_record_writers.py` (modify)
- `tests/integration/test_metrics_storage_binding.py` (modify — only if its imported helpers need it)
- `tests/integration/test_check_constraints.py` (modify — add the two registry rows)
- `tests/integration/test_pipeline_provenance_migration.py` (create)

**Depends on.** Nothing. **Must merge before every other card.**

**Work.**

**(a) The migration.** `db/migrations/versions/0016_pipeline_record_provenance.py`:

```python
revision = "0016_pipeline_provenance"
down_revision = "0015_remove_ledger_reversal"
branch_labels = None
depends_on = None
```

Verify the down-revision before writing: `grep -h 'revision = ' db/migrations/versions/0015_remove_unauthorized_ledger_reversal.py` must show `revision = "0015_remove_ledger_reversal"`. **If another migration has landed on `origin/main` in the meantime, re-point `down_revision` at the new head — do not renumber this revision.**

`upgrade()` does exactly four things, in this order, and touches nothing else on the table:

1. `op.add_column("pipeline_record", sa.Column("matched_provenance", sa.Text(), nullable=True))`
2. `op.execute("UPDATE pipeline_record SET matched_provenance = 'synthetic / coordinator-accepted' WHERE matched_provenance IS NULL")` — with a comment stating this is expected to affect **zero** rows in every environment that matters (no production caller has ever written this table), and that a stray developer-laptop row was by construction not engine-produced.
3. `op.alter_column("pipeline_record", "matched_provenance", nullable=False)`
4. `op.create_check_constraint("ck_pipeline_record_matched_provenance", "pipeline_record", "matched_provenance IN ('synthetic / coordinator-accepted', 'match-engine')")`

**No `server_default` at any point.** `downgrade()` drops the constraint then the column, in that order.

Module docstring, in the long-form register of `0011_pipeline_record.py` and `0013_review_decision.py`, must argue:
- Why a `pipeline_record` row without provenance is a claim it cannot support: `matched_at` is `NOT NULL` because "a record exists because a match does", and a synthetic coordinator-accept writes exactly that assertion. Once the matching engine lands beside it and D5 retains both for a year, nothing distinguishes the two.
- Why the vocabulary is closed and exactly these two members (Decision 4's table, restated).
- Why the first value carries a space and a slash: it is one spelling shared by the constant, the column, and the log line, and a tidier second spelling would be a second source of truth for one fact.
- Why there is **no server default** (Decision 5): a default would let a caller omit provenance and still write a row.
- That `'match-engine'` is a reserved slot for G1/M8 and **nothing in this repository writes it today**.
- That **adding a member later is a new revision, never an edit to this file** — a CHECK edited in place silently changes what already-stored rows were validated against.
- That constraints `ck_pipeline_record_stage_prefix`, `ck_pipeline_record_stage_order`, `ck_pipeline_record_attendance_evidence`, `uq_pipeline_record_subject_opportunity` and every foreign key on the table are untouched by this revision.

**(b) `schema.py`.** In the `pipeline_record` table definition, add immediately after the `matched_at` column:

```python
(sa.Column("matched_provenance", sa.Text, nullable=False),)
```

and add to the constraint list:

```python
(
    sa.CheckConstraint(
        "matched_provenance IN ('synthetic / coordinator-accepted', 'match-engine')",
        name="ck_pipeline_record_matched_provenance",
    ),
)
```

with a short mirror comment in the style the rest of `schema.py` uses ("full rationale lives in the migration's module docstring; only what a reader of this mirror needs is repeated here"). No other table changes.

**(c) `pipeline.py`.** Add `MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`, `MATCH_PROVENANCE_MATCH_ENGINE`, and `MATCH_PROVENANCE_VALUES` exactly as pinned in §3. Add `matched_provenance: str` to `PipelineRecordRow` immediately after `matched_at`, read it in `_to_row`, and add `matched_provenance: str` as a **required keyword argument with no default** to `record_matched`, written into the insert's `.values(...)`.

At the top of `record_matched`, before the existing `matched_at.tzinfo` check:

```python
if matched_provenance not in MATCH_PROVENANCE_VALUES:
    raise ValueError(
        f"matched_provenance must be one of {sorted(MATCH_PROVENANCE_VALUES)}, "
        f"not {matched_provenance!r} (ck_pipeline_record_matched_provenance)"
    )
```

Extend `record_matched`'s docstring with two new paragraphs: one on why the argument has no default (a default would let a caller write a row that asserts a match without saying where it came from), and one restating Decision 7's provenance-under-idempotency rule verbatim — the `ON CONFLICT DO NOTHING` means provenance is written once, by whichever call created the row, and a later call naming a different provenance **does not** overwrite it; do not add `ON CONFLICT DO UPDATE`.

`advance_stage`, `PipelineStageOutcome`, `get`, `_read_by_id`, `_read_by_journey`, `_STAGE_COLUMNS`, `_STAGE_COLUMN_NAMES`, and every existing error class are **unchanged**.

**(d) Existing tests.** Update the call sites that now fail to compile or insert:
- `tests/integration/test_pipeline_record_writers.py`: every `repo.record_matched(...)` call gains `matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`. Add one new test asserting the returned `PipelineRecordRow.matched_provenance` equals what was passed, and one asserting `record_matched` raises `ValueError` for `matched_provenance="fabricated"`.
- `tests/integration/test_pipeline_record_constraints.py`: `_insert_pipeline_record`'s raw `INSERT INTO pipeline_record ...` (line ~163) and the second raw insert (line ~616) must supply `matched_provenance`. Give the helper a keyword parameter `matched_provenance: str = "synthetic / coordinator-accepted"` so existing call sites are unchanged and a test can pass a bad value on purpose.
- `tests/integration/test_metrics_storage_binding.py`: only if it breaks — it imports `_insert_pipeline_record` from the constraints file, so the default parameter above should leave it untouched. **Do not edit it otherwise.**
- `tests/integration/test_check_constraints.py`: add one row to the catalogue dict —
  ```
  ("pipeline_record", "ck_pipeline_record_matched_provenance"): (
      "CHECK ((matched_provenance = ANY (ARRAY['synthetic / coordinator-accepted'::text, "
      "'match-engine'::text])))"
  ),
  ```
  and one row to `BEHAVIOURAL_COVERAGE`: `("pipeline_record", "ck_pipeline_record_matched_provenance"): "test_pipeline_provenance_migration.py"`. **Confirm the exact rendered text** by running `select pg_get_constraintdef(oid) from pg_constraint where conname = 'ck_pipeline_record_matched_provenance';` and paste what the database actually returns rather than trusting the string above.

**Tests.** `tests/integration/test_pipeline_provenance_migration.py`, `pytestmark = pytest.mark.integration`, following `tests/integration/migration_harness.py` if that module provides an upgrade/downgrade harness (read it first; reuse rather than reinvent):

1. **NOT NULL is real:** a raw `INSERT INTO pipeline_record (...)` omitting `matched_provenance` raises `IntegrityError` naming a not-null violation on that column.
2. **No server default:** query `information_schema.columns` for `pipeline_record.matched_provenance` and assert `column_default IS NULL` and `is_nullable = 'NO'`.
3. **The CHECK rejects an unknown value:** a raw insert with `matched_provenance = 'engine'`, `'synthetic'`, `''`, or `'SYNTHETIC / COORDINATOR-ACCEPTED'` (wrong case) each raise `IntegrityError` naming `ck_pipeline_record_matched_provenance`.
4. **The CHECK accepts both members:** raw inserts with `'synthetic / coordinator-accepted'` and with `'match-engine'` both succeed.
5. **`record_matched` refuses an unknown value in Python** — `ValueError`, message naming `ck_pipeline_record_matched_provenance` — before any statement reaches the database (assert no row was written).
6. **Round-trip:** `record_matched(..., matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR)` then `get(...)` returns a row whose `matched_provenance` is that exact string.
7. **Provenance is not overwritten by a repeat call:** `record_matched` with `'synthetic / coordinator-accepted'`, then again for the same `(tenant_id, subject_id, opportunity_event_id)` with `'match-engine'`; assert the stored value is still `'synthetic / coordinator-accepted'` and exactly one row exists.
8. **`downgrade` is reversible:** run the migration down then up (via the harness) and assert the column and constraint disappear and reappear, and that the rest of the table's constraints — `ck_pipeline_record_stage_prefix`, `ck_pipeline_record_stage_order`, `ck_pipeline_record_attendance_evidence`, `uq_pipeline_record_subject_opportunity` — are present and unchanged throughout, read from `pg_constraint`.
9. **Negative — the other CHECKs still bite after `0016`:** raw `UPDATE pipeline_record SET contacted_at = matched_at - interval '1 hour'` raises `IntegrityError` naming `ck_pipeline_record_stage_order`; raw `UPDATE pipeline_record SET attended_at = now()` (leaving `attended_attendance_id` NULL) raises `IntegrityError` naming `ck_pipeline_record_attendance_evidence`.
10. **Negative — no fabricated score:** `inspect.getsource` on `smartmatch_persistence.pipeline` contains no line matching the `fabricated-score` pattern, and `inspect.signature(PipelineRepository.record_matched).parameters` has exactly the keys `{"self", "session", "tenant_id", "owning_unit_id", "subject_id", "opportunity_event_id", "matched_at", "matched_provenance"}` — no more.

**Verification commands.**
```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller
docker compose up -d db
until docker compose exec -T db pg_isready -U smartmatch -d smartmatch >/dev/null 2>&1; do sleep 1; done
make migrate
make migrate-check          # the whole chain applies cleanly from empty
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
.venv/bin/pytest tests/integration/test_pipeline_provenance_migration.py -m integration
.venv/bin/pytest tests/integration/test_schema_matches_migration.py -m integration
.venv/bin/pytest tests/integration/test_check_constraints.py -m integration
.venv/bin/pytest tests/ -m integration
.venv/bin/pytest tests/ -m "not integration"
```

**Done when.**
- Exactly **one** new file exists under `db/migrations/versions/`, and `alembic heads` reports a single head.
- `make migrate-check` passes (clean chain from empty).
- `tests/integration/test_schema_matches_migration.py` passes — `schema.py` and the migrated database agree.
- All 10 assertions pass.
- `git diff --stat` lists only the eight fenced paths.
- **PR note required:** this branch must be **rebased onto the latest `origin/main` before merge**. If another migration lands first, re-point `down_revision` at the new head — do **not** renumber `0016`.

---

### Card 2 — Synthetic pilot derivation constants and identifiers (domain)

**Fence.** May create or modify **only**:
- `python/smartmatch_domain/smartmatch_domain/synthetic_pilot.py` (create)
- `tests/unit/test_synthetic_pilot_identity.py` (create)

**Depends on.** Card 1, merged (for the provenance-equality test).

**Work.**

Create `synthetic_pilot.py` with a module docstring stating: this module holds the *pure* derivation rules for the synthetic pilot's stand-in identities; it stores nothing, reaches nothing, and **contains no score of any kind** because no matching engine exists in this repository and the real one is landing on a separate branch; the provenance of every match these identifiers participate in is `SYNTHETIC_MATCH_PROVENANCE`, which is persisted in `pipeline_record.matched_provenance` and is a claim about *who accepted a row*, never a claim about computed fit. It must also state why `SYNTHETIC_MATCH_PROVENANCE` is a literal here rather than an import from `smartmatch_persistence.pipeline`: the import-linter layering contract forbids the domain package importing storage, so the two literals are pinned equal by test instead.

Define exactly the constants and functions pinned in §3 "Produced by Card 2", with those exact names, values, signatures and derivations. Add `__all__` listing every public name, alphabetically.

Additional required behaviour:
- `synthetic_professional_subject_id` raises `ValueError("name must not be blank — a synthetic professional identity derived from an empty name would collide across every unnamed row")` when `name.strip()` is empty.
- Only `uuid` and `typing.Final` are needed. Importing `sqlalchemy`, `os`, `pathlib` or any framework is forbidden by contract.

**Tests.** `tests/unit/test_synthetic_pilot_identity.py`, no marker (unit suite), asserting:
1. `synthetic_professional_subject_id` is **deterministic**: two calls with the same `(tenant_id, unit_id, name)` return the same UUID.
2. It is **case- and whitespace-insensitive** on name: `"Ada Lovelace"`, `"  ada lovelace  "`, `"ADA LOVELACE"` all yield the same id.
3. It **separates units**: the same name under two different `unit_id` values yields different ids.
4. It **separates tenants**: the same name and unit under two different `tenant_id` values yields different ids.
5. It raises `ValueError` for `""` and for `"   "`.
6. `synthetic_opportunity_event_id` is deterministic for the same `(tenant_id, review_item_id)` and differs for a different `review_item_id`.
7. `synthetic_professional_external_subject(x)` starts with the literal `"synthetic-professional:"`.
8. `synthetic_professional_email(x)` ends with the literal `"@synthetic.invalid"`.
9. **Provenance is exact:** `SYNTHETIC_MATCH_PROVENANCE == "synthetic / coordinator-accepted"`.
10. **Provenance is storable — the layering control:** `SYNTHETIC_MATCH_PROVENANCE == smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`, **and** `SYNTHETIC_MATCH_PROVENANCE in smartmatch_persistence.pipeline.MATCH_PROVENANCE_VALUES`. A failure here means the domain constant and the database's CHECK vocabulary have drifted and every synthetic write would raise `IntegrityError` at runtime. Do not delete or weaken this test.
11. **Negative — no fabricated score:** `inspect.getsource` on this module contains none of `"score"`, `"confidence"`, `"match_score"`, `"rank"`, `"weight"` (case-insensitive).
12. `SYNTHETIC_ATTENDANCE_METHOD == "coordinator_entry"` and is **not** `"qr_scan"`.

**Verification commands.**
```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
.venv/bin/pytest tests/unit/test_synthetic_pilot_identity.py
.venv/bin/pytest tests/ -m "not integration"
```

**Done when.**
- Every name in §3 is spelled exactly as pinned.
- All 12 assertions pass, including the provenance-equality control.
- `lint-imports` passes (the module reaches no storage or framework — the equality is asserted in the *test*, not in the module).
- `git status --short` lists only the two fenced files.

---

### Card 3 — Choice A professional identity writers (persistence)

**Fence.** May create or modify **only**:
- `python/smartmatch_persistence/smartmatch_persistence/professionals.py` (create)
- `tests/integration/test_professional_identity_writers.py` (create)

Explicitly **not** `schema.py`, **not** `pipeline.py`, **not** `smartmatch_persistence/__init__.py` (that file re-exports selectively; leave it alone — consumers import from the module path, as `routers/review.py` already does with `from smartmatch_persistence.review import ReviewRepository`).

**Depends on.** Card 1, merged.

**Work.**

Create `professionals.py` implementing `ProfessionalIdentityRepository` exactly as pinned in §3. Module docstring must state: this is Choice A from the synthetic pilot authorization — every synthetic professional gets a real `user_account` row so that `pipeline_record.subject_id`'s `ON DELETE RESTRICT` foreign key to `(user_account.tenant_id, user_account.id)` has something real to point at, and no orphan `subject_id` can exist; the accounts are synthetic, carry `.invalid` emails, are never issued a credential, and are not sign-in identities. It must also record Decision 2 in one paragraph: the account is created at **review-accept**, not at import, because v1.1 §1.5 forbids manufacturing verified records from quarantined rows, and this is a deliberate, ruled-on choice rather than an oversight.

`ensure_account` writes to `user_account`, columns `id`, `tenant_id`, `external_subject`, `email`:
- `postgresql.insert(schema.user_account).values(id=subject_id, tenant_id=tenant_id, external_subject=external_subject, email=email).on_conflict_do_nothing(constraint="user_account_pkey").returning(schema.user_account.c.id)`
- Return `True` if `RETURNING` yielded a row (this call inserted), `False` otherwise. Never infer from a re-read — the same discipline `PipelineStageOutcome.transitioned` documents.
- Document why `user_account_pkey` is the right conflict target and not `uq_user_account_external_subject`: `external_subject` is derived from `subject_id`, so the two constraints cannot disagree. State that if a caller ever supplies an `external_subject` not derived from `subject_id`, `uq_user_account_external_subject` raises `IntegrityError` rather than being silently absorbed, and that this is correct — two different subjects claiming one external identity is not something to swallow.
- Must not write `suspended`, `created_at`, or `version` — all carry server defaults.

`link_to_unit` writes to `professional_unit_relationship`, columns `tenant_id`, `professional_id`, `unit_id`, `board_role`:
- `on_conflict_do_nothing(constraint="professional_unit_relationship_pkey")`, `RETURNING` the `board_role` column, return `True` iff a row came back.
- Must not write `created_at` / `updated_at` (server defaults), and must not add any `effective_from` / `effective_to` notion (P9 Gate A §2).

`professional_ids_for_unit` selects `professional_unit_relationship.professional_id` where `tenant_id` and `unit_id` match, `ORDER BY professional_id`, `LIMIT limit`. Raises `ValueError("limit must be at least 1")` for `limit < 1`. Returns a `tuple`.

No method commits.

**Tests.** `tests/integration/test_professional_identity_writers.py`, `pytestmark = pytest.mark.integration`. Follow `tests/integration/test_pipeline_record_writers.py`'s conventions exactly: `pytest.importorskip("sqlalchemy")`, import `ensure_owning_unit`, `unique_subject`, `JOB_OWNING_UNIT_PATH` from `conftest`, a `db_session_factory` fixture built with `create_session_factory(engine.url.render_as_string(hide_password=False))`, and an `autouse` cleanup fixture deleting this file's rows for the test `tenant_id` in dependency order (`pipeline_record`, `professional_unit_relationship`, `user_account`) so the `tenant_id` fixture's own `ON DELETE RESTRICT` teardown succeeds.

Assert:
1. `ensure_account` returns `True` on first call and `False` on an identical second call; exactly one `user_account` row exists afterwards.
2. The written `external_subject` and `email` are exactly what was passed, and the row's `id` equals the `subject_id` passed.
3. `link_to_unit` returns `True` then `False`; exactly one `professional_unit_relationship` row exists with the `board_role` passed.
4. `professional_ids_for_unit` returns exactly the linked ids, ascending, and honours `limit` (link 3, request `limit=2`, get the two smallest).
5. `professional_ids_for_unit` returns `()` for a unit with no links, and does **not** return ids linked to a *different* unit in the same tenant.
6. `professional_ids_for_unit` raises `ValueError` for `limit=0`.
7. **Negative — no orphan subject_id:** after `ensure_account`, `PipelineRepository().record_matched(..., matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR)` with that `subject_id` succeeds; with a random `uuid4()` `subject_id` that has no `user_account` row it raises `sqlalchemy.exc.IntegrityError` naming the foreign key. Use a separate session/transaction for the failing case so the rollback does not poison the rest of the test.
8. **Negative — a foreign-tenant unit is not reachable:** `professional_ids_for_unit` scoped to tenant A returns nothing for a unit id belonging to tenant B.
9. **Negative — no fabricated score:** `inspect.getsource` on `smartmatch_persistence.professionals` contains none of `"score"`, `"confidence"`, `"match_score"`, `"rank"`, `"weight"` (case-insensitive).

**Verification commands.**
```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller
docker compose up -d db
until docker compose exec -T db pg_isready -U smartmatch -d smartmatch >/dev/null 2>&1; do sleep 1; done
make migrate
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
.venv/bin/pytest tests/integration/test_professional_identity_writers.py -m integration
.venv/bin/pytest tests/ -m "not integration"
```

**Done when.**
- All nine assertions pass against a live database.
- `schema.py` is unmodified; no migration file was created.
- `git status --short` lists only the two fenced files.

---

### Card 4 — Minimal synthetic attendance writer (persistence)

**Fence.** May create or modify **only**:
- `python/smartmatch_persistence/smartmatch_persistence/attendance.py` (create)
- `tests/integration/test_synthetic_attendance_writer.py` (create)

**Depends on.** Card 1, merged.

**Work.**

Create `attendance.py` implementing `ATTENDANCE_METHODS` and `AttendanceRepository.record_attendance` exactly as pinned in §3. Module docstring must state: this is the minimal `attendance_record` writer the synthetic pilot authorization allows so that the Attended funnel stage's CHECK — `ck_pipeline_record_attendance_evidence`, `(attended_at IS NULL) = (attended_attendance_id IS NULL)` — can be satisfied in the demo seed flow; it is **not** a QR scanning path, **not** a live event check-in, and **not** an engagement API; `routers/engagement.py` remains a declared-empty stub and this module gives it nothing.

Implementation:
- Validate `method` against `ATTENDANCE_METHODS` first and raise `ValueError(f"method must be one of {sorted(ATTENDANCE_METHODS)}, not {method!r} (ck_attendance_record_method)")`. Refused in Python before any statement, the same posture `PipelineRepository.advance_stage` takes for its own preconditions.
- `postgresql.insert(schema.attendance_record).values(id=uuid.uuid4(), tenant_id=..., owning_unit_id=..., subject_id=..., event_id=..., method=...).on_conflict_do_nothing(constraint="uq_attendance_record_subject_event")`, then `SELECT id FROM attendance_record WHERE tenant_id = :t AND subject_id = :s AND event_id = :e` and return it. If the read-back finds nothing, raise `RuntimeError` naming the three key values and stating it should be unreachable — mirroring `record_matched`'s own unreachable branch, and deliberately not an `assert` (compiled out under `python -O`).
- Do not write `created_at` (server default). Does not commit.

**Tests.** `tests/integration/test_synthetic_attendance_writer.py`, `pytestmark = pytest.mark.integration`, same fixture conventions as Card 3 (autouse cleanup deleting `pipeline_record`, `attendance_record`, `user_account` for the test tenant, in that order).

Assert:
1. `record_attendance` with `method="coordinator_entry"` writes one row and returns its id.
2. A second identical call returns the **same** id and leaves exactly one row (`uq_attendance_record_subject_event` idempotency).
3. A call with a different `event_id` for the same subject writes a **second** row with a different id.
4. `record_attendance` raises `ValueError` for `method="fabricated"`, message naming `ck_attendance_record_method`.
5. `record_attendance` accepts `"qr_scan"` and `"import"` as legal enum values (the constraint's own vocabulary), while `smartmatch_domain.synthetic_pilot.SYNTHETIC_ATTENDANCE_METHOD` is `"coordinator_entry"` — the writer is capable of the vocabulary, the synthetic path uses only the coordinator-entry member.
6. **Negative — CHECK still enforced:** a raw `INSERT INTO attendance_record ... method = 'fabricated'` via `text()` raises `IntegrityError` naming `ck_attendance_record_method`. This proves the Python guard did not replace the database's own.
7. **Negative — the Attended biconditional still holds:** using `PipelineRepository`, open a journey with `matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`, advance it to `CONTACTED` and `CONFIRMED`, then call `advance_stage(stage=PipelineStage.ATTENDED, reached_at=..., attended_attendance_id=None)` and assert it raises `ValueError`; then call it with the id this card's writer returned and assert `outcome.transitioned is True` and the resulting row has both `attended_at` and `attended_attendance_id` set.
8. **Negative — orphan evidence is refused:** `advance_stage(stage=ATTENDED, attended_attendance_id=uuid.uuid4())` raises `UnknownAttendanceEvidenceError`.
9. **Negative — no fabricated score:** `inspect.getsource` on `smartmatch_persistence.attendance` contains none of `"score"`, `"confidence"`, `"match_score"`, `"rank"`, `"weight"` (case-insensitive).

**Verification commands.** Identical to Card 3's, substituting `.venv/bin/pytest tests/integration/test_synthetic_attendance_writer.py -m integration`.

**Done when.**
- All nine assertions pass against a live database.
- No route, no router, and no `engagement.py` file was touched.
- `git status --short` lists only the two fenced files.

---

### Card 5 — The provisioning application service (API)

**Fence.** May create or modify **only**:
- `services/api/smartmatch_api/pipeline_provisioning.py` (create)
- `tests/integration/test_pipeline_provisioning.py` (create)

Explicitly **not** `routers/review.py` — that is Card 6.

**Depends on.** Cards 1, 2 and 3, merged.

**Work.**

Create `pipeline_provisioning.py` implementing `ProvisionOutcome` and `provision_on_accept` exactly as pinned in §3. Module docstring must state, at length: what this module is authorized to do (§4 of the synthetic pilot authorization, quoted); that its `matched_at` represents a **coordinator's acceptance**, not a computed fit; that every row it writes carries `matched_provenance = "synthetic / coordinator-accepted"` **in the database**, so the claim is auditable a year later rather than resting on a log line; that it **cannot** write a match score because `PipelineRepository.record_matched` has no parameter for one and this module introduces none; that the real matching engine is landing on a separate branch and this module must not grow toward it; and that every id it derives is a `uuid5`, so re-running it converges rather than multiplying rows.

Module-level:
```python
logger = logging.getLogger(__name__)

_professionals = ProfessionalIdentityRepository()
_pipeline = PipelineRepository()

PROFESSIONALS_DATASET: Final[str] = "professionals"
EVENTS_DATASET: Final[str] = "events"
PROFESSIONAL_NAME_KEY: Final[str] = "name"
EVENT_CATEGORY_KEY: Final[str] = "category"
```

`provision_on_accept` behaviour, in order:

1. If `accepted_at.tzinfo is None`, raise `ValueError("accepted_at must be timezone-aware")`.
2. If `dataset == PROFESSIONALS_DATASET`:
   - Read `row_data.get(PROFESSIONAL_NAME_KEY)`. If it is not a `str` or is blank after `.strip()`, emit `logger.warning` naming `review_item_id` and return `ProvisionOutcome()` — an accepted professionals row with no name is a row this module cannot give a stable identity, and inventing one would collide every unnamed row onto a single account.
   - `subject_id = synthetic_professional_subject_id(tenant_id=tenant_id, unit_id=owning_unit_id, name=name)`.
   - `_professionals.ensure_account(session, tenant_id=tenant_id, subject_id=subject_id, external_subject=synthetic_professional_external_subject(subject_id), email=synthetic_professional_email(subject_id))`.
   - `_professionals.link_to_unit(session, tenant_id=tenant_id, professional_id=subject_id, unit_id=owning_unit_id, board_role=SYNTHETIC_BOARD_ROLE)`.
   - Return `ProvisionOutcome(professional_subject_id=subject_id)`.
3. If `dataset == EVENTS_DATASET`:
   - `category = row_data.get(EVENT_CATEGORY_KEY)`; coerce anything that is not a `str` to `None`.
   - If `shape_opportunity_category(category) is not OpportunityCategoryShape.IN_LIST`, return `ProvisionOutcome()`. Do not re-implement the rule and do not treat out-of-list as an error — the ratified definition says out-of-list is pending coordinator review, not invalid.
   - `opportunity_event_id = synthetic_opportunity_event_id(tenant_id=tenant_id, review_item_id=review_item_id)`.
   - `subject_ids = _professionals.professional_ids_for_unit(session, tenant_id=tenant_id, unit_id=owning_unit_id, limit=MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT)`.
   - **§1.10 — silent zero is a defect.** If `subject_ids` is empty, emit
     ```python
     logger.warning(
         "accepted in-list events review_item %s in unit %s opened NO pipeline "
         "journeys: no professionals are linked to this unit yet. Accept the "
         "professionals rows for this unit first.",
         review_item_id,
         owning_unit_id,
     )
     ```
     and return `ProvisionOutcome(opportunity_event_id=opportunity_event_id)` with `journeys_opened=()`. Do **not** raise — the coordinator's decision is still valid and must still be recorded; what must not happen is the zero passing unremarked.
   - Otherwise, for each `subject_id` in order, call
     ```python
     record = _pipeline.record_matched(
         session,
         tenant_id=tenant_id,
         owning_unit_id=owning_unit_id,
         subject_id=subject_id,
         opportunity_event_id=opportunity_event_id,
         matched_at=accepted_at,
         matched_provenance=SYNTHETIC_MATCH_PROVENANCE,
     )
     ```
     collecting `record.id`.
   - Emit exactly one `logger.info` line carrying the provenance:
     ```python
     logger.info(
         "opened %d synthetic pipeline journey(s) for review_item %s in unit %s; provenance=%s",
         len(journeys),
         review_item_id,
         owning_unit_id,
         SYNTHETIC_MATCH_PROVENANCE,
     )
     ```
   - Return `ProvisionOutcome(opportunity_event_id=..., journeys_opened=tuple(journeys))`.
4. Any other `dataset`: return `ProvisionOutcome()` and log nothing. An unrecognised dataset is not an error here — the import contract already refused unknown datasets at `smartmatch_worker.handlers._dataset_contract`.

`ConflictingOwningUnitError` from `record_matched` must **not** be swallowed: let it propagate so the router's transaction rolls back and the decision is not recorded against a journey belonging to a different unit.

**Tests.** `tests/integration/test_pipeline_provisioning.py`, `pytestmark = pytest.mark.integration`. Call `provision_on_accept` directly against a real session (no HTTP — that is Card 8). Autouse cleanup deletes, in order: `pipeline_record`, `professional_unit_relationship`, `user_account`.

Assert:
1. Accepting a professionals row writes one `user_account` whose `id` equals `synthetic_professional_subject_id(...)`, and one `professional_unit_relationship` with `board_role == "synthetic_pilot_participant"`. `outcome.journeys_opened == ()`.
2. Accepting the same professionals row twice leaves exactly one account and one relationship.
3. A professionals row whose `name` is `""`, `"   "`, missing, or a non-string returns `ProvisionOutcome()`, writes nothing, and emits a `WARNING`.
4. An events row with `category = "hackathon"` after two professionals were provisioned opens exactly **two** `pipeline_record` rows, all with the same `opportunity_event_id`, `owning_unit_id` equal to the batch's unit, `matched_at` equal to the `accepted_at` passed, and **`matched_provenance == "synthetic / coordinator-accepted"` read back from the database**.
5. An events row with `category = "some unmapped label"` (OUT_OF_LIST) opens **zero** journeys and returns `ProvisionOutcome()`; `SELECT count(*) FROM pipeline_record` for the tenant is unchanged.
6. Same for a missing / blank category (ABSENT).
7. Accepting the same events row twice opens the same journeys (same `pipeline_record.id` values), not four rows.
8. Fan-out is capped: provision 55 professionals, accept one in-list events row, assert exactly `50` journeys opened and that they are the 50 smallest `professional_id` values.
9. `provision_on_accept` raises `ValueError` for a naive `accepted_at`.
10. **§1.10 — the empty-unit warning fires:** accepting an in-list events row in a unit with **no** linked professionals returns `journeys_opened == ()`, writes no `pipeline_record`, and — with `caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning")` — emits exactly one `WARNING` whose message contains `"opened NO pipeline journeys"`. Zero must never be silent.
11. **Provenance is logged, exactly once, verbatim:** with `caplog.at_level(logging.INFO, ...)`, an in-list events accept with professionals present produces exactly one `INFO` record whose formatted message contains the literal `"synthetic / coordinator-accepted"`.
12. **Negative — no fabricated score:** `inspect.getsource` on `smartmatch_api.pipeline_provisioning` contains none of `"score"`, `"confidence"`, `"match_score"`, `"rank"`, `"weight"` (case-insensitive); **and** `inspect.signature(PipelineRepository.record_matched).parameters` has exactly the keys `{"self", "session", "tenant_id", "owning_unit_id", "subject_id", "opportunity_event_id", "matched_at", "matched_provenance"}`.
13. **Negative — no orphan subject_id:** every `pipeline_record.subject_id` written resolves to a `user_account` row in the same tenant (SQL `LEFT JOIN` returning no unmatched rows).
14. **Negative — the CHECKs still bite:** raw `UPDATE pipeline_record SET contacted_at = matched_at - interval '1 hour'` raises `IntegrityError` naming `ck_pipeline_record_stage_order`; raw `UPDATE pipeline_record SET attended_at = now()` (leaving `attended_attendance_id` NULL) raises `IntegrityError` naming `ck_pipeline_record_attendance_evidence`; raw `UPDATE pipeline_record SET matched_provenance = 'engine'` raises `IntegrityError` naming `ck_pipeline_record_matched_provenance`.
15. **Negative — conflicting unit propagates:** provision one professional under unit A and open a journey under unit A; then call `record_matched` for the same `(subject_id, opportunity_event_id)` under unit B and assert `ConflictingOwningUnitError` rather than silent absorption.

**Verification commands.** As Card 3, substituting `.venv/bin/pytest tests/integration/test_pipeline_provisioning.py -m integration`.

**Done when.**
- All 15 assertions pass.
- `routers/review.py` is unmodified.
- `git status --short` lists only the two fenced files.

---

### Card 6 — Wire the provisioning service into the review-decision route

**Fence.** May create or modify **only**:
- `services/api/smartmatch_api/routers/review.py` (modify)
- `tests/integration/test_review_accept_opens_pipeline.py` (create)

**Depends on.** Card 5, merged.

**Work.**

Two changes to `routers/review.py`, and nothing else.

**(a) Extend the loaded context.** `_load_owning_unit_or_404` currently returns `_OwningUnit(id, path)`. It must also return the batch's `dataset` and the item's `row_data`, both reachable in the same join. Replace the dataclass with:

```python
@dataclass(frozen=True, slots=True)
class _ReviewItemContext:
    """What this router needs about a review item: the unit it authorizes
    against, and the row a synthetic acceptance provisions from."""

    unit_id: uuid.UUID
    unit_path: str
    dataset: str
    row_data: Mapping[str, Any]
```

Rename `_load_owning_unit_or_404` to `_load_review_item_context_or_404`, keeping its signature `(session: Session, *, tenant_id: uuid.UUID, review_item_id: uuid.UUID) -> _ReviewItemContext` and its existing docstring argument about inner joins and 404-not-403, extended with one paragraph on why `dataset` and `row_data` are read in the *same* query rather than a second one: a second read could observe a different row, and the authorization and the provisioning must be about the same row.

Add to the existing `sa.select(...)`, alongside the two current columns:
```python
(schema.import_batch.c.dataset,)
(schema.review_item.c.row_data,)
```
The `select_from`, both `join`s, and both `where` clauses are **unchanged**.

**(b) Call the provisioning service.** In `decide_review_item`, immediately after the `if not outcome.transitioned:` 409 branch and **before** `session.commit()`:

```python
if body.decision == "accepted":
    provision_on_accept(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=context.unit_id,
        review_item_id=review_item_id,
        dataset=context.dataset,
        row_data=context.row_data,
        accepted_at=now,
    )
```

`now` is the handler's existing `now = utc_now()` — the same instant written to `review_item.decided_at`, so `matched_at` and the decision it derives from are one timestamp, not two. The provisioning runs inside the handler's existing transaction and is committed by the existing `session.commit()`; if it raises, the decision rolls back with it.

Update the handler docstring: a rejection provisions nothing; an acceptance may open synthetic pipeline journeys whose `matched_at` is this coordinator's acceptance and nothing more; every such row stores `matched_provenance = "synthetic / coordinator-accepted"`; and no score is written or computed anywhere on this path.

**Must not change, in any way:** `_REVIEW_ROLES`, `REVIEW_DECISION_RATE_LIMIT`, `ReviewDecisionValue`, `ReviewDecisionRequest`, `ReviewDecisionResponse`; the `charge_quota(...)` call or its position (first); the `assert_allowed(...)` call, its `Resource(...)` construction, its `at=utc_now()`, or its `required_roles=_REVIEW_ROLES`; the route decorator, path, `status_code`, `response_model`, or `summary`; the 404 / 409 branches and their `code` strings `review_item_not_found` and `review_item_already_decided`; the response body.

Because the route's shape and its authorizer are unchanged, `contracts/openapi/smartmatch.json` must not change either — verify with `make openapi-check`.

**Tests.** `tests/integration/test_review_accept_opens_pipeline.py`, `pytestmark = pytest.mark.integration`. Drive the real HTTP route with `TestClient`, `FixtureTokenVerifier`, and a real `coordinator` membership, copying the `_make_client` and `_register_coordinator` helpers' shape from `tests/integration/test_pipeline_record_writers.py` (lines ~718–757) — insert `user_account` + `membership` with `granted_path = JOB_OWNING_UNIT_PATH` and role `'coordinator'`, then `client.app.state.token_verifier.register(token, subject)`.

Seed review items with `ReviewRepository().create_batch_with_items(...)`, which needs a real `job` row — reuse whatever helper `tests/integration/test_import_review_constraints.py` already uses rather than inventing a new one.

Assert:
1. `POST /v1/review-items/{id}/decision {"decision": "accepted"}` on a `professionals` item returns `200`; a `user_account` + `professional_unit_relationship` row now exist for the derived `subject_id`.
2. Then accepting an in-list `events` item (`category: "hackathon"`) returns `200`; one `pipeline_record` row now exists with that unit's `owning_unit_id` and `matched_provenance == "synthetic / coordinator-accepted"` read back from the database.
3. `{"decision": "rejected"}` on a professionals item returns `200` and provisions **nothing** (no `user_account` beyond the coordinator's own, no relationship, no `pipeline_record`).
4. A second decision on the same item returns `409` with `code == "review_item_already_decided"` and does not double-provision.
5. **Negative — authorization unchanged:** a principal with role `student` (membership at the same path) gets `403` and provisions nothing; a principal with **no** membership gets `403`; an unauthenticated request (no `Authorization` header) gets `401` and provisions nothing. Assert `SELECT count(*) FROM pipeline_record` is zero after each.
6. **Negative — cross-tenant:** a valid review-item id from tenant B, requested by a coordinator in tenant A, returns `404` (not `403`) and provisions nothing.
7. **Negative — a rejected item never becomes an opportunity:** after rejecting the in-list events item, `GET /v1/units/{unit_id}/metrics` reports `opportunities == 0`.
8. **Negative — response shape unchanged:** the decision response body has exactly the keys `{"id", "status", "decided_at"}` — no provenance, no journey count, no score.

**Verification commands.**
```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller
docker compose up -d db
until docker compose exec -T db pg_isready -U smartmatch -d smartmatch >/dev/null 2>&1; do sleep 1; done
make migrate
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy python/ services/
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence" .venv/bin/lint-imports --config pyproject.toml
.venv/bin/python tools/scan_forbidden.py
make openapi-check
.venv/bin/pytest tests/authz -m "not integration"
.venv/bin/pytest tests/integration/test_review_accept_opens_pipeline.py -m integration
.venv/bin/pytest tests/ -m "not integration"
```

**Done when.**
- All eight assertions pass.
- `make openapi-check` passes with no regeneration.
- `tests/authz/test_policy_matrix.py` passes **unmodified**.
- `git diff --stat` shows changes only in `services/api/smartmatch_api/routers/review.py` plus the one new test file.

---

### Card 7 — Dev-only demo seed tool: advance a journey to Attended, and fail loudly on zero

**Fence.** May create or modify **only**:
- `tools/seed_demo_pipeline.py` (create)
- `tests/integration/test_seed_demo_pipeline.py` (create)

Explicitly **not** `tools/seed_pilot.py`, **not** `docker-compose.yml`, **not** `Makefile`.

**Depends on.** Cards 1, 2, 3 and 4, merged.

**Work.**

Create an operator tool in the same shape and with the same guard as `tools/seed_pilot.py`. It refuses to run unless **both** `SMARTMATCH_EDITION=dev` and `SMARTMATCH_USE_FIXTURE_PROVIDERS=true`, with the same refusal-message pattern `seed_pilot.py` uses at its line ~41 (`"seed-pilot requires SMARTMATCH_EDITION=dev and SMARTMATCH_USE_FIXTURE_PROVIDERS=true."` — write the analogous sentence naming `seed-demo-pipeline`).

Module docstring must state: this walks already-open synthetic journeys through the remaining funnel stages so a stakeholder demo shows a funnel with depth rather than a single Matched bar; it is an **operator tool**, not part of either shipped image, is not importable by any route, and writes attendance with method `"coordinator_entry"` — **never** `"qr_scan"`, because no QR path exists and claiming one would be the fabricated-evidence defect `ck_pipeline_record_attendance_evidence` exists to prevent.

CLI, via `argparse`:
- `--tenant-slug` (default `"pilot"`)
- `--unit-path` (default `"pilot"`)
- `--through` (choices `contacted`, `confirmed`, `attended`, `member_inquiry`; default `attended`)
- `--limit` (int, default `1`)
- `--allow-empty` (store_true, default off) — see the loud-failure requirement below

Behaviour:
1. Resolve `tenant_id` from `tenant.slug` and `unit_id` from `org_unit.path` (cast to `ltree`); print to stderr and `return 1` if either is missing.
2. Select up to `--limit` `pipeline_record` rows for that `(tenant_id, owning_unit_id)`, ordered by `matched_at, id`.
3. **§1.10 — silent zero is a defect. This is a hard requirement, not a note.** If zero rows were selected, or if the walk advanced zero stages in total, the tool must print to stderr an explicit message naming the unit and saying what to do — e.g. `"seed-demo-pipeline advanced 0 journeys in unit 'pilot': no pipeline_record rows exist there yet. Accept a professionals row and then an in-list events row first, or pass --allow-empty."` — and **`return 1`**. `--allow-empty` downgrades it to a warning on stderr and `return 0`, for callers that genuinely tolerate a no-op. A silent, successful zero is not an available outcome.
4. Otherwise, for each selected journey, walk `PipelineStage.CONTACTED`, `CONFIRMED`, `ATTENDED`, `MEMBER_INQUIRY` in order, stopping after `--through`. Timestamps are strictly non-decreasing and derived from the row's own `matched_at`: stage *i* gets `matched_at + timedelta(minutes=10 * i)`. This satisfies `ck_pipeline_record_stage_order` by construction. Skip a stage whose `advance_stage` returns `already_reached=True`.
5. For `ATTENDED`, first call `AttendanceRepository().record_attendance(session, tenant_id=..., owning_unit_id=..., subject_id=<the record's subject_id>, event_id=<the record's opportunity_event_id>, method=SYNTHETIC_ATTENDANCE_METHOD)` and pass the returned id as `attended_attendance_id`. Using the journey's own `opportunity_event_id` as the attendance `event_id` is deliberate: it makes the cited evidence about the same opportunity the journey names, and `uq_attendance_record_subject_event` then makes re-running the tool idempotent.
6. Commit once per journey. Print a one-line summary per journey **and a final line reporting the total number of journeys advanced** — the count must always be visible, whatever it is.
7. `return 0` on success.

`main(argv: Sequence[str] | None = None) -> int` and `parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace`, matching `seed_pilot.py`'s shape so the tool is testable without a subprocess.

This tool does **not** call `record_matched` and therefore writes no provenance; it only advances journeys another writer already opened. Say so in the docstring, so a reader does not go looking for a provenance argument here.

**Tests.** `tests/integration/test_seed_demo_pipeline.py`, `pytestmark = pytest.mark.integration`. Import the tool as a module (`pyproject.toml` puts the repository root on `pythonpath`, which is how the other `tools/` scripts are tested). Autouse cleanup deletes `pipeline_record`, `attendance_record`, `professional_unit_relationship`, `user_account`.

Assert:
1. With `SMARTMATCH_EDITION` unset (monkeypatch `delenv`), `main([...])` refuses — non-zero return or raise — and writes nothing.
2. Same for `SMARTMATCH_USE_FIXTURE_PROVIDERS` unset.
3. With both set and one journey present, `--through attended` leaves the row with `contacted_at`, `confirmed_at`, `attended_at` all non-null and non-decreasing, and `attended_attendance_id` pointing at a real `attendance_record` row whose `method` is exactly `"coordinator_entry"`.
4. Re-running the same command is idempotent: the same `attendance_record.id` is cited, no second attendance row exists, and the stage timestamps are unchanged.
5. `--through contacted` sets only `contacted_at`; `confirmed_at`, `attended_at`, `member_inquiry_at` stay `NULL`.
6. `--limit 2` with three journeys advances exactly two, chosen by `(matched_at, id)` order.
7. **§1.10 — zero fails loudly:** with **no** `pipeline_record` rows in the unit, `main([...])` returns **non-zero** and its stderr names the unit and says what to do. With `--allow-empty`, the same situation returns `0` and still writes a message to stderr. Assert both.
8. **The count is always reported:** the final stdout line contains the number of journeys advanced, in both the zero case (with `--allow-empty`) and the non-zero case.
9. **Negative — never QR:** no `attendance_record` row this tool writes has `method = 'qr_scan'`, and `inspect.getsource` on the tool module does not contain the literal `"qr_scan"`.
10. **Negative — CHECKs still enforced:** raw `UPDATE pipeline_record SET attended_attendance_id = NULL WHERE attended_at IS NOT NULL` raises `IntegrityError` naming `ck_pipeline_record_attendance_evidence`.
11. **Negative — provenance untouched:** after the walk, every advanced row's `matched_provenance` is still `"synthetic / coordinator-accepted"` — `advance_stage` does not rewrite it.
12. **Negative — no fabricated score:** `inspect.getsource` on the tool contains none of `"score"`, `"confidence"`, `"match_score"`, `"rank"`, `"weight"` (case-insensitive).

**Verification commands.** As Card 3, substituting `.venv/bin/pytest tests/integration/test_seed_demo_pipeline.py -m integration`. Also run the tool by hand once against the compose database, and confirm both the zero path and the success path:
```bash
SMARTMATCH_EDITION=dev SMARTMATCH_USE_FIXTURE_PROVIDERS=true \
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence:services/api" \
.venv/bin/python tools/seed_demo_pipeline.py --unit-path pilot --through attended; echo "exit=$?"
```

**Done when.**
- All 12 assertions pass.
- The tool refuses to run outside dev edition, and **never** exits `0` on a silent zero without `--allow-empty`.
- `git status --short` lists only the two fenced files.

---

### Card 8 — End-to-end proof: funnel metrics non-zero, in-process and in compose

**Fence.** May create or modify **only**:
- `tests/integration/test_pipeline_funnel_end_to_end.py` (create)
- `scripts/compose_smoke.sh` (modify — append stages only)
- `INSTALL.md` (modify — document the new smoke stages)

**Depends on.** Cards 6 and 7, merged.

**Work — part A, in-process HTTP proof.**

`tests/integration/test_pipeline_funnel_end_to_end.py`, `pytestmark = pytest.mark.integration`. One test walking the whole path through **routes only**:

1. Seed a tenant, a unit at `JOB_OWNING_UNIT_PATH`, and a `coordinator` principal with a fixture bearer token.
2. Create a `professionals` import batch with two rows via `ReviewRepository.create_batch_with_items`, then `POST /v1/review-items/{id}/decision {"decision": "accepted"}` for each — through the route, with the bearer header.
3. Create an `events` import batch with one row, normalized per `normalize_header` to `{"event_program": "Portland Hackathon", "category": "hackathon"}`, and accept it through the route.
4. `GET /v1/units/{unit_id}/metrics` and assert:
   - `pipeline_matched == 2`, `unknown_reason is None`
   - `opportunities == 1`, `unknown_reason is None`
   - `pipeline_contacted`, `pipeline_confirmed`, `pipeline_attended`, `pipeline_member_inquiry` all `== 0` with `unknown_reason is None` — a **measured zero**, the honest state before the seed tool runs.
5. `GET /v1/units/{unit_id}/metrics/pipeline_matched/drill-down` and assert `aggregate_value == 2 == len(rows)`, and that the row ids are exactly the two `pipeline_record` ids in the database for that unit. Same for `opportunities`.
6. **Provenance is persisted, read from the database:** every `pipeline_record` row for that unit has `matched_provenance = 'synthetic / coordinator-accepted'`. This is the assertion that would have been impossible under the log-only design.
7. Run `tools.seed_demo_pipeline.main(["--unit-path", ..., "--through", "attended", "--limit", "2"])` with the dev env vars monkeypatched, assert it returns `0`, then re-read the metrics route and assert `pipeline_contacted == 2`, `pipeline_confirmed == 2`, `pipeline_attended == 2`, `pipeline_member_inquiry == 0`, and that each stage's drill-down `aggregate_value == len(rows)` (ADR-0011 rule 3).
8. Assert the funnel **never widens**: `matched >= contacted >= confirmed >= attended >= member_inquiry`.
9. **Negative — the numbers come from the routes:** no assertion in this file obtains a metric value from `PipelineRepository`. Enforce it mechanically — `inspect.getsource` of the test module must not contain `"record_matched("`; the only permitted direct database reads are the id-set comparison in step 5 and the provenance check in step 6.
10. **Negative — no orphan subject_id:** every `pipeline_record` row written has a matching `user_account` (`LEFT JOIN` returns nothing unmatched) — no orphan `subject_id` reached storage through the HTTP path either.

**Work — part B, compose appliance proof.**

Append to `scripts/compose_smoke.sh` after its existing stage 8, keeping every rule the script's own header states (no `|| true`, no swallowed exit code, no bare `sleep` standing in for readiness — every wait is a bounded poll of the actual condition):

- **Stage 9 — import one inline `events` row.** `POST ${API_BASE}/v1/units/${unit_id}/imports` with `{"dataset": "events", "dry_run": false, "rows": [{"Event / Program": "Portland Hackathon", "Category": "hackathon"}]}` and a fresh `Idempotency-Key`. Assert `202`.
- **Stage 10 — poll `pending_review_items` back to `1`** via the existing `metric_value` helper, bounded by `METRIC_ATTEMPTS`, failing with a named message otherwise.
- **Stage 11 — recover the new pending review item id** with the existing `psql_scalar` helper, using the same join stage 6 uses but adding `and ib.dataset = 'events'`.
- **Stage 12 — accept it.** `POST /v1/review-items/${id}/decision` with `{"decision": "accepted"}`; assert the response `status` is `accepted`.
- **Stage 13 — poll `pipeline_matched` to `1`.** This is the acceptance criterion: a metric that was a permanent measured zero is now non-zero, from a path that ran entirely inside the compose appliance. Fail with `"expected pipeline_matched == 1 after accepting an in-list events row, got ${value}"`. **§1.10:** a `2xx` on stage 12 is not sufficient evidence — the positive count is the assertion.
- **Stage 14 — assert `opportunities == 1`** from the same metrics route.
- **Stage 15 — assert the stored provenance**, with the existing `psql_scalar` helper:
  ```
  select count(*) from pipeline_record where matched_provenance = 'synthetic / coordinator-accepted'
  ```
  must be `1`, and
  ```
  select count(*) from pipeline_record where matched_provenance <> 'synthetic / coordinator-accepted'
  ```
  must be `0`. A row that reached the database without saying it is synthetic fails the smoke path.
- Update the script's closing `log` lines and its header comment block to describe the extended sentence:
  `import -> scheduler dispatch -> pending_review_items 0->1 -> accept -> 1->0 -> events import -> accept -> pipeline_matched 0->1, opportunities 0->1, provenance stored`.

Note for the implementer: stage 4's professionals import and stage 7's accept are what create the `user_account` and the unit link, so the events accept at stage 12 finds exactly one professional and opens exactly one journey. **Do not reorder the stages** — reversing them is the silent-zero case Card 5's warning exists to surface, and the smoke path must exercise the working order.

**Work — part C, `INSTALL.md`.** Add the new stages to whatever numbered smoke sequence `INSTALL.md` already documents, plus one paragraph: what `pipeline_matched` becoming `1` proves and what it does not (it proves a coordinator accepted a synthetic in-list event for a synthetic professional in the compose appliance, and that the row records itself as synthetic; it proves nothing about matching quality, and there is no score anywhere in the path). Mention `tools/seed_demo_pipeline.py` as the optional follow-on for demonstrating funnel depth, including that it exits non-zero if it finds nothing to advance.

**Verification commands.**
```bash
cd /mnt/c/Users/DangT/Documents/GitHub/smartmatch-wt-pipeline-caller

# Part A
docker compose up -d db
until docker compose exec -T db pg_isready -U smartmatch -d smartmatch >/dev/null 2>&1; do sleep 1; done
make migrate
.venv/bin/pytest tests/integration/test_pipeline_funnel_end_to_end.py -m integration

# Part B — the real appliance
docker compose down -v
docker compose up --build -d
scripts/compose_smoke.sh
docker compose down -v

# Gates
make check
```

**Done when.**
- `tests/integration/test_pipeline_funnel_end_to_end.py` passes, with `pipeline_matched == 2` and `opportunities == 1` read from the metrics routes and provenance read from the database.
- `scripts/compose_smoke.sh` exits `0` against a freshly built stack and its log ends with a line reporting `pipeline_matched 0->1` and the provenance assertion.
- `make check` passes.
- `INSTALL.md` documents the new stages.
- `git status --short` lists only the three fenced files.

---

## 7. Residual risks and open items

1. **The decision record needs amending.** `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §4 does not carry the provenance string `synthetic / coordinator-accepted` or the "review-accept of in-list professionals" call site, though both are binding on this branch by session ruling. **Action on the ratifier**, flagged in the PR (§1.1). No card edits that file.
2. **Choice A timing is a ruled-on deviation.** §4 item 2 says "import creates or links `user_account`"; this plan creates it at review-accept (Decision 2, accepted by ruling). Prominent in the plan and in Card 3's module docstring so a reviewer cannot mistake it for an oversight.
3. **`0016` must be rebased before merge.** Down-revision `0015_remove_ledger_reversal` is the head as of 2026-09-03. If another migration lands on `origin/main` first, **re-point `down_revision`** at the new head — do not renumber `0016`. Card 1 carries this as a done-when item.
4. **The provenance vocabulary is closed and grows only by revision.** `'match-engine'` is a reserved, unwritten slot for G1/M8. Adding a third member is a new migration, never an edit to `0016`, because a CHECK edited in place silently changes what already-stored rows were validated against.
5. **Provenance is written once and never rewritten.** `record_matched` conflicts `DO NOTHING`, so whichever call creates a journey sets its provenance for good (Decision 7). If a row's provenance ever legitimately needs to change, that is a deliberate separate operation this plan does not provide.
6. **Fan-out shape.** An events accept opens one journey per already-linked professional in the unit, capped at 50 so one accept cannot become an unbounded write. A demo needing more should raise the constant deliberately, in its own change.
7. **Demo order dependence now fails loudly, not silently** (§1.10, ruling 4). Accepting the events row before any professionals still opens zero journeys — that is honest, there was nobody to match — but it now emits a `WARNING` naming the unit (Card 5), the seed tool exits non-zero rather than reporting success (Card 7), and the compose smoke path asserts a positive count rather than a `2xx` (Card 8). The stakeholder run-book should still state the working order.
