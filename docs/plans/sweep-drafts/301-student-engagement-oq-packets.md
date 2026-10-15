> DRAFT — needs Danny (program owner of record) decision. Nothing here is decided.

# #301 — Student-engagement register: coverage table and first-slice packets

**Sources:** register `docs/plans/open-questions/student-engagement-deferred.md` (SC rows `:22-34`, SE rows `:40-61`; all OPEN — tentative-development, `:4-6`); plan `docs/plans/2026-09-14-student-engagement-program-plan.md` §3 (`:49-58`). Program owner of record: Danny Tran (`docs/decisions/owner-roster.md`, row 2). Plan names only "Student-engagement product owner" for slice 1 (`plan:51`), so the owner below is "program owner" unless the register names more.

**Coverage key:** PKT = decision packet in `docs/decision-packets/`; REC = dispositions in `docs/decisions/student-recommender-decision-record.md` (program-owner dispositions 2026-09-16, signatures pending `:216-218`); ADR = only listed in ADR-0026's slice table (`docs/architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md:95`), which is not a packet; none = no doc beyond the register.

## Table

| id | Question (short) | Blocks slice (plan §3) | Covered? |
|---|---|---|---|
| OQ-SC-01 | Ratify points schedule and funded catalog | none in §3; rewards beside slices (`plan:60`) | PKT `d6-d7-rewards.md` |
| OQ-SC-02 | What may a student be asked/stored | 6 (`plan:56`) | REC §4.1 (`:82`), confirmed 09-16 |
| OQ-SC-03 | Basis/channels/revocation for contacting a student | 7 (`plan:57`) | ADR only |
| OQ-SC-04 | D8 disclosure-consent; "FERPA-aware" meaning | none in §3; attendance QR (`plan:24`) | ADR only; named in #296 draft |
| OQ-SC-05 | Where uploaded media lives, access, retention | 4 (`plan:54`) | ADR only |
| OQ-SC-06 | Flyer: evidence or claim needing review | none (OCR out of flow, `plan:27`) | none |
| OQ-SC-07 | Handshake partnership | none (not in §3) | none |
| OQ-SC-08 | Mobile app to a store or a cohort | none (native mobile deferred, `plan:27`) | none |
| OQ-SC-09 | Store skip/not-interested | none in §3 | REC §4.5 (`:131`), deferred |
| OQ-SC-10 | Weekly digest cadence and copy owner | 7 | ADR only |
| OQ-SC-11 | Store what was recommended to whom | none in §3 | REC §4.5, deferred (scoped inside OQ-SE-19) |
| OQ-SC-12 | Eligible event with no mapped tag | none in §3 | REC §4.4 (`:122`), confirmed |
| OQ-SC-13 | May Event Host read aggregate demand | none in §3 | PKT `metrics-authz.md` |
| OQ-SE-01 | Approve student scoring registry | 6 | PKT `oq-se-01-02-student-ranking.md`; REC §4.2 |
| OQ-SE-02 | Wildcard contract | 6 | PKT same; REC §4.3 |
| OQ-SE-03 | Registration QR URL, actors, measurement | **1 (first slice)** | **none (ADR lists it only)** |
| OQ-SE-04 | Registered engagement metric + owning query | 8 | none; REC `:40` only maps objective to it; see #302 draft |
| OQ-SE-05 | ADR-0011 constituent fields/privacy | 8 | PKT `metrics-authz.md` names it as binding, does not answer; see #302 draft |
| OQ-SE-06 | W4 population | 8 | none; see #302 draft |
| OQ-SE-07 | Suppression threshold | 8 | PKT mentions only; see #302 draft |
| OQ-SE-08 | Roles for W4 aggregates/rows | 8 | PKT `metrics-authz.md` |
| OQ-SE-09 | Who files/reviews/approves host drafts | 2 | ADR only |
| OQ-SE-10 | Moderation and publication approval | 2 | ADR only |
| OQ-SE-11 | Private media policy | 4 | ADR only |
| OQ-SE-12 | Captions/transcripts for video | 4 | ADR only |
| OQ-SE-13 | Accommodation/perk vocabulary | 2 | ADR only |
| OQ-SE-14 | Announcement authoring/approval | 5 | ADR only |
| OQ-SE-15 | Responsive-web boundary; PWA later | 5 | ADR only |
| OQ-SE-16 | Digest producer identity/quota | 7 | ADR only |
| OQ-SE-17 | Digest schedule/idempotency/DST | 7 | ADR only |
| OQ-SE-18 | What is service uptake | none in §3 (only `plan:123`) | none |
| OQ-SE-19 | Registration/attendance as training label | none in §3 | REC §4.6 (`:143`), scoping path (b) approved |
| OQ-SE-20 | Who promotes a learned ranker | none in §3 | REC §4.7, owner named |
| OQ-SE-21 | Student x event interaction matrix | none in §3 | REC §4.8, "no" 09-16 |
| OQ-SE-22 | Log decisions with propensities | none in §3 | REC §4.9, "no" 09-16 |

Slice 3 (vertical flow) has no gate row of its own; it waits on slices 1-2 (`plan:53`). Of the first slice's gate (SE-03), no packet or disposition exists; of slice 8's (SE-04..08), only SE-08 has a packet (`metrics-authz.md`).

## First-slice gate: OQ-SE-03 (uncovered; highest leverage)

Slice 1 = registration QR/deep link into the existing authenticated registration action (`plan:21-23`, `plan:51`). Only gate: OQ-SE-03 (`register:42`). Today registration is `POST /v1/units/{unit_id}/student/events/{event_id}/registration`, role `{student}` only (`services/api/smartmatch_api/routers/student_events.py:11`, `:167`). Attendance/check-in QR is a different thing, behind S11/D8/OQ-SC-04 (`plan:23-25`). Three sub-questions; each is a separate packet.

### SE-03a — what exact URL does the QR encode?
- **Blocks:** slice 1 link/route/UI work and the threat model (`register:42`, closure evidence "URL/threat model").
- **Options:**
  1. The existing student event page URL for an approved published event, nothing added. No new route or token; the QR reveals nothing a browser link does not. Cannot tell QR from ordinary visits.
  2. Same URL plus a non-secret source marker (for example a query parameter). New client reading of the marker; marker is forgeable, so it is a label and not authorization.
  3. A server-issued opaque or signed link per event. Needs a token table or signing key, expiry/revocation, and a security-owner review; allows per-actor attribution.
- **Safe default in force:** QR is only an alternate link to an approved published event (`register:42`).
- **Who decides:** program owner + API/web + security owners (`register:42`).

### SE-03b — who may create and share the QR?
- **Blocks:** actor matrix in closure evidence (`register:42`); slice 2 interacts since host drafts are undecided (OQ-SE-09, `register:48`).
- **Options:**
  1. Connectors only (`admin`, `coordinator`), matching today's manual event writes (`register:48`).
  2. Connectors plus the Event Host (`volunteer`) for their own events. Needs an ownership check; host organization alone grants nothing (`plan:83-85`).
  3. Anyone with the event link can render a QR client-side (no server grant). No access control to design; no sharing record.
- **Safe default in force:** approved published events only; no new actor grant (`register:42`).
- **Who decides:** program owner + API/web + security owners.

### SE-03c — how is QR-attributed registration measured?
- **Blocks:** the "registered metric definition" closure evidence (`register:42`); ADR-0011 one-name/one-query rule (`docs/architecture/decisions/ADR-0011-accountable-numbers.md:61-80`).
- **Options:**
  1. No attribution. One registration count; QR and ordinary-link registrations are indistinguishable. Nothing new to reconcile.
  2. A source dimension on the same `event_registration` row (schema column, migration at current-head-plus-one, `plan:143-146`). One truth, split reporting; drill-down must reconcile (ADR-0011 rule 4).
  3. A separate QR-scan/visit count. Risks a second registration truth, which the register forbids ("without splitting the canonical registration truth", `register:42`).
- **Safe default in force:** no separate registration count (`register:42`).
- **Who decides:** program owner + metrics owner; connects to #302 (SE-04).

## Other rows gating later slices (not full packets here)
SE-09/10/13 (slice 2) and SC-05/SE-11/SE-12 (slice 4) have no packet; they gate slices after the first. Draft them after SE-03 closes if wanted.

## Open questions
1. SE-03a: URL form (1, 2 or 3)? — program owner + API/web + security.
2. SE-03b: which actors may create/share? — program owner + security.
3. SE-03c: measure QR attribution, and how without splitting registration truth? — program owner + metrics owner.
4. Is Danny the "student-engagement product owner" named for slice 1 (`plan:51`), or someone else? — Danny. Until named, "program owner — TBD" applies.
5. Do the REC dispositions (09-16) need signatures before SC-02/SE-01/SE-02 count as closed (`record:216-218`)? — Danny.
