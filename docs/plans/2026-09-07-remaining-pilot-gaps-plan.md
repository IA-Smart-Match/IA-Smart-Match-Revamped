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
