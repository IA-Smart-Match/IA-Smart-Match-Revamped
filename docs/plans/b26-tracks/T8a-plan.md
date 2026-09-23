# B26 T8a — `0040_speaker_booking_cancellation`, Cancel booking route and button

**Next action:** once `0039_speaker_portal` merges, rebase on `main`, then write `tests/integration/test_booking_cancellation_migration.py` (§5) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1 ("Nothing can cancel a Speaker
booking"), §3 intro, §3.3, §5.2, §6, §7 row 9, §8 T8a, §10 row 5. Branch `feat/b26-t8a`.
`down_revision = "0039_speaker_portal"`. If another revision lands first, use the current head plus one.

## 0. Facts this plan rests on (checked 2026-09-22 against `origin/main` 1909278f)

1. A Speaker booking is a `pipeline_record` row. `subject_id` is the professional's `user_account`
   (`0024_cba_classification_schema.py:90-100`, repointed in `0030…py:203`). The table is at `schema.py:677-773`.
2. Two routes write `confirmed_at`: `POST …/pipeline-records/{id}/stages` (`routers/pipeline.py:378-467`), which
   records a claim the Connector types, and `POST …/cba/events/{event_id}/speaker-handoff` (`routers/cba_handoff.py:348-452`),
   which copies the Speaker's accepted invitation. Both go through `PipelineRepository.advance_stage`
   (`smartmatch_persistence/pipeline.py:437`; the CBA path via `advance_cba_stage` `:961-994` and `_apply` `:1165`).
3. **No Connector screen lists confirmed bookings.** The only UI that reads `GET …/cba/confirmed-speakers`
   is the Event Host page `VolunteerConfirmedSpeaker.tsx:190` (the server allows only admin and coordinator). T8a therefore needs a new
   Connector page (§4). Parent §6 does not list one: contradiction C3.
4. Precedent for cancelling by changing state: `event_registration.status` `'registered'|'cancelled'` (`schema.py:2428-2468`,
   `ck_event_registration_status`). Its route is `student_events.py:1088-1152`: the row is kept, a repeat returns 200, and nothing is deleted.
5. Precedent for a composite account FK: `fk_event_filed_by_user` (`0033_event_filed_by.py`, upgrade and downgrade).

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0040_speaker_booking_cancellation.py` | **New.** DDL §2. Hand-written (ADR-0004), one transaction (ADR-0009), writes no rows. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py:677-773` | Mirror 2 columns, 1 FK and 4 CHECKs with the same names. |
| `python/smartmatch_persistence/smartmatch_persistence/pipeline.py` | `PipelineRecordRow` (`:211`) and `_to_row` (`:695`) get `cancelled_at` and `cancelled_by_user_id`. New `PipelineRepository.cancel_booking` (§3.3). New errors `PipelineRecordCancelledError`, `BookingNotConfirmedError`, `BookingAlreadyAttendedError`. `advance_stage` (`:437`) refuses ATTENDED on a cancelled row (read check plus `cancelled_at IS NULL` in the UPDATE's WHERE). `ConfirmedSpeakerRow` (`:788`) and `list_confirmed_speakers` (`:996-1080`) select `cancelled_at`. |
| `services/api/smartmatch_api/routers/pipeline.py` | New route §3. `PipelineRecordResponse` (`:200`) and `_record_view` (`:327`) get both fields. `advance_pipeline_stage` (`:383`) maps `PipelineRecordCancelledError` to 409. New `BOOKING_CANCEL_RATE_LIMIT`. Update the module docstring's route list. |
| `services/api/smartmatch_api/routers/cba_handoff.py` | `ConfirmedSpeakerView` (`:167`) and `_speaker_view` (`:287`) get `cancelled_at`. `reconcile_speaker_handoff` (`:353`) maps `PipelineRecordCancelledError` to 409 `pipeline_record_cancelled`. |
| `contracts/openapi/smartmatch.json` | Regenerate with `make openapi`. CI runs `--check` (`verify.yml:127`). |
| `apps/web/legacy-frontend/src/lib/api.ts` | `ConfirmedSpeaker` (`:4113`) gets `cancelled_at: string \| null`. New `cancelBooking(unitId, recordId)` and `BookingCancellationResult`. |
| `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorBookings.tsx` (+ `.test.tsx`) | **New** page, §4. |
| `routes.tsx:344-397`, `components/CoordinatorPortalLayout.tsx`, `navPrefetch.ts`, `tests/coordinatorLinks.test.ts` | Register `/coordinator-portal/bookings` with a nav entry and prefetch. Precedent: `ce2701ff`. |
| `apps/web/legacy-frontend/src/app/pages/volunteer/VolunteerConfirmedSpeaker.tsx` | Show a cancelled row as "Booking cancelled" instead of "Agreed to speak" (option C1-A). |
| `tests/authz/test_policy_matrix.py:1512-1535` | New `Operation` `pipeline.booking.cancel` (authorizer `_authorize_pipeline`, `_PIPELINE_ROLES`, unit-scoped). The matrix builds its route list from the source, so a missing row fails the test. `test_route_roles.py` stays as is: its ledger (`:72-79`) covers only job, import, review and me routes. |
| `tests/integration/test_check_constraints.py` | Add 4 keys to `CHECK_CONSTRAINT_DEFINITIONS` (`:76`) and `BEHAVIOURAL_COVERAGE` (`:766`). |
| Head pins and docs | Every `HEAD_REVISION` that T6b-1 moves to `0039_speaker_portal` moves to `0040_…`. Today those are `test_cba_contact_schema.py:150`, `test_cba_weight_settings_persistence.py:189`, `test_event_filed_by_migration.py:78` and `test_host_organization_migration.py:84`. Also `README.md:35` (count 40, head `0040`), `docs/operations/supabase-setup.md:162`, and `exercise-hosting.md` step 2. The owner has uncommitted edits in that last file: change only those lines. |

`test_schema_matches_migration.py` needs no edit: it runs per table (`:169`, `:181`, `:306`) and checks composite anchoring (`:225`).

## 2. DDL — `0040_speaker_booking_cancellation`

```sql
ALTER TABLE pipeline_record ADD COLUMN cancelled_at timestamptz NULL;          -- no default
ALTER TABLE pipeline_record ADD COLUMN cancelled_by_user_id uuid NULL;         -- no default
ALTER TABLE pipeline_record ADD CONSTRAINT fk_pipeline_record_cancelled_by_user
  FOREIGN KEY (tenant_id, cancelled_by_user_id) REFERENCES user_account (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE pipeline_record ADD CONSTRAINT ck_pipeline_record_cancellation_actor
  CHECK ((cancelled_at IS NULL) = (cancelled_by_user_id IS NULL));             -- set together
ALTER TABLE pipeline_record ADD CONSTRAINT ck_pipeline_record_cancellation_confirmed
  CHECK (cancelled_at IS NULL OR confirmed_at IS NOT NULL);                     -- parent §3.3
ALTER TABLE pipeline_record ADD CONSTRAINT ck_pipeline_record_cancellation_order
  CHECK (cancelled_at IS NULL OR cancelled_at >= confirmed_at);                 -- C4
ALTER TABLE pipeline_record ADD CONSTRAINT ck_pipeline_record_cancellation_not_attended
  CHECK (cancelled_at IS NULL OR attended_at IS NULL);                          -- §3.2, C2
```

- Every existing row has `cancelled_at IS NULL`, so all 4 CHECKs pass without rewriting data. The upgrade runs no UPDATE.
- `ck_pipeline_record_stage_prefix` and `ck_pipeline_record_stage_order` are unchanged. A cancellation is not a stage.
- No index. The load read (T8c) filters by subject, and T8c adds an index if it needs one.
- **Downgrade**, in reverse order: drop the 4 CHECKs, then `fk_pipeline_record_cancelled_by_user`, then both columns.
  It is a development tool that discards every cancellation, which is the same caveat as `0033`'s downgrade.

## 3. Route contract

### 3.1 `POST /v1/units/{unit_id}/pipeline-records/{record_id}/cancellation`

- **Where it lives:** `routers/pipeline.py`. It reuses `_authorize_pipeline` and `_load_record_or_404`, so
  a change to who may call it applies to every pipeline route at once.
- **Roles:** `{admin, coordinator}` (`_PIPELINE_ROLES`, `:128`), checked against the unit's own path.
- **Order:** `charge_quota` runs first (ADR-0015), then authorize, then load, then write.
  - `BOOKING_CANCEL_RATE_LIMIT`: `operation="pipeline.booking_cancel"`, 30 per minute (the same as `STAGE_ADVANCE_RATE_LIMIT`).
- **Body:** none, and no reason field. A free-text reason would collect health information, which `PROHIBITED_INPUTS` forbids (parent §2 non-goal 2).
- **Values written:**
  - `cancelled_at = utc_now()` (C5).
  - `cancelled_by_user_id = principal.user_id`.
  - `updated_at` is bumped.
- **200 response:** `BookingCancellationResponse { transitioned: bool, already_cancelled: bool, record: PipelineRecordResponse }`.
  This mirrors `StageAdvanceResponse` (`:227`).

| Case | Status | `code` |
|---|---|---|
| Confirmed, not attended, not cancelled | 200 | `transitioned: true` |
| Already cancelled (repeat, or lost a race) | 200 | `transitioned: false, already_cancelled: true`; the first actor and timestamp are kept |
| `confirmed_at IS NULL` | 409 | `pipeline_booking_not_confirmed` |
| `attended_at` set | 409 | `pipeline_booking_already_attended` |
| Record missing, in another unit, or in another tenant | 404 | `pipeline_record_not_found` (the existing code, `:302`) |
| Unit outside the caller's scope | 403 | the existing `assert_allowed` refusal |
| Quota spent | 429 | the existing quota code |

Both refusals are **409, not 422**: the request itself is valid, but the row is in a state that refuses it.
The existing precedent is `pipeline_stage_prerequisite_unmet` (409). There is no `Idempotency-Key`, because the
operation is already idempotent in the data (`pipeline.py` docstring on status codes).

### 3.2 How attended and cancelled interact

**Decision: the two states exclude each other.** An attended booking cannot be cancelled, and a cancelled booking cannot be marked attended.

- **Why attended cannot be cancelled:** attendance is evidenced (`ck_pipeline_record_attendance_evidence`), because the talk happened.
- **Why both at once breaks T8b:** parent §5.2 counts `completed` from `attended_at` alone and `confirmed` as "attended_at and
  cancelled_at NULL". A row with both set would still add to `completed`, so a cancelled booking would not "drop out".
- **Enforcement:** the database enforces the rule (`ck_…_not_attended`) and so does the repository.
  - `cancel_booking` refuses with `BookingAlreadyAttendedError`.
  - `advance_stage(ATTENDED)` refuses with `PipelineRecordCancelledError`.
  - Both HTTP paths map that refusal to 409 `pipeline_record_cancelled`: `/stages` and `/speaker-handoff` with `attendance_id`.

### 3.3 Repository: `cancel_booking(session, *, tenant_id, record_id, actor_user_id, at) -> BookingCancellationOutcome`

1. Read the row and classify it: missing (`exists=False`), already cancelled (a no-op), not confirmed, or attended.
2. `UPDATE … SET cancelled_at=:at, cancelled_by_user_id=:actor, updated_at=now() WHERE tenant_id, id, cancelled_at IS NULL,
   confirmed_at IS NOT NULL, attended_at IS NULL, confirmed_at <= :at RETURNING id`.
   `transitioned` is set only from `RETURNING`, never from a re-read, as in `advance_stage`.
3. If the UPDATE changes zero rows, re-read once to classify what happened. The method never commits.

### 3.4 Audit

The row is the audit record: who (`cancelled_by_user_id`) and when (`cancelled_at`). This matches Q5 = a (provenance only).
The pipeline routers write no audit log today, and T8a does not add one. Parent §10 row 5 (D5 retention) governs pruning,
so T8a deletes nothing.

## 4. Frontend — `CoordinatorBookings.tsx` at `/coordinator-portal/bookings`

- **Read:** `fetchConfirmedSpeakers(unitId, eventId?)` through `useScopedQuery`, with the key
  `[principalKey, "confirmed-speakers", unitId, eventId ?? "all"]`.
  - The unit comes from `grantedPortal`/`usePortalAccess`; nobody types an id.
  - `?event_id=` filters the list. `CoordinatorEvents.tsx` gets one "Confirmed speakers" link per event.
  - The page shows event titles from the unit's events query (it reuses that query's key). When a title is missing it shows "Event <first 8 characters of the id>".
- **Row:** name (or "Name not on file" when null), company, event, "Agreed <date>", and a state:
  "Booked", "Presented <date>", or "Cancelled <date>". The Cancel button appears only on Booked rows. That is a courtesy, not authorization.
- **Button:** `Cancel booking`, with the accessible name `Cancel booking for {name} at {event}`.
- **Confirm dialog** (`components/ui/alert-dialog.tsx`, Radix, `role="alertdialog"`):
  - Title: "Cancel this booking?"
  - Body: "{name} will no longer count as booked for {event}, and their load drops at once. Your name and the time are recorded. This cannot be undone here."
  - Buttons: **Keep booking** (focused first; Esc does the same) and **Cancel booking** (destructive).
  - Focus returns to the trigger when the dialog closes.
- **Mutation:** `useMutation`, with no optimistic update.
  - While the request is pending, the confirm button is disabled and reads "Cancelling…".
  - On success, invalidate only `["confirmed-speakers", unitId, …]`.
  - The page has one `role="status"` region. It says "Booking cancelled." when `transitioned`, and "Already cancelled — nothing changed." when not.
- **Errors:** branch on `ApiRequestError.code`. The message goes in `role="alert"` inside the dialog, and the dialog stays open.
  - `pipeline_booking_already_attended`: "This speaker already presented. An attended booking cannot be cancelled."
  - `pipeline_booking_not_confirmed`, `pipeline_record_not_found`, 403, 429: show the server's message word for word.
- **Page states:** loading, empty ("No confirmed speakers in this unit."), list, error, and denied (403 shown as a refusal, as in `VolunteerConfirmedSpeaker.tsx:108`). The page meets WCAG 2.2 AA.

## 5. Tests — written first, and each file is run on its own locally (CI runs `pytest tests/ -m "not e2e"` and `npm run test:components`)

**Integration: `tests/integration/test_booking_cancellation_migration.py` (new, pattern `test_event_filed_by_migration.py`)**
1. `test_the_upgrade_writes_no_row_and_leaves_every_journey_uncancelled`
2. `test_cancellation_needs_both_actor_and_time` and `test_an_actor_without_a_time_is_refused`
3. `test_an_unconfirmed_journey_cannot_be_cancelled` and `test_a_confirmed_journey_can_be_cancelled`
4. `test_a_cancellation_cannot_precede_the_confirmation` and `test_a_cancellation_at_the_confirmation_instant_is_permitted`
5. `test_an_attended_journey_cannot_be_cancelled` and `test_a_cancelled_journey_cannot_be_attended`
6. `test_a_canceller_from_another_tenant_is_refused` and `test_the_cancelling_account_cannot_be_deleted`
7. `test_downgrade_drops_both_columns_and_all_four_checks`

**Integration: the `test_check_constraints.py` registry.** Add 4 definitions and 4 `BEHAVIOURAL_COVERAGE` pointers to the file above.

**Integration: `tests/integration/test_pipeline_record_writers.py`.** This file covers the repository.
- `test_cancel_booking_records_actor_and_time`
- `test_cancel_booking_is_idempotent_and_keeps_the_first_actor`
- `test_cancel_booking_refuses_unconfirmed` and `test_cancel_booking_refuses_attended`
- `test_cancel_booking_reports_a_missing_record`
- `test_advance_stage_refuses_attended_on_a_cancelled_booking`
- `test_two_concurrent_cancels_transition_once`

**Integration: `tests/integration/test_cba_confirmed_handoff.py`**
- `test_a_cancelled_booking_stays_in_the_host_list_with_cancelled_at` (C1-A)
- The existing `:778` equality test gets a cancelled row added and must still pass.
- `test_a_handoff_citing_attendance_on_a_cancelled_booking_is_refused`
- `test_replaying_a_handoff_on_a_cancelled_booking_applies_nothing`

**Contract: `tests/contract/test_booking_cancellation_api.py` (new, fixtures as in `test_pipeline_stages.py:129-228`)**
1. `test_cancelling_a_confirmed_booking_returns_who_and_when`
2. `test_repeating_a_cancellation_is_200_and_changes_nothing`
3. `test_cancelling_an_unconfirmed_journey_is_409` and `test_cancelling_an_attended_booking_is_409`
4. `test_a_record_in_a_sibling_unit_is_a_404_not_a_403`, `test_an_unknown_record_is_the_same_404`, and `test_a_coordinator_without_the_unit_is_refused`
5. `test_an_unauthenticated_caller_writes_nothing`, `test_quota_is_charged_before_the_404` (ADR-0015), `test_attended_on_a_cancelled_booking_is_409_on_the_stages_route`, and `test_the_read_route_carries_cancelled_fields`

**Authz:** a `pipeline.booking.cancel` row in `test_policy_matrix.py`, which runs every principal shape.

**Vitest: `CoordinatorBookings.test.tsx`**
- States: loading, empty, list, error, denied.
- The dialog opens with focus on "Keep booking". Esc sends nothing.
- Confirming sends exactly one POST, and the button is disabled while it is pending.
- Success sets the status message and re-reads the list. The already-cancelled message differs.
- A 409 for an attended booking keeps the dialog open and shows the alert.
- Cancelled and attended rows have no button.
- Query keys are isolated per principal.
- Also `VolunteerConfirmedSpeaker.test.tsx` (new): a cancelled row reads "Booking cancelled".

## 6. Commit milestones (one commit each, pushed)

1. `test: 0040 cancellation migration and CHECK registry (red)`
2. `feat: 0040_speaker_booking_cancellation migration, mirror, head pins`
3. `feat: PipelineRepository.cancel_booking and attended guard` (repository tests green)
4. `feat: POST …/cancellation route, handoff/stages 409s, OpenAPI, policy matrix` (contract and authz tests green)
5. `feat: Connector bookings page with Cancel booking dialog` (Vitest green)
6. `docs: README/ops head to 0040`

## 7. Out of scope

- Undoing a cancellation (C6).
- Cancelling a whole event.
- Emailing the Speaker or the Host.
- A cancellation reason.
- A Speaker cancelling their own booking (a `/v1/me/*` route).
- Changing the funnel metric (C1).
- The ELI load read (T8b/T8c).
- `/v1/me/engagements` (T6b-2).
- Retention and pruning (D5).
- `docs/plans/frontend-broken-buttons.md`.

## 8. Contradictions and options

| # | Contradiction | Options | Recommendation |
|---|---|---|---|
| C1 | **Must decide.** `list_confirmed_speakers` is by construction the same set as the `pipeline_confirmed` metric (`pipeline.py:1006-1013`, tested at `test_cba_confirmed_handoff.py:778`). The metric counts journeys that ever *reached* Confirmed, cancelled ones included. | **A:** keep the set, add `cancelled_at`, and label the row in the UI. **B:** drop cancelled rows from the list and break the equality. `_confirmed_speaker_or_unreachable` (`cba_handoff.py:312`) would then raise a 500 when a handoff is replayed. **C:** change the metric to exclude cancelled rows, which is an ADR-0011 register change. | **A** |
| C2 | **Must decide.** Parent §3.3 lists 2 CHECKs. This plan adds a third that makes attended and cancelled exclusive. | **Keep:** needed for §5.2 to be consistent. **Drop:** rely on the repository guard alone. | Keep |
| C3 | **Must decide.** Parent §6 names no Connector surface for Cancel, and none lists bookings today (§0.3). | **A:** a new page `/coordinator-portal/bookings`. **B:** a panel inside `CoordinatorEvents.tsx`, which is already 792 lines against an 800-line cap. | A |
| C4 | Later. The order CHECK (`cancelled_at >= confirmed_at`) is an addition to the parent plan. A Connector-typed `confirmed_at` in the future (`/stages` sets no upper bound) makes Cancel return 409 until that time passes. | Keep it, or drop it. | Keep |
| C5 | Later. `cancelled_at` comes from the server clock, not a caller-supplied `cancelled_at` (unlike `reached_at`). | Server clock, or a caller-supplied value with a bound. | Server clock. Load is read at run time, and the server clock rules out backdating. |
| C6 | Later. Nothing can undo a cancellation, and a Speaker who was cancelled and presented anyway cannot be marked attended. | A future card adding un-cancel. | Log as a follow-up |
| C7 | Later. Parent §8 gives T8a no dependency, but the task sets `down_revision = 0039`, so T8a merges after T6b-1. T6b-2's `/v1/me/engagements` "cancelled" (§4.3) needs T8a's columns, yet §8 does not list T8a under T6b-2. | Add T8a to T6b-2's dependencies, or let T6b-2 omit "cancelled" until T8a lands. | Add the dependency |
