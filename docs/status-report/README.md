# Status reports

Point-in-time **audit-status** snapshots of repository readiness against a
fully functional pilot (self-hosted or cloud). Each report is dated and
preserved unchanged when superseded — update the index below, do not rewrite
history.

**Latest report (as of 2026-09-24):**
[2026-09-24-audit-status-report.md](2026-09-24-audit-status-report.md)

**Latest scoped report:** [2026-09-22-class-exercise-audit-status-report.md](2026-09-22-class-exercise-audit-status-report.md)
audits the `class_exercise` module against Ann Wang's build table only. The
09-24 report supersedes the 09-21 report for whole-repo readiness and folds the
09-22 exercise findings into the merged-B26 baseline (exercise code unchanged
since — its blocker list still applies verbatim).

**Post-report work not reflected in the 09-04 audit.** That report is preserved
unchanged; the 09-24 report supersedes it for current navigation. Major deltas
since 09-04 include CBA matching over HTTP, 41 migrations (exercise + speaker
availability/portal/cancellation/batch-request tables), the `class_exercise`
product scope, the fully merged B26 speaker self-service wave (`SPEAKER_PORTAL`
off, registry 3.0.0 proposed), pipeline stage writers, and the owner-open-
decisions queue for the Spring 2027 exercise — see the latest report for detail.

For current navigation, use the [planning index](../plans/README.md), the
[canonical student-engagement program](../plans/2026-09-14-student-engagement-program-plan.md),
and its [open-question register](../plans/open-questions/student-engagement-deferred.md).
Those 2026-09-14 artifacts are documentation-only planning authority, not a
fresh readiness report and not evidence that their target capabilities exist.

| Date | Report | Notes |
|------|--------|-------|
| 2026-09-24 | [2026-09-24-audit-status-report.md](2026-09-24-audit-status-report.md) | Whole-repo audit on `origin/main` @ `3f183277`: B26 wave fully merged (41 migrations, head `0041`; registry 3.0.0 proposed, SPEAKER_PORTAL off); class exercise unchanged vs 09-22 — dataset due 09-25, deploy unexecuted; supersedes 09-21 |
| 2026-09-22 | [2026-09-22-class-exercise-audit-status-report.md](2026-09-22-class-exercise-audit-status-report.md) | Class-exercise module audit vs Ann's build table: code ~90% done, dataset absent, deploy unexecuted, results gated on OQ-CE-03; scoped — does not supersede 09-21 for whole-repo readiness |
| 2026-09-21 | [2026-09-21-audit-status-report.md](2026-09-21-audit-status-report.md) | CBA pivot + class-exercise module, Supabase ticket, owner-open-decisions, branch posture; supersedes 09-04 for navigation |
| 2026-09-04 | [2026-09-04-audit-status-report.md](2026-09-04-audit-status-report.md) | Pilot readiness audit, self-hosted vs cloud; supersedes 09-02. Predates the CBA matching pivot |
| 2026-09-02 | [2026-09-02-audit-status-report.md](../archive/status-report/2026-09-02-audit-status-report.md) | Consolidated audit; third pass (review API, O3 binding, compose scheduler, CI smoke) |

**Historical blocker index for these dated reports:**
[`2026-08-31-session-ratification.md`](../decisions/2026-08-31-session-ratification.md).
For current blocker navigation, use the [planning index](../plans/README.md) and
the canonical registers it links, including the
[student-engagement register](../plans/open-questions/student-engagement-deferred.md).

**How to request a fresh report:** Ask Cursor to use the **smartmatch-status-report** skill (project skill in `.cursor/skills/smartmatch-status-report/`).
