# 007 — Make the one refresh visible (#329)

Lane C, branch `oct14/refresh-visibility`, base `origin/main`. No migration.

## Current behavior (verified against the worktree, 2026-10-06)

- `AskingStateView` (`services/api/smartmatch_api/routers/exercise_results_models.py:392-408`) = `choice`, `choices`, `refreshed`, `refresh_counts`. No time, no round-one fact.
- `RefreshCountsView` (`:378-389`) = three counts. No denominator, no before/after.
- `RefreshView` (`:411-426`) = `choice` + the same three counts, flat. No time.
- `read_asking_choice` (`exercise_results.py:333-362`) never reads the round-one run.
- `choose_asking` (`:371-401`) accepts a choice with no round-one run (200).
- `refresh_profiles` (`:430-500`) holds `utc_now()` and does not return it.
- `invited_without_a_card` (`exercise_results_refresh.py:100-123`) is the "22"; computed at `:228`, then dropped.
- `ListEntryView` (`exercise_matching_models.py:377-407`) has no refresh field; non-responders are on the list with no mark.
- Screen (`ExerciseAskingForMore.tsx`): choice cards are never gated on round one (`:393-398`); the button's shut label is "Your team has already asked" with no time (`:472`); three figures only (`:505-529`); the round-one probe is two extra client requests (`:93-114`).

## Ordered change list

1. `python/smartmatch_domain/smartmatch_domain/exercise/markers.py:84-103` — extract `marker_for(*, has_card, attended_event_count)`; `derive_marker` delegates. One rule for the list marker and the all-rows count. No behavior change.
2. `services/api/smartmatch_api/routers/exercise_results_refresh.py` — add `RefreshReport` (frozen dataclass: `counts`, `invited_without_card`, `marker_counts_before`, `marker_counts_after`), `marker_counts(profiles, *, with_overlay)`, `refresh_report(profiles, invited_profile_nos)`. Denominator = `invited ∩ base stated_interests is None` (stable across the refresh). Before = ingest rule on base fields over **every** row; after = same rows with the overlay applied.
3. `exercise_results_models.py`
   - `RefreshCountsView` += `invited_without_card: int`, `marker_counts_before: dict[str, int]`, `marker_counts_after: dict[str, int]`. The one shared shape (#330 reuses it).
   - `AskingStateView` += `refreshed_at: datetime | None`, `first_round_results: bool`, `first_round_event_name: str | None`.
   - `RefreshView` += `refreshed_at: datetime`, `refresh_counts: RefreshCountsView`. The three flat counts stay (additive).
   - `refresh_counts_view(report)` builder; `asking_state_view` takes the new facts.
4. `exercise_results.py`
   - `read_asking_choice`: reads `get_run_for_round(FIRST_ROUND)` and `datasets.list_events` (new `DatasetRepository` dependency); builds the report from the stored run's invited set when refreshed.
   - `choose_asking`: after `_choice_or_refusal` (422 stays first), no round-one run → 409 `exercise_no_first_round_results` (existing code and sentence).
   - `refresh_profiles`: after the claim, re-reads the team's view and returns `refreshed_at` + `refresh_counts` from it, so POST and every later GET are one derivation.
5. `exercise_matching_models.py` — `first_round_event(events)`; `ProfileFacts.refresh_marks`; `ListEntryView.refresh_marks: list[str]` (`new_card`, `new_event`, `stopped_responding`, in that order; a profile may carry several); `RankedListView.first_round_event_name: str | None` so the chip can say "New: went to Northline" without a second request.
6. `apps/web/legacy-frontend/src/lib/exerciseClient.ts` — mirror the fields.
7. `apps/web/legacy-frontend/src/app/pages/exercise/refreshWording.ts` (new) — `formatClockTime`, `refreshSummarySentences`, `refreshMarkLabel`, `markerCountLines`. Every sentence containing "refresh" is composed here.
8. `RefreshSummary.tsx` (new) — done-tone notice with the summary + the before → after lines.
9. `ExerciseAskingForMore.tsx` — drop the two-request probe; the choice cards render only when `first_round_results`; before that one reason line. Shut button label "Already refreshed at 10:42 AM". A raced second press (409 `exercise_already_refreshed`) reloads and shows the same line.
10. `RankedList.tsx` (+ callers `ExerciseMatching.tsx`, `MatchingCompareView.tsx`) — chips beside the name for each mark.
11. `docs/design/class-exercise/DESIGN.md` — §6.7 (marks), §6.19 (summary + before/after), §7.9, §11.1 rows beside the existing "Asking" rows.

## Test plan

- `tests/unit/test_exercise_markers.py` (or the existing markers test file): `marker_for` three cases + empty card still a card.
- `tests/unit/test_exercise_refresh_report.py` (new): before/after over every row including the major-less one; denominator does not shrink after overlay cards land; non-responders move no marker.
- `tests/unit/exercise_results_router/test_exercise_results_refresh.py`: POST carries `refreshed_at` + `refresh_counts`; GET `refreshed_at` equals POST's; second press writes nothing; choice before round one → 409; marks on this team's list only.
- `tests/unit/test_exercise_asking_counts.py`: GET `refresh_counts` == POST `refresh_counts`; `first_round_results` flips.
- Mechanical churn (choice now needs a run): `test_exercise_results_panels.py`, `test_exercise_results_asking_wording.py`, `test_exercise_asking_counts.py`, `test_exercise_results_refresh.py`, `test_exercise_results_contract.py`.
- `tests/unit/test_exercise_matching_router.py`: `refresh_marks` per overlay effect, empty pre-refresh, isolation.
- Vitest: `ExerciseAskingForMore.test.tsx`, `RankedList.test.tsx`, new `refreshWording.test.ts`.
- Gates: `make format-check lint typecheck imports scan VENV=<parent>/.venv`.

## Acceptance (Oct-2 checklist §6)

- "The choice appears only after the team has its round-one results." — step 4 + 9.
- "The refresh button is grey until a way of asking has been chosen, and says why." — already true; kept and pinned.
- "After pressing it, a summary appears in plain words. Example: 'Refresh done at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding.'" — steps 2-4, 7-9.
- "The 'how much we know' counts for all 300 change, and the screen shows before and after. Example: 'Completed card: 70 → 82.'" — steps 2, 3, 8.
- "The changed profiles are marked in the list (for example 'new card' or 'new: went to Northline'), so a team can see who changed." — steps 5, 10.
- "Under 'required,' about 15% of those without a card are marked 'stopped responding,' and the list shows this." — `stopped_responding` mark.
- "Pressing refresh a second time does nothing and says 'Already refreshed at 10:42 AM.'" — step 9.
- "One team's refresh changes nothing for any other team." — existing test + marks isolation test.
- §7 "Profiles marked 'stopped responding' are either left off the list or clearly marked on it." — marked.

## Decision status

| # | Question | Default taken | Source |
|---|---|---|---|
| C1 | Non-responders: mark or exclude | **Mark** on the list | brief §5.1 |
| C2 | "refreshed" vs product voice "asked" for the summary and shut line | **Ann's words** ("Refresh done at…", "Already refreshed at…"), composed client-side; existing "Ask them now" wording untouched | brief §5.5 |
| C3 | Refusal code for a choice before round one | Reuse `exercise_no_first_round_results` | brief §5.6 |
| C4 | Before round one: hide the choice cards or grey them | **Hide**, with one reason line (checklist: "appears only after") | checklist L102 |
| C5 | Round-one event name for "went to X" | Server field `first_round_event_name` on `AskingStateView` and `RankedListView` | brief §5.7 (either defensible) |
| C6 | `RefreshView` shape | **Additive**: flat counts kept, `refresh_counts` + `refreshed_at` beside them | lane constraint "extend additively" |
| C7 | Clock format | `en-US`, local time zone, "10:42 AM" | checklist example |

OQ entries: `docs/plans/open-questions/oct14-deferred.md` (Lane C section).

## As built (2026-10-06, commit 00d974cb on `oct14/refresh-visibility`)

Divergences from the list above:

- `first_round_event_name` rides on `RankableSet` so `ranked_list_view` keeps its signature; no caller changed.
- `ExerciseResults.tsx` has its own refresh button, which the brief did not list. It now shows the same shut label and the same summary sentence (`data-slot="exercise-results-refresh-counts"`).
- The sr-only "Your team asked. Cards filled in…" announcer on the asking screen is removed: the summary notice is a `role="status"` region and would have read twice.
- The mark tests live in `tests/unit/exercise_results_router/test_exercise_results_refresh.py` (through the real refresh), not in `test_exercise_matching_router.py`.
- `tests/integration/test_exercise_full_class_run.py` needed two fixes: its reset-rerun equality now ignores `refreshed_at`, and its counts check compares the full shape.
- Vitest collects `*.test.tsx` only, so the wording tests are `refreshWording.test.tsx`.
- `exercise_matching_models.py` is now 770 of 800 lines. Lane B (#319/#271) also edits it.
