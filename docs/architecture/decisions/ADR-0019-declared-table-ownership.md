# ADR-0019 — Table ownership is declared as data before any schema split

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §2.4; ADR-0004; ADR-0013
**Backlog:** Stage 2 AP-03; migration increment M6
**Findings:** `docs/architecture/risk-register.md` R-20;
`docs/architecture/data-architecture.md` §8;
`docs/architecture/domain-model.md` §2, §6

## Context

`python/smartmatch_persistence/smartmatch_persistence/schema.py` is 2,691 lines
and holds all 44 tables (Stage 1 reported 43; recounted 2026-09-08). Twenty-six
repository modules import it. Every persistence change touches it, which in an agent-parallel workflow is a
permanent merge-conflict surface (R-20).

The line count is the visible symptom and the least interesting part. The
finding underneath is that **nothing in the repository states which context or
which service owns which table** (`data-architecture.md` §8). Ownership is
inferable from three converging signals — module clustering in
`smartmatch_domain`, table clustering in `schema.py`, and the `Capability` gate
table in `main.py` — and `domain-model.md` §2 derives six contexts from them:
Identity & Access, Work Substrate, Event Catalog, Matching, Speaker
Relationship, Engagement & Outreach. Inferred, not declared. An inference is not
something a test can hold anyone to.

Two consequences are already live.

**Match-run writes.** `data-architecture.md` §8 and `domain-model.md` §6 both
say `routers/match_runs.py` writes match-run rows directly *and* submits a
command, with `worker/handlers.py:handle_match_run_create` also writing — "two
writers, no declared owner". Verified against the tree, that statement is now
too strong, and the way it is too strong is the argument for this ADR.
`routers/match_runs.py:22-27` says in as many words that nothing there inserts a
`match_run` row and nothing there could, because the table's `job_id` is a
`NOT NULL` foreign key to `job`; the router's only use of the repository is a
read (`match_runs.py:1175`, `_match_runs.get`). The single writer of `match_run`
is `handle_match_run_create` (`handlers.py:1109`). So the ambiguity Stage 1
recorded is resolved by a *docstring* — one that happens to be correct, in a
repository whose docstrings are load-bearing and where three of them were found
false (`capability-inventory.md` §4 D1–D3, R-15). The map was right and
unassertable, which is precisely R-04's shape one layer down.

**Attendance.** `attendance_record` has one writer today and nothing prevents a
second. ADR-0013's invariant — attendance is the only input to points, and
registration never writes attendance — depends on that single writer. The
invariant is recorded; the property it rests on is not.

## Decision

**Table ownership is declared as data, in the persistence package, and checked
by a test. No structural change to `schema.py` happens before it.**

1. A new module `smartmatch_persistence/ownership.py` holds a mapping from table
   name to three things: one **owning bounded context**; one **owning repository
   module** in `smartmatch_persistence` — the single module that issues SQL
   against that table; and the **set of writing services**. The six contexts are
   `domain-model.md` §2's, named as constants rather than free strings. The
   writer side names `api`, `worker`, or `migration` — the last for tables only
   seeded or maintained by an Alembic revision. The repository-module half is the
   layer Stage 1 did not have a name for, and it is the half that is already true
   without exception: no file under `services/` issues `insert()`, `update()` or
   `delete()` against a `schema.<table>` object at all (OBSERVED, AST scan of
   `services/`, 2026-09-08), so every table has exactly one module issuing its
   statements — `job` and `job_event` → `jobs.py`, `outbox_record` → `outbox.py`,
   `idempotency_record` → `idempotency.py`, `spend_reservation` → `spend.py`,
   `match_run` → `match_runs.py`.
2. A unit test asserts the map and `schema.py` agree **both ways**: every
   `sa.Table` declared in `schema.py` appears exactly once in the map, and every
   entry in the map names a real table. Both directions, for the reason
   `tests/unit/test_adr_index.py` gives about its own index: a map that is only
   checked one way goes stale on the first table nobody adds to it, and a stale
   map is read as complete.
3. **Multi-writer is allowed only by explicit declaration with a reason.** The
   writing-service set is derived one level up from the repository: which service
   package calls that repository's *mutating* methods. Measured that way, five
   tables have two writing services today, and all five are two-writer by
   ADR-0005's design rather than by accident — the Work Substrate tables `job`,
   `job_event`, `outbox_record` and `idempotency_record`, plus
   `spend_reservation`. `JobRepository.create/transition/append_event/claim` is
   called from the API (`commands.py`, `pipeline_provisioning.py`,
   `routers/cba_contacts.py`) and from the worker (`execution.py`,
   `dispatcher.py`); `OutboxRepository.enqueue/claim_batch/mark_dispatched` from
   the API (`commands.py`, `routers/cba_invitations.py`) and the worker
   (`dispatcher.py`); the idempotency and spend repositories likewise
   (`routers/redrive.py` and `worker/paid_extraction.py` among them). Each of the
   five declares both services together with the reason string "API records
   intent / worker transitions state (ADR-0005, ADR-0015 A1)". Every other table
   declares exactly one service, and `match_run` is the worked example: written
   only by the worker. The test therefore does not assert "one writer" — it
   asserts that any entry naming more than one service carries a reason, so a new
   second writer on a single-writer table fails the lane until someone declares
   it and says why. Service granularity is too coarse for one invariant that
   matters: ADR-0013 says registration never writes `attendance_record`, and both
   the attendance route and the registration route live in the API. So the
   writer half is derived and declared at **module** granularity — the calling
   module, `smartmatch_api.routers.attendance`, not merely the service — and the
   service set is the projection of it. ADR-0013's invariant then becomes an
   assertion the test can make, rather than an assumption: `attendance_record`'s
   declared writer modules do not include `smartmatch_api.routers.student_events`.
4. **Match-run ownership is resolved here explicitly, and recorded as the
   pattern.** The API writes the *request* — but the `job` row and the outbox
   record it writes through `submit_command` are exactly the tables the worker
   also writes, which is why they are declared two-service. The worker alone
   writes the *result*, the `match_run` snapshot. So the command path is not "two
   tables, two owners" but "two shared substrate tables with a declared reason,
   and one single-writer result table". This is the shape every future async
   capability should take, and stating it turns a docstring that could rot into
   a fact a test holds.
5. **The `schema.py` split is not decided by this ADR.** If it happens, it is
   permitted only along declared ownership lines, and only after this map exists
   and is green. `OPUS_AUDIT_HANDOFF.md` §7 rules out splitting on line count;
   this ADR is what makes the alternative available rather than requiring it.

## Consequences

**Good.** "Who writes this table" acquires an answer that is checked rather than
inferred, which is the prerequisite `data-architecture.md` §8 and
`domain-model.md` §6 both name. ADR-0013's single-writer premise becomes visible:
a second writer of `attendance_record` now requires editing a file that says what
it is doing, in a diff a reviewer will notice, instead of appearing as an
ordinary insert in an unrelated router. The map also gives every later
conversation about persistence a shared vocabulary — a bug report can say "an
Engagement table written by the API" and be understood without opening 2,691
lines.

**Seeding and re-verification.** The map is not typed out by hand.
`tools/derive_table_writers.py` (owner decision, 8 September 2026) makes **two**
syntactic passes, because the two halves of an entry live at two different
layers. Pass 1 walks the AST of `python/smartmatch_persistence`: for each
`schema.<table>` it records which module issues `insert()`, `update()` or
`delete()` against it — the owning repository module — and collects the names of
that module's mutating methods (any method whose body contains such a
statement). Pass 2 walks `services/api` and `services/worker` for call sites of
those method names, by attribute name, and records the **calling module** of
each; the service is the module's package. The tool prints table → repository
module → {calling modules} → {services}. Its output
**seeds** `ownership.py` in the change that introduces the map, and the ownership
test **re-runs the tool** and diffs it against the declaration, failing when the
owning module or the writing-service set disagrees. Matching pass 2 on the
attribute name over-approximates — an unrelated `.create` would be counted — and
that is the intended direction: an over-approximation surfaces as a discrepancy
somebody has to explain, never as a silent pass. Pass 1 has the same property
against aliasing. So both halves of every entry are a measurement checked against
a declaration, and a second writer appearing in a later PR fails the lane at the
point it is introduced.

**Cost.** A new table costs one map entry, and forgetting it fails the lane.
That is a deliberate speed bump on exactly the change that should be deliberate.
The map is also prose-adjacent in one respect the test cannot reach: nothing
verifies that the *context* named is the right context, only that it is one of
the six and that the table exists. That is the same silent failure mode the ADR
index's "Decides" column has, and it is recorded here for the same reason.

**Enforcement.** A unit test in the no-database lane that re-runs
`tools/derive_table_writers.py` and compares both halves of its output against
the declared map — owning repository module and the writer set, at module
granularity, projected to services — and fails any entry with more than one
service that carries no reason string. It sits
alongside `tests/integration/test_schema_matches_migration.py`, which already
establishes that `schema.py` is compared against something rather than trusted.
What the test still cannot reach is *which* service ought to be allowed to call a
given repository: it records that the API calls `JobRepository.create`, not that
it may. Making that assertable is possible under ADR-0018's contracts once both
services are root packages, and is named here as the follow-on rather than
claimed as done.

## Alternatives considered

**Split `schema.py` by line count now and declare ownership afterwards.**
Rejected. `OPUS_AUDIT_HANDOFF.md` §7 names this as an anti-goal, and the reason
is concrete: a split made on size produces module boundaries that mean nothing,
and the second split — the one along ownership — then has to move the same 44
tables again, through a file every one of 26 repositories imports. One
disruption, not two, and only when it buys something.

**Model ownership as ORM structure — one declarative base or one module per
context, with membership implied by location.** Rejected: it puts the assertion
in the file layout, so the only way to record ownership is to perform the split,
which is the ordering this ADR exists to refuse. It also pushes against ADR-0004,
which chose a hand-written schema reconciled by a drift test precisely so that
the composite `(tenant_id, id)` keys are visible and comparable rather than
generated.

**Comments in `schema.py` naming the owner beside each table.** Rejected: not
assertable, and the repository has already been bitten by unassertable prose
three times (D1, D2, D3). A comment is exactly what the match-run situation had.

**A per-table `owner` column or database-level role separation.** Rejected as
disproportionate: this is a design fact about the codebase, not a runtime
authorization boundary, and PostgreSQL role separation would have to be
maintained in migrations under ADR-0009's one-transaction rule for no gain the
pilot can observe.
