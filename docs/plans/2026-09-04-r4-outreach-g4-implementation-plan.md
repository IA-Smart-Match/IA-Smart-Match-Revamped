# Implementation plan — R4 outreach (G4): drafts, the send command, delivery events

**Date:** 2026-09-04 · **Plan id:** P9 · **Branch:** `claude/r4-outreach-infrastructure-4wxrp6`
**Shape copied from:** `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`

> **Authorization basis.** This plan is executed under the engineering
> assumption that G4 (consent-origin policy, supervised-recipient policy,
> deliverability review) is **closed for engineering purposes** and that the
> synthetic pilot's `.invalid` recipients are in scope. That assumption is
> recorded here rather than left implicit, because every card below depends on
> it and a reader who finds it untrue should stop at the stop-gate rather than
> discover the problem in card L6.
>
> What the assumption does **not** cover, and what no card below therefore
> does: send to a real address, construct a live provider client, or ship
> unreviewed legal copy. Those are OQ-001 through OQ-003 in
> `docs/plans/open-questions/r4-outreach-deferred.md`, and the code refuses
> each of them by name.

## Standing constraints (restated; permanent)

- **Consent before compose, consent before send.** `assert_send_eligible` runs
  before any message text exists, and the worker runs it *again* at delivery
  time against freshly read state. A task can sit in a queue while consent is
  withdrawn; the draft is a record of intent, never a standing permission.
- **No invite-to-consent.** No template asks an address to opt in. The closed
  template registry, and the test that pins its closure, are the mechanism.
- **Domain purity.** `smartmatch_domain` imports no `os`, `socket`, `httpx`,
  `requests`, or `smartmatch_providers`. The import-linter contract "Domain is
  pure" enforces it; a domain module that could open a socket would make every
  argument in `outreach_dryrun.py`'s docstring unenforceable.
- **The request path records intent and nothing else.** A send is
  `submit_command` → outbox → worker. The API answers `202` with a job id. It
  never returns a status that implies a message left the building.
- **No fake success anywhere.** A UI may say "queued". It may say "failed". It
  may say "delivered" only when a `delivery_event` says so. `console.log`
  followed by "Message sent!" (B17) is the defect this whole slice exists to
  replace, and replacing it with an optimistic 202-means-sent toast would be
  the same defect wearing a real network request.
- **Unknown is never zero (ADR-0011).** A send with no provider acknowledgement
  has `provider_message_id IS NULL`, not `''`. A draft with no approval is not
  an approved draft with a blank approver.
- **One transaction per Alembic revision (ADR-0009); expand only.**
- No production-readiness claims. No force-push. No skipped hooks.

## Stop-gate (verify before any card)

1. `python/smartmatch_domain/smartmatch_domain/consent.py` exists and
   `APPROVED_CONSENT_SOURCES` still excludes `SCRAPED`, `PURCHASED`, and
   `INFERRED`. If that set has grown, **stop**: the gate this slice builds on
   has been widened somewhere else.
2. `smartmatch_providers.base.SendRequest` still requires `idempotency_key`,
   `approval_id`, and **both** List-Unsubscribe URLs in `__post_init__`. Card
   L5 relies on that refusal being structural.
3. `build_email_provider` still refuses a live client under a fixture-only
   edition. Card L5 does not re-implement that check and must not.
4. The head Alembic revision is `0020_pilot_login_credentials`. Card L3 assumes
   it; a different head means renumbering, not rebasing on top blindly.

## Current state (verifiable, as read on 2026-09-04)

- `smartmatch_domain/outreach_dryrun.py` composes a message and proves
  eligibility. It is unwired, and `tests/unit/test_outreach_dryrun_wiring.py`
  asserts the absence — of a routed command type, of an import from any entry
  point, and of any outreach path in the committed contract.
- `smartmatch_providers` has `SendRequest`, `SendResult`, the `EmailProvider`
  protocol, and `FixtureEmailProvider`. Nothing calls any of them.
- `GET /u/{token}` renders a confirmation page and mutates nothing. Its
  docstring says the signed POST "arrives with R4". This is R4.
- `PipelineRepository` has `record_matched` and `advance_stage`. There is no
  `record_contacted`; **Contacted is a stage of `advance_stage`**, and card L5
  uses it rather than adding a method (the deliverable list named
  `record_contacted` from the older shape of this module).
- The durable command path — `submit_command`, `job`, `outbox_record`,
  `CommandRegistry` — is built and exercised by `import.create` and
  `match-run.create`.

## Out of scope — stated so nobody has to infer it

- **R5 Jarvis / the agentic stream.** `AgenticOutreachPanel` is not ported, and
  `/api/outreach/agentic-workflow/stream` gets no counterpart (B19–B21). A
  second send path that bypasses the command registry would make every
  guarantee below conditional on which path a caller chose.
- **Google Calendar API (G5).** ICS attachment is generated from
  `smartmatch_domain.ics` with explicit datetimes, or omitted. No calendar
  provider is contacted.
- **Live crawl / discovery.** Unrelated gate, unchanged.
- **Inbound mail, replies, threads.** OQ-008.
- **Bounce and complaint webhooks.** `delivery_event` is shaped to receive
  them; nothing ingests them yet, and no route accepts a provider callback.

## Task cards

### Card L1 — plan and deferred questions (first; blocks nothing but read by all)

**Paths:** `docs/plans/2026-09-04-r4-outreach-g4-implementation-plan.md`,
`docs/plans/open-questions/r4-outreach-deferred.md`

Write both before any code. Every OQ carries an implemented safe default whose
failure mode is *not sending*.

**Done when:** both files committed; every later card's deferral points at an
OQ number rather than at a comment.

### Card L2 — domain: `outreach.py` (after L1)

**Paths:** `python/smartmatch_domain/smartmatch_domain/outreach.py`,
`python/smartmatch_domain/smartmatch_domain/outreach_dryrun.py`

Move the template registry, rendering, and eligibility-gated composition into
`outreach.py`. Add:

- `OUTREACH_SEND_COMMAND_TYPE = "outreach.send"`
- `DraftStatus` and `assert_draft_transition` — the approval state machine, in
  the shape of `consent.assert_transition`.
- `compose_draft(...)` — the gate-first composition, returning a draft rather
  than a dry-run disposition.
- `assert_send_allowed(...)` — the worker's re-check, which adds the draft's
  own preconditions (approved, not superseded, content reviewed for live mode)
  on top of `assert_send_eligible` **without restating consent rules**.

`outreach_dryrun.py` becomes a delegating shim that re-exports the names its
existing tests import, so there is exactly one implementation of the
eligibility rules and `tests/unit/test_outreach_dryrun.py` keeps passing
unmodified. A shim rather than a deletion because deleting it would have made
this card a test rewrite as well as a domain change, and the two are worth
being separately reviewable.

**Done when:** `pytest tests/unit/test_outreach_dryrun.py tests/unit/test_outreach_domain.py`
passes; import-linter still reports "Domain is pure"; no eligibility rule is
written down twice.

### Card L3 — schema: migration `0021` (after L1, parallel with L2)

**Paths:** `db/migrations/versions/0021_outreach_schema.py`,
`python/smartmatch_persistence/smartmatch_persistence/schema.py`

Five tables:

| Table | What it is | The constraint that matters |
|---|---|---|
| `contact_channel` | one address plus its consent evidence | `consent_source` in the approved vocabulary, or `contact_state <> 'active_candidate'` |
| `outreach_draft` | rendered subject/body, recipient ref, status | `approved_by`/`approved_at` present iff status is `approved` |
| `outreach_send` | draft + job + idempotency key | `uq_outreach_send_idempotency` on `(tenant_id, idempotency_key)` |
| `delivery_event` | append-only provider event stream | immutability trigger; `(tenant_id, send_id, provider_event_id)` unique |
| `suppression_record` | unsubscribe token **hash** | unique on `(tenant_id, token_hash)`; unique on `(tenant_id, address)` |

`outreach_send.job_id` is `NOT NULL` with a composite FK to `job`, which is
what makes "a send only exists behind a durable command" a property of the
schema rather than of anyone's discipline — the same argument `match_run` makes.

**Done when:** `alembic upgrade head` then `downgrade` is clean;
`tests/unit/test_migration_transactions.py` passes; the schema mirrors match
the migration column for column.

### Card L4 — persistence: `OutreachRepository` (after L3)

**Path:** `python/smartmatch_persistence/smartmatch_persistence/outreach.py`

Draft create/read/list, send-intent reservation, delivery-event append,
suppression lookup and insert, contact-channel read. Sessions in, no commits —
the boundary every other repository here keeps.

The send reservation is `ON CONFLICT ... DO NOTHING` against the idempotency
constraint, returning whether this call was the writer, for the same reason
`MatchRunRepository.record` does: a re-driven job must not send twice.

**Done when:** `tests/integration/test_outreach_persistence.py` passes against
a real PostgreSQL, including the double-reserve and the immutability refusal.

### Card L5 — worker: `outreach.send` (after L2, L4)

**Path:** `services/worker/smartmatch_worker/handlers.py`

Load the draft → re-read the contact channel → `assert_send_allowed` →
suppression lookup → build `SendRequest` → `build_email_provider(...).send()` →
append `delivery_event` → mark the send accepted → advance the pipeline to
Contacted. Register on `default_registry()`.

Failure mapping, which is the part worth reviewing: a consent or suppression
refusal is `PolicyFailure` (terminal — re-driving it would only refuse again);
a provider error is `ProviderFailure` (re-drivable). Getting these backwards
produces either a message retried against a withdrawn consent or a transient
outage recorded as a permanent policy refusal.

No spend reservation — OQ-007.

**Done when:** `tests/unit/test_outreach_handler.py` passes, including the case
where consent is withdrawn *between* draft and send and the handler refuses.

### Card L6 — API: `routers/outreach.py` + the unsubscribe POST (after L5)

**Paths:** `services/api/smartmatch_api/routers/outreach.py`,
`services/api/smartmatch_api/main.py`

Five operations. Quota charged first, ADR-0015 ordering. Coordinator/admin
roles for the four unit-scoped ones; the unsubscribe POST is unauthenticated by
design and authorized by the signed token alone.

`POST .../drafts/{id}/send` returns `202` with `job_id` and `events_url`, and
its response model has no field that could be read as a delivery status.

**Done when:** `pytest tests/contract/test_outreach.py` passes; `make openapi`
produces no diff after the card's own regeneration.

### Card L7 — contract and the absence-to-presence test flip (after L6)

**Paths:** `contracts/openapi/smartmatch.json`, `tests/contract/test_outreach.py`,
`tests/unit/test_outreach_dryrun_wiring.py` → `tests/unit/test_outreach_wiring.py`,
`tests/unit/test_no_external_calls_on_request_path.py`

The absence tests are **rewritten, not deleted**. Each assertion that said "no
outreach command is routed" becomes "exactly `outreach.send` is routed, and it
is the only one" — the guard keeps its shape and changes its expectation, so a
sixth outreach route added later still has to come through a diff a reviewer
sees.

`test_no_external_calls_on_request_path.py` narrows its forbidden segments to
allow the outreach paths this slice publishes, with a comment naming why, and
keeps forbidding crawl, LLM, and vendor segments. The HTTP-client import guard
is untouched: the API still cannot reach the network.

**Done when:** `make check` green; the flip is visible as an expectation
change rather than a deletion.

### Card L8 — legacy UI, docs, PR (after L7)

**Paths:** `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorOutreach.tsx`,
`README.md`, `docs/architecture/diagrams/2026-09-04-system-process-architecture-diagrams.md`

B17: the Send button calls the real draft-then-send pair and renders the job's
own state. There is no success toast; there is a queued state with a job id.
B18's "create thread" is removed rather than wired — there is no thread
(OQ-008), and wiring a button to a table that does not exist would be B17's
defect in a new place.

**Done when:** `test_frontend_no_fake_success_contract.py` passes; the README
row says implemented-against-fixture rather than implemented.

## Card dependency graph

```
L1 ──┬─> L2 ──┬─> L5 ──> L6 ──> L7 ──> L8
     └─> L3 ──> L4 ──┘
```

L2 and L3 are independent and may run in parallel after L1. L5 needs both the
domain rules (L2) and the tables to write to (L4). Everything downstream of L5
is sequential: the contract cannot be regenerated before the routes exist, and
the UI cannot be wired before the contract says what it is calling.

## Evidence ladder

1. `make format-check lint typecheck imports` — style, types, and the domain
   purity contract.
2. `pytest tests/unit/test_outreach_domain.py tests/unit/test_outreach_wiring.py`
   — the domain rules and the wiring guards. The handler and persistence
   tests live under `tests/integration/` because what they assert is which
   writes survive which failures, which is not observable without a real
   database.
   The basename is `test_outreach_domain.py` rather than `test_outreach.py`:
   pytest imports test modules by basename, so it would have collided with
   `tests/contract/test_outreach.py`.
3. `pytest tests/contract/test_outreach.py`
4. `pytest tests/integration/test_outreach_persistence.py` — needs PostgreSQL.
5. `make openapi-check` — the committed contract matches the application.
6. `make check` — everything CI runs.

## Done means

Every card's done-when holds, the OQ list is in the PR body, and the README
says what is actually true: the outreach path is implemented end to end and
sends through a fixture provider, and a live send is blocked on OQ-001,
OQ-002, and OQ-003 rather than on missing code.
