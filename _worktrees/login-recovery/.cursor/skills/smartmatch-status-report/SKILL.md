---
name: smartmatch-status-report
description: >-
  Produces a dated pilot-readiness audit-status report for IA SmartMatch
  Revamped — foundation vs pilot product, self-hosted local vs cloud deploy,
  P1–P9 gates, and blocker inventory. Use when the user asks for a repo
  status report, pilot readiness, audit status, where we are vs a pilot,
  deployment readiness, or a report like the status-report session.
---

# SmartMatch repository status report

Produce an honest **audit-status report** for this repository. The report
summarizes pilot readiness (self-hosted and cloud), not production-readiness
claims.

## When to run

- User asks for repo status, pilot readiness, audit report, or "where are we"
- User wants comparison: local self-host vs cloud pilot
- User asks to refresh or save a status report under `docs/status-report/`

## Non-negotiables

- **Never declare production readiness** — nothing is deployed; standing
  constraints forbid live providers/data (`ALLOW_CLOUD_DEPLOY=false`, etc.)
- **Distinguish** foundation scaffold (strong) from pilot product (mostly gated)
- **Unknown ≠ zero** — pipeline metrics may be honest-unknown until S12
- **Matching fails closed** until G1/D1 — do not imply scores work
- Reports **decide nothing** and **fill no owner fields**

## Workflow

### 1. Load authoritative docs (read first)

| Purpose | Path |
|---------|------|
| Capability truth table | `README.md` |
| Blocker index | `docs/decisions/2026-08-31-session-ratification.md` |
| V1–V8 continuation | `docs/plans/2026-08-31-ratification-and-implementation-report.md` |
| Plan portfolio P1–P9 | `docs/plans/2026-08-28-plan-portfolio-index.md` |
| Blocked-work register | `docs/plans/prep/blocked-work-register-830.md` |
| Pilot decisions D1–D9 | `docs/decisions/pilot-decisions.md` |
| Deploy posture | `docs/operations/deploy-runbook.md`, `docs/operations/containers.md` |
| Prior status reports | `docs/status-report/README.md` |

### 2. Verify live facts (do not trust stale docs alone)

Re-check these against the tree; README and backlog files can lag code:

| Fact | How to verify |
|------|----------------|
| Migration head | `db/migrations/versions/` — count and latest revision id |
| J10 command payload | Migration `0005`; `job.payload` in worker handlers |
| OpenAPI operation count | `contracts/openapi/smartmatch.json` paths |
| Test collection | `pytest tests/ --collect-only -q` if environment allows |
| Factor registry gate | `python/smartmatch_domain/smartmatch_domain/factor_registry.py` — `REGISTRY_STATUS` |
| Engagement schema vs behavior | `0009_engagement_schema.py` exists; APIs in `routers/engagement.py` empty? |
| Frontend hold | `apps/web/DESIGN.md` |

Optional: launch one **explore** subagent for deploy/infra and one for
features if the tree changed significantly since the last report.

### 3. Write the report

Use the structure in [report-template.md](report-template.md). Include:

- Executive summary table (5 dimensions)
- Release train + gates G1–G5
- Implemented / partial / blocked matrices
- Self-hosted local dev vs pilot-in-a-box gaps
- Cloud intended vs actual (GCP, Terraform F5, CI images, no push)
- P1–P9 + V1–V8 status
- Pilot readiness checklist (yes/no/partial)
- Highest-leverage human blockers (ordered) + engineering backlog (J8, J9, A1b, S12, M1–M10, F5, W-series)
- Local vs cloud comparison table
- Key file index

Call out **doc-sync drift** when README or `remaining-foundation-r1-work.md`
contradicts verified code (e.g. J10 closed).

### 4. Save to repo (when user asks to persist or "like this session")

1. Create `docs/status-report/YYYY-MM-DD-audit-status-report.md` (today's date)
2. Append a row to `docs/status-report/README.md` index table
3. Do **not** rewrite older reports — preserve history

### 5. Deliver to user

- Link the new file path if written
- Lead with bottom-line verdict, then sections
- Keep proportional length; use tables for matrices

## Pilot scope reference

A **functional pilot** minimally needs: institutional sign-in (P2), pilot
import with `columns.yaml` wired, trustworthy matching (G1), canonical
opportunities metric (P8/S12), honest coordinator metrics (P1), optional
rewards (D6/D7), optional crawler (G3+R3), D8 before real student data,
and either new frontend (D-0) or API-only narrow scope.

## Example user prompts

- "Status report on the repo"
- "Where are we vs a self-hosted pilot?"
- "Audit readiness for cloud deploy"
- "Save today's status report to docs"

## Additional resources

- Latest saved report: `docs/status-report/` (see README index)
- Historical point-in-time: `docs/plans/status-report-830.md` (superseded for blockers by 31 Aug ratification)
