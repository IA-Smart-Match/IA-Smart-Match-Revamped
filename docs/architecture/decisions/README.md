# Architecture decision records

Every architectural decision made while building this repository, in number
order. An ADR is immutable once accepted: a decision that stops being true is
replaced by a new ADR that supersedes it, and both rows stay in this table, so
the history of a decision is readable without `git log`.

An ADR that is *refined* rather than replaced carries an amendment instead. The
amendment column below records those, because an ADR whose `Status` line reads
"Accepted — amended…" has a body that no longer matches its original date, and
that is worth seeing from the index.

## The index

| # | Title | Status | Date | Decides | Amended | Supersedes | Superseded by |
|---|-------|--------|------|---------|---------|------------|---------------|
| [ADR-0001](ADR-0001-monorepo.md) | Single monorepo for the SmartMatch platform | Accepted | 17 August 2026 | One repository holds the web app, API, worker, four Python packages, schema, and infrastructure — not one repository each. | — | — | — |
| [ADR-0002](ADR-0002-package-boundaries.md) | Package boundaries enforced by import-linter | Accepted | 17 August 2026 | The four layers of Architecture v1.1 §1.1 are enforced by an executable contract in CI, not by convention. | — | — | — |
| [ADR-0003](ADR-0003-no-agents-in-foundation.md) | No agent framework in the Foundation scaffold | Accepted | 17 August 2026 | Foundation ships no agent orchestration, adapter, or tool layer; the framework choice is deferred rather than inherited from the legacy repository. | — | — | — |
| [ADR-0004](ADR-0004-hand-written-schema-and-ltree.md) | Hand-written Core schema, hand-written migrations, and a declared `ltree` type | Accepted | 18 August 2026 | The schema and its migrations are written by hand and reconciled by a drift test, rather than one being generated from the other. **Also records the structural tenant-isolation mechanism** — the composite `(tenant_id, id)` key on tenant-owned tables — in Context, with Decision explaining why it is filed here. | 19 August 2026 — the drift test now covers the schema, not a list | — | — |
| [ADR-0005](ADR-0005-transactional-outbox-and-cte-claim.md) | The transactional outbox, and claiming with a CTE | Accepted | 18 August 2026 | A job and its dispatch intent share one transaction, which does **not** make the job and the Cloud Task atomic — nothing can — but converts the problem into one commit plus a retryable follow-up. **The outbox claim** is a single CTE using `FOR UPDATE SKIP LOCKED`. | 20 August 2026 — the invariant had two halves, and only one was guarded | — | — |
| [ADR-0006](ADR-0006-fixed-window-rate-limiting-in-postgresql.md) | Fixed-window rate limiting in PostgreSQL | Accepted | 18 August 2026 | Layer-2 per-caller limiting is a fixed window counted in PostgreSQL, not a sliding window and not a separate store. | — | — | — |
| [ADR-0007](ADR-0007-deterministic-task-names.md) | Deterministic Cloud Tasks names as the deduplication mechanism | Accepted | 18 August 2026 | The crash window ADR-0005 leaves open is closed by deriving the task name from the job, so a re-enqueue collides instead of duplicating. | 19 August 2026 — the re-drive collision is resolved | — | — |
| [ADR-0008](ADR-0008-globally-unique-external-subject.md) | Globally unique `external_subject` as the identity lookup's licence | Accepted | 19 August 2026 | `external_subject` is unique across all tenants, which is what makes the identity lookup's tenant-free filter correct rather than merely convenient. | — | — | — |
| [ADR-0009](ADR-0009-transaction-per-migration.md) | One transaction per Alembic revision | Accepted | 24 August 2026 | Each Alembic revision runs in its own transaction, so a lock a revision takes is released when that revision ends rather than at the end of the run. | — | — | — |
| [ADR-0010](ADR-0010-event-temporal-model.md) | An event carries an instant, an IANA zone, and a precision | Accepted | 25 August 2026 | An event's time is three fields — a UTC instant, the IANA zone the event *happens in*, and a precision of `exact`, `date_only` or `unresolved`. An event at `unresolved` cannot reach a matchable or publishable state, and display renders in the event's own zone with the zone named. Generalizes the rule `generate_ics` already enforces for its own output. | — | — | — |
| [ADR-0011](ADR-0011-accountable-numbers.md) | Every user-visible number is accountable | Accepted | 25 August 2026 | Four rules for any number a user can see: a value with no evidence is `unknown` and never `0`; every aggregate has one canonical name and a written definition in a register; each registered metric has exactly one owning query; and a drill-down returns exactly the rows the aggregate was computed from — the only one of the four a test can check unaided. | — | — | — |
| [ADR-0012](ADR-0012-event-identity-and-tag-vocabulary.md) | Deterministic event identity, and a closed tag vocabulary | Accepted | 25 August 2026 | Extracted events resolve by a deterministic key — host org unit, normalized title, resolved date window — so re-crawling updates rather than duplicates, and an `unresolved` event has no key at all. Source provenance is a structured field, never part of the title. Role and type tags come from a closed versioned vocabulary; unmapped values are quarantined, never rendered and never matched on. | — | — | — |
| [ADR-0013](ADR-0013-attendance-derived-engagement.md) | Attendance-derived engagement: a server-side ledger, and rewards with an owner | Accepted | 25 August 2026 | Points are a fold over an append-only `point_ledger_entry` derived from recorded attendance and nothing else — never a stored counter and never a browser formula, and a reversal is a compensating entry rather than a delete. Redemption is a command with an approval step. A catalog item with a real fulfilment cost cannot be listed without a named budget owner and a funded balance, and the economy is calibrated against a stated, tested property. | — | — | — |
| [ADR-0014](ADR-0014-disclosure-consent.md) | Disclosure consent is a separate record from contact consent | Accepted | 25 August 2026 | Permission for a *peer* to see that someone attended is its own record — subject, audience scope, purpose, granted/revoked — and **not** `smartmatch_domain.consent` widened, which models an organization's licence to contact a discovered person and has no audience dimension at all. Also records that in-app chat is cut rather than deferred. | — | — | — |
| [ADR-0015](ADR-0015-charge-quota-before-refusal.md) | Charge quota before the route can refuse the request | Accepted | 25 August 2026 | Every command route charges quota as its **first** statement — ahead of the resource load, the authorization, and the header and body validators — and the charge commits in a transaction of its own, so a `403`, `404` or `400` costs the caller what they spent producing it. Decides that an authenticated caller pays for requests they were never allowed to make, and for ids that do not exist. Refines ADR-0006's *timing*, not its counting. | 31 August 2026 — Amendment A1 ratified as session policy: monetary spend gets reserve-before-paid-call semantics, distinct from quota counting; live-provider estimate A3, credentials, and production ceilings remain external dependencies, not ratified by this entry (see the ADR's Amendment A1 section) | — | — |
| [ADR-0016](ADR-0016-cba-scoring-policy.md) | CBA scoring policy: neutral Topic, proximity bands, and virtual redistribution | Accepted | Drafted 5 September 2026; accepted 5 September 2026 | **Accepted — closes OQ-CBA-001, OQ-CBA-002 and OQ-CBA-004.** Ten proposals, all approved as drafted by Danny Tran, Development Lead / program owner of record. Establishes a third evidence state, `policy_neutral`, separating the customer's §9 neutral Topic score from a genuine `unknown`, so that only `unknown` makes a composite unscorable and weights are never re-spread per candidate. Sets the neutral value at `0.50` as the versioned constant `CBA_NEUTRAL_TOPIC_VALUE` (`cba-neutral-topic 1.0.0`) carried on every score that used it. Fixes proximity as a step function on raw miles — Near `<25` → `1.00`, Mid `25–<75` → `0.60`, Far `≥75` → `0.20` — lower-inclusive and upper-exclusive, with a missing address as `unknown` rather than Far. Handles virtual events as pinned scoring modes (`cba-physical-1` / `cba-virtual-1`) with proportional redistribution to `0.428571` / `0.357143` / `0.214286`. Moves `REGISTRY_VERSION` to `2.0.0-approved-oq-cba-004`, with 1.x runs readable but never compared across the bump. Refines ADR-0011 without amending it. | — | — | — |
| [ADR-0017](ADR-0017-offline-embedding-topic-semantics.md) | An offline, in-process embedding model is approved for §9 Topic | Accepted | 7 September 2026 | **Accepted — closes OQ-CBA-026 and dissolves OQ-CBA-061.** Approves averaged GloVe word-vector embeddings (Public Domain Dedication, ~4.2 MB vendored), run in-process with no network egress and no vendor, for customer §9's Topic comparison. `LocalEmbeddingSemanticTopicProvider.is_semantic_model` is genuinely `True`. `build_semantic_topic_provider` keeps the deterministic playback fixture as the default for every caller who does not opt in with `use_local_embedding=True`, and the refusal of a live, external vendor client is unchanged. | — | — | — |
| [ADR-0018](ADR-0018-service-packages-under-import-linter.md) | Service packages are governed by import-linter | Proposed | 8 September 2026 | `smartmatch_api` and `smartmatch_worker` — 28,080 lines, 40% of production Python — join the four `python/` packages in `[tool.importlinter].root_packages`, with two new contracts: routers may not import sibling routers, and the two services may not import each other. `smartmatch-persistence` is declared in both service manifests first, because a contract over a package whose manifest omits a dependency it imports in 43 files governs a graph only CI can reproduce. The two existing router→router imports land as named `ignore_imports` lines and are removed within the same increment by promoting the shared authorization helpers into an owned module, on `job_authz.py`'s pattern. | — | — | — |
| [ADR-0019](ADR-0019-declared-table-ownership.md) | Table ownership is declared as data before any schema split | Proposed | 8 September 2026 | Every one of the 44 tables names one owning bounded context, one owning repository module and a declared writing-service set in `smartmatch_persistence/ownership.py`, checked both ways against `schema.py` and against `tools/derive_table_writers.py` by a test. More than one writing service is permitted only with a declared reason — five command-path tables (`job`, `job_event`, `outbox_record`, `idempotency_record`, `spend_reservation`) name both services under ADR-0005. Resolves match-run ownership explicitly — the worker alone writes the `match_run` snapshot — and turns ADR-0013's unasserted single-writer premise for `attendance_record` into an assertion. **Does not decide the `schema.py` split**, which is permitted only along declared ownership lines and only after this map is green. | — | — | — |
| [ADR-0020](ADR-0020-generated-typescript-client-and-drift-gate.md) | A generated TypeScript client, with a drift gate | Proposed | 8 September 2026 | `clients/typescript` is generated from `contracts/openapi/smartmatch.json` by a pinned generator, committed, and regenerated-and-diffed by the CI gate already listed as deferred at the bottom of `verify.yml`. The tool is an implementation detail bound by three criteria — deterministic output, no browser runtime, types first. One page is migrated as the pattern and `lib/api.ts` becomes an adapter; the other 48 follow later. The FastAPI `description` that already claims a generated client becomes true in the same change. | — | — | — |
| [ADR-0021](ADR-0021-worker-task-delivery-contract.md) | The worker task-delivery contract is the acceptance test for any queue adapter | Proposed | 8 September 2026 | The `worker/main.py` docstring's semantics — at-least-once tolerated, duplicate delivery answers `200` and executes nothing twice, pre-dispatch race answers `503` and is redelivered, task names deterministic from the job (ADR-0007), OIDC verified before the body is read so an unauthenticated malformed request answers `401` and never `422`, and an unconfigured queue answers `501` rather than falling back to an in-memory double — become a parameterized contract suite. It runs today against `FixtureTaskQueue` and the PostgreSQL loopback queue and must pass **unchanged** against any live adapter. No live adapter is built here. | — | — | — |
| [ADR-0022](ADR-0022-appliance-is-production-topology.md) | The Docker Compose appliance is the production topology | Proposed | 8 September 2026 | The Compose appliance on a VM is the topology of record, and its answers to rollback, log destination and deploy-time migration are the system's answers. The GCP Terraform is a forward design record whose non-applyability — enforced by `tools/env_isolation_check.py` — is a property to preserve, not a limitation to remove; it is not deleted. Any move toward GCP first satisfies ADR-0021's contract suite and closes OQ-F5-001…004, whose answers belong to the program and security owners rather than to engineering. | — | — | — |
| [ADR-0023](ADR-0023-command-registry-completeness.md) | Every submittable command type is registered or explicitly refused | Proposed | 8 September 2026 | A test derives every command type any router passes to `submit_command` and asserts each is in the **composed** production registry — `default_registry()` plus the root compositions in `worker/main.py`, checked with and without spend ceilings — or on an explicit `INTENTIONALLY_REFUSED` list, empty today. The three idempotency-scope names (`speaker_contact.create`, `job.redrive`, `job.abandon`) are listed as such so the test does not mistake them for commands. Records that root-composed handlers are legitimate — they take collaborators a zero-argument factory cannot supply — but must be visible to the test. | — | — | — |

## Two pointers worth having

Two decisions are recorded in a *section* people do not find by scanning
filenames. Both pointers name the section, because that is the part that is
hard to locate:

- **The structural tenant-isolation mechanism** is in
  [ADR-0004](ADR-0004-hand-written-schema-and-ltree.md), under "Context", and
  justified under "Decision". The mechanism is a composite `(tenant_id, id)`
  unique key on every tenant-owned table, with every foreign key **from a
  tenant-owned child to a tenant-owned parent** being the composite pair. Note
  the scope: a foreign key straight to `tenant` stays single-column, and
  ADR-0004's amendment says so. This one is genuinely invisible from the
  filename — nothing in `hand-written-schema-and-ltree` suggests tenant
  isolation — and it is filed there because it is the reason hand-writing was
  chosen, not a separate decision. It is **not** in that ADR's "The `ltree`
  type" section, which is about path storage and its GiST index.
- **Why the outbox claim is one CTE** rather than a select followed by an
  update is in [ADR-0005](ADR-0005-transactional-outbox-and-cte-claim.md),
  under "Why the claim is a CTE". Unlike the entry above, this ADR's filename
  and title do name the CTE claim; what they do not tell you is that the
  reasoning — PostgreSQL cannot hash a subplan containing `FOR UPDATE`, so an
  `IN (SELECT ... LIMIT n)` may re-execute and blow the batch size — is there
  rather than in the code.

## Reserved numbers

**There is no reserved number.** Agent-memory Slice 1
(`docs/superpowers/plans/2026-08-24-agent-memory-slice-0.md` and the design spec
beside it) still has no file, and it now holds no number either. When it is
written it takes the next free one.

The reason is worth stating once rather than re-deriving: **a reservation with no
file cannot hold its number**, because `test_adr_numbers_are_contiguous_from_one`
refuses a gap. An ADR written while the reservation is unfilled therefore takes
the next free number and the reservation moves up; the alternative is a failing
lane, not a preserved number.

The reservation has now been displaced three times, for the same reason each
time. It was **ADR-0010** until 25 August 2026, when the five ADRs arising from
the stakeholder test-log audit took 0010–0014. It was **ADR-0015** until 25
August 2026, when the J16 rate-limit decision took that number. It was
**ADR-0016** until 5 September 2026, when the CBA scoring policy took that number
— and this section went on naming 0016 as reserved and file-less for three days
after `ADR-0016-cba-scoring-policy.md` was committed, which is the fourth
documentation drift of the kind `risk-register.md` R-15 records, in the one file
whose whole purpose is to be an accurate index.

Slice 1 had no file on any of the three occasions, so nothing was displaced but
the reservation itself. It is tracked in `adr-backlog.md` as B-09, which is where
a decision with no evidence and no number belongs.

## This table is checked, not maintained by hope

`tests/unit/test_adr_index.py` reads every `ADR-*.md` in this directory and the
table above, and fails the no-database lane if they disagree. It checks:

- **Membership, both ways.** An ADR with no row, or a row with no ADR. Two files
  claiming one number is an error, not a silent overwrite.
- **Identity.** Each row's link target, title, bare status, and date against the
  ADR's first line and header block.
- **Where it reads from.** The table is read only from between `## The index`
  and the next level-1 or level-2 heading, and an ADR's header only from above
  its first level-2 heading. Fenced code blocks are resolved *first*, so a
  heading inside a fence does not truncate either range and a table row inside
  one is not data. Fences are tracked by marker character and run length, as
  CommonMark defines them, so a tilde fence inside a backtick block is content
  rather than a closer.
  Headings allow the up-to-three leading spaces CommonMark permits, no more
  (four spaces is an indented code block), and accept a tab as the separator.
- **Amendments.** An ADR whose status says "amended" must have an Amended cell
  whose **leading date token** equals the date the status line gives. Not a
  prefix test: `20 August 20260` would pass one.
- **Supersession.** Each cell must be `—` or a comma-separated list of
  `ADR-NNNN` or `[ADR-NNNN](ADR-NNNN-slug.md)` — the whole cell, so a malformed
  name cannot hide beside a well-formed one, and a link whose text and target
  disagree is an error. Every name must be a real ADR, must not be the ADR
  itself, and must be recorded from both ends. `Superseded by` and status
  `Superseded` each require the other.
- **Status vocabulary.** Every status is one of `Accepted`, `Proposed`,
  `Rejected`, `Superseded`, `Deprecated`.
- **Order and numbering.** Rows in number order; ADR numbers contiguous from
  0001.

### What is not checked, and has already been wrong once

The **"Decides" column is prose, and nothing verifies it.** No test can tell
whether a one-line summary still describes the decision. This is not a
hypothetical: the first draft of this table said ADR-0005 made a job row and its
Cloud Task "atomic", which is the opposite of what ADR-0005 decides — it says in
as many words that the two systems cannot be made atomic. An independent review
caught it before this file was committed. Expect the next one to be caught the
same way, or not at all.

The **Amended column's description** is checked for its date and not its wording,
for the same reason.

When an ADR is amended, re-read its row.
