# Docs Consolidation Plan — 2026-09-26

Produced by a 5-partition audit of all 333 tracked files under `docs/`
(W1 plans top-level, W2 plans subdirs + status-report, W3 design,
W4 architecture/decisions/decision-packets, W5 ops/migration/product/etc.).

**Problem:** agents entering `docs/` today must wade through ~334 files where
dated process artifacts (executed plans, orchestrator prompts, status
snapshots, mock-up rounds, verification evidence) outnumber live reference
docs ~1.2:1. Context windows flood before decisions are found.

**Goal:** an agent answers "what was decided / how does it work / what do I do"
from ≤3 files: `INDEX.md` → one canonical doc → one register.

---

## Proposed structure

```
docs/
  INDEX.md                      # NEW — ≤150-line router: task → exact path
  README.md                     # existing — repoint to INDEX
  architecture/                 # canonical core — stays (minus 7 files → archive)
  decisions/                    # stays + NEW INDEX.md (decision spine)
  decision-packets/             # stays (all still-open framings) minus g1 packet
  plans/                        # keep ~14 live files; ~102 → archive/plans/
  plans/open-questions/         # STAYS PUT — these are the live OQ registers
  design/                       # keep DESIGN.md + experiments.md + assets/svg;
                                #   prompts/, mockups/, generated/ → archive
  operations/ migration/ security/ product/ pilot-data/ testing/
  agents/ agent-memory/ superpowers/ ui/ prototypes/
                                # keep current; dated evidence → archive
  archive/                      # NEW — cold storage, mirrors source paths
    INDEX.md                    # NEW — ID-namespace map (see below)
    plans/…                     # archive/<original-relative-path> layout
```

Moving to `archive/<same-relative-path>` keeps every move mechanical:
`docs/plans/x.md` → `docs/archive/plans/x.md`. Links that pointed at moved
files get rewritten `plans/x` → `archive/plans/x` (scripted pass + verify).

## File disposition (from audit)

| Bucket | Count | Examples |
|---|---|---|
| Keep visible | ~150 | all of `decisions/`, `architecture/` (minus 7), all OQ registers, runbooks, `pilot-data/` fixtures, `DESIGN.md`, canonical plans |
| Archive | ~180 | all 16 `b26-tracks`, all 20 `plans/prompts|design/prompts`, `prep/`, `workshops` packets, dated `2026-08/09-*` plans, status-report 09-02, superpowers plans/specs (12), testing evidence (3), security evidence (3), migration run records (2), design mockups/generated (33 assets) |
| Delete/empty | 1 | `docs/stakeholder deliverable/` (empty dir — remove) |

## NEVER MOVE (code references them by path)

- `pilot-data/columns.yaml`, `rewards-catalog-worksheet.md`, `fixtures/*` —
  read by worker config, `seed_pilot_*`, `verify_pilot_dataset`,
  `test_column_contract.py`, `test_gate_decision_artifacts.py`
- `agent-memory/` — `tools/agent_memory_check.py` enforces via `make check`
- `architecture/decisions/` — `test_adr_index.py` asserts its README rows
- `design/class-exercise/assets/svg/*` — consumed by the build

## INDEX.md design (the context-flood fix)

Sections, each ≤15 rows of `question → path`:
1. **Orientation** — topology, command-path, domain-model, GLOSSARY
2. **Decisions** — ADR index, `decisions/INDEX.md`, OQ registers
3. **Build here** — agents/architecture-implementation-guide, MODULE_BOUNDARIES, DEPENDENCY_RULES
4. **Operate** — vm-deploy, deploy-runbook, containers, exercise-hosting
5. **Product** — CBA requirements, class-exercise requirements, capability policy
6. **Now in flight** — B26 plan, registry-3.0 gate, PR #239
7. **Archive** — one line: `archive/INDEX.md` for historical/ID lookup

Rule of use (goes in INDEX.md header + AGENTS.md): read INDEX.md first;
never bulk-read `plans/` or `archive/`; cite decision IDs, not file contents.

## decisions/INDEX.md (decision spine)

One table, every decision surface:
- 27 ADRs (seed from CI-gated `architecture/decisions/README.md`)
- `decisions/*` records (D/D6/P9/R3/G3/A1b…)
- OQ registers: `OQ-CBA-*` (66 rows, ~36 open), `OQ-CE-*` (16, one open:
  CE-06 rate-limit), `OQ-SE/SC-*` (35 open), `OQ-A1b`, `OQ-S2`, `OQ-E`,
  `OQ-F5`, `OQ-101-104`, `OQ-R4-*` — with OPEN-count column per register
- Open gates: A1b worksheet, registry-3.0.0 flip (ADR-0027), SPEAKER_PORTAL
  turn-on (T6b-1 C5), MM-A09 legacy PII (CANNOT CLOSE), F-28 vendoring

## archive/INDEX.md (ID-namespace preservation)

Before moves, record where every ID family lives so archived IDs stay
findable: CP-*, P1–P9, D1–D9, F1–F13, F-1…F-30, J8–J17, M1–M10, H01–H21,
B01–B42, CBA-* tracks, B26-T*, MM-*, R-*, T-*, S-*, G1–G5, W1–W4.

## Known issues to fix during execution

1. **OQ-ID collision:** `calendar-deferred.md` and `r4-outreach-deferred.md`
   both use bare `OQ-001…009` for different questions → qualify as
   OQ-CAL-* / OQ-R4-* in the index (files untouched or renamed IDs).
2. `agents/feature-implementation-template.md` says migration head `0033`;
   actual `0043`. Fix line.
3. `status-report/README.md` "latest" pointer → update when wip reports land.
4. Stage-1 architecture docs describe 4 contracts/4 root packages; reality
   is 7/5 (`pyproject.toml`). Add pinned-baseline banner to
   `CURRENT_ARCHITECTURE_AUDIT.md`, `DEPENDENCY_RULES.md`,
   `MODULE_BOUNDARIES.md`, `ARCHITECTURE_PRINCIPLES.md` — do NOT rewrite counts.
5. Stale status lines: `student-recommender-decision-record.md` (header
   "DRAFT" vs accepted content), `student-recommender-contracts.md`
   (ADR-0024 now Accepted). Fix two header lines.
6. **Secret:** `plans/2026-09-10-pr154-closeout-recovery.md` line 33 contains
   test password `Testing123!!` — scrub on archive move (replace with
   `[redacted test credential]`).
7. `class-exercise-decisions-2026-09-25.md` D-records + `DESIGN.md §11`
   six rulings = the two anchor decision spots for the exercise feature —
   INDEX must point at both.

## Wip-branch docs (on `wip/local-main-scratch-2026-09-26`)

19 files incl. Sep-19→24 orchestrator prompts (9), status reports (3),
`class-exercise-process.html`, LICENSE, `test_data/`, and 4 modified files.
When consolidation executes: restore prompts + status reports into
`archive/plans/prompts/` and `status-report/` respectively; LICENSE and the
vite/exercise-hosting edits are real candidates for a proper commit.

## Execution checklist (when approved)

1. `git checkout -b docs/consolidation-2026-09-26`
2. `git mv` the ~180 archive files → `docs/archive/<same path>`
3. Write `docs/INDEX.md`, `docs/decisions/INDEX.md`, `docs/archive/INDEX.md`
4. Fix items 1–6 above; scrub the test password; remove empty dir
5. Rewrite inbound links (grep for `](.*plans/` etc. in kept files)
6. Restore wip prompts/status-reports into their archive homes
7. Verify: `make check` (agent-memory + ADR index tests must stay green),
   markdown link sweep
8. Commit; PR or keep local per workflow
