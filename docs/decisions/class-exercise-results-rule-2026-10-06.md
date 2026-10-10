# Class exercise: the results rule, as Ann ruled it (relayed 2026-10-06)

**Status:** Ruling recorded. **Not implemented.** The code on `main` still runs
the numbers of decision D7 (2026-09-25). This file changes no code, no test,
no fixture and no coefficient.
**Recorded:** 2026-10-06, by the team, for Danny (owner) and Chau.
**Decided by:** Ann Wang (owner of the scope). Relayed by the owner on
2026-10-06. Ann's own send date was not given.
**Scope:** `ProductScope.CLASS_EXERCISE` only.
**Code references:** `origin/main` at `783a1244`.
**Verbatim text:** [`stakeholder-correspondence-2026-09.md`, exchange D](stakeholder-correspondence-2026-09.md#d-chaus-question-and-ann-wangs-results-rule).
**Requirement:** [`class-exercise-requirements.md`, "The results rule (Ann, relayed 2026-10-06)"](../product/class-exercise-requirements.md#the-results-rule-ann-relayed-2026-10-06).
**Impact analysis:** [`2026-10-06-results-rule-impact-analysis.md`](../plans/2026-10-06-results-rule-impact-analysis.md).
**Open questions it raises:** OQ-CE-19 to OQ-CE-31 in the
[register](../plans/open-questions/class-exercise-open-questions.md).
**Earlier record:** [`class-exercise-decisions-2026-09-25.md`](class-exercise-decisions-2026-09-25.md)
(D1–D16).

Paths are shortened as in the earlier record:

- `domain/` = `python/smartmatch_domain/smartmatch_domain/`
- `api/` = `services/api/smartmatch_api/`

---

# Part 1 — In plain words (for Chau and Ann)

## The question

Chau asked how the app decides who among the 30 invited people signs up, and
who of those attends.

## The rule Ann gave

| Step | What it decides | Ann's numbers |
|---|---|---|
| A | Did the person notice the invitation? | The team's list of 30: 75%. "Email everyone" (all 300): 15%. |
| B | If they noticed, do they sign up? | Start at 5%. Add +35 if their true interests match the event (the main driver). Add +15 if their true career goal fits the event. Add +5 for 1–2 past events, +10 for 3 or more. Add +5 for the same major. |
| C | Of those who sign up, who attends? | A flat 70%. |
| Chance | Luck | A small element of luck, fixed for each team, so the same list always gives the same result. |

Ann also ruled three things about how the rule is applied:

1. Sign-up uses each student's **true interests and true career goal** (the
   hidden columns). So the rule works for all 300 students, with or without a
   card.
2. For students who have a card, the card already matches their true
   interests, so nothing conflicts.
3. Justin adds a short plain-words description of this rule to the one-page
   write-up.

## What this changes

- The app has no "did they notice" step today. It is new.
- "Email everyone" runs the same rule as the team's list today. Under the
  ruling it is noticed five times less often.
- Six of the eight numbers approved on 2026-09-25 (D7) get a new value, and
  the past-events lift gets a second tier.

## What is still open

Thirteen questions an implementer would otherwise have to guess: OQ-CE-19 to
OQ-CE-31. Three matter most:

1. **OQ-CE-24** — how big the "small element of luck" is. Today it moves each
   person's chance by up to 10 in 100 either way.
2. **OQ-CE-26** — whether "email everyone" reaches the team's own 30 at 15% or
   at 75%.
3. **OQ-CE-31** — whether Ann is content that "email everyone" draws about as
   many sign-ups as a typical list of 30 (see the impact analysis, §5).

---

# Part 2 — The decision in full (for the builders)

## R1. The results rule has three steps and a fixed chance

- **Question.** How is it decided who signs up and who attends? (Chau to Ann;
  the earlier answer was OQ-CE-03 / D7.)
- **Options.** (a) Keep D7's two-step rule and its numbers. (b) Ann's
  three-step rule with her numbers.
- **Decision.** (b), as Ann wrote it. The table in Part 1 is the whole of it.
- **Approved.** Ann Wang, relayed by the owner 2026-10-06.
- **Why.** Ann's reason for step A, in her words: "A personal invite from the
  team is noticed far more often than a mass email."
- **Affects.** Every results run, the "email everyone" panel, the sample
  result, the rule's plain-words paragraph, and Justin's write-up.
- **Code today.** Nothing below is changed by this record.
  - `domain/exercise/simulation.py:475-484` `EXERCISE_SIMULATION_COEFFICIENTS`
    (D7's numbers)
  - `:558-581` `_outcome` — three draws per profile (chance, sign up,
    attend); none is a notice draw
  - `:647-661` `run_email_everyone` — the same rule, the same seed, no
    separate rate
  - `tests/unit/test_exercise_coefficients_approved.py:56-65` pins D7's set

## What R1 supersedes

Each row is superseded **as the requirement**. The code keeps the old value
until an implementation PR lands.

| Quantity | D7 (2026-09-25), in code today | R1 (Ann, relayed 2026-10-06) |
|---|---|---|
| Notice step | none; every invited profile is treated as having noticed | 75% for the team's list, 15% for "email everyone" |
| Starting chance | 0.04 (`base_signup_rate`) | 5% |
| True interests match | 0.20 (half of `true_fit_lift` 0.40) | +35 |
| True career goal fits | 0.20 (the other half) | +15 |
| Past events | +0.10 for one or more (`frequent_attender_events` = 1) | +5 for 1–2, +10 for 3 or more |
| Same major | +0.04 (`same_major_lift`) | +5 |
| Show-up | 0.75 (`attend_given_signup`) | 70% |
| "Email everyone" | the same rule and seed as the team's list | the same rule with a 15% notice rate |

Also superseded:

1. **D7's "Why".** "An equal-weights top-30 list lands near Ann's example of
   about 8 sign-ups and 6 attendees (typical team: 9.5 / 7.1 at Northline,
   7.5 / 5.6 at Harbor)." Those figures belong to D7's numbers. The impact
   analysis, §5, gives the figures under R1.
2. **The sample result** in
   [`oq-ce-03-sample-result.md`](../archive/plans/open-questions/oq-ce-03-sample-result.md).
   Its tables are D7's numbers.
3. **The delegation of the numbers.** On 2026-09-25 Ann answered in words and
   left the numbers to Chau. Ann has now given the numbers herself.

## What R1 leaves standing

1. **Hidden truth decides outcomes, never the list.** The rule reads
   `hidden_true_interests` and `hidden_true_career_goal`
   (`api/routers/exercise_results_models.py:203-205`). The ranker never reads
   them. Ann's "use each student's true interests and true career goal (the
   hidden columns)" is what the code already does. ADR-0025 D6 and D6 of the
   earlier record stand.
2. **Chance is fixed per team.** The draws are a SHA-256 digest over the team's
   seed, the event key, the profile number and the purpose
   (`domain/exercise/simulation.py:503-518`; `domain/exercise/determinism.py`).
   The same list gives the same result.
3. **The order of the lifts.** True fit is the largest lift; past events and
   same major are smaller. The constructor's check
   (`simulation.py:429-440`) still holds for 35, 10 and 5.
4. **Seats.** 60 seats, 8 already signed up, 30 invitations (D8).
5. **"Asking for more".** 30 / 55 / 80 percent, 15 percent stop responding
   under "required", halves round up (OQ-CE-04, D12). Ann's text does not
   mention them.
6. **A card copied by the refresh** carries the hidden true interests and goal
   (D6).
7. **The response contract.** No response model carries a field named like
   score, percent, confidence, probability, likelihood or share, and no
   hidden column is shown (ADR-0025 D6, D8). Ann's percentages are rule
   inputs. They do not reach a class participant's screen.

## What R1 does not answer

Each is a register row with options and a recommended default. None is decided
here.

| Row | Gap |
|---|---|
| OQ-CE-19 | Are the Step B additions percentage points, capped at 100? Is 5% the floor for everyone who noticed? |
| OQ-CE-20 | What "true interests match the event" means with several interests or several event topics. |
| OQ-CE-21 | What "career goal fits" means, and what an undecided true goal earns. |
| OQ-CE-22 | Whether "past events" means any past events or related ones, and whether refresh-added topics count. |
| OQ-CE-23 | Whether "same major" means the event's target major. |
| OQ-CE-24 | How large "a small element of luck" is: a change to each person's chance, or only the fixed draw. |
| OQ-CE-25 | Whether the 8 already signed up attend for certain or at 70%. |
| OQ-CE-26 | Whether "email everyone" reaches the team's own 30 at 15% or at 75%. |
| OQ-CE-27 | Whether the notice step is drawn again in round two. |
| OQ-CE-28 | What round two can still improve, and how "stopped responding" sits with the notice step. |
| OQ-CE-29 | Whether these numbers replace D7's approved set outright. |
| OQ-CE-30 | Whether the notice draw is per team or one class-wide draw (ties to issue #295). |
| OQ-CE-31 | Whether Ann accepts how close "email everyone" comes to a list of 30 under these numbers. |

## Relation to open pull requests

- **PR #337** (Chau, `chau-10-02-update-matching-algorithm`, open, in conflict
  with `main` on 2026-10-06). It changes one thing in the results rule: an
  undecided true career goal earns nothing from the career-goal part. It
  leaves D7's eight numbers as they are. R1 is silent on the undecided goal,
  so PR #337 and R1 do not conflict; R1's numbers would be a further change
  on top of it. See OQ-CE-21 (closed 2026-10-07, option a).
- **PR #342** (on top of #337). No change to the rule.
- **PR #344** (keep the seed when the instructor clears a team, #331). It
  serves Ann's "the same list always gives the same result". Not merged on
  2026-10-06: `reset_team` on `main` still draws a new seed
  (`python/smartmatch_persistence/smartmatch_persistence/exercise/workspace_repository.py:546`).
- **Update 2026-10-09.** #337 and #342 merged (as #351, 2026-10-07) and #344
  merged (2026-10-08): on `main` the undecided half is gone and clearing a team
  keeps its seed. R1 itself is still not implemented.

## Also in the same message

The dean wants the team to present to the CBACH advisory board on Thursday
2026-10-08: two presenters including Chau, a 30-minute slot between 1:00 and
4:30 pm, about 15 minutes of demo **focused on the front end, not the back
end**, then about 15 minutes of questions. It is recorded here as a date. Who
presents is for the people involved. The impact analysis carries the
demo-readiness note.
