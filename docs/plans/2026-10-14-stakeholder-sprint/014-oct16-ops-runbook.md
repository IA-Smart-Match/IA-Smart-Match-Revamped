# 014 — Ops plan: clean the deployed exercise before Ann's Oct-16 run-through (#323)

**Prepared only. Nothing in this plan was run against any live environment.** Runbook: `docs/operations/exercise-oct16-cleanup-runbook.md`. Open question: `docs/plans/open-questions/oct14-deferred.md` → OQ-OCT14-03.

## Current behavior

- Deployed 2026-09-28 (backlog row, `docs/plans/backlog.md`): VM branch `deploy` at main `19b110eb`; `api-exercise` on `127.0.0.1:8090`, `web-exercise` on `127.0.0.1:5174`; tunnel `exercise.plated.blog` → `:5174`; Ann's September 300-row file uploaded. **Not re-verified since — verify on the VM.**
- Ann's Oct-2 note: Northline results were left open and test work is saved under Teams 1–4 (checklist §10 row 12).
- **No way to close results on `main`.** `exercise_result_unlock` is a presence row; the only write is the unlock insert (`instructor_repository.py:455-477`). The runtime role has `SELECT, INSERT` only on that table (`docs/operations/exercise-hosting.md:218`). #326 adds the close route and the `UPDATE` grant; it merged in #345 on 2026-10-06 (this paragraph describes `main` before that). Deploying it and running the grant on the VM are still separate steps.
- Clearing a team is per team: `POST /v1/exercise/instructor/workspaces/{team_number}/reset` (`exercise_instructor.py:532-533`). No bulk route.
- A re-point (`POST /v1/exercise/instructor/datasets/{dataset_id}/repoint`, `exercise_instructor.py:301-302`) clears **all six** teams and the new file starts with both events closed. Ann also asked for exactly this switch to the Oct-2 file.
- Seed after a clear: builds before #331 draw a new seed; builds with #331 keep it. Ann's checklist §8 passes only on a build with #331.
- No API undo. Recovery is a `pg_dump` restore (`scripts/vm/deploy.sh:356-364`; backups under `/opt/smartmatch/backups`).

## Ordered change list — conditional on the owner's choice of path

Nothing here changes code. Each path is a different section of the runbook.

**Path A — close route, then four clears (recommended when Teams 5–6 must stay untouched).**
1. Deploy #326 (merged in #345: close route + grant). Merge and deploy #331 (PR #344, seed kept).
2. Run the grant change from #326 as the owner role (verify the exact statement in the merged PR).
3. Runbook §§1–3 pre-flight → §4 close Northline, close Harbor → §5 clear Teams 1, 2, 3, 4 → §7 verify.

**Path B — the Oct-2 file re-point does the cleanup (recommended when the Oct-2 file is going live anyway).**
1. Deploy #339 (merged; accepts the Oct-2 workbook). Merge and deploy #331 (PR #344). #326 is not needed for the cleanup itself, but Ann's checklist §2 still needs it for "a way to close it again".
2. Pre-flight → upload the Oct-2 file → re-point → verify: six teams at the start, both events closed.
3. Owner accepts that Teams 5–6 are cleared too. Issue #323 says "leave Teams 5 and 6 untouched"; a re-point cannot do that.

**Path C — SQL fallback for the close (only if #326 slips past 2026-10-13).**
1. As the database owner role, inside the db container: delete the two unlock rows for the teams' data file. A deliberate, recorded exception to the least-privilege grant.
2. Then the four clears as in path A.

**After any path:** fill the evidence table; correct the stale "nothing here has been run" lines in `exercise-hosting.md` §9/§9b in a docs PR that cites the evidence.

## Test plan

- Before the live run, rehearse the chosen path on a developer machine: `make exercise-seed`, enter six teams, unlock, run, then follow the runbook against `localhost`. Compare the before/after snapshots with `diff`.
- Path C only: run the `DELETE` on the developer database first and confirm `GET /v1/exercise/instructor/events` flips `unlocked` to `false`.
- Live: the runbook's read-only §3 calls are the dry run. Confirm each response carries the fields the runbook names before any write.

## Acceptance

- Progress and Revisions, "Clean-up before Oct 16": "Danny: clear all test work under Teams 1 to 4, and set both events back to 'results closed,' so my run-through starts from a clean site."
- Checklist §2: "Before the Oct 16 run-through, every test team is cleared and both events are closed."
- Checklist §2: "Both events show 'Results closed' at the start, with a button to open each."
- Checklist §8: "After clearing, run the same list again for that team. The result is the same as before (the chance part is fixed per team)." — needs #331 in the deployed build.
- Issue #323: runbook written and reviewed; before/after state recorded with timestamps and operator; rollback documented; separate explicit confirmation before the destructive step.

## Decision status

- **Deferred to the owner (Danny).** Four answers needed — see OQ-OCT14-03:
  1. Path A, B or C.
  2. Which commit is deployed for the run-through (must contain #331; #326 for path A; #339 for path B).
  3. Written go-ahead, operator name and date for the destructive steps.
  4. Whether Teams 5–6 may be cleared (path B) or must be untouched (path A).
- **Recommended default:** path B if the Oct-2 file is being switched in before Oct 16 (Ann asked for the switch); otherwise path A.
- **Needed by:** answers 2026-10-13; execution 2026-10-14; hard stop 2026-10-16.
- **Dependencies:** #326 (close route), #331 (seed kept on clear), #339 (Oct-2 workbook upload), #299 (Justin's test evidence).
