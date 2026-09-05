# S12 pipeline stage writers — coordinator-driven advances (2026-09-05)

## Plan card

| | |
|---|---|
| **Goal** | Make `pipeline_confirmed`, `pipeline_attended` and `pipeline_member_inquiry` reachable by a real coordinator action, so the funnel's last three metrics can be non-zero without anything being invented. |
| **Shape** | HTTP only. `PipelineRepository.advance_stage` already implements every stage, every precondition and every constraint backstop; nothing in the persistence layer or the schema changes. |
| **Migration** | **None.** Head stays `0021`. Every column, check constraint and foreign key this needs landed in `0011` / `0016` / `0017`. |
| **New surface** | `GET /v1/units/{unit_id}/pipeline-records/{record_id}` and `POST /v1/units/{unit_id}/pipeline-records/{record_id}/stages`. |
| **Not in scope** | Live calendar/RSVP confirmation, an attendance *writer*, a coordinator queue listing other people's journeys, any crawler work, any frontend. See §5. |

## 1. What was already true

* `pipeline_record` (migration `0011`, provenance columns `0016`) holds the five
  stages as five nullable timestamps, ordered by `ck_pipeline_record_stage_prefix`
  and `ck_pipeline_record_stage_order`, with `ck_pipeline_record_attendance_evidence`
  making Attended biconditional on a real `attendance_record` id.
* `smartmatch_persistence.pipeline.PipelineRepository` writes it:
  `record_matched` opens a journey, `advance_stage` moves it one stage at a time.
  `advance_stage` already refuses a naive datetime, an unreachable stage, a
  `reached_at` that precedes its prerequisite, an Attended claim with no evidence,
  and evidence that names no row in this tenant — and repeats the ordering test in
  the `UPDATE`'s own `WHERE` clause so a concurrent write cannot slip past the read.
* The only *application* caller was the outreach worker's `_advance_pipeline`,
  which records **Contacted**, and only when the send command names an existing
  journey (migration `0021`, card L5).

So Matched had a writer (the review-accept path and the synthetic seed), Contacted
had a conditional one, and Confirmed / Attended / Member Inquiry had none. Their
metrics read a real table and honestly reported zero, because zero rows had reached
those stages — ADR-0011 rule 1 held, and the funnel was useless.

## 2. What this ships

A router, `services/api/smartmatch_api/routers/pipeline.py`:

* **`GET /v1/units/{unit_id}/pipeline-records/{record_id}`** — one journey, with
  every stage timestamp and `current_stage`. Read-only.
* **`POST /v1/units/{unit_id}/pipeline-records/{record_id}/stages`** — advance to
  `confirmed`, `attended` or `member_inquiry`. `matched` and `contacted` are *not*
  in the request enum: `matched` is opened by `record_matched`, and `contacted` is
  the outreach send's own consequence, which is the only evidence this system has
  that a message actually went out. Letting a coordinator type "contacted" would
  let the funnel's one machine-witnessed stage be asserted by hand.

`200`, not `202`: nothing durable starts. The `UPDATE` either lands in this request
or it does not, so the rewards `decide_redemption` shape applies rather than the
outreach `send_draft` one.

### Authorization

`admin` / `coordinator` against the *unit row's own path*, exactly as
`outreach.py::_authorize_outreach` does it. The record is then checked against the
loaded unit's id and a mismatch is a **404**, not a 403 — the same choice
`compose_draft` makes for a contact channel in another unit, so an id the caller may
not read is never confirmed to name something real. `load_unit_or_404` scopes by the
caller's tenant, so a unit in another tenant is a 404 before authorization is asked.

### Idempotency

No `Idempotency-Key` header, deliberately. A stage advance is idempotent *in the
data*, not by a stored key: the target column is set once and `advance_stage`'s
`UPDATE` carries `target_column IS NULL` in its `WHERE`. A repeat returns `200` with
`transitioned: false, already_reached: true` and the unchanged row. That is strictly
stronger than a key, which only covers retries of the *same request* and would
report a replay for a second coordinator asserting the same fact. The two booleans
stay separate in the response for the reason `PipelineStageOutcome` keeps them
separate.

### Evidence, not assertion

`reached_at` is **required and timezone-aware** (`AwareDatetime`, so a naive value
is a `422` from the schema, never a silent constraint violation). It is not derived
from `now()`: the coordinator is recording when a thing happened, and a server clock
reading is not that. `attendance_id` is **required for `attended` and rejected for
every other stage**, enforced by a model validator so the refusal is a `422` naming
the field rather than a `ValueError` surfacing from the repository.

## 3. Error mapping

| Cause | Status | `code` |
|---|---|---|
| No such record in this tenant, or not under the authorized unit | 404 | `pipeline_record_not_found` |
| Prerequisite stage not yet reached | 409 | `pipeline_stage_prerequisite_unmet` |
| `reached_at` precedes the prerequisite's timestamp | 409 | `pipeline_stage_out_of_order` |
| `attendance_id` names no `attendance_record` in this tenant | 409 | `pipeline_attendance_evidence_not_found` |
| `attendance_id` missing for `attended` / present for another stage | 422 | schema validation |
| Naive `reached_at` | 422 | schema validation |

## 4. Tests

* `tests/contract/test_pipeline_stages.py` — the HTTP contract: authz, the 404 for
  a sibling unit's record, each 409, the repeat-is-`already_reached` case, the
  request schema's refusal of `matched` / `contacted`, and the full
  `matched → contacted → confirmed → attended → member_inquiry` walk.
* `tests/integration/test_pipeline_stage_writer_metrics.py` — the point of the whole
  change: seed a synthetic journey, advance it through the real routes, and read
  `/v1/units/{id}/metrics` back to see `pipeline_confirmed`, `pipeline_attended` and
  `pipeline_member_inquiry` non-zero.

Both skip when no migrated PostgreSQL is reachable, the way every other DB-backed
test in this repository does.

## 5. Deferred

See `docs/plans/open-questions/pipeline-stage-writers-deferred.md`. The short form:
live calendar confirmation is not built, and this route does not pretend to be it —
a coordinator asserting "confirmed" with a timestamp is a *coordinator's* claim, and
the response says so by returning the row rather than a bare success flag.
