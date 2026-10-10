> DRAFT — needs Danny decision (Ann decides the branch). Nothing here is decided.

# #293 — P004 "interest off" half does not hold as built

## Facts
- Ann's checklist §4 (2026-10-02): "with 'said they are interested' turned up, he ranks above a plain Accounting major. With it set to zero, he does not." (quoted in `docs/plans/2026-10-05-oct-2-review-conflict-analysis.md:112`, row C3 at `:42`.)
- As built (D9, keep as built, Chau approved 2026-09-25): `docs/decisions/class-exercise-decisions-2026-09-25.md:35` and `:350-377`. Turned off, P004 still ranks above plain Accounting majors. Reasons: his career goal "Data, analytics or IT role" maps to "Technology / information systems" (`python/smartmatch_domain/smartmatch_domain/exercise/vocabulary.py:131`), which fits Northline; with that off too, more-information-first is Ann's own tie-break (`matching.py:291` `_exercise_ranked`; D9 "Why").
- Full 300 file: P004 is 6th with interest off; P257 161st, P231 295th (Chau's comment in #293; D9 text says 4th to 6th). D9 amendment `:362-365`: those ranks were NOT re-run under the new 3/3/2/2 defaults. Chau says #289 does not change this.
- Golden tests: `tests/golden/exercise/test_exercise_ann_dataset_golden.py:177` `test_turned_off_p004_still_ranks_above_on_its_career_goal` (asserts the opposite of Ann's line); also `:160` (turned up), `:169` (factor stops counting), `:187` (information tie-break). Per D9 text these sit at `:161/:170/:178/:188`, so the pinned lines moved by ~1.
- Chau flagged this as a test-pass criterion for Oct 16.

## Branch A — Ann accepts D9, edits her checklist line
- Changes: Ann's checklist §4 sentence only (her document, off-repo). No code, no tests.
- Optional repo follow-up: note in `stakeholder-correspondence-2026-09.md` row 5 that Ann accepted. <TBD — Danny>
- Cost: none. Teaching point preserved (information matters).

## Branch B — change the goal table or tie-break so P004 falls below plain Accounting when interest is off
Would touch (D9 option B, rejected by the team earlier; shown here for completeness):
1. `python/smartmatch_domain/smartmatch_domain/exercise/vocabulary.py:131` (role-to-topic table, remove or change the Data/IT mapping) OR `matching.py:291-320` (tie-break order).
2. `tests/golden/exercise/test_exercise_ann_dataset_golden.py:177` (flip assertion), `:187` (if tie-break changes).
3. `tests/unit/test_exercise_matching.py` and `tests/unit/test_exercise_ingest.py` (reference P004 / the table; exact tests not traced).
4. `docs/decisions/class-exercise-decisions-2026-09-25.md` D9 (new amendment, not an edit of history) and `docs/plans/open-questions/class-exercise-open-questions.md` OQ-CE-15.
5. Side effect: changing the goal table affects every Data/IT-goal student for every event, not only P004. Not quantified here.

## DRAFT check-in note to Ann (plain words; Danny edits and sends himself)
> Hi Ann, one item from your checklist. You wrote that with "said they are interested" turned up, P004 ranks above a plain Accounting major, and with it set to zero he does not. The first part works. The second does not, as built: with interest at zero, P004 still ranks above them, because his career goal (Data, analytics or IT role) fits the Northline event, and where scores tie we list the student with more information on file first. On the 300-row file he is 6th with interest off, and the plain Accounting majors are far below. [Danny: these ranks predate the 3/3/2/2 default weights — re-run before sending.] Two choices: (A) keep it as is and change that checklist line, or (B) we change how career goals or ties are scored so he drops below. [Danny: add a recommendation or leave the choice open.] Which would you like, before your run-through?

(The "we recommend A" sentence is the team's D9 position, not a new decision; Danny may delete it.)

## Open questions
1. Which branch? — Ann decides; Danny conveys.
2. Re-run the P004 ranks under 3/3/2/2 defaults before sending, so the numbers in the note are current? — Danny (or an agent).
3. Send by email (plan-affecting, per correspondence C item 5) or raise at Friday 11 AM? — Danny.
