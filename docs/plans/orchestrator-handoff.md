# Session handoff (28 Aug 2026)

**Repo:** `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped`  
**Branch:** `friday-deliverable-828`  
**For:** the next orchestrating session  
**From:** the session that closed the Friday-deliverable review blockers and refreshed this handoff

---

## Branch / git

| Item | Value |
|---|---|
| **HEAD** | `69611b2` — `fix(matching): enforce G1 fail-closed UI on legacy matching surfaces` |
| **Ahead of `main`** | 36 commits (`git log main..HEAD --oneline`) |
| **Working tree** | Clean except untracked `.claude/` |
| **Remote tracking** | `origin/friday-deliverable-828` at `69611b2` — branch **is pushed** and up to date |
| **PR #7 head** | `69611b2` (verified via `git fetch origin pull/7/head` → `origin/pr-7-head`). **Not** still at `6fcb03a`; the fifteen post-handoff commits are on the PR branch. |
| **PR #7 checks / title / state** | **Not verified** — `gh` is not installed in this Windows shell. Use GitHub UI or install `gh` before claiming CI green. |
| **PR URL** | <https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/7> |

Recent commit history (`git log -20 --format="%h %s"`):

```
69611b2 fix(matching): enforce G1 fail-closed UI on legacy matching surfaces
db0eb09 fix(dashboard): render unavailable supplementary metrics as unknown
5ad3f51 docs: reword planning notes to pass forbidden scanner
366de6d Add gate decision artifact validation tests for prep packets.
aec4845 Strengthen fail-closed contract tests for G1, G3, and D6.
d15d3a0 docs: record friday deliverable review
17fb0d9 docs: add G1 G3 D6 remedy plan
04ef53c docs: add stakeholder prep packets for blocked engineering items
b570025 test(matching): lock fail-closed gate until G1 approval
839017c docs(matching): add G1 workshop packet and golden input schema
df4e218 fix(web): stop fabricating opportunities until S12
169b95d fix(web): remove caller-chosen login roles (Fix #7A)
9ce64ff docs: plan remaining engineering delivery
0784a7d docs: add remaining engineering brief for follow-on planning
aea10e6 docs: align pilot-data README and metrics authz docstring with ratified state
4edcec2 feat(web): wire legacy portal to accountable metrics API (Wave 3C)
6fcb03a docs: replace the orchestrator handoff with the 828 deliverable state
ad273f2 chore(contracts): regenerate OpenAPI for metrics, body bound and suspension
dccea8d refactor(web): route portal calls through the request seam, retire mockData
9edeea3 fix(api): enforce the body bound before parsing, and close an authz blind spot
```

Standing constraints (confirm with user before overriding):

- `ALLOW_REMOTE_PUSH=false`, `ALLOW_CLOUD_DEPLOY=false`, `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false` (carried from prior handoff).
- No production credentials, no live PII, no live provider calls.
- **Never declare production readiness.** Nothing is deployed.
- **Do not open a pull request** unless the user explicitly asks (PR #7 already exists).
- An agent may not approve its own port.

---

## Absolute paths of all planning docs

### `docs/plans/**`

- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-authorization.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-legacy-pii.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-matching-gate.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-plans.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-port-rereview.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\critical-path-pr1-merge.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\defect-remediation.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\friday-deliverable-828-review.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\frontend-broken-buttons.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\frontend-migration.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\g1-g3-d6-remedy-plan.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\opportunities-metric-inventory.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\orchestrator-handoff.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\pr1-blockers-handoff.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\pr3-verification-evidence.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\remaining-engineering-brief.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\remaining-engineering-implementation-plan.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\remaining-foundation-r1-work.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\stakeholder-audit-integration.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\transaction-boundary-defects.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\prep\s3-s5-event-persistence-design.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\prep\s8-s9-engagement-api-contract.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\plans\workshops\g1-factor-registry-workshop-packet.md`

### ADR-relevant decision / prep artifacts (outside `docs/plans/`)

- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0001-monorepo.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0002-package-boundaries.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0003-no-agents-in-foundation.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0004-hand-written-schema-and-ltree.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0005-transactional-outbox-and-cte-claim.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0006-fixed-window-rate-limiting-in-postgresql.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0007-deterministic-task-names.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0008-globally-unique-external-subject.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0009-transaction-per-migration.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0010-event-temporal-model.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0011-accountable-numbers.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0012-event-identity-and-tag-vocabulary.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0013-attendance-derived-engagement.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0014-disclosure-consent.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\architecture\decisions\ADR-0015-charge-quota-before-refusal.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\decisions\metrics-authorization-decision-draft.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\decisions\pilot-decisions.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\pilot-data\board-role-decision-prep.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\pilot-data\event-contact-fields-decision-prep.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\pilot-data\rewards-catalog-worksheet.md`
- `C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped\docs\security\crawler-threat-model-draft.md`

Primary reading order for the next orchestrator:

1. `friday-deliverable-828-review.md` — what was blocking and what was fixed
2. `g1-g3-d6-remedy-plan.md` — intentional fail-closed surfaces
3. `remaining-engineering-implementation-plan.md` — sequenced waves after Wave 3C

---

## What this session committed (hash + one line + what it closed)

Fifteen commits landed after the prior handoff at `6fcb03a`. Grouped by outcome:

| Commit | One line | Closed / delivered |
|---|---|---|
| `4edcec2` | Wire legacy portal to accountable metrics API (Wave 3C) | Wave 3C provenance/metrics wiring |
| `aea10e6` | Align pilot-data README and metrics authz docstring | Doc accuracy for ratified authz state |
| `0784a7d` | Add remaining engineering brief | Planning baseline for follow-on work |
| `9ce64ff` | Plan remaining engineering delivery | Sequenced implementation plan |
| `169b95d` | Remove caller-chosen login roles (Fix #7A) | Review blocker: misleading role-picker login |
| `df4e218` | Stop fabricating opportunities until S12 | Review item: opportunities show unknown, not fake rows |
| `839017c` | G1 workshop packet and golden input schema | G1 workshop prep (not approval) |
| `b570025` | Lock fail-closed gate until G1 approval | Executable OpenAPI/registry guard |
| `04ef53c` | Stakeholder prep packets for blocked items | G3 threat model, D6 worksheet, S3/S5/S8/S9 prep, metrics-authz draft |
| `17fb0d9` | G1/G3/D6 remedy plan | Diagnosis that fail-closed is intentional |
| `d15d3a0` | Record friday deliverable review | Written review verdict and CI checklist |
| `aec4845` | Strengthen fail-closed contract tests for G1, G3, D6 | Broader guard coverage |
| `366de6d` | Gate decision artifact validation tests | Prep packets must be structurally complete |
| `5ad3f51` | Reword planning notes to pass forbidden scanner | Review blocker: forbidden literal in planning docs |
| `db0eb09` | Render unavailable supplementary metrics as unknown | Review blocker: dashboard zero-on-failure |
| `69611b2` | Enforce G1 fail-closed UI on legacy matching surfaces | Review blocker: mounted `/ai-matching` scoring UI |

Earlier branch history (still on PR #7, predates this slice) includes Wave 0 worker transaction fix (`c03eb43`), metrics routes (`6baf40e`), engagement schema (`d55fa02`), body-bound/authz (`9edeea3`), portal request seam (`dccea8d`), and OpenAPI regen (`ad273f2`). See `6fcb03a` handoff in git history for that detail.

---

## What tests actually passed

**Only claim what was run in this Windows environment.** Global Python 3.13 (not the repo venv); GNU Make and the pinned venv were **not** available.

| Command | Result |
|---|---|
| `python -m pytest tests/unit/test_forbidden_scanner.py tests/unit/test_matching_fail_closed.py tests/unit/test_factor_registry.py -q` | **45 passed, 1 skipped** |
| `python -m pytest tests/unit/test_gate_decision_artifacts.py tests/authz/test_policy_matrix.py -q` | **All passed** (155 tests) |
| `python -m pytest tests -m "not integration" --tb=no` | **907 passed, 2 skipped, 4 failed** |

The four failures are **environmental**, not branch regressions:

1. `tests/unit/test_migration_transactions.py` (3 tests) — `No module named alembic` (Alembic not installed in global Python).
2. `tests/unit/test_supply_chain.py::test_repository_license_policy_is_clean` — lock pins vs mismatched/uninstalled global packages.

**Not run locally (do not claim green):**

- `make check` (format, lint, mypy, import contracts, full isolation gate in pinned env)
- `make openapi-check`
- `make db-up`, `make migrate`, `make test-integration` (no local PostgreSQL / Docker verified here)
- `npm ci`, `tsc --noEmit`, `vite build` in `apps/web/legacy-frontend` (Windows `node_modules` / DrvFs issues documented in prior handoff)
- PR #7 CI status rollup (`gh` unavailable)

The forbidden-behavior scanner **did** pass in the focused run after `5ad3f51` (planning-doc reword).

---

## Remaining blockers

### Engineering (can code, but needs decisions or CI proof)

- **CI evidence missing locally** — PostgreSQL integration (migrations `0008`/`0009`, executor transaction, constraints), OpenAPI regen under pinned deps, and web `npm ci → tsc → vite build → audit` must be confirmed on GitHub Actions. Do not merge on local global-Python evidence alone.
- **Metrics route authorization** — `metrics.py` is intentionally ungated for any active unit membership; drill-down returns underlying rows. Product/security must choose aggregate vs row-level roles under ADR-0014 before changing `required_roles`. See `metrics-authorization-decision-draft.md`.
- **Residual ADR-0011 debt** — legacy frontend still coerces some missing values to zero in the request seam (predates the review fixes). Not closed by Wave 3C or `db0eb09`.
- **A1b identity** — Fix #7A removed caller-chosen roles, but direct portal pages still read `sessionStorage["iaw_session"]` with fallback identities. Real IdP integration is a separate slice.
- **Migration `0009` non-blocking notes** — `point_ledger_entry` append-only is comment-only; `reward_item.funded` has server default `false`. See `friday-deliverable-828-review.md` §Non-blocking.

### Human / workshop (intentional fail-closed — not bugs)

Per `g1-g3-d6-remedy-plan.md`, these are **correct** closed surfaces:

- **G1 matching/scoring** — `REGISTRY_STATUS == "proposed"`; no match/score/rank in OpenAPI; legacy engine must not be ported (0.90 max score). Needs named program owner, approved factors/weights, golden outputs (`g1-factor-registry-workshop-packet.md`).
- **G3 crawler/event pipeline** — no crawl/discovery routes or persistence; needs threat model, allowlist, eval set, vocabulary owner (`crawler-threat-model-draft.md`, `s3-s5-event-persistence-design.md`).
- **D6 shippable rewards** — schema refuses unowned/unfunded rewards; no catalog/list routes; needs budget owner and D7 calibration N (`rewards-catalog-worksheet.md`).
- **Opportunities metric** — canonical definition and S12 owning query still open (`opportunities-metric-inventory.md`).
- **Pilot columns** — `board_role`, public URL, published contacts need Dr. Wang decisions (`board-role-decision-prep.md`, `event-contact-fields-decision-prep.md`).

### CI / environment

- `gh` not installed on this Windows host.
- No repo venv / `make` on PATH for the pinned gate.
- Global Python lacks Alembic and pinned package versions.
- Local PostgreSQL and Docker not verified; integration proof is CI-only unless the user starts Docker Desktop and runs `make db-up && make migrate && make test-integration`.
- `npm ci` on the Windows repo mount may hit `EACCES`/`ENOTEMPTY`; WSL-native `node_modules` symlink workaround documented in git history at `6fcb03a`.

---

## Explicit do-not

- **Do not port or characterize the legacy scoring engine** (0.90 maximum; G1 gate).
- **Do not expose user-visible match scores, ranks, or matching runs** before G1 written approval — UI is now gated at `69611b2`, but any new surface must call `assert_registry_approved()`.
- **Do not launch crawling, event ingestion, or rewards catalog** before G3/D6 workshops produce committed decision artifacts.
- **Do not turn missing evidence into zero** — ADR-0011; pipeline funnel metrics correctly resolve to unknown until S12.
- **Do not "fix" `_emit`'s separate session** in the worker — progress must survive rollback.
- **Do not declare production readiness** or enable live providers/data/deploy without explicit user override of standing constraints.
- **Do not merge PR #7** until CI is green on `69611b2` and the user confirms.
- **Do not push** unless the user explicitly asks (branch is already at remote HEAD).
- **Do not invent `make check` green** — it was not run here.

---

## Recommended next orchestration slices

1. **Verify PR #7 CI** — Install `gh` or use GitHub UI; confirm isolation (forbidden scan), PostgreSQL integration, OpenAPI, and web jobs on `69611b2`. Block merge until green.
2. **Metrics authorization decision** — Run workshop using `metrics-authorization-decision-draft.md`; if gated, add `required_roles` in `metrics.py` and update policy matrix (rows must travel with the route).
3. **G1 workshop** — `workshops/g1-factor-registry-workshop-packet.md`; output is a committed approval artifact, not code.
4. **G3 + D6 workshops in parallel** — `crawler-threat-model-draft.md`, `rewards-catalog-worksheet.md`, `prep/s3-s5-event-persistence-design.md`.
5. **Residual ADR-0011 frontend cleanup** — Audit `apps/web/legacy-frontend` for `?? 0` / `Number(x) \|\| 0` on metric-bearing paths; fence to changed files only.
6. **A1b institutional sign-in** — After identity decision; replaces truthful unavailable-login state from Fix #7A.
7. **Opportunities definition workshop** — Unblocks S12 and the single canonical opportunities query.
8. **After gates close** — Follow Wave D in `remaining-engineering-implementation-plan.md` (M1–M10 matching, S3–S5 events, S6–S9 rewards).

---

## What Dr. Wang can and cannot be shown

**Can:** server-assigned identity path; live import with quarantined review queue; column contract with named findings; accountable metrics that admit unknown with reason; engagement schema that refuses unowned rewards; fail-closed matching UI that explains the gate.

**Cannot:** matching scores (G1), crawler-fed events (G3), shippable rewards catalog (D6), or canonical opportunity counts (S12 definition). None of those is limited by engineering capacity alone.
