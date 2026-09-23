# B26 T8a — `0040_speaker_booking_cancellation`, Cancel booking route and button

**Next action:** once `0039_speaker_portal` merges, rebase on `main`, then write `tests/integration/test_booking_cancellation_migration.py` (§5) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1 ("Nothing can cancel a Speaker
booking"), §3 intro, §3.3, §5.2, §6, §7 row 9, §8 T8a, §10 row 5. Branch `feat/b26-t8a`.
`down_revision = "0039_speaker_portal"`. If another revision lands first, use the current head plus one.

**Owner rulings (2026-09-23, final):**

| # | Ruling |
|---|---|
| C1 | **Option C.** A cancelled booking drops out of **both** `list_confirmed_speakers` and the `pipeline_confirmed` metric (§3.5). |
| C2 | Keep the not-attended CHECK. |
| C3 | New page `/coordinator-portal/bookings`, registered the way `ce2701ff` registered the redemptions page. |
| C4 | Keep the order CHECK. |
| C5 | `cancelled_at` comes from the server clock. |
| C6 | No undo in T8a. Recorded as follow-up card FU-1 (§7). |
| C7 | The orchestrator sequences T6b-2 after T8a. |

## 0. Facts this plan rests on (checked against `origin/main` 1909278f)

1. A Speaker booking is a `pipeline_record` row. `subject_id` is the professional's `user_account`
   (`0024_cba_classification_schema.py:90-100`; `0030…py:203`). The table is at `schema.py:677-773`.
2. Two routes write `confirmed_at`. Both go through `PipelineRepository.advance_stage` (`smartmatch_persistence/pipeline.py:437`).
   - `POST …/pipeline-records/{id}/stages` (`routers/pipeline.py:378-467`), a claim the Connector types.
   - `POST …/cba/events/{event_id}/speaker-handoff` (`routers/cba_handoff.py:348-452`), the Speaker's accepted invitation. It reaches `advance_stage` via `advance_cba_stage` `:961-994` and `_apply` `:1165`.
3. No Connector screen lists confirmed bookings. The only UI reading `GET …/cba/confirmed-speakers` is the Event Host page
   `VolunteerConfirmedSpeaker.tsx:190`, and the server allows only admin and coordinator on that route.
4. Precedent for a cancellation that is a transition: `event_registration.status` (`schema.py:2428-2468`), with its route at `student_events.py:1088-1152`.
   The row is kept, a repeat returns 200, and nothing is deleted.
5. Precedent for a composite account FK: `fk_event_filed_by_user` (`0033_event_filed_by.py`).
6. The ADR-0011 metric register is `METRIC_REGISTER` in `smartmatch_domain/metrics.py:142`. ADR-0011 rule 2 says the register "ships in the repository".
   - `pipeline_confirmed` is at `:157-163`.
   - Its owning query `_pipeline_funnel_rows_v1` (`routers/metrics.py:117-200`) reads the stage map `_PIPELINE_STAGE_COLUMNS` (`:108-114`).

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0040_speaker_booking_cancellation.py` | **New.** DDL §2. Hand-written (ADR-0004), one transaction (ADR-0009), writes no rows. |
| `smartmatch_persistence/schema.py:677-773` | Mirror 2 columns, 1 FK and 4 CHECKs with the same names. |
| `smartmatch_persistence/pipeline.py` | `PipelineRecordRow` (`:211`) and `_to_row` (`:695`) get `cancelled_at` and `cancelled_by_user_id`. New `cancel_booking` (§3.3). New errors `PipelineRecordCancelledError`, `BookingNotConfirmedError`, `BookingAlreadyAttendedError`. `advance_stage` (`:437`) refuses ATTENDED on a cancelled row (read check plus `cancelled_at IS NULL` in the UPDATE's WHERE). `list_confirmed_speakers` (`:996-1080`) adds `cancelled_at IS NULL` and its docstring is updated. `reconcile_invitation` (`:851`) refuses a cancelled journey before any write (§3.4). |
| `services/api/smartmatch_api/routers/pipeline.py` | New route (§3.1). `PipelineRecordResponse` (`:200`) and `_record_view` (`:327`) get both fields. `advance_pipeline_stage` (`:383`) maps a cancelled row to 409. New `BOOKING_CANCEL_RATE_LIMIT`. Update the docstring's route list. |
| `services/api/smartmatch_api/routers/cba_handoff.py` | `reconcile_speaker_handoff` (`:353`) maps a cancelled journey to 409 `pipeline_record_cancelled`. `_confirmed_speaker_or_unreachable` (`:312-345`) raises that 409, not a `RuntimeError`, when the record is cancelled (§3.4). Update the module docstring. `ConfirmedSpeakerView` is unchanged, because cancelled rows are no longer listed. |
| `smartmatch_domain/metrics.py` | Register change (§3.5): the `pipeline_confirmed` `definition` and `drill_down` strings, plus a dated "Register changes" note in the module docstring. |
| `services/api/smartmatch_api/routers/metrics.py:108-200` | New `_PIPELINE_STAGE_EXCLUSIONS = {"pipeline_confirmed": cancelled_at IS NULL}`, applied inside `_pipeline_funnel_rows_v1`. Every pipeline drill-down row gains `cancelled_at`. The adapter still fails closed on unmapped metrics. |
| `smartmatch_domain/speaker_pipeline.py` | The docstring on nesting (`:17-27`) adds that Confirmed excludes cancelled rows. Nesting still holds because a row cannot be both attended and cancelled (§3.2). |
| `tools/seed_pilot_student_feedback.py:457` | Add `cancelled_at IS NULL`, so the seed picks the same set as the list. |
| `contracts/openapi/smartmatch.json` | Regenerate with `make openapi`. CI runs `--check` (`verify.yml:127`). |
| `apps/web/legacy-frontend/src/lib/api.ts` | New `cancelBooking(unitId, recordId)` and `BookingCancellationResult`. `ConfirmedSpeaker` (`:4113`) is unchanged. |
| `apps/web/legacy-frontend/src/lib/metrics.ts:215-221` | `PIPELINE_STAGE_FIELDS` checks `["cancelled_at", "cancelled"]` first, so a cancelled row in a Matched or Contacted drill-down does not read "confirmed". |
| `pages/coordinator/CoordinatorBookings.tsx` + `.test.tsx` | **New** page (§4). |
| `routes.tsx:344-397`, `components/CoordinatorPortalLayout.tsx`, `navPrefetch.ts`, `tests/coordinatorLinks.test.ts` | Register the route, nav entry ("Bookings") and prefetch. These are the four files `ce2701ff` touched. |
| `tests/authz/test_policy_matrix.py:1512-1535` | New `Operation` `pipeline.booking.cancel` (`_authorize_pipeline`, `_PIPELINE_ROLES`, unit-scoped). `test_route_roles.py` is not touched: its ledger (`:72-79`) covers only job, import, review and me routes. |
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
  CHECK (cancelled_at IS NULL OR attended_at IS NULL);                          -- C2
```

- Every existing row has `cancelled_at IS NULL`, so the upgrade runs no UPDATE.
- `ck_pipeline_record_stage_prefix` and `ck_pipeline_record_stage_order` are unchanged.
- No index. T8c adds one if its load read needs it.
- **Downgrade**, in reverse order: drop the 4 CHECKs, then the FK, then both columns. It is a development tool that discards every cancellation, the same caveat as `0033`.

## 3. Behaviour

### 3.1 `POST /v1/units/{unit_id}/pipeline-records/{record_id}/cancellation`

- **Where it lives:** `routers/pipeline.py`, reusing `_authorize_pipeline` and `_load_record_or_404`.
- **Roles:** `{admin, coordinator}` (`_PIPELINE_ROLES`, `:128`), checked against the unit's path.
- **Order:** `charge_quota` runs first (ADR-0015), then authorize, then load, then write.
  - `BOOKING_CANCEL_RATE_LIMIT`: `pipeline.booking_cancel`, 30 per minute.
- **Body:** none. A free-text reason is a non-goal (`PROHIBITED_INPUTS`, parent §2).
- **Values written:** `cancelled_at = utc_now()` (C5), `cancelled_by_user_id = principal.user_id`, and `updated_at` is bumped.
- **200 response:** `BookingCancellationResponse { transitioned, already_cancelled, record: PipelineRecordResponse }`, in the same shape as `StageAdvanceResponse` (`:227`).

| Case | Status | `code` / body |
|---|---|---|
| Confirmed, not attended, not cancelled | 200 | `transitioned: true` |
| Already cancelled (a repeat, or a lost race) | 200 | `transitioned: false, already_cancelled: true`; the first actor and time are kept |
| `confirmed_at IS NULL` | 409 | `pipeline_booking_not_confirmed` |
| `attended_at` set | 409 | `pipeline_booking_already_attended` |
| Missing, in another unit, or in another tenant | 404 | `pipeline_record_not_found` (the existing code, `:302`) |
| Unit outside the caller's scope | 403 | the existing `assert_allowed` refusal |
| Quota spent | 429 | the existing quota code |

Both refusals are **409, not 422**: the request itself is valid, but the row's state refuses it.
The existing precedent is `pipeline_stage_prerequisite_unmet`. There is no `Idempotency-Key`, because the operation is idempotent in the data.

### 3.2 How attended and cancelled interact (C2)

The two states exclude each other: an attended booking cannot be cancelled, and a cancelled booking cannot be marked attended.

- Attendance is evidenced (`ck_pipeline_record_attendance_evidence`), because the talk happened.
- Parent §5.2 counts `completed` from `attended_at` alone. If both could be set, a cancelled booking would not "drop out".
- The database enforces the rule, and so does the repository:
  - `cancel_booking` raises `BookingAlreadyAttendedError`.
  - `advance_stage(ATTENDED)` raises `PipelineRecordCancelledError`, which becomes 409 `pipeline_record_cancelled` on `/stages`.

### 3.3 Repository `cancel_booking(session, *, tenant_id, record_id, actor_user_id, at) -> BookingCancellationOutcome`

1. Read the row and classify it: missing (`exists=False`), already cancelled (no-op), not confirmed, or attended.
2. `UPDATE … SET cancelled_at, cancelled_by_user_id, updated_at WHERE tenant_id, id, cancelled_at IS NULL, confirmed_at IS NOT NULL,
   attended_at IS NULL, confirmed_at <= :at RETURNING id`. `transitioned` is set only from `RETURNING`.
3. If zero rows change, re-read once to classify what happened. The method never commits.

### 3.4 Hand-off replay on a cancelled booking (C1 = C)

**Behaviour: 409 `pipeline_record_cancelled`, with nothing written.**

- **Before any write:** `reconcile_invitation` finds the existing journey the way `_apply` does (`:1187`, via `_read_by_journey` `:677`). If `cancelled_at` is set, it raises
  `PipelineRecordCancelledError` before any stage is written, with or without `attendance_id`.
  - The Speaker's accepted invitation still exists, but the Connector's later cancellation outranks it. Re-running a hand-off must not
    bring a cancelled Speaker back in front of the Host.
- **The race after the write:** `_confirmed_speaker_or_unreachable` (`:312`) reads back through the Host list, which now excludes cancelled rows.
  A cancellation that commits between the hand-off's write and that read-back would today reach the `RuntimeError` at `:337` and return a 500. Instead,
  on a miss it re-reads the record with `PipelineRepository.get`:
  - if the record is cancelled, it raises the same 409;
  - otherwise it keeps the `RuntimeError`, because that case is still unreachable.
- **Message:** "This booking was cancelled by a Speaker Connector. It cannot be handed to an Event Host again."
- **Frontend:** `VolunteerConfirmedSpeaker.tsx` already renders the server's message word for word (`:103-117`), so it needs no change.

### 3.5 ADR-0011 register change for `pipeline_confirmed` (C1 = C)

- **Definition, old:** "Pipeline records that have reached the Confirmed stage or a later stage."
- **Definition, new:** "Pipeline records that have reached the Confirmed stage or a later stage and whose booking has not been cancelled."
- **`drill_down`, new:** "The Pipeline records at Confirmed or any later funnel stage, excluding cancelled bookings."
- **Dated note in the register's module docstring:** "2026-09-23 — owner ruling (B26 T8a, C1 = C): `pipeline_confirmed` excludes `cancelled_at IS NOT NULL`. No other metric changes."
- **Owning query:** keeps the name `pipeline_funnel_rows_v1`. Rule 3 needs one owning query, and it still has one. Renaming it would touch 7 files for no reader.
- **Other stages unchanged:**
  - Matched and Contacted still count cancelled bookings. They did reach those stages.
  - Attended and Member Inquiry cannot hold a cancelled row (§3.2).
- **Nesting still holds:** attended is a subset of confirmed-and-not-cancelled, which is a subset of contacted. The conversion rates in `speaker_pipeline.py` stay legitimate. "Confirmed to speak" now means net of cancellations.

**Every reader of the metric or the list, and what changes**

| Reader | Change |
|---|---|
| `routers/metrics.py` `_pipeline_funnel_rows_v1` (aggregate and drill-down) | Exclusion applied. Rows gain `cancelled_at`. |
| `pipeline.py` `list_confirmed_speakers` → `confirmed_speakers_view` (`cba_handoff.py:461`) and `_confirmed_speaker_or_unreachable` (`:312`) | Exclusion applied; §3.4. |
| `speaker_pipeline.py` conversions, via `/metrics?surface=cba` (`SpeakerPipelineSection`, `PipelineFunnelTiles.tsx`, `lib/speakerPipeline.ts`, `lib/metrics.ts`) | Consume the new number, so no code changes. `metrics.ts:215` gets the "cancelled" label for drill-down rows. |
| `VolunteerConfirmedSpeaker.tsx:190` (Host) | A cancelled Speaker silently leaves the list, with no reason shown (the OQ-CBA-042 posture). No code change. |
| `CoordinatorBookings.tsx` (new) | Lists the same set, so a cancelled row disappears after Cancel. |
| `tools/seed_pilot_student_feedback.py:457` | Add `cancelled_at IS NULL`. |
| `tests/e2e/test_pilot_clickthrough.py:2345`, `test_frontend_handoff_contract.py`, `test_frontend_host_portal_contract.py`, `test_frontend_student_feedback_contract.py`, and student pages (comments only) | No change. None of them cancels, and none pins the predicate. |
| Metric tests: `test_metrics_register.py`, `test_speaker_pipeline.py`, `test_speaker_pipeline_api.py`, `test_pipeline_stage_writer_metrics.py`, `test_metrics_storage_binding.py:65`, `test_pipeline_funnel_end_to_end.py`, `test_pipeline_record_writers.py:74` | Existing assertions hold because none has a cancelled row. Cancelled cases are added (§5). |

## 4. Frontend — `CoordinatorBookings.tsx` at `/coordinator-portal/bookings`

- **Registration** (the `ce2701ff` pattern):
  - `routes.tsx`: `{ path: "bookings", element: withSuspense(<CoordinatorBookings />) }`.
  - `CoordinatorPortalLayout.tsx`: nav entry "Bookings".
  - `navPrefetch.ts`: prefetch `fetchConfirmedSpeakers` under the same key.
  - `tests/coordinatorLinks.test.ts`: add the link.
- **Read:** `fetchConfirmedSpeakers(unitId, eventId?)` through `useScopedQuery`, with the key `[principalKey, "confirmed-speakers", unitId, eventId ?? "all"]`.
  - The unit comes from `grantedPortal`/`usePortalAccess`; nobody types an id.
  - `?event_id=` filters the list. Event titles come from the unit's events query (its key is reused). A missing title shows as "Event <first 8 characters of the id>".
- **Row:** name ("Name not on file" when null), company, event, "Agreed <date>", and a state of "Booked" or "Presented <date>".
  - The **Cancel booking** button appears on Booked rows only. That is a courtesy, not authorization.
  - The button's accessible name is `Cancel booking for {name} at {event}`.
- **Confirm dialog** (`components/ui/alert-dialog.tsx`, Radix, `role="alertdialog"`, focus trapped):
  - Title: "Cancel this booking?"
  - Body: "{name} will no longer count as booked for {event}, and their load drops at once. Your name and the time are recorded. This cannot be undone."
  - Buttons: **Keep booking** (focused first; Esc does the same) and **Cancel booking** (destructive). Focus returns to the trigger on close, or to the list heading if the row is gone.
- **Mutation:** `useMutation`, with no optimistic update.
  - While pending, the confirm button is disabled and reads "Cancelling…".
  - On success, invalidate only `["confirmed-speakers", unitId, …]`.
  - One `role="status"` region says "Booking cancelled." when `transitioned`, and "Already cancelled — nothing changed." when not.
- **Errors:** branch on `ApiRequestError.code`. The message goes in `role="alert"` inside the dialog, linked by `aria-describedby`, and the dialog stays open.
  - `pipeline_booking_already_attended`: "This speaker already presented. An attended booking cannot be cancelled."
  - `pipeline_booking_not_confirmed`, `pipeline_record_not_found`, 429: show the server's message word for word.
- **Page states:**
  - **Loading:** a skeleton with `aria-busy`.
  - **Empty:** "No confirmed speakers in this unit."
  - **Error:** the server's message and a Retry button.
  - **Denied (403):** the refusal, named as one, as `VolunteerConfirmedSpeaker.tsx:108` does.
- **Accessibility:** WCAG 2.2 AA. A table with a `<caption>` at desktop width and a card list on mobile, in a logical tab order.

## 5. Tests — written first. Run each file on its own locally; CI runs `pytest tests/ -m "not e2e"` and `npm run test:components`.

**Integration: `tests/integration/test_booking_cancellation_migration.py` (new, pattern `test_event_filed_by_migration.py`)**
1. `test_the_upgrade_writes_no_row_and_leaves_every_journey_uncancelled`
2. `test_cancellation_needs_both_actor_and_time` and `test_an_actor_without_a_time_is_refused`
3. `test_an_unconfirmed_journey_cannot_be_cancelled` and `test_a_confirmed_journey_can_be_cancelled`
4. `test_a_cancellation_cannot_precede_the_confirmation` and `test_a_cancellation_at_the_confirmation_instant_is_permitted`
5. `test_an_attended_journey_cannot_be_cancelled`, `test_a_cancelled_journey_cannot_be_attended`, `test_a_canceller_from_another_tenant_is_refused`, `test_the_cancelling_account_cannot_be_deleted`, and `test_downgrade_drops_both_columns_and_all_four_checks`

**Integration: `test_check_constraints.py`.** Add 4 definitions and 4 `BEHAVIOURAL_COVERAGE` pointers to the file above.

**Integration: `test_pipeline_record_writers.py`**
- `test_cancel_booking_records_actor_and_time`
- `test_cancel_booking_is_idempotent_and_keeps_the_first_actor`
- `test_cancel_booking_refuses_unconfirmed` and `test_cancel_booking_refuses_attended`
- `test_cancel_booking_reports_a_missing_record`
- `test_advance_stage_refuses_attended_on_a_cancelled_booking`
- `test_two_concurrent_cancels_transition_once`

**Integration: `test_cba_confirmed_handoff.py`**
- `:778` `test_the_confirmed_aggregate_equals_its_drill_down_and_the_host_list` gains a 4th confirmed journey that is then cancelled.
  - It asserts `value == 3 == len(drill_down.rows) == len(host_list.speakers)`, and that the cancelled id is in none of the three sets.
- `test_replaying_a_handoff_on_a_cancelled_booking_is_409_and_writes_nothing`
- `test_a_handoff_citing_attendance_on_a_cancelled_booking_is_409`
- `test_a_cancellation_racing_the_readback_is_409_not_500` (the read-back hook is monkeypatched to cancel)

**Integration: `test_pipeline_stage_writer_metrics.py`**
- `test_a_cancelled_booking_leaves_confirmed_but_stays_in_contacted`
- `test_the_funnel_still_nests_with_a_cancelled_booking`

**Unit: `test_metrics_register.py`**
- `test_pipeline_confirmed_definition_names_the_cancellation_exclusion`
- `test_no_other_pipeline_metric_mentions_cancellation`

**Contract: `tests/contract/test_booking_cancellation_api.py` (new, fixtures as in `test_pipeline_stages.py:129-228`)**
1. `test_cancelling_a_confirmed_booking_returns_who_and_when`
2. `test_repeating_a_cancellation_is_200_and_changes_nothing`
3. `test_cancelling_an_unconfirmed_journey_is_409` and `test_cancelling_an_attended_booking_is_409`
4. `test_a_record_in_a_sibling_unit_is_a_404_not_a_403`, `test_an_unknown_record_is_the_same_404`, and `test_a_coordinator_without_the_unit_is_refused`
5. `test_an_unauthenticated_caller_writes_nothing`, `test_quota_is_charged_before_the_404` (ADR-0015), `test_attended_on_a_cancelled_booking_is_409_on_the_stages_route`, and `test_the_read_route_carries_cancelled_fields`

**Authz:** a `pipeline.booking.cancel` row in `test_policy_matrix.py`, which runs every principal shape.

**Vitest: `CoordinatorBookings.test.tsx`**
1. `renders loading, then the list` and `renders the empty state`
2. `renders the server's error with Retry` and `renders 403 as a refusal`
3. `Cancel opens an alertdialog focused on Keep booking` and `Escape closes it and sends nothing`
4. `confirm sends exactly one POST and disables while pending`, `success announces in role=status and re-reads the list`, and `already-cancelled response announces nothing changed`
5. `409 attended keeps the dialog open with role=alert`, `presented rows have no Cancel button`, and `query keys are isolated per principal`

**Node test:** `tests/coordinatorLinks.test.ts` (the link). CI does not run `npm test`; run it locally.

## 6. Commit milestones (one commit each, pushed)

1. `test: 0040 cancellation migration and CHECK registry (red)`
2. `feat: 0040_speaker_booking_cancellation migration, mirror, head pins`
3. `feat: PipelineRepository.cancel_booking, attended guard, handoff refusal`
4. `feat: pipeline_confirmed excludes cancelled bookings (ADR-0011 register change)`
5. `feat: POST …/cancellation route, 409s, OpenAPI, policy matrix`
6. `feat: /coordinator-portal/bookings page with Cancel booking dialog`
7. `docs: README/ops head to 0040`

## 7. Out of scope, and follow-up cards

- **FU-1 (C6): undo a cancellation.** Nothing in T8a can undo one, and a Speaker who was cancelled but presented anyway cannot be
  marked attended. The follow-up card adds an audited "reinstate" transition. It must decide whether reinstating restores the metric count and the Host list.
- Also out of scope:
  - Cancelling a whole event.
  - Emailing the Speaker or the Host.
  - A cancellation reason.
  - A Speaker cancelling their own booking.
  - Showing cancelled bookings on the new page (a later filter).
  - The ELI load read (T8b/T8c).
  - `/v1/me/engagements` (T6b-2, which runs after T8a).
  - Retention and pruning (D5).
  - `docs/plans/frontend-broken-buttons.md`.

## 8. Open points (none block the build)

| # | Point | Decision taken here |
|---|---|---|
| P1 | The owning query keeps its `_v1` name even though one metric's predicate changes. | The dated register note and the definition text carry the change. Rule 3 is met. |
| P2 | The new page lists only live bookings, so a Connector cannot see past cancellations there. | `GET …/pipeline-records/{id}` shows them, and the Matched and Contacted drill-downs label them "cancelled". |
