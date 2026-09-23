# B26 T4 — Stage A wiring: stored verdicts, "changed since", compose/dispatch re-check, Q8

**Next action:** write `tests/unit/test_availability_verdict.py` (§8, tests 1–9) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §5.1, §6 (MatchRuns/Invitations row), §7 row 4, §8 T4, §9 Q8, §11.
Depends on T1 (`origin/feat/b26-t1`: `availability_state_for_event`, `event_local_span`, `AvailabilityAssessment.to_evidence`, `AvailabilityReason`)
and T2 (`origin/feat/b26-t2` plan §3: `SpeakerAvailabilityRepository.get_many`, one query, absent key = no row). Branch from `main` after both merge.
Q8 also needs `speaker_profile.account_user_id` from `0039` (T6b-1) — see C2.

## 1. Files

| Path | Change |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/availability_verdict.py` | **New, pure.** `StoredVerdict` (frozen: `subject_id`, `verdict: EligibilityOutcome`, `state`, `reason`, `as_of`, `paused_until`); `verdicts_for_pool(subject_ids, statements, event_span, as_of)` → calls T1 `availability_state_for_event` per subject, then `apply_availability_filter` (`eligibility.py:110`) over the pool in pool order; `to_payload` / `from_payload` (strict, `explanation_from_payload` discipline, `explanation.py:653`); `changed_since(stored, current)`; `as_of_for(event_time, now)`; `event_time_from_columns(...)`; `filed_this_request(filed_by_user_id, account_user_id)`. |
| `python/smartmatch_domain/smartmatch_domain/cba_invitations.py` | `SkipReason` (`:174-197`) gains `SPEAKER_UNAVAILABLE_ON_DATE = "speaker_unavailable_on_date"` and `SPEAKER_INVITATIONS_PAUSED = "speaker_invitations_paused"`, plus `skip_reason_for_availability(StoredVerdict) -> SkipReason \| None`. `classify_recipient` (`:283`) and `_SKIP_SEVERITY` (`:319`) unchanged: they rank channels, not people. No migration: `cba_invitation.skip_reason` has only the iff CHECK (`schema.py:2718`). |
| `services/api/smartmatch_api/availability_reads.py` | **New.** DB side: `load_event_time(session, tenant_id, event_id)`; `current_verdicts(session, tenant_id, subject_ids, event_time, now)` = one `get_many` + `verdicts_for_pool`; `event_for_match_run(session, tenant_id, unit_id, match_run_id)`. |
| `services/api/smartmatch_api/match_run_evidence.py` | `SpeakerRequestEvidence` (`:169-202`) gains `filed_by_user_id` and `event_time`; `load_speaker_request` select (`:270-279`) adds `filed_by_user_id`, `time_precision`, `starts_at`, `ends_at`, `on_date`, `time_zone`. `EXCLUSION_FILED_THIS_REQUEST = "filed_this_request"`. `assemble_cba_pool` (`:353-419`): after the profile check (`:394-396`), before `match_ineligibility_reason` (`:403`), exclude when `filed_this_request(request.filed_by_user_id, row.account_user_id)`; `_profiles_by_professional_id` (`:440-457`) selects `account_user_id`. |
| `services/api/smartmatch_api/routers/match_runs.py` | Create (`:795`): after `explain_candidates`, one `current_verdicts` call over every evaluated subject; payload (`:961-989`) gains `availability` and `excluded` (C3). Read (`:1148`): `_read_stored_availability(payload)`, one `current_verdicts` call, `AvailabilityView` on each `CandidateExplanationView` (`:443`); `MatchRunResponse` (`:496`) gains `availability_recorded`, `availability_unreadable_reason`, `excluded`. `ExcludedCandidateView.reason` description (`:325-337`) lists `filed_this_request`. |
| `services/api/smartmatch_api/routers/cba_invitations.py` | `_load_batch_or_404` (`:617`) returns the batch row. Create (`:703`): resolve the run's event once; `_compose_one` (`:812`) checks availability **after** `choose_invitation_channel` (`:845`). Dispatch (`:1041`): one `current_verdicts` for all pending recipients; check after `classify_recipient` (`:1105`). |
| `tests/golden/matching/cba/G-CBA-13-availability-leaves-hash-and-pool-alone.json`, `cba_case.schema.json` | New fixture; schema gains optional `owner_decisions`, case `event_span` / `as_of`, candidate `availability` (C9). |
| `apps/web/legacy-frontend/src/lib/api.ts` | `MatchCandidateExplanation` (`:2297`) + `availability?: MatchAvailability \| null`; `MatchRunRead` (`:2342`) + `availability_recorded`, `availability_unreadable_reason`, `excluded`. |
| `apps/web/legacy-frontend/src/app/pages/AIMatching.tsx` | `CandidateCard` (`:192`) renders the §7 wording. |
| `.../coordinator/CoordinatorInvitations.tsx`, `CoordinatorOutreach.tsx`, `CoordinatorMatchRuns.tsx` | `RecipientRow` (`:188`) wording; both `describeSkip` copies (`Invitations:87`, `Outreach:160`) gain the 2 tokens; `MATCH_INELIGIBILITY_EXPLANATIONS` (`MatchRuns:115`) gains `filed_this_request`. |

Not touched: `factor_registry.py`, `match_run.py`, `weight_settings.py`, `explanation.py`, `services/worker/**`, any migration.

## 2. Payload shape — `job.payload["availability"]`

Written by `create_match_run`, one entry per **evaluated** subject (scorable and unscorable, ranked order). Pool-excluded subjects get none: they were never evaluated.

```json
"availability": [
  {"subject_id": "…", "verdict": "excluded",     "state": "blacked_out", "reason": "window",     "as_of": "2026-10-05", "paused_until": null},
  {"subject_id": "…", "verdict": "excluded",     "state": "blacked_out", "reason": "paused",     "as_of": "2026-10-05", "paused_until": "2027-01-10"},
  {"subject_id": "…", "verdict": "undetermined", "state": "unknown",     "reason": "not_stated", "as_of": "2026-10-05", "paused_until": null},
  {"subject_id": "…", "verdict": "eligible",     "state": "available",   "reason": "clear",      "as_of": "2026-10-05", "paused_until": null}
]
```

- `verdict` = `EligibilityOutcome` value; `state` / `reason` = T1 enums; `as_of` ISO date; `paused_until` set exactly when `reason = "paused"` (C6).
- `as_of` = today in the event's own zone (`as_of_for`); for an `unresolved` event the UTC date, unused because T1 returns `EVENT_UNRESOLVED` first (C7).
- The verdict **annotates**; it removes no one. `candidates` (`match_runs.py:963-968`) is built before and without it.
- **Back-compat:** no `availability` key → `availability_recorded: false`, every `availability: null`, UI "Availability not recorded for this run". Malformed key (strict reader, `ValueError`) → same, plus `availability_unreadable_reason`; never repaired.

Read view per candidate: `{verdict, state, reason, as_of, paused_until, changed_since_run: bool | null}`.

## 3. "Changed since this run" on read

1. `stored` = the payload entry. `current` = `current_verdicts(...)` with `now = utc_now()` and the request's event read now.
2. `changed_since_run = (verdict, reason, paused_until)` of `current` ≠ that of `stored`. `paused_until` is compared so a moved pause date is not shown stale.
3. `null` when the event row can no longer be read or `event_need_id` is not a UUID (a pre-OQ-CBA-031 run): "not checked", never "unchanged".
4. **Cost:** +2 queries per read, independent of pool size: the event row (1), `get_many` over every evaluated subject (1, ≤ `MAX_CANDIDATES` = 200, `match_runs.py:248`). Skipped entirely when `availability_recorded` is false. Test 13 counts them.

## 4. Compose and dispatch re-check

The batch has no event column: `event_name` / `event_date` are free text (`routers/cba_invitations.py:233-246`). The event is reached only through `match_run_id` → `match_run.event_need_id` → `event` (C1).

**Compose** (`create_invitation_batch`):
1. `event = event_for_match_run(...)`, read once per batch: `None` when `match_run_id` is null, the run is outside this unit, or `event_need_id` is not a UUID.
2. Per recipient, order: roster (`not_on_roster`) → channel (`choose_invitation_channel`) → **availability**. Consent first: a Speaker who said stop is reported as such (`classify_recipient` docstring's ordering rule).
3. `EXCLUDED/window` → `_skip(..., SkipReason.SPEAKER_UNAVAILABLE_ON_DATE)`; `EXCLUDED/paused` → `SPEAKER_INVITATIONS_PAUSED`. Stored `status = skipped` with the reason; no draft, no token.
4. `UNDETERMINED` and `ELIGIBLE` compose as today. `event is None` → no availability check.
5. Statements: one `get_many` for the batch's roster hits, not one per recipient.

**Dispatch** (`dispatch_invitation_batch`):
1. Same event resolution from the batch row; one `get_many` over pending recipients.
2. Per pending invitation: `classify_recipient` first (unchanged), then availability.
3. `EXCLUDED` → `NotDispatchedView(reason="speaker_unavailable_on_date" | "speaker_invitations_paused")`; the invitation **stays pending**, so clearing the window and dispatching again sends it, as for a consent gap.
4. The worker's delivery-time check is unchanged: consent only. Availability is not re-checked at delivery (parent §5.1 names compose and dispatch only).

## 5. Q8 — "filed this request" as a Stage A check

- Rule: `filed_by_user_id is not None and account_user_id is not None and filed_by_user_id == account_user_id`. Both-`None` guard in Python, so NULL never equals NULL.
- `event.filed_by_user_id` exists: `schema.py:1116`, FK `fk_event_filed_by_user` (`:1154-1159`), migration `0033`. NULL = unknown filer (pre-0033) → nobody excluded.
- Place: `assemble_cba_pool`, before scoring, so the requester never reaches `rank_cba_candidates`. Reported as `ExcludedCandidate(subject, "filed_this_request")`; UI words "Filed this request" (C4).
- `speaker_profile.account_user_id` does not exist on `main` (it comes with `0039`). Before `0039`, the rule cannot run, and would be a no-op anyway. The only account that could file a request is a Host's, and until T6b-5's existing-login merge no Speaker profile is bound to one. T6b-1's new-login mode binds `account_user_id = professional_id`, a contact account with no Host role. C2 covers the sequencing.
- A genuine self-nomination: the Connector invites the person in a batch with no `match_run_id` (§4 step 4 skips the check).

## 6. Proof: `registry_hash`, `inputs_fingerprint`, `REGISTRY_VERSION` unchanged

| Value | Computed from | Why T4 cannot move it |
|---|---|---|
| `registry_hash` | `weights_fingerprint(weights)`, `handlers.py:1254`; `weights = applied_weights(overrides, model=model)`, `:1225` | `availability` is `ELIGIBILITY`, weight 0 (`factor_registry.py:380-394`); `is_scoring` is false for it (`:266`). T4 edits no registry or weight code. |
| `inputs_fingerprint` | `match_run.py:135`: `event_need_id`, `(subject, utility)` pairs, size, seed, weights | The worker reads only `event_need_id`, `portfolio_size`, `random_seed`, `candidates`, `scoring_mode` (`handlers.py:1042-1074`, `.get`). `availability` and `excluded` are new keys it never reads. `candidates` is unchanged: verdicts annotate and remove no one. |
| `REGISTRY_VERSION` | `factor_registry.py:154` = `2.0.0-approved-oq-cba-004` | File not edited; `test_factor_registry.py:269` pins it. |

Q8 changes `candidates` only as naming fewer people would. Test 18e proves it: a run naming {requester, a, b, c} has the same `inputs_hash` as one naming {a, b, c}.

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

CI: `pytest tests/ -m "not e2e"` with Postgres (`verify.yml:107,117`); web `npm run test:components` = vitest `src/**/*.test.tsx` (`vitest.config.ts`). Locally, run one file at a time.

**Unit — `tests/unit/test_availability_verdict.py`** (no DB)
1. `test_each_parent_5_1_row_maps_to_its_verdict` (5 parametrized rows)
2. `test_verdicts_cover_every_subject_in_pool_order`
3. `test_payload_round_trip_is_exact`
4. `test_payload_reader_refuses_unknown_verdict_missing_field_and_mismatched_reason`
5. `test_unchanged_verdict_reason_and_pause_is_not_changed`
6. `test_moved_pause_date_is_changed`
7. `test_as_of_is_today_in_the_event_zone` (23:30 PDT 5 Oct → 5 Oct, while UTC is 6 Oct)
8. `test_event_time_from_columns_for_each_precision`
9. `test_filed_this_request_rule` (match; other filer; `None` filer; `None` account; both `None`)

**Unit — `tests/unit/test_cba_invitations_domain.py`** (new)
10. `test_availability_skip_reasons_map_from_excluded_only`

**Golden — `tests/unit/test_cba_matching_golden.py`**
11. `test_g_cba_13_availability_leaves_hash_and_pool_alone`. `REQUIRED_CASE_IDS` (`:87`) → `range(1, 14)`; `:284-291` accepts `owner_decisions` in place of `adr_proposals`.

**Contract — `tests/contract/test_match_runs_api.py`** (`integration`; `_insert_speaker_request` `:155` gains `filed_by_user_id`)
12. `test_the_payload_records_a_verdict_for_every_evaluated_candidate`
13. `test_availability_costs_one_query_on_create_and_two_on_read` (`before_cursor_execute` count)
14. `test_a_run_without_availability_reads_not_recorded`
15. `test_a_window_added_after_the_run_reads_changed_since`
16. `test_availability_moves_neither_inputs_hash_nor_registry_hash`
17. `test_an_excluded_speaker_stays_on_the_shortlist_in_place`
18. Q8: (a) `test_the_requester_is_excluded_as_filed_this_request`; (b) `test_another_hosts_request_excludes_nobody`; (c) `test_a_speaker_with_no_bound_login_is_never_excluded`; (d) `test_a_request_with_no_recorded_filer_excludes_nobody`; (e) `test_excluding_the_requester_fingerprints_like_not_naming_them`; (f) `test_the_read_lists_the_excluded_requester`
19. `test_a_malformed_availability_block_is_reported_not_repaired`

**Contract — `tests/contract/test_cba_invitations_api.py`** (helper `_insert_run_for_event` via `MatchRunRepository.record`)
20. `TestComposeBatch::test_a_blacked_out_speaker_is_skipped_as_unavailable_on_date`
21. `TestComposeBatch::test_a_paused_speaker_is_skipped_as_invitations_paused`
22. `TestComposeBatch::test_an_unstated_speaker_is_invited`
23. `TestComposeBatch::test_a_batch_without_a_match_run_is_not_availability_checked`
24. `TestComposeBatch::test_suppression_outranks_unavailability`
25. `TestDispatch::test_a_window_added_after_compose_refuses_dispatch_and_stays_pending`
26. `TestDispatch::test_clearing_the_window_lets_a_second_dispatch_send`

**Web — vitest**
27. `src/app/pages/AIMatching.test.tsx`: each §7 row; "not recorded"; "changed since"; no `%` in the text
28. `src/app/pages/coordinator/CoordinatorInvitations.test.tsx`: `RecipientRow` wording; both skip tokens
29. `src/app/pages/coordinator/CoordinatorOutreach.test.tsx`: `not_dispatched` renders both tokens
30. `src/app/pages/coordinator/CoordinatorMatchRuns.test.tsx`: `filed_this_request` explanation

## 9. Commit milestones

1. `test: failing T4 domain and golden tests` — tests 1–11, fixture, schema.
2. `feat: availability verdict domain and skip reasons` — `availability_verdict.py`, `SkipReason`; 1–11 green.
3. `feat: store availability verdicts on match runs and read changed-since` — `availability_reads.py`, `match_run_evidence.py` time fields, `match_runs.py`; tests 12–17, 19.
4. `feat: re-check availability at compose and dispatch` — `cba_invitations.py` router; tests 20–26.
5. `feat: exclude the requester from their own request's pool` — Q8; test 18. **Only if `0039` is on `main`**, else T4b (C2).
6. `feat: availability wording on shortlist, compose and outreach pages` — `api.ts`, four pages; tests 27–30.

## 10. Contradictions and choices

| # | Issue | Options | Proposed |
|---|---|---|---|
| **C1 must-decide** | Q4: "compose and dispatch re-check". A batch has no event (`event_name`/`event_date` are display strings, `schema.py:2600-2601`). Only `match_run_id` leads to one, and it is optional. | (a) check only when the batch has a run in this unit; hand-picked batches are not checked. (b) add `speaker_request_id` to the batch: a migration inside T4, and a renumber against 0038–0040. (c) require `match_run_id`: breaks hand-picked batches. | **(a)**; (b) as a later card. |
| **C2 must-decide** | Q8 reads `speaker_profile.account_user_id` (`0039`, T6b-1). §8 lists T4 as depending on T2 only. The rule bites only after T6b-5 (existing-login merge). | (a) T4's PR waits for `0039`. (b) ship availability now; Q8 lands as milestone 5 if `0039` is on `main`, else follow-up **T4b**. (c) guard on column presence: rejected, because `schema.py` is static and the drift test forbids a conditional mirror. | **(b)**. |
| **C3 must-decide** | Q8: "the run reports them in its `excluded` list". Today `excluded` lives only on the `202` (`match_runs.py:994`). It is not in the payload or on the read (`:496-560`), so it is gone once the Connector leaves the page. | (a) keep it `202`-only. (b) also store `excluded` in the payload and return it on the read (additive; the worker ignores it). | **(b)**. |
| C4 | The parent's reason is wording ("filed this request"); every existing reason is a stable snake_case token (`match_run_evidence.py:143-165`). | Token `filed_this_request`, UI words "Filed this request". | As proposed. |
| C5 | §6 gives no wording for `UNDETERMINED/event_unresolved`. | Add the §7 row. | As proposed. |
| C6 | The brief's payload fields (verdict, state, reason, as_of) cannot render §6's "Paused until …". | Add `paused_until`. | As proposed. |
| C7 | T1 left the `as_of` zone to T4. §5.2 uses the UTC run date for ELI. | (a) today in the event's zone; (b) UTC date. | **(a)**: a pause ends on the local date the Speaker typed. T8b keeps §5.2's own rule. |
| C8 | `submit_command` fingerprints the whole payload (`commands.py:194`). Once `as_of` is in it, a retry under the same key across a local midnight, or after an availability edit, gets `409`. | Accept (the explanations already carry this risk) / strip keys from the fingerprint (`commands.py` change). | Accept; one sentence in `create_match_run`'s docstring. |
| C9 | The golden runner allows only ADR-0016 cases: `REQUIRED_CASE_IDS` 1–12, `adr_proposals` 1–10 required, schema `additionalProperties: false`. | Optional `owner_decisions` (e.g. `["B26 Q4", "B26 §5.1"]`) plus the availability fields; the runner accepts either field. T8c reuses it for G-CBA-14…19. | As proposed. |
| C10 | `create_invitation_batch` accepts a `match_run_id` from another unit in the tenant. The FK is tenant-only (`schema.py:2614-2618`); pre-existing. | T4 reads the run scoped to the unit, so a mismatch is not checked; refusing it is a later card. | Later. |
| C11 | `apply_availability_filter`'s docstring says it runs after the shortlist; T4 runs it at create over the whole evaluated pool. | It is per-subject and order-preserving, so each shortlisted subject's verdict is the same. | As proposed; note it in the docstring. |

---

**Next action (under two minutes):** create `tests/unit/test_availability_verdict.py` with test 1's five parametrized rows.
