# Class exercise: Ann Wang's answers of 2026-10-10 (results rule, luck, Part 2, data file)

**Status:** Ruling recorded. Code merged to main: #396 (notice rule), #394 (lift line), #392, #393. No migration. **Step B question OPEN (2026-10-12): Ann's 2026-10-10 words say "the team's existing sign-up chances"; the team read that as the code's numbers, which Ann never saw. The only sign-up numbers she gave are her 2026-10-06 Step B (5 / +35 / +15 / +5 or +10 / +5). Recomputed on the Oct 2 file at 3/3/2/2, the app's suggested 30, 1,000 seeds: the code's numbers add 4.6 (Northline) and 3.9 (Harbor); Step B adds 6.4 and 5.1, which is Ann's "about 6 and 4-5". Draft PR #398 implements Step B; the owner confirms with Ann before it merges.**
**Decided by:** Ann Wang, email reply received 2026-10-10 to the team's Oct 9
email "Smart Match: choices before your Oct 16 run-through". Her words are
final; where earlier docs conflict, the earlier docs change.
**Issues:** #295 #327 #293 #273 #299 #336 #390 #391.
**Related source:** Ann's 2026-10-06 reply to Chau (Step B numbers), verbatim in [`stakeholder-correspondence-2026-09.md`](stakeholder-correspondence-2026-09.md) exchange D; owner pasted the full text again 2026-10-11.
**Verbatim source:** the Oct 9 questions are not in the repo; they can be
reconstructed from her reply below. Her reply is also `WangQuestion10_10_26.pdf`.
**Supersedes:** [`class-exercise-results-rule-2026-10-06.md`](class-exercise-results-rule-2026-10-06.md)
(the relayed sign-up points, notice 75/15 and 70% attend) and the "email
everyone as a separate option" idea in OQ-CE-24/26/29/30/31.

## Her answers, verbatim

**Q1. "Email everyone" same numbers per team:** "A" (keep: each team its own
chance draw). Debrief sentence: "Each team's numbers include its own luck. Look
at your gap over the mass email, not just the raw number."

**Q2. When the Oct 6 sign-up rule goes in:** "B", with a change to the rule
itself. Build the new sign-up rule before Oct 16. If Oct 16 is not possible,
tell her as soon as possible.

- Replace "email everyone": the mass email is not a separate option. It is what
  CPP already does; our approach adds personal emails on top.
- Everyone (all 300): receives the usual mass email or post. 20% notice it.
- The team's matched 30: also receive a personal email from CBACH. 60% notice
  it. Getting both, about 68% notice at least one.
- After that: the team's existing sign-up chances based on the match, then 65%
  show up.
- Sources: higher-ed email benchmarks; student survey (skip general emails,
  read personal ones); event data (free events lose about a third of sign-ups).
- The team screen shows the lift, not a contest: "Mass email alone: 11
  sign-ups. With your 30 CBACH emails: 17. Your list added 6."
- Check numbers: on the Oct 2 file, a suggested list of 30 should add about 6
  sign-ups at Northline and 4-5 at Harbor over mass email alone. Send her these
  numbers for a few teams once the rule is in, so she can confirm.
- This settles Q3 and Q5: the lesson is how much the list adds on top of CPP's
  mass email; the team's 30 receive both messages, so Q5 no longer applies.

**Q3:** see Q2. **Q5:** see Q2.

**Q4. Luck size:** "A". No extra luck. The team's fixed chance draw alone
decides who notices, signs up and shows up. Remove the extra plus or minus 10
points. Rates apply exactly: 20% mass email, 60% CBACH email, 65% show-up. Same
list, same result every time.

**Part 2** (the class-exercise checklist items):

- Weights 3, 3, 2, 2, whole steps 0-10, total a whole number: ok.
- P004 Brandon Soto: OK. Keep; reword the checklist to "he drops, but stays
  above a plain Accounting major".
- Past events 0 / 0.5 / 1: ok.
- Way of asking hidden before round one, one-sentence stand-in: ok.
- Instructor refresh of every team (button text, confirm text, report with skip
  reasons): ok.
- Team status line: ok. Pin it: it stays on screen while scrolling.
- Team's own refresh, two presses: OK. Keep two presses.
- Times: "match" - the instructor single-team page must say "Refreshed at 10:42
  AM" too, not "Asked at".
- Event description column optional: ok.
- License line: ok (final).

**Part 3, Q6. New data file:** "A". A new file gives a new chance draw. Keep the
fictional student data only. No upload for other instructors this semester.

## The rule now (interpretation note)

1. All 300: usual mass email or post; 20% notice.
2. The team's 30: also a personal CBACH email; 60% notice (about 68% notice at
   least one).
3. Then the team's **existing sign-up chances based on the match**.
   **OPEN, owner to confirm with Ann.** Reading 1 (what #396 shipped): the
   chances the app ran before (base 4, true-fit 40 split 20/20, past events 10,
   same major 4, out of 100); Ann never saw those numbers. Reading 2 (draft PR
   #398): her own 2026-10-06 Step B (base 5, +35 true interests, +15 true
   career goal, +5 for 1-2 past events or +10 for 3 or more, +5 same major).
   Only notice 75/15 and 70% attend are certainly superseded. Numbers below.
4. Then 65% show up.
5. No extra plus or minus 10 luck. The team's fixed draw alone decides; same
   list gives the same result.

The team screen shows counts only (ADR-0025 D8): "Mass email alone: N
sign-ups. With your 30 CBACH emails: M. Your list added K."

## What it supersedes

| Earlier text | Now |
|---|---|
| 2026-10-06 notice 75% (list) / 15% (mass) | 60% CBACH email / 20% mass email |
| 2026-10-06 sign-up points 5 / +35 / +15 / +5-10 / +5 | OPEN: replaced by "existing sign-up chances" only if the owner confirms reading 1; reading 2 keeps them (PR #398) |
| 2026-10-06 70% attend | 65% show up |
| luck band of up to 10 in 100 (D7, R1-L2) | none |
| "Email everyone" as a separate option and contest | baseline; screen shows the lift |

## Check numbers (real code path, mean of 1,000 seeds)

Oct 2 file, suggested top 30 at 3/3/2/2, excluding the 8 existing sign-ups.
N = mass email alone, K = sign-ups the list adds, M = N + K.

| Sign-up reading | Northline N / K / M | Harbor N / K / M | Matches Ann's about 6 / 4-5? |
|---|---|---|---|
| 1. Code's old chances (4 / 40 / 10 / 4), shipped in #396 | 8.5 / 4.6 / 13.1 | 9.7 / 3.9 / 13.6 | Northline low |
| 2. Ann's Step B, any past events (PR #398) | 10.5 / 6.4 / 16.9 | 12.1 / 5.1 / 17.1 | yes |
| 2b. Step B, related past events only | 9.5 / 6.1 / 15.5 | 11.0 / 4.8 / 15.8 | yes |

Reading 2 also reproduces her mock-up line ("Mass email alone: 11. With your 30 CBACH emails: 17. Your list added 6") at Northline: 10.5 to 16.9. Per-team lift ranges 0-12. Danny sends Ann the numbers for a few teams.

## Next step

After #396 merges, send Ann the per-team check numbers (lift N/M/K for a few teams, Northline and Harbor) so she can confirm them (Ann Wang, email 2026-10-10, Q2).

## Answered by this email

See the OQ table in the PR that added this file; rows are marked in the
[register](../plans/open-questions/class-exercise-open-questions.md) and
[`oct14-deferred.md`](../plans/open-questions/oct14-deferred.md). Still open:
the Step B question (OQ-CE-19, 22, 29 reopened), OQ-CE-20, 23, 27, 28; OQ-OCT14-03.
