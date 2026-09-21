# What the class exercise is waiting on — for Ann and Chau

**Prepared 2026-09-21 by Danny.** Nothing in this document closes a question.
Every question here stays OPEN in
[`class-exercise-open-questions.md`](class-exercise-open-questions.md) until a
dated answer is written into that register. No numbers are proposed below.

## Where the build stands

The site is built: a team enters its number and keeps its own work, the data
file loads, profiles are matched on the four factors with a reason next to each
name, settings save and compare side by side, the list table and download work,
results have a lock and an "email everyone" comparison, the three ways of
asking for more are there, and the refresh runs per team and for all teams at
once. Three things visibly do not work until you answer. **One** — *Run
results* refuses with one sentence, because the results rule has no confirmed
numbers. **Two** — the tie-break by class year is off: we do not know what the
year values are or which is most senior, so no name is ever placed by year.
**Three** — three of the reason lines participants read are placeholder
sentences we wrote, not Ann's. The dates that bind: the full 300-row file is
due **Fri Sept 25** (the 20-row sample was due Sept 18 and has not arrived);
**Fri Oct 16** needs results, comparison, repeatable runs, asking-for-more,
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

1. **The sample file.** Final column names, and what values each column may
   hold — major, year, past events, stated interests, career goal, and the
   hidden true interests. For year especially: what are the values, and what is
   their order from most senior to least? Nothing is placed by year until this
   arrives.
2. **The file itself.** A spreadsheet (.xlsx) or a plain CSV export? One file
   with a column marking each row as a person or an event, or two files? What
   separates several interests or events inside one cell? Is a past event named
   on a person by its short key or its title? And can someone have a card with
   nothing written on it, or does an empty interests cell always mean no card?
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
   exact half — 30 percent of 25 invited people is 7.5 — round up or down?
5. **Copied cards.** When the refresh gives someone a card, does that card
   carry the career goal already on their record, or nothing? We default to
   carrying it.

### Can wait

- **Two browser tabs on the same team number** — same saved runs in both, or a
  separate workspace per tab? We built "same saved runs".
- **The five quick questions** on the profile card. The requirements name only
  stated interests and career goal.
- **The license line** for the opening screen, any time before Nov 20.
- **People with no major or no year on their row** take no place on any list.
  We report how many. Is a count enough, or should the screen say something?
- **A career goal with no card behind it** is ignored today, because the
  refresh copies a card and a goal alone is not one. Worth confirming.

## What each answer changes

| Answer | What moves |
|---|---|
| The eight rule quantities | One set of numbers; *Run results* stops refusing |
| Starting weights, points | Four numbers, then two |
| Column names, values, year order | One description of the file; the year tie-break switches on |
| Spreadsheet or CSV | Either the same reader, or one added library |
| Reason-line words and precedence | The sentences themselves, and one true/false switch |
| Percentages and half-rounding | Four numbers, and one rounding rule |
| Copied-card career goal | One switch in the refresh |
| Two tabs | Either nothing, or how a team is recognised |
| Five questions, license line | The card mock-up; one line on the opening screen |

## Reply form

Tick or fill in and send back; anything left blank stays open.

- [ ] Eight rule quantities: 1 ___ 2 ___ 3 ___ 4 ___ 5 ___ 6 ___ 7 ___ 8 ___
- [ ] Starting weights: same major ___ interested ___ career goal ___ past events ___
- [ ] Points: per attended event ___ per completed card ___
- [ ] Sample file attached ☐ · year order, most senior first: ___
- [ ] File is: ☐ CSV ☐ .xlsx · one file ☐ two files ☐ · cell separator ___
- [ ] Reason lines: renderings ☐ fine ☐ change to ___ · three sentences: ___ · when both fit, show ☐ the tie line ☐ the major-only line
- [ ] Percentages: ☐ 30/55/80 and 15 as written ☐ instead ___ · exact half ☐ up ☐ down
- [ ] Copied card carries the career goal ☐ yes ☐ no
- [ ] Two tabs on one team number ☐ share saved runs ☐ separate
- [ ] Five questions: ___ · License line: ___
- [ ] No major or no year: ☐ a count is fine ☐ the screen should say ___

## Appendix — for the builders

| Question | Row | Where it lands |
|---|---|---|
| Eight rule quantities | OQ-CE-03 | `smartmatch_domain/exercise/simulation.py` — `EXERCISE_SIMULATION_COEFFICIENTS` (`None` today) |
| Starting weights | OQ-CE-02 | `smartmatch_domain/exercise/registry.py` — the four `*_DEFAULT_WEIGHT` constants |
| Points | OQ-CE-10 | `smartmatch_domain/exercise_points.py` — `POINTS_PER_ATTENDANCE`, `POINTS_PER_COMPLETED_CARD` |
| Columns, values, year order | OQ-CE-01 | `smartmatch_domain/exercise/layout.py` — `PLACEHOLDER_LAYOUT`; `routers/exercise_matching_models.py` — `PLACEHOLDER_CLASS_YEAR_RANK` (empty) |
| CSV or XLSX | OQ-CE-05 | `smartmatch_domain/exercise/ingest.py` |
| Reason wording and precedence | OQ-CE-12 | `smartmatch_domain/exercise/reasons.py` — three `_TIED_*` phrases, `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE` |
| Percentages and half-rounding | OQ-CE-04 | `smartmatch_domain/exercise/asking.py` — `CARD_COMPLETION_SHARE`, `REQUIRED_NON_RESPONDING_SHARE`, `select_share` |
| Copied-card career goal | OQ-CE-13 | `routers/exercise_results_refresh.py` — the card copy (PR #190, owner question 4) |
| Two tabs | OQ-CE-08 | `smartmatch_domain/exercise/workspace_token.py` |
| Five questions | OQ-CE-11 | profile-card mock-up |
| License line | OQ-CE-09 | opening screen; `license_line` is nullable |
| No major or no year | PR #188, owner question 2 | `unrankable_profile_count` |
| Career goal with no card | PR #188 q3, PR #190 q4 | `exercise_matching_models._profile_evidence` |
