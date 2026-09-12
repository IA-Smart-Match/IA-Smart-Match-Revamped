# Student-centric prioritization brief — stakeholder meeting, 12 September 2026

**Status:** research and planning only. This document changes no source file, adds
no route, writes no migration, and closes no open question. It exists so that the
next implementation plan can be written from a true statement of what already
exists.

**Input:** the stakeholder session of 12 September 2026 (Dr. Ann Wang, Yuka, Lisa),
relayed by Danny Tran, program owner of record. **Decisions recorded in that
session** are quoted in §1 and are treated here as direction, not as ratified
register closures — every one of them that contradicts a committed artifact is
named in §6 with the artifact it contradicts.

**Repositories in scope:** this one, and
`BrooklynD23/AI_Hackathon_CPP` — a separate team's Flutter prototype, assessed as a
pilot mobile base in
[`2026-09-12-mobile-pilot-base-assessment.md`](2026-09-12-mobile-pilot-base-assessment.md).

**Companion documents**

| | |
|---|---|
| Flyer → event database (OCR / phone photo) | [`research/2026-09-12-flyer-intake-research.md`](research/2026-09-12-flyer-intake-research.md) |
| The Flutter prototype as a mobile base | [`2026-09-12-mobile-pilot-base-assessment.md`](2026-09-12-mobile-pilot-base-assessment.md) |

---

## 1. What the session decided

Quoted from the relay, with no interpretation added:

> Next-phase MVP = **student-to-event matching plus push notifications/reminders
> that drive registrations**. Speaker matching, AI features, and mobile deferred.
>
> **Reward/points system is the strong second priority**; design a concrete
> low-cost scheme (Ann + Yuka).
>
> Registration backlog: **QR codes, flyer upload, video/summary, Handshake as one
> feed among many.**
>
> Faculty extra-credit workflow noted as a later add-on.
>
> Questions route through Ann and are consolidated so Pia and Lisa are asked once
> as a group, not individually.

Named needs behind those lines:

- **Yuka** — the reward/points system is the biggest value; the college is already
  discussing incentives and this could be the single place students earn points.
- **Ann** — the scheme must be affordable but motivating; points currently exist
  with nothing to spend on.
- **Lisa** — event creators should generate QR codes for registration *and*
  check-in directly (today a third person in Handshake is required), upload flyers
  directly, and attach a short video or summary (e.g. an Associate Dean "news
  flash").

---

## 2. The single most important finding

**The rewards system the meeting ranked second is the one that is nearly built,
and the matching the meeting ranked first is the one with no data to match on.**

That inversion should drive the sequencing, and §4 does.

### 2.1 Rewards — the engineering is done; the decision is not

Everything ADR-0013 specifies is committed and reachable over HTTP:

| Piece | Where |
|---|---|
| `attendance_record` write, coordinator-attested | `services/api/smartmatch_api/routers/attendance.py` |
| `point_ledger_entry` credited **in the same transaction** as the attendance | same file, `POST /v1/units/{unit_id}/events/{event_id}/attendance` |
| Balance as a fold over the ledger — no stored balance anywhere | `smartmatch_domain.rewards.fold_balance` |
| Catalog, per-item progress, redemption request, coordinator decision | `services/api/smartmatch_api/routers/rewards.py` (4 routes) |
| The calibration property `min(points_cost) ≤ N × points_per_event` | `smartmatch_domain.rewards`, asserted against the live catalog |
| D6 — budget owner | **CLOSED 2026-09-02**, Danny Tran, $5,000 placeholder ceiling (`docs/decisions/d6-rewards-budget-decision-record.md`) |

What is missing is **D7 ratification and a catalog with rows in it.**
`docs/decisions/pilot-decisions.md` §D7 carries 100 points per verified
attendance, bands 300 / 600 / 1,000, N = 3 — all marked *tentative*, and
`smartmatch_domain.rewards` carries those values verbatim rather than inventing
its own. A `reward_item` is listable only when it has a budget owner and
`funded IS TRUE`, which is D6's decision expressed as SQL, so **an unratified
catalog does not render as an empty page by accident — it renders as an empty
page by construction.**

Ann's observation that "points currently exist with nothing to spend on" is
therefore *literally* what the schema is enforcing, and the fix is a decision
plus a handful of rows, not a feature.

**This is the cheapest large win available.** §5 proposes a concrete low-cost
scheme for Ann and Yuka to accept, amend, or reject.

### 2.2 Student-to-event matching — there is no student side

Matching today is speaker ↔ speaker-request. `smartmatch_domain.scoring` composes
four registered factors (`industry_match`, `role_match`, `cba_semantic_topic`,
`proximity`) at registry version `2.0.0-approved-oq-cba-004`.

The event side already carries features: a closed twelve-term tag vocabulary
(`smartmatch_domain.event_vocabulary`, version `g3-2026-08-29`), a manual-event
category from a five-value approved set, `region`, `audience`, `speaker_topics`,
`location`.

The student side carries **nothing**. `user_account` is
`id, tenant_id, external_subject, email, suspended, created_at, version`. There is
no major, no program of study, no interest, no career goal, no availability, no
preferred region. Every join a matcher would need is absent.

So the MVP as stated is not "wire up the existing matcher to students". It is:

1. decide what a student may be asked and what may be stored about them (a D8-shaped
   question — see §6);
2. build the student profile that answers it;
3. *then* score, reusing `factor_registry` and the ADR-0016 composition rather than
   writing a second scorer.

Skipping (1) and (2) and shipping a recommender over the only signals that exist
today — a student's `attendance_record` history — would produce a surface that
recommends nothing to every student who has attended nothing, which is every
student on day one. ADR-0011 rule 1 makes the honest render of that the *absence*
of a recommendation list, so the feature would ship visibly empty.

### 2.3 Push notifications and reminders — nothing exists

`grep` for `push`, `reminder`, `fcm`, `apns`, `web push` across `python/`,
`services/` and `apps/` returns nothing. The only send path in the repository is
email outreach to **external professionals**, consent-gated through
`smartmatch_domain.consent`, and it cannot live-send: `build_email_provider`
refuses a live client, every shipped template is `content_status: synthetic`, and
no `contact_channel` row is seeded. Its three blockers (OQ-001 institutional From
domain, OQ-002 provider tenant, OQ-003 reviewed copy) are institutional, not
technical.

A reminder to a **student** is a different consent posture from outreach to a
professional whose address the research pipeline found, and it must not be built
by widening `smartmatch_domain.consent` — the same argument ADR-0014 makes for
`disclosure_consent` being its own table.

The infrastructure that *does* exist and that reminders should ride on: the
transactional outbox and dispatcher, the durable job state machine, and
`POST /operations/dispatch` driven by an external clock. A reminder is a scheduled
outbox row, not a new subsystem.

### 2.4 QR — Lisa's ask is roughly two-thirds built, in the wrong place

`routers/manual_events.py` already ships an event **feedback** QR: a
`event_feedback_qr` row with a `public_token`, a public `GET /q/{public_token}`
redirect that records a data-minimised open in `event_feedback_qr_open`, and a
client that renders the code itself with the `qrcode` npm package. Migration
`0035` is the shape.

Lisa needs the same mechanism pointed at two different verbs:

- **Registration QR** — a poster code a student scans to land on the registration
  surface. `event_registration` exists (migration `0026`) with
  `POST`/`DELETE /v1/units/{unit_id}/student/events/{event_id}/registration`, so
  the destination is already there. This is the smallest of the three asks.
- **Check-in QR** — `smartmatch_domain.checkin` issues and verifies tokens today,
  deterministically, with a 12-hour cap and a ≥32-byte secret enforced at both
  ends. **It is deliberately unwired**: `tests/unit/test_checkin_wiring.py` fails
  if either composition root imports it or if any served path mentions a check-in
  or a scan. Wiring it is blocked on **S11 and D8** (OQ-E04), because the copy on a
  scanning screen is a disclosure statement.

So "Lisa generates the QR herself" is available for registration now and for
check-in behind one decision.

### 2.5 Flyer upload and video/summary — no media plane exists

There is no object storage, no upload route, no `media` table, and no content-type
allowlist anywhere in this repository. A flyer upload and an attached video are the
same missing capability twice. See
[`research/2026-09-12-flyer-intake-research.md`](research/2026-09-12-flyer-intake-research.md);
the short version is that the *storage* is the work and the *OCR* is the easy part.

### 2.6 Handshake as one feed among many

`docs/plans/prep/campus-event-discovery-capability.md` already ranks discovery
sources and puts institution-gated student-org platforms at "**Ask the campus** —
only via partnership". Handshake is that row. It is a partnership question before
it is an adapter, and the crawler security gate (G3, threat model signed
2026-09-03, no crawl code scaffolded) stands in front of it either way.

Nothing about Handshake changes if the flyer path lands first — and the flyer path
is the one that needs no counterparty's permission, which is an argument for doing
it first that has nothing to do with how hard it is.

---

## 3. Current state, in one table

Read this as the correction to the README's status table, which predates several
shipped slices.

| Capability the meeting named | State today | The real blocker |
|---|---|---|
| Points earning, ledger, balance, catalog, redemption | **Built end to end** | D7 ratification + funded catalog rows |
| Attendance evidence | **Built** — coordinator-attested only | Scanner and roster-upload writers unbuilt (OQ-102) |
| Student event browse / agenda / register / cancel | **Built** (4 routes) | — |
| Per-event `.ics` download | **Built**, and refuses without an end time | OQ-002/OQ-003 — no parser reads `DTEND` |
| Event feedback QR + public redirect | **Built** | — |
| Registration QR | Not built; destination and QR precedent both exist | Small |
| Check-in QR flow | Token rule built, **deliberately unwired** | S11 + D8 (OQ-E04) |
| Student → event matching | **Not built, and unbuildable today** | No student profile data at all |
| Push notifications / reminders | **Nothing** | Channel consent for students; no D-equivalent recorded |
| Flyer upload | **Nothing** | No media plane; no storage decision |
| Flyer OCR → event | **Nothing** | Media plane first; then a review queue |
| Video / summary on an event | **Nothing** | Same media plane |
| Handshake feed | **Nothing** | Institutional partnership, then G3 |
| Mobile | **Nothing here**; a Flutter shell exists in the other repo | See the assessment doc |
| Faculty extra-credit workflow | **Nothing** | Explicitly "later add-on" |

---

## 4. Proposed priority order

The session's ranking is kept. The sequencing below reorders only *within* it, on
the ground that a track blocked on a decision should not hold a track that is
blocked on nothing.

### Track A — turn the points system on (weeks 0–2)

Highest value per unit of engineering in the entire backlog, because the
engineering is finished.

1. **Ratify D7** (Ann + Yuka; §5 proposes the numbers).
2. **Seed a funded catalog** for the pilot unit — rows in `reward_item` with a
   budget owner and `funded = true`, priced so the calibration property holds.
3. **Nothing else.** No new route, no migration, no frontend beyond what
   `GET /v1/units/{unit_id}/rewards` already serves.

Exit: a student with three recorded attendances sees a reachable reward and a real
progress line, and the "2,100 more for a mentor session" defect
(`engagement-model.md` §4) is closed by arithmetic that holds.

### Track B — the student profile, which is the actual MVP prerequisite (weeks 1–5)

Sequenced before matching because matching cannot start without it.

1. **A decision on what a student may be asked and what is stored.** This is
   D8-adjacent; §6 registers it as a proposed open question rather than answering
   it here.
2. A `student_profile` table, tenant-scoped on the composite key, holding only what
   the decision admits — proposed minimum: program of study, expected graduation
   term, and interests **drawn from the closed G3 vocabulary rather than free
   text**, so that a student's interests and an event's tags are the same twelve
   values and no embedding is needed for a first cut.
3. A student-owned read/write route. Identity from the token, never from a body,
   the way `routers/rewards.py` already does it.

Interests as closed-vocabulary terms is the load-bearing choice: it makes v1
matching a set-overlap over an approved vocabulary, which is explainable in one
sentence — a requirement `smartmatch_domain.one_sentence` and ADR-0016 already
impose on the speaker side — and it leaves ADR-0017's offline embedding path
available later without committing to it now.

### Track C — student → event matching (weeks 4–8, after B)

1. Register the student-side factors in `factor_registry` at a **new version**, the
   way the CBA pivot did. Never a second scorer, never weights as literals.
2. Compose them in `smartmatch_domain.scoring` beside `rank_cba_candidates`.
3. Expose them on the student surface as an ordering of the events
   `GET /v1/units/{unit_id}/student/events` already returns — **not** as a new
   catalog, and **not** as a percentage (OQ-CBA-005 forbids a match percentage in
   the UI, and that prohibition is not CBA-specific in spirit).
4. A student with no profile gets the existing time-ordered agenda, unranked, and
   the surface says so. Unknown never degrades to a default.

### Track D — reminders that drive registrations (weeks 4–8, parallel with C)

1. A **student channel consent** record — its own table, not a widening of
   `smartmatch_domain.consent`.
2. Reminders as scheduled rows on the **existing outbox**, dispatched by the
   existing `POST /operations/dispatch` clock. Two triggers only: *you registered
   and it is tomorrow*, and *registration for a thing you saved closes soon*.
3. **Channel order: in-app first, email second, push last.** Push requires a mobile
   client or a service worker, a credential, and a store presence; in-app requires
   none of those and the meeting deferred mobile. Building the reminder *domain*
   channel-agnostically means push becomes an adapter later rather than a rewrite.

### Track E — Lisa's registration surface (weeks 2–10, independently schedulable)

In ascending cost:

1. **Registration QR** — a second QR kind beside the feedback QR, pointing at the
   existing registration route. Smallest useful thing in this whole brief.
2. **Flyer upload** — needs the media plane; see the research doc.
3. **Short video / summary** — the same media plane, plus a hosting decision for
   video that is not the same decision as for an image.
4. **Check-in QR** — behind S11 and D8.
5. **Handshake** — behind an institutional partnership and G3.

### Track F — flyer OCR (weeks 6–12, after E2)

A photographed flyer becomes a **candidate for review**, never a published event.
The research doc argues this at length; the one-line version is that F-003 — the
legacy generator turning "Every Tuesday" into a confident invite thirty days out —
is exactly the failure an OCR pipeline reproduces at scale, and ADR-0012 already
requires that an event at `unresolved` precision has no identity key and cannot be
resolved against anything.

### Deferred, per the session

Speaker matching (already built; not being extended), AI features, mobile, faculty
extra-credit.

---

## 5. A concrete low-cost points scheme, for Ann and Yuka

Offered as a proposal to accept, amend, or reject. It is not a decision and nothing
in the repository is changed by it.

**Keep D7's earn rate: 100 points per verified attendance.** It is already the
value in code, and changing it changes nothing about affordability — only the
catalog does.

**Keep N = 3.** The cheapest listed reward must be reachable in three events, so
the cheapest band is 300 points.

**Price the catalog so that most of it costs the program nothing.** The
affordability problem is solved on the *fulfilment cost* axis, not the points axis:

| Band | Points | Character | Fulfilment cost | Examples |
|---|---|---|---|---|
| 300 | 3 events | Recognition and access | **$0** | Named on a chapter recognition list; priority seating; a digital badge on the student profile |
| 600 | 6 events | Access to people | **$0** | A reserved seat at a capped workshop; a coordinator-mediated introduction; a résumé review slot donated by a board member |
| 1,000 | 10 events | Something to hold | **low, capped** | Chapter merchandise; a covered competition entry fee; a covered conference student rate |

Three properties worth stating explicitly, because they are what makes it
affordable *and* motivating rather than one or the other:

1. **Free-to-give items sort first by construction** — ascending by `points_cost`,
   which `listable_items` already does. The student's first reachable reward costs
   the program nothing, which is precisely when a student is least invested.
2. **The $5,000 D6 placeholder is only ever exposed to the 1,000 band.** Two of
   three bands cannot draw on it at all.
3. **Access is the motivating currency, not merchandise.** Yuka's point that this
   could be "the single place students earn points" argues for rewards that are
   *scarce* rather than *bought* — a seat, an introduction, a slot. Those are
   things the chapter already controls and currently gives away unpriced.

**What Ann and Yuka have to actually decide:** the three fulfilment lists above,
who fulfils each row, and whether 100 / 300 / 600 / 1,000 survives contact with
the college's own incentive discussion. Once decided, Track A is rows in a table.

**What must not happen:** a catalog seeded with unfunded rows to make the page look
populated. `WHERE funded IS TRUE` will hide them, and the page will look broken
instead of honest.

---

## 6. Decisions this brief needs and does not make

Registered here as **proposed** questions with the `OQ-SC-` prefix. None is entered
in an existing register: `docs/plans/open-questions/cba-phase-deferred.md`'s last
issued id is OQ-CBA-064 and these are not CBA questions. Whoever opens the first
implementation plan should register them properly, in the register's own closure
shape.

Per the session's process note, **all of these route through Ann and are asked of
Pia and Lisa once, as a group.**

| Id | Question | Owner | Blocks | Safe default if unanswered |
|---|---|---|---|---|
| OQ-SC-01 | **D7 ratification** — is 100 / 300 / 600 / 1,000 with N = 3 the scheme, and what are the catalog rows? | Ann + Yuka, with Danny as D6 budget owner | Track A entirely | Catalog stays empty; `funded IS TRUE` already enforces this |
| OQ-SC-02 | What may a student be **asked** at profile setup, and what may be **stored**? Does program of study count as an education record? | Privacy / records, with Ann — this is D8's neighbour | Tracks B, C | No profile table; matching stays unbuilt |
| OQ-SC-03 | On what basis may SmartMatch **contact a student**, on which channels, and how is that consent revoked? | Ann + records | Track D | No student send path exists today, so the default holds itself |
| OQ-SC-04 | **D8** — the disclosure-consent policy, and what "FERPA-aware" asserts | Privacy / legal / records (already open as OQ-E01) | Check-in QR (OQ-E04), any peer-visible surface | Counts only, no student identifier in any response |
| OQ-SC-05 | Where does **uploaded media** live, who may read it, and how long is it kept? | Danny + records | Tracks E2, E3, F | No upload route |
| OQ-SC-06 | Is a photographed flyer **evidence** of an event, or a **claim** requiring a human? | Program owner | Track F | Claim requiring a human — the research doc's recommendation |
| OQ-SC-07 | Is there an institutional **Handshake partnership**, and on what terms? | Ann + Lisa + the campus | Track E5 | No adapter |
| OQ-SC-08 | Does the pilot **mobile app** ship to a store, or to a small named cohort? | Danny | Mobile track (deferred) | Deferred |

---

## 7. What this brief deliberately does not do

- It does not close, reword, or promote any register row. D7 stays tentative in
  `docs/decisions/pilot-decisions.md` until Ann and Yuka decide, and §5 is a
  proposal that names itself one.
- It does not write a migration, a route, or a factor. Track B's `student_profile`
  is described as a shape, not committed as one, because OQ-SC-02 decides its
  columns and a table written before the policy would be inventing the vocabulary
  the policy is supposed to choose — the argument OQ-E02 already makes for
  `disclosure_consent`.
- It does not authorize a crawler, a live provider, an upload, or a send.
  `ALLOW_LIVE_PROVIDERS` and `ALLOW_CLOUD_DEPLOY` stay false.
- It does not claim the mobile app is planned. The session deferred mobile; the
  assessment doc exists so that when mobile is undeferred, the question "do we
  start from that prototype" has a recorded answer instead of a fresh argument.
