# Class exercise — open-question register

**Status:** scoped register for `ProductScope.CLASS_EXERCISE`, created
2026-09-16. Rows here concern the class exercise only. Nothing here closes an
OQ-SC, OQ-SE, or OQ-CBA row, and nothing in those registers closes a row here:
the exercise stores no real student and no real event, so the privacy, records,
and consent questions of the CBA track do not arise in it.

**Owner of the scope:** Ann Wang (instructor and project lead). Placeholders
below are the numbers in her build table and stay in force until she confirms
or replaces them.

| ID | Decision question | Owner | Placeholder / safe default | Blocks | Status |
|---|---|---|---|---|---|
| OQ-CE-01 | What are the final column names and value vocabularies of the data file (major, year, past events, stated interests, career goal, hidden true interests)? | Ann | None — the 20-row sample due Fri Sept 18 answers this. Until then the spec's data model is marked PLACEHOLDER. | Ingest, factors, markers | OPEN — waits on 9/18 |
| OQ-CE-02 | What default weights do the four factors carry when a team opens an event? | Ann + Chau | Equal weights (0.25 each), shown in plain words. | Matching | OPEN |
| OQ-CE-03 | What are the four coefficients of the simulated-results rule (true-interest fit lift, frequent-attender lift, same-major lift, chance size)? | Ann + Chau | Chau proposes; Ann confirms before the November practice run. | Results | OPEN |
| OQ-CE-04 | What are the three "asking for more" percentages? | Ann | 30 percent / 55 percent / 80 percent with 15 percent non-responding, as named constants. | Refresh | OPEN — Ann confirms before the practice run |
| OQ-CE-05 | Is the data file CSV or XLSX? | Ann + Danny | CSV read with the standard library. XLSX would add `openpyxl` as a runtime dependency for one screen. | Ingest | OPEN — ask on 9/18 |
| OQ-CE-06 | Where does the site live and what is its stable address? And what rate-limits the no-login routes? | Danny | **Decided 2026-09-21, Danny (row owner): the exercise runs at `exercise.plated.blog`, a second hostname on the existing tunnel, exercise scope only, no Access policy; instructor routes protected by the passcode plus proxy rate limiting.** That settles the address and the hosting shape. It does not settle the second half: the proxy rate-limit rule is **not applied yet**, so `services/api/smartmatch_api/exercise_rate_limit.py` stays a marked `PLACEHOLDER (OQ-CE-06)`, per process and unable to bound CPU, until it is. | Hosting | OPEN — address and hosting shape decided 2026-09-21. The row stays OPEN, not CLOSED, because the rate-limit half it also carries (design spec §14; `exercise_rate_limit.py`, `routers/exercise_workspace.py`, `routers/exercise_instructor.py`, `routers/exercise_matching.py`, `routers/exercise_results.py`) is named work nobody has done. Closing it now would mark six marked placeholders as settled. |
| OQ-CE-07 | How is the instructor passcode set and shared with Ann and Dr. Lin? | Danny + Ann | One environment variable per deployment; shared out of band; rotated after the spring run. | Instructor page | OPEN |
| OQ-CE-08 | Do two browser tabs that enter the same team number share one workspace, or is each tab its own workspace? | Ann | Shared per team number: Ann's table says "one browser tab per team, team number entered", so a second tab on the same team sees the same saved runs. | Team workspaces | OPEN — confirm on 9/18 |
| OQ-CE-09 | What license line goes on the opening screen? | Ann | None shown until Ann provides the sentence. | Opening screen | OPEN — by Nov 20 |
| OQ-CE-10 | How many points does a profile earn per attended event, and for completing a card? | Ann + Chau | One point each, as named placeholder constants in `python/smartmatch_domain/smartmatch_domain/exercise_points.py`; equal so the code does not rank attendance above card completion. Unknown card completion earns nothing. | Points | OPEN — Ann confirms before the November practice run |
| OQ-CE-11 | What are the five questions on the "five quick questions" card? The requirements name only stated interests and career goal as what a completed card holds. | Ann | The mock-up shows the five profile fields design spec §2 (data model) names (major, year, stated interests, career goal, past events), marked as a mock-up; the hidden true interests are never asked. Depends on OQ-CE-01 for wording. | Profile-card mock-up | OPEN — confirm before the November practice run |
| OQ-CE-12 | Reason-line wording and precedence (design spec §4.5). Three tie sentences Ann did not write, kept in `reasons.py` as `PLACEHOLDER (wording pending Ann; see PR #180)`: `tied on what counted; ordered by year` (a tie that is not on the major), `tied; more information on file first`, and `tied; placed in a fixed order that never changes` — what are her words for each? Separately, her two verbatim phrases are table cells without a capital or a full stop, so `assert_one_sentence` refuses them as written; they are stored byte for byte as `ANN_MAJOR_ONLY_PHRASE` (`same major; nothing else on file`) and `ANN_TIED_ON_YEAR_PHRASE` (`tied on major; ordered by year`) and rendered capitalised and full-stopped (`Same major; nothing else on file.`), and the single-factor line is framed `What counted: same major.` because the bare label is a two-word fragment — is each rendering acceptable? And precedence: a major-only profile whose place the year decided matches both of her lines, and the requirements rank neither — which line should a class participant see? | Ann | The current code behaviour: the three sibling phrases above, both renderings as shown, and `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE = True` in `python/smartmatch_domain/smartmatch_domain/exercise/reasons.py` (the tie line wins; flipping it is one line). | Reason lines | OPEN |
| OQ-CE-13 | When a refresh copies a card onto a profile, what career goal does the copied card carry — the one already on the base row, or nothing? | Ann | Owner ruling 2026-09-21 (Danny): **copied cards carry the base `career_goal`; `NULL` only when the base row has none.** A safe default, not Ann's answer. **Implemented on `main`** (PRs #195 and #199): `smartmatch_domain.exercise.asking.COPIED_CARD_CAREER_GOAL = CopiedCardCareerGoal.BASE_GOAL`, marked `PLACEHOLDER (OQ-CE-13)`; `copied_card_career_goal` is exhaustive over the enum (`assert_never`) and is applied in `smartmatch_persistence.exercise.results_cards`. Ann's answer becomes a one-constant switch. | Refresh | OPEN — Ann may replace the default; the default is implemented as a switchable placeholder |

## Closure discipline

A row closes with a dated line naming who decided and what. Ann's Friday
check-in notes are sufficient evidence for this register.

A dated decision on part of a row is recorded in the row's decision cell and
leaves the row OPEN while the rest of it is undone — see OQ-CE-06.

## What is being asked of Ann and Chau

[`class-exercise-proposal-for-ann-and-chau.md`](class-exercise-proposal-for-ann-and-chau.md)
collects the rows above into one short document the owner brings to them. It
closes nothing: every row stays as this register records it until a dated
answer is written here.
