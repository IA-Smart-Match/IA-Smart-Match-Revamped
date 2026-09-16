# ADR-0023 — Every submittable command type is registered or explicitly refused

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §1.6, §1.11; ADR-0005
**Backlog:** Stage 2 AP-05, AP-11; migration increment M1
**Findings:** `docs/architecture/risk-register.md` R-04;
`docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md` §19 U1;
`docs/architecture/wip-analysis.md` §2

## Context

R-04 calls this "the hardest question in the codebase for a future agent to
answer": given a command a router can submit, what executes it? Stage 1 could not
answer it and recorded U1 as an unknown, on the arithmetic that
`default_registry()` registers three handlers while eight routers reference
`submit_command`.

Resolved in tree, 2026-09-08. The eight was a grep over docstring mentions.

| Command type | Submitting router | Executor | Registered where |
|---|---|---|---|
| `import.create` | `routers/imports.py:293` | `handle_import_create` | `handlers.py:1360`, inside `default_registry()` |
| `match-run.create` (`domain/match_run.py:75`) | `routers/match_runs.py:947` | `handle_match_run_create` (`handlers.py:1109`) | `handlers.py:1367` |
| `outreach.send` (`domain/outreach.py:126`) | `routers/outreach.py`, `routers/cba_invitations.py:1112` | `build_outreach_send_handler` | **composed at the root**, `worker/main.py:468-489`, unconditionally when `registry_is_ours` |
| `test.noop` | none over HTTP | `handle_noop` | `handlers.py:1359` |
| `extraction.paid_pages` (`worker/paid_extraction.py:123`) | none over HTTP | `build_paid_extraction_handler` | composed at the root, `worker/main.py:491`, only when spend ceilings are configured |

Three further names reserve an idempotency key and never create a job or an
outbox row, so no handler is expected: `speaker_contact.create`
(`routers/cba_contacts.py:302,1097` — reserve only) and `job.redrive` /
`job.abandon` (`routers/redrive.py` — `_reserve` only). Two routers mention
`submit_command` in prose and deliberately do not use it, being synchronous by
design: `routers/review.py:40` and `routers/speaker_requests.py:25`.

So: four routers submit, three command types reach the worker over HTTP, and
every one has an executor. **The map is complete today.**

R-04 survives in a sharper form, and the sharper form is the reason for this ADR:

1. **Nothing asserts it.** The map above was assembled by hand from five files
   and is true as of one commit. A new async capability can be submitted
   successfully and terminally refused, with no build-time signal — the refusal
   path is fail-closed and correct (`handlers.py:11`), which is exactly what
   makes the gap quiet.
2. **Two of the five handlers are invisible to a reader of `default_registry()`.**
   `outreach.send` and `extraction.paid_pages` are composed in
   `worker/main.py`, and a reader who takes `default_registry()`'s docstring at
   its word — "deliberately short… a handler added ahead of its gate is a handler
   someone will trigger" — concludes that `outreach.send` has no executor. That
   conclusion is wrong, and Stage 1's own audit shows how easy it is to reach:
   `wip-analysis.md` §2 records `test_20_the_worker_sends_through_the_fixture_provider`
   passing as *countervailing evidence* against the registry reading.

The root composition is legitimate and should not be undone. `worker/main.py`'s
comments argue it: these handlers take collaborators — a provider, a From
address, an HMAC key, a session factory — and a registry function that takes no
arguments cannot supply them; `handlers` importing `smartmatch_worker.outreach`
to reach the command type would make a cycle out of a dependency that is
genuinely one-way. The conditionality is argued too: a worker with no spend
ceilings must not be able to spend money, so absence withholds the paid handler,
while a worker with no email credential is in fixture mode — the mode the pilot
runs in — so absence configures the send handler rather than withholding it.

The problem is not the composition. It is that the composition is invisible.

## Decision

**A test enumerates every command type any router can submit and asserts each is
either present in the composed production registry or on an explicit refusal
list. The test is the map.**

1. **The submittable set is derived, not typed twice.** The test collects every
   command type reaching `smartmatch_api.commands.submit_command` from the router
   package — by AST walk over `services/api/smartmatch_api/routers`, or from an
   explicit constant list that a second assertion proves exhaustive against the
   same walk. What is not acceptable is a hand-written list nothing compares
   against the routers, because that is the artifact whose staleness R-04 is
   about.
2. **The registry the test checks is the composed one.** `default_registry()`
   alone is the wrong target: it would report `outreach.send` as unregistered and
   the test would be false. The test builds the registry the way `create_app`
   does — `default_registry()`, then `with_outreach_send`, then
   `with_paid_extraction` under configured ceilings — or the composition is
   factored into a named function that both `create_app` and the test call. The
   second is preferable and is the smaller change: it makes "the registry this
   worker runs with" a thing with a name.
3. **The composition is checked under both configurations.** With spend ceilings
   and without, because `extraction.paid_pages` is present in one and absent in
   the other **by decision**, and a test that only sees one of them asserts half
   the rule.
4. **`INTENTIONALLY_REFUSED` is an explicit set**, with a reason per entry, for a
   command type a router can submit and the worker deliberately will not execute.
   It is empty today. It exists so that adding a submission ahead of its gate is
   a deliberate, reviewed entry rather than a silent terminal refusal.
5. **Idempotency-scope names are listed as such and excluded by name.**
   `speaker_contact.create`, `job.redrive` and `job.abandon` reserve a key and
   create no job. They are not commands, they are not refused commands, and a
   test that treats them as either will fail for the wrong reason and be
   "fixed" by weakening it. Listing them with their reserve-only call sites is
   what stops that.
6. **This does not change capability gating by absence.** A gated-off capability
   still owns no router and no registered handler
   (`main.py:CAPABILITY_SCOPED_ROUTERS`; AP-11). A capability with no router
   submits nothing, so it contributes nothing to the submittable set and needs no
   refusal entry — which is the property that makes the test's set small and
   meaningful.

## Consequences

**Good.** The question R-04 calls the hardest in the codebase gets an answer that
is generated rather than remembered, and the answer is in a file a future agent
will find by grepping the command type. Root-composed handlers become visible
without moving them: the test names them, so `default_registry()` stops being
mistaken for the whole registry. A new async capability now fails a lane at the
moment its submission lands without a handler, instead of returning `202` to a
caller and terminally refusing in a worker nobody is watching.

**Cost.** The test needs the composed registry, which means either duplicating
`create_app`'s composition — a second place to keep in step, the failure mode
this ADR is about — or refactoring the composition into a shared function. The
refactor is the right answer and it is a change to worker startup, which is a
sensitive area. An AST walk is also a static approximation: a command type
computed at runtime rather than named as a constant would be invisible to it. All
five present types are module-level `Final[str]` constants, so the approximation
holds today; if it stops holding, the test should fail loudly on an unresolvable
argument rather than skipping it silently.

**Enforcement.** A unit test in the no-database lane. Migration increment M1,
ahead of the boundary work, because it is a one-file change and a prerequisite
for everything asynchronous that follows — the same argument `OPUS_AUDIT_HANDOFF.md`
§10 makes for resolving U1 before designing anything async.

## Alternatives considered

**Register everything in `default_registry()` so the registry is the map.**
Rejected on three grounds the code already argues. The handlers take
collaborators a zero-argument factory cannot supply; `handlers` importing
`smartmatch_worker.outreach` would create an import cycle out of a genuinely
one-way dependency; and `default_registry()`'s stated rule — a handler appears
only once something can genuinely execute or genuinely refuse it, because a
handler added ahead of its gate is one someone will trigger — is a good rule that
this change would break. The problem is visibility, and the fix for visibility is
a test, not a relocation.

**Document the map in `docs/architecture/command-path.md` and keep it current.**
Rejected: the map above *is* that document, and it was accurate for exactly as
long as it took to write. This repository has three false docstrings on record
(D1–D3, R-15) in an area where documentation is load-bearing. An unasserted map
is the artifact R-04 is complaining about.

**Assert only that the submittable set is non-empty and every registered handler
is reachable.** Rejected: it checks the safe direction. The dangerous direction
is a submission with no handler, which is what returns `202` and then refuses.

**Make an unregistered command type a startup failure instead of a test.**
Rejected: the worker cannot know what the API can submit — they are separate
deployables, and ADR-0018 forbids the import that would let it. The check belongs
where both trees are visible, which is CI.
