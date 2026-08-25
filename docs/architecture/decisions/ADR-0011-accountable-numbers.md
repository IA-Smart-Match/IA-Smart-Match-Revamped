# ADR-0011 — Every user-visible number is accountable

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §3.6 N1, §5.5
**Backlog:** S1, S2, S12
**Findings:** Stakeholder test log, 19–20 August 2026 — Fix #5, Fix #8, Fix #12

## Context

Three findings, one cause. The stakeholder was not reporting arithmetic errors.
She was reporting that the numbers on the screen had no accountable meaning.

| Fix | What she saw |
|---|---|
| #5 | Two pages both labelled "opportunities", showing different totals |
| #8 | "Topic Relevance 0%" on an event about AI; "Match Depth 0"; "Rest recommended: 0" beside a volunteer the same page had flagged as overloaded |
| #12 | Clicking a count of 15 produced a list of 31 rows |

Each is a different symptom of a number that nobody can be held to. #5 is two
definitions wearing one name. #8 is *absence* rendered as *zero*. #12 is a
count and a list computed by different queries, so the drill-down disagrees with
the thing it drills into.

None of these is caught by a test that checks the arithmetic, because in each
case the arithmetic was probably right. What was wrong is that no artifact
anywhere said what the number was supposed to mean.

**One module in this repository already gets the third rule right.**
`FeedbackAggregate.acceptance_rate` (`feedback.py:132`) returns `None`, not
`0.0`, for an empty feedback set:

```python
@property
def acceptance_rate(self) -> float | None:
    """Fraction accepted, or ``None`` when there is no feedback.

    ``None`` rather than ``0.0``: an empty feedback set means *unknown*, and
    rendering it as a 0% acceptance rate is the kind of confident-looking
    fabrication v1.1 §5.5 exists to eliminate.
    """
```

That is a habit in one property. This ADR makes it a platform rule, and adds
the three that would have caught the rest.

## Decision

Four rules. A number that a user can see must satisfy all four.

### 1. Unknown is not zero

A value with no evidence is `unknown` and renders as `unknown`. Never `0`,
never `0%`, never `—` styled to look like a measurement. This applies to counts,
rates, scores, and durations alike.

`feedback.acceptance_rate` is the reference implementation. The rule it follows
becomes the type-level default: an aggregate over a possibly-empty set returns
an optional, and the render primitive refuses to coerce `None` to a numeral.

### 2. One canonical name, one written definition

Every user-visible aggregate is registered with a name and a one-sentence
definition of what it counts, in a metric register that ships in the
repository. **A metric with no register entry does not ship.**

"Opportunities" is not a definition. "Events in the match pool with at least one
speaker above the score floor, excluding events whose date is `unresolved`" is.
Two screens may show the same registered metric; they may not both invent one.

### 3. One owning query

A registered metric is computed by exactly one query, in one place. Two views
cannot disagree because there is only one implementation to disagree with. A
view that needs a variant registers the variant as its own metric, with its own
name and definition, rather than filtering the original in the view layer.

This is what closes #5. It is also what makes #3 (the funnel) buildable at all:
Matched → Contacted → Confirmed → Attended → Member Inquiry is five metrics that
must be mutually consistent, and five separate queries will not be.

### 4. A drill-down returns exactly the rows the number was computed from

Clicking an aggregate yields its constituent rows — the same rows, from the same
query, not a re-query with similar-looking filters. The count of the drill-down
result equals the aggregate. **This is a contract test, not a convention:** it
is the only one of the four rules that can be checked automatically without a
human reading a definition, and it is the one that catches #12.

## Rationale

**Why a register rather than docstrings.** A docstring is attached to an
implementation, and the defect here is two implementations. The register is the
thing there is only one of.

**Why rule 4 is the testable one, and why that matters.** Rules 1–3 need a
person to read a sentence and agree it describes the query. Rule 4 is an
equality between two values the system can produce on its own. Given this
repository's standing observation that a documented rule with no executable
check goes unenforced, the rule that *can* carry a check is worth more than its
share, and S1 is scoped so that check lands with the register rather than after
it.

**Why `unknown` is not deferred to the render layer.** It cannot be. By the time
a `0` reaches the render layer the information that distinguishes it from
`unknown` is gone. The distinction has to survive in the type.

## Consequences

- **S1** — the metric register and the drill-down contract test.
- **S2** — the render primitive that refuses to print `None` as `0`. This is a
  frontend item and inherits the **ON HOLD** behind D-0; the domain-side half
  (aggregates returning optionals) does not.
- **S12** — the funnel becomes a set of five registered metrics with one owning
  query, rather than a chart.
- **MM-002** — her three matching symptoms (the exact 43% tie, Topic Relevance
  0%, Match Depth 0) become required golden cases for gate G1. "Topic Relevance
  0%" on an AI event is either a real zero that needs an explanation or an
  unknown wearing a zero's clothes, and today nothing distinguishes them.
- Existing domain code is already compliant in the one place it applies. Nothing
  in the current tree changes.

## Alternatives considered

**Render `unknown` as `—` and leave the type alone.** Rejected: it fixes the
pixel and leaves the ambiguity in the data, so the next consumer reproduces it.

**Reconcile the two "opportunities" numbers and move on.** Rejected. That is
the fix for one instance of a defect whose cause is structural; the stakeholder
found three instances in two days.
