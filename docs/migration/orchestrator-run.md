# SmartMatch Migration Run

## Run identity

- **Run ID:** revamp-foundation-2026-08-17
- **Started:** 17 August 2026
- **Architecture contract version:** v1.1 (17 August 2026)
- **Legacy remote:** `https://github.com/BrooklynD23/Nebiux-Team-IA-West-SmartMatch`
- **Legacy baseline SHA:** `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42` — **verified**, HEAD of legacy `main`, dated Fri Apr 17 12:00:15 2026 -0700
- **Target:** `BrooklynD23/IA-Smart-Match-Revamped`
- **Target branch:** `claude/smart-match-v1-migration-sp1t49`
- **Target state at start:** empty repository, no commits

### Authority

| Authorization | Configured | Actual |
|---|---|---|
| Remote push | Kickoff prompt says `false` | **Yes, to the designated feature branch only** — see deviation below |
| Cloud deploy | `false` | No |
| Live providers | `false` | No |
| Live data | `false` | No |
| Pull request | Not authorized | None opened |

**Recorded deviation.** The kickoff prompt sets `ALLOW_REMOTE_PUSH=false`. The
standing branch instruction for this engagement requires development, commits,
and a push to `claude/smart-match-v1-migration-sp1t49`. The standing instruction
governs, and the push was made to that feature branch only — no protected branch
was written and no pull request was opened. Recorded here rather than assumed,
per §4 of the orchestrator contract.

---

## Gate status

| Gate | Status | Evidence | Blocking findings |
|---|---|---|---|
| Preflight | `VERIFIED` | Baseline SHA verified; target confirmed empty; legacy worktree clean | None |
| Architecture review | `VERIFIED` | `docs/architecture/review/contract-findings.md` — 13 consistency checks, 6 findings | None structural |
| Legacy inventory | `VERIFIED` | 745 tracked files surveyed; 44 endpoints reconciled mechanically | None |
| Foundation scaffold | `VERIFIED` | 207 tests pass, 3 import contracts kept, migration applies from empty | None |
| Selective ports | `READY_FOR_REVIEW` | 4 entries at `ported_unverified` | Awaiting independent reviewer (F3) |
| Integration verification | `VERIFIED` | `docs/testing/scaffold-verification.md` | None |

`READY_FOR_REVIEW` rather than `VERIFIED` for the ports is deliberate: §6 of the
orchestrator contract forbids an agent approving its own port.

---

## Method

The instruction under evaluation was whether to install the legacy repository and
copy the fitting files across. That method was **rejected**, per §7 of the
orchestrator contract ("Meaning of cherry-pick"). Copying the legacy tree carries
forward the demo architecture v1.1 exists to replace — caller-selected identity,
SQLite and CSV business writes, module-level authoritative state, and demo-mode
fallbacks.

The method used instead was **characterization-first selective porting**:

1. Scaffold the target around the accepted contracts, with no legacy feature code.
2. For each candidate, write the manifest entry first.
3. Write characterization tests capturing the behavior worth keeping.
4. Reimplement the smallest useful unit against target interfaces.
5. Verify, scan, and commit separately with provenance trailers.

No file was copied from the legacy repository. The legacy was read through
`git archive` into a scratch directory and never modified.

---

## Architecture findings

| ID | Severity | Area | Finding | Owner |
|---|---|---|---|---|
| F-001 | `BLOCKER` (matching slice) | Matching | Registry declares 9 factors, engine computes 7; max attainable score is 0.90, not 1.00 | Program owner (gate G1) |
| F-002 | `DOCUMENTATION` | API | v1.1 route facts verified correct — all 44 endpoints reconcile | — |
| F-003 | `REQUIRED_BEFORE_LIVE` | ICS | Fabricated dates, false UTC, no line folding | Resolved in MM-001 |
| F-004 | `REQUIRED_BEFORE_LIVE` | Consent | No barrier between research evidence and send eligibility | Resolved in `smartmatch_domain.consent` |
| F-005 | `DEFERRED_WITH_TRIGGER` | Coordination | Process-local job state; incorrect on multi-instance Cloud Run | Resolved by schema; dispatcher is R1 |
| F-006 | `DOCUMENTATION` | Contract | 8 open decisions carried forward | Various, none block Foundation |

**F-001 is the substantive finding.** v1.1 flagged a "6/8/9 factor contradiction"
as a documentation problem to resolve. Measurement showed it is a correctness
defect: `_normalize_weights` divides by the sum of all nine declared weights while
`compute_match_score` sums only the seven it computes, so the weight mass of
`event_urgency` and `coverage_diversity` is silently discarded and every score in
the stakeholder demo was deflated by up to 10%.

---

## Port summary

| Manifest ID | Legacy symbol | Disposition | Target symbol | Tests | Status |
|---|---|---|---|---|---|
| MM-001 | `ics_generator.generate_ics` | ADAPT | `smartmatch_domain.ics` | 15 golden | `ported_unverified` |
| MM-002 | `matching.compute_match_score` | ADAPT | registry proposal only | 17 | `blocked_contract` |
| MM-003 | `factors.volunteer_fatigue` | REPLACE | `smartmatch_domain.eli` | 18 | `ported_unverified` |
| MM-004 | `data_loader._validate_columns` | ADAPT | `smartmatch_domain.ingest` | 13 | `ported_unverified` |
| MM-005 | `feedback.acceptance` | ADAPT | `smartmatch_domain.feedback` | 16 | `ported_unverified` |
| MM-A01…A08 | mock login, runtime state, demo mode, local DBs, Streamlit, voice, agents, scraper | ARCHIVE / REPLACE | — | — | `archived` |
| MM-F01, F02 | frontend components, QR helpers | ADAPT | — | — | `inventoried` |

By disposition: 4 ADAPT, 1 REPLACE ported, 8 archived, 2 inventoried for later,
1 blocked.

---

## Verification

| Check | Result |
|---|---|
| `ruff format --check .` | PASS — 36 files |
| `ruff check .` | PASS |
| `mypy python/ services/` (strict) | PASS — 20 files |
| `lint-imports` | PASS — 3 kept, 0 broken |
| Import boundary non-vacuous | PASS — deliberate violation reported `BROKEN` |
| `alembic upgrade head` from empty | PASS — PostgreSQL 16.13 |
| `pytest tests/` | PASS — 207 passed, 1 skipped |
| `tools/scan_forbidden.py` | PASS — clean, 48 files, 12 rules |
| Scanner non-vacuous | PASS — 25 self-tests |
| OpenAPI drift check | PASS |

Checks not run, and why: secret scanning (gitleaks unavailable locally; CI job
configured), dependency and license scanning (deferred to before-live; blocked on
dependency pinning), container and IaC scanning (no artifacts), all frontend
checks (no frontend). Detail in `docs/testing/scaffold-verification.md`.

---

## Integrity statement

- Legacy worktree modified: **no**
- Cloud resources changed: **no**
- Live provider calls made: **no**
- Live data accessed or imported: **no**
- Pull request opened: **no**
- Production readiness claimed: **no**
- Remote changes: **feature branch only**, per the recorded deviation above

### Unverified claims

- Four manifest entries await an independent reviewer.
- CI has not executed. The workflow parses and every step was run locally by
  equivalent command, but the hosted run is unobserved.

### Corrections made during the run

Two errors were caught by verification rather than shipped, both worth recording
because they show the gates working:

1. A fabricated PostgreSQL image digest in the CI workflow, written from memory
   and replaced with the digest resolved from the registry. The three GitHub
   Action SHAs were also written from memory but verified correct against
   upstream.
2. A gap in the scanner's hard-coded-credential rule, which matched
   `api_key = "…"` but not `"api_key": "…"` — the quoted form being how
   credentials are most often actually committed. Found by the scanner's own
   self-test.
