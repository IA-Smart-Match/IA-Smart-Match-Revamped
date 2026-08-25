# ADR-0010 — An event carries an instant, an IANA zone, and a precision

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §3.1, §3.6 N1
**Backlog:** S3
**Findings:** Stakeholder test log, 19–20 August 2026 — Fix #4, Fix #6

## Context

Two findings in the stakeholder test log are the same defect seen from two
angles.

**Fix #6:** events displayed at 3 AM and 7 AM. Those are not times anyone
scheduled. They are a UTC instant rendered in a zone nobody chose, or a naive
local time relabelled as UTC — the classic pair, and from the outside they are
indistinguishable.

**Fix #4, in part:** events with no resolved date at all. The legacy pipeline
extracted events from pages that said "next Thursday" or gave no date, and
something downstream had to produce a `datetime` anyway.

This repository already refuses the second half of that, in exactly one place.
`smartmatch_domain.ics.generate_ics` will not build an invite from an
unresolved or naive datetime:

```python
def _require_aware(value: datetime, field: str) -> None:
    """Reject naive datetimes.

    Fixes legacy defect 2: a naive datetime formatted with a trailing ``Z``
    claims UTC for a value that never carried a timezone.
    """
```

It raises `UnschedulableEventError` rather than inventing a slot
(`ics.py:60`, `:110`, `:115`). `MM-001`'s `behavior_rejected` records why: the
legacy's `_parse_date` turned an unparseable date into "30 days from now",
"fabricating a meeting slot nobody chose — prohibited by v1.1 §3.6 N1".

**That rule is real, and it is in the wrong place.** It guards one exporter. An
event whose time is unknown can still be stored, listed, matched against, and
rendered — it only fails when someone asks for an `.ics`. The stakeholder was
not looking at an `.ics`. She was looking at a list, which is a render path that
does not exist yet and therefore inherits nothing.

## Decision

An event's time is three fields, not one:

| Field | Type | Meaning |
|---|---|---|
| `starts_at` | `timestamptz` | The instant, stored in UTC |
| `time_zone` | IANA zone name (`America/Los_Angeles`) | The zone the event *happens in* |
| `time_precision` | `exact` · `date_only` · `unresolved` | How much of the instant is actually known |

Three rules follow.

1. **`time_zone` is the event's zone, not the viewer's and not the server's.**
   A UTC offset is not acceptable in its place: an offset is a fact about one
   instant, and an event moved across a DST boundary silently shifts.

2. **An event at `unresolved` cannot reach a matchable or publishable state.**
   This is a state-machine constraint, not a validation warning. It is the
   generalization of what `generate_ics` already does for its own output.

3. **Display renders in the event's own zone and names the zone.** A time
   without a named zone is not a rendered time; it is a number that happens to
   have a colon in it.

`date_only` exists because it is the honest description of most of what the
crawler will find. "Thursday 14 September, on campus" is real information and
is not an instant. Collapsing it to midnight and rendering that is how a list
comes to show 3 AM.

## Rationale

**Why precision is a stored enum rather than an inference.** A nullable
`starts_at` distinguishes only "known" from "unknown". It cannot express
`date_only`, which is the case that produced the visible bug — and inferring
`date_only` from a midnight timestamp is a heuristic that mislabels the events
that genuinely start at midnight.

**Why this is filed as a model decision rather than a render rule.** A render
rule lives in a layer that has no owner (`apps/web/DESIGN.md` is a brief and is
on hold behind D-0) and cannot be tested today. Putting precision in the model
means a test can see the defect now, before any screen exists. It also means
every future render path inherits the constraint instead of re-deriving it —
which is the failure mode this ADR is about, since `generate_ics` did have the
rule and nothing else got it.

**Why the state machine and not validation.** Validation is advisory and is
applied by whoever remembers to call it. A state an event cannot leave is
enforced by the same mechanism that already enforces job state
(`ck_job_status`, pinned to `smartmatch_domain.jobs.JobState` by
`tests/integration/test_job_states_match_domain.py`).

## Consequences

- `ics.generate_ics` becomes the *second* enforcement point rather than the
  only one, and its `UnschedulableEventError` becomes a defence in depth rather
  than the guard. Its behaviour does not change.
- The R3 crawler (`MM-A08`) must map extracted dates onto the precision enum
  rather than producing a `datetime` unconditionally. ADR-0012 constrains the
  same entry from the identity side.
- The event table does not exist yet; this decision is a contract that S3 and
  the R2 schema work implement. Nothing in the current schema changes.
- A `date_only` event needs a display treatment that is not a time. That is a
  design question and belongs to D-0's successor, not here.

## Alternatives considered

**Store a local naive datetime plus a zone.** Rejected. It makes every
comparison a conversion, and the ambiguous hour of a DST fall-back has no single
answer.

**Store the offset instead of the zone name.** Rejected — see Decision rule 1.

**Render in the viewer's zone.** Rejected. A coordinator in one region briefing
a speaker in another needs one shared answer to "when is this", and the event's
own zone is the only candidate that does not change per reader.
