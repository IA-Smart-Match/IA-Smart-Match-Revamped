# Review: `friday-deliverable-828` and PR #7

**Reviewed:** 2026-08-28  
**Local HEAD:** `17fb0d9`  
**PR/remote head:** `6fcb03a`  
**Verdict:** Not merge-ready as a combined branch. Fix the forbidden-scanner
regression and close the two frontend fail-closed/accountable-number gaps below,
then obtain green PostgreSQL, OpenAPI, and web CI evidence.

## PR #7 status versus local HEAD

- Local branch `friday-deliverable-828` is ten commits ahead of
  `origin/friday-deliverable-828`.
- `refs/pull/7/head` and the remote branch both resolve to `6fcb03a`; local HEAD
  is `04ef53c`. The Wave 3C, Fix #7A, opportunities-unknown, G1-gate, and
  stakeholder-prep commits are therefore not in PR #7.
- The working tree began clean except for untracked `.claude/`.
- GitHub CLI is not installed in this environment, and the private GitHub API
  returned 404 without authenticated API access. PR title/body/state and check
  rollup could not be verified. No push or merge was attempted.
- The latest local-only commit, `17fb0d9`, adds a G1/G3/D6 remedy plan. Its
  explicit rule “Do not expose a score, rank, match run, or matching UI before
  G1” reinforces blocking issue 3; it does not resolve that existing UI.
- Derived PR URL:
  <https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/7>

## Blocking issues

### 1. The local branch fails its forbidden-behavior gate

`python -m pytest tests -m "not integration"` reported 893 passed, 2 skipped,
and 5 failed. One failure is repository content, not the unpinned local Python
environment:

- `docs/plans/remaining-engineering-brief.md:435` contains the forbidden
  `POST /auth/mock-login` literal.
- `docs/plans/remaining-engineering-implementation-plan.md:180` contains the
  forbidden `mock-login` literal.

`tests/unit/test_forbidden_scanner.py::test_repository_scan_is_clean` therefore
fails. These documents are among the ten local-only commits, so PR #7 does not
currently exercise this failure; adding the local commits unchanged would make
the isolation gate red.

### 2. Dashboard failures are rendered as measured zeroes

In `Dashboard.tsx`, failed assignment and feedback requests are converted to
empty summaries (`setCalendarAssignments([])` and
`setFeedbackStats(emptyFeedbackStatsSummary())`). The same render then shows
`0%` average fatigue, zero “Rest Recommended,” `0%` acceptance, zero pain, and
`0%` membership interest.

Those values mean “request unavailable,” not measured zero. This directly
contradicts ADR-0011 rule 1 and the implementation plan’s standing rule that
missing evidence stays unknown with a reason. The warning banner does not make
the numeric claims accountable. This regression is in local-only Wave 3C work.

### 3. G1 fail-closed matching is not enforced across the mounted frontend

The new API/OpenAPI correctly exposes no match/score/rank route while
`REGISTRY_STATUS == "proposed"`, but the shipped legacy frontend still:

- mounts `/ai-matching`;
- calls `/api/matching/rank`, `/api/matching/rank-for-course`, and
  `/api/matching/score`;
- automatically requests rankings from the dashboard; and
- renders match scores and factor scores.

Against the current API these calls fail with 404, but the gate is not attached
to this legacy `/api` client path. Pointing the proxy at any backend that still
implements those routes re-enables user-visible scoring without
`assert_registry_approved()`. The new fail-closed test checks only OpenAPI paths,
so it does not catch this alternate surface.

## Non-blocking issues

- Migration `0009` calls `point_ledger_entry` append-only, but the database does
  not prevent `UPDATE`/`DELETE`; absence of bookkeeping columns is not an
  append-only control. It also permits repeated positive credits against one
  `source_attendance_id`. Define and enforce the write-path/idempotency and
  reversal invariants before S7 can issue points.
- `reward_item.funded` is `NOT NULL` but has a server default of `false`.
  Fail-closed behavior is safe, but comments claiming every insert must supply
  `funded` explicitly are inaccurate.
- `git diff --check` reports Markdown trailing whitespace and an extra blank
  line at EOF in the local-only planning/prep documents.
- Source-contract tests for Fix #7A and opportunities are narrow string scans.
  They are useful migration guards, but they do not replace browser tests for
  route behavior, session creation, and disabled sign-in.
- The frontend request seam still contains many legacy numeric coercions from
  missing values to zero. They predate the local nine commits, but remain
  residual ADR-0011 debt and should not be treated as approved by Wave 3C.

## Residual stakeholder and human decisions

- Metrics aggregate and drill-down authorization remain intentionally ungated
  for any active unit membership. This is recorded policy, not a review bug.
  Product/security still must decide aggregate and row-level roles under
  ADR-0014 before changing it.
- A1b must provide real institutional identity. Until then, direct portal pages
  still read `sessionStorage["iaw_session"]` and fall back to identities such as
  `stu-001`, `coord-001`, and `shana-demarinis`. Fix #7A correctly removes the
  caller-chosen login UI but does not close this residual risk.
- G1 approval is still required for factors, weights, and golden outputs.
- G3 and its crawler threat-model/allowlist/evaluation decisions remain open.
- D6/D7 reward ownership, funding, and calibration remain open.
- Dr. Wang/privacy decisions remain open for `board_role`, public URL, and
  published contacts.
- The canonical opportunities definition and S12 owning evidence query remain
  open. Local `df4e218` correctly shows unknown instead of fabricated rows.

## What CI must still prove

1. The isolation job passes `tools/scan_forbidden.py` after all ten local
   commits are included.
2. PostgreSQL 16 applies migrations `0008` and `0009` from an empty database and
   runs the full integration suite, including tenant isolation, constraints,
   inline import execution, and executor transaction behavior.
3. OpenAPI regeneration/check passes using the pinned dependency set. A local
   check reported stale output under mismatched global FastAPI/Pydantic
   versions, so that result is not authoritative.
4. The web job completes locked `npm ci`, TypeScript checking, Vite build, and
   audit. Local `npm ci` was blocked by a Windows `EACCES` in `node_modules`, so
   no local clean-build evidence was obtained.
5. PR #7’s actual status-check rollup is green. It could not be queried here
   because `gh` is unavailable.

`make check` itself could not run because GNU Make and the repository virtual
environment are absent. The direct global-Python run is useful evidence but not
a substitute for the pinned local gate, and it excludes integration tests by
design.
