# Class exercise factor revisions decision

**Status:** Accepted  
**Date:** 2026-10-02 (Ann Wang's revisions); rulings on scope 2026-10-04 and 2026-10-05 (Chau)

**Source:** Ann Wang, *SmartMatch Progress and Revisions*, 2026-10-02
(`SmartMatch_Progress_and_Revisions_10022026.docx`; not stored in this
repository).
**Supersedes:** D2's "Undecided at half credit" in
[`class-exercise-decisions-2026-09-25.md`](class-exercise-decisions-2026-09-25.md),
and with it the implemented half of OQ-CE-14.
**Scope:** `ProductScope.CLASS_EXERCISE` only.

## Decision

Three things change in how the class exercise ranks profiles for an event. The
factor keys, Ann's labels, the equal default weights, the composition (an
unknown factor contributes nothing and its weight is not re-spread), the
tie-break, the markers and the reason sentences do not change.

**"Said they are interested in this topic" is yes or no.** The factor is 1 when
any interest on the profile card is one of the event's topics, and 0 when none
is. It was the Jaccard overlap of the two lists, so a card sharing one of three
distinct terms earned a third. A profile with no card stays unknown, not 0.
Approved by Ann Wang, 2026-10-02.

**"Went to similar events before" counts related past events.** A past event is
related when it shares at least one topic with this event. No related event
counts 0, one counts 0.5, and two or more count 1. Each past event is read on
its own: one that shares every topic counts once. It was the Jaccard overlap of
all attended topics pooled together. A profile that attended no event, or has
no attendance record, stays unknown.

- Counting related past events is Ann Wang's, 2026-10-02.
- The 0.5 middle step for exactly one related event is **Chau's** refinement,
  confirmed 2026-10-04. It is not in Ann's document.

**An undecided career goal fits no event.** Ann's item 4b, verbatim: "It is
being counted as fitting a 'broad event.' That rule is not in the plan, and
Northline is not a broad event. Please remove it." Chau ruled on 2026-10-05
that this removes the rule everywhere, not only on Northline:

- Matching: "career goal fits this event" is a measured 0 for `Undecided` on
  every event, the same as `Graduate school`.
- Simulated results: an undecided hidden career goal earns none of the
  career-goal part of the true-fit lift. Ann's answer of 2026-09-25 bound the
  two together ("the results step should treat undecided students the same
  way"), so they are removed together.
- The plumbing goes with the rule: the "undecided goal suits a broad event"
  wording, the `undecided_goal_half` flag and label on the list response, the
  web's handling of both, and `exercise_event.is_exploratory`.

The rulebook is `exercise-0.2.0` (was `exercise-0.1.0`), Stage B formula
`1.1.0-exercise`, approver "Ann Wang, progress check and revisions 2026-10-02".

## Compatibility and scope

- **The column is dropped in the same release.** Migration
  `0044_drop_event_exploratory` removes `exercise_event.is_exploratory`.
  `db/migrations/script.py.mako` asks for a destructive step to wait until the
  release that stops reading the column is promoted and stable. Chau decided on
  2026-10-05 to drop it with the rule. Consequence: rolling the application
  back needs `alembic downgrade 0043_exercise_event_exploratory` first. The
  downgrade restores the column as `false` for every event.
- **`event_type` is still required and checked at ingest** against Ann's seven
  kinds of event. Nothing is stored from it.
- **The list response loses a field.** `undecided_goal_half` is gone from each
  entry and from `factor_labels`. The exercise routers are not in
  `contracts/openapi/smartmatch.json`, so that file does not change.
- **The plain-words results rule changes.** The paragraph at the top of
  `exercise/simulation.py` is the statement Ann and Dr. Lin receive; its
  sentence about an undecided career goal is removed. The coefficients Chau
  approved on 2026-09-25 are unchanged.
- **The sample result is regenerated.**
  [`oq-ce-03-sample-result.md`](../archive/plans/open-questions/oq-ce-03-sample-result.md)
  carries the new tables; a golden test holds it to the code.
- **Stored scores.** A score stored under `exercise-0.1.0` cannot be recomputed
  by this code. Acceptable before the class runs.
- **The deferred student track inherits these formulas.** ADR-0024 and the
  design spec describe a future `STUDENT_REGISTRY` over the same shared
  `student_factors` functions as Jaccard-based. Those functions are now the
  ones above. Accepted by Chau, 2026-10-04; revisit when that track is built.
- **On Ann's current file the past-event factor tops out at 0.5.** No profile
  has two past events related to Northline (only E08 is related) or to Harbor
  (only E05). The "went to similar events before" slider will move names less
  than the other three until the file has more related past events.

## Not decided here

- Ann's item 4c (one reason line per name; remove the second line of factor
  names under it) is separate web work.
- After a team's refresh, Northline's own topics are added to the topics of
  the profiles who attended it. Under the count rule that makes Northline
  attendance a related past event when Northline is ranked again. Left as is.
