# R2 engagement — open questions carried by the attendance-summary slice

**Date:** 2026-09-04 · **Slice:** R2 engagement scaffold (attendance summary +
QR check-in token)

Every item here is a decision a human has to make that engineering could not
make for them. None of them stopped the slice: each carries a **safe default**
that is implemented, and the default is chosen so that being wrong about it
degrades into *reporting less* rather than into *disclosing more*.

That asymmetry is the whole policy on this surface. A deferral that fails toward
a narrower response costs a coordinator a number they wanted; a deferral that
fails toward a wider one puts a named student's attendance in front of somebody
whose right to see it nobody has established, and no later decision can undo
that. Attendance is a record of where a person physically was.

Nothing here is a placeholder that *reports success*. Where a decision is
missing, the code returns a count or refuses, and it says which decision it is
waiting on.

---

## What this slice did ship

| | |
|---|---|
| `GET /v1/units/{unit_id}/engagement/attendance-summary` | Counts of one unit's `attendance_record` rows. `{admin, coordinator}`, unit-scoped, no tenant-wide reach. |
| `smartmatch_domain.checkin` | Issue/verify for a QR check-in token. Pure, deterministic, unwired — no route imports it. |
| `smartmatch_domain.attendance` | The fold: total derived from the breakdown, and a refusal for counts that cannot describe one set of rows. |
| `smartmatch_persistence.engagement` | The reader. Counts subjects and events with `count(distinct …)` and never selects either column. |

No migration. No change to the rewards surface. No frontend. No crawler.

---

## OQ-E01 — D8: the disclosure-consent policy, and what "FERPA-aware" asserts

**Question.** Who may see *whose* attendance, on what basis, for what purpose,
and what does the phrase "FERPA-aware" commit this system to?

**Why engineering cannot answer it.** It is a privacy, legal, and records
decision with a named owner — `docs/architecture/engagement-model.md` §8 puts D8
with "Privacy / legal / records", and ADR-0014 is the contract that would carry
the answer. An engineer choosing a disclosure rule would be choosing, on behalf
of an institution, which student records leave which room.

**Safe default, implemented.** The summary returns **counts only**, and that is
structural rather than a filter anyone is trusted to apply:
`EngagementRepository.attendance_counts_for_unit` aggregates `subject_id` inside
the database and never projects it, so there is no path through which a student
identifier could reach a response body.
`tests/contract/test_engagement_api.py::test_the_response_names_no_student`
asserts it against the raw response text rather than against the model, so
adding a field would fail even if the model were widened deliberately.

**What would lift it.** A ratified D8 / ADR-0014 naming the audience scope and
purpose vocabulary. The `disclosure_consent` table (`engagement-model.md` §1) is
the shape it would need, and it does not exist: migration `0009` deliberately
created three of the five tables and said so.

## OQ-E02 — S10: `disclosure_consent`, the table that gates peer visibility

**Question.** What does one consent record contain — subject, audience scope,
purpose, `granted_at`, `revoked_at` — and what exactly does each audience scope
admit?

**Why engineering cannot answer it.** It is D8's schema. Writing the table
before the policy would be inventing the vocabulary the policy is supposed to
choose, and a CHECK constraint over guessed values is harder to correct than an
absent table.

**Safe default, implemented.** The table is not created, and nothing in this
slice pretends it exists. `engagement-model.md` §6's "people you met at this
event" surface is not built, the connect action is not built, and no route
returns a peer. Revocation being *a state and not a delete* is recorded in the
design and will be enforced by the migration that lands it, not approximated
here.

**What would lift it.** D8 first (OQ-E01), then a migration adding
`disclosure_consent` with the audience-scope vocabulary as a CHECK constraint,
in the shape `0009` used for `ck_attendance_record_method`.

## OQ-E03 — live student data on this surface

**Question.** When does `attendance_record` hold rows about real, identified
students rather than synthetic ones?

**Why engineering cannot answer it.** The synthetic-pilot development
authorization (2026-09-03) is what currently permits an `attendance_record`
writer at all, and it permits a *synthetic* one. Admitting live student records
is a data-governance decision that D8 gates and that the pilot authorization
does not grant.

**Safe default, implemented.** The only writer in the codebase is
`smartmatch_persistence.attendance.AttendanceRepository`, reachable from the
demo seed flow and from no route — its own docstring states this and no route
imports it. This slice adds a **reader** and no writer: there is no `POST` under
`/v1/units/{unit_id}/engagement/…`, and
`tests/unit/test_matching_fail_closed.py::test_the_engagement_router_is_read_only`
fails if one appears. Every row in the contract test belongs to a throwaway
tenant it creates and deletes.

**What would lift it.** D8, plus a records agreement naming retention and
deletion for attendance evidence — which `0009` already made deliberately
awkward to satisfy by deleting rows: both foreign keys onto `attendance_record`
are `ON DELETE RESTRICT`, because attendance is evidence.

## OQ-E04 — B08: the QR check-in flow (blocked on S11 and D8)

**Question.** What does a student see when they scan, what does the surface say
about what is being recorded, and what does the coordinator's issuing surface
look like?

**Why engineering cannot answer it.** `docs/plans/frontend-broken-buttons.md`
B08 names the blockers: **S11** and **D8 (minimization copy)**. The copy on a
scanning screen is a disclosure statement, which is D8's, and the flow itself is
a design decision behind D-0 (`apps/web/DESIGN.md` has no owner).

**Safe default, implemented.** The *token rule* landed and the *flow* did not.
`smartmatch_domain.checkin` issues and verifies, deterministically, with no
clock and no entropy source of its own; `tests/unit/test_checkin_wiring.py`
asserts that neither composition root imports it and that no served route path
mentions a check-in or a scan. The payload names a tenant, a unit and an event —
and no student, because a QR code is handed to a room and everything in it is
public to that room.

**What this deliberately did not do.** It did not port the legacy "referral QR"
(B36) and it did not reuse `/api/qr/stats`. B08 says explicitly: "do not reuse
`/qr/stats`."

## OQ-E05 — who issues a check-in token, and where its secret lives

**Question.** Which component mints tokens, under which secret, and what is the
rotation procedure?

**Why engineering cannot answer it.** It is a secrets-management decision tied
to a deployment, and it only becomes urgent when OQ-E04 unblocks — the same
shape as `r4-outreach-deferred.md`'s OQ-005 for the unsubscribe secret.

**Safe default, implemented.** The module takes the secret as an argument and
reads no environment variable — it cannot, since the import-linter "Domain is
pure" contract forbids it `os` entirely. It refuses a secret shorter than 32
bytes at **both** issue and verify, so a deployment that weakened its secret
fails on the next scan rather than quietly accepting forgeries. Token life is
capped at 12 hours (`MAX_CHECK_IN_TOKEN_TTL`): a token outliving its event is a
credential to a room nobody is standing in.

## OQ-E06 — is a check-in token single-use, and who remembers?

**Question.** May one token admit many scans (the "reusable token" v1.1 §1.9
describes), or must each scan be distinguishable and revocable?

**Why engineering cannot answer it.** It is a product decision about how
check-in is run at an event — one code on a wall, or one per attendee — and it
has an operational cost either way.

**Safe default, implemented.** The token is reusable within its window, which is
what §1.9 describes, and it carries a caller-supplied `nonce` so that whatever
later issues tokens *can* distinguish and supersede them without this module
holding any state. No replay store exists, and none is faked: the duplicate
protection that actually matters is already at the evidence layer, where
`uq_attendance_record_subject_event` refuses a second row for the same student
at the same event outright.

## OQ-E07 — D7's earn rate is still tentative, and this surface does not touch it

**Question.** What is N, the calibration in `engagement-model.md` §3?

**Why engineering cannot answer it.** It is the program owner's, and it is
recorded tentative in `docs/decisions/pilot-decisions.md` §D7.

**Safe default, implemented.** The attendance summary reads
`point_ledger_entry` not at all and reports no points. A count of evidence is
not a claim about anybody's balance, and the balance already has one honest home
in `routers/rewards.py` — including its `unknown` state, which a second
computation of the same thing would be free to disagree with.
