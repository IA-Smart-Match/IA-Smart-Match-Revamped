# ADR-0013 — Attendance-derived engagement: a server-side ledger, and rewards with an owner

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §2.2, §3.1, §3.6 N1
**Backlog:** S6, S7, S8, S9
**Findings:** Stakeholder test log, 19–20 August 2026 — Fix #9, Fix #15

## Context

The legacy student surface showed a points balance and a rewards catalog. Both
findings are about the same surface, and both are structural.

**Fix #9 — the balance is a browser formula.** The whole of
`frontend/src/lib/studentPoints.ts` at `bdce024`:

```ts
/** Total redeemable balance: streak bonus + attendance bonus (demo formula). */
export function getStudentTotalPoints(profile: Pick<StudentProfile, "attendance_streak" | "events_attended">): number {
  return profile.attendance_streak * 100 + profile.events_attended * 25;
}
```

Three things are wrong at once, and the third is the one that matters most.
It is computed in the browser from two summary counters, so no server-side
record of a balance exists. It has no history, so nothing can be audited,
reversed, or explained. And **the source calls it a demo formula in its own
docstring** — the legacy authors did not believe it was a balance either. It
was rendered to students as one.

**Fix #15 — the catalog is unreachable.** `studentRewardsCatalog.ts` defines
seven `StudentRewardItem`s across four categories (`linkedin`, `platforms`,
`certs`, `growth`), with costs on the `pointsCost` field:

| Costs, ascending |
|---|
| 2,500 · 3,200 · 5,000 · 8,500 · 12,000 · 15,000 · 45,000 |

Against attendance at 25 points per event, the **cheapest** item costs **100
events attended** and the dearest 1,800. Crediting the streak bonus at every
single event — 125 a time, the most favourable reading the formula admits — the
cheapest is 20 events and the dearest 360.

A student chapter does not run 100 events. The catalog was not a reward
structure; it was decoration, and it was decoration that made a promise.

There is nothing in this repository on either subject. A term search for
`reward`, `gamif`, and `studentPoints` over the whole tree returns zero.

## Decision

### Points are a fold over an append-only ledger, computed server-side

A `point_ledger_entry` table, tenant-scoped on the composite `(tenant_id, id)`
key ADR-0004 requires. Each entry records its amount, its **source** (the
attendance record it derives from), its reason, and the actor.

A balance is a fold over that ledger. It is never stored as a counter and never
computed by a client. A client that wants a balance asks the server for one.

### Points derive from recorded attendance and nothing else

An entry exists because an attendance record exists. There is no discretionary
grant, no client-submitted event, and no formula over summary counters.

### A reversal is a compensating entry, never a delete

Attendance recorded in error is corrected by an offsetting ledger entry that
names what it reverses. The ledger is append-only, so the evidence plane stays
append-only — the same property the outbox and job-event tables already have.

### Redemption is a command with an approval step

`requested → approved → fulfilled | denied | expired`. Redemption goes through
the durable command path like any other mutation; it is not a client-side
decrement of a client-side number.

### A catalog item with a real fulfilment cost needs a named budget owner and a funded balance

`reward_item` carries `fulfilment_cost`, `budget_owner_id`, and `funded`. An
item whose fulfilment costs the program money **cannot be listed** without both.

This is the structural form of the stakeholder's ask — name an owner or do not
ship rewards. It is a schema constraint rather than a policy sentence, because a
policy sentence is what the legacy had.

### The economy is calibrated against a stated, testable property

**The cheapest reward is reachable within N events**, where N is a parameter set
by the program owner. Proposed default: **3**. The property is asserted by a
test against the live catalog, so a catalog edit that breaks it fails rather
than shipping.

N itself is **not decided here** — it is D7, and the recommendation is a
recommendation. What is decided is that a number exists, that it is written
down, and that something checks it.

## Rationale

**Why a ledger and not a counter.** A counter cannot answer "why is my balance
this", cannot be reversed without losing history, and cannot be reconciled after
a bug. Every one of those questions arrives the first time a student disputes a
balance.

**Why the ledger is not the attendance record itself.** Points are a *policy*
over attendance, and policies change. Keeping them separate means a rule change
is new entries, not a rewrite of the evidence.

**Why the budget owner is a column.** The stakeholder's point was not that the
catalog was badly priced. It was that nobody had committed to honouring it.
Pricing is a number a person can fix; an unowned promise is a defect that
survives every repricing. Making it `NOT NULL` on a listable item is the only
form of the requirement that cannot be forgotten.

**Why the calibration is a test and not a guideline.** A guideline is how the
legacy got to 100 events. The arithmetic above was available to anyone who did
it; nobody did.

**Why this surface is designed in rather than archived.** It is the only part of
the product a student touches, and QR check-in — the mechanism that produces
attendance — is already scheduled for R2 (`MM-F02`). Archiving the engagement
surface would leave attendance collected with nothing built on it.

## Consequences

- `docs/architecture/engagement-model.md` carries the full ERD, the derivation
  rule, and the calibration arithmetic worked through.
- **MM-F03** records `studentPoints.ts` and `studentRewardsCatalog.ts` as
  `REPLACE`. A browser-computed balance is not a balance.
- **S6–S9** implement the tables, the ledger, the catalog, and redemption. All
  are R2, alongside attendance and QR — not Foundation.
- **D6** (budget owner) and **D7** (the N) are decisions outside engineering and
  block a *shipped* catalog, not the schema.
- The legacy catalog's seven items carry forward as content to re-price, not as
  values. None of the seven costs is retained.
- The legacy `getSortedCatalog` already sorts ascending by `pointsCost`, so
  free-to-give items sort first by construction rather than editorially. That
  property is worth keeping; nothing else in the file is.

## Alternatives considered

**Keep the formula, move it server-side.** Rejected. It fixes where the number
is computed and none of what is wrong with it: still no history, still no
reversal, still no audit.

**Re-price the catalog and ship it.** Rejected — this is D6/D7's decision, and
shipping a repriced catalog with no owner reproduces Fix #15 at a different
price point.

**Archive the student surface entirely.** Rejected. See Rationale. It would also
leave Fix #10 (the empty month grid) and Fix #16 (Student Connect) with nowhere
to land.
