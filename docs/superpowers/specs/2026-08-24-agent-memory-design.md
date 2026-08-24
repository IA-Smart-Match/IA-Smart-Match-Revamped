# Agent memory for SmartMatch — design

**Status:** Proposed
**Date:** 24 August 2026
**Supersedes:** nothing. First design in this area.
**Research basis:** dependency verification performed 23–24 August 2026 (§7).

## 1. Problem

Agents working in this repository re-derive the same context every session. They
re-read the same ADRs, rediscover the same constraints, and occasionally assert
things about the system that stopped being true. The cost is paid on every
session start, and the failure mode — an agent confidently acting on a stale
belief — is worse than the cost.

What is wanted is a durable, reviewable record of what has been learned, that an
agent can consult cheaply and that cannot quietly drift away from the code.

## 2. What this design refuses to build, and why

The originating brief specified a three-layer system: a committed Markdown
ledger, a pinned Graphify structural index, claude-mem lifecycle capture, a
`tools/agent_memory/` package containing a gateway, storage, redaction,
promotion workflow and two adapters, a five-schema contract family, and an
authenticated HTTPS MCP gateway hosted in an isolated GCP project.

Verification of the external dependencies changed the design. Four premises did
not hold.

**claude-mem does not perform the role assigned to it.** The brief has it
producing "redacted, expiring candidates." It performs no automatic redaction —
only manual in-prompt tagging — it sends captured tool data to a third-party
model before storing it, and it implements no expiry. It was to be the component
closest to student-adjacent data and it is the component that ships data
outward. It is not adopted.

**Graphify cannot be pinned in the sense the brief intends.** At the time of
writing it is at version 0.9.48 with roughly 216 releases since April, a default
branch of `v8` alongside branches `v1` through `v7`, and over a thousand open
issues. Its PyPI distribution is named `graphifyy`; the name `graphify` is
unregistered, so a plausible typo installs an unrelated package. Its
documentation-indexing pass sends repository documents to a third-party model.
Against a repository whose dependency locks are hash-pinned specifically so that
"a compromised or newly-broken upstream release cannot be picked up silently,"
this is not a casual addition. It is deferred to an optional, manually-run,
git-ignored tool (§6, slice 3) and is not added to `requirements/`.

**The repository already has the redaction backstop the brief proposed to
build.** `tools/scan_forbidden.py` walks every file in the tree, not only Python,
and its `hard-coded-credential` rule carries no file-type restriction. Anything
committed under `docs/` is therefore already subject to a mandatory, executable,
pre-merge secret gate. Rows in a gateway database would not be. This is the
decisive argument for a committed ledger over a service, and it carries one
binding consequence: **`docs/agent-memory/` must never be added to
`EXCLUDED_PREFIXES`.** Exempting the ledger from the scanner would discard the
single strongest control this design has.

**Two retention rules in the brief are not implementable on a committed
ledger.** "Redact approved operational payloads by 90 days" cannot be honoured in
git: history is append-only, and redacting a file at day 90 leaves the payload in
every existing clone and fork. Likewise "retain audit metadata for 18 months"
describes a bounded store, whereas the audit trail here is `git log`, which is
unbounded. This design resolves both by construction (§4): approved records are
permanent and hold no payloads, so nothing in them has a 90-day life, and the
retention policy states the life of the repository rather than a figure the
system does not implement. Asserting a capability the system lacks is the
specific class of defect `docs/plans/defect-remediation.md` exists to prosecute.

Two further corrections carried into the threat model: Claude.ai's remote MCP
connectors have no platform-enforced read-only mode, so read-only is this
project's code to enforce; and Codex `PostToolUse` hooks run concurrently and
cannot block, so no hook may be relied on as a security control.

## 3. Architecture

**Files are the source of truth. There is no service.**

Approved memory is committed Markdown under `docs/agent-memory/approved/`, one
record per file, carrying structured YAML front matter. A validator runs in
`make check`. Later, a thin stateless local MCP server reads those same files
directly and holds no state of its own.

Governance is inherited rather than built:

| Requirement | Mechanism |
|---|---|
| Approval | A merged pull request |
| Audit trail | `git log` |
| Reviewer attribution | Commit authorship and the `reviewed_by` field |
| Secret gate | `make check` running `tools/scan_forbidden.py` |
| Access control | Repository permissions |
| Rollback | `git revert` |

The promotion workflow specified in the brief — gateway, queue, reviewer state
machine — already exists as code review. Building a second one is the clearest
instance of over-engineering in the original design.

This ordering is deliberate and reversible: a ledger of files can later be served
by a gateway, but a gateway's database cannot be retrofitted into the review and
scanning guarantees that committing to git provides for free.

### 3.1 Records are pointers, not payloads

A record cites where a fact lives — a repository-relative path plus the git blob
SHA of the file at the time of approval — and states a short claim about it. It
does not copy the content.

This is the central safety property, and it is structural rather than
probabilistic. The realistic leak in a system like this is not a credential that
a regular expression catches; it is a fluent English sentence describing a real
student, committed permanently to git history where no later redaction can
reach it. A record that may only point at repository files cannot contain such a
sentence, because the repository does not contain one. Redaction quality stops
being the load-bearing control.

It also makes permanence safe, which is what allows §2's retention contradiction
to dissolve instead of needing a mechanism.

### 3.2 Staleness is the only thing here a notes file cannot do

Every cited source carries the blob SHA it had when the record was approved. The
validator recomputes those SHAs and marks a record `stale` when a cited blob has
moved, when a cited path no longer exists, or when the worktree is dirty for a
cited path — the last because a claim about uncommitted content cannot be
verified by anyone else.

This is the entire justification for the ledger being a system rather than a
scratchpad, and it is roughly 150 lines of stdlib Python. Every other component
in the original brief is a delivery mechanism for content this check keeps
honest.

### 3.3 Memory never outranks the repository

Records carry an `authority` field whose permitted values are `observation` and
`convention`. `decision` is deliberately not a permitted value: architectural
decisions are ADRs, and a memory record that believed itself to be a decision
would create a second, unreviewed decision store competing with
`docs/architecture/decisions/`.

Contracts, code, tests and ADRs outrank memory in every case. A record whose
claim conflicts with the code is a defect in the record.

### 3.4 Repository identity survives ownership transfer

`.agent-memory.yaml` holds a `repository_id` minted once as a UUID. It is never
derived from the remote URL. Remote URLs are recorded, if at all, as
non-authoritative aliases.

The ownership transfer from `BrooklynD23/...` to `IA-Smart-Match/...` is
therefore not an event this system needs to handle: identity was never tied to
the URL. Historical provenance in existing documents stays as written and is not
retroactively relabelled.

## 4. Record schema

One record per file, named `NNNN-short-slug.md`.

**Front matter is flat — no nested mappings.** This is a deliberate constraint,
not a limitation. PyYAML is present in this repository only as a transitive
dependency of `uvicorn[standard]`; it is not declared in `requirements/*.in`,
and a gate that runs on every `make check` must not rest on a package nothing
declares. A flat `key: value` grammar with `- item` lists is parseable in about
forty lines of stdlib, and it removes a class of YAML surprises — implicit type
coercion, anchors, arbitrary tags — from a format that carries security-relevant
fields. Nested values are flattened with underscores (`produced_by_tool`), and a
source is written as `path@blob_sha`.

```markdown
---
schema: agent-memory/record/v1
entry_id: 018f3c2a-7b4e-7c1d-9a2f-3e5d6c7b8a90
project_id: smartmatch
repository_id: <uuid from .agent-memory.yaml>
status: approved
authority: observation
privacy_class: repo-public
claim: One or two sentences. What was learned.
sources:
  - docs/architecture/decisions/ADR-0005-transactional-outbox-and-cte-claim.md@<blob sha>
produced_by_tool: claude-code
produced_by_session: <session uuid>
produced_by_commit: <commit sha>
reviewed_by: <reviewer identity>
approved_at: 2026-08-24T00:00:00Z
expires_at: null
supersedes: null
superseded_by: null
conflicts_with:
content_hash: <sha256 of body, set by the validator>
---

Prose body. Descriptive, not imperative. Points the reader at the sources.
```

**Field rules.**

- `status` is one of `approved`, `superseded`, `revoked`, `stale`. Candidates
  never appear in this directory.
- `authority` is `observation` or `convention` (§3.3), or `external-research`,
  which additionally requires a non-null `expires_at` no more than 30 days after
  `approved_at`.
- `privacy_class` must be `repo-public`. It is the only class permitted in
  `approved/`; anything else is not committed at all. The field exists so that
  the rule is visible in the record rather than only in this document.
- `sources` accepts `path@blob_sha` entries with repository-relative paths only.
  Absolute paths, URLs and parent-directory traversal are rejected.
- `expires_at` is null for `observation` and `convention`, meaning the record
  lives until it is superseded or goes stale.

## 5. Lifecycle

```
   agent proposes            human moves file,           validator, automatically
        │                    fills reviewed_by,                    │
        ▼                    opens a PR                            │
  ┌───────────┐                   │                                ▼
  │ candidate │───────────────────┼──────────►┌──────────┐   ┌────────┐
  │(git-ignored)                  │           │ approved │──►│ stale  │
  └─────┬─────┘                   │           └────┬─────┘   └────────┘
        │                                          │
        ├──► expires at 30 days  [default outcome] ├──► superseded
        └──► quarantined (schema violation)        └──► revoked (tombstone)
```

**Transition rules.**

- Only a human performs `candidate → approved`, and only through a merged pull
  request.
- **No agent may approve any candidate** — not merely its own. The stronger rule
  is simpler to enforce and gives up nothing.
- `approved → stale` is performed automatically by the validator and is the only
  automatic transition out of `approved`. Stale records are excluded from search
  results by default.
- `revoked` retains the file as a tombstone with the body removed so that
  superseding links do not dangle. It does not remove content from git history,
  which is why §3.1 forbids payloads in the first place.
- Candidate expiry is `find .agent-memory/candidates -mtime +30 -delete` in a
  make target. That is the whole of the 30-day retention implementation.

## 6. Slices

Each slice stands alone and is separately abandonable.

**Slice 0 — the ledger and its validator.** `docs/agent-memory/approved/` with a
small number of hand-written records; the schema in §4 documented in one Markdown
file; `.agent-memory.yaml` with exactly `project_id`, `repository_id` and
`policy_version`; and `tools/agent_memory_check.py`, a single stdlib-only file
wired into `make check`, which parses front matter, rejects unknown or missing
fields, verifies cited blob SHAs and marks stale records, rejects non-repository
pointers, rejects instruction-shaped language in bodies, and enforces caps on
record count and length.

`.agent-memory.yaml` gains `graphify_revision` and gateway discovery keys when
and if those things exist. A configuration file describing systems that do not
exist is an untrue assertion about the repository.

**Measurement gate — before any further slice.** Write down ten questions the
memory is meant to answer. Check whether the ledger answers them better than
`rg` over `docs/` does. If it does not, delete `docs/agent-memory/` and stop. The
cost of learning this is one day.

**Slice 1 — local read-only stdio MCP.** One stateless process, no network,
exposing `memory_search` and `memory_get` over the committed Markdown, registered
in `.codex/config.toml` and in Claude Code's local MCP configuration. No
database: re-reading the files per call is preferable, because it leaves no state
that can disagree with the repository.

**Slice 2 — human-initiated proposals.** `memory_propose` writes a candidate to a
git-ignored `.agent-memory/candidates/`. Promotion is a pull request.

**Slice 3 — Graphify as an optional local tool.** A documented manual `make
graph` writing to a git-ignored output directory, installed outside
`requirements/`, required by nothing, in `make check` never. Reconsidered as a
pinned dependency only if it reaches a stable release and proves its worth.

**Slice 4 — remote read-only access for Claude.ai web.** Only on evidence from
slices 0–2, and only with the isolation the original brief specified: a separate
GCP development project, a separate database, and a service account that cannot
reach SmartMatch databases, providers or production secrets. The threat to model
is the public internet reaching the gateway — OAuth misconfiguration, bearer
credentials leaking into agent transcripts, absent rate limiting, and an endpoint
serving content derived from a private repository.

**Slice 5 — automatic capture, and remote proposals.** Deliberately last. The
original pilot order placed automatic capture second; it is the
highest-volume and highest-risk slice, it lands on a single reviewer, and it may
never be worth building. Nothing else depends on it.

## 7. Risks

**Prompt injection through memory.** An agent reading a record treats it as
context. A record containing instruction-shaped text is an injection vector into
every future session. Mitigations: bodies are descriptive prose, the validator
rejects instruction-shaped language, records may only point at repository files,
and approval requires human review of a diff.

**A record outliving its truth.** Addressed by §3.2's staleness check, which is
the reason the system exists. The residual risk is a claim that becomes false
without its cited blob changing — for example a claim about behaviour that
changed elsewhere. Human review and the pointer-only rule limit the blast radius;
nothing eliminates it.

**Ledger degradation.** A ledger that grows without curation becomes noise, and
retrieval quality falls. The record cap in slice 0 is a deliberate forcing
function: reaching it requires deleting or superseding something.

**Review burden on a single reviewer.** Every approval is a human PR review. This
is the reason automatic capture is last: it is the slice that would generate
volume this workflow cannot absorb.

**Scanner interaction.** Because `docs/` is scanned, a record quoting a
configuration line or a credential shape will fail `make check`. This is correct
behaviour and must not be worked around by extending `EXCLUDED_PREFIXES` (§2).

## 8. Relationship to existing decisions

ADR-0003 forbids agent frameworks, agent code, and agent dependencies in
Foundation. This design is developer tooling rather than product code and does
not ship in the API or worker images, so it does not fall under that prohibition.
Its rationale is nonetheless directly applicable — a dependency's "transitive
tree and vulnerability surface would exist for two releases before anything used
them" — and is a substantial part of why Graphify and claude-mem are deferred
rather than adopted.

ADR numbering: this work takes **ADR-0010**. **ADR-0009** is the migration
transaction-boundary decision (F11), which landed in `ba5f9df`.

## 9. Open questions

1. Does the ledger beat `rg` over `docs/`? Answered by the measurement gate, not
   by argument.
2. Where do candidate records live relative to worktrees? A git-ignored
   directory is per-worktree, so candidates proposed in one worktree are
   invisible in another. Acceptable for slice 2; revisit if it bites.
3. Who is `reviewed_by` when the repository has one maintainer? The field is
   honest attribution, not separation of duties, until there is a second
   reviewer. It should say so rather than imply a control that does not exist.
