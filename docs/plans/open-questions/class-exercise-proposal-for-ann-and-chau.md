# What the class exercise is waiting on — for Ann and Chau

**Prepared 2026-09-21 by Danny; updated 2026-09-24, and again 2026-09-25**
after Ann's email reply and Chau's approvals. This page now holds only what is
still open for Ann and Chau. Every question it used to ask has a dated answer
in [`class-exercise-open-questions.md`](class-exercise-open-questions.md). The
reasons behind each answer are in
[`class-exercise-decisions-2026-09-25.md`](../../decisions/class-exercise-decisions-2026-09-25.md).
Nothing in this document closes a question.

## Nothing is waiting on you

The site is built and the results screen works. Every question on the earlier
versions of this page is answered:

| Question | Answered by | Register row |
|---|---|---|
| Results-rule numbers | Team translation of Ann's words; Chau approved, 2026-09-25 | OQ-CE-03 |
| Starting weights | Ann, 2026-09-25: equal | OQ-CE-02 |
| Points | Ann, 2026-09-25: as built | OQ-CE-10 |
| Career-goal table, and "Undecided" | Ann, 2026-09-25: half credit on broad events | OQ-CE-14 |
| P004 test case | Chau approved keeping it as built, 2026-09-25 | OQ-CE-15 |
| Reason lines | Ann, 2026-09-25: all as written | OQ-CE-12 |
| Asking-for-more percentages, and halves | Ann, 2026-09-25; halves round up (Danny) | OQ-CE-04 |
| Two tabs on one team number | Ann's answers, 2026-09-22: shared | OQ-CE-08 |
| Card questions | Ann, 2026-09-25: interests and career goal only | OQ-CE-11 |
| License line | Ann, 2026-09-25 | OQ-CE-09 |
| Empty seats on the results screen | Chau approved showing both groups, 2026-09-25 | OQ-CE-16 |

## For Ann, for information

1. **The sample result.**
   [`oq-ce-03-sample-result.md`](oq-ce-03-sample-result.md) shows what the
   approved numbers do on your file for Northline and Harbor.
2. **Two things Chau approved that you may revisit.**
   - **The numbers** behind "a lot", "some", "a little" and "some
     randomness". If a result looks wrong to you, say "more sign-ups",
     "fewer sign-ups" or "less luck". Each change is one line.
   - **P004.** With "said they are interested" turned off, P004 drops from 4th
     to 6th for Northline but stays above a plain Accounting major. Its career
     goal still fits Northline, and with that off too, more information on
     file comes first. That is your own tie-break, and it matches the lesson
     that information matters. If you would rather it fell below, tell us
     which rule to change.
3. **Empty seats** will read, for example: "8 were already coming. Your
   invitations added 6. 46 seats are still open."

## Still open, for the team

These are not asked of Ann or Chau.

- **Rate limiting at the proxy** (OQ-CE-06). The address is decided; the proxy
  rule is not applied yet.
- **Instructor session revocation** (design spec §14, PR #184 "owner decision
  1"). Danny's to decide.

## The dates that bind

- **Fri Oct 2:** the site running on the full data.
- **Fri Oct 16:** results, comparison, repeatable runs, asking-for-more,
  refresh, round two and download working.
- **Week of Nov 9:** practice run with Ann, Dr. Lin and volunteers. The hidden
  rule and the three percentages are reviewed there.
- **Fri Nov 20:** fixes done.

## Appendix — where a change would land

| If Ann revisits | Row | Where it lands |
|---|---|---|
| Results-rule numbers | OQ-CE-03 | `smartmatch_domain/exercise/simulation.py` — `EXERCISE_SIMULATION_COEFFICIENTS` |
| P004 | OQ-CE-15 | `smartmatch_domain/exercise/vocabulary.py` (`CAREER_GOAL_TOPICS`) or `smartmatch_domain/exercise/matching.py` (`_exercise_ranked`); pinned by `tests/golden/exercise/test_exercise_ann_dataset_golden.py` |
| Empty-seats wording | OQ-CE-16 | `ResultPanels.tsx` (on `feat/ce-results-integration`) |
