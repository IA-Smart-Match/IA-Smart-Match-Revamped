# SmartMatch — Matching Process and Test Results

**Application revision:** `4fc80d0` (the revision on the class VM) · **Test date:** 27 October 2026 · **Class URL:** https://exercise.smartmatch.cloud/exercise

## 1. Purpose

SmartMatch is a two-round classroom exercise for AI in Marketing. Each team chooses which 60 of 300 fictional students get a personal CBACH email for an event. Round 1 is Northline Analytics (technology). Round 2 is Harbor Consumer Brands (International Business and Marketing). All 300 students also get the usual mass email, which is the comparison. The tests checked that a team can complete both rounds, that the matching follows the documented rules, and that the results are correct and repeatable.

## 2. Matching Method

**Inputs.** The instructor loads one data file: 300 fictional student profiles and 12 events (`SmartMatch_Student_Body_300_10022026.xlsx`). A profile has a major, class year, past events attended, and, for 70 students, a profile card with stated interests and a career goal. 230 students have no card.

**Ranking.** The team saves a setting: four whole-number weights (0–10) for major, interest, past events and career goal. The default is 3/3/2/2. The system scores each student as the weighted sum of the four fits and sorts by score. Ties go to the student with more known information, then to the senior, then to a fixed order stored in the data file. The top 60 form the team's list. The ranking contains no randomness.

**Outcome.** The system then simulates each of the 300 students:

1. Notices an email: 20 in 100 for the mass email; 60 in 100 for the CBACH email (listed students only).
2. Signs up, if noticed: 5 in 100, plus 35 if a true interest matches the event topic, 15 for a fitting career goal, 5 or 10 for past events (1+ or 3+), and 5 for the targeted major.
3. Attends, if signed up: 65 in 100.

"True interest" is hidden data, not the card. Each chance uses a SHA-256 hash of the team's stored seed, the event, the student and the step. Therefore the same team and list always give the same result. **List added** is the number of listed students who signed up and would not have signed up from the mass email alone.

**Round 2.** Before Harbor, the team chooses how to ask students without a card for one: a promise (30% respond), a small reward (55%), or required (80%, but 15% of students stop responding). New cards change only the information the ranking uses. The Harbor list uses the same rules. Each team runs results once per event; the database rejects a second run.

## 3. Test Method

- **Environment:** local copy of the exercise stack (PostgreSQL 16, exercise API, web front end) at `4fc80d0`, driven by Playwright in Chromium. Public deployment evidence comes from the GitHub deploy workflow.
- **Dataset:** the shipped 300-profile fictional fixture (SHA-256 `57cb47e7…9866`).
- **Procedure:** the instructor opened results for both events. Team 1 and Team 2 worked at the same time in separate browser sessions. Each saved the setting "Balanced" (3/3/2/2), sent the Northline list, read the results, chose "A small reward", asked students, then sent and read the Harbor list.
- **Checks:** 25 screenshots; server run counts; negative tests (wrong code, short code, empty setting name, double send, page reload, deep-link reload). A separate script ran the real matching code twice with fixed seed 20261027 and compared the outputs. Unit and golden tests ran with pytest; front-end tests ran with Vitest.

## 4. Test Results

Results as shown on the results pages, 27 October 2026, 21:31–21:33 UTC. Each list has 60 students.

| Round | Team | Way of asking | List signed up | Would sign up from mass email anyway | List added | Came because of list | Seats still open |
|---|---|---|---:|---:|---:|---:|---:|
| 1 Northline | Team 1 | — | 9 | 1 | 8 | 7 | 41 |
| 1 Northline | Team 2 | — | 16 | 8 | 8 | 4 | 38 |
| 2 Harbor | Team 1 | Small reward | 15 | 6 | 9 | 8 | 39 |
| 2 Harbor | Team 2 | Small reward | 17 | 5 | 12 | 6 | 43 |

Both teams used the same setting but got different numbers. This is expected: each team has its own seed, so each team has its own luck. In every row, *list added* equals *list signed up* minus *would sign up anyway*. The fixed-seed script gave identical output on two runs and under a different Python hash seed. All four fixed-seed lists had 60 unique students, in weight order.

## 5. What Worked

- A first-time team entered with its code, completed Round 1, chose a way of asking, completed Round 2, and saw both results pages. Two teams did this at the same time.
- Matching follows the documented rules. The code agrees with every rule in Section 2.
- Results persist: reloading the page keeps the run, and a double press of "Send list" recorded one run.
- Invalid input is rejected: a wrong team code shows "That code is not right for this team"; a short code and an empty setting name disable the button.
- Automated tests: 1,271 front-end tests passed; 66 golden exercise tests passed; 1,440 exercise unit tests passed.
- The last deploy (26 October, 06:32 UTC) placed `4fc80d0` on the VM. All checks passed. On the same day the exercise host answered HTTP 200 from the deploy runner.

## 6. What Did Not Work

- **Deploy check (fixed).** On 26 October two deploys failed at the public check. The first used the retired `pilot.plated.blog` address. The second pointed the check at the exercise host, which does not serve the route the check expects. The third deploy, against `pilot.smartmatch.cloud`, passed. No automated check covers the exercise host yet.
- **Walkthrough recorder (open).** `tools/walkthrough/record_student_flow.mjs` does not enter the 4-digit team code, so it fails at step 1. This does not affect students.
- **Test environment limits (open).** Docker Hub rate limits stopped the container image build, so the local API and front end ran as host processes on Python 3.12. `make setup` fails on Python 3.13. Two unit tests failed only because of a local settings file.
- **Not reproduced.** The "5,000 simulated runs" table in the earlier write-up has no script in the repository, so this report does not use it.
- **Not tested.** PUBLIC-RUN-PLACEHOLDER

## 7. Conclusion

The full two-round exercise passed in the local test at revision `4fc80d0`. Matching agrees with the documented rules, and results are repeatable with a fixed seed. CONCLUSION-PLACEHOLDER
