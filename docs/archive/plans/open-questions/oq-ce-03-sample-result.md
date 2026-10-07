# Sample result for the results rule (OQ-CE-03)

**For:** Ann, for information. Chau used it to approve the numbers.
**Date:** 2026-09-25.
**Status:** **Approved 2026-09-25.** The numbers below were translated by the
team from Ann's answers and approved by Chau, to whom Ann delegated the
numbers. OQ-CE-03 is closed
([register](../../../plans/open-questions/class-exercise-open-questions.md); decision record D7 in
[`class-exercise-decisions-2026-09-25.md`](../../../decisions/class-exercise-decisions-2026-09-25.md)).
If Ann would like the numbers changed, each is one line in `simulation.py`.

**Regenerated 2026-10-05.** Ann's progress check and revisions of 2026-10-02
changed two matching factors and removed the half match for an undecided
career goal (item 4b), in matching and in this rule. The result tables and
"What this shows" below are recomputed under those rules; the coefficients
Chau approved are unchanged. "What Chau decided" is left as it was written on
2026-09-25, against the earlier tables. See
[`class-exercise-factor-revisions-2026-10-02.md`](../../../decisions/class-exercise-factor-revisions-2026-10-02.md).

## What Ann asked for

Ann was asked how strongly each of these should make a student more likely to
sign up. Her answers:

| What | Ann's answer |
|---|---|
| The event matches what the student genuinely cares about (their true interests and career goal) | a lot |
| The student has attended events before | some |
| The event is aimed at the student's major | a little |
| Random chance and individual circumstances | some randomness |

On 2026-09-25 she also said that a student whose career goal is undecided
should count as a half match for broad, exploratory events. Her revisions of
2026-10-02 removed that rule: an undecided career goal now fits no event.

## How her words became numbers

Every student starts with a 4 in 100 chance of signing up. On top of that:

| What | Ann's word | Extra chance of signing up |
|---|---|---|
| The event matches what they truly care about | a lot | 40 in 100 |
| They have been to at least one past event | some | 10 in 100 |
| The event is aimed at their major | a little | 4 in 100 |
| Chance | some randomness | up to 10 in 100, either way |

The "a lot" boost is split in two equal halves. One half comes when one of the
student's true interests is a topic of the event. The other half comes when
their career goal fits the event. A student whose career goal is undecided, or
is graduate school, gets none of that second half.

A student's chance never goes below 0 or above 100 in 100. Each student who
signs up has a 75 in 100 chance of attending. That matches Ann's own example,
where 6 of 8 attended.

The rule uses each student's true interests and true career goal, not what the
student has told the app. That is why a list built only on what the app knows
can miss people.

## The data

The run used Ann's file of 300 fictional profiles shaped by overall survey
percentages.

## The three lists

For each event, a team invites 30 students. We tried three lists:

- **Equal weights.** The list the app suggests if a team changes nothing: same
  major, said they are interested, career goal fits, and went to similar events
  before all count the same.
- **Said they are interested.** Only what a student's profile card says they
  are interested in counts.
- **Same major.** Only whether the student is in the major the event is aimed
  at counts.

## Results

Each team's chance is fixed, so one team always gets the same answer for the
same list. "One team" below is one example team. "A typical team" is the
average over 1,000 different teams, which shows what the list does apart from
luck.

Empty seats are counted as 60 seats, minus the 8 people who had already signed
up, minus the invited students who attended. The results screen shows both
groups, for example "8 were already coming. Your invitations added 6. 46 seats
are still open." (OQ-CE-16, approved by Chau 2026-09-25).

### Northline

| List | One team: signed up | One team: attended | One team: empty seats | A typical team: signed up | A typical team: attended |
|---|---|---|---|---|---|
| Equal weights | 14 | 12 | 40 | 9.5 | 7.2 |
| Said they are interested | 12 | 10 | 42 | 6.8 | 5.1 |
| Same major | 7 | 6 | 46 | 7.7 | 5.8 |

### Harbor

| List | One team: signed up | One team: attended | One team: empty seats | A typical team: signed up | A typical team: attended |
|---|---|---|---|---|---|
| Equal weights | 9 | 6 | 46 | 8.0 | 6.0 |
| Said they are interested | 11 | 7 | 45 | 8.6 | 6.4 |
| Same major | 7 | 7 | 45 | 6.9 | 5.1 |

## What this shows

1. The size is close to Ann's example. A typical team using the suggested list
   gets about 8 to 10 sign-ups and 6 to 7 attendees out of 30 invited.
2. For Northline, the suggested list does best for a typical team. For Harbor,
   the "said they are interested" list does best.
3. Luck can change the order for one team. On Harbor the example team's "same
   major" list brought as many attendees as its "said they are interested" list
   (7 each), although "same major" is the weakest of the three for a typical
   team.

## What Chau decided

These were the questions put to Chau with this sample. On 2026-09-25 Chau
approved the numbers as shown and the team's recommendation for empty seats,
which answers all three.

1. **Are these sizes believable?** The numbers stand as shown.
2. **Is the randomness the right size?** It stays at up to 10 in 100 either
   way. At this size one team's luck can flip which list looks best, as the
   example team shows.
3. **How should empty seats be counted?** Show both groups: the 8 who had
   already signed up, and the invited students who attended. So 6 attendees
   leave 46 seats open. An earlier example of ours read "54 seats remained
   open", which left the 8 out. That figure was the team's own example text,
   not Ann's.
