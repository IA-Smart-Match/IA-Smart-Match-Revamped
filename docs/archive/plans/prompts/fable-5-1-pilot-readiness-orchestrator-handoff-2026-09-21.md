# Fable 5.1 pilot-readiness orchestrator — handoff, 2026-09-21

**Goal:** Complete every row of the pilot-readiness checklist in
[`docs/status-report/2026-09-21-audit-status-report.md`](../../../status-report/2026-09-21-audit-status-report.md)
§6 that engineering can close without institutional IdP or crawler runtime.

**Supersedes for scope:** the hard-gate line *"D6/D7 rewards"* in
[`fable-5-1-backlog-orchestrator-handoff-2026-09-21.md`](fable-5-1-backlog-orchestrator-handoff-2026-09-21.md)
— **rewards is now mandatory** for this pilot. The exercise wave train in that
file remains authoritative for CE tracks unless this document says otherwise.

Paste the block below as the **first message** of a fresh Fable 5.1 session.

---

```text
/goal Complete pilot-readiness checklist §6 (2026-09-21 audit) by orchestrating Sonnet 5.0 subagents in isolated worktrees — one track, one PR, one review each. Read docs/archive/plans/prompts/fable-5-1-pilot-readiness-orchestrator-handoff-2026-09-21.md first, then docs/archive/plans/prompts/fable-5-1-backlog-orchestrator.md (XML operating contract), then docs/status-report/2026-09-21-audit-status-report.md §6.

Mission: every checklist row YES or honestly PARTIAL except (a) institutional sign-in — DEFERRED, do not dispatch P2/A1b; (b) crawler — DEFERRED, do not dispatch G3/S6a. Rewards is MANDATORY: funded synthetic catalog + seed path + student/coordinator flows + un-skip e2e rewards step where appliance is seeded.

Subagent model: Sonnet 5.0 (claude-fable-5-thinking-medium or composer-2.5 if Sonnet unavailable). Orchestrator: Fable 5.1. Worktrees: .claude/worktrees/ or git worktree add per using-git-worktrees skill — never share a worktree between tracks.

Verify origin/main before every wave (git fetch). Owner merges; you do not. UpdateGoal complete only when Phase F audit passes every success_criterion in the armed goal.
```

---

## Pilot-readiness checklist → tracks

| Checklist row | Target | Track id | Notes |
|---------------|--------|----------|-------|
| Institutional sign-in | **DEFER** | — | Pilot has no IdP; fixture auth stays |
| Pilot import + `columns.yaml` | YES (CBA) | VERIFY-COLUMNS | `make verify-pilot-dataset`; no code unless drift |
| Trustworthy matching | YES | VERIFY-MATCH | CBA `POST …/match-runs`; exercise matching API |
| Opportunities metric | YES | VERIFY-O3 | Already bound; regression tests only |
| Honest coordinator metrics | YES | VERIFY-P1 | Policy matrix + metrics contract |
| **Rewards** | **YES (mandatory)** | **P7-REWARDS-PILOT** | See § Rewards below |
| Crawler | **DEFER** | — | G3 signed; no runtime |
| D8 / real student data | PARTIAL | — | Synthetic pilot only; no peer-attendance disclosure surface |
| Frontend | YES | CE-MOUNT + VERIFY-CBA-UI | Exercise screens + coordinator portals smoke |
| Managed DB backups | YES (docs + optional staging project) | SUPABASE-SOP | Ticket acceptance criteria |
| Deployed & reachable | YES | EXERCISE-HOSTING + VM-VERIFY | Exercise scope on VM; CBA already at pilot.plated.blog |

---

## Rewards mandatory — P7-REWARDS-PILOT

**Previous orchestrator handoff gated D6/D7.** This pilot run **lifts that gate
for synthetic pilot only**, using tentative decisions already in
`docs/decisions/pilot-decisions.md` (100 pts/event, N=3 tentative) and
`docs/pilot-data/rewards-catalog-worksheet.md`.

**Deliver:**

1. Owner-approved **synthetic** catalog rows in pilot seed (or fixture seed
   script) — every item has `budget_owner_id` + `funded=true` per migration
   `0009` constraints.
2. `make seed-pilot-rewards` documented in VM deploy / local walkthrough; pilot
   appliance recipe includes rewards seed step.
3. Coordinator can list funded items; student can request/decide when balance
   covers cost (attendance credit path already exists).
4. `tests/e2e/test_pilot_clickthrough.py` rewards step: either runs when seed
   present or documents explicit seed in `pilot-e2e` workflow — **not
   permanently skipped on every CI run** without reason.

**Do not:** invent real budget owners, live money, or close D6/D7 registers.
Mark worksheet fields `TENTATIVE (pilot-decisions.md)` where used.

**Read first:** `docs/archive/plans/2026-08-28-d6-rewards-s8-s9-plan.md`, P7 cards
L1–L4 as already implemented; gap is **content + seed + e2e wiring**.

---

## Wave train (pilot-readiness)

Max **3** implementation agents. Serial files unchanged from exercise handoff:
`main.py`, `exercise_dependencies.py`, `pyproject.toml` contracts,
`tests/authz/test_policy_matrix.py`, `config.py`, `routes.tsx`, migration queue.

```
WAVE 0 — verify + baseline (orchestrator)
  V0. git fetch; record origin/main SHA, migration head, OpenAPI op count.
  V1. VERIFY-* tracks: columns, match-runs smoke, metrics — report only unless red.
  V2. README sync: migration 0037, exercise scope paragraph if missing.

WAVE A — exercise finish (from 09-21 exercise handoff; skip merged)
  A1. CE-RESULTS-API — if not on origin/main, merge or finish PR #190 follow-ups.
  A2. SPLIT-INSTRUCTOR-ROUTER — refactor/exercise-instructor-session.
  A3. EXERCISE-HOSTING-DOC — docs/exercise-hosting (needs owner #1–2 OR build to recommended defaults).
  A4. CE-MOUNT — feat/exercise-mount-components (after results API on main).

WAVE B — rewards (mandatory)
  B1. P7-REWARDS-PILOT — seed + worksheet + e2e + docs (parallel with A3 if no schema touch).

WAVE C — infra + backups
  C1. SUPABASE-SOP — docs/operations/supabase-setup.md + maintenance + .env.example.
  C2. VM-VERIFY — exercise deploy checklist in vm-deploy.md; optional promote dry-run notes.

WAVE D — closeout
  D1. Update status-report checklist table with evidence links.
  D2. Phase F audit vs goal success_criteria; UpdateGoal complete or list blockers.
```

---

## Hard gates (do not dispatch)

| Gate | Reason |
|------|--------|
| P2 / A1b institutional sign-in | **Owner deferral — pilot has no IdP** |
| G3 crawler / S6a live fetch | **Owner deferral** |
| OQ-SC / OQ-SE student program | Registers OPEN; W4 STOPPED |
| Speaker accounts, AMP, Handshake, mobile | backlog.md parking lot |
| Live email send | OQ-001–003 |
| `ALLOW_CLOUD_DEPLOY=true` | standing constraint |
| Closing OQ-CE-01/03/04 without Ann/Chau | human owners |

**Rewards is NOT in this table for this run.**

---

## Subagent card template (Sonnet 5.0)

```xml
<role>Implementation agent — track [TRACK_ID] only.</role>
<mission>[One sentence from table above]</mission>
<context>
Repository: IA-Smart-Match-Revamped
Base: git fetch origin && git switch -c [branch] origin/main
Worktree: [absolute path]
Model: Sonnet 5.0
PR base: main
</context>
<read_first order="strict">
1. [paths]
</read_first>
<non_negotiables>
- ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, ALLOW_CLOUD_DEPLOY=false
- Regenerate OpenAPI; never hand-edit smartmatch.json
- One migration per PR if schema changes; head+1
- ADR-0025: exercise never touches CBA tables
- Rewards: funded + budget_owner_id or refuse list
</non_negotiables>
<success_criteria>
[Measurable — tests, files, PR URL]
</success_criteria>
```

---

## Phase F completion audit

Before `UpdateGoal complete`, prove each item:

| Criterion | Evidence |
|-----------|----------|
| Institutional sign-in deferred | No P2/A1b files in any merged PR of this run |
| Crawler deferred | No crawl handler/router PRs |
| Rewards mandatory | `make seed-pilot-rewards` + funded row + e2e or CI seed step |
| Import/columns | `make verify-pilot-dataset` log |
| Matching | pytest match-runs + exercise matching tests |
| Metrics | contract tests green |
| Frontend | CE-MOUNT PR merged; routes.tsx exercise paths |
| Supabase | two ops docs exist + .env.example |
| Deploy | exercise hosting section in vm-deploy or exercise-hosting doc |
| Exercise human blockers | OQ-CE registers still OPEN where required; placeholders marked |

---

## Baseline (verify at session start)

| Fact | Check |
|------|-------|
| `origin/main` | `git rev-parse origin/main` |
| Migration head | `0037_exercise_tables` |
| OpenAPI | 83 ops (CBA export; exercise routes scope-gated) |
| Local main lag | May be behind — **always branch from origin/main** |

---

## First actions

1. `CreateGoal` — use the `/goal` block at top (or confirm goal already armed).
2. `git fetch origin`.
3. Run WAVE 0 verify tracks; post ledger.
4. Dispatch **P7-REWARDS-PILOT** and **CE-MOUNT** (if results on main) as first implementation wave.
5. Ask owner decisions 1–4 once (hosting); build to recommended defaults meanwhile.

---

## Phase F audit — 2026-09-21 (goal closure)

**Baseline:** `origin/main` @ `29ce2fab` (#204). Local engineering tracks for this
goal are merged unless noted.

| Success criterion | Result |
|-------------------|--------|
| Checklist §6 rows YES/PARTIAL with owner-only blockers | **Met** — see `docs/status-report/2026-09-21-audit-status-report.md` §6a |
| Institutional sign-in deferred | **Met** — no P2/A1b PRs |
| Crawler deferred | **Met** — no crawl runtime PRs |
| Funded rewards via seed | **Met** — #198/#202; `pilot-e2e` + `SMARTMATCH_E2E_REQUIRE_REWARDS` |
| Supabase runbooks | **Met** — #197 docs + `.env.example` (live project optional) |
| Exercise hosting doc | **Met** — `exercise-hosting.md` + #204 compose |
| CE-MOUNT merged | **Met** — #194, #201 |
| CE-RESULTS / instructor split | **Met** — results routers on main; `exercise_instructor_session.py` |
| README `0037` | **Met** — README row updated on closure branch |
| Exercise Vite host | **Met** — `exercise.plated.blog` in `allowedHosts` |

**Remaining operator/human work (does not block goal):** run exercise-hosting §9 on
VM; Cloudflare WAF rate limit; Ann/Chau OQ-CE rows; Supabase project for drift
test against managed Postgres; D8 for real students.
