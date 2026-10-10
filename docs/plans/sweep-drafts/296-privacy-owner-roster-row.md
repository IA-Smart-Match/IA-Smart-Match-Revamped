> DRAFT — needs Danny decision. Nothing here is decided.

# #296 — Candidate roster row: B26 privacy owner

## Where the roster lives
- `docs/decisions/owner-roster.md` (table at `:20-26`, status CLOSED for rows 1-7). Row 1 "Privacy owner (P9 Gate B)" is already named, scoped to P9 Gate B only (contact fields on the `events` dataset) and closed 2026-09-02 (`owner-roster.md:22`; `docs/decisions/p9-gate-b-contact-fields-worksheet.md:24`).
- The B26 gap is a different, unfilled role: "A named privacy owner. ... None is named (D5, D8)." (`docs/plans/2026-09-22-b26-self-service-availability-plan.md:630`, §10 row 2).
- Discrepancy to settle: the OQ-CBA texts say "the named privacy owner"; the roster already has a Gate-B-scoped entry. Whether that entry covers B26 questions or a new/separate role is needed is Danny's call (the repo does not say).
- The roster file says it is CLOSED; adding a row means reopening or adding a new section. Placement TBD.

## Candidate row (draft; Danny names)
| # | Role | Named | What it blocks today | Closes via |
|---|---|---|---|---|
| 8 | **Privacy owner (B26 / Speaker accounts)** | `<TBD — Danny names>` | Speaker accounts go-live; OQ-CBA-011/015; Connector self-invite decision; OQ-SC/SE rows listed below | Written answers to the rows below, recorded in `docs/plans/open-questions/cba-phase-deferred.md` |

## What it unblocks (with citations)
1. Speaker accounts go-live / storing Speakers' real emails and passwords, self-service consent beyond the pilot: B26 plan §10 row 2 (`2026-09-22-b26-self-service-availability-plan.md:630`). Also needs Ann/Pia/Lisa (§10 row 1) and hostname (row 4); SPEAKER_PORTAL stays off meanwhile.
2. OQ-CBA-011 (may SmartMatch store a speaker's personal Contact Email) and OQ-CBA-015 (keep or remove the field; shipped as keep-and-discard, "to be confirmed jointly with the privacy owner's OQ-CBA-011 answer"): `docs/plans/open-questions/cba-phase-deferred.md:23`, `:27`, `:146`.
3. OQ-CBA-035 (self-service opt-in) and OQ-CBA-043 name "the named privacy owner" as co-owner: `cba-phase-deferred.md:47`, `:54`.
4. T6b-1 §11 risk "Connector self-invite": "The privacy owner (parent §10 row 2) decides whether the issuer must differ from the consent recorder." `docs/archive/plans/b26-tracks/T6b-1-plan.md:501`.
5. Student-engagement rows that cite a records/privacy owner: OQ-SC-04, OQ-SC-13, OQ-SE-04, OQ-SE-19 (`docs/plans/open-questions/student-engagement-deferred.md:25`, `:34`, `:43`; OQ-SE-19 per grep, line not captured; OQ-SC-04/13 are "OQ-SC", the issue says "OQ-SE rows" loosely). Not exhaustive.

Naming does not close the gates; it makes them runnable (`owner-roster.md:17-18`).

## Open questions
1. Who is named? — Danny (this draft suggests no one).
2. Is the existing roster row 1 (Gate B) enough, or is this a new role/row? — Danny.
3. Where does the row go, given the roster file is marked CLOSED? — Danny.
4. Does naming need anyone's consent first? — Danny.
