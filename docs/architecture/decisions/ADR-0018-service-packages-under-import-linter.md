# ADR-0018 — Service packages are governed by import-linter

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §1.1, §4.1; ADR-0002
**Backlog:** Stage 2 AP-01, AP-02; migration increment M2
**Findings:** `docs/architecture/risk-register.md` R-05, R-06;
`docs/architecture/dependency-analysis.md` §3, §3a–§3c;
`docs/architecture/OPUS_AUDIT_HANDOFF.md` §8 ("where the leverage is")

## Context

ADR-0002 made four packages uncrossable. `pyproject.toml`'s
`[tool.importlinter].root_packages` lists exactly `smartmatch_domain`,
`smartmatch_authz`, `smartmatch_providers`, `smartmatch_persistence`, and four
contracts govern them. The domain may not import `os`. That is real: the audit
looked for a domain module importing a framework, a driver or a provider SDK and
found **none** (`risk-register.md`, "What is explicitly NOT on this register").

`smartmatch_api` and `smartmatch_worker` appear in no contract. Together they are
28,080 lines — 40% of production Python (`dependency-analysis.md` §3). The
asymmetry is the finding: *the inner layers cannot drift precisely because they
are contracted, and the outer ones are protected only by convention.*

Convention has already failed twice, in the same way:

| Importer | Imports | From |
|---|---|---|
| `routers/cba_contact_channels.py:131` | `_authorize_speaker_contacts` and others | `routers/cba_contacts.py` |
| `routers/outreach_contacts.py:109` | `READ_RATE_LIMIT`, `_authorize_outreach` | `routers/outreach.py` |

Both are *deliberate and well argued* — `main.py`'s router table says one
question about a unit's outreach should have one answer, which is right. The
behaviour is correct and the mechanism is wrong: reaching across a sibling
module for an underscore-prefixed name means the router layer has no definable
public surface, and a rename in `outreach.py` breaks `outreach_contacts.py` with
nothing to catch it. `capability-inventory.md` §5 records that six routers
authorize *by delegation*, two of them by exactly this route — so the coupling is
load-bearing for a security property, not incidental.

Second, the manifests do not describe the real graph. `services/api` imports
`smartmatch_persistence` in 33 files and `services/worker` in 10;
`services/api/pyproject.toml:6-14` and `services/worker/pyproject.toml:6-13`
declare `smartmatch-domain`, `smartmatch-authz`, `smartmatch-providers` and not
persistence, while `services/api/smartmatch_api/main.py:47` opens with
`from smartmatch_persistence.engine import create_session_factory`. It works
because CI installs every package with `--no-deps -e` and pytest puts every
source root on `pythonpath`. It breaks at the first real wheel, slim container,
or `uv sync --frozen` (R-05).

Third, nothing prevents `smartmatch_api` from importing `smartmatch_worker` or
the reverse. Today neither does (`dependency-analysis.md` §3c). The boundary is
a habit.

None of this needs a new mechanism. import-linter is configured, running as a
required check, and has four working contracts to copy.

## Decision

**The two service packages are governed by import-linter on the same terms as
the four inner packages.**

1. `smartmatch-persistence` is added to `dependencies` in both
   `services/api/pyproject.toml` and `services/worker/pyproject.toml`. This is a
   prerequisite, not a nicety: a contract over a package whose manifest lies
   about its inputs governs a graph nobody can reproduce outside CI.
2. `smartmatch_api` and `smartmatch_worker` are added to
   `[tool.importlinter].root_packages`.
3. Two new contracts:
   - **Routers are independent.** No module under
     `smartmatch_api.routers` may import another module under
     `smartmatch_api.routers`. Expressed as an `independence` contract over the
     router modules.
   - **The services do not import each other.** `smartmatch_api` must not import
     `smartmatch_worker`, and `smartmatch_worker` must not import
     `smartmatch_api`. A `forbidden` contract in both directions, because the
     two run as separate deployables with separate callers and a shared import
     would make that a fiction.
4. The two existing violations are landed as explicit `ignore_imports` entries,
   each carrying the line it excuses, **and both are removed within migration
   increment M2** by promoting `_authorize_speaker_contacts` and
   `_authorize_outreach` / `READ_RATE_LIMIT` into an owned unit-authorization
   module on the pattern `services/api/smartmatch_api/job_authz.py` already
   sets — the module whose own docstring records that `jobs.py` and `redrive.py`
   each carried a different subset of one policy before it existed
   (`dependency-analysis.md` §4, "Exemplary").

The ordering is the point. Landing the contract with two ignores makes the rule
true for the other 24 routers immediately, and turns the two known exceptions
from invisible convention into two named lines with a scheduled end. Landing the
promotion first would be a refactor of authorization code with no contract
holding the result.

**What this does not decide.** It does not layer the services against each other
or against `python/` beyond what ADR-0002's existing layering contract already
says. It does not forbid a router importing a shared API module — `errors.py`,
`dependencies.py`, `units.py`, `job_authz.py` are exactly where shared decisions
belong, and their fan-in of 26, 26, 18 and 4 is cohesion.

## Consequences

**Good.** The largest ungoverned surface in the repository acquires the
enforcement the rest already has, using a mechanism that is running today. The
router layer gains a definable public surface: after M2, an authorization rule
shared between two routers has one home, and the answer to "who may change
`_authorize_outreach`" stops being "whoever finds it". Every later structural
change — the generated client (ADR-0020), the ownership map (ADR-0019), the
observability middleware — lands inside a boundary that either holds or fails a
required check.

**Cost.** The independence contract will refuse a future shared helper placed in
a router, and the correct response is to move the helper, which is more work in
the moment than importing it. That is the cost being bought deliberately. Adding
persistence to the manifests also makes the dependency real for anyone building
a slim image, which is the point but is not free. Two `ignore_imports` lines
exist between M2's first and last commit; a contract with an excuse in it is
weaker than one without, and the excuse must not outlive the increment.

**Enforcement.** `make check`'s `imports` step. Verifiable the way ADR-0002's is:
add an import of `smartmatch_api.routers.outreach` to another router and the
contract reports `BROKEN`. The manifest half is verified by
`uv sync --frozen` on a single service, or by the absence of persistence from a
built wheel's metadata — not by import-linter, which reads source rather than
manifests. Both halves are needed and neither substitutes for the other.

## Alternatives considered

**Convention plus code review.** Rejected on this repository's own evidence, not
on principle. This is what governs `services/*` today, and it produced two
violations that a reviewer approved *with reasons* — both times the reviewer was
right about the behaviour and had no place to put it. Review catches the
violation it is looking at; it cannot catch the one that has not been written.

**A single `services` layer contract instead of router independence.** Rejected:
a layers contract between `smartmatch_api` and `smartmatch_worker` says nothing
about the coupling that actually exists, which is lateral and *inside* one
package. The two failures observed are router→router, and a contract that does
not name them is decorative.

**Move the routers into the `python/` packages so ADR-0002's contracts cover
them.** Rejected: it inverts the layering. Routers are the framework boundary —
they import FastAPI, which contract 1 exists to keep out of the inner packages —
so the only way to make them fit is to widen the contract that makes the domain
testable in under a second. That trades the repository's strongest property for
a configuration convenience.

**Wait for the service split that would make this natural.** Rejected by
`OPUS_AUDIT_HANDOFF.md` §7: nothing in the repository exerts pressure toward a
microservice split, and the boundary is needed now, inside the monorepo
ADR-0001 chose.
