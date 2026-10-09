# Results rule (Ann, relayed 2026-10-06): impact analysis

**Status:** analysis only. It changes no code, test, golden file, fixture or
coefficient, and it decides nothing.
**Written:** 2026-10-06, for Danny (owner) and Chau.
**Scope:** `ProductScope.CLASS_EXERCISE`.
**Code references:** `origin/main` at `783a1244`; PR #337 head `152486cf`.
**The ruling:** [`class-exercise-results-rule-2026-10-06.md`](../decisions/class-exercise-results-rule-2026-10-06.md)
(R1); verbatim in the
[correspondence record, exchange D](../decisions/stakeholder-correspondence-2026-09.md#d-chaus-question-and-ann-wangs-results-rule).
**Open questions:** OQ-CE-19 to OQ-CE-31 in the
[register](open-questions/class-exercise-open-questions.md).

Paths are shortened:

- `sim` = `python/smartmatch_domain/smartmatch_domain/exercise/simulation.py`
- `domain/` = `python/smartmatch_domain/smartmatch_domain/`
- `api/` = `services/api/smartmatch_api/routers/`
- `web/` = `apps/web/legacy-frontend/src/app/pages/exercise/`

## 1. Read this first

1. **The rule Ann gave is not the rule the app runs.** The app has no notice
   step, and six of its eight numbers differ. Nothing is implemented.
2. **Under Ann's numbers, "email everyone" draws about as many sign-ups as a
   typical list of 30.** On Ann's 300 profiles it is expected to draw 7.8
   sign-ups at Northline and 9.1 at Harbor. The app's suggested list
   (equal weights) is expected to draw 9.0 and 6.7. At Harbor the mass email
   matches or beats that list for about 4 teams in 5. This is a question for
   Ann (OQ-CE-31). It is not something to tune.
3. **This is still far closer to the lesson than today.** Today "email
   everyone" draws about 46 to 53 sign-ups against a list's 7 to 9, because
   it runs the same rule with no notice step.
4. **Neither rule fills the room.** Under Ann's rule "email everyone" adds
   about 5 to 6 attendees to the 8 already coming: about 14 of 60 seats.
5. **A refresh changes results only through a better list.** That is true
   today and stays true under Ann's rule. The expected gain at Harbor is
   0.2 to 1.6 sign-ups, against a team-to-team spread of about 2.4. One
   team's round two will not reliably look better than its round one
   (OQ-CE-28).

## 2. Current rule against the ruling, step by step

| Step | Ann's rule (R1) | `main` today | Seam on `main` | Status |
|---|---|---|---|---|
| A. Notice, team's list | 75% | No such step. Every invited profile reaches step B. | `sim:558-581` `_outcome` | **missing** |
| A. Notice, "email everyone" | 15% | The same rule and the same seed as the team's list; no separate rate. | `sim:647-661` `run_email_everyone`; `api/exercise_results_run.py:331` | **missing** |
| B. Start | 5% | 0.04 | `sim:476` `base_signup_rate` | **differs** |
| B. True interests match | +35 | +0.20: half of `true_fit_lift` 0.40. Any one true interest equal to any one event topic earns it. | `sim:477`, `:483`, `:535-536` | **differs** |
| B. True career goal fits | +15 | +0.20: the other half. The goal's topic must be one of the event's topics. | `sim:537-538` | **differs** |
| B. Undecided true goal | not mentioned | +0.10 on an exploratory event (half of the goal half). | `sim:539-540` | **differs** (OQ-CE-21) |
| B. Past events | +5 for 1–2, +10 for 3 or more | +0.10 for one or more. One tier. Counts every past event on the file row. | `sim:478`, `:482`, `:551-552`; `api/exercise_results_models.py:206` | **differs** |
| B. Same major | +5 | +0.04, for a major in the event's target majors. | `sim:479`, `:553-554` | **differs** |
| B. Cap | not mentioned | Clamped to 0–1 after chance. | `sim:574` | OQ-CE-19 |
| C. Attend | flat 70% | flat 0.75 | `sim:481`, `:577-580` | **differs** |
| Chance, fixed per team | "a small element of luck, fixed for each team" | Two parts. (1) Every draw is a SHA-256 digest over seed, event key, profile number and purpose. (2) A band of up to 0.10 either way is added to each profile's chance. | `sim:503-518`, `:569-572`, `:480` | fixed per team **matches**; the size is OQ-CE-24 |
| Hidden truth for all 300 | true interests and true career goal | The same two hidden columns, for every profile. | `api/exercise_results_models.py:203-205` | **matches** |
| Card matches truth | "the card already matches their true interests" | True in the committed 300-row fixture: 70 of 70 cards equal the hidden columns, interests and goal. | data fact | **matches** |
| "Stopped responding" | not mentioned | Never signs up, in both panels. | `sim:565-566`; `api/exercise_results_run.py:312-313` | OQ-CE-28 |
| Write-up | Justin adds a short plain-words description | No write-up file exists. | — | **missing** |

One consequence of step A the table does not show. Today a profile on both the
team's list and "email everyone" has the same outcome in both
(`sim:129-132`, and `sim:657-659`). With two notice rates that stops being
true. A shared notice draw keeps a weaker form of it: anyone who notices the
mass email also notices the personal invitation (OQ-CE-26).

## 3. Delta against `main` and against PR #337

PR #337 (`chau-10-02-update-matching-algorithm`) is open and conflicts with
`main` on 2026-10-06. PR #342 sits on top of it and does not touch the rule.

| Quantity | `main` | PR #337 head | Ann's rule (R1) | Change from `main` | Change from #337 |
|---|---|---|---|---|---|
| Notice, list | none | none | 75% | new | new |
| Notice, email everyone | none | none | 15% | new | new |
| Start | 0.04 | 0.04 | 0.05 | +0.01 | +0.01 |
| Interests match | 0.20 | 0.20 | 0.35 | +0.15 | +0.15 |
| Goal fits | 0.20 | 0.20 | 0.15 | −0.05 | −0.05 |
| Undecided goal | 0.10 on an exploratory event | 0 | not mentioned | open (OQ-CE-21) | none, if 0 is right |
| Past events, 1–2 | 0.10 | 0.10 | 0.05 | −0.05 | −0.05 |
| Past events, 3 or more | 0.10 | 0.10 | 0.10 | none | none |
| Same major | 0.04 | 0.04 | 0.05 | +0.01 | +0.01 |
| Chance band | ±0.10 | ±0.10 | "small" | open (OQ-CE-24) | open |
| Attend | 0.75 | 0.75 | 0.70 | −0.05 | −0.05 |

What PR #337 does to the rule: it deletes the undecided branch
(`sim:539-540`), `SimulationProfile.career_goal_undecided` and
`SimulationEvent.exploratory`. It changes no coefficient.
`tests/unit/test_exercise_coefficients_approved.py` is not in its diff. It
moves five rows of the pinned sample result.

**Ordering.** Implement R1 on top of PR #337, not beside it. Both rewrite the
rule's plain-words paragraph (`sim:12-27`), the test that pins it
(`tests/unit/test_exercise_simulation.py`), and the pinned sample result. Two
branches doing that at once will conflict in all three.

PR #337 also changes how lists are built (interest yes/no, related past
events at 0 / 0.5 / 1). The numbers in §5 use `main`'s matching. They will
shift a little on #337's head. The rule's numbers will not.

## 4. Downstream areas

**Must change** = cannot stay as it is if R1 is implemented.
**Must re-verify** = may hold, but has to be checked against the new numbers.
**Unaffected** = no change expected.

| # | Area | Rating | Why | Seam |
|---|---|---|---|---|
| 1 | The rule itself | **must change** | New notice step, new numbers, a second past-events tier. | `sim:475-484`, `:544-581` |
| 2 | "Email everyone" panel | **must change** | Needs its own notice rate. It can no longer be "the same rule and seed over everybody". | `sim:647-661`; `api/exercise_results_run.py:331`; design spec §10 |
| 3 | Issue #295 / OQ-OCT14-01 (per-team or class-wide baseline) | **must re-verify** | New information: at 15% the baseline is about 8 sign-ups with a spread of about 2.8. Team-to-team differences become a larger share of the number than at today's 46 ± 5.9. | OQ-CE-30 |
| 4 | Refresh and "asking for more" shares (30 / 55 / 80, 15) | **unaffected** by the text; **must re-verify** the effect | Ann's rule does not mention them. They never fed the outcome directly, except "stopped responding". | `domain/exercise/asking.py:80-92`; `api/exercise_results_refresh.py:126` |
| 5 | "Stopped responding" under "required" | **must re-verify** | Today these profiles never sign up. Under R1 the question is whether that means "never notices", and whether it applies to "email everyone" too. | `sim:565-566`; OQ-CE-28 |
| 6 | Round two does noticeably better after "small reward" or "required" (Ann's checklist of 2026-10-02) | **must re-verify** | The expected gain is small under both rules (§5.5). No test asserts the direction. | OQ-CE-28 |
| 7 | Harbor round and the three-way comparison (list, email everyone, round one) | **must re-verify** | Same code path as round one. At Harbor the mass email is expected to beat two of the three reference lists (§5.3). | `web/ResultPanels.tsx:49-58` |
| 8 | Seat arithmetic (60, 8, 30) | **unaffected** | The constants and `seats_empty` do not change. | `sim:221`, `:225`, `:664-676` |
| 9 | Whether the 8 attend for certain | **must re-verify** | Today they are certain. Ann's "a flat 70% show up" is about those who sign up after an invitation. | OQ-CE-25; D8 |
| 10 | Result panels and the seat sentences | **unaffected** | Counts only. No sentence states a rate. | `web/ResultPanels.tsx`; `web/ExerciseResults.tsx:212` |
| 11 | Copy that describes the rule to a participant | **unaffected** | None exists. No screen, help text or tutorial explains the rule. DESIGN.md §11.1 holds no such sentence. | — |
| 12 | The rule's plain-words paragraph (what Ann and Dr. Lin receive) | **must change** | It states 4, 40, 10, 4, 10 and 75. A test checks each number against the code. | `sim:12-27`; `tests/unit/test_exercise_simulation.py` |
| 13 | Justin's one-page write-up | **must change** (to be written) | Ann asked for the rule to be added. No file exists. | requirements, "Justin", item 2 |
| 14 | Approved-coefficients pin | **must change** | It pins D7's eight values and the words "Chau approved". | `tests/unit/test_exercise_coefficients_approved.py:56-65` |
| 15 | Pinned sample result and its document | **must change** | Six pinned rows; the document is compared with them. | `tests/golden/exercise/test_exercise_results_rule_sample_golden.py:138-145`; `docs/archive/plans/open-questions/oq-ce-03-sample-result.md` |
| 16 | Simulation golden (test-only numbers) | **must change** if the coefficient set gains fields | It builds its own set, in the test and in a subprocess source string. A new draw moves its pinned tuples. | `tests/golden/exercise/test_exercise_simulation_golden.py` |
| 17 | Router and integration tests that recompute the rule | **must re-verify** | They assert structure and "same seed" equality, not exact counts. The "same seed for both panels" test inverts. | `tests/unit/exercise_results_router/test_exercise_results_panels.py:81-98`; `tests/integration/test_exercise_full_class_run.py` |
| 18 | Response contract (no score / percent / confidence / probability / likelihood / share; no hidden column) | **unaffected**, with one caution | R1 adds no response field. A new coefficient must not surface in a response model, and a field must not be named `notice_share` or similar. | `tests/unit/exercise_results_router/test_exercise_results_contract.py:119` |
| 19 | Hidden columns never build a list | **unaffected** | R1 uses them for outcomes only. The readers stay two: the rule, and the refresh's card copy. | `api/exercise_results_models.py:203-205`; `python/smartmatch_persistence/smartmatch_persistence/exercise/results_cards.py:114-122` |
| 20 | Determinism | **must re-verify** | A notice draw is one more purpose in the same digest. Fixed per team holds by construction. | `sim:503-518` |
| 21 | Seed kept on clear (#331, PR #344) | **unaffected** | Independent. PR #344 is open; `main` still draws a new seed on clear. | `python/smartmatch_persistence/smartmatch_persistence/exercise/workspace_repository.py:546` |
| 22 | Documents that state D7's numbers | **must change** | Design spec §10 and §11, the D7 row, the requirements table, the sample result. | listed in §6 |
| 23 | Requirements: "no team can fill the room by invitations alone" | **unaffected** | Still true: the best possible list adds about 8 to 9 attendees. | requirements, "Why the rule…" |

## 5. Sanity numbers

### 5.1 How they were computed

- **Data.** The committed fixture
  `tests/fixtures/exercise/SmartMatch_Student_Body_300.xlsx`, read through
  the production ingest and the production ranker. No live system was run.
- **Method.** Expected values, by arithmetic over each profile's chance. No
  random draws, except to pick who attended round one in §5.5.
- **"Spread"** is one standard deviation across teams.
- **The scripts** are scratch files, not committed.

Assumptions made where Ann's text is silent. Each is an open question.

| # | Assumption | Row |
|---|---|---|
| 1 | The additions are percentage points. The most a profile can reach is 5 + 35 + 15 + 10 + 5 = 70, so a cap never applies. | OQ-CE-19 |
| 2 | "Interests match" = any one true interest is one of the event's topics. | OQ-CE-20 |
| 3 | "Goal fits" = the topic the true goal points at is one of the event's topics. An undecided goal earns 0. | OQ-CE-21 |
| 4 | "Past events" = every past event on the file row. | OQ-CE-22 |
| 5 | "Same major" = the event's target major. | OQ-CE-23 |
| 6 | No extra band of luck: each chance is exactly as Ann wrote it. | OQ-CE-24 |
| 7 | "Email everyone" reaches all 300 at 15%, the team's own 30 included. | OQ-CE-26 |
| 8 | The 8 already signed up attend for certain. | OQ-CE-25 |

What the fixture holds, against the facts Ann gave on 2026-10-02:

| Fact | Northline | Harbor |
|---|---|---|
| Truly interested (Ann) | 78 | 92 |
| Truly interested (fixture, assumption 2) | 79 | 92 |
| Of those, in the target major (Ann / fixture) | 19 / 19 | 20 / 20 |
| In the target major, all 300 (fixture) | 26 | 70 |
| True goal fits (fixture) | 15 | 28 |
| Past events, all 300 (fixture) | 200 with none, 81 with 1–2, 19 with 3 or more | the same |

The fixture counts 79 where Ann wrote 78. The one-profile difference is not
explained. It moves no number below by more than 0.1.

### 5.2 One profile at a time

Ann's rule. "List" = 0.75 × step B. "Email" = 0.15 × step B. Attend = × 0.70.

| Profile | Step B | Signs up, on the list | Signs up, by mass email | Attends, on the list |
|---|---|---|---|---|
| Interests + goal + same major + 3 or more past events | 5+35+15+5+10 = 70% | 0.75 × 0.70 = 52.5% | 0.15 × 0.70 = 10.5% | 36.8% |
| Interests + goal | 5+35+15 = 55% | 41.3% | 8.3% | 28.9% |
| Interests + same major | 5+35+5 = 45% | 33.8% | 6.8% | 23.6% |
| Interests only | 5+35 = 40% | 30.0% | 6.0% | 21.0% |
| Same major only | 5+5 = 10% | 7.5% | 1.5% | 5.3% |
| 1–2 past events only | 5+5 = 10% | 7.5% | 1.5% | 5.3% |
| No match at all | 5% | 0.75 × 0.05 = 3.8% | 0.15 × 0.05 = 0.8% | 2.6% |

The same profiles under today's rule (before the ±0.10 band; no notice step,
so the list and the mass email give the same chance):

| Profile | Today |
|---|---|
| Interests + goal + same major + past events | 0.04+0.40+0.04+0.10 = 58% |
| Interests + goal | 44% |
| Interests + same major | 28% |
| Interests only | 24% |
| Same major only | 8% |
| Past events only | 14% |
| No match at all | 4% (4.9% on average, because the band is cut off at 0) |

### 5.3 A list of 30

Two made-up lists first, to show the arithmetic.

- **Strong list:** 30 truly interested; 10 of them also fit on goal, 10 are in
  the target major, 10 have 1–2 past events.
  Points: 30 × 40 + 10 × 15 + 10 × 5 + 10 × 5 = 1,450, so 14.5 would sign up
  if all noticed. × 0.75 = **10.9 sign-ups**. × 0.70 = **7.6 attend**.
  Today: 30 × 0.24 + 10 × 0.20 + 10 × 0.04 + 10 × 0.10 = 10.6 sign-ups,
  8.0 attend.
- **Weak list:** 30 in the target major, none truly interested, 10 with 1–2
  past events.
  Points: 30 × 10 + 10 × 5 = 350, so 3.5. × 0.75 = **2.6 sign-ups**.
  × 0.70 = **1.8 attend**.
  Today: 30 × 0.08 + 10 × 0.10 = 3.4 sign-ups, 2.6 attend.

Real lists on Ann's 300, expected sign-ups / attendees, with the spread of
sign-ups in brackets:

| List of 30 | Northline, today | Northline, Ann's rule | Harbor, today | Harbor, Ann's rule |
|---|---|---|---|---|
| Equal weights (the app's suggestion) | 9.2 / 6.9 | 9.0 / 6.3 (2.4) | 7.6 / 5.7 | 6.7 / 4.7 (2.1) |
| "Said they are interested" only | 6.7 / 5.1 | 6.3 / 4.4 (2.1) | 9.0 / 6.8 | 8.9 / 6.2 (2.4) |
| "Same major" only | 8.0 / 6.0 | 7.9 / 5.5 (2.3) | 7.2 / 5.4 | 6.0 / 4.2 (2.0) |
| Best possible (picked with the hidden truth) | 13.0 / 9.7 | 11.9 / 8.4 (2.7) | 14.7 / 11.0 | 13.2 / 9.2 (2.7) |
| Worst possible | 1.8 / 1.4 | 1.1 / 0.8 (1.0) | 1.6 / 1.2 | 1.1 / 0.8 (1.0) |
| An average 30 (the class average × 30) | 4.6 | 3.9 | 5.3 | 4.6 |

"Today" in this table is the expected value of today's rule. It agrees with
the pinned sample result's 1,000-team averages (9.5, 6.8, 8.1 and 7.5, 8.9,
7.1) to within 0.3.

Under Ann's rule the size stays close to her example of "8 signed up, 6
attended" at Northline, and falls a little at Harbor.

### 5.4 Emailing all 300

Ann's rule, by hand.

- **Northline.** Points: 300 × 5 + 79 × 35 + 15 × 15 + 26 × 5 + 81 × 5 +
  19 × 10 = 1,500 + 2,765 + 225 + 130 + 405 + 190 = 5,215. So 52.2 would
  sign up if all noticed. × 0.15 = **7.8 sign-ups**. × 0.70 = **5.5 attend**.
  With only Ann's own facts (78 interested; nothing else known):
  300 × 5 + 78 × 35 = 4,230, × 0.15 = 6.3 sign-ups at least.
- **Harbor.** Points: 1,500 + 92 × 35 + 28 × 15 + 70 × 5 + 405 + 190 = 6,085.
  × 0.15 = **9.1 sign-ups**. × 0.70 = **6.4 attend**.

| "Email everyone" | Northline | Harbor |
|---|---|---|
| Today: sign-ups / attendees | 46.1 / 34.6 (spread 5.9) | 52.8 / 39.6 (spread 6.1) |
| Ann's rule: sign-ups / attendees | 7.8 / 5.5 (spread 2.7) | 9.1 / 6.4 (spread 2.9) |
| Ann's rule, if the team's own 30 notice at 75% (OQ-CE-26; equal-weights list) | 15.1 / 10.5 | 14.5 / 10.1 |

**Does a targeted 30 beat the mass email?** By rate, always: 30 invitations
against 300. By count, not reliably.

- The break-even is exact. 30 × 0.75 = 22.5 "noticed" on a list; 300 × 0.15 =
  45 by mass email. A list wins on expected sign-ups only when its people are,
  on average, **more than twice as likely to sign up as the class average**.
  The class average is 17.4% at Northline and 20.3% at Harbor, so a list
  needs an average above 34.8% and 40.6%.
- The equal-weights list averages 40.2% at Northline (wins, narrowly) and
  29.6% at Harbor (loses).

How often the mass email draws at least as many sign-ups as the list, for one
team (the two treated as independent draws):

| List of 30 | Northline | Harbor |
|---|---|---|
| Equal weights | 42% | 79% |
| "Said they are interested" only | 72% | 57% |
| "Same major" only | 54% | 85% |
| Best possible | 17% | 19% |

So: **yes, "email everyone" can out-draw a good list of 30 in absolute
sign-ups under these numbers.** At Harbor it is the likely outcome for two of
the three reference lists. Even the best possible list loses or ties about
one time in five.

**Does that fill the 60 seats?** No. 8 + 5.5 = 13.5 at Northline and
8 + 6.4 = 14.4 at Harbor. The chance of 20 or more attendees from the mass
email is below 1 in 100,000. The best possible list reaches about 16 to 17.
(Today the mass email reaches about 43 to 48 of 60.)

This is OQ-CE-31, for Ann. Two readings are both reasonable: the lesson is
about the rate (30 well-chosen invitations do the work of 300 emails), or the
count should favour the list. The team does not pick one.

### 5.5 Round two after a refresh

Under Ann's rule the outcome reads only the hidden truth, the past-event
count on the file row, the major, and "stopped responding". A card does not
change anyone's chance. **So a refresh can change results only by helping the
team build a better Harbor list.** That is how the code works today too
(`api/exercise_results_models.py:186-190`, `:203-207`).

What limits the gain: the refresh gives cards only to people the team invited
in round one who had none (`api/exercise_results_refresh.py:126`). With an
equal-weights Northline list that is 21 of the 30, so 6, 12 or 17 new cards.
Only 10 of those 30 are truly interested in Harbor's topics.

Expected Harbor sign-ups, round-one list = equal weights at Northline,
averaged over 150 teams:

| Harbor list | Rule | No refresh | Better recommendations (6 cards) | Small reward (12) | Required (17) |
|---|---|---|---|---|---|
| Equal weights | today | 7.6 | 7.7 (+0.2) | 8.0 (+0.4) | 8.2 (+0.7) |
| Equal weights | Ann's | 6.7 | 6.8 (+0.2) | 7.1 (+0.5) | 7.4 (+0.8) |
| "Said they are interested" only | today | 9.0 | 9.6 (+0.6) | 10.1 (+1.0) | 10.4 (+1.4) |
| "Said they are interested" only | Ann's | 8.9 | 9.5 (+0.6) | 10.1 (+1.2) | 10.5 (+1.6) |

1. **The order holds:** promise < reward < required, under both rules.
2. **The size is small.** The gain is 0.2 to 1.6 sign-ups. One team's spread
   is about 2.1 to 2.4. A single team will often see no improvement, or a
   worse round two, by luck alone. Ann's checklist of 2026-10-02 says "If
   every team gets about the same, the lesson doesn't show."
3. **Ann's rule does not cause this.** The gains are about the same today.
4. **"Required" showed no cost in these runs.** The profiles that stop
   responding are people from the Northline list without a card, mostly CIS
   majors. In 150 teams none of them landed on a Harbor reference list. The
   cost appears only if a team invites the same people twice. This is how
   the app behaves today, on these reference lists; other weights may differ.
5. **Round one and round two are different events.** A team that compares its
   Harbor result with its Northline result is also comparing two different
   crowds.

## 6. What would have to change

Estimates are for one person who knows the module. They assume PR #337 has
merged first, and that the recommended defaults of OQ-CE-19 to OQ-CE-30 are
accepted. Nothing here is authorised by this document.

### Before the board demo, Thursday 2026-10-08

| # | Change | Hours |
|---|---|---|
| 1 | **No rule change in code.** Two days is not enough to change the rule, regenerate the sample result and re-verify it on the demo site, and the demo is about the front end. | 0 |
| 2 | Send Ann the three questions that most change the numbers: OQ-CE-24, OQ-CE-26, OQ-CE-31. | 0.5 |
| 3 | Presenters know that the results screen still runs the 2026-09-25 numbers, in case the board asks how results are decided. | 0.25 |

### Before Ann's run-through, Friday 2026-10-16

In order. Each step leaves the tests green.

| # | Change | Where | Hours |
|---|---|---|---|
| 1 | Coefficient set: two notice rates, an interests lift and a goal lift in place of the split, two past-event tiers, new values. Keep the "true fit is the largest lift" check. | `sim:365-484` | 3 |
| 2 | The rule: a notice draw (a new purpose in the digest) before sign-up; the two tiers; the band of luck per OQ-CE-24. | `sim:521-581` | 3 |
| 3 | "Email everyone" takes the mass-email notice rate; the team's run takes the list rate. | `sim:608-661`; `api/exercise_results_run.py:289-345` | 2 |
| 4 | The plain-words paragraph and the rest of the module docstring, with the test that checks each number. | `sim:1-182`; `tests/unit/test_exercise_simulation.py` | 2 |
| 5 | Unit tests: notice step, tiers, the two rates, superset property if a shared notice draw is chosen, determinism in a fresh process. | `tests/unit/test_exercise_simulation.py` | 4 |
| 6 | Approved-coefficients pin: the new set, and who approved it (Ann). | `tests/unit/test_exercise_coefficients_approved.py` | 1 |
| 7 | Golden files: the test-only set and its subprocess source; regenerate the pinned sample result and its document. | `tests/golden/exercise/test_exercise_simulation_golden.py`; `…results_rule_sample_golden.py`; `oq-ce-03-sample-result.md` (or a new dated sample) | 3 |
| 8 | Router and integration tests that assume one rule for both panels. | `tests/unit/exercise_results_router/test_exercise_results_panels.py:81-98`; `tests/integration/exercise_class_driver.py`; `test_exercise_full_class_run.py` | 3 |
| 9 | Documents: design spec §10 and §11; D7 note; requirements status table; this register's rows closed. | `docs/` | 2 |
| 10 | Run both rounds on the demo site with six teams; record sign-ups against "email everyone" for Ann. | demo site | 2 |
| 11 | Justin: the plain-words description in the one-page write-up. | new file, location to be agreed | 2 |
| | **Total** | | **27** |

### Later

| # | Change | Hours |
|---|---|---|
| 1 | Issue #295: per-team or class-wide "email everyone" (OQ-CE-30). | 8 |
| 2 | If Ann answers OQ-CE-28 with a new mechanism for round two, design it. | not estimated |
| 3 | Retire D7's sample document to history once the new sample is approved. | 0.5 |

## 7. Risks

1. **The lesson may not show at Harbor.** The mass email is expected to match
   or beat the suggested list for about 4 teams in 5 (§5.4). If Ann wants the
   count to favour the list, the numbers have to change, and only she can
   change them.
2. **Round two may not look better.** Small expected gain, larger luck
   (§5.5). Not new, but Ann's checklist expects it to show.
3. **Guessing the luck.** If the ±0.10 band stays, a profile at 5% ranges
   from 0 to 15%, and its average rises because the band is cut off at 0.
   That quietly changes Ann's numbers (OQ-CE-24).
4. **Three branches rewriting one paragraph.** PR #337, PR #344 and an R1
   implementation all touch the rule's documents; #337 and R1 both touch
   `simulation.py`. Merge #337 first.
5. **Stale approval wording.** The code and a test say "Chau approved" the
   numbers. Under R1 the numbers are Ann's. Leaving the words would misstate
   who decided.
6. **Changing the rule days before a demo.** A regenerated sample that nobody
   has looked at is worse than the approved one. Hence "no rule change before
   Thursday".
7. **Six days to the run-through.** 27 hours of work depends on answers to
   OQ-CE-24 and OQ-CE-26 at least. If they do not arrive, the recommended
   defaults are the fallback, recorded as defaults taken.

## 8. Demo-readiness note (board, Thursday 2026-10-08)

- **The constraint.** About 15 minutes of demo, front end first, not the back
  end. Then about 15 minutes of questions.
- **What that means for this ruling.** Nothing on any screen states a rate or
  explains the rule (§4, row 11). The results screen shows counts. Changing
  the rule would change the counts and no wording. The demo does not need R1.
- **What to have ready.** One sentence, if asked how results are decided:
  the app uses each made-up student's true interests, which it never shows,
  plus a fixed element of chance per team. That is true of both the current
  rule and Ann's.
- **What not to do.** Do not change the rule, the seed handling or the sample
  result on the demo site between now and Thursday.

## 9. What was not verified

1. Ann's send date and channel. Recorded as "relayed 2026-10-06".
2. The 78 / 79 difference at Northline (§5.1).
3. Every number in §5 on PR #337's head. They use `main`'s matching.
4. The independence assumed in the "how often" table (§5.4). In the app the
   two panels share a seed, so the true figures will differ somewhat.
5. Nothing was run on the demo site or against a database.
6. `docs/10-2-2026/` is not on `main`. Its text was read from the owner's
   checkout and is quoted, not linked.
