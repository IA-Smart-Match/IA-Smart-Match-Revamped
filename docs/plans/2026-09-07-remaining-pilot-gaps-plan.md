# Remaining pilot gaps — implementation plan (2026-09-07)

**Status:** planning only. This document changes no source file, adds no route, and
writes no migration. It is written so that an agent can execute each section from the
text alone.  
**Authorization:** the product owner (Danny Tran, program owner of record) has
authorized implementation of all five gaps below, including the three that reverse a
recorded decision. That authorization does not loosen a single invariant: no match
percentage in the UI (OQ-CBA-005), weights only in `factor_registry` and persisted
matching-weights, never literals; UI gates are never authorization; every `/v1` route
stays deny-by-default; no fake success; unknown never degrades to a default
(ADR-0011 rule 1, `docs/architecture/decisions/ADR-0011-accountable-numbers.md:51-57`);
`ALLOW_LIVE_PROVIDERS` and `ALLOW_CLOUD_DEPLOY` stay false; and a role set is never
widened as a shortcut.  
**Migration head at planning time:** `0032_match_run_scoring_mode`
(`db/migrations/versions/0032_match_run_scoring_mode.py:143-144`). One Alembic
revision per PR. Exactly one gap below needs one.  
**Not planned here, because it is in flight:** nav links for `matching-weights`,
the Connector speaker-feedback page and the student speaker-feedback page (TRACK 15
in the coordinator's numbering), and the extension of
`FixtureSemanticTopicProvider`'s recorded pairs (TRACK 16). Nothing below touches
those files except where a section says so and tells the implementer to rebase.

## How to read the classification

Every gap is labelled one of two ways, and the label has changed meaning from an
earlier draft of this brief. It no longer gates anything — the owner has decided.

* **Decision-free** — implementable now; no recorded decision, register row, role set
  or prohibition is contradicted by building it.
* **Reverses a recorded decision** — the work contradicts something a committed
  artifact says. The section names the artifact, the sentence, and what must change
  *with* the code so that the repository does not contradict itself. The register
  entry is updated in the register's own closure shape (see below); nothing is
  silently closed.

The register's closure shape, verified against three existing closures: the row's
"Safe planning default" cell is rewritten to open with **`Closed <date> by <who>.`**
followed by what was decided (see OQ-CBA-028 at
`docs/plans/open-questions/cba-phase-deferred.md:40`), and a dated section
**`## Decision taken 2026-09-07 — OQ-CBA-NNN`** is added below the existing
`## Decision taken 2026-09-06 — OQ-CBA-024` section (`:251`), opening with
`Owner: Danny Tran, program owner of record.` and carrying a three-column
`| OQ | Decision | Obligation |` table, exactly as OQ-CBA-047's section does at
`:236-249`. The register's last issued id is **OQ-CBA-064** (`:72`); a new question this
work raises is registered as **OQ-CBA-065**, never folded into an existing row.

Every PR must carry the trade-off report the owner asked for. Each section ends with
the paragraphs that report has to contain: **what was chosen**, **what was rejected
and why**, **what it costs**, **what it exposes that was not exposed before**, and
**what could go wrong**.

---

## Gap 1 — the Event Host portal has zero readable surfaces

**Classification: reverses a recorded decision** — OQ-CBA-014's safe planning default
(`docs/plans/open-questions/cba-phase-deferred.md:30`) and the sentence in
`services/api/smartmatch_api/routers/speaker_requests.py:118-126` that records it. It
also needs the one migration in this plan.

### 1.1 What exists today

The `volunteer` role holds exactly one permit. `_SPEAKER_REQUEST_CREATE_ROLES` at
`routers/speaker_requests.py:113-115` is `{"admin", "coordinator", "volunteer"}`;
`_SPEAKER_REQUEST_READ_ROLES` at `:127` is `{"admin", "coordinator"}`; and
`tests/authz/test_policy_matrix.py:4826-4829` describes the volunteer's create cell as
"the only permit any `volunteer` shape has in this file". The other two routes the
Event Host portal renders — `GET /v1/units/{unit_id}/cba/confirmed-speakers` and the
hand-off `POST` — are `_HANDOFF_ROLES = {"admin", "coordinator"}`
(`routers/cba_handoff.py:103`), and the page that calls them says so in its own
header (`apps/web/legacy-frontend/src/app/pages/volunteer/VolunteerConfirmedSpeaker.tsx:41-48`:
"Both routes are `admin`/`coordinator` server-side, and an Event Host account may
hold neither"). `VolunteerHome.tsx` and `VolunteerAssignments.tsx` read only
`GET /v1/me` and `GET /v1/me/portals` (`VolunteerHome.tsx:11-13`,
`VolunteerAssignments.tsx:11-13`). So a stakeholder who logs into
`/volunteer-portal` (`routers/portals.py:210`) can file a request and read nothing
back, which `tests/e2e/test_pilot_clickthrough.py:2614-2701` (step 26) asserts as a
`403` on the queue.

The queue route `GET /v1/units/{unit_id}/speaker-requests`
(`routers/speaker_requests.py:643-679`) calls
`SpeakerRequestRepository.list_for_unit`
(`python/smartmatch_persistence/smartmatch_persistence/speaker_requests.py:244-269`),
which selects every `coordinator_entry` event under the unit. It holds every host's
title and description for the unit, so adding `volunteer` to `_SPEAKER_REQUEST_READ_ROLES`
would hand one host the others' request text. OQ-CBA-014 pre-refuses exactly that:
*"Do not widen the list role set as a shortcut; a host-scoped read is a different
query, not a wider permit."* It also names the schema question: whether "filed by"
needs "a stored actor column the `event` table does not have today".

That column does not exist. The `event` table definition at
`python/smartmatch_persistence/smartmatch_persistence/schema.py:1052-1200` carries
`host_org_unit_id`, `origin`, the three provenance columns and the temporal set, and no
column naming an account; a grep for `created_by|actor_id|decided_by|filed_by` over
`schema.py` finds such columns on `job` (`:224`), `point_ledger_entry` (`:509`),
`redemption` (`:615`), `review_item` (`:831`), `discovery_review_item` (`:1250`),
`outreach_draft` (`:1696`) and `match_weight_setting_revision` (`:2352`) — never on
`event`. `SpeakerRequestRepository.file` (`speaker_requests.py:168-224`) passes no
actor to `EventRepository.upsert_returning_outcome`
(`python/smartmatch_persistence/smartmatch_persistence/events.py:290-304`), whose
signature has no parameter for one. **A host-scoped read therefore cannot be written
without a migration**: there is no stored fact to filter on.

### 1.2 What is planned

**Route.** `GET /v1/units/{unit_id}/host/speaker-requests` — the Event Host's own
filed requests, in the same `SpeakerRequestListResponse` shape the queue returns. The
`host/` segment follows the student self-scoped surface, which lives under
`/v1/units/{unit_id}/student/events` (`routers/student_events.py:725-730`) and scopes
every row by `principal.user_id` rather than by anything in the request. It is a
different query with a different authorizer and a different role set, which is what
OQ-CBA-014 asked for.

**Authorization.** A new literal `_SPEAKER_REQUEST_OWN_READ_ROLES: Final[frozenset[str]] =
frozenset({"volunteer"})` in `routers/speaker_requests.py`, with its own
`_authorize_speaker_request_own_read(session, principal, unit_id)` that loads the unit
with `load_unit_or_404` and calls `assert_allowed` with `required_roles=` that set —
the same shape as `_authorize_speaker_request_read` at `:339-361`, and a *third*
function rather than a parameter on either existing one, for the reason that module
gives at `:344-348` ("one helper taking the role set as an argument would make a
single call site the place both could be widened from"). `admin` and `coordinator`
are deliberately not in this set: they already hold the queue, and a coordinator who
filed a request sees it there. The queue's role set is untouched.

**Storage — migration `0033_event_filed_by`.** One nullable column on `event`:

* `filed_by_user_id UUID NULL`, with a composite foreign key
  `(tenant_id, filed_by_user_id) → user_account (tenant_id, id) ON DELETE RESTRICT`
  — composite, as every account reference in this schema is
  (`schema.py:433-480` shows the same shape on `attendance_record.subject_id`), so a
  single-column key cannot accept an owner from another tenant.
* A CHECK `ck_event_filed_by_manual_origin`:
  `filed_by_user_id IS NULL OR origin = 'coordinator_entry'`. An extracted event has
  no filer, and a filer on a crawled row would attribute a fetch to a person — the
  mirror of the rule `ck_event_provenance_evidence` already enforces the other way
  (`routers/speaker_requests.py:60-62`).
* A partial index `ix_event_filed_by` on
  `(tenant_id, host_org_unit_id, filed_by_user_id) WHERE filed_by_user_id IS NOT NULL`,
  because that is the exact predicate the new read issues.
* **No backfill and no default.** A request filed before `0033` has no recorded filer,
  and the column says so with `NULL`. Writing the unit's coordinator, or the only
  volunteer in the unit, would be a reconstruction indistinguishable from a recorded
  fact — the same argument OQ-CBA-028's closure makes at
  `cba-phase-deferred.md:40` for `scoring_mode`, and ADR-0011 rule 1 applied to an
  identity rather than a number. Consequence, stated plainly: **a host cannot list a
  request they filed before this migration.** That is a true statement about what the
  system knows.

Nullable `NULL` here means *unknown filer*, never *no filer*. Both the migration
docstring and the column comment in `schema.py` must say so.

The `schema.py` mirror must gain the column, constraint and foreign key, or
`tests/integration/test_schema_matches_migration.py` fails (that file compares the
hand-written definitions to the migrated database in both directions, per its
docstring at `:1-20`). The index has no Core mirror, as the module already says of
every other index.

**Write path.** `EventRepository.upsert_returning_outcome` gains a keyword
`filed_by_user_id: uuid.UUID | None = None`, added to the insert `columns` dict at
`events.py:335-349` **and excluded from the `updated` dict** at `:365-372`, alongside
the four identity columns that are already excluded. So the first filer is kept on a
resubmission. This matters because ADR-0012's identity key — host unit, folded title,
resolved date — is what `ON CONFLICT` matches on (`:378`), and it does not include the
filer: two hosts in one unit filing the same title on the same date are, under
ADR-0012, one request. Keeping the first filer means the second host's resubmission
updates a row they cannot then list. That collision is real, was already true of the
create route before this work (the second host's `201` became a `200` on somebody
else's row), and is now *visible* through the new read. It is registered as
**OQ-CBA-065** rather than solved here (see 1.4); last-writer-wins was rejected
because it would let a host take over another host's request by retyping its title.

`SpeakerRequestRepository.file` gains a required keyword `filed_by_user_id: uuid.UUID`
and passes it through. `create_speaker_request` (`routers/speaker_requests.py:571-621`)
passes `principal.user_id` — the verified principal, never a body field, exactly as
the request model's docstring at `:157-161` already promises ("no actor ... come[s]
from the verified principal"). A coordinator filing a request is recorded as its
filer too; that is the truth about who typed it.

**Read path.** `SpeakerRequestRepository.list_filed_by(session, *, tenant_id,
host_org_unit_id, filed_by_user_id, limit)` — a public method beside `get` and
`list_for_unit`, built on the existing `_rows` helper (`speaker_requests.py:322-389`)
with `extra=(event.c.host_org_unit_id == host_org_unit_id, event.c.filed_by_user_id ==
filed_by_user_id)`. `_rows` already restricts to `origin = 'coordinator_entry'` and
scopes by tenant, so an extracted event cannot appear here either. `SpeakerRequestRow`
is unchanged; the route renders through the existing `_view` (`:487-535`) and returns
`SpeakerRequestListResponse` with `truncated` computed the way the queue computes it
(`:667-679`, read `MAX_ROWS + 1`).

**Route body.** Charge `SPEAKER_REQUEST_READ_RATE_LIMIT` (`:136`) — a read is a read;
a separate counter would be a second number nobody asked for — then authorize, then
`list_filed_by` with `filed_by_user_id=principal.user_id`. Nothing from the request
selects whose rows come back.

**Frontend.** A new page
`apps/web/legacy-frontend/src/app/pages/volunteer/VolunteerMyRequests.tsx` at
`/volunteer-portal/my-requests`, a `fetchMySpeakerRequests(unitId)` helper in
`apps/web/legacy-frontend/src/lib/api.ts` beside `fetchSpeakerRequests` (`api.ts:3025`)
returning the existing `SpeakerRequestList` type (`:3008`), a lazy import in
`app/routes.tsx` beside the other volunteer pages (`routes.tsx:100-118`, child routes
`:258-277`), and one entry in `VolunteerPortalLayout.tsx`'s nav list (`:20-30`). The
page reads the unit from `GET /v1/me/portals`'s `default_unit_id` and renders server
values only, in the discipline `VolunteerSpeakerRequest.tsx` states in its header. It
must not import `fetchSpeakerRequests`: that is the Connector's queue, and the frontend
contract test pins the direction (1.3). The nav file is not one TRACK 15 was
described as touching; the implementer must still check the merged TRACK 15 diff
before editing it and rebase if it did.

### 1.3 Tests, written first

1. `tests/integration/test_event_filed_by_migration.py` — new, modelled on
   `tests/integration/test_match_run_scoring_mode_migration.py` (docstring `:1-16`):
   bring a scratch database to `0032`, insert one `coordinator_entry` event and one
   extracted event, upgrade to `0033`, assert both rows' `filed_by_user_id` are `NULL`,
   assert an `UPDATE` setting a filer on the extracted row violates
   `ck_event_filed_by_manual_origin`, and assert a filer from another tenant violates
   the composite foreign key.
2. `tests/integration/test_speaker_request_persistence.py` — add, next to the
   existing read tests at `:458-549`:
   `test_filing_records_who_filed`, `test_refiling_keeps_the_first_filer`,
   `test_list_filed_by_returns_only_that_hosts_requests`,
   `test_list_filed_by_is_scoped_to_its_unit_and_tenant`, and
   `test_a_request_with_no_recorded_filer_is_listed_by_nobody` (the pre-`0033` case,
   written by inserting with `filed_by_user_id=None`).
3. `tests/authz/test_policy_matrix.py` — a new `Operation(key="speaker_request.list_own",
   method="GET", path="/v1/units/{unit_id}/host/speaker-requests",
   module="smartmatch_api.routers.speaker_requests",
   authorizer="_authorize_speaker_request_own_read",
   roles_constant="_SPEAKER_REQUEST_OWN_READ_ROLES", authorizer_module=None,
   required_roles=frozenset({"volunteer"}), resource_type="org_unit",
   unit_scoped=True)` in `OPERATIONS` (`:606`) directly after `speaker_request.list`
   (`:1261`), and its full rectangle in `MATRIX` (`:1988`) after the
   `speaker_request.create` block (`:4787`). `volunteer_at_owning_unit` permits;
   `coordinator_at_owning_unit`, `admin_at_org_root`, `student_at_owning_unit` and the
   sibling shapes deny — the coordinator and admin cells must say *why* (they hold the
   queue, and this route is narrower on purpose). Without the row,
   `test_every_authenticated_route_has_a_matrix_row` (`:6708`) fails; that failure is
   the reminder, not an obstacle. Update the comment at `:4826-4829` — it will no
   longer be true that the create cell is the only volunteer permit.
4. `tests/contract/test_speaker_requests_api.py` — extend the module's
   `request_context` fixture (`:88-165`, one tenant, one unit, one sibling, one host)
   with a **second host in the same unit**, then add:
   `test_a_host_lists_only_the_requests_they_filed` (host A files two, host B files
   one; A's list has A's two and not B's; B's has B's one),
   `test_the_host_list_carries_the_same_fields_as_the_filed_response`,
   `test_a_coordinator_is_refused_the_host_list` (`403 forbidden` — they have the
   queue), `test_a_student_is_refused_the_host_list`,
   `test_a_host_in_a_sibling_unit_is_refused`, `test_a_unit_in_another_tenant_is_a_404`,
   `test_the_host_list_reports_truncation`, and — the one that guards the leak —
   `test_a_request_filed_before_the_filer_was_recorded_is_listed_by_nobody`, which
   inserts an event row with `filed_by_user_id NULL` under the unit and asserts
   neither host sees it.
5. `tests/unit/test_frontend_speaker_requests_contract.py` — add
   `test_the_host_page_reads_only_the_host_route` (source contains
   `fetchMySpeakerRequests`, does not contain `fetchSpeakerRequests`) and
   `test_the_host_page_composes_no_identifier_in_the_browser`, mirroring
   `test_the_page_composes_no_identifier_in_the_browser` at `:197`.
6. `tests/e2e/test_pilot_clickthrough.py` step 26 (`:2614`) — keep every existing
   assertion (the queue still answers `403` to the host; the Connector still sees the
   request), then add: `host_api.get(f"/v1/units/{unit}/host/speaker-requests")` is
   `200` and contains `request_id`; `student_api` on the same path is `403`. Rewrite
   the docstring's OQ-CBA-014 paragraph (`:2624-2632`) to describe the answered
   question.
7. Regenerate `contracts/openapi/smartmatch.json` with `make openapi`
   (`Makefile:180-183`); `tools/export_openapi.py --check` runs in CI.

### 1.4 Files to change

Code: `db/migrations/versions/0033_event_filed_by.py` (new; `down_revision =
"0032_match_run_scoring_mode"`), `python/smartmatch_persistence/smartmatch_persistence/schema.py`,
`.../events.py`, `.../speaker_requests.py`,
`services/api/smartmatch_api/routers/speaker_requests.py`, `contracts/openapi/smartmatch.json`,
`apps/web/legacy-frontend/src/lib/api.ts`, `.../app/routes.tsx`,
`.../app/components/VolunteerPortalLayout.tsx`, `.../app/pages/volunteer/VolunteerMyRequests.tsx` (new).

Prose that currently records the gap and must change with it — every one of these was
read and says the host can read nothing: `routers/speaker_requests.py:118-126`
(`_SPEAKER_REQUEST_READ_ROLES` comment) and the module docstring's route list at
`:6-9`; `tests/authz/test_policy_matrix.py:1231-1238` and `:4826-4829`;
`tools/seed_pilot_principals.py:23-26`; `docker-compose.yml:113` and `:307-308`;
`docs/operations/containers.md:215`; `docs/operations/hosted-synthetic-pilot-guide.md:227-232`;
`tests/e2e/test_pilot_clickthrough.py:2624-2632` and `:2701`.

Register: `docs/plans/open-questions/cba-phase-deferred.md:30` — rewrite the OQ-CBA-014
cell to open **`Closed 7 September 2026 by Danny Tran, program owner of record.`**,
keeping the row's argument; add `## Decision taken 2026-09-07 — OQ-CBA-014` with the
three-column table, whose Obligation cell records: the queue's role set is unchanged;
`filed_by_user_id` is `NULL` for every pre-`0033` row and is never backfilled; the
host list is filtered on the verified principal and on nothing a caller supplies.
Register **OQ-CBA-065** (the same-key collision between two hosts, 1.2) as a new row
with the fail-closed default "first filer is kept; the second host's resubmission is
a `200` on a row they cannot list; do not switch to last-writer-wins".

### 1.5 Branch and milestones

Branch `feat/host-speaker-request-read`. Commit after each:

1. `feat(db): 0033 event.filed_by_user_id, schema mirror, migration test` — tests 1
   red, then green; `make migrate-check` passes.
2. `feat(persistence): record the filer on file, keep it on refile, list_filed_by` —
   tests 2.
3. `feat(api): GET /v1/units/{unit_id}/host/speaker-requests` — tests 3, 4, 7.
4. `feat(web): the Event Host's own requests page` — test 5; e2e step 26 (test 6).
5. `docs: close OQ-CBA-014, register OQ-CBA-065, update the prose that recorded the gap`.

### 1.6 What would make it wrong

* Filtering on anything from the request. The only acceptable predicate is
  `filed_by_user_id == principal.user_id`; a `?host_id=` query parameter, however
  convenient for an admin, is caller-selected identity.
* Treating `NULL` as "the caller". A `WHERE filed_by_user_id IS NULL OR ...` clause, or
  a fallback to `host_org_unit_id` when the filer is unknown, republishes the queue.
  Contract test 4's last case exists for this.
* Letting the filer be overwritten on refile (`updated` at `events.py:365-372`).
* Adding `volunteer` to `_SPEAKER_REQUEST_READ_ROLES` "since the host can see their
  own anyway". The queue and the host list must stay two operations.
* Rendering anything about invitations. **OQ-CBA-042** (`cba-phase-deferred.md:53`)
  binds: a host must not learn who declined by any route. `SpeakerRequestRow`
  (`speaker_requests.py:103-149`) carries no invitation, batch, count or response
  field, and the new read must reuse it unchanged — not a wider row type.

### 1.7 The PR's trade-off report

**Chosen.** A volunteer-only host-scoped read over a new nullable `filed_by_user_id`,
first-filer semantics, no backfill.  
**Rejected.** Widening the queue's role set (OQ-CBA-014 pre-refuses it; it hands one
host every other host's text). Inferring the filer for old rows (fabricated
attribution). Last-writer-wins on refile (lets a host take over another's request).
Filtering by `host_org_unit_id` alone for units with one host (a unit's membership
changes; the filter would silently widen).  
**Cost.** One migration and a schema mirror change; a foreign key that makes deleting
an account with filed requests a `RESTRICT` error; a nav item and a page.  
**Exposure.** A host can now read back exactly the fields `SpeakerRequestResponse`
already returned to them on `POST` (`routers/speaker_requests.py:266-297`): title,
description, time, virtual flag, location, industries, roles, `publication_status`,
`review_status`, timestamps — for the requests **they** filed. Nothing about other
hosts' requests, nothing about invitations, declines, batch sizes, matches or confirmed
speakers, none of which is on the row. `review_status` and `publication_status` were
already disclosed to the host by the create response, so no new field is exposed; the
new fact exposed is *the list itself* — that these requests are theirs.  
**Could go wrong.** A pre-`0033` request the host filed is invisible to them and they
may re-file it, producing a `200` on the old row (still invisible, because the filer is
kept `NULL`); the register's OQ-CBA-065 row and the page's empty-state copy must say
"requests filed before 7 September 2026 are not listed". Two hosts with the same
title and date collide (OQ-CBA-065).

---

## Gap 2 — no unit-level student-feedback aggregate

**Classification: decision-free.** OQ-CBA-003's decision
(`docs/plans/open-questions/cba-phase-deferred.md:129-141`) says Connector reads
"publish the arithmetic mean and response count only when at least three submitted
ratings exist" and that "Connector responses contain no student identifier,
individual ratings, timestamps, or comments". A unit-level read that obeys both is a
second Connector read under the same rule, not a wider one. OQ-CBA-054 (`:66`) gates a
Connector response model gaining *comments or individual rows*; this one gains
neither. OQ-CBA-053 (`:65`) is untouched: nothing here reads into matching. No OQ is
closed. Because it is a Connector surface the 6 September decision did not name, the
PR records it as an addendum under that decision rather than quietly beside it.

### 2.1 What exists today

The only Connector read is `GET /v1/units/{unit_id}/speakers/{speaker_id}/feedback-summary`
(`services/api/smartmatch_api/routers/student_speaker_feedback.py:718-773`), gated by
`_SPEAKER_FEEDBACK_SUMMARY_ROLES = {"admin", "coordinator"}` (`:168`) and mounted on
`connector_router` under `Capability.SPEAKER_CONTACT_MANAGEMENT`
(`services/api/smartmatch_api/main.py:452`). It calls
`StudentSpeakerFeedbackRepository.submitted_ratings`
(`python/smartmatch_persistence/smartmatch_persistence/student_speaker_feedback.py:281-315`),
which selects **one column** — `rating` — for one speaker in one unit with
`status = 'submitted'`, and returns `list[int]`; then
`aggregate_speaker_feedback` (`python/smartmatch_domain/smartmatch_domain/student_speaker_feedback.py:311-337`)
suppresses both mean and count below `MIN_RESPONSES_FOR_AGGREGATE = 3` (`:92`), and
`SpeakerFeedbackAggregate.__post_init__` (`:289-297`) makes a suppressed aggregate
that carries a number unrepresentable. The response model
`SpeakerFeedbackSummaryResponse` (`routers/student_speaker_feedback.py:295-325`) has no
field a student could be assigned to.

The Connector dashboard says the rest. `CoordinatorHome.tsx:60-64` — "Student feedback
has no unit-level aggregate anywhere in this API" — and the pointer component at
`:289-336` renders no number and links to the per-speaker page. PR #104's contract test
`tests/unit/test_frontend_dashboard_stats_contract.py:272-288` pins that the page
*names* the gap (`"feedback-summary"` must appear in the page text), and `:158-181`
pins that the page computes nothing (`reduce(`, `toFixed` are forbidden). Summing
per-speaker aggregates in the browser is therefore both forbidden by that test and
wrong on its merits: a suppressed per-speaker summary contributes `null`, so any
client-side total either drops it (undercounting) or republishes what suppression
withheld.

### 2.2 The suppression rule, at the unit level

Pooling a unit's ratings and applying `n ≥ 3` is necessary but not sufficient. The
per-speaker route is public to the same reader, so a unit aggregate can be
*differenced* against it. With speaker A published at `n=3` and the unit at `n=5`,
`5 − 3 = 2` ratings of somebody else are recoverable as a mean over two students —
precisely what the decision withholds ("in a class of thirty, 'two students rated this
speaker' narrows the field considerably", `domain/student_speaker_feedback.py:269-272`).
The same holds for any set of published speakers: with A(3), B(3), C(2) the unit
`n=8` minus the published `6` isolates C's two.

The rule the domain must implement, as a pure function:

```
residual = n_unit − Σ n_s over speakers s whose own aggregate is published (n_s ≥ MIN)
publish the unit aggregate iff n_unit ≥ MIN and (residual == 0 or residual ≥ MIN)
```

The suppressed speakers' counts are not known to the reader, so the residual is the
only quantity they can compute; requiring it to be zero or itself above the threshold
closes the differencing attack against everything the API publishes. Two things are
deliberately *not* claimed: that this is safe against differencing across time
(withdrawals move both routes and the decision already accepts that for the
per-speaker read, `cba-phase-deferred.md:140`), and that the unit aggregate is
meaningful when only one speaker has ratings — in that case it equals the per-speaker
aggregate and discloses nothing new.

Add to `python/smartmatch_domain/smartmatch_domain/student_speaker_feedback.py`:
`aggregate_unit_feedback(ratings_by_speaker: Mapping[uuid.UUID, Sequence[int]]) ->
SpeakerFeedbackAggregate`, reusing `SpeakerFeedbackAggregate` so the "no numbers when
suppressed" invariant is inherited, and exporting it in `__all__` (`:58-72`). The
function filters nothing (the same contract `aggregate_speaker_feedback` states at
`:315-318`: withdrawn rows are the caller's bug). `MIN_RESPONSES_FOR_AGGREGATE` is the
one threshold; no second constant.

### 2.3 What is planned

**Persistence.** `StudentSpeakerFeedbackRepository.submitted_ratings_by_speaker(session,
*, tenant_id, owning_unit_id) -> dict[uuid.UUID, list[int]]`, selecting exactly
`(speaker_professional_id, rating)` with `status = 'submitted'` and `rating IS NOT NULL`,
scoped by tenant and unit in the query. Two columns rather than one, and the second is
a speaker id, not a student: the module's argument at `:290-295` — "there is no
`student_id` in the result set for a route to forget to strip" — still holds.

**Route.** `GET /v1/units/{unit_id}/speaker-feedback-summary` on `connector_router`
(so it inherits `SPEAKER_CONTACT_MANAGEMENT`; a deployment with the roster off should
not aggregate over it, the reason the module docstring gives at
`routers/student_speaker_feedback.py:118-127`). A new literal
`_UNIT_FEEDBACK_SUMMARY_ROLES = frozenset({"admin", "coordinator"})` and
`_authorize_unit_feedback_summary_read`, separate from the per-speaker authorizer for
the ledger reason (`tests/authz/test_route_roles.py:1-30`). No `tenant_wide_roles`: the
metrics decision's §4 tenant-wide aggregate rule is read narrowly by `routers/metrics.py:388-402`
and by `routers/engagement.py` for the attendance summary; this surface follows
engagement, not metrics. Response model `UnitFeedbackSummaryResponse`: `unit_id`,
`suppressed`, `response_count: int | None`, `mean_rating: float | None`,
`display_text`, `minimum_responses` — the per-speaker model's fields with `unit_id` in
place of `speaker_professional_id`. **No per-speaker breakdown, no rated-speaker count,
no list of speaker ids.** Every extra number is a differencing handle.

**Frontend.** `fetchUnitSpeakerFeedbackSummary(unitId)` in `lib/api.ts` beside
`fetchSpeakerFeedbackSummary` (`api.ts:3930`); `CoordinatorHome.tsx`'s
`StudentFeedbackPointer` (`:303-340`) renders the server's `display_text` when
suppressed and the server's `mean_rating` / `response_count` when not, computes
nothing, keeps its sentence that feedback does not feed matching (pinned at
`test_frontend_dashboard_stats_contract.py:261`), and keeps the link to the
per-speaker page. The contract test at `:272-288` currently asserts the page *names*
the unit-aggregate gap; it must be rewritten to assert the page reads the unit route,
not that the gap is stated. The `CoordinatorSpeakerFeedback.tsx` page (TRACK 15's nav
target) is not touched.

### 2.4 Tests, written first

1. `tests/unit/test_cba_student_feedback_decision.py` — a new class
   `TestUnitAggregate` beside the existing scale/state classes (`:56-132`):
   empty unit suppressed; one speaker `n=3` publishes and equals the per-speaker
   aggregate; A(3)+B(2) suppressed (residual 2); A(3)+B(3) publishes (residual 0);
   A(3)+B(2)+C(2) publishes (residual 4); A(3)+B(3)+C(2) suppressed (residual 2);
   two suppressed speakers A(2)+B(2) publishes `n=4` (no published speaker to
   difference against); suppressed result carries no numbers (inherited invariant);
   mean is rounded to two decimals over the pooled list.
2. `tests/integration/test_student_speaker_feedback.py` — in the repository class
   (`:297-419`): `test_ratings_by_speaker_excludes_withdrawn_rows`,
   `test_ratings_by_speaker_is_scoped_to_unit_and_tenant`,
   `test_ratings_by_speaker_selects_no_student_column` (assert on the result type's
   keys and values, and on the compiled statement's selected columns).
3. `tests/contract/test_student_feedback_api.py` — beside
   `test_connector_gets_only_the_thresholded_aggregate` (`:162`):
   `test_the_unit_summary_is_suppressed_below_the_threshold`,
   `test_the_unit_summary_is_suppressed_when_it_would_difference_a_speaker` (A rated
   by three, B by two; per-speaker A publishes; the unit read is suppressed),
   `test_the_unit_summary_publishes_when_nothing_can_be_differenced`,
   `test_the_unit_summary_names_no_student_and_no_speaker`,
   `test_a_student_is_refused_the_unit_summary`,
   `test_a_sibling_coordinator_is_refused_the_unit_summary`.
4. `tests/authz/test_policy_matrix.py` — `Operation(key="student_feedback.unit_summary",
   method="GET", path="/v1/units/{unit_id}/speaker-feedback-summary", ...,
   authorizer="_authorize_unit_feedback_summary_read",
   roles_constant="_UNIT_FEEDBACK_SUMMARY_ROLES",
   required_roles=frozenset({"admin", "coordinator"}), resource_type="org_unit",
   unit_scoped=True)` and its rectangle, copied from the per-speaker summary's row
   and rectangle (locate by `grep -n "feedback_summary" tests/authz/test_policy_matrix.py`).
5. `tests/unit/test_frontend_student_feedback_contract.py` — add
   `test_the_dashboard_reads_the_unit_aggregate_and_computes_nothing`; and rewrite
   `tests/unit/test_frontend_dashboard_stats_contract.py:272-288` as described.
6. `tests/e2e/test_pilot_clickthrough.py` step 25 (`:2388`) — add a `GET` of the unit
   summary by the coordinator asserting `suppressed is True` and both numbers `null`
   on the appliance's data, and a `403` for `student_api`. (The submission itself
   stays skipped until Gap 3 lands; see §6 for the order.)
7. `make openapi`.

### 2.5 Files, branch, milestones

Code: `python/smartmatch_domain/smartmatch_domain/student_speaker_feedback.py`,
`python/smartmatch_persistence/smartmatch_persistence/student_speaker_feedback.py`,
`services/api/smartmatch_api/routers/student_speaker_feedback.py`,
`contracts/openapi/smartmatch.json`, `apps/web/legacy-frontend/src/lib/api.ts`,
`apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorHome.tsx`. No migration.

Docs: `cba-phase-deferred.md` — under `## Decision taken 2026-09-06 — OQ-CBA-003`
(`:129`) add a dated addendum paragraph, "**Addendum 7 September 2026** — a unit-level
Connector aggregate under the same threshold, with the differencing rule of 2.2;
recorded because the 6 September table named the per-speaker read only." Update
`routers/student_speaker_feedback.py:1-12`'s route list to five.

Branch `feat/unit-feedback-aggregate`. Milestones: (1) `feat(domain): aggregate_unit_feedback
with the differencing rule` — test 1; (2) `feat(persistence): submitted_ratings_by_speaker`
— test 2; (3) `feat(api): GET /v1/units/{unit_id}/speaker-feedback-summary` — tests 3,
4, 7; (4) `feat(web): the Connector dashboard reads the unit aggregate` — tests 5, 6;
(5) `docs: record the addendum`.

### 2.6 What would make it wrong

* Implementing suppression as a `HAVING count(*) >= 3` — the module docstring at
  `routers/student_speaker_feedback.py:62-70` says why: "a privacy rule in a query plan
  is a privacy rule nobody can read".
* Applying only `n ≥ 3` to the pool and skipping the residual rule. Contract test 3's
  second case exists for this.
* Returning `0.0` or `0` for an empty unit. Both must be `null` with
  `display_text = "not enough responses yet"` (`NOT_ENOUGH_RESPONSES`,
  `domain/student_speaker_feedback.py:97`).
* Adding a `speakers: [...]` breakdown "for the chart". That is the per-speaker route
  again with the suppression decided in one place for all of them, and it re-opens
  differencing between rows.
* Reading this into a factor, a weight, or `match_run`. OQ-CBA-053.

### 2.7 The PR's trade-off report

**Chosen.** One pooled aggregate per unit, suppressed by the pooled threshold *and* the
residual rule, on the Connector's existing role set.  
**Rejected.** Client-side summation (forbidden by the dashboard contract test and
republishes suppressed rows); a per-speaker list with a unit total (differencing);
a rated-speaker count in the response (a handle).  
**Cost.** A second Connector read to keep honest; one more rectangle in the matrix; a
dashboard section that can legitimately read "not enough responses yet" for the whole
pilot, which is the true statement about synthetic data.  
**Exposure.** A Connector learns the unit's pooled mean and count when at least three
submitted ratings exist and no published speaker can be subtracted out. No student,
speaker, timestamp or comment. When the unit has one rated speaker the number equals
what the per-speaker route already gives.  
**Could go wrong.** The residual rule is easy to lose in a refactor that "simplifies"
the domain function to `len(all) >= 3`; the unit test matrix in 2.4 item 1 is the
guard. The dashboard test that pinned "names the gap" must be rewritten, not deleted.

---

## Gap 3 — `attendance_record` has no route writer

**Classification: reverses a recorded decision** — three of them, in three places that
must change together:

1. `python/smartmatch_persistence/smartmatch_persistence/attendance.py:1-22` — the module
   docstring scopes the writer to "the minimal `attendance_record` writer the synthetic
   pilot authorization allows" and closes with "**no route imports this repository, and
   none may**". `python/smartmatch_persistence/smartmatch_persistence/engagement.py:11-19`
   quotes that sentence and says "That sentence is still true after this module exists".
2. `services/api/smartmatch_api/routers/pipeline.py:61-65` and
   `routers/cba_handoff.py:46-48` — both open a paragraph with "**No attendance
   writer.** The Attended stage *cites* an `attendance_record`; it does not create one."
3. `docs/plans/open-questions/pipeline-stage-writers-deferred.md:56-72` — **OQ-102**,
   "who writes `attendance_record`", whose safe default is "The synthetic pilot path
   (`tests/integration/test_synthetic_attendance_writer.py`) remains the only writer,
   and it is not a production one", and whose reason is the one that matters here:
   "`attendance_record` is the only input to points (ADR-0013), so whatever writes it
   is also what mints student rewards."

The authorization the writer was built under is
`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md:63` — item 3,
"minimal synthetic writer for Attended-stage CHECK constraints in demo seed flow" — and
`services/api/smartmatch_api/pipeline_provisioning.py:41-48` explains why even the
review-accept path does not call it. A route exceeds item 3. The owner's 7 September
authorization is the new authority; it is recorded in the register, and the ratified
3 September document is **not** edited (the precedent is OQ-CBA-032's closure at
`cba-phase-deferred.md:195-203`, which left the ratified worksheet untouched and
recorded the narrowing beside it).

### 3.1 What exists today

`AttendanceRepository.record_attendance(session, *, tenant_id, owning_unit_id,
subject_id, event_id, method) -> uuid.UUID` (`attendance.py:63-170`) inserts with
`ON CONFLICT DO NOTHING` on `uq_attendance_record_subject_event`, refuses a `method`
outside `ATTENDANCE_METHODS = {"qr_scan", "coordinator_entry", "import"}` (`:47`),
reads the row back, and raises `ConflictingOwningUnitError` when an earlier row sits
under a different unit. It returns the id and does not say whether this call inserted.
The table (`schema.py:433-480`) carries composite foreign keys to `org_unit`,
`user_account` (the subject) and `event`, all `RESTRICT`.

Three readers already depend on the row: the Attended stage in both funnels
(`PipelineRepository.advance_stage` checks the row exists in the tenant at
`persistence/pipeline.py:539-550`; the CBA hand-off additionally checks the row's
subject is the invitation's professional and its event is the journey's event,
`persistence/pipeline.py:776-786` and `:855-903`); student feedback eligibility
(`persistence/student_speaker_feedback.py:415-424` — an attendance row for the
*student* at the event, also a composite foreign key on the feedback table); and the
rewards balance (`routers/rewards.py:512-566`: no ledger entry **and** at least one
attendance row is the *unknown* balance, "It is not zero"). The student browse surface
reads it too (`routers/student_events.py:667-693`). Everything above is a read. The
only writer in the tree is the test file the OQ names, plus `tools/generate_pilot_dataset.py`
through the same repository.

Two consequences follow for the e2e walk-through. Step 25
(`tests/e2e/test_pilot_clickthrough.py:2388-2420`) skips the feedback submission
because "nothing in the `/v1` surface creates one"; step 24 (`:2243`) leaves
`attended_at` null for the same reason. And **the subject of an attendance row is not
only a student**: the CBA hand-off cites a row whose `subject_id` is the *speaker's*
professional id (`persistence/pipeline.py:889-892`). A route that only accepted
students would leave the Attended stage of the CBA funnel unreachable.

Points are minted by a separate call. `RewardsRepository.credit_attendance`
(`persistence/rewards.py:240-262`) appends the ledger entry for one attendance,
idempotently under `uq_point_ledger_entry_attendance_credit`, and its docstring says of
`actor_id`: "It is accepted for the case where a coordinator's action is what caused
the derivation to be run." Nothing under `services/` calls it; `tools/generate_pilot_dataset.py:858`
does.

### 3.2 What is planned

**Route.** `POST /v1/units/{unit_id}/events/{event_id}/attendance` in a **new** router
`services/api/smartmatch_api/routers/attendance.py`. Not on `routers/engagement.py`,
whose router is pinned read-only by
`tests/unit/test_matching_fail_closed.py:372-388` and bounded to one path by
`R2_AUTHORIZED_ENGAGEMENT_PATHS` (`:269-273`) — a `POST` there would need both pins
loosened and would attach a write to the router that exists to prove D8 is still
open. The path contains none of `_CHECK_IN_MARKERS = ("check-in", "checkin",
"check_in", "/qr", "qr-", "qr_", "scan")` (`tests/unit/test_checkin_wiring.py:56`),
because this is not the B08 check-in flow: no token is issued or verified, and the
router must not import `smartmatch_domain.checkin` (`:111-118` holds the composition
root to that). `attendance` and `events` are not forbidden segments in
`_forbidden_gate_for_path` (`test_matching_fail_closed.py:128-207`; the existing
`/v1/units/{unit_id}/cba/events/{event_id}/speaker-handoff` already passes the same
scan at `:603-612`).

**Mounting.** In `main.py`'s capability list beside `pipeline.router`
(`main.py:373`, `Capability.DISCOVERY_METRICS`): the row exists to make the funnel's
Attended stage reachable, and the funnel is what that capability mounts. This is a
judgement the reviewer may move — `EVENT_READS` (feedback eligibility) and
`REWARDS_LEDGER` (points) also depend on the row — but it must be *one* capability,
stated in the router docstring.

**Authorization.** `_ATTENDANCE_WRITE_ROLES = frozenset({"admin", "coordinator"})`, a
literal, with `_authorize_attendance_write` loading the unit via `load_unit_or_404`
and calling `assert_allowed` with `required_roles=` and nothing else — the same shape
as `_authorize_engagement_read` (`routers/engagement.py:153-175`). The coordinator is
the accountable actor for unit record-keeping (the argument at `engagement.py:100-107`),
and OQ-102's own framing — the coordinator is one of its three candidate writers — is
what makes this the narrowest honest answer.

**Body.** `subject_id: uuid.UUID` only. No `method` field: the route *is* a
coordinator's entry, so `method` is fixed server-side to `"coordinator_entry"` — taken
from a new domain constant `COORDINATOR_ENTRY_METHOD` in
`smartmatch_domain/attendance.py` beside `ATTENDANCE_METHODS` (`:66`), not from
`synthetic_pilot.py`, whose equal-valued constant is documented as the *synthetic*
writer's (`synthetic_pilot.py:65-69`). A caller-chosen `qr_scan` would claim a scanner
that does not exist; `import` would claim a batch. No `recorded_at`: `created_at` is
the server default (`schema.py:446`) and a coordinator cannot backdate presence.

**Preconditions, each a worded refusal rather than an `IntegrityError`:**

* the event exists in this tenant **and** `event.host_org_unit_id == unit_id`, else
  `404 event_not_found` — the same scoping the hand-off applies to its event
  (`persistence/pipeline.py:741-750`); an attendance owned by unit A at an event
  hosted by unit B is a row nobody's drill-down can explain;
* the subject is a `user_account` in this tenant, else `404 attendance_subject_not_found`
  — the composite foreign key would refuse it anyway, but as a `500`;
* `ConflictingOwningUnitError` → `409 attendance_owned_by_another_unit`.

Registration is **not** required. An attendance row is evidence that somebody was
present; requiring an `event_registration` row first would refuse the walk-in the
coordinator is looking at.

**Repository change.** `record_attendance` returns a new frozen
`AttendanceWriteResult(attendance_id, created)`, with `created` read from
`RETURNING id` on the `ON CONFLICT DO NOTHING` insert (a row comes back only when this
call inserted) — the same "one statement decides" discipline
`EventRepository.upsert_returning_outcome` applies at `events.py:378-387`. The two
existing callers (the integration test and `generate_pilot_dataset.py`) change to
`.attendance_id`.

**Points.** After the attendance write, in the same transaction, the route calls
`RewardsRepository.credit_attendance(session, tenant_id=..., attendance_id=...,
actor_id=principal.user_id)` and catches `AlreadyCreditedError` so a repeated request
is idempotent. This is ADR-0013's model — "Points derive from recorded attendance and
nothing else" (`ADR-0013-attendance-derived-engagement.md:60`) — and it is the case the
`actor_id` parameter was written for. Without it, every student the coordinator marks
present shows `state: "unknown"` on `GET /v1/units/{unit_id}/rewards` forever
(`routers/rewards.py:548-557`), and step 15 has no balance to spend. The rate is
`POINTS_PER_VERIFIED_ATTENDANCE = 100` (`smartmatch_domain/rewards.py:101`) with
`EARN_POLICY_RATIFIED = False` (`:121`), both already published on the catalog
response; nothing here promotes D7.

**Response.** `201 AttendanceRecordResponse{attendance_id, unit_id, event_id,
subject_id, method, recorded_at, points_credited: bool, ledger_entry_id | null}` read
back from the rows; `200` with the same body when the row already existed (the
speaker-requests pattern at `routers/speaker_requests.py:613-620`). No score, no
balance.

**Rate limit.** `ATTENDANCE_WRITE_RATE_LIMIT = RateLimit(operation="attendance.record",
max_requests=120, window=timedelta(minutes=1))` — a coordinator marking a room of
students present needs more than the 30-per-minute a filing gets.

### 3.3 The docstrings, changed with the code

* `attendance.py:1-22` — rewrite. The module is now the attendance writer for the
  coordinator route and the synthetic seed; it is still not a scanner, not a live
  check-in, and not identity. Delete "no route imports this repository, and none
  may"; state which route does, and that `tests/unit/test_checkin_wiring.py` still
  holds the route away from `smartmatch_domain.checkin`.
* `engagement.py:11-19` — the paragraph quoting the sentence must go; the reason the
  reader is a separate module (different exposure) still stands and is kept.
* `routers/pipeline.py:61-65` and `routers/cba_handoff.py:46-48` — each becomes "**No
  attendance writer here.** The Attended stage *cites* an `attendance_record` written by
  `routers/attendance.py`; this router never creates one." OQ-102's citation at
  `pipeline.py:65` changes to the closure.
* `pipeline_provisioning.py:41-48` — still true (it does not call the writer); add one
  sentence pointing at the route so a reader does not conclude the writer is uncalled.
* `tests/integration/test_synthetic_attendance_writer.py:1-15` — "the minimal
  `attendance_record` writer" is no longer minimal-and-synthetic; reword.
* `tests/e2e/test_pilot_clickthrough.py:2404-2409` (step 25) and `:2602` — rewrite.
* `docs/plans/2026-09-07-matching-expansion-brief.md:63-67` is a dated brief and is
  left as written.

### 3.4 Tests, written first

1. `tests/integration/test_synthetic_attendance_writer.py` — add
   `test_record_attendance_reports_whether_it_inserted` (first call `created=True`,
   second `False`, same id).
2. `tests/authz/test_policy_matrix.py` — `Operation(key="attendance.record",
   method="POST", path="/v1/units/{unit_id}/events/{event_id}/attendance",
   module="smartmatch_api.routers.attendance", authorizer="_authorize_attendance_write",
   roles_constant="_ATTENDANCE_WRITE_ROLES", required_roles=frozenset({"admin",
   "coordinator"}), resource_type="org_unit", unit_scoped=True)` and its rectangle,
   copied from `engagement.attendance_summary`'s (locate with `grep -n
   "attendance_summary" tests/authz/test_policy_matrix.py`).
3. `tests/contract/test_attendance_api.py` — new, on the fixture shape of
   `tests/contract/test_engagement_api.py` (docstring `:1-12`; one tenant, one unit,
   one sibling, a coordinator, a student, real `event` rows):
   `test_a_coordinator_records_a_students_attendance_and_the_row_is_in_the_table`,
   `test_the_same_request_twice_is_a_200_and_one_row`,
   `test_the_method_is_coordinator_entry_and_the_body_cannot_choose_it` (a `method`
   field in the body is a `422`), `test_attendance_credits_points_once`
   (one `point_ledger_entry` after two calls; the student's `GET .../rewards` balance is
   `measured` and equals `POINTS_PER_VERIFIED_ATTENDANCE`),
   `test_a_speaker_subject_is_accepted` (a `user_account` with no student membership),
   `test_an_event_hosted_by_another_unit_is_a_404`,
   `test_a_subject_outside_the_tenant_is_a_404`,
   `test_a_student_may_not_record_attendance`,
   `test_a_sibling_coordinator_may_not_record_attendance`,
   `test_the_response_carries_no_score_and_no_balance`.
4. `tests/unit/test_checkin_wiring.py` — no edit; it must still pass (path markers,
   composition-root import) and the PR must say it ran.
5. `tests/unit/test_matching_fail_closed.py` — no allowlist edit is needed for a new
   router (the engagement pins are on `engagement.router` only); the OpenAPI scan at
   `:603-612` must pass on the regenerated document.
6. `tests/e2e/test_pilot_clickthrough.py` — step 24 (`:2243`): after the hand-off, the
   coordinator records the accepted speaker's attendance at the event and re-issues the
   hand-off with `attendance_id`; assert `attended_at` is set and `applied` contains
   `"attended"`. Step 25 (`:2388`): the coordinator records the **student principal's**
   attendance at the same event; the student then submits a rating (`201`), reads it
   back, and the Connector's per-speaker and unit summaries are asserted suppressed
   (one rating). Keep every existing `403` assertion. The `pytest.skip` on the
   submission is removed.
7. `make openapi`.

### 3.5 Files, register, branch, milestones

Code: `services/api/smartmatch_api/routers/attendance.py` (new), `main.py`,
`python/smartmatch_persistence/smartmatch_persistence/attendance.py`,
`python/smartmatch_domain/smartmatch_domain/attendance.py`, `tools/generate_pilot_dataset.py`
(the `.attendance_id` change), `contracts/openapi/smartmatch.json`. No migration.
No frontend in this PR: the Connector page that records attendance is a separate,
smaller PR once the route exists, and the e2e steps drive the route directly.

Register: `docs/plans/open-questions/pipeline-stage-writers-deferred.md:56-72` — add
under OQ-102 a paragraph opening **"Decided 7 September 2026 by Danny Tran, program
owner of record."**: the coordinator writes it, through `POST
/v1/units/{unit_id}/events/{event_id}/attendance`, `{admin, coordinator}`, method fixed
to `coordinator_entry`, points credited on record at the unratified D7 rate; the
scanner and roster-upload writers remain unbuilt. That register has no table shape;
its closures are prose paragraphs under each heading, and this follows it. Also add a
one-row entry to `cba-phase-deferred.md`'s `## Decision taken 2026-09-07` section
cross-referencing OQ-102, so the CBA gate lists the reversal.

Branch `feat/attendance-route`. Milestones: (1) `feat(persistence): record_attendance
reports whether it inserted` — test 1; (2) `feat(api): POST
/v1/units/{unit_id}/events/{event_id}/attendance, credited on record` — tests 2, 3, 4,
5, 7; (3) `docs: retire the "none may" prohibition where it is written, close OQ-102`
— 3.3; (4) `test(e2e): steps 24 and 25 walk the Attended stage and the feedback
submission` — test 6.

### 3.6 What would make it wrong

* Letting the body choose `method`. `qr_scan` on a row nobody scanned is a false
  provenance the engagement summary then reports by mechanism
  (`routers/engagement.py:121-128`).
* Accepting `recorded_at` from the caller. The Attended stage reads
  `attendance_record.created_at` as its timestamp (`persistence/pipeline.py:732-733`).
* Skipping the unit check on the event. The composite foreign key does not check the
  event's host unit, only that the event exists in the tenant.
* Crediting points twice, or not at all. The contract test on the ledger count is the
  guard; `AlreadyCreditedError` must be caught, `UnknownAttendanceError` must not be.
* Importing `smartmatch_domain.checkin` from the router, or naming the path with any
  check-in marker. Both are pinned.
* Returning a balance. `GET /v1/units/{unit_id}/rewards` is the balance's only surface.

### 3.7 The PR's trade-off report

**Chosen.** A coordinator-gated write with a server-fixed `coordinator_entry` method,
crediting points in the same transaction.  
**Rejected.** A `POST` on the engagement router (pinned read-only for D8's sake); a
caller-chosen method (false provenance); requiring registration first (refuses
walk-ins); recording without crediting (leaves every balance `unknown` and step 15
unreachable); a separate "credit" route (a second human step for a derivation ADR-0013
says is automatic).  
**Cost.** The three prohibitions above are retired and their prose rewritten; the
synthetic-pilot authorization's item 3 is exceeded by the owner's later decision;
`record_attendance` changes return type for two callers.  
**Exposure.** A coordinator can now assert that a named account was present at a unit's
event, and that assertion mints 100 points for that account. A speaker's attendance
also mints a ledger entry the speaker cannot spend (the catalog is student-gated,
`routers/rewards.py:182`); it is inert but it is a row, and the PR must say so. No
roster is exposed: `GET .../engagement/attendance-summary` still counts and never lists,
and this route returns the one row it wrote.  
**Could go wrong.** OQ-102's warning is now live: a wrong row is a wrong reward. The
compensating control is the append-only ledger with `actor_id` and
`record_reversal` (`persistence/rewards.py:340`), which the PR must name as the
correction path. A coordinator marking the wrong student present cannot delete the
row (`RESTRICT` everywhere); the PR must say the fix is a reversal entry, not a delete.

---

## Gap 4 — no funded reward item exists

**Classification: reverses a recorded decision** — the rewards catalog worksheet's
status line, `docs/pilot-data/rewards-catalog-worksheet.md:3`: "**do not seed listable
catalog rows**", and the sentence under it, "Empty cells are intentional — engineering
must not invent owners, funding, or point costs." The D6 decision record's boundary
(`docs/decisions/pilot-decisions.md:197-204`: "No new ... catalog, route, or UI behavior
is authorized by this record") and its §5 list of what stays open
(`docs/decisions/d6-rewards-budget-decision-record.md:104-123`: "Item names, costs, and
content", "Read/redemption roles") are ratified records and are **not edited**; the
owner's 7 September authorization is recorded beside them.

### 4.1 What exists today

Step 15 (`tests/e2e/test_pilot_clickthrough.py:1370-1421`) asserts the catalog is empty,
issues a redemption request for an invented item id, requires `404
reward_item_not_found` — "403 would mean the student gate had closed again" — and
skips. The gap is data. `RewardsRepository` "Reads and appends `point_ledger_entry`;
reads the listable catalog" (`persistence/rewards.py:235-236`) and has no item writer;
`routers/rewards.py:105-110` says "**No catalog writer, no seeding, and no money.**
`reward_item` rows are written by the synthetic seed path, not by this API" — and
`tools/generate_pilot_dataset.py:66-76` says the seed path *cannot* write them either:
"`reward_item` ... has **no writer anywhere in the application**. ... Reaching around
that with an `INSERT` here is precisely what this tool must not do", reported on every
run at `:1150-1156`. The only inserts are raw SQL in tests
(`tests/integration/test_rewards_api.py:142-165`,
`tests/integration/test_engagement_schema_constraints.py:309-450`).

A `/v1` route is the wrong fix, and the tree says why twice. `test_the_rewards_router_exposes_two_reads_and_two_commands`
(`tests/unit/test_matching_fail_closed.py:565-585`) pins the four method/path pairs
precisely so that "a later card [cannot] hang a catalog *writer* off `/rewards` — a
`POST` there would seed items the D6/D7 artifacts do not authorize"; and D6 §5 lists
"Read/redemption roles" as undecided, so a route would have to invent the role set that
may create catalog items. A seed tool needs no role set: it is an operator's act,
gated the way every seed tool here is gated.

### 4.2 What is planned — a repository writer and an operator tool, no route

**Persistence.** `RewardsRepository.create_item(session, *, tenant_id, name,
points_cost, fulfilment_cost, budget_owner_id, funded) -> uuid.UUID` — an `INSERT`
through `schema.reward_item`, so `ck_reward_item_points_cost_positive`,
`ck_reward_item_fulfilment_cost_non_negative` and the composite owner key
(`schema.py:543-576`) all apply. It commits nothing. It raises a new
`UnknownBudgetOwnerError(ValueError)` after checking the owner is a `user_account` in
the tenant, so the tool refuses with a sentence rather than an `IntegrityError`. It
does not default `funded`: the column's `server_default 'false'` is an insert default,
not a policy, and the tool passes the value explicitly.

**Operator tool.** `tools/seed_pilot_rewards.py`, on the shape of
`tools/seed_pilot_logins.py` and `tools/seed_pilot_principals.py`: reuses
`require_development_fixture_settings` and `acquire_seed_lock` from `tools/seed_pilot.py`
(`:37-52`), refuses to run outside `SMARTMATCH_EDITION=dev` with fixture providers, and
takes **every value as an argument with no default** — `--name`, `--points-cost`,
`--fulfilment-cost`, `--budget-owner-subject` (the `user_account.external_subject`;
the tool resolves the id and refuses an unknown one), `--funded/--unfunded`. The
worksheet's rule that engineering "must not invent owners, funding, or point costs" is
honoured by construction: the tool cannot run without the owner typing them.
Idempotent on `(tenant, name)`: an existing item with identical values is a no-op
report, with different values a `SeedConflictError`, like `seed_pilot`'s own rule
(`tools/seed_pilot.py:1-6`, `seed_pilot_logins.py:41-44`). It prints the D7 calibration
check — whether `points_cost <= CALIBRATION_N × POINTS_PER_VERIFIED_ATTENDANCE` using
the domain's constants (`smartmatch_domain/rewards.py:101-121`) — as a *report line*,
not a refusal: D7 is tentative, and the owner may seed a stretch reward on purpose.

A `make seed-pilot-rewards` target beside `seed-pilot-logins` (`Makefile:167-174`),
`SEED_PILOT_REWARD_ARGS` passed through. **No compose one-shot**: a compose service
would need the values in `docker-compose.yml` or `.env`, and a reward's name and cost
in a checked-in file is exactly the invented catalog the worksheet forbids. The hosted
guide documents the `make` invocation the operator runs after `seed-principals`.

**Where the owner's values go.** The tool's `--help` and the hosted guide point at the
worksheet's catalog table (`rewards-catalog-worksheet.md:20-27`); the owner fills a
row, then runs the tool with that row. The budget owner for the pilot is named in D6
(`d6-rewards-budget-decision-record.md:27-29`: Danny Tran); the tool still takes the
subject as an argument rather than hard-coding it, because a name in a decision record
is not a `user_account` row.

**e2e step 15.** Rewritten to *branch* rather than skip: if the catalog is empty, keep
today's assertions and skip naming the seed command; if it is not, the student — whose
balance is measured once Gap 3's route has credited an attendance — requests the
cheapest item, asserts `201` and `status == "requested"`, and the coordinator decides
it through `POST .../redemptions/{id}/decision`, asserting the returned state. If the
balance is `unknown` or below cost, the step asserts the server's `409` code
(`balance_unknown` / `insufficient_balance`, `routers/rewards.py:705-745`) and skips
naming which. The step must never insert a row; the seed tool is the operator's.

### 4.3 Tests, written first

1. `tests/integration/test_rewards_repository.py` — `test_create_item_writes_a_listable_row_when_funded_and_owned`,
   `test_create_item_refuses_an_owner_outside_the_tenant` (`UnknownBudgetOwnerError`),
   `test_create_item_rejects_a_non_positive_cost_at_the_database` (`IntegrityError`
   from the CHECK, not caught), `test_an_unfunded_item_is_not_listable`
   (`listable_items` excludes it — the existing rule at `persistence/rewards.py:521-577`).
2. `tests/unit/test_seed_pilot_rewards.py` — on the pattern of
   `tests/unit/test_seed_pilot.py:38-100`: every argument required (argparse exits
   non-zero on any omission), the settings gate is checked before any connection, the
   lock is acquired, an identical rerun is an idempotent repeat, a differing rerun is a
   `SeedConflictError`, and the calibration line is printed and never refuses.
3. `tests/unit/test_matching_fail_closed.py` — **no change**, and the PR must say
   `test_the_rewards_router_exposes_two_reads_and_two_commands` still passes: the
   router gains nothing.
4. `tests/e2e/test_pilot_clickthrough.py` step 15 — as in 4.2.
5. `tests/unit/test_cba_rewards_copy.py:89-92` — no change; the student page still
   renders `catalog.items.map`.

### 4.4 Files, register, branch, milestones

Code: `python/smartmatch_persistence/smartmatch_persistence/rewards.py`,
`tools/seed_pilot_rewards.py` (new), `Makefile`. No migration, no route, no frontend,
no OpenAPI change.

Prose that must change with it: `routers/rewards.py:105-110`, `tools/generate_pilot_dataset.py:66-76`
and `:1150-1156` (the tool may now say the catalog is seeded separately by
`seed_pilot_rewards.py`, or call the new repository method itself when given the same
arguments — the implementer chooses, and either way the "no writer anywhere" sentence
goes); `tests/unit/test_matching_fail_closed.py:73-77` (the paragraph about "no
`reward_item` writer by construction" — the *router* still has none; reword to say
the writer is the operator tool); `docs/pilot-data/rewards-catalog-worksheet.md:3`
(status line becomes "human completion required — seed only values the owner has
written into the table below, with `make seed-pilot-rewards`"); `docs/operations/hosted-synthetic-pilot-guide.md`
(a subsection after "Pre-loaded pilot principals", `:207-224`, and the "Cannot" line at
`:309` which lists "rewards ledger APIs" among things that cannot run — verify whether
that line is still accurate after PR #104 and this PR, and correct it if not).

Register: `cba-phase-deferred.md` — a row in `## Decision taken 2026-09-07` reading
"Rewards catalog seeding — **Decided.** A funded `reward_item` may be seeded on the
pilot appliance by the operator tool with owner-supplied values; no route creates one;
D7 stays tentative; the worksheet's empty cells are filled by the owner, not by
engineering." D6's own record is not edited.

Branch `feat/seed-pilot-rewards`. Milestones: (1) `feat(persistence): RewardsRepository.create_item`
— test 1; (2) `feat(tools): seed_pilot_rewards, every value owner-supplied` — test 2,
Makefile; (3) `docs: the catalog has an operator writer; register the decision` — 4.4
prose; (4) `test(e2e): step 15 walks request and decision when a funded item exists`
— test 4 (after Gap 3 has merged, see §6).

### 4.5 What would make it wrong

* A default for any of name, cost, owner or `funded`. The worksheet's rule is the
  whole reason the catalog is empty today.
* A route. It reopens the D6 role question and breaks a pin that exists on purpose.
* Seeding from the e2e test or from `compose_smoke.sh` to make step 15 go green. The
  step says why at `:1385-1389`: "Inserting a reward row and a ledger entry to force a
  ticket into existence would manufacture the evidence the decision route exists to
  check."
* Promoting D7. The tool reports calibration; it does not enforce or ratify it.
* Reading `fulfilment_cost` anywhere on the API. `routers/rewards.py:108` still holds.

### 4.6 The PR's trade-off report

**Chosen.** A repository writer plus an operator seed tool whose every value is an
argument, and a `make` target.  
**Rejected.** A `/v1` catalog-create route (undecided role set; breaks a pin that
guards D6); a compose one-shot with values in a checked-in file (invents the catalog);
raw SQL in the tool (bypasses the constraints every other write goes through).  
**Cost.** Two docstrings and one test docstring that said "no writer" are rewritten; a
new tool to keep gated.  
**Exposure.** A student on the appliance can now see a catalog item and open a
redemption against a balance credited by Gap 3; a coordinator can decide it. Real
money is still nowhere: `fulfilment_cost` is stored and never read, and D8 is untouched.  
**Could go wrong.** An operator seeds an item the owner has not written into the
worksheet — the tool cannot tell; the guide must say the worksheet row comes first. A
seeded item under a budget owner who later loses their account hits `RESTRICT`.

---

## Gap 5 — `feedback.py` is orphaned and mis-wired

**Classification: decision-free**, with a recommendation: **correct the map; do not
delete the module.**

### 5.1 What exists today

`python/smartmatch_domain/smartmatch_domain/feedback.py` (276 lines) is imported by
`tests/unit/test_feedback.py:8` and by nothing else — a grep for
`smartmatch_domain.feedback` over `services/`, `python/` and `apps/` finds only the
cross-reference in `student_speaker_feedback.py:8` ("**This is not**
`smartmatch_domain.feedback`"). Its `REASON_TO_FACTOR` at `feedback.py:108-118` maps
`WRONG_TOPIC → "topic_relevance"`, `WRONG_ROLE → "role_fit"`, `TOO_FAR → "travel_burden"`,
`UNAVAILABLE → "availability"`, `OVERCOMMITTED → "engagement_load"`,
`RECENTLY_ENGAGED → "repeat_penalty"`, `OTHER → None`.

Against `PROPOSED_FACTORS` (`factor_registry.py:280-378`): `topic_relevance` (`:334`)
and `travel_burden` (`:349`) are present but carry `retired_in_version=REGISTRY_VERSION`
(`:346`, `:361`) and are listed in `SUPERSEDED_SCORING_KEYS` (`:394`); `availability`
(`:364`) is present as an `ELIGIBILITY` factor with `proposed_weight=0.0` — a Stage A
filter whose weight cannot move; `role_fit`, `engagement_load` and `repeat_penalty` do
not exist in the registry at all. The four active scoring keys are
`APPROVED_SCORING_KEYS` (`:383-390`): `industry_match`, `role_match`,
`cba_semantic_topic`, `proximity`, each defined as a module constant
(`factors/industry_match.py:104`, `factors/role_match.py:114`,
`factors/cba_semantic_topic.py:124`, `factors/proximity.py:145`). So a proposal from
this module today would nudge two retired weights, one immovable weight, and three
names nothing can look up. `tests/unit/test_feedback.py:130-142` asserts the retired
`travel_burden` mapping by name.

Why deletion is the wrong fix. The OQ-CBA-032 closure
(`cba-phase-deferred.md:195-225`) rests one of its rows on this module: "MM-005's
shadow mode is a **different** control, and it is already satisfied ...
`smartmatch_domain.feedback.WeightProposal.requires_approval` is a setterless property
on a `@final`, frozen, slotted class, so a proposal can never apply itself. Nothing in
this repository consumes those proposals." `routers/matching_weights.py:69-80` repeats
the argument. Delete the module and a ratified closure cites a class that does not
exist, MM-005 in `docs/migration/migration-manifest.yaml:399` loses its target, and the
one tested statement of the approval control (`test_feedback.py:204-255`) goes with it.
The module is also the reference implementation ADR-0011 rule 1 names
(`ADR-0011-accountable-numbers.md:55`: "`feedback.acceptance_rate` is the reference
implementation"). Orphaned is a fact about wiring; the register says the un-wiring is
deliberate. Correcting a stale map inside an unwired module changes no behaviour, no
weight, no registry version and no route — which is what makes it decision-free.

### 5.2 What is planned

In `feedback.py`:

* Import the four key constants from their factor modules (all inside
  `smartmatch_domain`, so the "Domain is pure" import-linter contract in
  `pyproject.toml:148-166` is unaffected) and rewrite `REASON_TO_FACTOR` as:
  `WRONG_TOPIC → CBA_SEMANTIC_TOPIC_FACTOR_KEY`, `WRONG_ROLE → ROLE_MATCH_FACTOR_KEY`,
  `TOO_FAR → CBA_PROXIMITY_FACTOR_KEY`, `UNAVAILABLE → None`, `OVERCOMMITTED → None`,
  `RECENTLY_ENGAGED → None`, `OTHER → None`. The three `None`s are honest: availability
  is a Stage A filter with no weight to move, and no factor measures load or recency —
  OQ-CBA-040 (`cba-phase-deferred.md:51`) records that a decline is "recorded, never
  scored", so mapping those reasons to a made-up factor would be the very signal it
  bars. No `WRONG_INDUSTRY` reason is added: `DeclineReason` is the seven-member
  closed enum finding F-18 replaced (`feedback.py:14-18`), and adding a member is a
  vocabulary change the manifest would have to record; it is noted in the PR as a
  follow-up, not done.
* Update the module docstring's account of the mapping (`:14-18`) to say the targets
  are the `2.0.0-approved-oq-cba-004` registry's active scoring keys, resolved by
  import so a rename cannot strand them again.
* `MAX_FACTOR_DELTA` and `PER_REASON_BUMP` (`:64-68`) stay. They are bounds on a
  human-approved *proposal*, not weights; weights live in the registry and in
  `match_weight_setting`, and this module writes neither. The PR says so.

In `tests/unit/test_feedback.py`:

* `test_declines_raise_the_implicated_factor` (`:130-134`) asserts on
  `CBA_PROXIMITY_FACTOR_KEY` instead of `"travel_burden"`.
* New `test_every_mapped_factor_is_an_active_scoring_key`: every non-`None` target of
  `REASON_TO_FACTOR` is in `factor_registry.implemented_scoring_keys()` (`:576-583`,
  implemented and not retired) — the test that would have caught this drift, and will
  catch the next retirement.
* New `test_reasons_with_no_factor_move_nothing`: the three `None` reasons at the
  floor produce no proposal.
* `test_each_reason_maps_to_its_documented_factor` (`:136-142`) is unchanged and now
  passes for the right reason.

In `docs/migration/migration-manifest.yaml`, MM-005 (`:399`): the entry carries
`legacy_symbol`, `behavior_replaced` and `behavior_rejected` fields (`:399-470`); add a
`corrections:` field in the shape MM-004's has (`:381-388`) — "7 September 2026 —
`REASON_TO_FACTOR` retargeted to the 2.0.0 registry's active keys after
`topic_relevance` and `travel_burden` were retired by OQ-CBA-027/025; three reasons map
to no factor; module still unwired." Status stays `ported_unverified` — the correcting
party does not set `verified` (`:375`).

### 5.3 Files, branch, milestones

Code: `python/smartmatch_domain/smartmatch_domain/feedback.py`,
`tests/unit/test_feedback.py`, `docs/migration/migration-manifest.yaml`. No migration,
no route, no registry change (`REGISTRY_VERSION` at `factor_registry.py:137` is
untouched — no factor was added, removed or reweighted). Branch
`fix/feedback-reason-map`. Milestones: (1) `test(feedback): pin mapped factors to the
active registry` — red; (2) `fix(feedback): retarget REASON_TO_FACTOR to the active
scoring keys` — green; (3) `docs(migration): MM-005 correction note`.

### 5.4 What would make it wrong

* Wiring it to anything. The OQ-CBA-032 obligation is explicit: "Do not add an
  advisory shadow run, a stored evaluation record, or a 'validated' flag on a weight
  set without reopening this." A route, a worker command, or an import from
  `matching_weights.py` reopens a closed decision.
* Mapping `OVERCOMMITTED` or `RECENTLY_ENGAGED` to `proximity` or `role_match` "so the
  reason does something". That is a decline feeding a factor it does not describe —
  OQ-CBA-040 by another route.
* Adding a factor to satisfy the map. That is a registry bump and an approver's
  signature (`factor_registry.py:383-390`).
* Bumping `REGISTRY_VERSION` or `registry_hash` inputs. Nothing in the registry
  changed; `tests/unit/test_match_run_pins.py` would fail for stored runs if it had.

### 5.5 The PR's trade-off report

**Chosen.** Retarget the map to the active keys by import; three reasons map to no
factor; module stays unwired.  
**Rejected.** Deleting the module (strands a ratified closure, MM-005, and ADR-0011's
reference implementation); adding `WRONG_INDUSTRY` (a vocabulary change under MM-005
F-18); mapping the three orphan reasons to the nearest existing factor (OQ-CBA-040).  
**Cost.** Nothing at runtime; one manifest note.  
**Exposure.** None. No route reads the module.  
**Could go wrong.** The next factor retirement re-strands the map silently — the new
registry-pinning test is the guard. Someone reads the corrected map as an invitation
to wire it; the OQ-CBA-032 obligation is the answer, and the module docstring should
quote it.
