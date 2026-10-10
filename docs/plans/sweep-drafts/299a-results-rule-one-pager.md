> DRAFT — needs Danny decision (for Justin; Ann and Chau confirm the numbers). Nothing here is decided.

# Results rule, the three asking choices, and the refresh (one-page draft)

Refs #299 part (a). For Justin's one-page write-up before the week-of-Nov-9 practice run.

**Sources.** Rule in words: `python/smartmatch_domain/smartmatch_domain/exercise/simulation.py:1-38` (docstring). Numbers and Ann's words: `docs/archive/plans/open-questions/oq-ce-03-sample-result.md`. Asking choices: `python/smartmatch_domain/smartmatch_domain/exercise/asking.py:60-73,80-92,191-203`.

## 1. Status: two versions of the rule exist

| Version | State | Citation |
|---|---|---|
| D7 (2026-09-25, Chau approved) | Built. Page 2 below describes this. | `simulation.py:447-456`, `simulation.py:1-38` |
| R1 (Ann, relayed 2026-10-06) | Ruled, not built. As of main `122b01b0`, `simulation.py` still has `base_signup_rate=0.04`, no notice step. | `docs/decisions/class-exercise-results-rule-2026-10-06.md` (Status line); `simulation.py:448` |

R1 differs: a "did they notice" step (75% for the team's list, 15% for "email everyone"), 5% start, +35 interests, +15 career goal, +5/+10 past events, +5 same major, 70% attend (`class-exercise-results-rule-2026-10-06.md`, Part 1 table). Thirteen gaps (OQ-CE-19..31) are open. The one-pager must pick which version it describes (OQ 1).

## 2. The results rule, plain words (D7, what the app runs today)

1. For each of the 30 invited students the app decides: sign up? then, attend?
2. Everyone starts at 4 in 100 to sign up (`simulation.py:448`).
3. Biggest boost, 40 in 100: the event matches what the student truly cares about. Half is for a true interest that is a topic of the event, half for a career goal that fits (`simulation.py:12-15`). An undecided career goal fits nothing (`oq-ce-03-sample-result.md`, "How her words became numbers").
4. Medium boost, 10 in 100: been to at least one past event (`simulation.py:16-17`).
5. Small boost, 4 in 100: in the major the event is aimed at (`simulation.py:17-18`).
6. A little chance, up to 10 in 100 either way. It is fixed for each team, so the same list gives the same answer (`simulation.py:18-21`, `simulation.py:450-452`).
7. Everyone who signs up has a 75 in 100 chance to attend (`simulation.py:22-23`).
8. The rule reads each student's true interests, not the card the app shows. So a list built on the card can miss people (`simulation.py:23-26`).

Ann's words behind the numbers: "a lot" = 40, "some" = 10, "a little" = 4, "some randomness" = up to 10 either way. Chau approved the translation (`oq-ce-03-sample-result.md`).

## 3. The three asking choices (before the refresh)

After round one a team picks one way to ask the profiles that have no card for more information (`asking.py:60-73`). Share of those profiles that complete a card (`asking.py:80-92`):

| Choice | Completes a card |
|---|---|
| Promise better recommendations | 30% |
| A small reward | 55% |
| Required | 80%, but 15% stop responding and never sign up in round two (`asking.py:94`) |

Halves round up (`asking.py:191-203`).

## 4. The refresh

Pressing refresh applies the chosen share, deterministically from the team's seed. Each selected profile gets a new card that copies its hidden true interests onto the visible card (`asking.py:96-101`, `simulation.py:142`). One team's refresh changes nothing for other teams. The checklist expects a before/after summary on screen (`docs/10-2-2026/extracted/SmartMatch_User_Test_Checklist_10022026.txt`, section 6).

## 5. Pointer, not fact

Draft numbers for #336 (how much each asking choice lifts round two) are in PR #363, titled "[DO NOT MERGE] exercise: asking-choice round-two lift harness + ordering golden". Treat as unreviewed. Do not quote them here until Danny/Chau accept them.

## Open questions

1. Which version does the one-pager describe: D7 as built, or R1 once built? Danny. If R1, it also needs OQ-CE-19..31 answered first (Ann, via Danny).
2. Are the D7 numbers in section 2 still what Ann and Chau confirm for the demo? Ann/Chau.
3. Should the page say who the 8 already-signed-up are (OQ-CE-25)? Ann.
4. Does the page include the #336 lift numbers once #363 is reviewed? Danny/Chau.
5. Plain-words wording on "true interests" vs the shown card: does Ann want it explained to participants, or only to the instructor? Ann.
