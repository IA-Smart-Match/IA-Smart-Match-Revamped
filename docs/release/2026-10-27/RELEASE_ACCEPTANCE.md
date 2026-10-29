# Release acceptance — class exercise, 27 October 2026

**Release status: PASS** (decided by the lead session, 2026-10-27 23:20 UTC)

- Public URL: https://exercise.smartmatch.cloud/exercise
- Revision on the VM: `4fc80d02783fa64b2418f379a44f8689080b3907` (deploy run 17, 2026-10-26 06:32 UTC, all jobs green). `main` is at `763e666` (PR #444); not deployed, not tested.
- Report: `SMARTMATCH_TEST_REPORT.pdf` (2 pages; table redone 2026-10-29 with the full Team 6 public run), source `SMARTMATCH_TEST_REPORT.md`.
- Models: lead Claude Opus 5.5; workers A (deploy audit), B (browser workflow) and C (matching) ran as `claude-haiku-5-5` by their own report. Agents D and E were not spawned: no UX defect needed a fix, and the lead wrote the report from the evidence.

## Acceptance matrix

| ID | Status | Evidence |
|---|---|---|
| APP-01 Public URL | PASS | `public/team6-run-2026-10-29.md` (full run, 2026-10-29 05:53–05:57 UTC); `public/02`–`07` screenshots (Team 1, 2026-10-27) |
| APP-02 Release | PASS | VM runs 4fc80d0 (DEPLOYMENT_AUDIT.md §1). Newer main not deployed. |
| APP-03 Setup | PASS | `public/02-team-entry.jpg`; E2E S-01..S-04 |
| APP-04 Round 1 | PASS | `public/03`, `public/04`; E2E R1-01..R1-05 |
| APP-05 Round 1 results | PASS | seat counts sum to 60 in every run |
| APP-06 Round transition | PASS | `public/05`, `public/06` (230 asked, 127 cards, 70→197) |
| APP-07 Round 2 | PASS | `public/07`; E2E R2-01..R2-04 |
| APP-08 Round 2 results | PASS | `public/07-r2-results.jpg` |
| APP-09 Completion | PASS | both rounds "Results run" on the status card |
| APP-10 Stability | PASS | no blocking error in public or local runs |
| MATCH-01 Rules | PASS | MATCHING_VERIFICATION.md claim table |
| MATCH-02 Constraints | PASS | MATCHING_TEST_RESULTS.csv: 60 unique, order/weights/tie checks true |
| MATCH-03 Reproducibility | PASS | run1 = run2, byte-identical CSV under another hash seed |
| MATCH-04 Persistence | PASS | reload keeps run; double send = one run (E2E R1-06, E-07) |
| DOC-01..05 | PASS | PDF 2 pages, inspected; failures listed in §6 |
| REL-01 | PASS | this file |

## Test summary

| Test group | Passed | Failed | Blocked |
|---|---:|---:|---:|
| Deployment runs (Oct 26) | 1 | 2 (fixed by run 17) | 0 |
| Round 1 (2 public + 2 local teams) | 4 | 0 | 0 |
| Round 2 (2 public + 2 local teams) | 4 | 0 | 0 |
| Matching fixture runs | 4 | 0 | 0 |
| Exercise unit / golden tests | 1,440 / 66 | 2 / 0 (local `.env` only) | 0 |
| Front-end tests | 1,271 | 0 | 0 |
| Full workflow (2 public + 2 local) | 4 | 0 | 0 |

## Open issues

| Severity | Issue | Remaining action |
|---|---|---|
| P1 (ops) | Teams 1 and 6 hold test runs on the live site | Clear Team 1 and Team 6 on the instructor page before class |
| P2 | No automated check of the exercise host | Add a separate exercise probe to deploy.yml |
| P2 | Walkthrough recorder lacks team code step | Update `tools/walkthrough` before re-recording |
| P2 | `make setup` fails on Python 3.13 | Pin a 3.11/3.12 interpreter in the Makefile |
| P2 | Documented rollback refuses older commits | Fix deploy-runbook.md rollback steps |
| Info | Write-up §2 "5,000 runs" table not reproducible from repo | Commit its script or drop the table |
