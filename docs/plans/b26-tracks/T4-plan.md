# B26 T4 — Stage A wiring: stored verdicts, "changed since", compose/dispatch re-check, Q8, `0041`

**Next action:** write `tests/integration/test_invitation_batch_speaker_request_migration.py` (§8, tests M1–M7) and run it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §5.1, §6 (MatchRuns/Invitations row), §7 row 4, §8 T4, §9 Q8, §11.
Rulings applied (revision 2, 2026-09-23): C1 (b) owner, C2 in T4, C3 (b), C7 UTC, C4–C6/C8/C9/C11 as proposed, C10 folded in. See §10.

**Branch and chain.** Stacked on T8a: `feat/b26-t4` branches from `feat/b26-t8a` (→ T6b-1 → T2 → T1) and rebases onto `main` as each lands.
Migration chain: `0038_speaker_availability` (T2, PR #212) → `0039_speaker_portal` (T6b-1) → `0040_speaker_booking_cancellation` (T8a) → **`0041_invitation_batch_speaker_request` (T4)**.
Uses T1 (`availability_state_for_event`, `event_local_span`, `AvailabilityAssessment.to_evidence`, `AvailabilityReason`), T2 (`SpeakerAvailabilityRepository.get_many`: one query, absent key = no row), `0039`'s `speaker_profile.account_user_id` (Q8).

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0041_invitation_batch_speaker_request.py` | **New.** `revision = "0041_invitation_batch_speaker_request"`, `down_revision = "0040_speaker_booking_cancellation"`. Hand-written (ADR-0004), no transaction code (ADR-0009). §4.1. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | `cba_invitation_batch` (`:2577-2625`) mirrors `speaker_request_id` and `fk_cba_invitation_batch_speaker_request`. |
| `python/smartmatch_persistence/smartmatch_persistence/cba_invitations.py` | `BatchRow` (`:86`) + `speaker_request_id: uuid.UUID \| None`; `reserve_batch` (`:194`) + keyword `speaker_request_id: uuid.UUID \| None = None`; `_to_batch` (`:568`) carries it. |
| Head pins | `README.md:35` (41 revisions, head `0041_invitation_batch_speaker_request`), `docs/operations/supabase-setup.md`, `docs/operations/exercise-hosting.md` ("confirm the migration head" step), and the `_HEAD_REVISION` / `HEAD_REVISION` constants in `tests/integration/test_cba_contact_schema.py`, `test_cba_weight_settings_persistence.py`, `test_event_filed_by_migration.py`, `test_exercise_schema_migration.py`, `test_host_organization_migration.py` (the set T2 moved). At implementation, `git grep 0040_speaker_booking_cancellation` finds the complete list. |
| `python/smartmatch_domain/smartmatch_domain/availability_verdict.py` | **New, pure.** `StoredVerdict` (frozen: `subject_id`, `verdict: EligibilityOutcome`, `state`, `reason`, `as_of`, `paused_until`); `verdicts_for_pool(subject_ids, statements, event_span, as_of)` calls T1 `availability_state_for_event` per subject, then `apply_availability_filter` (`eligibility.py:110`) over the pool in pool order; `to_payload` / `from_payload` (strict, `explanation_from_payload` discipline, `explanation.py:653`); `changed_since(stored, current)`; `as_of_utc(now)` (C7); `event_time_from_columns(...)`; `filed_this_request(filed_by_user_id, account_user_id)`. |
| `python/smartmatch_domain/smartmatch_domain/cba_invitations.py` | `SkipReason` (`:174-197`) gains `SPEAKER_UNAVAILABLE_ON_DATE = "speaker_unavailable_on_date"` and `SPEAKER_INVITATIONS_PAUSED = "speaker_invitations_paused"`, plus `skip_reason_for_availability(StoredVerdict) -> SkipReason \| None`. `classify_recipient` (`:283`) and `_SKIP_SEVERITY` (`:319`) unchanged: they rank channels, not people. `cba_invitation.skip_reason` has only the iff CHECK (`schema.py:2718`), so the new tokens need no migration. |
| `services/api/smartmatch_api/availability_reads.py` | **New.** DB side: `load_request_event_time(session, tenant_id, unit_id, speaker_request_id) -> EventTime \| None` (scoped like `load_speaker_request`: tenant, `host_org_unit_id`, `origin = 'coordinator_entry'`); `request_for_run(session, tenant_id, unit_id, match_run_id) -> RunRequest \| None` (`None` = no such run in this unit; `RunRequest.speaker_request_id` is `None` when `event_need_id` is not a UUID naming a request in this unit); `current_verdicts(session, tenant_id, subject_ids, event_time, as_of)` = one `get_many` + `verdicts_for_pool`. |
| `services/api/smartmatch_api/match_run_evidence.py` | `SpeakerRequestEvidence` (`:169-202`) gains `filed_by_user_id` and `event_time`; `load_speaker_request` select (`:270-279`) adds `filed_by_user_id`, `time_precision`, `starts_at`, `ends_at`, `on_date`, `time_zone`. `EXCLUSION_FILED_THIS_REQUEST = "filed_this_request"`. `assemble_cba_pool` (`:353-419`): after the profile check (`:394-396`), before `match_ineligibility_reason` (`:403`), exclude when `filed_this_request(request.filed_by_user_id, row.account_user_id)`; `_profiles_by_professional_id` (`:440-457`) selects `account_user_id`. |
| `services/api/smartmatch_api/routers/match_runs.py` | Create (`:795`): after `explain_candidates`, one `current_verdicts` call over every evaluated subject; payload (`:961-989`) gains `availability` and `excluded` (C3). Read (`:1148`): `_read_stored_availability(payload)`, one `current_verdicts` call, `AvailabilityView` on each `CandidateExplanationView` (`:443`); `MatchRunResponse` (`:496`) gains `availability_recorded`, `availability_unreadable_reason`, `excluded`. `ExcludedCandidateView.reason` description (`:325-337`) lists `filed_this_request`. |
| `services/api/smartmatch_api/routers/cba_invitations.py` | `BatchCreateRequest` (`:198`) gains `speaker_request_id: uuid.UUID \| None`; `_resolve_speaker_request(...)` (§4.2) runs before `reserve_batch` (`:747`). `BatchResponse` (`:329`) and `BatchSummaryView` (`:356`, built `:985`) gain `speaker_request_id`. `_load_batch_or_404` (`:617`) returns the `BatchRow`. `_compose_one` (`:812`) checks availability **after** `choose_invitation_channel` (`:845`). Dispatch (`:1041`): one `current_verdicts` over all pending recipients; check after `classify_recipient` (`:1105`). |
| `contracts/openapi/smartmatch.json` | `make openapi` in every milestone that changes a request or response model. CI runs `export_openapi.py --check` (`verify.yml:127`). |
| `tests/golden/matching/cba/G-CBA-13-availability-leaves-hash-and-pool-alone.json`, `cba_case.schema.json` | New fixture; schema gains optional `owner_decisions`, case `event_span` / `as_of`, candidate `availability` (C9). |
| `apps/web/legacy-frontend/src/lib/api.ts` | `MatchCandidateExplanation` (`:2297`) + `availability?: MatchAvailability \| null`; `MatchRunRead` (`:2342`) + `availability_recorded`, `availability_unreadable_reason`, `excluded`. `SpeakerInvitationBatch` (`:3114`) and `SpeakerInvitationBatchSummary` (`:3130`) + `speaker_request_id: string \| null`; `createSpeakerInvitationBatch` (`:3201`) input + optional `speakerRequestId`, sent as `speaker_request_id`. |
| `apps/web/legacy-frontend/src/app/pages/AIMatching.tsx` | `CandidateCard` (`:192`) renders the §7 wording. |
| `.../coordinator/CoordinatorInvitations.tsx`, `CoordinatorOutreach.tsx`, `CoordinatorMatchRuns.tsx` | `RecipientRow` (`:188`) wording; both `describeSkip` copies (`Invitations:87`, `Outreach:160`) gain the 2 tokens; `MATCH_INELIGIBILITY_EXPLANATIONS` (`MatchRuns:115`) gains `filed_this_request`. The compose page already sends `matchRunId` on every submit (`CoordinatorInvitations.tsx:433-447`), so the server derives the request; no new input. |

Not touched: `factor_registry.py`, `match_run.py`, `weight_settings.py`, `explanation.py`, `services/worker/**`, the `match_run` table.

## 2. Payload shape — `job.payload["availability"]`

Written by `create_match_run`, one entry per **evaluated** subject (scorable and unscorable, ranked order). Pool-excluded subjects get none: they were never evaluated.

```json
"availability": [
  {"subject_id": "…", "verdict": "excluded",     "state": "blacked_out", "reason": "window",     "as_of": "2026-10-06", "paused_until": null},
  {"subject_id": "…", "verdict": "excluded",     "state": "blacked_out", "reason": "paused",     "as_of": "2026-10-06", "paused_until": "2027-01-10"},
  {"subject_id": "…", "verdict": "undetermined", "state": "unknown",     "reason": "not_stated", "as_of": "2026-10-06", "paused_until": null},
  {"subject_id": "…", "verdict": "eligible",     "state": "available",   "reason": "clear",      "as_of": "2026-10-06", "paused_until": null}
]
```

- `verdict` = `EligibilityOutcome` value; `state` / `reason` = T1 enums; `as_of` ISO date; `paused_until` set exactly when `reason = "paused"` (C6).
- `as_of` = the **UTC** date of the run or compose (`as_of_utc(utc_now())`, C7), the same value T3 uses for the pause floor and T8 for the run date. Window overlap is still computed against the event's **local** dates (`event_local_span`).
- The verdict **annotates**; it removes no one. `candidates` (`match_runs.py:963-968`) is built before and without it.
- `excluded` (C3): the pool's `ExcludedCandidate` list, `[{"subject_id", "reason"}]`, the same shape the `202` returns (`match_runs.py:994`).
- **Back-compat:** no `availability` key → `availability_recorded: false`, every `availability: null`, UI "Availability not recorded for this run". Malformed key (strict reader, `ValueError`) → same, plus `availability_unreadable_reason`; never repaired. No `excluded` key → `excluded: []` on the read.

Read view per candidate: `{verdict, state, reason, as_of, paused_until, changed_since_run: bool | null}`.

## 3. "Changed since this run" on read

1. `stored` = the payload entry. `current` = `current_verdicts(...)` with `as_of = as_of_utc(utc_now())` and the request's event read now (`run.event_need_id`).
2. `changed_since_run = (verdict, reason, paused_until)` of `current` ≠ that of `stored`. `paused_until` is compared so a moved pause date is not shown stale.
3. `null` when the event row can no longer be read in this unit or `event_need_id` is not a UUID (a pre-OQ-CBA-031 run): "not checked", never "unchanged".
4. **Cost:** +2 queries per read, independent of pool size: the event row (1), `get_many` over every evaluated subject (1, ≤ `MAX_CANDIDATES` = 200, `match_runs.py:248`). Skipped entirely when `availability_recorded` is false. Test 17 counts them.

## 4. The batch names its Speaker Request (`0041`), then compose and dispatch re-check

Today a batch has no event: `event_name` / `event_date` are display strings (`schema.py:2600-2601`), and `match_run_id` is optional. C1 (b), owner: the batch gains `speaker_request_id`, so compose and dispatch check against the batch's own Speaker Request, with or without a run.

### 4.1 Migration `0041_invitation_batch_speaker_request`

A Speaker Request is an `event` row with `origin = 'coordinator_entry'` (`schema.py:2348-2350`, `match_run_evidence.load_speaker_request`). Target key: `uq_event_tenant_id (tenant_id, id)` (`schema.py:1133`).

`upgrade()`, in order:

1. `ADD COLUMN speaker_request_id uuid NULL` on `cba_invitation_batch`.
2. Backfill, one statement:

   ```sql
   UPDATE cba_invitation_batch AS b
   SET speaker_request_id = e.id
   FROM match_run AS r
   JOIN event AS e
     ON e.tenant_id = r.tenant_id
    AND e.id::text = r.event_need_id
   WHERE r.tenant_id = b.tenant_id
     AND r.id = b.match_run_id
     AND r.owning_unit_id = b.owning_unit_id
     AND e.host_org_unit_id = b.owning_unit_id
     AND e.origin = 'coordinator_entry'
   ```

   - Text comparison, never `::uuid`: a pre-OQ-CBA-031 `event_need_id` is free text and a cast would abort the revision. Such a row stays NULL.
   - The unit predicates apply §4.2's rule to history: a run or request in another unit (C10) stays NULL, not linked.
   - Not a reconstruction (ADR-0011 rule 1): since OQ-CBA-031 the run's `event_need_id` is written from the request id (`match_runs.py:960`), and the batch recorded the run. The join reads two recorded facts. Rows it cannot resolve stay NULL.
   - Only `cba_invitation_batch` is written. `match_run` is only read, so `0018`'s `match_run_is_immutable` trigger is not involved; `0029` puts no trigger on the batch table.
3. `ADD CONSTRAINT fk_cba_invitation_batch_speaker_request FOREIGN KEY (tenant_id, speaker_request_id) REFERENCES event (tenant_id, id) ON DELETE RESTRICT`. Composite, so a batch can never name another tenant's request. RESTRICT: nothing deletes `event` rows today, and a batch's record of what it invited for must not vanish (CASCADE) or be silently unstamped (SET NULL).

`downgrade()`: drop the FK, then the column. The backfilled values are derivable again on re-upgrade.

Deliberately **not** in the migration:

- **No NOT NULL, no `CHECK ... NOT VALID`.** Legacy hand-picked batches and pre-031 runs have no request to name, and every persistence test that calls `reserve_batch` without one would break. The "new batches must carry it" rule is an API rule (§4.2, C12).
- **No unit FK.** A `(tenant_id, host_org_unit_id, id)` key would need a new unique constraint on `event`. The unit match is enforced where `match_run` already enforces it, in the route (`load_speaker_request`'s scope).
- **No index.** No read filters batches by request, and no code path deletes an `event` row, so the RESTRICT check never scans.

Mirror: `schema.py` adds the column and a named `ForeignKeyConstraint` next to the `match_run` one (`:2614-2618`). `test_schema_matches_migration.py` iterates the whole schema (columns, FKs, nullability, composite anchoring), so it covers the new column with no edit.

### 4.2 `create_invitation_batch` resolves the request

Before `reserve_batch`, same place as `_require_distinct_recipients`:

1. **Run given.** `request_for_run(session, tenant, unit, match_run_id)`. No run in this unit → `404 match_run_not_found` (the read route's code). This closes C10: a run from another unit in the tenant is refused, not stored.
2. **Derive.** The run's request, when its `event_need_id` names a Speaker Request in this unit; else none (a pre-031 run).
3. **Explicit id given.** `load_request_event_time(...)` in this unit with `origin = 'coordinator_entry'`; not found (other unit, other tenant, extracted event, no such id) → `404 speaker_request_not_found` (the match-run create code, `match_runs.py:743-747`). 404 not 403: no confirmation that an id names something elsewhere.
4. **Both, and they differ** → `422 speaker_invitation_request_mismatch`. Both and equal, or explicit with a pre-031 run → the explicit id.
5. **Neither resolves** → rule C12. Plan default R1: `422 speaker_invitation_request_required`. R0 fallback: store NULL and skip the check (§4.3 step 4).
6. `reserve_batch(..., speaker_request_id=resolved)`. On a replay the stored batch's request is reported, never this body's (the existing replay rule).

### 4.3 Compose (`_compose_one`)

1. The request's `EventTime` is read once per batch (step 3 of §4.2 already has it); one `get_many` for the batch's roster hits, not one per recipient.
2. Per recipient, order: roster (`not_on_roster`) → channel (`choose_invitation_channel`) → **availability**. Consent first: a Speaker who said stop is reported as such (`classify_recipient` docstring's ordering rule).
3. `EXCLUDED/window` → `_skip(..., SkipReason.SPEAKER_UNAVAILABLE_ON_DATE)`; `EXCLUDED/paused` → `SPEAKER_INVITATIONS_PAUSED`. Stored `status = skipped` with the reason; no draft, no token.
4. `UNDETERMINED` and `ELIGIBLE` compose as today. `speaker_request_id` NULL (legacy batch; or R0) → no availability check.

### 4.4 Dispatch (`dispatch_invitation_batch`)

1. The event comes from `batch.speaker_request_id` directly: no run hop. One `get_many` over pending recipients. `as_of` = UTC date of the dispatch.
2. Per pending invitation: `classify_recipient` first (unchanged), then availability.
3. `EXCLUDED` → `NotDispatchedView(reason="speaker_unavailable_on_date" | "speaker_invitations_paused")`; the invitation **stays pending**, so clearing the window and dispatching again sends it, as for a consent gap.
4. Request row no longer readable in this unit → no check, same as NULL. The worker's delivery-time check is unchanged: consent only (parent §5.1 names compose and dispatch only).

## 5. Q8 — "filed this request" as a Stage A check

- Rule: `filed_by_user_id is not None and account_user_id is not None and filed_by_user_id == account_user_id`. Both-`None` guard in Python, so NULL never equals NULL.
- `event.filed_by_user_id` exists: `schema.py:1116`, FK `fk_event_filed_by_user` (`:1154-1159`), migration `0033`. NULL = unknown filer (pre-0033) → nobody excluded.
- `speaker_profile.account_user_id` comes from `0039`, which is below `0041` in this branch's chain (C2), so Q8 ships inside T4. No T4b.
- Place: `assemble_cba_pool`, before scoring, so the requester never reaches `rank_cba_candidates`. Reported as `ExcludedCandidate(subject, "filed_this_request")`, stored in the payload and returned on the read (C3); UI words "Filed this request" (C4).
- It bites only once a Host login is bound to a Speaker profile (T6b-5's existing-login merge). T6b-1's new-login mode binds a contact account with no Host role.
- A genuine self-nomination: the Connector adds the person to a batch by hand. Q8 is a pool rule; compose does not re-apply it, and the batch still checks availability against its request.

## 6. Proof: `registry_hash`, `inputs_fingerprint`, `REGISTRY_VERSION` unchanged

| Value | Computed from | Why T4 cannot move it |
|---|---|---|
| `registry_hash` | `weights_fingerprint(weights)`, `handlers.py:1254`; `weights = applied_weights(overrides, model=model)`, `:1225` | `availability` is `ELIGIBILITY`, weight 0 (`factor_registry.py:380-394`); `is_scoring` is false for it (`:266`). T4 edits no registry or weight code. |
| `inputs_fingerprint` | `match_run.py:135`: `event_need_id`, `(subject, utility)` pairs, size, seed, weights | The worker reads only `event_need_id`, `portfolio_size`, `random_seed`, `candidates`, `scoring_mode` (`handlers.py:1042-1074`, `.get`). `availability` and `excluded` are new keys it never reads. `candidates` is unchanged: verdicts annotate and remove no one. |
| `REGISTRY_VERSION` | `factor_registry.py:154` = `2.0.0-approved-oq-cba-004` | File not edited; `test_factor_registry.py:269` pins it. |

`0041` touches only `cba_invitation_batch`; no fingerprint reads it. Q8 changes `candidates` only as naming fewer people would. Test 22e proves it: a run naming {requester, a, b, c} has the same `inputs_hash` as one naming {a, b, c}.

**Golden `G-CBA-13-availability-leaves-hash-and-pool-alone`** (`tests/unit/test_cba_matching_golden.py`): pool of 4, one per verdict (window, paused, not stated, clear). The test:
1. scores the pool through `rank_cba_candidates`;
2. computes `weights_fingerprint` and `inputs_fingerprint` with and without `verdicts_for_pool`;
3. asserts ranking, utilities and both digests identical, and `apply_availability_filter` output in input order;
4. asserts the fixture's hand-written verdict per subject, and `REGISTRY_VERSION` equal to the case's pin.

## 7. Frontend wording (parent §6, no numbers)

| Stored `verdict` / `reason` | Text |
|---|---|
| `eligible` / `clear` | "Available" |
| `excluded` / `window` | "Unavailable on this date (Speaker's statement)" |
| `excluded` / `paused` | "Paused until {paused_until, long date}" |
| `undetermined` / `not_stated` | "Availability not stated" |
| `undetermined` / `event_unresolved` | "Event date not set, so availability was not checked" (C5) |
| `availability` null | "Availability not recorded for this run" |
| `changed_since_run: true` | appended: "— changed since this run" |
| skip / not-dispatched `speaker_unavailable_on_date` | "The Speaker said they cannot speak on this date." |
| skip / not-dispatched `speaker_invitations_paused` | "The Speaker has paused invitations." |
| excluded `filed_this_request` | "Filed this request, so left out of its matching. To invite them anyway, add them to a batch by hand." |

- No score, percentage, count or decimal literal. The only digits come from the date. `test_frontend_match_run_contract.py:161,196` and `test_frontend_invitation_compose_contract.py:303,333` must stay green.
- `RecipientRow` shows the text and stays selectable: the server decides at compose.
- Wording is by state only. Event Hosts never reach these pages.

## 8. TDD tests

CI: `pytest tests/ -m "not e2e"` with Postgres (`verify.yml:107,117`); web `npm run test:components` = vitest `src/**/*.test.tsx` (`vitest.config.ts`). Locally, run one file at a time, against a private database (`smartmatch_b26_t4`), dropped afterwards.

**Migration — `tests/integration/test_invitation_batch_speaker_request_migration.py`** (new; `migration_harness.scratch_database` + `alembic`, the `test_match_run_scoring_mode_migration.py` pattern: bring a scratch DB to `0040`, seed, upgrade)
- M1. `test_upgrade_backfills_the_request_from_a_same_unit_run`
- M2. `test_upgrade_leaves_null_for_a_batch_without_a_run`
- M3. `test_upgrade_leaves_null_for_a_run_whose_need_is_not_a_uuid` (pre-031 text; the revision must not abort)
- M4. `test_upgrade_leaves_null_when_the_run_or_request_is_in_another_unit` (two rows: run in unit B; run in A naming a request hosted by B)
- M5. `test_the_fk_refuses_a_request_from_another_tenant`
- M6. `test_the_fk_restricts_deleting_a_request_a_batch_names`
- M7. `test_downgrade_drops_column_and_fk_and_upgrade_reapplies`

**Drift and persistence**
- M8. `tests/integration/test_schema_matches_migration.py` green unedited (whole-schema: column, FK, nullability, composite anchor).
- M9. `tests/integration/test_cba_invitation_batch.py::test_reserve_batch_stores_and_reads_back_the_speaker_request` (and a replay returns the first row's value).
- Head-pin constants in the 5 integration files of §1 move to `0041_invitation_batch_speaker_request`.

**Unit — `tests/unit/test_availability_verdict.py`** (no DB)
1. `test_each_parent_5_1_row_maps_to_its_verdict` (5 parametrized rows)
2. `test_verdicts_cover_every_subject_in_pool_order`
3. `test_payload_round_trip_is_exact`
4. `test_payload_reader_refuses_unknown_verdict_missing_field_and_mismatched_reason`
5. `test_unchanged_verdict_reason_and_pause_is_not_changed`
6. `test_moved_pause_date_is_changed`
7. `test_as_of_is_the_utc_date` (23:30 PDT 5 Oct → 6 Oct; a naive datetime is refused)
8. `test_window_overlap_uses_the_event_local_dates_not_as_of` (event 5 Oct 23:30 PDT, window 5 Oct → excluded, while `as_of` is 6 Oct)
9. `test_event_time_from_columns_for_each_precision`
10. `test_filed_this_request_rule` (match; other filer; `None` filer; `None` account; both `None`)

**Unit — `tests/unit/test_cba_invitations_domain.py`** (new)
11. `test_availability_skip_reasons_map_from_excluded_only`

**Golden — `tests/unit/test_cba_matching_golden.py`**
12. `test_g_cba_13_availability_leaves_hash_and_pool_alone`. `REQUIRED_CASE_IDS` (`:87`) → `range(1, 14)`; `:284-291` accepts `owner_decisions` in place of `adr_proposals`.

**Contract — batch request resolution, `tests/contract/test_cba_invitations_api.py`** (helpers: `_insert_speaker_request(unit)`, `_insert_run_for_event` via `MatchRunRepository.record`; `create_batch` (`:195`) defaults `speaker_request_id` to a request seeded in setup, so the 24 existing calls keep passing under R1)
13. `TestBatchRequest::test_a_run_derives_the_speaker_request`
14. `TestBatchRequest::test_a_hand_picked_batch_stores_its_named_request`
15. `TestBatchRequest::test_refusals` (parametrized: run in another unit → 404 `match_run_not_found`; request in another unit, another tenant, or an extracted event → 404 `speaker_request_not_found`; request ≠ run's request → 422 `speaker_invitation_request_mismatch`; neither → 422 `speaker_invitation_request_required` (R1 only); nothing reserved in any case)
16. `TestBatchRequest::test_list_and_read_return_the_speaker_request`

**Contract — `tests/contract/test_match_runs_api.py`** (`integration`; `_insert_speaker_request` `:155` gains `filed_by_user_id`)
17. `test_availability_costs_one_query_on_create_and_two_on_read` (`before_cursor_execute` count)
18. `test_the_payload_records_a_verdict_for_every_evaluated_candidate`
19. `test_a_run_without_availability_reads_not_recorded`
20. `test_a_window_added_after_the_run_reads_changed_since`
21. `test_availability_moves_neither_inputs_hash_nor_registry_hash`; `test_an_excluded_speaker_stays_on_the_shortlist_in_place`
22. Q8: (a) `test_the_requester_is_excluded_as_filed_this_request`; (b) `test_another_hosts_request_excludes_nobody`; (c) `test_a_speaker_with_no_bound_login_is_never_excluded`; (d) `test_a_request_with_no_recorded_filer_excludes_nobody`; (e) `test_excluding_the_requester_fingerprints_like_not_naming_them`; (f) `test_the_read_lists_the_excluded_requester` (C3)
23. `test_a_malformed_availability_block_is_reported_not_repaired`

**Contract — compose and dispatch, `tests/contract/test_cba_invitations_api.py`**
24. `TestComposeBatch::test_a_blacked_out_speaker_is_skipped_as_unavailable_on_date`
25. `TestComposeBatch::test_a_paused_speaker_is_skipped_as_invitations_paused`
26. `TestComposeBatch::test_an_unstated_speaker_is_invited`
27. `TestComposeBatch::test_a_hand_picked_batch_is_checked_against_its_request` (no `match_run_id`)
28. `TestComposeBatch::test_suppression_outranks_unavailability`
29. `TestDispatch::test_a_window_added_after_compose_refuses_dispatch_and_stays_pending`
30. `TestDispatch::test_clearing_the_window_lets_a_second_dispatch_send`
31. `TestDispatch::test_a_legacy_batch_with_no_request_is_not_checked` (row reserved through the repository with NULL)

**Web — vitest**
32. `src/app/pages/AIMatching.test.tsx`: each §7 row; "not recorded"; "changed since"; no `%` in the text
33. `src/app/pages/coordinator/CoordinatorInvitations.test.tsx`: `RecipientRow` wording; both skip tokens
34. `src/app/pages/coordinator/CoordinatorOutreach.test.tsx`: `not_dispatched` renders both tokens
35. `src/app/pages/coordinator/CoordinatorMatchRuns.test.tsx`: `filed_this_request` explanation

`tests/unit/test_frontend_invitation_compose_contract.py:101-107`: add `speaker_request_id` to the fields `createSpeakerInvitationBatch` must carry.

## 9. Commit milestones

One commit per milestone; each ends green on its own tests, run one file at a time.

1. `feat: 0041 links invitation batches to their Speaker Request` — migration, mirror, `BatchRow` / `reserve_batch`, head pins, README; tests M1–M9.
2. `test: failing T4 domain and golden tests` — tests 1–12, fixture, schema.
3. `feat: availability verdict domain and skip reasons` — `availability_verdict.py`, `SkipReason`; 1–12 green.
4. `feat: batches resolve and report their Speaker Request` — `_resolve_speaker_request` (steps 1–4 and 6, C10), response fields, `make openapi`, `api.ts` batch types; tests 13, 14, 15 (except R1 row), 16.
5. `feat: a new batch must name its Speaker Request` — §4.2 step 5 R1, `create_batch` helper default; test 15 R1 row. **Isolated so it can be reverted if C12 goes to R0.**
6. `feat: store availability verdicts on match runs and read changed-since` — `availability_reads.py`, `match_run_evidence.py` time fields, `match_runs.py`, `excluded` (C3), `make openapi`; tests 17–21, 23.
7. `feat: re-check availability at compose and dispatch` — `cba_invitations.py` router; tests 24–31.
8. `feat: exclude the requester from their own request's pool` — Q8; test 22.
9. `feat: availability wording on shortlist, compose and outreach pages` — `api.ts`, four pages; tests 32–35.

## 10. Contradictions and choices

| # | Issue | Ruling |
|---|---|---|
| **C1** | A batch has no event; only the optional `match_run_id` led to one. | **(b), owner 2026-09-23.** `0041` adds `speaker_request_id`: nullable, composite tenant FK to `event`, backfilled from the run (§4.1). The route derives it from a run, accepts it for hand-picked batches, refuses another unit's (§4.2). |
| **C2** | Q8 needs `speaker_profile.account_user_id` (`0039`). | `0041` sits on `0040` → `0039`, so Q8 lands inside T4 (milestone 8). No T4b. Branch stacked on T8a. |
| **C3** | `excluded` lived only on the `202`. | **(b).** Stored in the payload, returned on the read (additive; the worker ignores it). |
| C4 | The parent's reason is wording. | Token `filed_this_request`, UI words "Filed this request". |
| C5 | No wording for `UNDETERMINED/event_unresolved`. | §7 row added. |
| C6 | "Paused until …" needs a date. | `paused_until` in the payload. |
| **C7** | `as_of` zone. | **UTC** (overrides the event-zone proposal): the UTC run / compose / dispatch date, same as T3's pause floor and T8's run date. Window overlap stays on the event's local dates. Consequence, accepted: a pause "until 10 Jan" lifts at 00:00 UTC on 11 Jan, which is 16:00 Pacific on 10 Jan. |
| C8 | `submit_command` fingerprints the whole payload (`commands.py:194`). With `as_of` in it, a retry under the same key across a **UTC** midnight, or after an availability edit, gets `409`. | Accept; one sentence in `create_match_run`'s docstring. |
| C9 | The golden runner allows only ADR-0016 cases. | Optional `owner_decisions` plus the availability fields; the runner accepts either field. T8c reuses it for G-CBA-14…19. |
| C10 | `create_invitation_batch` accepted a `match_run_id` from another unit (FK tenant-only, `schema.py:2614-2618`). | **Folded in:** deriving the request reads the run scoped to the unit, so a foreign run is `404 match_run_not_found` (§4.2 step 1). Backfill leaves such history NULL. |
| C11 | `apply_availability_filter`'s docstring says it runs after the shortlist. | Per-subject and order-preserving; noted in the docstring. |
| **C12 open** | Owner intent: "every batch is checked". Must a **new** batch name a request? | **R1 (plan default):** the API requires one — derived from a run or given — else `422 speaker_invitation_request_required`; the column stays nullable for history. Breaks no shipped client: the compose page always sends `matchRunId` and the e2e step sends `match_run_id`. Breaks 24 test calls through 1 helper (`test_cba_invitations_api.py:195`), fixed in the helper. A hand-picked API caller with no request is refused. **R0 (least change):** optional; a batch with neither is stored NULL and never checked. Milestone 5 is the only commit that differs. |
| C13 | Where the unit match is enforced. | Route, like `match_run`'s own link to its request (`load_speaker_request`'s scope). A unit FK needs a new unique constraint on `event`; not worth it for one column. |

---

**Next action (under two minutes):** create `tests/integration/test_invitation_batch_speaker_request_migration.py` with M1's seed (one unit, one request, one run naming it, one batch naming the run).
