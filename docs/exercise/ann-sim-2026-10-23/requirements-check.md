# Requirements check: class-exercise simulation (2026-10-21)

64 PASS, 0 FAIL, 41 not checkable by simulation (screens and process). 3 rounds x 5,000 runs, seeds 1-5000, 5001-10000, 10001-15000.

Re-run: `python ann_simulation.py --runs 5000 --rounds 3 --seed 1`.

## Sign-ups added, 60 emails (mean of all rounds; Ann's number in brackets)

| Setting | Northline | Harbor before | After: promise | After: small reward | After: required |
|---|---|---|---|---|---|
| Major first | 7.2 [7.5] | 6.6 [6.7] | 6.9 [6.9] | 7.0 [7.0] | 6.8 [6.8] |
| Interest first | 5.3 [5.3] | 7.1 [7.0] | 10.8 [10.8] | 13.5 [13.5] | 13.7 [13.6] |
| Balanced 3/3/2/2 | 9.4 [9.4] | 9.2 [9.2] | 10.3 [10.1] | 11.3 [11.1] | 11.9 [12.0] |
| Best possible list | 13.8 [13.8] | 14.9 [14.9] | 14.9 | 14.9 | 14.5 |

## Per round (balanced 3/3/2/2, 60 emails, sign-ups added: mean / SD)

| Round | Northline | Harbor before | After: promise | After: small reward | After: required |
|---|---|---|---|---|---|
| 1 | 9.42 / 2.68 | 9.14 / 2.66 | 10.30 / 2.85 | 11.23 / 2.99 | 11.84 / 3.04 |
| 2 | 9.42 / 2.72 | 9.19 / 2.73 | 10.33 / 2.87 | 11.29 / 2.92 | 11.92 / 3.01 |
| 3 | 9.39 / 2.70 | 9.20 / 2.70 | 10.34 / 2.89 | 11.33 / 2.96 | 11.90 / 3.04 |

## Every rule

| ID | Rule | Ann's words | Source | Target | Ours | Result | Note |
|---|---|---|---|---|---|---|---|
| R01 | Mass email to all 300; 20 in 100 notice it | Everyone (all 300): receives usual mass email or post. 20% notice it. | E10 Q2, 2026-10-10 | mass-alone sign-ups = 0.20 x sum of chances = 10.43 | 10.47 (+/- 0.03) | PASS | Northline, balanced 60; same check holds for any list. |
| R02 | CBACH email to the listed students; 60 in 100 notice it (about 68 notice one) | Team's matched 30: also receive a personal email from CBACH. 60% notice it. | E10 Q2, 2026-10-10 | added = 0.48 x sum of listed chances = 9.41 | 9.41 (+/- 0.02) | PASS | Northline, balanced 60. |
| R03 | Each sign-up shows up with chance 65 in 100 | Rates apply exactly: 20% mass email, 60% CBACH email, 65% show-up. | E10 Q4, 2026-10-10 | attended / signed up = 0.65 | 0.6492 | PASS |  |
| R04 | The 8 already signed up attend at 65 in 100 | the 8 pre-registered students should attend 65% of the time, like everyone else. | E15 Q2, 2026-10-15 | 8 x 0.65 = 5.20 on average | 5.21 (+/- 0.01) | PASS |  |
| R05 | No extra luck; same run repeated gives the same answer | No extra luck. The team's fixed chance draw alone decides who notices, signs up and shows up. | E10 Q4, 2026-10-10 | identical results on a repeat | identical | PASS |  |
| R06 | Each team has its own chance draw | keep A (each team own chance draw) | E10 Q1, 2026-10-10 | different seeds give different draws | every run uses its own seed | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R07 | Students who stop responding notice nothing, mass email included | They notice nothing, mass email included. | F16 decisions table, 2026-10-16; E15 Q3 | mass-email-alone sign-ups at Harbor fall under 'required' | 12.17 before -> 10.80 under required | PASS | They are skipped before any draw (the app's rule; parity test). |
| R08 | +35 when a true interest is an event topic | The "+35" in your example is the interest-match bonus, not past events | E15 second reply, 2026-10-15 | +35 | +35 | PASS |  |
| R09 | Past events: +5 for 1-2, +10 for 3 or more | past events add +5 (1–2 events) or +10 (3 or more), which is fine. | E15 second reply, 2026-10-15 | +5 / +10 | +5 / +10 | PASS |  |
| R10 | Profile updates during the exercise never count as past events | Agree that profile updates during the exercise don't count as past events. | E15 second reply, 2026-10-15 | sign-up chance reads the file's past events only | p_signup reads len(file past events) only | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R11 | Start at 5; +15 for a career-goal fit; +5 for same major | (team summary of Ann's Step B) Start at 5 ... +15 if the hidden true career goal fits ... +5 if the event targets the student's major | S6 2026-10-06 via owner ruling 2026-10-12 (not quoted by Ann since) | 5 / +15 / +5 | 5 / +15 / +5 | PASS | Conflict C16: Ann has not restated these three numbers in her own words. |
| R12 | Highest sign-up chance is 70 | the most anyone can reach is 70 (team summary) | S6 / docs/decisions/class-exercise-current-rule.md | at most 0.70 | highest in the class file: 0.70 | PASS |  |
| R13 | A matching stated interest counts in full | a matching interest should count in full. | O2 item 4a, 2026-10-02 | 1 for any overlap | 1 for any overlap (A10) | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R14 | Past-event topic factor is 0 / 0.5 / 1 | Past events 0 / 0.5 / 1: ok | E10 part 2, 2026-10-10 | 0 / 0.5 / 1 | 0 / 0.5 / 1 | PASS |  |
| R15 | An Undecided career goal earns 0, on every event (Harbor too) | That rule is not in the plan, and Northline is not a broad event. Please remove it. | O2 item 4b, 2026-10-02; answer of 2026-10-07 | 0 in matching and in the sign-up chance | matching 0.0; sign-up chance 0.05 (= the 5 start) | PASS |  |
| R16 | Default weights 3/3/2/2 | Weights 3,3,2,2, whole steps 0-10, total whole number: ok | E10 part 2, 2026-10-10; ruling 2026-10-06 | 3/3/2/2 | 3/3/2/2 | PASS |  |
| R22 | Hidden true columns never used to build a list | The app must never show them and never use them to build a list. | O2, 2026-10-02 | lists use only major, card, past events | only 'best possible' (an oracle for comparison) reads them; card completers copy them, as the app does | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R23 | 60 emails in both rounds | Send 60 tailored, personalized emails in both rounds, not 30. | F16, 2026-10-16 | 60 per list | [60] | PASS |  |
| R25 | The 300-student mass email stays as the comparison | The 300-student mass email stays as the comparison. | F16, 2026-10-16 | all 300 get it | 300 students | PASS |  |
| R26 | Seats empty out of 60, counting the 8 | seats still empty out of 60, counting the 8 already signed up. | checklist row 60 (Ann's test step) | 60 - the 8 who came - attendees | 41.9 empty on average (Northline, balanced 60) | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R27 | Lift line: mass email alone X; with your list Y; your list added Y - X | Mass email alone: 11 sign-ups. With your 30 CBACH emails: 17. Your list added 6. | E10 Q2, 2026-10-10 | added = with list - mass alone | computed exactly that way | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R28 | Attendees added are fewer than sign-ups added; about 3 fewer is fine | If it shows attendance, the ~3 fewer attendees is fine. | E15 Q2, 2026-10-15 | about 3 fewer | 3.3 fewer (Northline, balanced 60) | PASS |  |
| R32 | Asking goes to all students without a card (230) | The card request goes to all students without a card (230 of 300), not only the team's invitees. | F16, 2026-10-16 | 230 | 230 | PASS |  |
| R33 | About 30 / 55 / 80 in 100 complete a card | about 30%, 55%, and 80% of invited profiles without a card complete one. | checklist row 76 (Ann's test step) | 69 / 127 / 184 of 230 | 69 / 127 / 184 | PASS |  |
| R34 | Required: about 15 in 100 stop responding | Under 'required,' about 15% of those without a card are marked 'stopped responding,' | checklist row 77 (Ann's test step) | 35 of 230 | 35 | PASS |  |
| R38 | Before and after asking use the same draws | the gap between the two rows can only come from better information. | F16, 2026-10-16 | same seed for both rows | same seed for both rows | PASS | By design: built into the rule; the parity test proves the app does the same. Not measured on the runs. |
| R47 | 5,000-run check for both events with 60 | a rerun of the 5,000-run check for both events with 60. | F16, 2026-10-16 | 5,000 runs, both events | 3 rounds x 5,000 runs | PASS |  |
| R52 | '13 already coming' is not all 8 + 5: the 8 attend at 65% | equals all 8 plus the mass email's 5, so please confirm this is live. | F16, 2026-10-16 | 8 at 65% (about 5.2 of 8 come) | 5.21 of 8 come | PASS | Live: same rule as R04. Her test run predates the Oct 16 change. |
| R42-major | Major first, Northline, 60 emails: sign-ups added | The list adds about 7.5 (major first), 5.3 (interest first) and 9.4 (balanced) | F16 'Round one with 60', 2026-10-16 | 7.5 (within 0.5) | 7.20 (diff -0.30) | PASS |  |
| R42-interest | Interest first, Northline, 60 emails: sign-ups added | The list adds about 7.5 (major first), 5.3 (interest first) and 9.4 (balanced) | F16 'Round one with 60', 2026-10-16 | 5.3 (within 0.5) | 5.28 (diff -0.02) | PASS |  |
| R42-balanced | Balanced 3/3/2/2, Northline, 60 emails: sign-ups added | The list adds about 7.5 (major first), 5.3 (interest first) and 9.4 (balanced) | F16 'Round one with 60', 2026-10-16 | 9.4 (within 0.5) | 9.41 (diff +0.01) | PASS |  |
| R42-best | Best possible list, Northline, 60 emails: sign-ups added | The list adds about 7.5 (major first), 5.3 (interest first) and 9.4 (balanced) | F16 'Round one with 60', 2026-10-16 | 13.8 (within 0.5) | 13.80 (diff -0.00) | PASS |  |
| R43-major-before | Major first, Harbor, before asking, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.7 (within 0.5) | 6.55 (diff -0.15) | PASS |  |
| R43-major-after_promise | Major first, Harbor, after: promise, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.9 (within 0.5) | 6.85 (diff -0.05) | PASS |  |
| R43-major-after_reward | Major first, Harbor, after: small reward, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 7.0 (within 0.5) | 6.98 (diff -0.02) | PASS |  |
| R43-major-after_required | Major first, Harbor, after: required, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.8 (within 0.5) | 6.79 (diff -0.01) | PASS |  |
| R43-interest-before | Interest first, Harbor, before asking, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 7.0 (within 0.5) | 7.06 (diff +0.06) | PASS |  |
| R43-interest-after_promise | Interest first, Harbor, after: promise, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 10.8 (within 0.5) | 10.78 (diff -0.02) | PASS |  |
| R43-interest-after_reward | Interest first, Harbor, after: small reward, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 13.5 (within 0.5) | 13.54 (diff +0.04) | PASS |  |
| R43-interest-after_required | Interest first, Harbor, after: required, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 13.6 (within 0.5) | 13.73 (diff +0.13) | PASS |  |
| R43-balanced-before | Balanced 3/3/2/2, Harbor, before asking, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 9.2 (within 0.5) | 9.18 (diff -0.02) | PASS |  |
| R43-balanced-after_promise | Balanced 3/3/2/2, Harbor, after: promise, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 10.1 (within 0.5) | 10.32 (diff +0.22) | PASS |  |
| R43-balanced-after_reward | Balanced 3/3/2/2, Harbor, after: small reward, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 11.1 (within 0.5) | 11.29 (diff +0.19) | PASS |  |
| R43-balanced-after_required | Balanced 3/3/2/2, Harbor, after: required, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 12.0 (within 0.5) | 11.89 (diff -0.11) | PASS |  |
| R43-best-before | Best possible list, Harbor, before asking, 60 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 14.9 (within 0.5) | 14.91 (diff +0.01) | PASS |  |
| R44-major-before | Major first, Harbor, before asking, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 3.7 (within 0.5) | 3.85 (diff +0.15) | PASS |  |
| R44-major-after_promise | Major first, Harbor, after: promise, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 3.3 (within 0.5) | 3.50 (diff +0.20) | PASS |  |
| R44-major-after_reward | Major first, Harbor, after: small reward, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 3.1 (within 0.5) | 3.40 (diff +0.30) | PASS |  |
| R44-major-after_required | Major first, Harbor, after: required, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 3.0 (within 0.5) | 3.36 (diff +0.36) | PASS |  |
| R44-interest-before | Interest first, Harbor, before asking, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 5.8 (within 0.5) | 5.68 (diff -0.12) | PASS |  |
| R44-interest-after_promise | Interest first, Harbor, after: promise, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.9 (within 0.5) | 6.79 (diff -0.11) | PASS |  |
| R44-interest-after_reward | Interest first, Harbor, after: small reward, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.8 (within 0.5) | 6.80 (diff +0.00) | PASS |  |
| R44-interest-after_required | Interest first, Harbor, after: required, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.9 (within 0.5) | 6.71 (diff -0.19) | PASS |  |
| R44-balanced-before | Balanced 3/3/2/2, Harbor, before asking, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 4.8 (within 0.5) | 5.08 (diff +0.28) | PASS |  |
| R44-balanced-after_promise | Balanced 3/3/2/2, Harbor, after: promise, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 6.3 (within 0.5) | 6.20 (diff -0.10) | PASS |  |
| R44-balanced-after_reward | Balanced 3/3/2/2, Harbor, after: small reward, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 7.3 (within 0.5) | 7.39 (diff +0.09) | PASS |  |
| R44-balanced-after_required | Balanced 3/3/2/2, Harbor, after: required, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 7.8 (within 0.5) | 7.95 (diff +0.15) | PASS |  |
| R44-best-before | Best possible list, Harbor, before asking, 30 emails: sign-ups added | These are my estimates ... from a simplified version of the rule on the Oct 2 class file | F16 'Why 60 emails, in numbers' table, 2026-10-16 | 8.4 (within 0.5) | 8.46 (diff +0.06) | PASS |  |
| R45a | Northline target about 9 (balanced, 60) | My rough new targets are about 9 at Northline | F16, 2026-10-16 | 8.5 to 9.5 | 9.41 | PASS |  |
| R45b | Harbor before asking about 9 (balanced, 60) | at Harbor about 9 before asking | F16, 2026-10-16 | 8.5 to 9.5 | 9.18 | PASS |  |
| R45c-promise | Harbor after asking (promise) 10 to 12 (balanced, 60) | and 10 to 12 after. | F16, 2026-10-16 | 10 to 12 | 10.32 | PASS |  |
| R45c-reward | Harbor after asking (reward) 10 to 12 (balanced, 60) | and 10 to 12 after. | F16, 2026-10-16 | 10 to 12 | 11.29 | PASS |  |
| R45c-required | Harbor after asking (required) 10 to 12 (balanced, 60) | and 10 to 12 after. | F16, 2026-10-16 | 10 to 12 | 11.89 | PASS |  |
| R46 | Old 30-email targets (about 6 Northline, 4-5 Harbor) no longer apply | The old targets ('about 6' at Northline, '4 to 5' at Harbor) no longer apply. | F16, 2026-10-16 | superseded | for reference: 6.20 / 5.08 | N/A |  |
| V1 | The rounds agree within sampling noise (our own check) |  | brief | largest gap < 4 standard errors | 2.49 standard errors | PASS |  |
| R17 | P004 drops but stays above a plain Accounting major | P004 Brandon Soto: OK (keep, reword checklist | E10 part 2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R18 | Tie order: more information, then seniors, then a fixed order | Works as written: more information first, then seniors first, then a fixed order. | O2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R19 | Years run Freshman to Senior on 'who is on the list' | years should run Freshman, Sophomore, Junior, Senior, not alphabetically. | O2 4d | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R20 | One reason line per name | A profile known by major alone says 'same major; nothing else on file.' | O2 4c; F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R21 | Event description above the sliders | Show a short description at the top of the Northline and Harbor pages | O2 item 5 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R24 | 60 as an instructor setting (checklist said 5 to 30) | whether 60 is a simple instructor setting | F16 (open question) | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R29 | Debrief sentence on the results screen | Each team's numbers include its own luck. | E10 Q1; E15 Q4 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R30 | One results run per team per event | A second run must be blocked | O2; F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R31 | Lock round two until Northline results | Lock round two, and Harbor results, until round one is done. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R35 | Three asking options, one plain sentence each | Three options each have one plain sentence | checklist row 69 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R36 | Way of asking picked after Northline results | Your team picks a way of asking after it has its results for Northline. | E10 addition 2026-10-12 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R37 | Major-only setting kept in round two | A major-only setting cannot benefit from new cards. That is a lesson | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R39 | Before/after rows do not use up the run | These extra rows do not use up the team's one results run. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R40 | Harbor debrief line | Same event, same students, same luck. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R41 | 'How much we know' table in both rounds | Show it in round one, and again in round two as before and after. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R48 | Chart caption | Light bar: mass email alone. Dark bar: mass email plus your CBACH emails. | F16 results item 5 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R49 | Leave 'invited' out of the chart | Leave 'invited' out of the chart, or give it its own chart. | F16 results item 4 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R50 | One 'added' measure in the headline | Use one measure in the headline, or label both | F16 results item 1 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R51 | Round-one recap matches the round-one screen | Same numbers and wording in both places. | F16 results item 3 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R53 | Show 'You will send' with the 60 names | Show 'You will send: [name]' with a short summary of its 60 names | F16 results item 7 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R54 | Confirm wording names the setting | Send 'Balanced'? You get one results run for Northline. | F16 results item 8 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R55 | Round banners | Round 1 of 2: Northline | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R56 | Round-one done message | Round 1 done. Next: Round 2, Harbor. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R57 | Nothing from round two before round one results | Show nothing from round two ... until round one results are in. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R58 | Same-topic note | Keep it, but say it only counts toward events on the same topic. | F16 asking item 2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R59 | 'Stopped responding' in plain words | Say this in plain words on the screen. | F16 asking item 1 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R60 | Clear test teams, close both events | Clear all test teams and close both events before testing week | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R61 | Fixed copy for testing and class | Run testing and class from a fixed copy that nobody edits. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R62 | Two teams at once, isolated | Neither should see or change the other's work. | F16 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R63 | Readable on the projector | Readable from the back of the room on the projector. | checklist row 63 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R64 | Pages load in under 5 seconds | Each page loads in under 5 seconds in Chrome | checklist row 95 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R65 | Wrong passcode message | A wrong passcode shows 'Wrong passcode' and nothing else. | checklist row 11 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R66 | Missing-column upload message | You see a plain message naming the missing column | checklist row 13 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R67 | List limit can be changed | Change the list limit from 30 to 25. You see 'Limit set to 25.' | checklist row 15 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R68 | Refresh needs two presses | Team's own refresh two presses: OK | E10 part 2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R69 | 'Refreshed at' time stamp | must say 'Refreshed at 10:42 AM' too | E10 part 2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R70 | Pinned team status line | pin it — stays on screen while scrolling | E10 part 2 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R71 | New data file gives a new draw | New file gives new chance draw. | E10 Q6 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R72 | License line | All student profiles are fictional. | E10 addition 2026-10-12 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |
| R73 | Download leaves out the pink columns | The two pink columns from the data file do not appear. | checklist row 51 | - | - | N/A | A screen or process rule; checked on the class checklist, not by the simulation. |

## Conflicts between sources (newest from Ann wins)

| ID | Topic | Older | Newest | What we used |
|---|---|---|---|---|
| C1 | Notice, show-up and luck | Sep 25: start 4, +40 'a lot', +/-10 luck, 75 attend. Oct 6 Step A: 75/15 notice, 70 attend, small luck. | Oct 10: 20 / 60 notice, 65 show up, no luck | Used Oct 10 |
| C2 | Sign-up points | Sep 25 translation +40 / +10 / +4. Oct 6 Step B +35 / +15 / +5 or +10 / +5. | Step B; Oct 15 confirms +35 and +5/+10 | Used Step B |
| C3 | Past-event cap | Oct 15 first reply: +5 per event, cap +15. Same-day second reply withdrew it. | Oct 15 second reply and Oct 16: +5 / +10 | Used +5 / +10 |
| C4 | 'Past events' means two things | List factor counts RELATED past events (0 / 0.5 / 1); sign-up chance counts ANY past event (+5 / +10). | Both approved, for different parts | Kept both |
| C5 | Undecided career goal | Sep 25: half credit on broad events. Oct 2: remove on Northline. Oct 7: 0 on every event. | Oct 7 | Used 0 everywhere |
| C6 | Default weights | Oct 2: all start at 0.25. Oct 6: 3/3/2/2. | Oct 10 'ok' to 3/3/2/2 | Used 3/3/2/2 |
| C7 | List size | Oct 2 and Oct 10: 30. Oct 16: 60. Checklist: 5 to 30. | Oct 16: 60 (instructor-setting range still open) | Ran 60, and 30 for comparison |
| C8 | Targets | Oct 10: about 6 Northline, 4-5 Harbor (30 emails). | Oct 16: about 9; Harbor about 9 then 10-12 | Used Oct 16 |
| C10 | Who is asked for more | Older: only the team's invitees, end of round one (checklist row 76 still says 'invited'). | Oct 16: all 230 without a card | Used all 230 |
| C14 | '13 already coming' | Her Oct 16 test run showed all 8 plus 5. | Oct 15: the 8 attend at 65% | Used 65% |
| C16 | Start 5 / +15 goal / +5 major | Only in the team's summary of her Oct 6 Step B; 'the team's existing sign-up chances' (Oct 10) was read as Step B. | Not restated by Ann | Used Step B; ask Ann to confirm |

## Cross-checks and caveats

1. **Same code as the app.** `tests/unit/test_ann_simulation_parity.py` (13 tests) proves `tools/ann_simulation.py` gives the app's exact lists, asking plan and per-run numbers for every setting, both list sizes and all three ways of asking. Round 1 (seeds 1-5000) also equals the Oct 19 run that imported the app directly (`sim-60`, repo sha c79fd7db) to every digit, in all 20 cells at 60 emails and both 30-email continuity cells.
2. **No FAIL.** 64 PASS: 57 measured on the runs, 7 marked "By design" (R06, R10, R13, R22, R26, R27, R38) that are built into the rule rather than measured. 41 rules are screens or process and are checked on the class checklist instead.
3. **Tolerance.** Ann's per-cell numbers pass within 0.5 sign-ups, a margin set before the runs. Largest gaps: major first at Northline -0.30; 30-email major first after asking +0.20 to +0.36; balanced after promise +0.22. Her table came from "a simplified version of the rule on the Oct 2 class file", so gaps of this size are expected. The direction of every lesson holds: major first stays flat, interest first gains most from asking, required beats reward beats promise for balanced.
4. **Rounds agree.** The largest round-to-round gap on any of Ann's cells is 2.49 standard errors (check V1, limit 4).
5. **To confirm with Ann (open, not blocking the numbers).** C16: start 5 / +15 career goal / +5 major are the team's reading of her Oct 6 Step B. R24: whether 60 should be an instructor setting with a floor of 5. C13: the team chose to explain the fixed tie order rather than order ties by class year.
