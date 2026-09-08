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
(`tests/integration/test_synthetic_attendance_writer.py`) was for a time the
only writer, and it was not a production one. The paragraph below supersedes
that last sentence; the rest of the safe default still stands, because the
Attended stage still only ever cites.

**Decided 7 September 2026 by Danny Tran, program owner of record.** The
**coordinator** writes `attendance_record`, through `POST
/v1/units/{unit_id}/events/{event_id}/attendance`
(`services/api/smartmatch_api/routers/attendance.py`), gated to `{admin,
coordinator}` and scoped to the unit in the path. `method` is fixed server-side
to `coordinator_entry` and the request has no field for it: the route *is* a
coordinator's entry, and a caller-chosen `qr_scan` would claim a scanner nobody
used while `import` would claim a batch that never ran. There is no
`recorded_at` either — `created_at` is the server default and the Attended stage
reads that column, so presence cannot be backdated. The subject may be any
`user_account` in the tenant, student or speaker, because the CBA hand-off cites
a row whose subject is the speaker.

Points are credited **on record**, in the same transaction, at
`POINTS_PER_VERIFIED_ATTENDANCE` with `EARN_POLICY_RATIFIED` still `False`.
That is ADR-0013's model rather than a new one — points derive from recorded
attendance and nothing else — and nothing here promotes D7. Recording without
crediting was rejected: it would leave every marked student's balance `unknown`
forever, which is the honest report of a state this decision exists to stop
creating.

**What this decision does not authorize.** The **check-in scanner** and the
**roster upload** — the other two candidate writers this question named — remain
unbuilt, and B08's QR flow stays behind S11 and D8.
`tests/unit/test_checkin_wiring.py` holds that structurally: the route's path
carries none of its check-in markers, and the API composition root still never
imports `smartmatch_domain.checkin`. Building either writer re-opens this row
rather than inheriting its answer.

**The exposure, stated rather than discovered later.** A coordinator can now
assert that a named account was present at their unit's event, and that
assertion mints 100 points for that account. The warning this question carried —
a wrong row is a wrong reward — is live from here on. The compensating control
is the append-only ledger: an `attendance_record` cannot be deleted (every
foreign key to it is `RESTRICT`), so the correction for a wrong row is
`RewardsRepository.record_reversal`, a withdrawing entry carrying its own
`actor_id` and reason. A reversal, never a delete.

**What was superseded, and what was not.** This exceeds item 3 of
`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` §4
("minimal synthetic writer ... in demo seed flow"). That ratified document is
**not** edited — a ratified record that quietly acquires a later exception stops
being a record of what was ratified — and this paragraph is the later authority,
recorded beside it, on the precedent OQ-CBA-032's closure set. The prohibition
in `smartmatch_persistence/attendance.py`'s own docstring ("no route imports
this repository, and none may") is retired in the same change as the code that
retires it, as are the "No attendance writer" paragraphs in
`routers/pipeline.py` and `routers/cba_handoff.py`; both routers still only
cite.

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
