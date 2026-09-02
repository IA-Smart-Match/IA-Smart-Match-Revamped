# Critical path plans

Master index of every outstanding **critical path** reconstructed from the
repository's own documentation. There is no file named "Architecture Overhaul
Report"; the findings live in the plans, ADRs, reviews, and migration records
cited below.

**This document plans. It changes no code.**

**Current-status correction (2026-09-02):** The tree table and entries below
preserve their 26-August historical snapshot. This checkout now closes J8/J9
(code plus recorded focused evidence), A4, A5, J4, and J17. External Cloud
Scheduler/OIDC deployment, Terraform/F5, live identity, and remaining product
and review gates remain open.

**How to read status.** Two trees are in play, and several backlog files have
not caught up with either:

| Tree | Tip (as of 26 August 2026) | What is true there |
|---|---|---|
| `main` (this checkout) | `c4ae716` (local; `origin/main` is four CI-only commits ahead) | Command path is durable but **unexecutable**: `import.create` always fails (`command_not_executable`). J8, J9, J10, J15, J16, J17, A4, F9, F13 (three of four files), F2b, F5 are **open**. |
| `claude/pr1-blockers-todos-er5heu` | `a48408a`, 13 commits ahead of `main`, pushed | Those items are **closed in code**. Remaining engineering: job-read grant hole, A5, F9 re-review, revert-checks. `docs/plans/remaining-foundation-r1-work.md` was **not** updated on this branch and still lists J8–J10, J15–J17, A4 as open. |

Treat the PR1 branch as the candidate "current engineering state" and `main` as
the merge baseline. Do not re-implement J10 (or its siblings) on `main`.

**Two numbering collisions, kept apart throughout.** Backlog items from
`remaining-foundation-r1-work.md` are unhyphenated (**F7**, **F9**, **A5**).
Port-verification findings are hyphenated (**F-7**, **F-9**, **F-15**).
Stakeholder-audit **Q1** (PII remediation owner) is not kickoff **Q1** (which
factors does matching use).

---

## Suggested priority order

Work top to bottom. Items in the same band can overlap only when their file
sets are disjoint and no named human is the bottleneck.

| # | ID | Path | Why here |
|---|---|---|---|
| 1 | **CP-PR1** | Merge and evidence-check the PR1 blockers branch | Everything below is written against the post-PR1 tree. Re-doing J10 on `main` wastes the branch. Four commits have no revert-check evidence. |
| 2 | **CP-GRANT** | Job reads ignore `resource_grant` deny | Historical priority; closed with the shared job authorizer in the current tree. |
| 3 | **CP-A5** | `job.owning_unit_id` (S-006) | Historical priority; migration `0006` and unit-scoped authorization are closed in the current tree. |
| 4 | **CP-PII** | Assign an owner and decide MM-A09 remediation | Only severity-1 stakeholder finding. Unassigned. Gates D9 / `LICENSE` / kickoff Q11. Not engineering. |
| 5 | **CP-G1** | Start D1 / gate G1 (factor registry) | Longest pole. All matching (M1–M10) waits. Matching is the product. |
| 6 | **CP-V11** | Place Architecture v1.1 in the repository, or demote `contract_refs` | F-28. Without this, no port entry can reach a clean `verified`. Must precede the F9 re-review or the re-review returns F-28 again. |
| 7 | **CP-REREVIEW** | Independent re-review of MM-003, MM-004, MM-005 | Foundation gate. Corrections and code fixes are on the PR1 branch; §6 of the orchestrator contract forbids self-approval. |
| 8 | **CP-A1B** | Live identity verifiers (API JWKS + worker signature backend) | S-001 residual. Worker still refuses every task delivery. Needs a lock-file change; coordinate with any lock-touching PR. |
| 9 | **CP-DOCSYNC** | Bring `remaining-foundation-r1-work.md` and `orchestrator-run.md` in line with the tree | The backlog still recommends J10 as next; the orchestrator run still lists MM-001 as `ported_unverified`. Agents will re-implement closed work. |
| 10 | **CP-D0** | Assign a `DESIGN.md` owner | Entire W-series frontend, plus S2 render half. Deliberate hold, not a coding backlog. |
| 11 | **CP-MATCH** | Matching implementation M1–M10 | Blocked on CP-G1. Not startable by engineering alone. |
| 12 | **CP-STAKE** | Stakeholder S-series + test-log reconciliation | R2/R3. Not ordered ahead of the command path. The audit's PARTIAL/MOOT rows cannot be filled without the log. |
| 13 | **CP-TAIL** | Contract-phase and deferred tails | F12, F-25, leftover docstring copies, J14 NULL-generation fallback, classroom-reset, crawler threat model, agent-memory Slice 1. |

Focused plans:

- [critical-path-pr1-merge.md](critical-path-pr1-merge.md) — CP-PR1
- [critical-path-authorization.md](critical-path-authorization.md) — CP-GRANT, CP-A5
- [critical-path-port-rereview.md](critical-path-port-rereview.md) — CP-REREVIEW, CP-V11, leftover F9
- [critical-path-matching-gate.md](critical-path-matching-gate.md) — CP-G1, CP-MATCH
- [critical-path-legacy-pii.md](critical-path-legacy-pii.md) — CP-PII, D9, F13 `LICENSE`

---

## Dependency graph

```
CP-PR1 ──► CP-GRANT ──► CP-A5 ──► A4 matrix cells rewritten
   │
   ├──► CP-DOCSYNC (can start as soon as merge lands)
   ├──► CP-REREVIEW ◄── CP-V11 (program owner; else ceiling is "verified except contract_refs")
   │         └── leftover docstring copies in eli.py / ingest.py / feedback.py
   │
   └──► CP-A1B (lock-file coordination)

CP-PII (named human) ──► D9 ──► F13 LICENSE
CP-G1  (named human) ──► CP-MATCH (M1–M10) ──► W5 control center
CP-D0  (named human) ──► W1–W7, S2 render
D8     (privacy/legal) ──► S10
D6+D7  (program owner) ──► S9 catalog
D3     (procurement)   ──► M4 travel_burden
```

Nothing in CP-GRANT / CP-A5 / CP-PII / CP-G1 blocks another except GRANT before
A5 (so the matrix is not rewritten twice) and V11 before a *clean* re-review.

---

## 1. CP-PR1 — Merge and evidence-check the PR1 blockers branch

**Own plan:** [critical-path-pr1-merge.md](critical-path-pr1-merge.md)

**(a) What / where.** Branch `claude/pr1-blockers-todos-er5heu` closed the
items `remaining-foundation-r1-work.md` still names as next: J10, J8, J9, J15,
J16, J17, A4, F9 (code + docs), F13 (except `LICENSE`), F2b, F5. Recorded in
`docs/plans/pr1-blockers-handoff.md` (exists **only** on that branch).

**(b) Status.** Pushed, not merged to `main`. Four commits (`J9+J8`, `J16`,
`F9 docs`, `F2b+F5`) have green gates but **no per-test revert-check evidence**
— agents were killed at the last verification step. `terraform validate` was
never run.

**(c) Plan.** Merge after the revert-checks in the focused doc; do not land
and then re-derive J10.

**(d) Depends on.** Nothing. **Unblocks** treating the rest of this file as
current.

**(e) Accept.** `main` contains migrations `0005`, ADR-0015, A4 matrix, F9
corrections; revert-checks recorded; `remaining-foundation-r1-work.md` rows
struck through.

**(f) Priority.** First.

---

## 2. CP-GRANT — Job reads ignore resource-grant deny

**Own plan:** [critical-path-authorization.md](critical-path-authorization.md) §1

**(a) What / where.** `_authorize_job_read` consults no `resource_grant`. An
admin holding an explicit DENY on a job is refused by `/redrive` and `/abandon`
and **permitted** by `GET /v1/jobs/{id}` and its event stream. Found by A4;
pinned in two matrix cells. `docs/plans/pr1-blockers-handoff.md` §3.1;
`docs/security/scaffold-security-review.md` S-006 (adjacent).

**(b) Status (historical snapshot).** Open in the source tree this plan was
written against; closed in the current checkout by the shared job authorizer.

**(c) Plan.** See focused doc. Small: apply the same grant evaluation the
re-drive path already uses, then update the two matrix cells that pin the hole.

**(d) Depends on.** CP-PR1 (A4 matrix). **Do before CP-A5.**

**(e) Accept.** Explicit DENY on a job refuses GET status and SSE. Matrix cells
that currently document the hole fail, then are rewritten to the new equality.

**(f) Priority.** First engineering item after merge.

---

## 3. CP-A5 — `job.owning_unit_id` (S-006)

**Own plan:** [critical-path-authorization.md](critical-path-authorization.md) §2

**(a) What / where.** `job` has no owning org unit, so job reads, re-drive, and
abandon cannot call `assert_allowed` with an `owning_unit_path`. A coordinator
in one department can act on another department's job.
`docs/plans/defect-remediation.md` §8; `docs/plans/remaining-foundation-r1-work.md`
A5; `docs/architecture/command-path.md` §3; `docs/security/scaffold-security-review.md`
S-006.

**(b) Status (historical snapshot).** Open on both trees at the time of writing;
closed in the current checkout by migration `0006` and shared authorization.
On PR1, `job.payload` exists so
`payload.unit_id` can backfill `import.create` jobs. Columns for J9/J17 already
landed in `0004`; A5 is `0006`.

**(c) Plan.** Expand (nullable composite FK, `RESTRICT`) → populate at
`submit_command` → backfill from payload → enforce with labelled `unscoped_job`
fallback → contract-phase `NOT NULL` later. Restore the unit-scoped job-read
test that was removed because the control did not exist
(`orchestrator-handoff.md` trap list).

**(d) Depends on.** CP-PR1 (J10 payload; A4 matrix). F7 (done). Sequence with
any other `0006`. **Blocks** a truthful A4 matrix for `job.*`.

**(e) Accept.** Same principal, two units: allowed on own unit's job, denied on
the other. `unscoped_job` reason code on NULL rows. Drift test covers the new
composite FK. SSE mid-stream expiry decided in writing (in or out of scope).

**(f) Priority.** Immediately after CP-GRANT.

---

## 4. CP-PII — MM-A09 legacy identity exposure

**Own plan:** [critical-path-legacy-pii.md](critical-path-legacy-pii.md)

**(a) What / where.** Six tracked paths in the **legacy** repository at
`bdce024` carry named real people, including a communications log. Target
disposition is already `archived`; git history in the legacy repo is the
finding. Stakeholder Fix #1, severity 1, **unassigned**.
`docs/migration/migration-manifest.yaml` MM-A09;
`docs/plans/stakeholder-audit-integration.md` §9 Q1;
`docs/architecture/review/stakeholder-test-log-audit.md`.

**(b) Status.** Documented, not remediated. No write to the legacy repo is
authorized. Gates D9, F13 `LICENSE`, kickoff Q11 (open-sourcing).

**(c) Plan.** Name an owner. Choose history rewrite vs repository replacement.
Do not treat deleting HEAD files as closure.

**(d) Depends on.** A person, not a checkout. **Blocks** D9 / LICENSE /
open-source decision.

**(e) Accept.** Named owner on MM-A09 `blocking_owner`; written remediation
decision; D9 unblocked or explicitly still blocked with a date.

**(f) Priority.** Parallel with engineering; first human-assignment on the list.

---

## 5. CP-G1 — Factor-registry approval (D1)

**Own plan:** [critical-path-matching-gate.md](critical-path-matching-gate.md)

**(a) What / where.** Legacy registry declares 9 factors and computes 7; max
score 0.90. Gate G1. `docs/architecture/review/contract-findings.md` F-001;
`docs/plans/remaining-foundation-r1-work.md` D1, M1–M10; MM-002
`blocked_contract`; stakeholder Q6 (dropped factors).

**(b) Status.** Registry committed as `proposed`; `assert_registry_approved()`
fails closed. No scoring path. Three stakeholder symptoms are required golden
cases (43% tie, Topic Relevance 0%, Match Depth 0). `historical_conversion` and
`student_interest` have no target and no decision.

**(c) Plan.** Program owner approves contents + golden set; engineering flips
`REGISTRY_STATUS` in a reviewed commit (M1); then M2–M10.

**(d) Depends on.** Program owner. **Blocks** all matching, W5, F-25 consumer.

**(e) Accept.** `REGISTRY_STATUS = approved`; golden cases in CI; MM-002 leaves
`blocked_contract`; `test_registry_is_not_yet_approved` inverted deliberately.

**(f) Priority.** Start the conversation now; delivery follows CP-PR1.

---

## 6. CP-V11 — Architecture v1.1 not in the repository (F-28)

**Own plan:** [critical-path-port-rereview.md](critical-path-port-rereview.md) §2

**(a) What / where.** Every manifest `contract_refs` cites v1.1 by section.
The text is not vendored. `docs/migration/port-verification.md` "What could not
be verified" item 1; `defect-remediation.md` §5; `stakeholder-audit-integration.md`
§1.1.

**(b) Status.** Open. Program-owner decision. PR1 manifest adds
`contract_refs_status: UNVERIFIABLE` per entry — honest, not closed.

**(c) Plan.** Pin a hash-referenced copy in-repo (recommended), or redefine
`contract_refs` as author-asserted and stop reading it as evidence.

**(d) Depends on.** Program owner. **Blocks** a clean `verified` on any port.

**(e) Accept.** Either `docs/architecture/` contains the pinned contract and a
test that `contract_refs` sections exist, or the field's semantics are rewritten
in the manifest schema and the review checklist.

**(f) Priority.** Before requesting CP-REREVIEW, not during it.

---

## 7. CP-REREVIEW — Independent re-review of MM-003 / MM-004 / MM-005

**Own plan:** [critical-path-port-rereview.md](critical-path-port-rereview.md)

**(a) What / where.** F3 ran; three of four ports were rejected for false
manifest claims, not bad code. F9 is the remedy. Code + most doc corrections
are on the PR1 branch. Status remains `ported_unverified` by design.
`docs/migration/port-verification.md`; `docs/plans/defect-remediation.md`;
orchestrator contract §6.

**(b) Status.** Fixes landed on PR1; re-review not started. Docstring copies
in `eli.py:10`, `ingest.py` (F-12), `feedback.py` (F-18/19/21/22) still OPEN on
that branch. F-25 open by design. F-13 route (a) not taken. F-21 must be
re-derived from `bdce024`, which was **absent** from the PR1 checkout when
corrections were written. F-30 (review's own frozen-dataclass error) recorded;
`defect-remediation.md` §4.6 table still OPEN.

**(c) Plan.** Separate corrector from re-reviewer. Re-derive legacy claims from
`bdce024` before reading the corrected YAML. Require a "what could not be
verified" section. Ceiling is F-28 unless CP-V11 lands first.

**(d) Depends on.** CP-PR1, preferably CP-V11, access to legacy at `bdce024`.
**Unblocks** the Foundation ports gate.

**(e) Accept.** An independent reviewer sets MM-003/004/005 to `verified`
(or `verified except contract_refs`) with a named `reviewer` distinct from the
corrector; leftover docstring copies closed or explicitly deferred.

**(f) Priority.** After merge and V11 decision.

---

## 8. CP-A1B — Live identity verification (S-001 residual)

**(a) What / where.** API token verifier is a fixture. Worker OIDC verifier is
real but ships with no signature backend (`requirements/runtime.txt` has no
asymmetric-crypto library), so every task delivery is refused.
`docs/security/scaffold-security-review.md` S-001;
`remaining-foundation-r1-work.md` A1b, J6;
`docs/plans/pr1-blockers-handoff.md` §3.1 (ruled out of scope for that branch
because PR #2 was already touching locks).

**(b) Status.** Fail-closed, not live. Blocked on a hash-pinned lock change.

**(c) Execution plan.**

1. Coordinate with any open lock-file PR (origin `claude/fix-lock-drift-and-gitleaks-gate` / PR #2).
2. Add a vetted RS256 library to `requirements/runtime.in`; `make lock`.
3. Wire `SignatureVerifier` in `services/worker/smartmatch_worker/identity.py`.
4. Configure `SMARTMATCH_TASK_AUDIENCE` and `SMARTMATCH_TASK_SERVICE_ACCOUNTS` only in deploy config, never in-repo.
5. Implement A1b JWKS verifier for user requests (`services/api` auth adapter).
6. Keep the fixture path for tests; assert the live backend cannot be confused with it.

**(d) Depends on.** Lock-file ownership. Not blocked on CP-A5. **Blocks** any
real Cloud Tasks delivery.

**(e) Accept.** Worker accepts a signed test token and rejects `alg: none`,
wrong audience, and tampered payload with the real backend. API rejects an
unsigned / wrong-audience user token. Classroom edition still cannot construct
a live client.

**(f) Priority.** Before first worker deploy; after CP-PR1.

---

## 9. CP-DOCSYNC — Backlog documents that describe a tree that no longer exists

**(a) What / where.** `docs/plans/remaining-foundation-r1-work.md` "Suggested
next three" still names J10, J8, D1. `docs/migration/orchestrator-run.md` still
lists MM-001 as `ported_unverified` and Selective ports as `READY_FOR_REVIEW`.
`docs/testing/scaffold-verification.md` is dated 17 August (207 tests).
`docs/plans/orchestrator-handoff.md` "Not started" still lists F8, F9, A5, F10,
F11, F12 — F8, F10, F11 are done on `main`.

**(b) Status.** Stale on `main`; PR1 added a handoff file but did not strike
the backlog rows.

**(c) Execution plan.** After CP-PR1 merge, one docs commit:

1. Strike J8, J9, J10, J15, J16, J17, A4, F2b, F5, F9-code, F13 (partial) in
   `remaining-foundation-r1-work.md`; replace "Suggested next three" with
   CP-GRANT, CP-A5, D1 (matching the PR1 handoff §5).
2. Update `orchestrator-run.md` port table and gate status from the manifest.
3. Add a dated note to `scaffold-verification.md` that it is a Foundation-run
   record, not current CI.
4. Amend `orchestrator-handoff.md` "Not started" to A5, F9 re-review, F12.

**(d) Depends on.** CP-PR1 merge (otherwise the strikes are lies). **Unblocks**
correct agent routing.

**(e) Accept.** Grep for "always fails as `failed_policy`" and "nothing calls
them on a timer" returns only historical quotes, not current backlog rows.

**(f) Priority.** Same wave as the merge, not a follow-up weeks later.

---

## 10. CP-D0 — Frontend design owner

**(a) What / where.** `apps/web/DESIGN.md` is a brief with owner unassigned.
`remaining-foundation-r1-work.md` "R1 — Frontend — ON HOLD"; W1–W7; S2.

**(b) Status.** Deliberate hold. Settled constraints exist (provenance, truthful
failure, WCAG 2.2 AA, event-local time, unknown ≠ zero). Eight open decisions
in Part 2.

**(c) Plan.** Assign owner; settle D-1…D-8; then W1 scaffold → W2 generated
client from `contracts/openapi/smartmatch.json` → W4 provenance primitives
before any screen.

**(d) Depends on.** A person. W5 also needs M8 / G1. **Blocks** all `apps/web`.

**(e) Accept.** `DESIGN.md` has a named owner; Part 2 decisions recorded;
W1 may start.

**(f) Priority.** Assign whenever someone is free; do not start W3/W5 early.

---

## 11. CP-MATCH — Matching implementation (M1–M10)

**Own plan:** [critical-path-matching-gate.md](critical-path-matching-gate.md) §2

Blocked on CP-G1. Factors unimplemented; CP-SAT not started; `match_run`
persistence not started. OpenAPI has no matching routes (only health, jobs,
imports). Interim `travel_burden` may use labelled straight-line estimates
(M4) once D3 is answered; never fabricate mileage.

---

## 12. CP-STAKE — Stakeholder product contracts (S1–S12) and audit holes

**(a) What / where.** `docs/architecture/review/stakeholder-test-log-audit.md`;
`docs/architecture/engagement-model.md`; ADR-0010…0014;
`remaining-foundation-r1-work.md` S1–S12; `stakeholder-audit-integration.md` §6.

**(b) Status.** ADRs and backlog rows exist. No tables, no metric register, no
funnel query. **Reconciliation gap:** headline 1 COVERED / 6 PARTIAL / 8 ABSENT
/ 1 MOOT vs per-row 1 / 1 / 12 / 0 / 2 blank. Fix #2 and #14 unreadable without
the test log, which is in **neither** repository. Kickoff questions incompletely
enumerated.

**(c) Plan.**

1. Program owner decides whether the test log is vendored redacted (Q7) or
   remains externally pinned.
2. Reconcile PARTIAL/MOOT/Fix #2/#14 from the log — this is documentation, not
   R2 schema.
3. Domain-side S1 register can start without D-0; S2 render waits on D-0.
4. S3–S5 follow ADR-0010/0012 (R2/R3, G3 for crawler-shaped work).
5. S6–S10 follow `engagement-model.md` in R2, behind D6/D7/D8 as noted.
6. S11 load test with QR (MM-F02); S12 funnel as one owning query.

**(d) Depends on.** D-0 (render), D6/D7 (catalog), D8 (S10), G3 (S4/S5 extraction),
MM-F02 (S6). **Must not** jump the command-path / G1 queue.

**(e) Accept.** Per-item: register exists; drill-down equality test; event
precision enum in schema; ledger has no balance column; catalog CHECK requires
owner+funded; funnel five metrics share one query.

**(f) Priority.** After CP-G1 conversation is in flight; not before CP-PR1.

---

## 13. CP-TAIL — Deferred and contract-phase items (not a single stream)

Each is real; none is this week's merge blocker.

| Item | Source | Status | When |
|---|---|---|---|
| **F12** drop `uq_user_account_tenant_subject` | ADR-0008, `0003` docstring, remaining-work F12 | Expand-phase kept the redundant unique. Contract-phase after the release that added `0003` is fully promoted. | After first production promote of `0003`, not before. |
| **F-25** weight-proposal aggregate bound | defect-remediation §4.5; PR1 left open; pinned by `test_aggregate_movement_is_deliberately_unbounded` | Decision: normalize-on-apply vs bound-at-proposal vs both. Do **not** invent a number. | With M1/M8, behind G1. |
| **F-11** dtype validation dropped | port-verification / PR1 amendment | Decision recorded as OPEN. | Migration owner, before MM-004 promotion. |
| **F-13 route (a)** real ingest characterization tests | PR1 took route (b) `n/a` | F-12 transcript is the spec. | Before or during CP-REREVIEW. |
| **F-9 / D2** committed vs completed load | eli now refuses future-dated records | Behaviour explicit; whether committed load should count is D2. | Program owner with open decision 2. |
| **Docstring copies** F-4, F-12, F-18/19/21/22 | PR1 re-review notes | Manifest corrected; module strings not. | Same files as CP-REREVIEW; cheap, should ride that PR. |
| **defect-remediation.md §4.6** F-30 table | PR1 F-30 | Review doc annotated; plan table not. | Docs fix in CP-REREVIEW wave. |
| **J14** NULL `result_generation` fallback | remaining-work J14 | Permanent for pre-0004 rows; no retention job. | Accept or add retention; do not `NOT NULL` the column. |
| **SSE auth at open only** | defect-remediation §8.3 | Mid-stream expiry not re-checked. | Decide while touching jobs.py for A5. |
| **422 uncharged** | ADR-0015 | Deliberate; FastAPI validates before handler. | Revisit only if abused. |
| **Cloud Armor L1 / budget L3** | S-002 remaining | No deploy, no paid provider. | R4 / first live spend. |
| **MM-F01** shadcn port | manifest inventoried | Confirm upstream license; no mockData. | After W1/W2/W4. |
| **MM-F02** QR helpers | inventoried, R2 | Token model replaced (v1.1 §1.9). | With S6. |
| **MM-F03** student points | inventoried REPLACE | ADR-0013. | R2 + D6/D7. |
| **Classroom-reset tooling** | stakeholder audit; diagram 3 | No backlog ID. | Needs a scope before a number. |
| **Crawler threat model** | MM-A08, ADR-0003, remaining-work R3 | No crawl code. Gate G3. | Before any crawl code. |
| **Agent-memory Slice 1** | `docs/superpowers/plans/2026-08-24-agent-memory-slice-0.md`; spec | Slice 0 done. Reservation moved 0010 → 0015 → **0016** on PR1 (ADR-0015 taken by J16). Spec still says ADR-0015. | When Slice 1 starts; first fix the number in the spec. |
| **Deferred ledger claims 0004–0006** | stakeholder-audit-integration §9 Q8 | Maintainer must approve; agents must not write `reviewed_by`. | Maintainer. |
| **D3–D8** | remaining-work | Outside engineering. | As their blocked items approach. |
| **R2–R5 product slices** | remaining-work "Deferred beyond R1" | Profiles, ICS delivery, Jarvis, mail, conversational CC. | After their gates. |

---

## Security findings — residual map

From `docs/security/scaffold-security-review.md`, current residual:

| ID | Residual | Critical path |
|---|---|---|
| S-001 | No signature backend, no JWKS | CP-A1B |
| S-002 | Cloud Armor + budget layers absent | CP-TAIL (deploy) |
| S-003 / S-004 | Pinning + pip-audit done on `main`; SBOM/license on PR1 (F2b) | CP-PR1 |
| S-005 | Legacy local DBs — out of scope here; adjacent to MM-A09 | CP-PII |
| S-006 | No `owning_unit_id`; extended to re-drive/abandon | CP-A5 |
| S-007 | Bare grant cannot satisfy role-gated ops (fail-closed); which roles a grant *should* convey is A4 | A4 done on PR1; policy still open |
| S-008 | 409 quota kept; J15/J16 close the remaining holes **on PR1** | CP-PR1 |

New, from A4: **JOB-READ-IGNORES-GRANTS** (CP-GRANT).

---

## Migration items not yet ported or verified

| ID | Status on `main` | Status on PR1 | Notes |
|---|---|---|---|
| MM-001 | `verified` with F-1..F-3 | F-1..F-3 fixed; still `verified` | Does not gate re-review. |
| MM-002 | `blocked_contract` | same | CP-G1. |
| MM-003 / 004 / 005 | `ported_unverified` | code+YAML corrected; **still** `ported_unverified` | CP-REREVIEW. |
| MM-A01–A08 | `archived` | A08 amended with ADR-0010/0012 | A08 still needs crawler threat model at R3. |
| MM-A09 | `archived` (target); legacy exposure open | same | CP-PII. |
| MM-F01 | `inventoried` | same | Frontend hold. |
| MM-F02 | `inventoried` | same | R2 / S6. |
| MM-F03 | `inventoried` | same | R2 / ADR-0013. |
| MM-F04 | `archived` | same | Chat cut. |

Manifest schema on PR1 gained `behavior_introduced` / `behavior_replaced` /
`contract_refs_status` (defect-remediation §3.3). `main` does not have those
fields yet.

---

## Contract / OpenAPI gaps

`contracts/openapi/smartmatch.json` (this checkout) documents:

- `GET /api/health`
- `GET /v1/jobs/{job_id}`, `GET …/events`, `POST …/redrive`, `POST …/abandon`
- `POST /v1/units/{unit_id}/imports`

There are **no** matching, profile, attendance, QR, outreach, or metric routes.
That is honest: those surfaces are not implemented. It is a gap relative to
v1.1 §1.11's eventual surface, not a drift defect. W2 generates the TypeScript
client from this file; building screens against a richer hand-written client
is forbidden (v1.1 §5.1, `DESIGN.md`).

ADR-0015 (PR1) does not change response models. Do not add `AbandonedResponse.replayed`
until W2 has a consumer (`transaction-boundary-defects.md` §7).

---

## Assumptions this index makes

1. Nothing is deployed. Severities are about the first day the API serves
   traffic, not about production incidents.
2. The legacy at `bdce024` remains reachable for CP-REREVIEW. If it does not,
   F-21 and F-12 become unfalsifiable (`defect-remediation.md` §10 assumption 2;
   PR1 review already noted the legacy tree missing from that checkout).
3. PR1's claim of 1078 green tests is taken as the branch author's measurement;
   CP-PR1 re-runs the suite rather than trusting it.
4. `origin/main` four-commit lead is CI (gitleaks, lock regen), not product
   work; rebase PR1 onto it as part of merge, do not treat it as a third
   architecture line.

---

## Open questions that block more than one path

Carried forward; none is defaulted here.

| # | Question | Blocks | Owner |
|---|---|---|---|
| 1 | MM-A09 remediation: history rewrite or replace the repo? | D9, LICENSE, open-source | **Unassigned** (CP-PII) |
| 2 | Vendor v1.1 or demote `contract_refs`? | Clean `verified` | Program owner (CP-V11) |
| 3 | Canonical factor set, including the two unimplemented and the two stakeholder factors with no target? | M1–M10 | Program owner (CP-G1) |
| 4 | `EngagementRecord` = completed only, or committed too? | ELI semantics | Migration owner + D2 |
| 5 | Weight proposal: normalize on apply, bound at proposal, or both? | F-25, M8 | Program owner + engineering |
| 6 | Charge quota on `422`? | ADR-0015 leftover | Engineering, only if abused |
| 7 | Vendor the stakeholder test log, redacted? | Audit reconciliation | Maintainer (Q7) |
| 8 | DESIGN.md owner? | All frontend | Unassigned (CP-D0) |
| 9 | Quota as its own transaction — already decided as ADR-0015 on PR1; confirm `commands.py` J15 hole is closed as a side effect | Docs on `main` still ask this (`transaction-boundary-defects.md` §9 Q1) | Closed on PR1; strike the question in CP-DOCSYNC |
