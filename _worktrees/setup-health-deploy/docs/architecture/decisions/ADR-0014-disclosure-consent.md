# ADR-0014 — Disclosure consent is a separate record from contact consent

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §2.3, §5.5
**Backlog:** S10, D8
**Findings:** Stakeholder test log, 19–20 August 2026 — Fix #11

## Context

Fix #11 records a decision the stakeholder made in the session, and it exists
nowhere in this repository:

- **In-app chat is cut.** Not deferred — cut.
- **"People you met at this event" is kept** as a concept.
- **The connect action becomes an opt-in LinkedIn URL**, supplied by the person
  themselves.
- **Deeper access goes through a coordinator-mediated mentor request**, not
  peer-to-peer.
- **Attendance visibility is gated on consent.**

A term search for `disclosure` over the whole tree returns zero. The decision
was made, it has consequences for the schema, and no artifact records it — which
is precisely the class of silence this audit is about.

**The tempting mistake is to widen the consent module that already exists.**
`smartmatch_domain.consent` is a real, tested state machine — but it models
something else:

```python
class ContactState(StrEnum):
    """States in the contact-confidence lifecycle (v1.1 §2.3)."""

    DISCOVERED = "discovered"
    CORROBORATED = "corroborated"
    REVIEWED = "reviewed"
    RELATIONSHIP_RECORDED = "relationship_recorded"
    REJECTED = "rejected"
    CONSENTED = "consented"
    ACTIVE_CANDIDATE = "active_candidate"
    STALE = "stale"
```

Read the first state. That lifecycle begins with a contact **discovered by the
research pipeline** and ends with the organization being permitted to email
them. `ConsentSource` enumerates `SCRAPED`, `PURCHASED`, and `INFERRED`
explicitly so they can be refused, and `APPROVED_CONSENT_SOURCES` is the closed
set that may produce a `CONSENTED` record.

Every part of that shape is wrong for the thing Fix #11 needs.

## Decision

**Disclosure consent is its own record, its own table, and its own lifecycle.**
`smartmatch_domain.consent` is not widened.

A `disclosure_consent` record carries:

| Field | Meaning |
|---|---|
| subject | Whose information is disclosed |
| audience scope | To whom — e.g. co-attendees of one event, a coordinator, a named mentor |
| purpose | What the disclosure is for |
| granted / revoked | With timestamps; revocation is a state, not a delete |

Three rules:

1. **Attendance is visible to a peer only under an active disclosure consent
   covering that peer.** Absent a consent, a co-attendee is not shown — and per
   ADR-0011 the surface says the list is limited, rather than showing an
   unexplained empty state.
2. **Revocation is prospective and immediate.** A revoked consent stops future
   disclosure. It does not attempt to unsend what was already shown, and the
   record says so rather than implying otherwise.
3. **The connect action discloses only what the subject published.** An opt-in
   LinkedIn URL that the person supplied. No email address, no phone number, and
   nothing the research pipeline found.

**In-app chat is not built.** Recorded here with the decision, its owner, and
its date, so it reads as a decision rather than as an omission — `MM-F04`
archives the legacy `StudentConnect.tsx` chat surface on this basis.

**Mentor requests are coordinator-mediated.** A student requests; a coordinator
decides; the mentor is contacted through the existing consent-governed path.
There is no peer-to-peer channel.

## Rationale

**Why not widen `ContactState`.** Four differences, any one of which is
disqualifying:

| | Contact consent | Disclosure consent |
|---|---|---|
| Subject | A contact discovered by research | An authenticated user already known to the platform |
| Counterparty | The organization | Another *user* |
| Permission granted | May we contact you | May this person see that you were here |
| Audience | One, implicit — there is no audience field | Scoped, and the scope is the whole point |

The last row is the structural one. `ContactState` has no audience dimension
because it does not need one; there is exactly one party doing the contacting.
Disclosure consent is meaningless without an audience scope. Adding that field
to `ContactState` would put an always-null column on the outreach path and make
`ACTIVE_CANDIDATE` mean two unrelated things.

The two also fail differently: a contact-consent violation emails someone who
never asked. A disclosure-consent violation shows a student's attendance to a
peer. Both matter; conflating them means one set of tests has to cover both.

**Why revocation is prospective and stated.** A record that implies retraction
it cannot perform is the same defect as a number with no definition — a claim
the system cannot honour.

**Why the LinkedIn URL is opt-in and self-supplied.** It is the narrowest thing
that makes "people you met at this event" useful. A scraped profile URL would
be a `SCRAPED` source, which `APPROVED_CONSENT_SOURCES` already refuses for
contact — refusing it here too keeps the two modules consistent where they
genuinely agree.

## Consequences

- **S10** implements `disclosure_consent`. R2, alongside attendance.
- **D8** is the policy decision that must precede S10: what the consent asks,
  what audience scopes exist, what retention applies, and — the test log's Q35
  — **what the phrase "FERPA-aware" actually asserts.** Nothing in this
  repository defines it today. It is owned by privacy / legal / records, the
  same owner as D5.
- **Q31** (no data-minimization statement for QR signup) belongs to the same
  decision: QR check-in is what produces the attendance being disclosed.
- **MM-F04** archives the chat surface, retaining "people you met at this event"
  as a requirement under this ADR.
- `smartmatch_domain.consent` is unchanged. No existing test moves.

## Alternatives considered

**One consent table with a `kind` discriminator.** Rejected. The two lifecycles
share no state, no source vocabulary, and no transition; a shared table would be
two tables in a trench coat, with every query filtering on `kind` and one
missing filter crossing the two.

**Default attendance to visible among co-attendees.** Rejected. It is the
setting the stakeholder was questioning, and an opt-out on attendance data is
not a consent record.

**Defer the whole question to D8.** Rejected. D8 decides the *policy*; the
*shape* — that disclosure consent is a distinct record with an audience scope —
is an engineering decision, and leaving it open is what let the legacy ship a
chat surface nobody had classified.
