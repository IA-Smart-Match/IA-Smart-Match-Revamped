> DRAFT — needs Danny/Justin decision. Nothing here is decided.

# Row-by-row acceptance test list (draft)

Refs #299 part (b), due Oct 16 per the issue. Source checklist: `docs/10-2-2026/extracted/SmartMatch_User_Test_Checklist_10022026.txt` (Ann, 2026-10-02; sections 1-9, problems table in section 10).

## Harness status (plain)

No exercise end-to-end harness exists. Evidence:
1. `tests/e2e/` holds only `conftest.py` and `test_pilot_clickthrough.py`, a CBA-pilot appliance walk (`tests/e2e/test_pilot_clickthrough.py:1-12`), not the class exercise.
2. No Playwright config found outside node_modules (`find . -name "playwright.config*"` returned nothing).
3. Exercise coverage today is pytest unit/integration under `tests/unit/test_exercise_*.py`, `tests/unit/exercise_results_router/`, `tests/integration/test_exercise_*.py`, plus Vitest component tests under `apps/web/legacy-frontend/src/app/pages/exercise/*.test.tsx`. These test API and components in isolation, not a browser session against a live stack.

"Covered" below means a test of the same behaviour exists. I read test names, not bodies, so each "covered" is a lead for Justin to confirm.

## Rows

| Sec | Checklist row (short) | Do | Expect | Existing automated test or "manual" |
|---|---|---|---|---|
| 1 | Every press shows a message | Press each button | In-words message beside it, persists | `ExerciseMatching.feedback.test.tsx`, `InstructorFeedback.test.tsx` (component only); live pass manual |
| 1 | Used-up button greys out | Run results twice | Grey, "Results already run for this event." | `tests/unit/exercise_results_router/test_exercise_results_rules.py::test_a_second_run_is_refused_with_the_specs_own_sentence` (API); grey button manual |
| 1 | Status line on team page | Open team page | Team, event, round, results, asking, refresh | `TeamStatusBand.test.tsx`, `TeamStatusBand.pages.test.tsx` |
| 1 | Confirm before wiping | Clear a team | "Are you sure?" with detail | `InstructorUnlock.confirm.test.tsx`; clear flow manual |
| 2 | Passcode | Wrong, then right | "Wrong passcode" only | `tests/unit/test_exercise_instructor_router.py::test_a_wrong_passcode_is_one_sentence_and_no_cookie`, `ExerciseInstructor.passcode.test.tsx` |
| 2 | Upload 300-row workbook | Upload Ann's file | "300 profiles, 12 events loaded" | `test_exercise_instructor_router.py::test_anns_october_workbook_is_accepted_and_stored` |
| 2 | Upload with column removed | Upload broken file | Names missing column; old file stays | `test_exercise_instructor_router.py::test_a_workbook_with_a_column_removed_is_refused_in_plain_words_and_nothing_is_stored` |
| 2 | Which file in use | Read instructor page | File named | `test_exercise_instructor_router.py::test_the_dataset_list_is_behind_the_session_and_names_the_file` |
| 2 | Limit 30 to 25 | Change limit | "Limit set to 25", list cut | `test_exercise_instructor_router.py::test_the_invite_limit_can_be_changed`; `tests/unit/test_exercise_matching_router.py::test_the_list_is_cut_at_the_data_files_invite_limit` |
| 2 | Results open/close | Open Northline, close | Label + time | `test_exercise_instructor_router.py::test_results_can_be_closed_again_and_the_time_is_reported` |
| 2 | Open team's work | Open a team | Settings, list, results, asking, refresh | `InstructorTeamDetail.test.tsx` |
| 2 | Clear team X | Clear | "Team X cleared"; others untouched | `tests/unit/test_exercise_registry_isolation.py` (lead); `tests/integration/test_exercise_instructor_persistence.py` (lead) |
| 3 | No sign-in, opening text | Visit address | Intro, licence line | `ExerciseEntry.test.tsx` |
| 3 | Pick team 1-6, "You are Team 3" | Enter number | Banner every page | `tests/unit/test_exercise_workspace_router.py::test_entering_a_team_number_opens_a_workspace_and_sets_a_cookie`, `::test_a_team_number_outside_one_to_six_is_refused_with_a_sentence` |
| 3 | Events screen round labels | Open events | Round one/two shown, Harbor gated | `ExerciseEventPicker.layout.test.tsx`; `test_exercise_matching_router.py::test_an_event_says_whether_results_are_open_and_whether_this_team_has_run` |
| 3a | Event descriptions | Open each event | Text above sliders, also on instructor page | `EventDescription.surfaces.test.tsx`; `test_exercise_matching_router.py::test_the_ranked_list_carries_its_events_description`; readability on projector manual |
| 4 | Sliders, "List updated" | Move slider | Message, list changes | `WeightsControls.test.tsx`, `ExerciseMatching.feedback.test.tsx` |
| 4 | One reason line | Read names | One line each | `tests/unit/test_exercise_reasons.py::test_every_branch_is_one_sentence_with_no_number` |
| 4 | "same major; nothing else on file" | Major-only profile | Exact phrase | `test_exercise_reasons.py::test_a_major_only_profile_gets_anns_sentence` |
| 4 | "tied on major; ordered by year" | Tied names | Exact phrase | `test_exercise_reasons.py::test_a_year_tie_genuinely_on_major_gets_anns_sentence` |
| 4 | Stops at 30 | Build list | 30 and says so | `test_exercise_matching_router.py::test_the_list_is_cut_at_the_data_files_invite_limit`; `exerciseListCoverageNotice.test.ts` (lead) |
| 4 | P004 case | Weight up/zero "said interested" | Ranks above / not | `tests/unit/test_exercise_matching.py` (lead, case not confirmed); OQ-CE-15 per memory |
| 4 | Interest credit not cut to a third | List with 3 interests | Clear credit | `test_exercise_matching.py` / `test_exercise_event_interest_fit_csv.py` (lead) |
| 4 | No credit for undecided on Northline | Undecided profile | No career credit | `tests/unit/test_exercise_simulation.py::test_a_missing_career_goal_is_not_a_penalty` (simulation side only); matching side lead in `test_exercise_matching.py` |
| 4 | Who-is-on-list table, class-order years | Read table | Freshman..Senior; empty groups named | `ListCompositionTable.desk.test.tsx` (lead) |
| 4 | Save/4th refused/delete | Save 4 settings | "Saved", 3 limit, confirm delete | `tests/integration/test_exercise_full_class_run.py::test_a_fourth_saved_setting_is_refused`; `SavedSettingsPanel.desk.test.tsx` |
| 4 | Compare two settings | Pick two | Highlights + counts | `MatchingCompareView.test.tsx` |
| 4 | Download | Download | Columns present, pink columns absent | `tests/unit/test_exercise_matching_csv.py` (lead) |
| 5 | Results grey until open | Before unlock | "Results not open yet." | `test_exercise_full_class_run.py::test_every_team_is_refused_before_the_instructor_unlocks` |
| 5 | Confirm, then one run | Run, rerun, reload, second tab | No second run, reason shown | `test_exercise_full_class_run.py::test_a_second_run_of_round_one_is_refused`; `test_exercise_workspace_router.py::test_a_second_tab_on_the_same_team_shares_the_workspace_and_the_token`; browser tab race manual |
| 5 | Results unaffected by slider change | Move slider after run | Results unchanged | `test_exercise_full_class_run.py::test_the_stored_run_reads_back_as_it_was_answered` (lead) |
| 5 | Four numbers + email everyone | Read results | Both sets of four | `ResultPanels.test.tsx`, `tests/unit/exercise_results_router/test_exercise_results_panels.py` |
| 5 | Repeatable, differs by team | Same list, two teams | Same per team, may differ | `tests/unit/test_exercise_simulation.py::test_same_inputs_twice_give_the_same_result`, `::test_a_different_seed_generally_gives_a_different_result` |
| 5 | Uses hidden truth | Compare lists | True-tech list wins | `test_exercise_simulation.py::test_true_fit_profiles_sign_up_far_more_often_than_same_major_only_ones` |
| 5 | Projector legibility | View on projector | Readable back row | manual / no harness (`ExerciseResultsChart.layout.test.tsx` checks layout only) |
| 6 | Asking choice after results, 3 options | Open asking | Three sentences | `ExerciseAskingForMore.test.tsx`; `tests/unit/test_exercise_asking.py::test_the_three_choices_are_exactly_the_ones_the_spec_names` |
| 6 | Refresh gated until choice | Press early | Grey with reason | `ExerciseAskingForMore.refresh.test.tsx` |
| 6 | Refresh summary, before/after counts | Refresh | Plain summary | `tests/unit/test_exercise_refresh_report.py`, `refreshWording.test.tsx`, `test_exercise_full_class_run.py::test_the_refresh_reports_every_profile_before_and_after` |
| 6 | Marks on changed profiles | View list | "new card" marks | `RankedList.refreshMarks.test.tsx` |
| 6 | 30/55/80 and 15% | Refresh per choice | Shares as set | `test_exercise_asking.py::test_the_completion_shares_are_anns_build_table_numbers`, `::test_the_required_non_responding_share_is_anns_number`, `tests/unit/test_exercise_asking_counts.py` |
| 6 | Second refresh no-op | Press twice | "Already refreshed at ..." | not found by name; `tests/unit/exercise_results_router/test_exercise_results_refresh.py` (lead) |
| 6 | Instructor refresh all | Press | Refreshed/skipped listed | `test_exercise_instructor_router.py` (lead, not located by name) |
| 7 | Harbor uses refreshed cards | Build Harbor list | New-card credit | `test_exercise_full_class_run.py::test_round_two_carries_the_teams_own_round_one` (partial) |
| 7 | Stopped-responding handling | View list | Left off or marked | `test_exercise_simulation.py::test_non_responding_profiles_never_sign_up` (results side) |
| 7 | Three results side by side | Read Harbor results | Harbor, everyone, own Northline | `ResultPanels.test.tsx` (lead) |
| 7 | Round-two lift visible | Run all 6 teams | Reward/required beat promise | no test; this is the #336 question, PR #363 |
| 8 | Two teams at once, isolation | Two browsers | No cross-visibility | `test_exercise_workspace_router.py::test_two_teams_at_once_do_not_see_each_other`; `test_exercise_registry_isolation.py` |
| 8 | Reload / return keeps work | Reload, close, return | Saved work present | `test_exercise_workspace_router.py::test_a_reload_with_the_same_cookie_returns_the_same_workspace` |
| 8 | Same list after clear gives same result | Clear, rerun | Identical | seed kept on clear per PR #344 (`class-exercise-results-rule-2026-10-06.md` update note); test not located |
| 8 | New file warns | Repoint all teams | Warning + file shown | `test_exercise_instructor_router.py::test_a_repoint_reports_what_it_did` |
| 9 | Load under 5 s, tab title, licence line | Time on room PC | Under 5 s, "Smart Match" tab | manual / no harness |
| 9 | Five quick questions mock-up | Open | One screen | `ProfileCardMockup.test.tsx` (lead) |

## Scope options (not picked)

1. **Manual list only.** Ship this table as the Oct 16 script; Justin and two testers tick it. Cost: none. Leaves browser-level rows (grey buttons, two-tab race, projector, load time) unproven.
2. **Playwright smoke for N rows.** Needs a new Playwright config, a live-stack bring-up (local ports per memory :8190/:5273), and one passcode/workbook fixture. A first N of about 8 rows: sec 2 upload+unlock, sec 3 team entry, sec 4 slider+list, sec 5 run-once, sec 6 refresh, sec 8 two-team isolation. Cost: new infra; owner of CI time needed.
3. **Defer.** Run option 1 on Oct 16; decide on a harness after the practice run.

## Open questions

1. Which scope option? Danny, with Justin.
2. Does Justin want rows tagged by who runs them (Ann's single pass vs two-team pass)? Justin.
3. Rows marked "lead" need a body read to confirm they assert the checklist behaviour. Who verifies: Justin or a follow-up agent? Danny.
4. Does "due Oct 16" mean the list or the harness? Issue says list; harness only if option 2. Danny.
5. Rows whose rule R1 would change (section 5 and 7 numbers) will need rewording if R1 is built (`docs/decisions/class-exercise-results-rule-2026-10-06.md`). Ann/Danny.
