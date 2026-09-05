# S12 pipeline stage writers — open questions carried by this slice

**Date:** 2026-09-05 · **Slice:** coordinator-driven stage advances
(`docs/plans/2026-09-05-pipeline-stage-writers-plan.md`)

Every item here is a decision or an integration engineering could not supply on
its own. None of them stopped the slice: each carries a **safe default that is
implemented**, and every default is chosen so that being wrong about it degrades
into *the funnel under-reporting* rather than into *the funnel reporting a stage
nobody reached*.

That asymmetry is the policy, and it is ADR-0011 restated for this table: a
missing advance is a coordinator's number being lower than reality, which they
can see and correct; a fabricated advance is a number about a real student's
engagement that nothing behind it supports, and no later decision can undo the
report it fed.

Nothing here is a placeholder that reports success. Where an integration is
missing, the route requires a human to assert the fact with a timestamp, and the
response returns the stored row so the assertion is auditable rather than
implied.

---

## OQ-101 — live calendar / RSVP confirmation (deferred, blocks an automatic Confirmed)

**Question.** Which calendar or RSVP system is authoritative for "this
professional confirmed they will speak at this event", and how does this
appliance read it — a Google Calendar event's `attendees[].responseStatus`, a
form submission, an email reply parsed by the outreach path, or a coordinator
reading any of those and typing the result?

**Why engineering cannot answer it.** Each option is a different claim with a
different provenance. A calendar `accepted` is the professional's own act; a
coordinator ticking a box is the coordinator's reading of one. Both can be
honest and they are not the same fact, so the schema would eventually need to
record *which* — and inventing that column before the integration exists would
guess at a vocabulary the chosen system may not use. It is also an OAuth scope
and a data-processing decision (`docs/decisions/a1b-*`) that belongs with the
same owner who decides the IdP.

**Safe default, implemented.** `POST .../pipeline-records/{id}/stages` requires
an authenticated `admin`/`coordinator` and an explicit, timezone-aware
`reached_at`. There is **no** poller, no webhook, and no code path that infers
Confirmed from anything. The stage is only ever reached because a named human
asserted it, and the row that results carries that timestamp — so when a
calendar integration does land, the question "was this row a machine
observation or a person's claim?" is answerable from the data instead of
guessed at.

**What lands when it is answered.** A provenance column on the Confirmed stage
mirroring `matched_provenance` (migration `0016`'s shape), and a worker that
writes it. Neither is written now, because a provenance column with exactly one
possible value is not provenance.

## OQ-102 — who writes `attendance_record` (deferred, gates Attended at volume)

**Question.** What creates attendance rows in the pilot — a check-in scanner, a
roster upload, or the coordinator?

**Why engineering cannot answer it.** `attendance_record` is the only input to
points (ADR-0013), so whatever writes it is also what mints student rewards. The
tolerance for a wrong row is a program decision, not a technical one.

**Safe default, implemented.** The Attended stage does not write attendance. It
**cites** it: `attendance_id` is required, and
`PipelineRepository.advance_stage` verifies the row exists in this tenant before
the `UPDATE`, backed by `ck_pipeline_record_attendance_evidence`. A journey
therefore cannot reach Attended without a real attendance row already existing,
whoever eventually writes it. The synthetic pilot path
(`tests/integration/test_synthetic_attendance_writer.py`) remains the only
writer, and it is not a production one.

## OQ-103 — what "member inquiry" means operationally (deferred, definition only)

**Question.** Does Member Inquiry mean a membership application submitted, an
expression of interest recorded by a coordinator, or a click on a membership
link?

**Why engineering cannot answer it.** It is the funnel's terminal conversion
metric and the number the program will be judged on. Its definition is the
program owner's.

**Safe default, implemented.** The stage is advanced only by explicit
coordinator action with a timestamp, and the API documents it as "a coordinator
recorded a membership inquiry" rather than asserting a definition. No count
derived from clicks, opens, or link tokens feeds it.

## OQ-104 — a coordinator-facing queue of journeys (deferred, read surface)

**Question.** May a coordinator list *other people's* pipeline records for their
unit, and at what granularity?

**Why engineering cannot answer it.** It is the same unresolved read-role
decision `docs/decisions/d6-rewards-budget-decision-record.md` §5 raises for
redemptions, over student engagement data.

**Safe default, implemented.** There is no list route. `GET
.../pipeline-records/{record_id}` reads exactly one record, by an id the caller
was given out of band, scoped to the tenant and checked against the authorized
unit — mirroring `rewards.py`'s deliberate absence of a coordinator queue. A
list route is additive when the decision lands; a list route shipped early
cannot be un-shipped.
