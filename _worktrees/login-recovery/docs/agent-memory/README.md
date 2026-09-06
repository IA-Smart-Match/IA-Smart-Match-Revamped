# Agent memory — the shared policy

This directory is the **approved memory ledger**: what agents working in this
repository have learned and a human has confirmed. It is plain committed
Markdown, validated by `tools/agent_memory_check.py` on every `make check`.

Design and rationale: `docs/superpowers/specs/2026-08-24-agent-memory-design.md`.

## The one rule that matters

**Memory never outranks the repository.** Contracts, code, tests and ADRs are
higher authority in every case. A record whose claim conflicts with the code is
a defect in the record, not a finding about the code.

## Records are pointers, not payloads

A record cites repository-relative paths and the git blob SHA each had when the
record was approved, and states a short claim about them. It never copies file
content, log lines, error text, query text, or data of any kind.

This is what makes permanence safe. Git history is append-only, so anything
committed here cannot later be redacted out of existing clones. A record that
may only point at repository files cannot contain a sentence about a real
person, because the repository does not contain one.

## Fields

Front matter is **flat** — `key: value` scalars and `- item` lists, no nested
mappings. `tools/agent_memory_check.py` is the authority on the field set; it
rejects anything missing or unrecognised. Notable rules:

| Field | Rule |
|---|---|
| `authority` | `observation`, `convention`, or `external-research`. **Never `decision`** — decisions are ADRs. `external-research` requires a non-null `expires_at` within 30 days. |
| `privacy_class` | Must be `repo-public`. It is the only class permitted here; anything else is not committed at all. |
| `sources` | `path@blob_sha` entries, repository-relative only. Absolute paths, parent traversal and URLs are refused. At least one is required. |
| `content_hash` | `sha256:` over the stripped body. A body edited after approval fails the gate. |
| `status` | `approved`, `superseded`, `revoked`, or `stale`. Candidates never live here. |

`project_id` and `repository_id` must match `.agent-memory.yaml`. A record
copied from another repository carries a well-formed identity that is not this
one, and the gate rejects it — which is the point of minting `repository_id`
once rather than deriving it from the remote URL.

The instruction check applies to the `claim` as well as the body: both are read
by agents, and a record with an impeccable body and a directive claim is the
obvious way around a body-only check.

Obtain a blob SHA with:

```bash
git rev-parse HEAD:path/to/file.md
```

Recompute a body hash by running the validator; it names the value it expected.

## Staleness

The validator recomputes each cited blob SHA. A record is reported when its
source has moved, is untracked at HEAD, or has uncommitted changes — the last
because a claim about uncommitted content cannot be verified by anyone else.

This check is the only thing here a plain notes file cannot do, and it is the
whole reason this is a system rather than a scratch file. When it fires,
re-verify the claim and update the record, or mark it superseded. Do not update
the SHA alone.

Freshness applies to records claiming to be current. A `superseded`, `revoked`
or `stale` record is history, and is exempt — otherwise the remedy above would
itself fail the gate. The pointer rule is never suspended: repository-relative
paths are required whatever the status.

## Promotion is a pull request

There is no gateway, queue, or reviewer state machine. Approval is a merge, the
audit trail is `git log`, and reviewer attribution is commit authorship plus the
`reviewed_by` field.

**No agent may approve any candidate** — not merely its own.

While this repository has a single maintainer, `reviewed_by` is honest
attribution rather than separation of duties. It should not be read as a control
that does not yet exist.

## Bodies describe; they do not direct

A record is read as context by every future agent session, so instruction-shaped
text in one is an injection vector reaching every later run. The validator
refuses imperative framing aimed at the reader's behaviour.

## Never exempt this directory from the scanner

`tools/scan_forbidden.py` walks every file type, and its credential rule applies
to all extensions — so this ledger inherits a mandatory, executable, pre-merge
secret gate simply by being committed. That is the strongest control this design
has, and the reason the ledger is files rather than rows in a service.

If a record trips the scanner, **rewrite the record**. Adding
`docs/agent-memory/` to `EXCLUDED_PREFIXES` would throw the control away.
