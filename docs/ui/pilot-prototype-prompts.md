# Pilot prototype prompt pack — NON-AUTHORITATIVE

> **This document is not a design, not a specification, and not a decision.**
>
> - **No generated UI code is merged through this work.** None. Not as a
>   scaffold, not as "just the components", not as a starting point.
> - **Generated artifacts stay external.** The prototype lives in whatever
>   external tool produced it and stays there.
> - **This repository stores exactly five things from this exercise:** this
>   prompt pack, a shareable link to the external prototype, selected
>   screenshots, a flow map, and UI-team review notes. Nothing else comes back.
> - **It closes nothing.** [`../../apps/web/DESIGN.md`](../../apps/web/DESIGN.md)
>   stays unresolved. **D-0** (assign a `DESIGN.md` owner) is still unassigned
>   and **D-1..D-11** are still open. This pack is input to that conversation,
>   not a substitute for it.

The purpose is narrow: give the UI team something clickable to react to, so the
Part 2 decisions in `DESIGN.md` are made against a concrete artifact instead of
against prose. A prototype that provokes a good objection has done its job.

---

## What the backend actually implements today

**Read this before writing any prompt, and before believing any screen.** The
prototype will show a lot of product. Almost none of it exists.

| Area | Annotation | Reality in this repository |
|---|---|---|
| Unit-scoped import submission (`POST /v1/units/{unit_id}/imports`) | **LIVE CONTRACT** | Implemented. Returns `202` with a job id. |
| Job status (`GET /v1/jobs/{job_id}`) | **LIVE CONTRACT** | Implemented. |
| Job event stream (`GET /v1/jobs/{job_id}/events`), resumable via `Last-Event-ID` | **LIVE CONTRACT** | Implemented. |
| Re-drive and abandon (`POST /v1/jobs/{job_id}/redrive`, `/abandon`) | **LIVE CONTRACT** | Implemented, reason required. |
| Health (`GET /api/health`), unsubscribe (`GET /u/{token}`, non-mutating) | **LIVE CONTRACT** | Implemented. |
| Matching, match runs, ranked results, scenario comparison | **PLANNED BACKEND** | Does not exist. Scoring fails closed; blocked on D1 / gate G1. |
| Attendance, QR check-in | **PLANNED BACKEND** | Does not exist. No attendance record, no QR mechanism. |
| Points ledger, rewards catalog, redemption, fulfilment | **PLANNED BACKEND** | Does not exist. No ledger, no catalog. |
| Consent, disclosure, people-met, mentor requests | **PLANNED BACKEND** | Does not exist. ADR-0014 records the model; no code implements it. |
| Gmail outreach, Google Calendar, ICS delivery | **PLANNED BACKEND** | Does not exist as a live integration. No Workspace tenant, no OAuth client. ICS *generation* exists as a domain function; nothing sends or synchronizes anything. |
| Engagement Load Index | **PLANNED BACKEND** (partly domain-implemented) | The ELI computation exists in `smartmatch_domain.eli`. There is no API, no professional-facing surface, and no correction path. |
| Research Scout | **FUTURE CONCEPT** | Does not exist. No source discovery, no extraction, no crawling of any kind. |
| Jarvis | **FUTURE CONCEPT** | Does not exist. |

`contracts/openapi/smartmatch.json` describes **seven operations, total**. That
is the whole live surface. Any screen in the prototype that implies more is
**PLANNED BACKEND** or **FUTURE CONCEPT**, and the prompts below require it to
be annotated as such in the design notes.

**Do not let a screenshot become evidence.** The single habit this revamp exists
to end is presenting proposed things as working ones, and a high-fidelity
prototype is the most efficient machine ever built for doing exactly that.

---

## How to use this pack

1. Every prompt below is prefixed by **the shared prefix**, used **verbatim**,
   with no edits, additions, or "improvements". The prefix carries the rules
   that make the output usable; a prompt sent without it produces a prototype
   that has to be thrown away.
2. Run the prompts in order. Prompt 1 establishes the shared components that
   prompts 2–8 reuse. Prompt 9 validates the whole set and reports gaps.
3. Record what comes back in the coverage table and the review-notes section at
   the end of this file. Leave the external artifacts external.

---

## The shared prefix

Use this text verbatim at the start of every one of the nine prompts.

```text
Create a clickable, neutral high-fidelity prototype for the IA West SmartMatch pilot. This is UX exploration for the UI team, not final branding or production code. Use replaceable design tokens, WCAG 2.2 AA contrast and interaction patterns, keyboard-complete navigation, visible focus, responsive layouts, and only clearly labeled synthetic data.

Annotate frames in design notes as LIVE CONTRACT, PLANNED BACKEND, or FUTURE CONCEPT; do not show those engineering labels as normal user-facing chrome. Every displayed value must identify its provenance as Observed, Inferred, Heuristic score, Model output, or Synthetic/demo. Unknown values must say "Unknown," never zero.

Show loading, empty, partial, denied, stale, and failed states. Never fabricate rankings, travel times, event times, successful sends, calendar synchronization, or completed writes. Use the event's named IANA time zone. Students are mobile-first; coordinators and administrators are desktop-first; professional screens are responsive.

Return a shareable clickable prototype, screen inventory, flow map, component inventory, accessibility notes, screenshots, and unresolved UI questions. Do not generate or replace production application code.
```

---

## Prompt 1 — Shared foundation and public screens

> *[shared prefix]*

Build the shared foundation and the public, pre-authentication screens: **public
landing**, **real authentication handoff**, **auth callback / loading**, **access
denied**, **not found**, and **unsubscribe confirmation**.

There is **no role selection**, **no canned demo accounts**, and **no role query
parameter**. Role derives from the session. A caller cannot pick who they are,
and the prototype must not offer an affordance that implies otherwise.

Build the shared components the rest of the pack reuses:

- A **provenance value** component — every displayed value carries Observed,
  Inferred, Heuristic score, Model output, or Synthetic/demo. Provenance belongs
  in the primitive that renders a value, not in a decoration someone remembers
  to add.
- An **unknown value** component — a value with no evidence renders as
  "Unknown", never `0`, never `0%`, never an em-dash styled to look like a
  measurement.
- An **event-local time** component — renders in the event's own IANA zone with
  the zone named beside the time; a date-only event renders as a date, never as
  midnight.
- A **same-query metric drill-down** — clicking an aggregate opens exactly the
  rows it was computed from. The row count equals the number clicked.
- A **confirmation dialog** used by every consequential action.
- An **approval history** component.
- A **status timeline** component.
- The **six non-happy states**: loading, empty, partial, denied, stale, failed.

---

## Prompt 2 — Student experience

> *[shared prefix]*

Build the student experience, mobile-first:

1. **Home** — upcoming actions, next event, the current **server-authored**
   points balance, and progress toward a **reachable** reward.
2. **Agenda** — registered and open-to-register events in one **time-ordered**
   list. **Not a month grid.**
3. **Event details** — named time zone, registration, accessibility
   information, calendar action.
4. **QR check-in** — phone-first, with data-minimization and consent copy.
5. **Attendance history** — with same-query drill-down.
6. **Points ledger** — append-only, showing *why* each credit, debit,
   correction, or refund exists.
7. **Rewards catalog** — the 300 / 600 / 1,000 pilot bands, with availability.
8. **Redemption detail and status timeline** — requested, approved, fulfilled,
   denied, cancelled, expired.
9. **People met** — explains when consent limits the results rather than
   silently returning a shorter list.
10. **Self-supplied LinkedIn disclosure** — with immediate revocation.
11. **Mentor request** — coordinator-mediated, with its status.

**Exclude, deliberately:** chat, scraped contact information, browser-computed
balances, points for logging in / referrals / streaks, and progress toward an
unreachable reward.

---

## Prompt 3 — Professional / speaker experience

> *[shared prefix]*

Build the professional / speaker experience, responsive:

1. **Home** — upcoming assignments and the actions needing attention.
2. **Assignment list and detail** — accept, decline with a reason, event-local
   time, and an ICS / calendar action.
3. **Availability, blackout, declared-capacity, and workload editor.**
4. **Engagement Load Index explanation** — showing observed inputs, inferred
   load, the 90-day history, the 45-day decay, the 30-day confirmed-future
   horizon, and the controls to correct the inputs.
5. **Profile** — self-published contact and LinkedIn consent.

Rules the design must hold:

- **Missing capacity shows as "Unknown"** and **prevents automatic assignment**.
  It is never treated as zero and never treated as unlimited.
- **Over 100% is ineligible; exactly 100% is allowed.**
- **Never expose another professional's private workload data.** A professional
  sees and corrects their own inputs, and nobody else's.

---

## Prompt 4 — Coordinator experience

> *[shared prefix]*

Build the coordinator experience, desktop-first — twelve views:

1. **Action-first home.** What needs doing comes before how things are going.
   **When the queue is small, name the people** rather than counting them.
2. **Event intake, event-quality review, staffing request.**
3. **Match review** — eligibility gates, factor explanations, travel quality,
   and the registry version the scores came from.
4. **Attendance and QR monitoring.**
5. **Outreach draft editor** — with an **immutable** recipient, subject, body,
   and attachment version.
6. **Coordinator approval, rejection, consent recheck, Gmail send status,
   retry, and audit trail.**
7. **Meeting proposal and Google Calendar approval** — attendees, visibility,
   description, and cancellation approval.
8. **Mentor-request review queue.**
9. **Reward-redemption fulfilment tickets.**
10. **Reward catalog editor** — create, edit, reorder, activate, deactivate,
    owner, point cost, fulfilment instructions.
11. **Point-rule editor** — verified-attendance earning rate, effective date,
    version, reason, audit history.
12. **Gmail and Calendar connection and health.**

Rules the design must hold:

- **Existing redemptions retain their point-cost snapshot.** Repricing a reward
  does not reprice a redemption already requested.
- **A deactivated reward blocks new requests but remains visible on existing
  tickets.** Deactivation is not deletion.
- **Balance corrections use audited ledger adjustments.** There is no field
  anywhere that sets a balance directly.

---

## Prompt 5 — Administrator and matching control center

> *[shared prefix]*

Build the administrator and matching control center, desktop-first — thirteen
views:

1. **Action and exception queue.**
2. **Events, opportunities, and data-quality review.**
3. **Professional directory.**
4. **Match-run history.**
5. **Ranked match detail.**
6. **Scenario comparison.**
7. **Funnel** — Matched → Contacted → Confirmed → Attended → Member Inquiry.
8. **Capacity, coverage, ELI, and travel-provider health.**
9. **Outreach approvals and delivery status.**
10. **Scheduling and Calendar operations.**
11. **Engagement operations** — attendance, rewards, mentor requests,
    disclosures.
12. **Imports, jobs, SSE progress, parked work, redrive, abandon.**
13. **Governance** — registry versions, adaptive-weight proposals, shadow
    results, promotion and rollback, retention classes, integrations, and the
    disclosure audit.

Rules the design must hold:

- **Every aggregate opens the exact rows used to compute it** — the same rows,
  from the same query, not a re-query with similar-looking filters.
- **Every heuristic score names its registry version and its factor
  provenance.**
- **Adaptive promotions show holdout, golden-case, and fairness results**, and
  **enforce an eight-percentage-point maximum total weight movement**.

---

## Prompt 6 — Operator command-path flow

> *[shared prefix]*

Build the operator command path end to end. **This is the one flow backed by a
live contract**, so it is the flow the prototype has the least excuse to get
wrong:

**Unit-scoped import submission with dry-run as the default → 202 accepted →
job status → resumable SSE event stream → success, partial, policy failure,
provider failure, timeout, or parked → reason-required redrive or abandon.**

Show, as designed states:

- **403, 404, 409**, and **429 with the actual retry window** — the real number
  of seconds, never a generic "try again later".
- **Stale connection**, and **reconnect from `Last-Event-ID`**.
- **Explicit lack of authorization** — the operator is told they are not
  authorized, rather than shown an empty screen that looks like no data.

**Closing the browser must not imply cancellation.** The job continues. The
design must say so, because the opposite assumption is the natural one and it is
wrong.

---

## Prompt 7 — Research Scout (FUTURE CONCEPT)

> *[shared prefix]*

Build the Research Scout flow, annotated throughout as **FUTURE CONCEPT**:

**Source proposal → permitted scope, robots and safety, budget, provider mode,
and human approval → run progress → extracted-event quarantine → duplicate and
entity-resolution review → provenance inspection → approve, correct, or
reject.**

Constraints the design must hold:

- **Do not imply that live crawling is currently authorized.** It is not.
- **No arbitrary URL crawling.** Sources are proposed and approved, never typed
  in and fetched.
- **No credentials.** The flow never asks for, stores, or uses a login to reach
  a source.
- **No automatic publication.** Nothing extracted reaches a matchable or
  publishable state without a human approving it.
- **Every extracted field retains its source evidence**, inspectable from the
  field itself.

---

## Prompt 8 — Jarvis (FUTURE CONCEPT)

> *[shared prefix]*

Build the Jarvis surface, annotated throughout as **FUTURE CONCEPT**. Jarvis is
**an accelerator over normal workflows, not a parallel system**:

**Editable typed intent → autonomy tier → proposed actions → scenario analysis →
affected records → approval or rejection with a reason → open the ordinary
editor or queue → execute through the same confirmation and authorization path →
audit and failure explanation.**

Include **agent-assisted outreach drafting** — a draft opens in the ordinary
outreach draft editor from Prompt 4, and goes through the ordinary approval.

The hard constraint: **ambient conversation must never directly send an email,
change a calendar, promote model weights, alter reward values, or execute any
other consequential action.** Every consequential action leaves the
conversational surface and appears in the same confirmation UI the conventional
screens use.

---

## Prompt 9 — Cross-role prototype validation

> *[shared prefix]*

Connect and validate the following six cross-role flows across the prototype
built in Prompts 1–8:

1. **Event intake → matching → coordinator approval → consent check → Gmail
   outreach.**
2. **Professional acceptance → Calendar / ICS → attendance.**
3. **QR attendance → 100-point ledger credit → reward redemption → coordinator
   fulfilment → student notification.**
4. **Disclosure consent → people met → LinkedIn visibility or mentor request →
   revocation.**
5. **Import → job stream → failure → authorized redrive.**
6. **Outcome feedback → shadow weight proposal → evaluation → human promotion →
   rollback.**

For each flow, identify:

- the **actor**,
- the **approval boundary**,
- the **data disclosed**,
- the **audit event**,
- the **terminal states**,
- the **failure recovery**, and
- the **screens affected**.

**Report any screen or transition that is missing from the prototype.** A gap
found here is the most useful output of the whole pack; do not paper over one by
inventing a screen to fill it.

---

## Coverage table

Every screen named in the prompts above, mapped to the prompt that produces it,
with the annotation the design notes must carry. **The plan requires that every
approved prototype screen maps to a prompt** — a screen that appears in the
prototype and not in this table is either an unrequested addition or a missing
row, and either way it needs resolving before the UI team reviews the pack.

### Prompt 1 — shared foundation and public screens

| Screen / component | Prompt | Annotation |
|---|---|---|
| Public landing | 1 | PLANNED BACKEND |
| Real authentication handoff | 1 | PLANNED BACKEND |
| Auth callback / loading | 1 | PLANNED BACKEND |
| Access denied | 1 | LIVE CONTRACT (the API refuses today) |
| Not found | 1 | LIVE CONTRACT |
| Unsubscribe confirmation | 1 | LIVE CONTRACT (`GET /u/{token}`, non-mutating) |
| Provenance value component | 1 | Shared component |
| Unknown value component | 1 | Shared component |
| Event-local time component | 1 | Shared component |
| Same-query metric drill-down | 1 | Shared component |
| Confirmation dialog | 1 | Shared component |
| Approval history | 1 | Shared component |
| Status timeline | 1 | Shared component |
| Six non-happy states (loading, empty, partial, denied, stale, failed) | 1 | Shared component |

### Prompt 2 — student

| Screen | Prompt | Annotation |
|---|---|---|
| Student home (actions, next event, balance, reachable-reward progress) | 2 | PLANNED BACKEND |
| Time-ordered agenda | 2 | PLANNED BACKEND |
| Event details | 2 | PLANNED BACKEND |
| QR check-in | 2 | PLANNED BACKEND |
| Attendance history | 2 | PLANNED BACKEND |
| Points ledger (append-only) | 2 | PLANNED BACKEND |
| Rewards catalog (300 / 600 / 1,000) | 2 | PLANNED BACKEND |
| Redemption detail and status timeline | 2 | PLANNED BACKEND |
| People met | 2 | PLANNED BACKEND |
| LinkedIn disclosure and revocation | 2 | PLANNED BACKEND |
| Mentor request and status | 2 | PLANNED BACKEND |

### Prompt 3 — professional / speaker

| Screen | Prompt | Annotation |
|---|---|---|
| Professional home | 3 | PLANNED BACKEND |
| Assignment list and detail (accept / decline with reason, ICS) | 3 | PLANNED BACKEND |
| Availability, blackout, declared-capacity, workload editor | 3 | PLANNED BACKEND |
| Engagement Load Index explanation and correction | 3 | PLANNED BACKEND (ELI computation exists in the domain; no API, no surface) |
| Profile, contact and LinkedIn consent | 3 | PLANNED BACKEND |

### Prompt 4 — coordinator (twelve views)

| # | View | Prompt | Annotation |
|---|---|---|---|
| 1 | Action-first home | 4 | PLANNED BACKEND |
| 2 | Event intake, event-quality review, staffing request | 4 | PLANNED BACKEND |
| 3 | Match review (gates, factors, travel quality, registry version) | 4 | PLANNED BACKEND |
| 4 | Attendance and QR monitoring | 4 | PLANNED BACKEND |
| 5 | Outreach draft editor (immutable version) | 4 | PLANNED BACKEND |
| 6 | Approval, rejection, consent recheck, send status, retry, audit trail | 4 | PLANNED BACKEND |
| 7 | Meeting proposal and Calendar approval, incl. cancellation | 4 | PLANNED BACKEND |
| 8 | Mentor-request review queue | 4 | PLANNED BACKEND |
| 9 | Reward-redemption fulfilment tickets | 4 | PLANNED BACKEND |
| 10 | Reward catalog editor | 4 | PLANNED BACKEND |
| 11 | Point-rule editor | 4 | PLANNED BACKEND |
| 12 | Gmail and Calendar connection and health | 4 | PLANNED BACKEND |

### Prompt 5 — administrator and matching control center (thirteen views)

| # | View | Prompt | Annotation |
|---|---|---|---|
| 1 | Action and exception queue | 5 | PLANNED BACKEND |
| 2 | Events, opportunities, data-quality review | 5 | PLANNED BACKEND |
| 3 | Professional directory | 5 | PLANNED BACKEND |
| 4 | Match-run history | 5 | PLANNED BACKEND |
| 5 | Ranked match detail | 5 | PLANNED BACKEND |
| 6 | Scenario comparison | 5 | PLANNED BACKEND |
| 7 | Matched → Contacted → Confirmed → Attended → Member Inquiry funnel | 5 | PLANNED BACKEND |
| 8 | Capacity, coverage, ELI, travel-provider health | 5 | PLANNED BACKEND |
| 9 | Outreach approvals and delivery status | 5 | PLANNED BACKEND |
| 10 | Scheduling and Calendar operations | 5 | PLANNED BACKEND |
| 11 | Engagement operations (attendance, rewards, mentor requests, disclosures) | 5 | PLANNED BACKEND |
| 12 | Imports, jobs, SSE progress, parked work, redrive, abandon | 5 | **LIVE CONTRACT** |
| 13 | Governance (registry versions, weight proposals, shadow results, promotion / rollback, retention classes, integrations, disclosure audit) | 5 | PLANNED BACKEND |

### Prompt 6 — operator command path

| Screen / state | Prompt | Annotation |
|---|---|---|
| Unit-scoped import submission, dry-run default | 6 | **LIVE CONTRACT** |
| 202 accepted with job id | 6 | **LIVE CONTRACT** |
| Job status | 6 | **LIVE CONTRACT** |
| Resumable SSE event stream | 6 | **LIVE CONTRACT** |
| Terminal states: success, partial, policy failure, provider failure, timeout, parked | 6 | **LIVE CONTRACT** |
| Reason-required redrive | 6 | **LIVE CONTRACT** |
| Reason-required abandon | 6 | **LIVE CONTRACT** |
| 403 / 404 / 409 refusals | 6 | **LIVE CONTRACT** |
| 429 with the actual retry window | 6 | **LIVE CONTRACT** |
| Stale connection and reconnect from `Last-Event-ID` | 6 | **LIVE CONTRACT** |
| Explicit lack of authorization (not an empty screen) | 6 | **LIVE CONTRACT** |
| "Closing the browser does not cancel" affordance | 6 | **LIVE CONTRACT** |

### Prompt 7 — Research Scout

| Screen | Prompt | Annotation |
|---|---|---|
| Source proposal | 7 | FUTURE CONCEPT |
| Permitted scope, robots / safety, budget, provider mode, human approval | 7 | FUTURE CONCEPT |
| Run progress | 7 | FUTURE CONCEPT |
| Extracted-event quarantine | 7 | FUTURE CONCEPT |
| Duplicate and entity-resolution review | 7 | FUTURE CONCEPT |
| Provenance inspection | 7 | FUTURE CONCEPT |
| Approve / correct / reject | 7 | FUTURE CONCEPT |

### Prompt 8 — Jarvis

| Screen | Prompt | Annotation |
|---|---|---|
| Editable typed intent | 8 | FUTURE CONCEPT |
| Autonomy tier | 8 | FUTURE CONCEPT |
| Proposed actions | 8 | FUTURE CONCEPT |
| Scenario analysis | 8 | FUTURE CONCEPT |
| Affected records | 8 | FUTURE CONCEPT |
| Approval / rejection with reason | 8 | FUTURE CONCEPT |
| Hand-off into the ordinary editor or queue | 8 | FUTURE CONCEPT |
| Execution through the same confirmation and authorization path | 8 | FUTURE CONCEPT |
| Audit and failure explanation | 8 | FUTURE CONCEPT |
| Agent-assisted outreach drafting | 8 | FUTURE CONCEPT |

**Prompt 9 produces no screens of its own.** It validates and connects the
screens above and reports what is missing.

---

## Cross-role flow checklist

**The plan requires that every cross-role flow is covered.** Tick a row only
when the flow is clickable end to end in the prototype *and* its actor, approval
boundary, disclosed data, audit event, terminal states, and failure recovery are
each identified in the flow map.

| # | Flow | Prompts involved | Covered? |
|---|---|---|---|
| 1 | Event intake → matching → coordinator approval → consent check → Gmail outreach | 4, 5, 9 | ☐ |
| 2 | Professional acceptance → Calendar / ICS → attendance | 3, 4, 9 | ☐ |
| 3 | QR attendance → 100-point ledger credit → reward redemption → coordinator fulfilment → student notification | 2, 4, 9 | ☐ |
| 4 | Disclosure consent → people met → LinkedIn visibility or mentor request → revocation | 2, 4, 9 | ☐ |
| 5 | Import → job stream → failure → authorized redrive | 5, 6, 9 | ☐ |
| 6 | Outcome feedback → shadow weight proposal → evaluation → human promotion → rollback | 5, 9 | ☐ |

Boxes are unticked because **the prompts have not been run**. Nothing in this
pack has been executed, and no prototype exists at the time of writing.

---

## Unresolved UI questions

Carried forward from `DESIGN.md` Part 2, plus the ones this pack raises. None is
answered here.

| # | Question | Source |
|---|---|---|
| D-1 | Design system: adopt, adapt, or build | `DESIGN.md` Part 2 |
| D-2 | Visual language — typography, color, spacing, density | `DESIGN.md` Part 2 |
| D-3 | Provenance label treatment on a dense table where every cell needs one | `DESIGN.md` §1.1, Part 2 |
| D-4 | Information density across 13 control-center views | `DESIGN.md` Part 2 |
| D-5 | Portal navigation model — one shell or four experiences | `DESIGN.md` Part 2 |
| D-6 | Treatments for the six non-happy states | `DESIGN.md` Part 2 |
| D-7 | Responsive and device targets on the coordinator / administrator side | `DESIGN.md` Part 2 (student side partly settled) |
| D-8 | Charting approach, and how a chart of heuristic scores says so | `DESIGN.md` Part 2 |
| D-9 | Rewards and points presentation | `DESIGN.md` Part 2 |
| D-10 | How consent is asked for, and how a limited list explains itself | `DESIGN.md` Part 2 |
| D-11 | Agenda density, grouping, and region badges | `DESIGN.md` Part 2 |
| — | How does a prototype show LIVE CONTRACT / PLANNED BACKEND / FUTURE CONCEPT to a reviewer without those labels leaking into user-facing chrome? | This pack |
| — | What does the student home show when nothing in the catalog is reachable — no progress line at all, and how is that not read as an error? | This pack; `engagement-model.md` §4 |
| — | How does a coordinator's "name the people when n is small" home degrade as n grows, and where is the threshold? | `DESIGN.md` §1.11 |
| — | How does the operator command path communicate "closing the browser does not cancel" without a modal nobody reads? | This pack |

---

## UI-team review notes

**Empty. The UI team has not reviewed this pack.**

Record notes below as they arrive, attributed and dated. Do not edit the prompts
in place in response to a note — a prompt that produced a reviewed artifact
should stay recoverable, so append a revision instead.

| Date | Reviewer | Prompt / screen | Note | Disposition |
|---|---|---|---|---|
| — | — | — | — | — |

### External artifacts

Fill these in once the prompts have been run. They are blank because nothing has
been produced, not because someone forgot.

| Artifact | Location |
|---|---|
| Shareable prototype link | *not yet produced* |
| Selected screenshots | *not yet produced* |
| Flow map | *not yet produced* |
| Screen inventory returned by the tool | *not yet produced* |
| Accessibility notes returned by the tool | *not yet produced* |
