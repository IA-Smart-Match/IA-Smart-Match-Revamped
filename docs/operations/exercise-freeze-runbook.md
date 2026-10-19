# Class exercise — freeze the served copy, and clear before testing/class

**Owner-run. No agent runs any step here.** Why: Dr. Wang, "The class site seems to run straight from your working copy. During my test it lost its connection and reloaded several times. Run testing and class from a fixed copy that nobody edits. Make changes on a separate copy." (Load-test plan F8 says the same.)

What changed in the repo: `web-exercise` (`docker-compose.exercise.yml`) now builds an image (`apps/web/legacy-frontend/Dockerfile.exercise`: `npm ci` + `vite build`, served by `vite preview`). No bind mount, no HMR websocket. Port 5173 inside, `127.0.0.1:5174` outside, so the tunnel is unchanged.

## 1. Freeze (once, before testing week)

1.1 Cut a tag on main (from your dev copy, after the PR is merged):

```bash
git fetch origin && git tag -a exercise-2026-10-23 origin/main -m "class exercise 2026-10-23" && git push origin exercise-2026-10-23
```

1.2 Put the VM checkout on that tag. `/opt/smartmatch/app` is now **frozen: nobody edits it**; do all changes on another checkout/branch.

```bash
gcloud compute ssh smartmatch --zone us-west2-c --tunnel-through-iap
cd /opt/smartmatch/app && git status --short   # must be empty
git fetch origin --tags && git checkout exercise-2026-10-23 && git rev-parse HEAD
```

1.3 Edit `/opt/smartmatch/exercise-setup.sh`: delete `-f /opt/smartmatch/exercise-web.override.yml` from `FILES`. That VM-local file re-declares the dev server and would override the built service. Then `mv /opt/smartmatch/exercise-web.override.yml /opt/smartmatch/exercise-web.override.yml.disabled`.

1.4 Rebuild only the web service (same files as the setup script, minus the override):

```bash
cd /opt/smartmatch/app
sudo docker compose -f docker-compose.yml -f docker-compose.vm.yml -f docker-compose.exercise.yml \
  --profile exercise up -d --build web-exercise
```

(Needs the exercise vars from `.env`; `exercise-setup.sh` loads them. If compose complains about a missing variable, run the same command through that script instead.)

1.5 Verify:

```bash
curl -s http://127.0.0.1:5174/ | grep -o '/assets/index-[^"]*\.js'     # expect one match
curl -s http://127.0.0.1:5174/ | grep -c '/@vite/client'                # expect 0
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5174/v1/exercise   # API proxy works: 200
sudo docker ps --filter name=exercise --format '{{.Names}} {{.Status}}'
curl -s https://exercise.plated.blog/ | grep -c '/@vite/client'          # expect 0, through the tunnel
```

## 2. Rollback

```bash
cd /opt/smartmatch/app && git checkout <previous-sha>     # e.g. 4989ff9b
# restore the old FILES line in exercise-setup.sh and the .override.yml, then:
sudo bash /opt/smartmatch/exercise-setup.sh
```

## 3. How `deploy.sh` interacts

`scripts/vm/deploy.sh` does **not** use the VM override; it adds `docker-compose.exercise.yml --profile exercise` itself when `.env` has `SMARTMATCH_EXERCISE_WORKSPACE_SECRET`. So after this change a push to `deploy` (= a deploy) rebuilds the bundle from whatever it checks out. **Do not push to `deploy` during testing week or class.** Only the owner does, deliberately, after re-tagging.

## 4. Before testing week and before class

Dr. Wang: "Clear all test teams and close both events before testing week and again before class." **Owner only.** Takes a dump first (see `exercise-oct16-cleanup-runbook.md` §3.6; a clear has no undo).

State on the VM today (2026-10-19): runs on teams 1, 3, 4; E12 unlocked 2026-10-16, E11 unlocked 2026-10-19; team 4 refreshed. Teams 1, 3, 4, 5, 6 have rows; Team 2 never entered there.

4.1 Log in (passcode typed, not echoed):

```bash
H=https://exercise.plated.blog; cd ~ && umask 077
read -rs PASS; curl -sS -c jar -X POST "$H/v1/exercise/instructor/login" -H 'Content-Type: application/json' \
  -H 'X-Exercise-Request: 1' --data "$(printf '{"passcode":"%s"}' "$PASS")"; unset PASS
```

4.2 Close both events (route exists: `POST /v1/exercise/instructor/events/{event_key}/lock`, idempotent, deletes nothing; the instructor page's close button calls it). Needs the `UPDATE` grant on `exercise_result_unlock` (exercise-hosting.md §3). Do this **before** clearing.

```bash
for k in E11 E12; do curl -sS -b jar -X POST "$H/v1/exercise/instructor/events/$k/lock" -H 'X-Exercise-Request: 1'; echo; done
curl -sS -b jar "$H/v1/exercise/instructor/events"      # both unlocked:false
```

4.3 Clear each team that has a row, one at a time, reading each answer (page button: "Clear team N's work"). A reset **keeps the team's row** and its seed; it deletes saved settings, result runs, asking choice, refresh. Team 2 has no row and is refused (404), expected.

```bash
for n in 1 3 4 5 6; do curl -sS -b jar -X POST "$H/v1/exercise/instructor/workspaces/$n/reset" -H 'X-Exercise-Request: 1'; echo; done
```

Pass per team: `saved_setting_count: 0`, `result_run_count: 0`, `refreshed_at: null`.

4.4 Verify, read-only (VM):

```bash
cd /opt/smartmatch/app && sudo docker compose -f docker-compose.yml -f docker-compose.vm.yml exec -T db \
  psql -U smartmatch -d smartmatch -c "SELECT w.team_number, (SELECT count(*) FROM exercise_saved_setting s WHERE s.workspace_id=w.id) AS settings, (SELECT count(*) FROM exercise_result_run r WHERE r.workspace_id=w.id) AS runs FROM exercise_team_workspace w ORDER BY 1;" \
  -c "SELECT event_key, unlocked_at FROM exercise_result_unlock ORDER BY 1;"
```

Expect settings 0 and runs 0 for every team. Unlock rows: on a build with the close route, a closed event shows a `closed_at` after `unlocked_at` (use the `/events` answer as the source of truth). Column names above are from the repo's repositories; **VERIFY ON THE VM** (`\d exercise_team_workspace`) before trusting them.

4.5 **Write (owner SQL, only if the close route is refused or not deployed).** Marked WRITE. Dry-run first: it rolls back. Then change to COMMIT.

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.vm.yml exec -T db psql -U smartmatch -d smartmatch -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
DELETE FROM exercise_result_unlock WHERE event_key IN ('E11','E12');   -- WRITE
SELECT count(*) AS still_open FROM exercise_result_unlock;
ROLLBACK;   -- change to COMMIT after reading the output
SQL
```

Do not run 4.5 on a build that tracks `closed_at`; it discards the close times. See `exercise-oct16-cleanup-runbook.md` §4-C.
