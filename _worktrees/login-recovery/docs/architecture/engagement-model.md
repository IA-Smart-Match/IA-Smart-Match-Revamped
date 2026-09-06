# The engagement surface — attendance, points, rewards, and disclosure

The design for the one part of SmartMatch a student touches. It exists because
the stakeholder test log of 19–20 August 2026 found four defects on this surface
(Fix #9, #10, #11, #15) and the revamp had classified none of them — the surface
was neither ported nor archived, it was simply absent.

This document is a design, not an implementation. Nothing here ships in
Foundation. The tables land in **R2**, alongside attendance and QR check-in
(`MM-F02`), per the sequencing in `docs/plans/remaining-foundation-r1-work.md`.

**Decisions this document depends on and does not make:** D6 (a rewards budget
owner), D7 (the economy calibration N), D8 (disclosure-consent policy, including
what "FERPA-aware" asserts).

| Contract | Where |
|---|---|
| Points ledger, rewards, redemption | [ADR-0013](decisions/ADR-0013-attendance-derived-engagement.md) |
| Disclosure consent | [ADR-0014](decisions/ADR-0014-disclosure-consent.md) |
| Event times shown in the event's own zone | [ADR-0010](decisions/ADR-0010-event-temporal-model.md) |
| Every visible number is accountable | [ADR-0011](decisions/ADR-0011-accountable-numbers.md) |

---

## 1. Tables

Five new tables. Every one is tenant-scoped on the composite `(tenant_id, id)`
unique key ADR-0004 requires, with foreign keys from a tenant-owned child to a
tenant-owned parent carried as the composite pair — the convention proven in
`db/migrations/versions/0001_foundation_baseline.py` and enforced by
`tests/integration/test_schema_matches_migration.py`. A foreign key straight to
`tenant` stays single-column.

```
                      ┌──────────────────┐
                      │      event       │  (ADR-0010: instant + zone + precision)
                      └────────┬─────────┘
                               │
                      ┌────────▼──────────┐
                      │ attendance_record │  who was where, and how it was recorded
                      └────────┬──────────┘
                               │  derivation (§2)
                      ┌────────▼──────────┐
                      │ point_ledger_entry│  append-only; balance is a fold
                      └────────┬──────────┘
                               │
        ┌──────────────┐       │        ┌────────────────────┐
        │ reward_item  │◄──────┴───────►│    redemption      │
        │ cost, owner, │                │ requested→approved │
        │ funded       │                │ →fulfilled|denied  │
        └──────────────┘                │       |expired     │
                                        └────────────────────┘

        ┌────────────────────┐
        │ disclosure_consent │  subject, audience scope, purpose, granted/revoked
        └────────────────────┘  (gates peer visibility of attendance_record)
```

### `attendance_record`

The evidence. Who attended which event, when it was recorded, and by what
mechanism (QR scan, coordinator entry, import). It is the only input to points.

### `point_ledger_entry`

Append-only. Columns beyond the tenant key: `amount`, `source_attendance_id`,
`reason`, `actor`, `occurred_at`. **No balance column anywhere in the schema.**

### `reward_item`

`fulfilment_cost`, `budget_owner_id`, `funded`, `points_cost`. An item is
listable only with a budget owner and a funded balance — ADR-0013 makes this a
constraint rather than a policy, because a policy is what the legacy had.

### `redemption`

`requested → approved → fulfilled | denied | expired`, moved through the durable
command path. A CHECK constraint pins the vocabulary, exercised behaviourally
the way `tests/integration/test_check_constraints.py` exercises the CHECK
constraints already in the schema — the forbidden write *and* the permitted one,
since a rejection-only test passes against an inverted expression.

### `disclosure_consent`

`subject`, `audience_scope`, `purpose`, `granted_at`, `revoked_at`. Revocation
is a state, not a delete. See ADR-0014 for why this is not
`smartmatch_domain.consent` widened.

---

## 2. The derivation rule

**Points are a function of recorded attendance and nothing else.**

- Every `point_ledger_entry` names the `attendance_record` it derives from.
- There is no discretionary grant and no client-submitted entry.
- A balance is a fold over the ledger, computed server-side, on request. It is
  never stored and never computed in a browser.
- **A reversal is a compensating entry**, never a delete or an update. The
  evidence plane stays append-only, the same property the outbox and
  `job_event` tables already have.

This is the whole of Fix #9. The legacy computed the balance in the browser from
two summary counters, with no history and no server-side record.

---

## 3. Economy calibration

The stakeholder's finding was not that the catalog was priced badly. It was that
the catalog made a promise the program could not keep. The calibration turns
that into a property something can check.

### The legacy arithmetic, read from the source at `bdce024`

| | Value |
|---|---|
| Per event attended | **25** points — `events_attended * 25` |
| Per streak increment | **100** points — `attendance_streak * 100` |
| Catalog costs (`pointsCost`, ascending) | 2,500 · 3,200 · 5,000 · 8,500 · 12,000 · 15,000 · **45,000** |

| Earn rate | Events to the cheapest (2,500) | Events to the dearest (45,000) |
|---|---|---|
| Attendance only — 25/event | **100** | 1,800 |
| Attendance + streak every event — 125/event, the most favourable reading | **20** | 360 |

A student chapter does not run 100 events. It does not run 20. The catalog was
decoration that made a promise, and the arithmetic showing so was available to
anyone who did it.

### The property

> **The cheapest listed reward is reachable within N events of attendance
> alone**, where N is set by the program owner.

Formally: `min(points_cost over listed items) ≤ N × points_per_event`.

**Proposed default N = 3.** This is a recommendation, not a decision — it is
**D7**, and the owner is the program owner. What is decided (ADR-0013) is that
an N exists, is written down, and is asserted by a test against the live catalog,
so a catalog edit that breaks it fails rather than ships.

"Attendance alone" is deliberate. Crediting the streak makes the property depend
on a student's history rather than on the catalog, and a property that different
students evaluate differently cannot be a gate.

**Free-to-give items sort first by construction**, not editorially — ascending
by `points_cost`. The legacy `getSortedCatalog` already did this; it is the one
property of that file worth keeping.

---

## 4. The motivating view

> "400 pts — 2,100 more for a mentor session"

Specified as **progress to the nearest *reachable* reward**. "Reachable" is
load-bearing: against the legacy numbers this line would have read "2,100 more"
for something 84 events away, which is a discouraging fact dressed as
encouragement.

The view is only non-vacuous if §3's calibration holds. If it does not, the
honest render is the absence of a progress line, not a progress line toward
something unreachable — ADR-0011 rule 1.

---

## 5. The unified agenda

Fix #10: the student calendar was a month grid, and a mostly-empty month grid
looks like a dead chapter. That is a true signal about the *view*, not about the
chapter.

**Registered and open-to-register events in one time-ordered agenda.** Not a
month grid.

- Time-ordered, forward-looking, dense by construction — an agenda with four
  entries looks like four entries, not like twenty-six empty cells.
- Registration state is a property of the row, so a student sees what they are
  going to and what they could go to in one place.
- Region badges, so a multi-region chapter reads at a glance.
- **Times render in the event's own zone, with the zone named** — ADR-0010. An
  event at `date_only` precision renders as a date, not as midnight.

---

## 6. Disclosure and connection

Full contract in ADR-0014. On this surface:

- **"People you met at this event"** is kept, and is gated on an active
  disclosure consent covering the viewer.
- **The connect action is an opt-in LinkedIn URL** the person supplied
  themselves. No email, no phone, nothing the research pipeline found.
- **Mentor requests are coordinator-mediated.** A student requests, a
  coordinator decides, and the mentor is reached through the existing
  consent-governed path.
- Where consent limits the list, the surface **says the list is limited** rather
  than rendering an unexplained empty state — ADR-0011 rule 1 again.

---

## 7. Explicitly not built

**In-app chat.**

| | |
|---|---|
| Decision | Cut — not deferred |
| Made by | Dr. Ann Wang, in the 19–20 August 2026 session |
| Recorded | ADR-0014; `MM-F04` archives the legacy `StudentConnect.tsx` chat surface |

Recorded here with its owner and its date so it reads as a decision rather than
as something nobody got to. The legacy surface's one retained requirement is
"people you met at this event", which §6 covers.

---

## 8. What this does not settle

| | Owner |
|---|---|
| D6 — who owns the rewards budget | Program owner |
| D7 — the N in §3 | Program owner |
| D8 — disclosure-consent policy, and what "FERPA-aware" asserts | Privacy / legal / records |
| The re-priced catalog's actual costs | D6/D7, once both are answered |
| Visual design of any of it | Behind D-0 — `apps/web/DESIGN.md` has no owner |

The seven legacy catalog items carry forward as *content to re-price*, not as
values. None of the seven costs is retained.
