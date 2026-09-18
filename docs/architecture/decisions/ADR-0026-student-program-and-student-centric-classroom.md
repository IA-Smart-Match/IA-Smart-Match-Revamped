# ADR-0026 — The student program, and the student-centric classroom

**Status:** Proposed
**Date:** 17 September 2026
**Owner of record:** Student-engagement program owner (CBA platform track), with Ann Wang for the class-exercise track
**Decides:** that the student is the subject of the next phase of work — that the eight-slice engagement program is the CBA platform's shape for it, that every slice fails closed on a named register row, and that the Spring 2027 class exercise is the student-centric classroom where the shared matching mechanism is exercised over fictional rows. It closes no register row and licenses no route, table, or model artifact.
**Program:** `docs/plans/2026-09-14-student-engagement-program-plan.md`
**Register:** `docs/plans/open-questions/student-engagement-deferred.md`
**Evidence:** `docs/plans/2026-09-12-student-centric-prioritization-brief.md` (historical, superseded 2026-09-14); `docs/plans/2026-09-13-student-recommendation-program-plan.md` (historical)
**Relates to:** ADR-0013 (attendance-derived engagement), ADR-0016 (CBA scoring policy), ADR-0024 (staged student→event recommender), ADR-0025 (class-exercise scope shares the matching mechanism). Amends none of them.

> **Proposed.** This ADR adds no capability and removes none. Both stakeholder
> tracks proceed: the CBA platform track on the canonical engagement program,
> and Ann Wang's class-exercise track on ADR-0025's scope. What this ADR fixes
> is the *subject* — the student — and the discipline that follows from it:
> each program slice stops at a plan until its named register row closes, and
> the classroom is where the shared mechanism is proved without a real datum
> in the process.

## Context

**The direction is recorded, and its source is a relayed meeting.** The
stakeholder session of 12 September 2026 (Dr. Ann Wang, Yuka, Lisa), relayed by
Danny Tran as program owner of record, is quoted in
[`2026-09-12-student-centric-prioritization-brief.md`](../../plans/2026-09-12-student-centric-prioritization-brief.md)
§1: the next-phase MVP is **student-to-event matching plus push
notifications/reminders that drive registrations**, with **speaker matching, AI
features, and mobile deferred**; the reward/points system is the **strong second
priority**; the registration backlog is QR codes, flyer upload, video/summary,
and Handshake as one feed among many; a faculty extra-credit workflow is noted
as a later add-on. The brief itself records that those lines are *direction, not
ratified register closures*, and it has carried a HISTORICAL — SUPERSEDED
2026-09-14 banner since the canonical program plan replaced it. This ADR treats
it the same way: as the source of the priority, not as authority for behavior.

**The brief's own finding inverted the order.** Its §2 records that the rewards
system the meeting ranked second is the one that is nearly built (ADR-0013's
ledger, catalog, and redemption routes are committed), while the matching the
meeting ranked first is the one with no data to match on. That inversion is why
the canonical plan makes registration QR the first owned slice rather than
ranking, and why ranking sits at slice 6.

**The canonical plan is a plan, not a licence.**
[`2026-09-14-student-engagement-program-plan.md`](../../plans/2026-09-14-student-engagement-program-plan.md)
states in its own header that it implements no route, schema, UI, provider,
schedule, or metric, and closes no decision; decision authority belongs to
[`student-engagement-deferred.md`](../../plans/open-questions/student-engagement-deferred.md),
where every row reads **OPEN — tentative-development**. A safe default in that
register prevents unauthorized behavior; it is not a product decision. Nothing
in this ADR changes a row's status.

**Two tracks, two audiences, one mechanism.** ADR-0025 records that the class
exercise is a second `ProductScope` over about 300 made-up profiles, with no
login, no tenancy, and no account — and that its four factors are the CBA
track's student factors, built once in `smartmatch_domain/student_factors/` and
composed by two registries. ADR-0024 records the recommender's staged shape and
that `STUDENT_REGISTRY` stays `status = "proposed"` and fails closed until
OQ-SE-01. The classroom is therefore the only place on this platform where the
student-side factors can be run end to end at all today, because the CBA side of
them is gated and the exercise side is not.

**What is not recorded.** The push notification wording in the 12 September
relay and the outbound-delivery slice in the canonical plan are not the same
thing: the plan splits passive authenticated in-app content from outbound
delivery, and outbound stays gated on consent (OQ-SC-03) and on a producer that
does not exist (OQ-SE-16, OQ-SE-17). Whether the stakeholders' "push
notifications/reminders" means outbound push, email, or in-app reminders is
**unrecorded** in the repository, and it needs an owner before slice 7 can be
scoped. Attendance at that session beyond the three named people, and any
numbers, dates, or commitments not quoted in the brief, are likewise unrecorded
here.

## Decision

### D1. The student is the subject of the next phase

The next phase of platform work is judged by whether a student finds a useful
CBA service or event, registers, attends, and takes up the service. Speaker
matching, AI features, and native mobile are deferred per the 12 September
direction; deferred means not scheduled, not cancelled, and the speaker-side
mechanism — `CBA_REGISTRY`, ADR-0016's weights and bands — stays bit-identical
(ADR-0025 D3). Rewards proceeds as a parallel secondary track and never becomes
the recommendation objective; it may activate only after OQ-SC-01.

### D2. The eight-slice program is the platform shape, and each slice names its gate

The delivery order is the canonical plan's §3. This ADR records the slices and
the register rows each waits on, so the gate is readable from a decision record
rather than only from a plan:

| # | Slice | Gate |
|---|---|---|
| 1 | Registration QR/deep link into the existing authenticated registration action | OQ-SE-03 |
| 2 | Host-owned drafts, immutable submitted revisions, authorized review/approval/publication, accommodations and perks | OQ-SE-09, OQ-SE-10, OQ-SE-13 |
| 3 | One host → review → student vertical flow, proven end to end | slices 1–2 |
| 4 | Private media/video: upload, scan, moderation, captions, authorization, retention | OQ-SC-05, OQ-SE-11, OQ-SE-12 |
| 5 | Approved announcements and responsive student-portal parity | OQ-SE-14, OQ-SE-15 |
| 6 | Supporting interest profile and event ranking | OQ-SC-02, OQ-SE-01, OQ-SE-02 |
| 7 | Outbound consent and digest | OQ-SC-03, OQ-SC-10, OQ-SE-16, OQ-SE-17 |
| 8 | Registered engagement metrics over `event_registration` and `attendance_record` | OQ-SE-04 through OQ-SE-08 |

Slice 1 is registration QR only. It is **not** attendance/check-in QR, which
stays governed by OQ-E04, S11, and D8/OQ-SC-04 and needs an accessible
typed-code alternative. Slice 8 is where W4 sits, and the plan records **W4 as
STOPPED**: counts-only versus exact drill-down is unresolved, and ADR-0011 is
neither superseded nor weakened by anything here.

### D3. Gates fail closed: an unresolved gate means the slice stops at a plan, not code

A slice whose entry gate is open may be designed, specified, threat-modelled,
and reviewed. It may not ship a route, a table, a schedule, a provider call, a
student-visible surface, or a published number. The register's safe default
stays active until closure evidence lands, and the register states what closure
evidence is not: a plan, a prototype, a feature flag, or an unwired
implementation is not closure. This ADR marks no row resolved and reserves no
migration number; schema-bearing slices take current-head-plus-one at merge
readiness under the single migration-queue owner.

The failure direction is toward doing nothing. Where a gate is open, the
implementation refuses rather than guesses — `STUDENT_REGISTRY` scores nothing
(OQ-SE-01), no outbound message is sent (OQ-SC-03), no aggregate is published
(OQ-SE-04 through OQ-SE-08), and `host_organization` grants no authority
(OQ-SE-09).

### D4. The class exercise is the student-centric classroom, and it is a proving ground, not a pilot

`ProductScope.CLASS_EXERCISE` (ADR-0025 D1) is where the shared matching
mechanism is exercised with a live audience while the CBA student gates are
open. It proves the mechanism, not the program: the weighted-factor registry,
the `unknown`-distinct-from-`0` composition (ADR-0011), the reason line, and the
determinism machinery all run under real classroom use over fictional rows.

What it proves transfers as *mechanism*; what it observes does not transfer as
*data or decision*. No class-exercise result closes a register row, ratifies a
weight for `STUDENT_REGISTRY`, or supplies a training label — OQ-SE-01 and
OQ-SE-19 are unaffected by anything the exercise produces. ADR-0025's isolation
holds as written: separate scope, `exercise_`-prefixed tables with no
`tenant_id` and no foreign key to `user_account`, exercise routers barred from
importing `smartmatch_authz`, and the authenticated CBA routers not registered
in the exercise scope. Nothing learned in the exercise moves real data.

### D5. One `student_factors/` module, two registries, two processes

The relationship this ADR depends on is ADR-0025 D3's and is restated, not
changed: the four student-side factors are implemented once in
`smartmatch_domain/student_factors/`; `EXERCISE_REGISTRY` composes them with
Ann's labels, team-adjustable weights, and `status = "approved"` on the
authority of the requirements document; `STUDENT_REGISTRY` composes the same
functions under the student-engagement owners' governance at
`status = "proposed"`, failing closed until OQ-SE-01. Two rankers
(`rank_profiles_for_event`, `rank_events_for_student`) sit over them and import
neither the other. Two processes, because a no-login surface never shares a
process with real data.

### D6. Both tracks proceed

Neither track is parked, paused, or sequenced behind the other. The CBA platform
track runs its eight slices against its register; the class-exercise track runs
to Dr. Lin's Spring 2027 course against
`class-exercise-open-questions.md`. The shared cost is the ADR-0024 D2
parameterisation and the factor module, which both tracks need and which is
built once. A future decision that one track waits on the other is a new ADR,
not a schedule change.

## Rejected

- **Writing the 12 September direction into the register as closures.** The
  brief names its own lines as direction rather than ratified closures, and the
  register requires an attributed, dated decision artifact plus named evidence.
  Promoting a relayed meeting to a closure would erase the distinction the
  register exists to keep.
- **Ranking first, because the meeting ranked matching first.** The brief's §2
  records that matching has no data to match on and rewards is nearly built. The
  canonical plan's order — registration QR first, ranking at slice 6 — follows
  the evidence, and this ADR follows the plan.
- **Treating the class exercise as a pilot of the student program.** It has no
  accounts, no consent question, no tenancy, and fictional rows; its results are
  not evidence about real students. Calling it a pilot would invite a register
  row to be closed on synthetic data.
- **A separate student-side scoring system to move while the gates are open.**
  ADR-0016 and ADR-0024 D1 forbid a second scoring system beside the first, and
  ADR-0025 D9 already rejected the standalone exercise scorer for the same
  reason. The way past an open gate is to close it, not to build beside it.
- **Building outbound delivery from the "push notifications" line.** The plan
  separates passive in-app content from outbound delivery; absence of consent
  means off, and the digest producer does not exist. What the stakeholders meant
  by that phrase is unrecorded and needs an owner.

## Consequences

**Good.** The priority has one recorded subject and one recorded shape, so a
reader finds both the direction and the gate that holds each slice without
reconstructing them from a superseded brief. The failure direction is uniform:
open gate, no code. The classroom gives the shared mechanism real use and real
feedback on schedule, while the CBA student surface waits on its owners rather
than on engineering.

**Bad, accepted.** Most of the program's value is behind decisions engineering
does not own, so the visible output of several slices is documents. The same
small team carries two tracks at once. And the classroom's success will be
tempting to read as validation of the student program — D4 exists because that
reading is wrong, and it will have to be refused more than once.

**Verification.** ADR-0025's checks carry the isolation: `make imports` enforces
the exercise routers' boundary, `make scan` enforces the naming rule, the
scope-absence tests enforce that neither scope registers the other's routers,
and the schema walk enforces the withheld-field rule. `tests/unit/test_adr_index.py`
holds this ADR's row to its title, status, and date. This ADR adds no test of
its own, because it adds no mechanism: D3 is verified by the register continuing
to read OPEN for every row named in D2, and by no slice shipping past its gate.

## Amendment discipline

A later change to the slice order, to which register row gates a slice, to the
fail-closed rule in D3, or to the proving-ground boundary in D4 amends this ADR.
Closing a register row does not: that is a register event, recorded in
`student-engagement-deferred.md` with its decision artifact, and the slice it
unblocks proceeds without touching this file. A decision to pause either track
is a new ADR.
