> DRAFT — needs Chau (rules owner) + Ann decision on whether the spread is enough. Nothing here is decided.

# #336 — does the asking choice change round two enough to show?

Refs #336. Nothing in `asking.py` or the results rule was changed; this only measures.

## How it was measured

Driver: `tests/golden/exercise/asking_choice_lift.py` (pure domain, no database).
Per seed and per choice: Northline (E11) list at default weights 3/3/2/2 (30 names)
-> `simulate_results` -> `refresh_plan` applied the way `apply_refresh` writes the
overlay -> Harbor (E12) list at default weights on the refreshed rows ->
`simulate_results` (the rule at `EXERCISE_SIMULATION_COEFFICIENTS`). Same list,
same seed for all three choices, so choices are compared paired. Round one is
therefore identical across choices by construction.

Data: Ann's 300 profiles through `ann_full_parsed()` (the September `.xlsx`).
The ledger says the fixture is an `.accdb`; the repo has one, but the app and
every test read the `.xlsx`, and the README calls the `.xlsx` the source of truth
for the `.accdb`. The October file has the same profile cells.

Run: `python -m tests.golden.exercise.asking_choice_lift 100` (about 2 minutes).

## Numbers (attended of 30 invited; mean / sd across team seeds)

N = 100 seeds:

| Choice | Round one | Round two | Lift (two minus one) |
|---|---|---|---|
| promise (`better_recommendations`) | 7.24 / 2.28 | 6.50 / 2.30 | -0.74 / 3.00 |
| small reward (`small_reward`) | 7.24 / 2.28 | 6.73 / 2.26 | -0.51 / 3.04 |
| required (`required`) | 7.24 / 2.28 | 6.87 / 2.30 | -0.37 / 3.10 |

Paired against promise (same seeds): small reward +0.23 (se 0.07), required +0.37 (se 0.09).

N = 20 (what the golden pins): lifts -0.40, -0.10, 0.00; paired +0.30 (se 0.15) and +0.40 (se 0.17).

## Ordering

Holds: required and small reward both lift more than promise, and required is above small reward.
It is a real but tiny ordering: 0.2 to 0.4 more attendees out of 30, against a per-team spread of about 3.
One team's result will not show it. Every lift is negative, so no team does "noticeably better" in round two.

## The four design risks against the numbers

1. Few profiles change: confirmed. Round-one invitees without a card: 14 (not about 22). Cards completed: 4 / 8 / 11 (promise / reward / required). Names on Harbor's list that differ from the unrefreshed list: about 1.4 / 2.8 / 3.8 of 30.
2. Northline topics do not carry to Harbor: consistent with the result. Only about 7 round-one attendees gain topics; unrefreshed Harbor and Northline lists share 4 names.
3. Stopped-responding profiles ranking onto Harbor's list: not seen. Under `required`, 0.0 non-responders landed on Harbor's list on average over 40 seeds (they are no-card profiles, which rank low). Note that `non_responding` only changes the marker in matching, not the rank, so this is luck of the data, not a guarantee.
4. Past-event credit cap from #289: not measured here. This harness runs on main, which does not contain that branch's change. Re-run after it lands.

## Open questions (for Chau, then Ann)

1. Is a gap of 0.2 to 0.4 attendees (of 30) enough for the lesson, or does Ann want a visible gap? If not, the levers are the card shares, the topic carry-over, or the coefficients. Each is Chau's and Ann's call.
2. Should round two be expected to beat round one at all? Today every choice does worse in round two because Harbor is a different event; the lesson may need to compare the choices against each other, not against round one.
3. Is 14 no-card invitees (not about 22) the intended number for the default reasonable list?
4. Draft text for Ann (Chau to send, not sent): "On your 300 profiles, with the same Northline list, teams that chose a small reward or required did about 0.2 to 0.4 attendees better than teams that only promised, out of 30 invited, across 100 simulated teams. Is that enough difference for students to see?"
