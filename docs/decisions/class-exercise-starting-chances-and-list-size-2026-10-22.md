# Class exercise: Ann Wang's answers of 2026-10-22 (starting chances, list size 60, ties, round two)

**Status:** Ruling recorded. List-size code on branch `chau-1027` (not yet merged; the class site is locked through Oct 30 except fixes Ann approves on #413). Her words are final; where earlier docs conflict, the earlier docs change.
**Decided by:** Dr. Fan (Ann) Wang, comment on issue #413, 2026-10-22 6:36 PM Pacific (GitHub shows 2026-10-23 01:36 UTC): <https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/issues/413#issuecomment-6355280437>. She was answering the team's open questions (a)–(c).
**Restated by:** Ann Wang herself, team message to @Danny Tran, 2026-10-26 8:13 PM (screenshot), verbatim: "Danny TranI confirmed 5 / +15 / +5 on issue #413 on Oct 22. Please add that as the source for R11. R67 -  remove it, The list should be fixed at 60" ("Danny Tran" is the mention; the missing space is in the original). This is also her OK for the list-size change.
**Supersedes:** the current-rule "List size" row ("Top 30; the instructor can lower the limit (e.g. 25)"), the instructor list-limit control (checklist row 15, requirements-check R67), and the list of 30 in [`class-exercise-results-rule-2026-10-10.md`](class-exercise-results-rule-2026-10-10.md).
**Open questions:** OQ-CE-23 closed; see the [register](../plans/open-questions/class-exercise-open-questions.md). Items for review are at the end.

## Her words, verbatim (issue #413, 2026-10-22)

> My answers to the team's open questions:
>
> (a) Starting chances: confirmed. 5 in 100 to start, +15 when the career goal fits, +5 for the target major.
> (b) List size: 60, fixed for this class. No instructor setting needed.
> (c) Ties: fine as is. Students we know more about first, then seniors, then a fixed order, explained on screen.
>
> Round-two design: approved. With 60 emails, asking for more now lifts the balanced setting from about 9 to 10–12 added sign-ups, while major first stays flat. That is the lesson I want students to see.

The same comment also covers the class site, video, running costs and materials list. Those are not rulings on the rule and are not recorded here.

## Rulings

| Q | Ruling | Status | Where it lives |
|---|---|---|---|
| (a) | Start at 5 in 100; +15 when the hidden true career goal fits; +5 when the event targets the student's major | **Confirms** Step B's start, goal and major points (owner ruling 2026-10-12, PR #398; Ann had not quoted them since 2026-10-06). Closes OQ-CE-23 with her words "the target major" | `simulation.py:480` (start 0.05), `:481` + `:488` (true-fit 0.50 × goal share 0.3 = 0.15), `:483` (major 0.05) |
| (b) | The list holds 60 names, fixed for this class; no instructor setting | **Supersedes** "Top 30; the instructor can lower the limit" and the "Limit set to 25." control | migration `0049_exercise_invite_limit_fixed.py:29-31` (every file to 60; check `invite_limit = 60`); `schema.py:149`; instructor route, repository method and form removed; `ExerciseMatching.tsx:484` |
| (c) | Ties: more information on file first, then seniors, then the file's fixed order, explained on screen | **Confirms** the ties row (OQ-CE-01, D-rulings 2026-09-24/25) | `vocabulary.py:86-93`; reason lines in `reasons.py` |
| Round two | The round-two design (asking for more at the start of round two; before/after rows) is approved | **Confirms** the design built in #420 and #423 | no code change |

No ruling is classified Withdraws.

## Check numbers (run on the code, not by hand)

Oct 2 file, the app's suggested list at 3/3/2/2, mean of 5,000 seeds (1–5000), through the production path (`exercise_ranked_list`, `run_email_everyone`, `simulate_results`), on `origin/main` @ `4fc80d02`. Harbor is before asking.

| Event | List | Mass email alone (N) | List adds (K) | With list (M) | Ann's target (Oct 16) |
|---|---|---|---|---|---|
| Northline | 60 | 10.48 | 9.42 | 19.90 | about 9 (9.4 balanced) |
| Harbor | 60 | 12.10 | 9.14 | 21.24 | about 9 before asking (9.2) |

Harbor after asking (10–12 for balanced) is not rerun here; the 50,000-run package Ann reviewed in #435 has it and she wrote "the numbers match my estimates".

The 30-list pins in `tests/golden/exercise/test_exercise_ann_check_numbers_golden.py` (K 6.4 / 5.1) are left as they are: they check the rule at Ann's earlier list of 30, the rule did not change, and that file says not to re-pin without her written OK.

## Code changed (list size only)

Behavior changed for (b) only. (a) and (c) are already what the code does.

- `db/migrations/versions/0049_exercise_invite_limit_fixed.py` (new): sets every data file to 60, narrows `ck_exercise_dataset_invite_limit` to `invite_limit = 60`. Checked on a scratch database: a file at 25 became 60; a new file at 30 is refused; downgrade restores `>= 1`.
- Removed: `PATCH /v1/exercise/instructor/datasets/{dataset_id}`, `InviteLimitRequest`, `ExerciseInstructorRepository.set_invite_limit`, `MIN_INVITE_LIMIT` / `MAX_INVITE_LIMIT`, `setInviteLimit` and the instructor form.
- Wording: "Your instructor set this size." → "Every team's list holds this many."

## For the reviewer

1. OQ-CE-23 is closed on her words "+5 for the target major". If "target major" should not be read as the event's target majors (option (a)), reopen it.
2. OQ-CE-28, first half (round two improves only through a better list): her round-two approval says major first "stays flat", which is option (a)'s behavior, but she did not answer the question as asked. Left OPEN.
3. Deploying (b) changes the class database. Ann's message of 2026-10-26 asks for the fixed 60; back up the class database before the migration runs.
