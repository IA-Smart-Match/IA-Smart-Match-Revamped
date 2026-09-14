# Student engagement program — canonical plan (2026-09-14)

**Status:** canonical planning authority for the student-engagement program.
Documentation only: this plan implements no route, schema, UI, provider, schedule,
or metric and closes no decision.

**Decision authority:** every unresolved product, privacy, records, accessibility,
security, and operating choice is owned by the canonical
[`student-engagement-deferred.md`](open-questions/student-engagement-deferred.md)
register. Older recommendation plans are historical evidence, not implementation
authority.

## 1. Outcome and priority

The primary outcome is that students find useful CBA services and events, register,
attend, and take up the offered service. Interest-based recommendation supports
that journey; it is not the program spine. Rewards is a parallel secondary track.

The first owned product slice is **registration QR**: an actor authorized under
OQ-SE-03 shares a QR/deep link to an approved published event, and an authenticated
student lands on the existing registration action. Registration QR is not attendance/check-in QR;
the latter remains governed by OQ-E04, S11, D8/OQ-SC-04, and an accessible typed-code
alternative.

Native mobile, app-store delivery, PWA installation, flyer OCR, and invented speaker
or employer line-ups are outside the default flow. They stay deferred unless the
register is closed with explicit authority.

## 2. Current pilot versus target

| Area | CURRENT PILOT | TARGET PROGRAM |
|---|---|---|
| Student access | Responsive student web; published-event browse; registration and agenda; attendance and rewards seams | Responsive-web parity for the complete approved engagement flow; optional PWA installation only after OQ-SE-15 |
| Event creation | Host can file a Speaker Request. Connector manually creates, edits, and publishes an event | Host filer owns a draft and immutable submitted revisions; Connector reviews, approves, and publishes; students see approved content only |
| Publication control | Current publication checks completeness/publishability, not reviewer approval | Review approval is a separate required state before publication; host organization metadata is never authorization |
| Registration | Authenticated registration action exists | Approved-event QR/deep link enters the same authenticated registration action, with registered measurement |
| Attendance and rewards | Attendance evidence and rewards seams exist; feedback QR exists | Keep attendance evidence distinct from registration; operate approved rewards in parallel without making points the recommendation objective |
| Event detail | Published event facts | Approved accommodations and perks, with vocabulary and accessibility decisions closed |
| Media | No approved engagement media plane | Private video/media with malware scanning, caption/transcript handling, moderation, authorization, and retention controls |
| Announcements | No approved student-announcement flow | Approved, scoped announcements on authenticated student web; outbound delivery remains separately consented |
| Recommendation | No authoritative student recommendation program | Optional supporting ranking from approved inputs and an approved registry; no invented line-ups and no hidden wildcard |
| Delivery | Authenticated app content can be read when a surface exists; no student digest producer | Passive authenticated in-app content remains non-outbound; email or other outbound messages require opt-in and a separately operated digest producer |
| Measurement | Existing metrics do not define registration-to-attendance | Registered engagement definitions and owning queries over `event_registration` and `attendance_record`, with ADR-0011 reconciliation and authorized exact rows |

## 3. Delivery slices and gates

| Order | Slice | Owner | Entry gate | Completion evidence |
|---|---|---|---|---|
| 1 | Registration QR/deep link to the existing authenticated registration action | Student-engagement product owner + API/web owners | OQ-SE-03 | Link threat model; route and UI tests; QR and ordinary-link registrations reconcile under one registered definition |
| 2 | Host-owned draft, immutable submitted revisions, Connector review/approval/publication, accommodations and perks | Program owner + Connector operations + records owner | OQ-SE-09, OQ-SE-10, OQ-SE-13 | Authorization matrix; revision/audit tests; publication refuses unapproved content; host organization grants no access |
| 3 | One host-to-review-to-student vertical flow | Same owners as slice 2 | Slices 1–2 | Host files → Connector reviews → approved event becomes student-visible → student registers, proven end to end |
| 4 | Private media/video | Program owner + records, security, accessibility owners | OQ-SC-05, OQ-SE-11, OQ-SE-12 | Upload, scan, moderation, captions, authorization, retention, and failure-path evidence |
| 5 | Approved announcements and responsive student portal parity | Program owner + web/accessibility owners | OQ-SE-14, OQ-SE-15 | Keyboard, screen-reader, responsive, non-happy-state, and authorization checks |
| 6 | Supporting interest profile and event ranking | Program owner + records owner | OQ-SC-02, OQ-SE-01, OQ-SE-02 | Approved registry and golden cases; unknowns remain unknown; no speaker identity in student cards |
| 7 | Outbound consent and digest | Program owner + records + operations owners | OQ-SC-03, OQ-SC-10, OQ-SE-16, OQ-SE-17 | Opt-in/revocation, producer, schedule, idempotency, retry, quota, and operations evidence |
| 8 | Registered engagement metrics | Program owner + records/privacy + metrics owners | OQ-SE-04 through OQ-SE-08 | Registered names/definitions, one owning query each, authorized exact rows, aggregate reconciliation, privacy tests |

Rewards can proceed beside these slices only after OQ-SC-01; it does not reorder
the engagement flow. OCR, native mobile, app-store release, live providers, public
release, and cross-unit expansion are not hidden dependencies of this internal CBA
development plan.

Internal development still must satisfy applicable privacy, records, accessibility,
and security constraints and the named owners must make the register decisions.
Legal review is a future gate before external deployment, public release, cross-unit
expansion, or live-provider/live-data use; it is not required to start or complete
the internal CBA development slices described here.

## 4. Event authority and content flow

The target state separates authorship, review, publication, and visibility:

1. An authenticated, authorized filer creates a draft for their host scope.
2. Submission freezes an immutable revision; later edits create another revision.
3. A Connector reviews that revision and records approval or refusal with reason.
4. Publication requires both completeness and approval of the exact revision.
5. Student reads return only the approved, published revision and its approved
   accommodations, perks, media, and announcements.

`host_organization` is descriptive provenance, not a role, grant, or membership.
No implementation may infer filing, review, publication, or read authority from
organization association alone.

## 5. Delivery is two different capabilities

**Passive authenticated in-app content** is content a signed-in student chooses to
open. It is not an outbound notification and does not need an email opt-in. It must
still be authorized, approved, and privacy-safe.

**Outbound delivery** includes email and any later push channel. Absence of consent
means off. Revocation must be checked again at delivery. Push remains deferred; PWA
installation does not imply notification consent.

Before the existing dispatcher can send a digest, a separate producer must create
the durable `student-digest.send` command. `POST /operations/dispatch` only drains
existing outbox work; it does not create scheduled digest jobs. The outbound slice
therefore remains gated on:

- producer system identity and unit scope, quota ownership, and failure ownership;
- a per-unit schedule with a named IANA time zone and default-disabled state;
- deterministic idempotency from unit, schedule occurrence, content version, and
  channel, with duplicate submission refused or folded safely;
- late-run, retry, outage, clock-change, and daylight-saving-time behavior;
- human-owned content version, opt-in evidence, delivery-time revocation recheck,
  and auditable terminal outcomes.

## 6. Measurement and W4 stop gate

`pipeline_record` measures the CBA speaker-handoff journey. It does **not** measure
a student's registration-to-attendance journey.

The engagement metric is only a candidate until OQ-SE-04 through OQ-SE-08 close. A
registered definition and one server-owned query must join `event_registration`
and `attendance_record` using an approved population and time basis. Every visible
aggregate remains subject to accepted ADR-0011: authorized drill-down must return
the exact constituent rows and reconcile to the aggregate. Population, suppression
threshold, aggregate roles, exact-row roles/fields, and privacy treatment are
tentative-development choices, not decisions in this plan.

Service uptake also needs an owner-defined outcome under OQ-SE-18. Registration or
attendance must not be relabeled as service uptake when the service has a distinct
completion, referral, or fulfillment record.

**W4 is STOPPED.** Counts-only versus exact drill-down is not resolved here, and
ADR-0011 is not superseded or weakened. Work may resume only after the register
records a compatible privacy/accountability decision and closure evidence.

## 7. Ranking boundaries

`STUDENT_REGISTRY_VERSION` is only a proposed version against OQ-SE-01, the distinct
student scoring-registry approval question. OQ-SC-09 is about storing skip behavior
and cannot approve a registry.

The wildcard follows the W2 definition: at most one explicitly labeled exploration
item, represented separately from ranked `items`, selected only from eligible,
scorable published events outside the ranked list, and never laundered into a recommendation.
No backend wildcard toggle exists unless OQ-SE-02 approves one. No unsupported
prefetch size, retention percentage, or churn percentage is part of the program.

All schema-bearing slices use **current-head-plus-one** when they are ready to merge.
A single migration-queue owner assigns order; concurrent schema work rebases before
merge, and the repository must retain one migration head. No revision number is
reserved by this plan.

## 8. Engineering estimate

| Work | Engineering hours |
|---|---:|
| Documentation and governance | 20–32 |
| Registration QR | 24–40 |
| Host draft/revision/review plus accommodations/perks | 96–152 |
| Private media/video | 136–216 |
| Announcements plus responsive student portal parity | 72–112 |
| Outbound consent/digest | 56–88 |
| Registered engagement metrics | 40–64 |
| E2E/security/accessibility/operations hardening | 64–104 |
| **Total** | **508–808** |

That is about **13–20 engineer-weeks at 40 hours/week**. The ranges assume reuse
of the existing PostgreSQL, API, React, authentication, and outbox foundations and
include implementation plus slice-level tests. They exclude stakeholder/privacy/
records decision wait time, cloud or vendor procurement, deployment approval, and
native mobile. They also exclude supporting ranking implementation and rewards
activation; estimate those separately only after their register decisions close.
Legal review is outside the internal-development critical path;
it becomes a gate only for the external-release cases in §3. Parallelism changes
calendar time, not total engineering hours.

## 9. Evidence and non-authority

The following documents preserve useful research and the superseded recommendation
sequence. They do not authorize implementation:

- [`2026-09-12-student-centric-prioritization-brief.md`](2026-09-12-student-centric-prioritization-brief.md)
- [`2026-09-13-student-recommendation-program-plan.md`](2026-09-13-student-recommendation-program-plan.md)
- [`research/2026-09-12-flyer-intake-research.md`](research/2026-09-12-flyer-intake-research.md)
- [`research/2026-09-13-engagement-feed-research.md`](research/2026-09-13-engagement-feed-research.md)
- [`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md)

An executor starts from this plan and the canonical register, then verifies current
README authority, current code, current migration head, and accepted ADRs. This
documentation change is not evidence that any target capability is implemented.
