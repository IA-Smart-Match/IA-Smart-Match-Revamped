# Status reports

Point-in-time **audit-status** snapshots of repository readiness against a
fully functional pilot (self-hosted or cloud). Each report is dated and
preserved unchanged when superseded — update the index below, do not rewrite
history.

**Latest report (as of 2026-09-04):**
[2026-09-04-audit-status-report.md](2026-09-04-audit-status-report.md)

**Post-report work not reflected in that audit.** The 09-04 report is a snapshot
of the tree on 2026-09-04 and is preserved unchanged, so its figures are now
behind in ways a reader should know about before quoting them:

- It records **15 migrations, head `0015_remove_ledger_reversal`**. The tree now
  has **36** revisions, head `0036_host_organization`.
- It records **11 OpenAPI paths / 11 operations**. `contracts/openapi/smartmatch.json`
  now describes **66 paths / 83 operations**, all 83 with an `operationId`.
- It records the G1 registry with **no scoring engine**. The registry is now
  `2.0.0-approved-oq-cba-004` with four implemented CBA factors, and
  `POST /v1/units/{unit_id}/match-runs` composes them through
  `rank_cba_candidates`.
- It predates the CBA legacy-frontend surfaces at `/coordinator-portal/match-runs`,
  `/coordinator-portal/invitations`, and `/volunteer-portal/confirmed-speaker`.

None of that changes the report's posture line — not production-ready, not
deployed, synthetic data only. Request a fresh report via the skill below when
the gap needs auditing rather than listing.

For current navigation, use the [planning index](../plans/README.md), the
[canonical student-engagement program](../plans/2026-09-14-student-engagement-program-plan.md),
and its [open-question register](../plans/open-questions/student-engagement-deferred.md).
Those 2026-09-14 artifacts are documentation-only planning authority, not a
fresh readiness report and not evidence that their target capabilities exist.

| Date | Report | Notes |
|------|--------|-------|
| 2026-09-04 | [2026-09-04-audit-status-report.md](2026-09-04-audit-status-report.md) | Pilot readiness audit, self-hosted vs cloud; supersedes 09-02. Predates the CBA matching pivot |
| 2026-09-02 | [2026-09-02-audit-status-report.md](2026-09-02-audit-status-report.md) | Consolidated audit; third pass (review API, O3 binding, compose scheduler, CI smoke) |

**Historical blocker index for these dated reports:**
[`2026-08-31-session-ratification.md`](../decisions/2026-08-31-session-ratification.md).
For current blocker navigation, use the [planning index](../plans/README.md) and
the canonical registers it links, including the
[student-engagement register](../plans/open-questions/student-engagement-deferred.md).

**How to request a fresh report:** Ask Cursor to use the **smartmatch-status-report** skill (project skill in `.cursor/skills/smartmatch-status-report/`).
