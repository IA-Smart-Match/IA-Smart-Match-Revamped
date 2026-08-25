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

**ADR-0010 is reserved** for agent-memory Slice 1
(`docs/superpowers/plans/2026-08-24-agent-memory-slice-0.md` and the design spec
beside it). It has no file yet. Do not take that number for anything else.

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
