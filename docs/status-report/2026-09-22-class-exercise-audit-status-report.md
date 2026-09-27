# Audit-status report — 2026-09-22 (class exercise scope)

**Repository:** IA SmartMatch Revamped
**Report type:** Class-exercise module audit vs Dr. Ann Wang's build requirements
**Prepared:** 2026-09-22
**Posture:** Code substantially complete and tested; not deployed; no real
dataset; results rule refuses to run pending owner-confirmed coefficients

**Requirements authority:** `docs/product/class-exercise-requirements.md`
(2026-09-16, transcribing Ann's Sept-15 build table and email)
**Design spec:** `docs/superpowers/specs/2026-09-16-class-exercise-design.md`
**Architecture:** `docs/architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md`,
`ADR-0026-student-program-and-student-centric-classroom.md`
**Open-question register:** `docs/plans/open-questions/class-exercise-open-questions.md` (OQ-CE-01–13)
**Owner-decision queue:** `docs/archive/plans/owner-open-decisions-2026-09-19.md`

Scope note: this report audits `ProductScope.CLASS_EXERCISE` only — the Spring
2027 AI in Marketing class exercise (300 fictional profiles → 2 exercise
events). It says nothing new about the CBA platform track; for that see
`2026-09-21-audit-status-report.md`. This report decides nothing and fills no
owner field.

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| Domain + persistence | Implemented | `smartmatch_domain/exercise/*`, `smartmatch_persistence/exercise/*`, migration head `0037_exercise_tables` |
| API surface | Implemented | 20+ `/v1/exercise` routes, mounted only under `class_exercise` scope; zero paths in committed OpenAPI contract (deliberate, ADR-0025 D1) |
| Frontend | Implemented, 2 real gaps | All 6+ screens mounted, every call reaches a real route; results run cannot select a saved setting; instructor unlock panel needs a team cookie |
| Results simulation | **Blocked** | `EXERCISE_SIMULATION_COEFFICIENTS=None` → 409 `exercise_results_rule_not_confirmed` (OQ-CE-03) |
| Dataset | **Absent** | Ann's Sept-18 sample never arrived; Sept-25 full file pending; ingest runs on `PLACEHOLDER_LAYOUT` |
| Hosting | **Not executed** | `exercise.plated.blog` decided 2026-09-21; compose service + runbook written; nothing ever deployed; runbook's tunnel config cannot serve the SPA as written |

**Bottom line:** The class module is ~90% code-complete with an unusually deep
test suite (unit + golden + integration, incl. scope-isolation proofs) and zero
"Not now" scope violations. It cannot run today for three non-code reasons:
Ann's dataset has not arrived, `exercise.plated.blog` has never been stood up,
and the simulation coefficients ship as `None` by design. The Oct-2 milestone
("matching … working on the site with the full data") is at risk on data and
deploy, not on engineering.

---

## 1. Dr. Wang's three stated keeps

From her email: *"the matching engine with adjustable weights, the ranked list
with a reason next to each name, and the results screen."*

| Keep | Status | Evidence |
|------|--------|----------|
| Matching engine, adjustable weights | Implemented | `python/smartmatch_domain/smartmatch_domain/exercise/registry.py:137-200` (4 factors, Ann's plain labels, placeholder 0.25 defaults OQ-CE-02); `exercise/matching.py`; per-team weight routes `services/api/smartmatch_api/routers/exercise_matching.py` |
| Ranked list, reason next to each name | Implemented | `exercise/reasons.py` (incl. verbatim `ANN_MAJOR_ONLY_PHRASE`, `ANN_TIED_ON_YEAR_PHRASE`); rendered `apps/web/legacy-frontend/src/app/pages/exercise/RankedList.tsx:111`; wording placeholders pending Ann (OQ-CE-12) |
| Results screen | **Blocked** | Screen + panels + lock + comparison all built; runtime refuses until `EXERCISE_SIMULATION_COEFFICIENTS` set — `simulation.py:408-424`, 409 path proven in `tests/unit/test_exercise_results_router.py:665-686` |

## 2. Build-table status (required rows)

| Row | Status | Evidence / gap |
|-----|--------|----------------|
| Getting in — no login, public address, teams 1–6, tab workspaces | Implemented (site pending) | HMAC workspace tokens `exercise/workspace_token.py`; teams 1–6 `exercise/__init__.py:37`, CHECK constraint `db/migrations/versions/0037_exercise_tables.py:222`; same team # shares workspace across tabs (OQ-CE-08 open) |
| Instructor page — passcode, open any team's runs, unlock, invite limit, replace file, refresh-all, reset | Implemented | `routers/exercise_instructor*.py`; fail-closed passcode `exercise_instructor_session.py:175-183`; wrinkle: unlock panel lists events via team route, needs workspace cookie (`ExerciseInstructor.tsx:237-241`) |
| Data — ~300 profiles, 12 events (10 past + 2 exercise), instructor replace, missing-column sentence | **Partial** | `exercise/ingest.py` works; exactly-2 exercise events enforced; CSV only, XLSX refused with sentence (OQ-CE-05); column layout is `PLACEHOLDER_LAYOUT` `exercise/layout.py:151-172` (OQ-CE-01) |
| Hidden "true" interests — never shown, never matched, results-rule only | Implemented | Withheld set `exercise/__init__.py:41`; sole reader `dataset_repository.py:493-535`; response-body walks `test_exercise_results_router.py:1596-1721` |
| "How much we know" markers (3 levels) + list counts by group | Implemented | `exercise/markers.py`; `ListCompositionTable.tsx` |
| Matching — 4 plain-label factors, major always on, unknowns don't count | Implemented | Unknown contributes nothing, weight not re-spread (ADR-0016/§4.3), `matching.py:18-41` |
| Tie-break — more info → seniors first → fixed random | **Partial** | Sort key `matching.py:289-307`; fixed order SHA-256 `determinism.py:53-88`; **year rung dormant**: `PLACEHOLDER_CLASS_YEAR_RANK={}` `exercise_matching_models.py:202` until year vocabulary arrives (OQ-CE-01) |
| Reason lines incl. "same major; nothing else on file" / "tied on major; ordered by year" | Implemented | `reasons.py:83-100`; three sibling phrases are placeholders awaiting Ann's words (OQ-CE-12) |
| Invite cap (default 30), ≤3 named settings/event, side-by-side compare w/ shared names highlighted | Implemented | Cap `0037:125`; settings cap + advisory lock `settings_repository.py:73,379-385`; `on_both_profile_nos` `exercise_matching.py:499-563`; highlight `RankedList.tsx:90-106` |
| "Who is on the list" table vs all-300 counts | Implemented | `exercise_matching_models.py:448-459,629-656`; incl. if-time coverage notice `exercise_list_coverage.py:104-160` |
| Download list with reasons as spreadsheet | Implemented | `GET …/list.csv` `exercise_matching.py:423-491`; formula neutralisation `exercise_matching_csv.py:107-135` |
| Results lock — instructor unlock per event, one run per team per event | Implemented | Unlock row `0037:346-357`; gate `exercise_results_run.py:350-363`; UNIQUE one-run `0037:328` + `AlreadyRunError` `results_repository.py:203,433-436` |
| Comparison — "email everyone" baseline; round-1 result in round 2; seats empty | Implemented | `exercise_results_run.py:207-261`; `seats_empty` `simulation.py:597`; `ResultPanels.tsx:34-92` |
| Simulated results — hidden rule, 5 sub-rules, deterministic per team, per-team reset, plain-words | **Blocked** | Full rule + docstring `simulation.py:1-39,405-597`; all behaviors test-proven with test-only coefficients; ships `None` → 409 (OQ-CE-03) |
| Asking for more — 3 choices, ~30/55/80%, ~15% disengage | Implemented | `asking.py:57-90`; once-only `results_repository.py:460-490`; placeholders pending Ann (OQ-CE-04); half-rounding edge flagged `exercise_results_refresh.py:23-37` |
| Profile refresh — per-team, attendees gain topics, cards copied from hidden, markers update, instructor refresh-all, isolation | Implemented | `exercise_results.py:390-467`; `results_repository.py:565-605`; `exercise_instructor_refresh.py:96-203` (atomic, per-team seeds); copied-card goal policy OQ-CE-13 shipped (`asking.py:119`) |
| Hosting — stable address, <5s Chrome load | **Not done** | Address decided (`exercise.plated.blog`, OQ-CE-06 half-closed); `docker-compose.exercise.yml` + 1,025-line runbook exist; **never executed** (`exercise-hosting.md:998-1005`); TTI never measured |

**If-time-allows:** coverage notice (done), bar-chart results `ExerciseResultsChart.tsx` (done), five-questions mockup `ProfileCardMockup.tsx` (done, unlinked), points counter `exercise_points.py` + `ProfilePointsCounter.tsx` (arithmetic + component done; **unwired — no API field, mounted nowhere**).

**"Not now" violations: none.** No accounts/roles, invite-only speaker
accounts, ML matching, speaker-to-event matching, real student data, real
notifications/email, or in-app message writing exists in exercise scope —
enforced by `product_scope.py:315-331`, router mounts `main.py:594-657`, and
the forbidden-import scanner `tests/unit/test_class_exercise_scope.py:167`.

## 3. Blockers, ordered by leverage

| # | Blocker | Owner | Consequence of waiting |
|---|---------|-------|------------------------|
| 1 | **OQ-CE-01 dataset** — 20-row sample (due Sept 18) never arrived; 300-row file due Sept 25; layout + `class_year` vocabulary unknown | Ann | Oct-2 milestone fails: "on the site with the full data" impossible; year tie-break stays dormant |
| 2 | **Deploy execution** — all 22 runbook steps unrun; hostname, secrets, DB role, WAF rule pending; SPA-origin gap below | Danny | No site at any date; Oct 2 slips regardless of code |
| 3 | **OQ-CE-03 coefficients** — rule needs **eight** quantities; Chau proposes Oct 2, Ann confirms before Nov 9 | Chau→Ann | Oct-16 milestone fails: `require_coefficients()` raises; results untested until demonstrated |
| 4 | **OQ-CE-06 second half** — Cloudflare WAF rate-limit rule, the only edge protection on a no-Access public host | Danny | Public URL ships with per-process limiter only |
| 5 | **OQ-CE-07** instructor passcode — unset fails closed | Danny+Ann | Instructor page dead at deploy |
| 6 | **Results-run setting picker** — UI hard-codes `setting_name: null` (`ExerciseResults.tsx:180`); a run always simulates default weights | Engineering | Teams' tuned weights never reach the simulation |
| 7 | Ann message unsent — ready-to-paste at `owner-open-decisions-2026-09-19.md:18-31`, covers OQ-CE-01/04/05/08/09/11/12 | Danny→Ann | Six register rows stay open |
| 8 | OQ-CE-02/04/10 placeholder numbers; OQ-CE-09 license line; OQ-CE-11 five questions | Ann/Chau | Practice-run polish, not Oct-2 blockers |
| 9 | Justin's row-by-row test deliverable (due Oct 16) — no e2e harness exists; coverage is Vitest + pytest only | Justin | Oct-16 review has no independent test list |

## 4. Deploy defect found during audit

`exercise-hosting.md` §4 correctly requires `exercise.plated.blog` to route
`/v1/exercise` → exercise API and everything else → static frontend, but §4a/§9
configure **one** hostname entry → `127.0.0.1:8090`. The API mounts no SPA (no
`StaticFiles`; `GET /` → 404), and the vite dev server's single proxy target is
pinned to the CBA `api:8080`, which 404s every exercise route. The working
shape — `exercise.plated.blog`+`/v1/exercise*`→8090 plus
`exercise.plated.blog`→5173 (or a built SPA) — is written down nowhere. The
frontend already ships the failure sentence: `NOT_THE_EXERCISE`
(`exerciseApi.ts:132-148`). Step 12 of the deploy checklist cannot pass as
written.

## 5. Doc drift

| Finding | Detail |
|---------|--------|
| OQ-CE-13 register row stale | Register says "not yet in the code"; the policy shipped via PRs #195/#199 (`asking.py:119`, `results_repository.py:503-557`) |
| Owner-decisions #1–4 stale | Listed OPEN in `owner-open-decisions-2026-09-19.md`; all four decided 2026-09-21 per `exercise-hosting.md` |
| README capability table omits exercise | Zero rows for the whole second product (scope, `exercise_*` tables, `/v1/exercise`, ~30 test modules) — drift by omission |
| Design spec normative text vs "as shipped" | 5 corrections live only in footnotes (raw CSV upload, in-process limiter, signed cookie, workspace-wins, instructor-only reset) |
| `critical-path-plans.md` | No class-exercise mention despite it carrying the repo's only dated external deadlines |
| Requirements doc vs pivot email | **Not outdated** — it post-dates and transcribes the Sept-15 email; it *is* the pivot's document |
| Phase-two speaker workflow | Correctly logged `docs/plans/backlog.md:11` with Ann's "phase two" quote |

## 6. Timeline position

| Milestone | Date | Status |
|-----------|------|--------|
| Scope confirmed; 20-row sample due | Sept 18 | Sample **not received** — chase it |
| Full 300-row file due | Sept 25 | Pending (3 days) |
| Matching + factors + tie-break + cap + settings + markers + list table **on the site with full data** | Oct 2 | **At risk** — code done; site and data do not exist |
| Results + lock + comparison + refresh + round 2 + download working; Ann runs both sessions | Oct 16 | At risk — gated on coefficients (#3) and deploy (#2) |
| Problems fixed | Oct 30 | — |
| Practice run w/ Ann, Dr. Lin, volunteers | Week of Nov 9 | — |
| Fall deliverable; Ann's CBACH decision | Nov 20 | — |

## 7. Key reference paths

- Requirements: `docs/product/class-exercise-requirements.md`
- Register: `docs/plans/open-questions/class-exercise-open-questions.md`; proposal for Ann/Chau: `class-exercise-proposal-for-ann-and-chau.md`
- Owner queue: `docs/archive/plans/owner-open-decisions-2026-09-19.md`
- Runbook: `docs/operations/exercise-hosting.md`; compose: `docker-compose.exercise.yml`
- Domain: `python/smartmatch_domain/smartmatch_domain/exercise/`; persistence: `python/smartmatch_persistence/smartmatch_persistence/exercise/`; routes: `services/api/smartmatch_api/routers/exercise_*.py`
- Frontend: `apps/web/legacy-frontend/src/app/pages/exercise/`; transport `src/lib/exerciseApi.ts`, `exerciseClient.ts`
- Tests: `tests/unit/test_exercise_*.py`, `tests/golden/exercise/`, `tests/integration/test_exercise_*.py`

---

*End of audit-status report.*
