# ADR-0020 — A generated TypeScript client, with a drift gate

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §4.1 (staged gates); `contracts/openapi/smartmatch.json`
**Backlog:** Stage 2 AP-07; migration increment M3
**Findings:** `docs/architecture/risk-register.md` R-02, R-15;
`docs/architecture/capability-inventory.md` §4 D2, D5;
`docs/architecture/OPUS_AUDIT_HANDOFF.md` §5 (finding 2), §8

## Context

The OpenAPI document published by this API says, in its own `description`
(`services/api/smartmatch_api/main.py:213-217`):

> "OpenAPI is the source of truth; the TypeScript client is generated from it
> and never hand-maintained."

`clients/` does not exist. `apps/web/legacy-frontend/src/lib/api.ts` is 4,238
hand-written lines, and the `/v1` calls are inline `fetch` across 49 files. 42
`/v1` endpoints are consumed with response types transcribed per page (R-02,
D2). `pyproject.toml:41` still carries
`extend-exclude = ["clients/typescript", …]` — ruff excluding a path that has
never existed, the fossil of the claim (D5).

This is the repository's worst documentation failure, and not because it is the
falsest. It is the only false claim that is **published to consumers**: D1 and D3
are stale docstrings a maintainer reads, while D2 ships inside the contract
artifact. A downstream integrator reading `smartmatch.json` is told a generated
client exists.

The gap it leaves is mechanical. A backend field rename passes every gate in
`.github/workflows/verify.yml` — the contract-freshness check regenerates the
OpenAPI document and it changes *consistently*, so the check is satisfied — and
reaches a user as a runtime `undefined` on a page whose transcribed type still
names the old field. The consumer side of the contract has no gate at all.

The repository has already decided it wants one. `verify.yml`'s deferred-gate
list, at the bottom of the file, names "generated TypeScript client drift check
(needs `clients/`)" under **before-live (R1+)**. The gate is designed and blocked
on the artifact it checks.

## Decision

**Generate a TypeScript client into `clients/typescript` from
`contracts/openapi/smartmatch.json`, commit the generated output, and add a CI
job that regenerates and diffs it.**

1. **Generation is from the committed contract**, not from a running server. The
   contract is already the CI-gated source of truth; introducing a second source
   would reintroduce the drift this closes.
2. **The generator is pinned by exact version** and recorded in the repository,
   on ADR-0004's reasoning about the schema: an artifact that is committed and
   compared is only meaningful if the thing producing it is fixed.
   `openapi-typescript` is the candidate — it emits types and no runtime — but
   the tool choice is an implementation detail of M3 rather than part of this
   decision. What is decided are the criteria it must meet:
   - **deterministic output** — the same contract produces the same bytes, so a
     diff means a contract change and never a tool mood;
   - **no runtime dependency shipped to the browser** — the client must not add
     a request library, an interceptor stack, or a validation runtime to the
     bundle;
   - **types first** — the initial output is type declarations for paths,
     operations and schemas. A generated fetch layer may follow; it is not
     required for the gate to be worth having.
3. **The output is committed.** A generated artifact that only exists in CI
   cannot be diffed against what the frontend actually compiled, and cannot be
   read by a developer or an agent trying to answer what a response looks like.
4. **The drift gate**: a `verify.yml` job regenerates the client from the
   committed contract and fails if the working tree differs. That is the gate
   already listed as deferred; landing `clients/` is what unblocks it. The
   corresponding deferred-list entry moves to the "implemented since this list
   was written" section in the same change, because a list that stays honest is
   the reason it exists.
5. **One page is migrated, as the pattern.** Not 49. The migrated page imports
   the generated types, `lib/api.ts` becomes an adapter over them rather than a
   parallel transcription, and the diff is the reference every later page copies.
6. **`main.py`'s `description` becomes true in the same change**, and the ruff
   `extend-exclude` entry stops being a fossil. If the client is not landing yet,
   the description is corrected first — a published false claim is not held
   hostage to a build task.

## Consequences

**Good.** The one loop where green CI can still ship a broken page closes: a
renamed field now fails `tsc` in the migrated page instead of surfacing as
`undefined` in a browser. The repository's most visible false statement becomes
a true one. And an agent asking "what does this endpoint return" gets an answer
from a file rather than by reading a router and a page and hoping they agree.

**Cost.** A committed generated artifact is a diff in every contract-changing PR,
which is noise until the moment it is the entire point. `clients/typescript`
must stay excluded from Python linting (it already is) and be excluded from
frontend lint and coverage, or generated code becomes review burden. And the
migration is genuinely long-tailed: 48 pages keep hand-written types after M3,
which means the guarantee is partial for as long as that lasts. Partial and
growing beats absent — but this ADR does not claim the loop is closed on the
day it lands.

**Enforcement.** The `verify.yml` drift job, plus `tsc` over the migrated page.
The gate fails on exactly two things: a contract change with no regeneration,
and a hand edit to generated output. Neither is currently detectable at all.

## Alternatives considered

**Keep hand-maintained types and rely on review.** Rejected: it is the status
quo, and the status quo produced 49 independent transcriptions of one contract
with no mechanism that notices when one falls behind. It also leaves D2 false or
requires deleting a claim the team evidently wants to be true.

**Runtime schema validation in the frontend (parse responses against a schema
derived from the contract).** Rejected as the primary mechanism: it moves the
failure from build time to the user's browser, which is later and worse, and it
adds a validation runtime to the bundle for a guarantee `tsc` gives for free.
Not ruled out as a defensive addition on a small number of critical responses;
ruled out as the answer to R-02.

**Fetch the OpenAPI document at runtime and derive types from it.** Rejected:
TypeScript types do not exist at runtime, so this buys nothing at the type layer,
and it makes the frontend's correctness depend on a network call to the service
it is trying to call correctly.

**Generate from the live application at build time rather than from the
committed contract.** Rejected: it creates a second source of truth and makes the
frontend build depend on a running API, which the `web` job in `verify.yml`
deliberately does not have.

**Migrate all 49 files at once.** Rejected by R-02's own remediation and by the
Stage 2 rule that every increment be independently shippable and reversible. A
49-file mechanical change is neither reviewable nor revertible in pieces, and it
would land before anyone has learned what the adapter shape should be.
