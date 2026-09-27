# Audit-status report — 2026-09-24

**Repository:** IA SmartMatch Revamped
**Report type:** Whole-repo audit — class-exercise modules vs Dr. Wang's build
requirements, implementation-plan portfolio vs merged code, and the CBA scope
vs the original SmartMatch platform it replaces
**Prepared:** 2026-09-24
**Posture:** Foundation scaffold strong; **B26 wave fully merged today**;
class exercise code-complete but undeployed; nothing production-ready;
synthetic data only

**Authoritative blocker index:** `docs/decisions/2026-08-31-session-ratification.md`
**Continuation order:** `docs/archive/plans/2026-08-31-ratification-and-implementation-report.md` (V1–V8)
**Class-exercise authority:** `docs/product/class-exercise-requirements.md`
**CBA authority:** `docs/product/cba-smart-match-customer-requirements.md`
**B26 plan + ledger:** `docs/plans/2026-09-22-b26-self-service-availability-plan.md`,
`docs/plans/b26-tracks/LEDGER.md` (branch `docs/b26-ledger`)

This report decides nothing and fills no owner field.

**Verification note:** Audited against **`origin/main` @ `3f183277`** (PR #225,
merged 2026-09-24 ~18:43 PDT) via detached worktree `_worktrees/audit-main`.
The checked-out local `main` is `012080f1` (PR #205, 2026-09-21) — **338
commits behind** the merged tip. All facts below are the merged baseline, not
the working tree. No pytest run was performed; CI on Ubuntu + PostgreSQL 16
remains authoritative (B26 CI: 10/10 jobs green on every merged PR per the
ledger).

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| Backend foundation | **Strong** | 41 migrations (head `0041_invitation_batch_speaker_request`); 69 OpenAPI paths / 88 operations; CBA matching live over HTTP |
| B26 speaker self-service wave | **Merged today** | All 16 tracks (#210–#225) + CI timeout fix (#226); `SPEAKER_PORTAL` capability OFF in every scope; registry 3.0.0 `proposed`, 2.0.0 still current |
| Class exercise product | **Code ~90%, unchanged since 09-22** | Zero exercise-scope commits since PR #205; blocked on dataset, deploy, coefficients — all non-code |
| CBA pilot product | **Moderate** | Synthetic pilot on VM (`pilot.plated.blog`); live OIDC, live send, crawler runtime, CP-SAT still gated |
| Self-hosted dev / appliance | **Available / partial** | `make setup` + compose work; VM runs CBA scope; exercise service defined, never started |
| Cloud pilot | **Not started** | `ALLOW_CLOUD_DEPLOY=false`; Terraform skeleton; Supabase ticket 3/6 criteria |

**Bottom line:** Since the 09-22 class-exercise audit, the repository absorbed
its largest single build wave: the **B26 self-service availability program** —
Speaker portal accounts, availability windows, booking cancellation, batch
Speaker Requests, and the load-aware ELI 2.0.0 / registry 3.0.0 proposal — all
merged to `origin/main` with review and green CI. This is the "phase two"
speaker workflow Dr. Wang deferred for *her* deliverable, built in **CBA scope**
where her "not now" does not apply; it ships dark behind `SPEAKER_PORTAL` with
five stakeholder gates still open. The class-exercise track is byte-for-byte
the 09-22 audit: every code gap and blocker it names still stands, including
the runbook deploy defect (§9 steps 9/12). Original-platform preservation is
intact — all CBA §22 keeps are implemented. The dated risks are external: Ann's
300-row file is due **tomorrow** (09-25) and has not arrived; Oct-2 is eight
days out.

---

## 0. Repository and branch posture (2026-09-24)

| Signal | Value |
|--------|-------|
| Merged tip | `origin/main` → `3f183277` (PR #225, B26 T8d) |
| Local `main` | `012080f1`, **338 commits behind** |
| OpenAPI | **69 paths / 88 operations** |
| Migration head | **`0041_invitation_batch_speaker_request`** (41 revisions; chain `0037`→`0038`→`0039`→`0040`→`0041`) |
| Factor registry | `REGISTRY_VERSION` / `CURRENT_CBA_REGISTRY` = **`2.0.0-approved-oq-cba-004`**; **`3.0.0-approved-b26-eli` declared proposed**, refused as current until approval (ADR-0027) |
| Test surface | 319 `test_*.py` files (floor, incl. 29 exercise + 30 speaker/ELI modules) |
| Untracked local docs | This and the 09-21/09-22 audit reports, B26 handoff prompts, `LICENSE` |
| Uncommitted local fixes | `vite.config.ts` adds `exercise.plated.blog` to `allowedHosts`; `exercise-hosting.md` marks that gap closed — **stranded on the stale checkout, not on `origin/main`** |

---

## 1. Dr. Wang's class-exercise document vs the repo

Authority: `docs/product/class-exercise-requirements.md` (2026-09-16,
transcribing Ann's Sept-15 build table + email). Scope: `ProductScope.CLASS_EXERCISE`
only (ADR-0025).

**Verification:** `git log 012080f1..origin/main` over `exercise/` domain,
persistence, routers, and `pages/exercise/` returns **zero commits** — the
09-22 audit's code findings are current. Re-verified directly on `3f183277`:

### 1a. Her three stated keeps

| Keep | Status | Evidence |
|------|--------|----------|
| Matching engine, adjustable weights | Implemented | `exercise/registry.py`, `exercise/matching.py`, per-team weight routes; placeholder 0.25 defaults (OQ-CE-02) |
| Ranked list, reason next to each name | Implemented | `exercise/reasons.py` incl. verbatim `ANN_MAJOR_ONLY_PHRASE` / `ANN_TIED_ON_YEAR_PHRASE`; `RankedList.tsx`; sibling wording placeholders pending (OQ-CE-12) |
| Results screen | **Blocked** | Built incl. lock/comparison; runtime refuses until `EXERCISE_SIMULATION_COEFFICIENTS` is set — still `None` (`simulation.py:123-124`), OQ-CE-03 |

### 1b. Required build-table rows

| Row | Status |
|-----|--------|
| Getting in — no login, teams 1–6, tab workspaces | Implemented (site pending deploy) |
| Instructor page — passcode, any team's runs, unlock, invite limit, replace file, refresh-all | Implemented; unlock panel still lists events via a team route needing a workspace cookie (`ExerciseInstructor.tsx:237-241`) |
| Data — ~300 profiles, 12 events, instructor replace, missing-column sentence | **Partial** — `PLACEHOLDER_LAYOUT` still in force (OQ-CE-01); CSV only; **dataset absent — full file due 2026-09-25** |
| Hidden "true" interests | Implemented (withheld set; results-rule sole reader) |
| "How much we know" markers + list counts | Implemented |
| 4 plain-label factors, major always on, unknowns don't count | Implemented (no weight re-spread, ADR-0016) |
| Tie-break: more info → seniors → fixed random | **Partial** — year rung dormant (`PLACEHOLDER_CLASS_YEAR_RANK={}`) until year vocabulary arrives with the dataset |
| Reason lines incl. her two verbatim phrases | Implemented; 3 sibling phrases placeholder (OQ-CE-12) |
| Invite cap 30 / ≤3 named settings / side-by-side | Implemented |
| "Who is on the list" vs all-300 counts | Implemented (incl. if-time coverage notice) |
| Download list with reasons as spreadsheet | Implemented (formula neutralisation) |
| Results lock — instructor unlock, one run per team per event | Implemented |
| Comparison — "email everyone" + round-1 result in round 2 + seats empty | Implemented |
| Simulated results — hidden rule, 5 sub-rules, deterministic, resettable | **Blocked** — rule complete; ships `None` → 409 `exercise_results_rule_not_confirmed` |
| Asking for more — 3 choices, ~30/55/80%, ~15% disengage | Implemented; placeholder constants (OQ-CE-04) |
| Profile refresh — per-team, attendees gain topics, copied cards, markers, refresh-all | Implemented; OQ-CE-13 default shipped (`BASE_GOAL`) |
| Hosting — stable address, <5s load | **Not done** — `exercise.plated.blog` decided but never deployed; TTI never measured |

**If-time items:** coverage notice done; bar chart done (`ExerciseResultsChart.tsx`);
five-questions mockup done (`ProfileCardMockup.tsx`, unlinked); points counter —
arithmetic + component done, **unwired** (no API field, mounted nowhere).

**"Not now" violations: none.** No accounts/roles, invite-only speaker accounts,
ML matching, real student data, real notifications, or in-app message writing
in exercise scope — enforced by `product_scope.py`, scope-gated router mounts,
and `tests/unit/test_class_exercise_scope.py`.

### 1c. Exercise blockers (ordered by leverage) — all still open

| # | Blocker | Owner | Consequence |
|---|---------|-------|-------------|
| 1 | **OQ-CE-01 dataset** — 20-row sample never arrived; 300-row file due **tomorrow 09-25** | Ann | Oct-2 fails: "on the site with the full data" impossible; year tie-break dormant |
| 2 | **Deploy execution** — all §9 steps unrun; secrets, DB role, hostname, WAF rule pending | Danny | No site at any date |
| 3 | **Deploy defect** — §9 step 9 points the single hostname at the API (`127.0.0.1:8090`, no SPA mount, `GET /`→404) while step 12 requires `GET /`→200 | Danny | Checklist cannot pass as written; two-route shape described in §4 prose but not in the step |
| 4 | **OQ-CE-03 coefficients** — **eight** quantities; `require_coefficients()` raises | Chau→Ann | Oct-16 results milestone fails |
| 5 | **OQ-CE-06 second half** — Cloudflare WAF rate-limit rule, the only edge protection on a no-Access host | Danny | Public URL ships with per-process limiter only |
| 6 | **OQ-CE-07** instructor passcode — unset fails closed | Danny+Ann | Instructor page dead at deploy |
| 7 | **Results-run setting picker** — `ExerciseResults.tsx:180` hard-codes `null`; tuned weights never reach the simulation | Engineering | Teams' saved settings are decorative at results time |
| 8 | **Stranded fix** — `allowedHosts` for `exercise.plated.blog` exists only as an uncommitted diff on a 338-behind checkout | Danny | Lost if the checkout is reset; needs rebase + PR |
| 9 | Justin's row-by-row test list (due Oct 16) — no e2e harness | Justin | Oct-16 review has no independent test evidence |

---

## 2. Implementation plans vs merged code

### 2a. B26 wave — merged 2026-09-24 (the delta since the last audit)

Plan: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (16 tracks,
28 engineer-days estimated). Ledger records every PR Opus APPROVE, CI 10/10.

| Track | Delivered | PR |
|-------|-----------|----|
| T1/T2 | Domain availability verdicts + `0038_speaker_availability` (windows, declared capacity) | #210, #212 |
| T3/T5 | Connector availability GET/PATCH + panel | #215, #216 |
| T4 | Stage-A availability filter wired, self-request exclusion (Q8), `0041` batch→request link | #220 |
| T6a | `/i/{token}` accept/decline controls fixed | #213 |
| T6b-1…5 | Speaker accounts (`0039`), invite/revoke/activate, `/v1/me/*` routes, self-service consent (Speaker-wins), `/speaker-portal` frontend, one-login-two-roles + switcher | #217, #219, #222, #223, #224 |
| T7 | `VolunteerProfile` host-record close-out | #211 |
| T8a | `0040` booking cancellation + Connector cancel | #218 |
| T8b–d | ELI 2.0.0 centered 90-day utilization, band table, registry 3.0.0 proposed, load bands on Connector + Speaker views | #214, #221, #225 |
| R-D | CI python timeout 15→25 min | #226 |

**Guardrails verified on `origin/main`:**

- `Capability.SPEAKER_PORTAL` = `False` in every scope (`product_scope.py:284,313,349`); routes unmount when off.
- `REGISTRY_VERSION` stays `2.0.0-approved-oq-cba-004`; 3.0.0 is declared
  `proposed` and refused as current pending normal approval + IA West review
  (ADR-0027). The flip (`CURRENT_CBA_REGISTRY = CBA_REGISTRY_3`) is not done.
- R-A applied: no load numbers (`completed_hours`, `confirmed_hours`,
  `capacity`, `utilization`) on the API wire — band + reason only; numbers stay
  in the stored run payload.
- R-B/R-C applied: seed merge volunteer-only with `SeedConflictError`;
  existing-login binding is a `{volunteer}` allow-list.

**B26 stakeholder gates — all open (plan §10):** Ann/Pia/Lisa sign-off on
Speaker accounts; a named privacy owner; IA West review of D2 (keeps 3.0.0
`proposed`); pilot hostname for invite links; retention periods (D5). The code
is merged but dark — nothing Speaker-facing can run until these close. 22
follow-up cards logged in the ledger.

### 2b. Plan portfolio P1–P9 / V1–V8 — unchanged since 09-21

| Id | Status |
|----|--------|
| P1 metrics authz | Implemented |
| P2 institutional sign-in | **Blocked** — fixture auth; A1b worksheet unfilled |
| P3 ADR-0011 zero coercion | Partial |
| P4 caching | Stage 0–1; no Redis |
| P5 matching M1–M10 | M1 closed; CBA factors live; **M7–M10 (CP-SAT, explanations) not started** |
| P6 events/crawler | Parsers + schema; no live crawl |
| P7 rewards | Routes + ledger + coordinator redemption queue (#205, #207); catalog values tentative (D6/D7) |
| P8 opportunities metric | O3 bound |
| P9 pilot columns | Gates closed; `columns.yaml` enforced |

V1–V5 largely delivered; V6–V8 partial (pipeline writers landed; outreach
fixture-complete; calendar ICS-only).

### 2c. Plan/scope consistency note

Ann's build table lists invitation-only speaker accounts as "phase two … log
it in the backlog" for *her* deliverable. B26 built that workflow in **CBA
scope** — `docs/plans/backlog.md` records both her quote and the 2026-09-22
owner decision (B26 option B, Q2 = B). No scope violation: ADR-0025 shares only
the matching mechanism, and the new speaker surfaces never touch `exercise_*`
tables or routes. Still standing: Pia/Lisa have not answered — the flag stays
off for real Speakers.

---

## 3. Original SmartMatch platform vs the revamp

Authority for the port: `docs/migration/migration-manifest.yaml` against legacy
`BrooklynD23/Nebiux-Team-IA-West-SmartMatch` @ `bdce024`; authority for current
intent: `docs/product/cba-smart-match-customer-requirements.md`.

| Item | Status |
|------|--------|
| Migration manifest | 18 entries — **6 ADAPT / 5 REPLACE / 7 ARCHIVE**, each with recorded kept/rejected rationale |
| §22 preserves — event browsing, registration, calendar (ICS), role-based permissions, speaker invitation workflow, discovery feed, matching architecture | All implemented (deny-by-default authz; Dashboard; ICS download; invitation workflow now deepened by B26) |
| CBA matching spec (§5–11) | Registry 2.0.0: Industry 30 / Role 25 / Topic 15 / Proximity 30; 20 NAICS sectors; 10 roles; 0–25/25–75/75+ bands; virtual redistribution; neutral score on missing topic; `POST /v1/units/{id}/match-runs` live |
| Roles (§2) | Student / Event Host (`volunteer`) / Speaker Connector (`admin`,`coordinator`) / **Speaker — now a real role post-B26** (was contact-record-only) |
| Pilot posture | Synthetic pilot on GCE VM at `pilot.plated.blog`; `ALLOW_CLOUD_DEPLOY=false`; no live OIDC (A1b), no live send (G4), ICS-only calendar (G5), no real student data (D8 unmet) |
| Speaker capabilities (§14) | **Now exceeds spec** — invitations + engagements + upcoming events + self-service availability/consent, behind flag |
| Known unresolveds (§26) | Virtual redistribution formula, proximity band sub-scores, feedback schema, match-percentage display — all still owner-open |

---

## 4. Timeline position (class-exercise milestones)

| Milestone | Date | Status |
|-----------|------|--------|
| Scope confirmed; 20-row sample due | Sept 18 | Sample **not received** |
| Full 300-row file due | **Sept 25 — tomorrow** | Pending; chase it |
| Matching + factors + tie-break + cap + settings + markers + list table **on the site with full data** | **Oct 2** (8 days) | **At risk** — code done; site and data do not exist |
| Results + lock + comparison + refresh + round 2 + download; Ann runs both sessions | Oct 16 | At risk — gated on coefficients + deploy |
| Problems fixed | Oct 30 | — |
| Practice run w/ Ann, Dr. Lin, volunteers | Week of Nov 9 | — |
| Fall deliverable; Ann's CBACH decision | Nov 20 | — |

---

## 5. Doc drift found

| Finding | Detail |
|---------|--------|
| Local `main` 338 behind | Audit baseline is `origin/main`; the working tree predates the entire B26 merge |
| 09-21 + 09-22 reports uncommitted | `docs/status-report/*.md` and the index update are untracked local files |
| README omits exercise scope | Zero capability-table rows for the second product — drift by omission persists |
| `owner-open-decisions-2026-09-19.md` stale | Items #1–4 decided 2026-09-21, still listed OPEN |
| `backlog.md` lists built items | Coverage notice, results chart, card mockup are built in exercise scope (points counter partial) |
| Stranded fix | `allowedHosts` + hosting-doc gap closure live only as uncommitted diffs on the stale checkout |
| Exercise runbook defect | §9 step 9 single-origin hostname vs step 12 `GET /`→200 — API mounts no SPA; the two-route shape is prose-only in §4 |

---

## 6. Highest-leverage blockers (ordered)

1. **Ann's 300-row dataset** (due 09-25) — unblocks layout, year tie-break, real ingest.
2. **Exercise deploy execution** — commit/rebase the stranded `allowedHosts` fix, fix runbook steps 9/12 (two-route shape), run the checklist.
3. **OQ-CE-03 simulation coefficients** — eight quantities; Chau proposes by Oct 2, Ann confirms.
4. **Cloudflare WAF rule** on the exercise host — only edge protection (OQ-CE-06).
5. **Instructor passcode** (OQ-CE-07) — unset fails closed.
6. **B26 stakeholder gates** — Ann/Pia/Lisa, privacy owner, IA West review, hostname, D5. Code is safely dark until then.
7. **CBA long-leads** — A1b IdP, D8, F5 cloud, W-series registers (OQ-SE-04–08).

---

## 7. Key reference paths

| Purpose | Path |
|---------|------|
| Class-exercise requirements | `docs/product/class-exercise-requirements.md` |
| Class-exercise register | `docs/plans/open-questions/class-exercise-open-questions.md` (OQ-CE-01–13, all OPEN) |
| CBA requirements | `docs/product/cba-smart-match-customer-requirements.md` |
| B26 plan / tracks / ledger | `docs/plans/2026-09-22-b26-self-service-availability-plan.md`, `docs/plans/b26-tracks/`, `docs/b26-ledger:docs/plans/b26-tracks/LEDGER.md` |
| Exercise runbook / compose | `docs/operations/exercise-hosting.md`, `docker-compose.exercise.yml` |
| Exercise code | `python/smartmatch_domain/smartmatch_domain/exercise/`, `routers/exercise_*.py` (14 modules), `pages/exercise/` |
| Speaker portal | `product_scope.py` (`SPEAKER_PORTAL` off), `routers/` speaker + `/v1/me/*`, `pages/speaker/`, ADR-0027 |
| Migration manifest | `docs/migration/migration-manifest.yaml` |
| Prior audits | `2026-09-22-class-exercise-audit-status-report.md`, `2026-09-21-audit-status-report.md` |

---

*End of audit-status report.*
