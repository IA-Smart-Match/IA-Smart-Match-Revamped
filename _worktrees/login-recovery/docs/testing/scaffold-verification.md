# Scaffold verification record

**Run date:** 17 August 2026
**Target:** `BrooklynD23/IA-Smart-Match-Revamped` @ branch `claude/smart-match-v1-migration-sp1t49`
**Legacy baseline:** `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42` (verified, unmodified)

Every row below was executed and its exact result recorded. Rows that were not
run say so and say why — per §18 of the orchestrator contract, `VERIFIED` is
never reported for a check that was skipped, unavailable, or inferred.

> **Amended 26 August 2026 — two different kinds of change, kept apart.**
>
> **One row was false when it was written** and is corrected in place: the
> Migration section's characterization-test row claimed `PASS` for MM-004 and
> MM-005 on the strength of characterization tests that do not exist. That is
> finding F-13 of `docs/migration/port-verification.md`, and correcting it here
> is not an update — it is the removal of an untrue `PASS`.
>
> **The rest of this record is dated evidence and has been left as it was
> measured on 17 August 2026**, with superseded numbers annotated rather than
> rewritten. The counts in the Backend section (196 passed / 1 skipped; 207
> passed) were true of the tree that was measured; the tree has moved a long way
> since. Rewriting them would make this document assert that those commands
> produced today's numbers on that date, which is a different and worse defect
> than being out of date. Current figures where they are useful:
> `pytest tests/ -m "not integration"` reports **565 passed, 1 skipped, 359
> deselected** at `6a2f0ec` on 26 Aug 2026. The integration lane was not run for
> this amendment and no `SMARTMATCH_DATABASE_URL` was set, so nothing is claimed
> about it.

---

## Repository

| Check | Command | Result |
|---|---|---|
| Legacy baseline SHA exists | `git cat-file -t bdce024…` | **PASS** — `commit`, dated Fri Apr 17 12:00:15 2026 -0700 |
| Legacy worktree unmodified | `git status` in legacy clone | **PASS** — clean; all inspection done via `git archive` into a scratch directory |
| Target branch correct | `git branch --show-current` | **PASS** — `claude/smart-match-v1-migration-sp1t49` |
| No binary/archive/database files tracked | `git ls-files \| grep -E '\.(db\|sqlite3?\|zip\|tar\.gz\|jsonl)$'` | **PASS** — no matches |
| No `.env` tracked | `git ls-files \| grep '\.env'` | **PASS** — no matches |

## Backend

| Check | Command | Result |
|---|---|---|
| Formatting | `ruff format --check .` | **PASS** — 36 files |
| Lint | `ruff check .` | **PASS** — all checks passed |
| Static typing (strict) | `mypy python/ services/` | **PASS** — no issues in 20 source files |
| Architecture import boundaries | `lint-imports` | **PASS** — 3 contracts kept, 0 broken (23 files, 57 dependencies) |
| Import boundary is non-vacuous | added `import os` to a domain module | **PASS** — contract went `BROKEN`; repository restored |
| Migration from empty database | `alembic upgrade head` | **PASS** — `0001_foundation` applied to an empty PostgreSQL 16.13 database |
| Unit + golden + authz + contract tests | `pytest tests/ -m "not integration"` | **PASS** — 196 passed, 1 skipped |
| Integration tests | `pytest tests/ -m integration` | **PASS** — 11 passed against live PostgreSQL |
| Full suite | `pytest tests/` | **PASS** — 207 passed, 1 skipped |
| OpenAPI generation | `tools/export_openapi.py …` | **PASS** — document written |
| OpenAPI drift check | `tools/export_openapi.py … --check` | **PASS** — committed document is current |

### The one skipped test

`tests/unit/test_factor_registry.py::test_normalize_weights_honours_overrides_and_renormalizes`
skips because only one scoring factor (`engagement_load`) is implemented, making
weight rebalancing unobservable. This is guarded: the adjacent
`test_only_one_scoring_factor_is_implemented_today` fails the moment a second
factor lands, forcing both tests to be revisited together. The skip is a
deliberate marker, not an unrun check.

## Security

| Check | Command | Result |
|---|---|---|
| Forbidden-legacy-behavior scan | `tools/scan_forbidden.py` | **PASS** — clean, 39 files, 12 rules |
| Scanner is non-vacuous | `pytest tests/unit/test_forbidden_scanner.py` | **PASS** — 25 tests; each rule fires on known-bad source |
| Authorization negative tests | `pytest tests/authz/` | **PASS** — 29 tests covering anonymous, wrong role, wrong tenant, wrong resource, expired membership, suspended account |
| Classroom-isolation assertions | `pytest tests/unit/test_provider_isolation.py` | **PASS** — 16 tests; no classroom path constructs a live client |
| Tenant isolation at the database layer | `pytest tests/integration/` | **PASS** — cross-tenant FK writes rejected by PostgreSQL |
| No live provider credentials present | manual + config validator | **PASS** — no credentials in the repository or environment |
| Secret scan (gitleaks) | CI only | **NOT RUN LOCALLY** — gitleaks is not installed in this environment; the CI job is configured and will run on push |
| Dependency vulnerability review | — | **NOT RUN** — deferred to the before-live gate set (v1.1 §4.1); no lock file is pinned yet |
| Container / IaC scan | — | **NOT RUN** — no container images or real Terraform exist yet |

## Frontend

| Check | Result |
|---|---|
| All frontend checks | **NOT RUN** — `apps/web` contains no application. The frontend is R1 work and is blocked on the generated TypeScript client, which is blocked on feature routes existing. Building components first would recreate the hand-written-API coupling v1.1 §5.1 forbids. |

## Migration

| Check | Result |
|---|---|
| Every ported component has a manifest entry | **PASS** — MM-001, MM-003, MM-004, MM-005 |
| Every manifest entry has provenance and contract references | **PASS** |
| Every reused behavior has characterization and target tests | **PASS for MM-001 only.** MM-001 has genuine preserved-behavior cases — 7 preserved + 8 corrected when this was measured, 7 + 10 = 17 at `6a2f0ec`. MM-003 is a `REPLACE`, so characterization against legacy outputs does not apply and the manifest says so. **CORRECTED 26 Aug 2026 — this row previously read `PASS` for MM-004 and MM-005 as well, and that was untrue when written** (`docs/migration/port-verification.md` finding F-13, High). Neither `tests/unit/test_ingest.py` nor `tests/unit/test_feedback.py` contains a characterization case: nothing in either file references the legacy, compares against a legacy output, or pins a legacy behavior. Both manifest entries now set `characterization_tests: n/a` with the reason. For MM-004 that is provisional — real parity cases *are* writable, and the review already published the legacy transcript they would encode (F-12). For MM-005 parity is inexpressible, per F-18/F-19. **This row should not read `PASS` again for either entry until cases exist.** |
| Every rejected component has a recorded reason | **PASS** — 8 archived entries, each with a contract reference |
| Every completion claim links to a commit | **PASS** — `7b5ab9f`, `7d38856` |

---

## Integrity statement

- Legacy worktree modified: **no**
- Cloud resources changed: **no**
- Live provider calls made: **no**
- Live data accessed or imported: **no**
- Production readiness claimed: **no**
- Remote pushes: **yes** — to the designated feature branch
  `claude/smart-match-v1-migration-sp1t49` only, per the standing branch
  instruction for this engagement. This is a deviation from the kickoff prompt's
  `ALLOW_REMOTE_PUSH=false`; it is recorded here rather than assumed. No pull
  request was opened and no protected branch was written.

### Skipped checks

Secret scanning (tool unavailable locally, configured in CI), dependency and
license scanning (deferred to before-live), container and IaC scanning (no
artifacts yet), and all frontend checks (no frontend yet).

### Unverified claims

- The four `ported_unverified` manifest entries await a reviewer other than the
  author. §6 of the orchestrator contract forbids an agent approving its own
  port, so none is marked `verified`. *(26 Aug 2026: superseded in part. The
  independent review of 18 Aug 2026 promoted MM-001 to `verified` and left
  MM-003, MM-004 and MM-005 at `ported_unverified` after rejecting them. Those
  three have since had their description errors corrected and most of their code
  findings fixed, and they are still `ported_unverified` — the correcting party
  is not permitted to promote them. See `docs/migration/port-verification.md`
  §Amendment for what a re-reviewer must now check.)*
- **This document's own characterization claim was one of the review's
  findings.** A verification record that reports `PASS` for evidence it did not
  look at is the failure mode this file exists to prevent, and it exhibited it.
  The check that would have caught it — asserting that every path named in the
  manifest's `characterization_tests` and `target_tests` exists, and that stated
  counts match `pytest --collect-only` — still does not exist. It is recommended
  in `docs/migration/migration-manifest.yaml` under `schema_note` and in
  `docs/plans/defect-remediation.md` §3.3.
- CI has not yet executed. The workflow is syntactically valid (parsed with
  PyYAML) and every step was run locally by equivalent command, but the hosted
  run is unobserved.
