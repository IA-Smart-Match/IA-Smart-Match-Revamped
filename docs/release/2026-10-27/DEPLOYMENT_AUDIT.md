# Deployment audit: SmartMatch class release (read-only)

Date: 2026-10-27. Auditor: Agent A (model claude-haiku-5-5).
Scope: deploy.yml, promote.yml, scripts/vm/deploy.sh, docker-compose.exercise.yml, the exercise and tunnel runbooks, and GitHub Actions runs 15-17.
Read-only. No DNS, secret, variable, Cloudflare, workflow, push or commit changes. No workflow was triggered or re-run.
Public class URL https://exercise.smartmatch.cloud/exercise: NOT TESTED (this container gets 403 on CONNECT to that host).

## 1. Revision state

| Ref | Commit | Source |
|---|---|---|
| deploy branch (2026-10-27) | 4fc80d02783fa64b2418f379a44f8689080b3907 (PR #442) | list_branches |
| main at the time of the runs | 4fc80d0 | run 15/16/17 head_sha |
| main now | 763e6665377d48f7e595aa9f53594682b0bb09f7 (PR #444) | list_commits |
| Deployed on the VM | 4fc80d0 | VM release.env read back; job 121405926814 line "the VM is running 4fc80d0..."; job 121431865715 same |

Commits on main not yet on deploy (subjects only):
- 97dcb300 "feat(exercise): fix the ranked list at 60; record Ann's Oct 22 ruling" (adds migration 0049)
- 763e666 "Merge pull request #444 from IA-Smart-Match/chau-1027"

## 2. Runs (IA-Smart-Match-Revamped)

| Run | Workflow / ref | Conclusion | Probe host (job env) | Probe outcome | Evidence |
|---|---|---|---|---|---|
| 40268157058 | promote, source main | success | n/a | n/a | run list 2026-10-26 04:15Z |
| 40268173718 (#15) | deploy, ref deploy | failure at probe | https://pilot.plated.blog | curl exit 6, "Could not resolve host" | job 121399054397, 04:34:04Z |
| 40270215789 | promote, source main | success | n/a | n/a | run list 2026-10-26 04:39Z |
| 40270229833 (#16) | deploy, ref deploy | failure at probe | https://exercise.smartmatch.cloud | GET / 200, /coordinator-portal 200, /v1/me fixture token 404 (expected 401) | job 121405926814, 04:59:40Z |
| 40278494536 (#17) | deploy, manual dispatch on ref main | success, all 11 jobs | https://pilot.smartmatch.cloud | all probes pass, release=4fc80d0 | job 121431865715, 06:32:17-18Z |

The brief's premise is partly right. Run 15 failed on the retired pilot.plated.blog. Run 16 failed on a different assertion after the variable had been changed to the exercise host. Run 17 passed on pilot.smartmatch.cloud. The promote runs themselves succeeded; the failures were in deploy.yml. The current value of SMARTMATCH_PUBLIC_URL was not readable here; run 17 is the latest evidence of it.

## 3. Claims, separately

- Deployment succeeded: VERIFIED. Run 17 job 121431865715 "=== deployed 4fc80d0 (was 4fc80d0)" at 06:32:14Z. Run 16 job 121405926814 "health: every check passed against 4fc80d0" at 04:59:36Z. The deploy step passed in run 15 too (job 121399054397, step 5).
- Services started: VERIFIED on the VM in run 16 (job 121405926814, 04:59:07-04:59:36Z): api, worker, db, scheduler, web-exercise and api-exercise reached Running or Healthy; migrate and seed exited 0. Run 17 (06:32:14Z) api and worker Healthy. Exercise containers in run 17: NOT VERIFIED (not in the log tail read).
- Public URL responded: pilot.smartmatch.cloud VERIFIED (run 17: / 200, /coordinator-portal 200, /api/health 200). exercise.smartmatch.cloud PARTIAL (run 16: / 200, /coordinator-portal 200). pilot.plated.blog FAILED, does not resolve (run 15). Class URL: NOT TESTED.
- Application initialized: VM side VERIFIED (alembic_version=0048_exercise_team_code; api-health status=ok release=4fc80d0 in runs 16 and 17). Public-host API health VERIFIED on pilot host only (run 17). Exercise host NOT VERIFIED: run 16 failed before reaching /api/health.
- Required API calls succeeded: pilot host VERIFIED (run 17: /v1/me with all four fixture tokens returns 401; /api/health 200). Exercise host FAILED the fixture assertion (run 16: 404, expected 401). Class-exercise API flows (instructor login, team pages, results): NOT TESTED; no workflow step calls them.
- Full workflow passed: VERIFIED for run 17 only, and that run probed the pilot host, not the exercise host.

## 4. Probe failure causes

- Run 15: SMARTMATCH_PUBLIC_URL was https://pilot.plated.blog. That host no longer resolves (job 121399054397, 04:34:04Z).
- Run 16: SMARTMATCH_PUBLIC_URL was https://exercise.smartmatch.cloud. The probe's CBA-only fixture-token check (.github/workflows/deploy.yml:329-343) expects 401 from /v1/me and got 404. Inference: the exercise host is served by web-exercise (127.0.0.1:5174), whose /v1 is proxied to api-exercise, a class_exercise-scope process. That process probably does not mount the CBA /v1/me identity router. Mount rules are in services/api/smartmatch_api/main.py:710 (routers_for); I did not read the full table. So the probe asserted a CBA route on an exercise host. The API did not fail.
- Run 17: passes on pilot.smartmatch.cloud with the same release.

## 5. Does any step probe the exercise host?

No. deploy.yml probes only SMARTMATCH_PUBLIC_URL (deploy.yml:263-366). scripts/compose_health.sh checks the CBA frontend at 127.0.0.1:5173 (line 80) and has no exercise check. The exercise host is probed only when the variable points at it (run 16) or by the manual curls in exercise-hosting.md section 9 (lines 954-1009).

## 6. Does deploy.sh bring up api-exercise and web-exercise?

Conditionally. resolve_compose_scope (scripts/vm/deploy.sh:273-299) adds docker-compose.exercise.yml with --profile exercise only when the VM's .env sets SMARTMATCH_EXERCISE_WORKSPACE_SECRET to a non-empty value and the file exists. Run 16 logs show smartmatch-api-exercise-1 and smartmatch-web-exercise-1 Running (job 121405926814, 04:59:07Z), so the overlay was active on 4fc80d0. The VM's .env itself: NOT TESTED.

Ports (docker-compose.exercise.yml):
- api-exercise: 127.0.0.1:8090 -> 8080 (lines 127-128)
- web-exercise: 127.0.0.1:5174 -> 5173 (lines 162-163); /v1 proxied to api-exercise:8080 (line 161)

Tunnel: exercise.smartmatch.cloud -> http://127.0.0.1:5174 per exercise-hosting.md:455-485 and 927-935 (marked VERIFY ON VM). The mapping lives in the Cloudflare dashboard, not in git (classroom-vm-cloudflare-tunnel.md:372-390). NOT VERIFIED.

## 7. Proposed correction (NOT APPLIED)

1. Confirm in GitHub environment pilot-vm that SMARTMATCH_PUBLIC_URL is https://pilot.smartmatch.cloud. A human should check this; it was not readable here.
2. Do not point the CBA probe at the exercise host. Make the fixture-token assertion host-aware, or split it into a separate exercise probe job for the exercise host with its own assertions (/api/health release match, /exercise page 200, no CBA /v1/me check).
3. If exercise probing is wanted, add a separate variable (for example SMARTMATCH_EXERCISE_PUBLIC_URL) so the CBA probe stays stable.
4. Reconcile the docs: exercise.plated.blog and pilot.plated.blog still appear in several files (backlog.md, status reports, tests, classroom-vm runbook placeholders).

## 8. Rollback procedure (from the docs)

- Automatic: deploy.sh rollback() (scripts/vm/deploy.sh:615) checks out the previous SHA, rebuilds, and reruns health. The job still fails. Migrations are never downgraded. Documented in deploy-runbook.md:281-300 and vm-deploy.md:727. A skip-migrate override exists for the case where migrate failed on a revision the previous release lacks (deploy.sh:522-615; deploy-runbook.md:298-330). Its own doc says it is untested on a real VM.
- Manual, as documented: deploy-runbook.md:322-331 says to promote an earlier commit with promote.yml and redeploy. This does not work as written. promote.yml:27-31 and deploy.sh:351-358 refuse any ancestor of the current deploy head. An earlier SHA therefore cannot be re-promoted without a forced push, which the workflow forbids.
- Exercise only: exercise-hosting.md:1017-1033 stops api-exercise and web-exercise with the three -f files and --profile exercise. The next deploy.sh run recreates them.

## 9. Risks

- Pending commit 97dcb300 adds migration 0049, which rewrites invite_limit to 60 and replaces a check constraint. Its downgrade restores >= 1. The expand/contract tool (tools/migration_expand_contract_check.py) targets drop_column, drop_table and rename, so it may pass. Rollback risk: the previous release could write invite_limit values the narrowed constraint rejects. Not verified.
- Run 17 was a manual dispatch on ref main, and deploy.yml does not restrict dispatch to the deploy ref. Whatever deploy points at is what gets deployed, so this is a process gap.
- No Cloudflare Access wall on the public host (deploy.yml:273-281), a known gap. The exercise host has no Access policy and its login rate-limit rule is not applied (exercise-hosting.md:566-580).
- Run 16 left exercise containers running on a VM whose probes target the CBA host. The next promote will converge, but the mismatch is easy to misread.

## 10. Not tested

- https://exercise.smartmatch.cloud/exercise (container network 403).
- Current value of SMARTMATCH_PUBLIC_URL and all other pilot-vm variables and secrets (not readable here).
- Cloudflare tunnel ingress and Access policy.
- VM .env, exercise-scope route table, and class-exercise API flows.
- Exercise containers after run 17.
- Rollback path (skip-migrate) on a real VM.

## 11. Method

GitHub Actions: list_workflow_runs, list_workflow_jobs, get_job_logs (tail 200-420 lines per job), list_branches, list_commits. Local: file reads and grep. gh could not download log archives (token invalid for that download). No secret values appear in this file; log env values shown as *** were not recorded.
