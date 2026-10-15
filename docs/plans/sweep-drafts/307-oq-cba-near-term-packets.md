> DRAFT — needs Danny (program owner of record) decision; 011 also needs a privacy owner. Nothing here is decided.

# #307 — OQ-CBA near-term decision packets (011, 021, 044, 063, 064, 065, 066)

**Source:** `docs/plans/open-questions/cba-phase-deferred.md` (rows at `:23`, `:34`, `:55`, `:71`, `:72`, `:73`, `:74`). Each packet frames; none closes a row (closure needs a dated artifact, `student-engagement-deferred.md:12`).
**Owners:** Danny Tran (@BrooklynD23) is program/product owner of record (`docs/decisions/owner-roster.md` rows 2 and 4). No privacy owner is named for B26/Speaker accounts; the Gate-B privacy owner row is scoped to P9 Gate B only (`docs/plans/sweep-drafts/296-privacy-owner-roster-row.md`, "Where the roster lives").

## OQ-CBA-011 — store a speaker's personal Contact Email?
- **Question:** may SmartMatch keep the personal "Contact Email" from a CPP CBA contact import, and under what retention/access/deletion rules? (`cba-phase-deferred.md:23`)
- **Blocks:** storing/displaying a speaker contact email; Connector invitations that need an address (`:23`, last cell).
- **Options:**
  1. Keep withholding. No change; `professionals.contact_email` stays `gate_pending`/`withhold`, warning `columns_withheld_pending_gate` (`:23`). Invitations to that speaker need another route.
  2. Store with a full ADR-0014 field set (retention, access roles, deletion). Needs a new column/write path, import-contract change, deletion tests, and a named privacy owner's record.
  3. Remove the field from the contract (drop the recognised-but-withheld column). Cleaner import contract; interacts with OQ-CBA-015 (shipped keep-and-discard, `296-privacy-owner-roster-row.md` item 2).
- **Not a consent question:** an import is not one of the four approved consent sources, so no answer makes the address send-eligible (`:23`).
- **Safe default in force:** withhold and warn (`:23`).
- **Who decides:** CBA program owner and a named privacy owner (`:23`); the privacy owner is unnamed (#296).

## OQ-CBA-021 — warn on likely-duplicate speaker contacts?
- **Question:** once identity is opaque (OQ-CBA-017) and the same-name `409` is gone, what tells a Connector the contact may already exist? (`:34`)
- **Blocks:** duplicate contacts in one unit; any merge surface; whether create ever blocks vs warns (`:34`).
- **Options:**
  1. Likely-duplicate hint on create (warn, never block). Needs a match rule and a response field.
  2. Hint plus a merge surface. Adds merge semantics, audit trail, and a repoint of anything referencing the contact.
  3. Nothing for now. Accepts duplicates until a roster is large.
- **Excluded by the register:** do not reinstate a unique `(tenant_id, owning_unit_id, full_name)` constraint (`:34`).
- **Safe default in force:** nothing warns today beyond the `409` that OQ-CBA-017 removes (`:34`).
- **Who decides:** CBA product owner with the pilot data owner; before rosters make duplicates routine (`:34`).

## OQ-CBA-044 — may a Speaker change a recorded answer?
- **Question:** `record_response` refuses a different second answer; should a speaker be able to withdraw after accepting? (`:55`)
- **Blocks:** a withdrawal path; an amended answer with its own trail entry; showing an Event Host that a confirmed speaker is no longer coming (`:55`).
- **Options:**
  1. Keep fail-closed; withdrawal via a new invitation row for a rescheduled event, or phone a Connector (`:55`).
  2. Connector-recorded withdrawal: new status transition with trail entry; Speaker cannot self-withdraw.
  3. Speaker self-withdraw via their link: needs trail entry, Host-visible state, and distinct states for changed-mind / never-answered / expired (OQ-CBA-041 — they may not share a spelling, `:55`). Any Host-visible state must respect OQ-CBA-042 (hosts do not learn who declined).
- **Safe default in force:** fail closed; first answer stands, on both the connector route and the Speaker link (`:55`).
- **Who decides:** CBA product owner with the events owner; before a real cohort is invited (`:55`).

## OQ-CBA-063 — resolve a city name to a coordinate?
- **Question:** `speaker_profile.location_city` has no state column; how does a city resolve? (`:71`)
- **Blocks:** city-only proximity; any "assume in-state" rule; a `location_state` column; telling Connectors a city alone suffices for a physical run (`:71`).
- **Options (from the register, none adopted):**
  - (a) Add a state column and require it on import: changes the §13 contact form and import contract, needs backfill.
  - (b) Resolve only cities unambiguous within California; others stay unknown: honest, but a Connector cannot see why one city resolved and another did not.
  - (c) Ask the Connector for a ZIP instead: smallest system change, largest typing burden.
- **Safe default in force:** no city resolved, none guessed; city-only speaker is `unknown` under `cba-physical-1` (`:71`). ADR-0016 treats missing address as `unknown`, not Far.
- **Who decides:** CBA product owner with the data owner and the Speaker Connector; before a pilot roster is matched on physical events with cities (`:71`).

## OQ-CBA-064 — how does a student find a speaker to rate the first time?
- **Question:** the feedback write takes `speaker_id` in the path and no student-authorized route returns one (`:72`).
- **Blocks:** first-time student feedback via any UI; any speaker picker; any student-visible "who spoke" (`:72`). OQ-CBA-003 stays amend/withdraw only meanwhile (`:15`).
- **Options (from the register, none adopted):**
  - (a) Student-scoped roster read limited to events the student attended. Smallest picker surface; discloses named roster professionals tied to an attended event.
  - (b) Derive from the student's own attendance rows (`routers/student_events.py::_attended_event_ids`). Cannot be narrower than (a) until OQ-CBA-051 (speaker-to-event appearance relation) is answered.
  - (c) Add a speaker field to an existing student surface (`StudentEventSummary`/agenda). Wider than (a) unless suppressed for non-attended events.
- **Constraints:** no UUID typing; no pointing a client at a refused route; any read built from confirmed/appeared speakers only, never invitation state (OQ-CBA-042) (`:72`).
- **Safe default in force:** no student roster read, no invented speaker id (`:72`).
- **Who decides:** CBA product owner with the API owner, and the privacy owner on the disclosure; alongside OQ-CBA-051 (`:72`).

## OQ-CBA-065 — two Event Hosts, same title, same date
- **Question:** ADR-0012's key excludes the filer, so the second host's `POST` is a `200` against the first host's row they cannot list (`:73`).
- **Blocks:** a second filer on a request; a `409`; a "already filed by another host" response (`:73`).
- **Options (register lists these; each discloses something about the other host):**
  1. Keep first-filer-wins with a truthful `200` (today).
  2. Return `409` when the key names someone else's row: clear to the second host; reveals that the first request exists.
  3. Allow multiple filers (a list, not a column): schema change; both hosts see the request; needs a visibility rule.
  4. Tell the second host in the create response it was already filed by another host.
- **Excluded by the register:** last-writer-wins; widening the identity key with the filer (`:73`).
- **Safe default in force:** first filer kept; `filed_by_user_id` withheld from the `ON CONFLICT` update set (`:73`).
- **Who decides:** CBA product owner with the API owner; before a unit has more than one Event Host account filing (`:73`).

## OQ-CBA-066 — what is a "meeting with the CBA team"?
- **Question:** is it only an internal note, or something with participants and outbound effects? Three sub-questions (`:74`).
- **Blocks:** any participant list/column; Host or student view of meetings; a per-meeting `.ics` plus its G5 allowlist entry; notifications/invitations/calendar writes; cancellation reasons (`:74`).
- **Options per sub-question:**
  - (a) Who may book: keep `{admin, coordinator}`; or add Event Host (changes the route role set and what Hosts see).
  - (b) What a participant is: none (today); a `user_account` reference (authorizable, needs an account); or free text (a string someone typed, different privacy and correction story). Naming an external person records someone who never consented (`:74`, cf. OQ-CBA-042).
  - (c) Does a booking leave the system: stays a note (today); or sends/ICS. This is a **G5** question: the ratified synthetic-pilot authorization §3 defers the Calendar API and permits only the event `.ics` at `/v1/units/{unit_id}/events/{event_id}/invite.ics`; a second `.ics` path widens `G5_AUTHORIZED_CALENDAR_PATHS` in `tests/unit/test_matching_fail_closed.py` (`:74`).
- **Safe default in force:** internal record only (title, instant, IANA zone, optional location/link, status, recorder); nothing tells a participant; the coordinator page says so on screen (`:74`).
- **Who decides:** CBA product owner with the Speaker Connector on (a); privacy owner on (b); (c) is also a G5 decision for Danny (`:74`).

## Open questions
1. Who is the privacy owner for 011, 064 (disclosure) and 066(b)? — Danny names (#296).
2. 011: keep withholding, store, or remove the field? — program owner + privacy owner.
3. 021: warn, warn+merge, or nothing? — CBA product owner + pilot data owner.
4. 044: can a Speaker withdraw after accepting, and who sees it? — CBA product owner + events owner.
5. 063: (a), (b) or (c)? — CBA product owner + data owner + Speaker Connector.
6. 064: (a), (b) or (c), and does OQ-CBA-051 go first? — CBA product owner + API owner + privacy owner.
7. 065: which disclosure, if any, to the second host? — CBA product owner + API owner.
8. 066(a)/(b): who books, what is a participant? — CBA product owner, Speaker Connector, privacy owner.
9. 066(c): may a meeting ever leave the system (G5 allowlist widening)? — Danny.
