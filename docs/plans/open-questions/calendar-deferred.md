# Calendar — open questions carried by the .ics download slice (G5)

**Date:** 2026-09-04 · **Slice:** `GET /v1/units/{unit_id}/events/{event_id}/invite.ics`

This slice spends the one calendar permission the synthetic pilot development
authorization (2026-09-03, §3) grants — *ICS artifacts* — and stops there. Gate
**G5 (Calendar API)** stays deferred to public-release planning, and nothing in
this slice moves it.

Every item below is a decision a human has to make that engineering could not
make for them. None of them stopped the slice: each carries a **safe default**
that is implemented, and each default is chosen so that being wrong about it
degrades into *no calendar entry* rather than into *a calendar entry nobody's
source stated*.

That asymmetry is the whole policy, and it is the lesson of finding **F-003**.
The legacy generator turned the unparsed recurrence string "Every Tuesday" into
a confident invite thirty days out; a student who imported it had a real-looking
entry on a real day for an event that was not happening. A refusal costs
somebody a download. A fabrication costs somebody a Tuesday.

Nothing here is a placeholder that reports success. Where a fact is missing, the
route returns a `409` naming which fact, and no bytes are issued.

---

## OQ-001 — the Google Calendar API authorization model (G5, deferred)

**Question.** Under whose OAuth client, on which scopes, with whose consent
screen, does SmartMatch write into a person's calendar? Who administers the
grant, and what happens to existing entries when a student leaves the
institution?

**Why engineering cannot answer it.** Writing into someone's calendar on their
behalf is a delegated-authority claim over an account SmartMatch does not own.
The scope set, the verification review Google requires for it, and the
data-retention answer that comes with it are institutional commitments, not
implementation choices.

**Safe default, implemented.** There is no client, no scope string, no
credential and no environment variable anywhere in this slice that a later edit
could point at Google. `smartmatch_domain.calendar_invite` imports nothing but
the standard library and `smartmatch_domain.ics`;
`services/api/smartmatch_api/routers/calendar.py` adds a database read and a
`Response`. `tests/unit/test_calendar_invite_wiring.py` asserts the absence of
`googleapiclient`, `google_auth_oauthlib`, `auth/calendar`, `calendar.events`,
`GOOGLE_CALENDAR` and `CALENDAR_CREDENTIALS` by name, so acquiring the
capability fails a test that cites this gate rather than passing as a diff.

The user-visible substitute is complete rather than degraded: an .ics file is
what a person imports into *whichever* calendar they use, and it needs no
authorization from anybody because the person performs the import themselves.

## OQ-002 — who supplies an event's end time

**Question.** Where does an event's end instant come from? A coordinator typing
it, a duration convention per event type, or the source document?

**Why engineering cannot answer it.** A duration is a fact about a real event.
Picking a default — an hour, ninety minutes, "until the next one" — is
inventing one, which is F-003's defect wearing a different field name.

**Safe default, implemented.** Migration `0022` adds `event.ends_at`, nullable
and nullable permanently, with `ck_event_end_after_start` requiring that an end
exist only alongside an `exact` start and fall strictly after it. Existing rows
are **not backfilled**: writing `starts_at + 1 hour` into storage would make a
guess look like something a source said. `NULL` means "the source stated no
end", the catalog reports it as `time.ends_at: null` so a client can tell before
it offers a link, and the download route answers `409 event_end_unknown`.

**Consequence to accept knowingly.** Until an event acquires an end time, no
event is downloadable. Today that is *every* event in the pilot fixtures,
because neither `ical_parser` nor `jsonld_parser` reads `DTEND` / `endDate` yet
(OQ-003). The route is therefore correct and, on current data, always refusing —
which is the honest state of the world, and it is visible in the response rather
than hidden behind a spinner.

## OQ-003 — reading `DTEND` and `endDate` in the Stage 0 parsers

**Question.** Should `smartmatch_domain.ical_parser` and
`smartmatch_domain.jsonld_parser` populate `ExactTime.ends_at` from `DTEND` /
`DURATION` and schema.org `endDate`, and what should they do with the
combinations RFC 5545 permits but that contradict each other?

**Why engineering cannot answer it here.** It is a scoped parser change with its
own golden-test surface, and folding it into this slice would put two unrelated
behavior changes behind one review. `DURATION` in particular needs a decision
about whether a *stated* duration is an end time (it is) or a derived one (it is
not), and `VALUE=DATE` end dates in iCalendar are exclusive, which is the kind
of off-by-one a golden test should pin before a calendar shows it to anybody.

**Safe default, implemented.** `ExactTime.ends_at` defaults to `None` and both
parsers construct `ExactTime` without it, exactly as before this slice. The
field is additive; no existing parser behavior changed, and no golden test
moved.

## OQ-004 — what "a student's own events" means

**Question.** Which events may a student download? The ones they registered for,
the ones they attended, or every published event in their unit?

**Why engineering cannot answer it.** It is a privacy-surface decision about a
minor-adjacent population, and the three readings differ in what a student can
enumerate about their peers' unit.

**Safe default, implemented.** The narrowest reading the schema can actually
express: a student may download an event only when an `attendance_record` row
names them and it. There is no registration table in this schema, so "registered
for" is not expressible today, and the route deliberately does **not** widen to
"every event in the unit" to compensate. A student asking for an event they have
no row for gets `404`, identical to the response for an event that does not
exist — a denial distinguishable from an absence is an existence oracle, the same
argument `load_unit_or_404` makes for a cross-tenant unit.

`admin` and `coordinator` read the whole unit, which is the role set
`routers/events.py` already applies to the catalog these event ids come from.

## OQ-005 — the organizer identity, and therefore `METHOD`

**Question.** What mail domain and mailbox represents the institution as an
event `ORGANIZER`?

**Why engineering cannot answer it.** It is open decision 8 (mail-domain
registration) — the same question
`docs/plans/open-questions/r4-outreach-deferred.md` OQ-001 asks for outbound
mail. It is an institutional identity claim.

**Safe default, implemented.** The document carries no `METHOD`, no `ORGANIZER`
and no `ATTENDEE`. RFC 5546 §3.2.2 makes the latter two mandatory on a VEVENT
inside a `METHOD:REQUEST` calendar, and the only way to emit one today would be
to invent an address. Dropping `METHOD` leaves a plain RFC 5545 calendar object
— which is what an .ics download actually is — and also restores the legacy's own
behavior. `smartmatch_domain.ics` states this at the line that omits it.

## OQ-006 — the UID namespace

**Question.** Which domain should own the UIDs SmartMatch issues, once one is
registered?

**Why engineering cannot answer it.** Same decision as OQ-005.

**Safe default, implemented.** `events.smartmatch.invalid` — an RFC 2606
reserved TLD that cannot resolve and cannot be mistaken for a mailbox. The UID
is keyed on the **event row id** rather than on the title-and-start hash the
domain derives by default, so correcting a typo in a title updates a recipient's
existing entry instead of adding a second one beside it. Changing the namespace
later would re-issue every invite as a new entry, which is why it is written
down here rather than left to be noticed.

---

## What this slice deliberately did not build

* **No crawler, and no fetch of any kind.** Coordinators enter events; G3 §9
  keeps every network action worker-side, and this route makes none.
* **No engagement or rewards change.** Attendance is read as an authorization
  fact and nothing else — no ledger entry, no points, no attendance write.
* **No job, no `202`, no artifact store.** The document is bytes the request
  already has in hand; see the route module docstring for why a job would be
  machinery whose only function is to look like the routes around it.
* **No .ics *upload*, and no subscription feed.** A per-unit `webcal:` feed is a
  different authorization question — a URL that carries its own long-lived
  credential — and is not asked here.
