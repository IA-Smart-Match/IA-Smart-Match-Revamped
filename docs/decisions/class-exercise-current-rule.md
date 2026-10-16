# Class exercise: the current rule (one page)

**Status:** current. This page states every number Ann Wang has ruled for the
class exercise as it stands today, and where each one lives in the code. It
decides nothing new; each row names its ruling. When a ruling changes, change
this page in the same PR.
**Read this first.** Everything older (the 2026-10-06 rule, D7, the impact
analysis, the 09-16 design spec §10-§11) is history; where it conflicts, this
page and the records it cites win.
**Code reference:** `origin/main` @ `97445df3` (#398 merged 2026-10-12).

## The results rule (who signs up, who shows up)

Every one of the 300 gets CPP's usual mass email. The team's 30 also get a
personal CBACH email. For each person, in order:

| Step | Rule | Ruled by | Code |
|---|---|---|---|
| 1. Notice | Mass email 20 in 100 (all 300). CBACH email 60 in 100 (the team's 30 only). Both: about 68 in 100 notice at least one | Ann Wang, email 2026-10-10, Q2 | `simulation.py:482-483,585-586` |
| 2. Sign up (Step B) | Start at 5. +35 if the hidden true interests match the event. +15 if the hidden true career goal fits. +5 for 1–2 past events, +10 for 3 or more (**any** past event on the file row; refresh-added topics never count). +5 if the event targets the student's major. Points are added; the most anyone can reach is 70; 5 is the floor | Ann Wang 2026-10-06 Step B, kept by the owner ruling of 2026-10-12; past-event points and "any past event" ruled by Ann Wang, second reply 2026-10-15 ([record](class-exercise-ann-reply-2026-10-15.md)) | `simulation.py:477-489,540-559`; `exercise_results_models.py:205` |
| 3. Show up | 65 in 100 of sign-ups | Ann Wang, email 2026-10-10, Q2 and Q4 | `simulation.py:484,593` |
| 3b. The 8 pre-registered | Each of the 8 attends at 65 in 100 too, from a fixed draw (team seed + event), the same in the mass-only and the team run. Seats open = 60 - (the 8 who came) - everyone else who attended | Ann Wang 2026-10-15, Q2 | `simulation.py` `existing_attended`, `seats_empty` |
| Luck | None. Each team's fixed chance draw alone decides; same list, same result | Ann Wang, email 2026-10-10, Q4 | `simulation.py:508-523` (5 draws only) |
| Baseline | Mass email alone, run on the team's own draw (same seed as the team's run) | Ann Wang, email 2026-10-10, Q1 | `exercise_results.py:268`; `exercise_results_run.py:321,331` |

Undecided and Graduate-school career goals earn 0 on every event, in matching
and in results. Graduate school fits no event topic (Ann confirmed D2,
2026-09-25); Undecided earns nothing (Ann Wang, 2026-10-02 and 2026-10-07). Sign-up reads only the hidden true
columns, for all 300, card or not. Students who stopped responding never sign
up and notice nothing, mass email included (Ann Wang, reply 2026-10-15, Q3).

**Not superseded:** Step B. From Ann's 2026-10-06 message only Step B
survives. Its Step A (notice 75 / 15), Step C (flat 70% show-up) and the
"small element of luck" are replaced by the 2026-10-10 email.

## What the team sees

- Lift line, verbatim: "Mass email alone: N sign-ups. With your 30 CBACH
  emails: M. Your list added K." (Ann Wang, email 2026-10-10, Q2;
  `ResultPanels.tsx:214-218`).
- Debrief line, verbatim: "Each team's numbers include its own luck. Look at
  your gap over the mass email, not just the raw number." (Q1;
  `ResultPanels.tsx:225`).
- Seats: 60 seats, 8 already signed up before any invitation. The 8 attend at
  the 65% show-up rate (Ann Wang, reply 2026-10-15, Q2). Seats still open =
  60 − (how many of the 8 came) − (everyone who attended from the mass email
  **or** the team's list). The
  lift line uses sign-ups; the seats sentence and the round-one recap use
  attendance. "Already coming" = how many of the 8 came plus the mass email's attendees; "Your
  invitations added" = the team's attendees the mass email missed.
  (`simulation.py:232,236,680-693`; `exercise_results_run.py:382-385`;
  `ResultPanels.tsx:207-211`). Example: "15 were already coming. Your
  invitations added 4. 41 seats are still open."

## Check numbers (Oct 2 file, suggested 30 at 3/3/2/2, mean of 5,000 seeds)

| Event | Mass email alone (N) | List adds (K) | With list (M) | Ann expected |
|---|---|---|---|---|
| Northline | 10.48 | 6.22 | 16.70 | about 6 |
| Harbor | 12.10 | 5.05 | 17.15 | 4-5 |

Pinned per seed by `tests/golden/exercise/test_exercise_ann_check_numbers_golden.py`
([record](class-exercise-ann-reply-2026-10-15.md)). The older 1,000-seed table
(6.4 / 5.1) is in [`class-exercise-results-rule-2026-10-10.md`](class-exercise-results-rule-2026-10-10.md).

## Matching (building the list)

| Value | Rule | Ruled by | Code |
|---|---|---|---|
| Weights | Four dials, whole steps 0-10; defaults 3 / 3 / 2 / 2 (major, stated interest, career goal, past events); all-zero refused. Copy: "a factor set to 6 counts twice as much as one set to 3" | Ann Wang 2026-10-06, reconfirmed 2026-10-10 Part 2 ([record](class-exercise-default-weights-2026-10-06.md)) | `registry.py:142-146,363-371`; `WeightsControls.tsx:48-49` |
| Stated interest | Any match = full credit | Ann Wang 2026-10-02 ([record](class-exercise-factor-revisions-2026-10-02.md)) | `student_factors/factors.py:122-147` |
| Past events (matching factor) | 0 / 0.5 / 1 for 0 / 1 / 2+ **related** past events | Ann 2026-10-02; "ok" 2026-10-10 Part 2 | `student_factors/factors.py:15,76` |
| Ties | More information on file first, then seniors first, then the file's fixed order | OQ-CE-01, D-rulings 2026-09-24/25 | `vocabulary.py:86-93` |
| List size | Top 30; the instructor can lower the limit (e.g. 25) | Requirements; Ann's checklist | `matching.py:489,509-518` |
| Hidden columns | Never shown on screen, in the list, the CSV or any response | ADR-0025 D6 | `exercise/__init__.py:39-43` |

Note the two different "past events": the matching factor counts **related**
events (0 / 0.5 / 1); the sign-up rule counts **any** past events (+5 for 1–2, +10 for 3 or more).

## Asking for more, and the refresh

| Way of asking | Share of invited students without a card who complete one |
|---|---|
| Better recommendations | 30% |
| Small reward | 55% |
| Required | 80%, and 15% stop responding (drawn only from those without a card) |

Counts round half up. Choice once per team, only after round-one results.
Refresh once per team (two presses). Ruled by Ann Wang 2026-09-25 (OQ-CE-04);
code `asking.py:82-84,92,191-203`.

## Still open (to confirm with Ann)

- OQ-CE-20 (several true interests), OQ-CE-23 (same major = event's target
  majors), OQ-CE-27 (notice drawn per event). The code runs the recommended
  default (a) for each.
- OQ-CE-28 first half (round two improves only through a better list): no reply.
- Register: [`class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md).

Paths: `simulation.py`, `asking.py`, `registry.py`, `matching.py`,
`vocabulary.py` are under `python/smartmatch_domain/smartmatch_domain/exercise/`;
`factors.py` under `.../student_factors/`; `exercise_results*.py` under
`services/api/smartmatch_api/routers/`; `*.tsx` under
`apps/web/legacy-frontend/src/app/pages/exercise/`.
