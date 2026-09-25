# What the class exercise is waiting on — for Ann and Chau

**Prepared 2026-09-21 by Danny; updated 2026-09-24** after Ann's data file
arrived. Her file answered the column names and values, the file format, the
year order and what a copied card carries, so those questions are gone from
this page. Nothing in this document closes a question.
Every question here stays OPEN in
[`class-exercise-open-questions.md`](class-exercise-open-questions.md) until a
dated answer is written into that register. No numbers are proposed below.

## Where the build stands

The site is built: a team enters its number and keeps its own work, the data
file loads, profiles are matched on the four factors with a reason next to each
name, settings save and compare side by side, the list table and download work,
results have a lock and an "email everyone" comparison, the three ways of
asking for more are there, and the refresh runs per team and for all teams at
once. The instructor uploads Ann's `.xlsx` exactly as she sent it, and the tie
by class year now places seniors first. Two things visibly do not work until
you answer. **One** — *Run results* refuses with one sentence, because the
results rule has no confirmed numbers. **Two** — three of the reason lines
participants read are placeholder sentences we wrote, not Ann's. The dates that
bind: **Fri Oct 2** is the site running on the full data; **Fri Oct 16** needs results, comparison, repeatable runs, asking-for-more,
refresh, round two and download working, and the results half of that is gated
entirely on the numbers below; the **practice run in the week of Nov 9** is
where the rule and the three percentages are reviewed; **Fri Nov 20** is fixes
done.

## From Chau, with Ann confirming

The register already records the procedure for the results rule: *Chau
proposes; Ann confirms* — confirmation before the November practice run. The
rule needs **eight** quantities, not the four first written down. Each is one
number.

| # | In plain words | Range |
|---|---|---|
| 1 | How likely is someone with nothing in their favour to sign up at all? | 0 to 1 |
| 2 | How much more likely when the event really matches what they care about and where they want to work? | 0 to 1, and must be larger than 3 and 4 |
| 3 | How much more likely for someone who has been to many past events? | 0 to 1, smaller than 2 |
| 4 | How much more likely for being in the right major and nothing else? | 0 to 1, smaller than 2 |
| 5 | Of the lift in row 2, how much comes from interests rather than from career goal? | a share, 0 to 1 |
| 6 | How many past events count as "many"? | a whole number, 1 or more |
| 7 | How big is the element of luck? | 0 to 1; 0 means no luck at all |
| 8 | Of the people who sign up, how many actually turn up? | 0 to 1 |

The app refuses any set where row 2 is not larger than rows 3 and 4, so the
ordering Ann wrote cannot be broken by whichever numbers arrive.

Two more sets belong in the same conversation. **Starting weights for the four
matching factors** — four numbers that decide where a team begins before it
adjusts anything. **Points** — how many points an attended event earns, and how
many a completed card earns; two whole numbers. Both currently sit at
placeholder values that nobody chose.

## From Ann

### Needed first

1. **The career-goal table.** "Career goal fits this event" compares a goal
   with an event's topics, so each goal needs a topic. We read one off your
   file: every "<field> role" goes with its field (for example, *Data,
   analytics or IT role* goes with *Technology / information systems*), *Start
   my own business* goes with *Entrepreneurship / startups*, and *Undecided*
   and *Graduate school* go with no topic, so they never fit an event. Is that
   right?
2. **The P004 test case.** Turned up, "said they are interested" puts P004
   above a plain Accounting major, as you wrote. Turned off, it stops counting
   for P004, but P004 still ranks above them, for two reasons. First, its goal
   (*Data, analytics or IT role*) fits Northline under the table in question 1.
   Second, when that is turned off too, the tie goes to the profile with more on
   file, and P004 has a completed card. Should one of these change, or is this
   what you expected?
3. **Reason lines.** Your two lines are shown capitalised and full-stopped —
   *"Same major; nothing else on file."* and *"Tied on major; ordered by
   year."* — and a single-factor line reads *"What counted: same major."* Are
   those acceptable? Three more tie sentences are ours, not yours, and need
   your words: *"Tied on what counted; ordered by year."*, *"Tied; more
   information on file first."*, *"Tied; placed in a fixed order that never
   changes."* And when both of your lines fit one name, which does a
   participant see?
4. **Asking for more.** Confirm 30 / 55 / 80 percent, and the 15 percent who
   stop opening messages after the required option. When the share lands on an
   exact half — 55 percent of a full list of 30 invited people is 16.5 — round
   up or down?

### Can wait

- **Two browser tabs on the same team number** — same saved runs in both, or a
  separate workspace per tab? We built "same saved runs".
- **The five quick questions** on the profile card. Your file has the card's
  interests and career goal; the other three questions are still yours to give.
- **The license line** for the opening screen, any time before Nov 20.

## Reply form

Answers are cheap to apply: each one lands in a single named place, listed in
the appendix. Tick or fill in and send back; anything left blank stays open.

- [ ] Eight rule quantities: 1 ___ 2 ___ 3 ___ 4 ___ 5 ___ 6 ___ 7 ___ 8 ___
- [ ] Starting weights: same major ___ interested ___ career goal ___ past events ___
- [ ] Points: per attended event ___ per completed card ___
- [ ] Career-goal table as read off the file ☐ yes ☐ change ___
- [ ] P004 with "interested" turned off: ☐ fine as it is ☐ change ___
- [ ] Reason lines: renderings ☐ fine ☐ change to ___ · three sentences: ___ · when both fit, show ☐ the tie line ☐ the major-only line
- [ ] Percentages: ☐ 30/55/80 and 15 as written ☐ instead ___ · exact half ☐ up ☐ down
- [ ] Two tabs on one team number ☐ share saved runs ☐ separate
- [ ] Five questions: ___ · License line: ___

## Appendix — for the builders

| Question | Row | Where it lands |
|---|---|---|
| Eight rule quantities | OQ-CE-03 | `smartmatch_domain/exercise/simulation.py` — `EXERCISE_SIMULATION_COEFFICIENTS` (`None` today) |
| Starting weights | OQ-CE-02 | `smartmatch_domain/exercise/registry.py` — the four `*_DEFAULT_WEIGHT` constants |
| Points | OQ-CE-10 | `smartmatch_domain/exercise_points.py` — `POINTS_PER_ATTENDANCE`, `POINTS_PER_COMPLETED_CARD` |
| Career-goal table | OQ-CE-14 | `smartmatch_domain/exercise/vocabulary.py` — `CAREER_GOAL_TOPICS` |
| P004 test case | OQ-CE-15 | `tests/golden/exercise/test_exercise_ann_dataset_golden.py`; `smartmatch_domain/exercise/matching.py` |
| Reason wording and precedence | OQ-CE-12 | `smartmatch_domain/exercise/reasons.py` — three `_TIED_*` phrases, `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE` |
| Percentages and half-rounding | OQ-CE-04 | `smartmatch_domain/exercise/asking.py` — `CARD_COMPLETION_SHARE`, `REQUIRED_NON_RESPONDING_SHARE`, `select_share` |
| Two tabs | OQ-CE-08 | `smartmatch_domain/exercise/workspace_token.py` |
| Five questions | OQ-CE-11 | profile-card mock-up |
| License line | OQ-CE-09 | opening screen; `license_line` is nullable |
