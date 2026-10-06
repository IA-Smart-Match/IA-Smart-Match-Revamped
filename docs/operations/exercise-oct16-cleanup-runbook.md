# Class exercise — clean-up runbook for Ann's Oct-16 run-through

**Status:** written 2026-10-06, **not run**. Nobody has executed any step here against the VM. Issue #323.
**Target:** results closed for Northline and Harbor, Teams 1–4 cleared, on `https://exercise.plated.blog`, by 2026-10-14.
**Operator:** Danny (owner). **This document authorizes nothing.** Step 0 is a written go-ahead.

Every step marked **VERIFY ON THE VM** could not be checked from the repository. Treat its command as a draft: read the output before trusting it.

Source of the ask (Ann, 2026-10-02): "Danny: clear all test work under Teams 1 to 4, and set both events back to 'results closed,' so my run-through starts from a clean site."

---

## 0. Stop conditions — read first

Stop and do not write anything if any of these is true:

1. No written go-ahead from the owner naming the date, the operator and the path (A, B or C below).
2. `GET /v1/exercise` does not say `synthetic_data: true`, or the hostname is not `exercise.plated.blog`.
3. The data file's checksum does not match the file you expect (§3.3).
4. The release on `/api/health` is not the commit you meant to deploy (§2).
5. Path A and the deployed build has no close route (#326 not deployed).
6. No fresh backup (§3.6).

There is **no undo button**. A cleared team's settings, lists, results and refresh are deleted. The only recovery is restoring a database dump (§8).

## 1. Pick the path (owner decides — OQ-OCT14-03)

| Path | What it does | Needs deployed | Teams 5–6 | When to use |
|---|---|---|---|---|
| **A** | Close both events with the close route, then clear Teams 1–4 one at a time | #326, #331 | Untouched | The data file is **not** being switched before Oct 16 |
| **B** | Upload Ann's Oct-2 file and switch every team to it. The switch clears all six teams, and the new file starts with both events closed | #339, #331 | **Cleared too** | The Oct-2 file is going live anyway (Ann asked for the switch) |
| **C** | Path A, but the close is done in SQL as the database owner | #331 | Untouched | Only if #326 is not deployed by 2026-10-13 |

Two facts decide between A and B:

- A switch to a new file (`repoint`) clears **every** team. If you run path A and switch files afterwards, the switch redoes the clean-up and wipes Teams 5–6 anyway. So if the Oct-2 file is going in before Oct 16, do the switch **first** and treat §§4–5 as checks.
- Issue #323 says "leave Teams 5 and 6 untouched". Path B cannot. The owner must accept that in writing, or use path A.

**Order inside path A and C: close results BEFORE clearing teams.** The instructor's event routes find "the file the teams are on" from the team rows, and refuse with `exercise_no_teams_yet` when there are none (`exercise_instructor.py` `_teams_dataset`). A clear keeps the team row, so the order should not matter — but closing first costs nothing and removes the risk. Clear first only if #326 shipped its zero-teams fallback (check the merged PR).

## 2. Confirm what is deployed

Deployed facts last recorded 2026-09-28 (`docs/plans/backlog.md`): VM checkout `/opt/smartmatch/app` on branch `deploy` at `19b110eb`; `api-exercise` on `127.0.0.1:8090`; `web-exercise` on `127.0.0.1:5174`; tunnel `exercise.plated.blog` → `:5174`. **All of it: VERIFY ON THE VM.**

2.1 **Release, from outside.**

```bash
curl -sS https://exercise.plated.blog/api/health
# {"status":"ok","release":"<sha>"}
```

Record `release`. Expect a full commit SHA: `scripts/vm/deploy.sh:385` exports `SMARTMATCH_RELEASE` and `docker-compose.exercise.yml:125` passes it in. If it reads `vm-unknown` or `dev`, the container was started by hand without the release — the value proves nothing; use 2.2. **VERIFY ON THE VM.**

2.2 **Release, on the VM.**

```bash
git -C /opt/smartmatch/app rev-parse HEAD
git -C /opt/smartmatch/app status --short | head
cat /opt/smartmatch/release.env
curl -sS http://127.0.0.1:8090/api/health
```

Pass: the three SHAs agree and the checkout is clean. The web container bind-mounts the checkout, so `rev-parse HEAD` is the frontend's version; `/api/health` is the API image's. They can differ if a deploy was done without `--build`. **VERIFY ON THE VM.**

2.3 **The build contains what the path needs.** On any clone with `origin` fetched (`<release>` = the SHA from 2.1):

```bash
git merge-base --is-ancestor <merge-sha-of-331> <release> && echo "has #331" || echo "NO #331"
git merge-base --is-ancestor <merge-sha-of-326> <release> && echo "has #326" || echo "NO #326"
git merge-base --is-ancestor <merge-sha-of-339> <release> && echo "has #339" || echo "NO #339"
```

- No #331 → a cleared team gets a **new** chance seed, and Ann's checklist §8 ("The result is the same as before") **fails** for Teams 1–4 if she compares against results from before the clear. Deploy #331 first, or tell Ann.
- No #326 → path A is not possible. Use B or C.
- No #339 → the Oct-2 file may be refused at upload. Path B is not possible.

2.4 **Both exercise containers are up.** From `/opt/smartmatch/app`:

```bash
docker compose -f docker-compose.yml -f docker-compose.vm.yml \
  -f docker-compose.exercise.yml --profile exercise ps
```

Always all three `-f` files. Omitting `docker-compose.vm.yml` strips restart policies from anything compose recreates. This command only reads. **VERIFY ON THE VM** — on 2026-09-28 the exercise services were started from an override outside the checkout (`/opt/smartmatch/exercise-web.override.yml`, `/opt/smartmatch/exercise-setup.sh`); PR #253 moved them into `deploy.sh`. Confirm which one is in use before running any compose command, and if the containers are missing after a deploy, re-run `sudo -u smartmatch /opt/smartmatch/exercise-setup.sh`.

## 3. Record the state before (read-only)

Work from a private directory on your own machine. Do not paste the passcode or the cookie file into a ticket or a chat.

3.1 **Sign in.** The passcode is on the VM, root-only, at `/opt/smartmatch/exercise-instructor-passcode` (**VERIFY ON THE VM**).

```bash
H=https://exercise.plated.blog
mkdir -p ~/oct16-cleanup && cd ~/oct16-cleanup && umask 077
read -rs PASS && export PASS    # type the passcode; nothing is echoed
curl -sS -c jar -X POST "$H/v1/exercise/instructor/login" \
  -H 'Content-Type: application/json' -H 'X-Exercise-Request: 1' \
  --data "$(printf '{"passcode":"%s"}' "$PASS")"
unset PASS
```

A wrong passcode is refused; ten wrong tries in five minutes is rate-limited.

3.2 **Environment is the fictional one.**

```bash
curl -sS "$H/v1/exercise" | tee before-scope.json
```

Pass: `synthetic_data` is `true`.

3.3 **Data file.**

```bash
curl -sS -b jar "$H/v1/exercise/instructor/datasets" | tee before-datasets.json
sha256sum /path/to/SmartMatch_Student_Body_300.xlsx     # the file you believe is live
```

Pass: one row's `checksum` equals the `sha256sum`, with `row_count` 300 and `event_count` 12. Record `label`, `source_filename`, `checksum`. The checksum is the SHA-256 of the uploaded bytes, so Ann's own file — not the stripped test fixture in the repository — is the one to hash.

3.4 **Events and locks.**

```bash
curl -sS -b jar "$H/v1/exercise/instructor/events" | tee before-events.json
```

Record `dataset_label` and, for each event, `event_key`, `name`, `unlocked`. In Ann's file Northline is `E11` and Harbor is `E12` — read the keys from this response, do not assume. The open **time** is not in this response on a build without #326; path C reads it in SQL.

3.5 **Teams.**

```bash
curl -sS -b jar "$H/v1/exercise/instructor/workspaces" | tee before-teams.json
for n in 1 2 3 4 5 6; do
  curl -sS -b jar "$H/v1/exercise/instructor/workspaces/$n" | tee "before-team-$n.json"; echo
done
```

Record per team: `dataset_label`, `saved_setting_count`, `result_run_count`, `asking_choice`, `refreshed_at`. A team that never entered is absent from the list and its detail call is refused — that is its "before".

3.6 **Backup, on the VM, immediately before the first write.** Same shape as the dump `deploy.sh` takes (`scripts/vm/deploy.sh:359`). **VERIFY ON THE VM** — check the database URL variable and the owner role name in `/opt/smartmatch/app/.env` first; the host-side URL says `localhost`, inside the container the host is `db`.

```bash
cd /opt/smartmatch/app
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker compose -f docker-compose.yml -f docker-compose.vm.yml exec -T db \
  pg_dump --clean --if-exists -U smartmatch -d smartmatch \
  | gzip -c > /opt/smartmatch/backups/smartmatch-$STAMP-pre-oct16-cleanup.sql.gz
docker compose -f docker-compose.yml -f docker-compose.vm.yml exec -T db \
  pg_dump --data-only -U smartmatch -d smartmatch -t 'exercise_*' \
  | gzip -c > /opt/smartmatch/backups/exercise-only-$STAMP-pre-oct16-cleanup.sql.gz
ls -l /opt/smartmatch/backups | tail -3
```

Pass: both files exist and are not empty. `deploy.sh` prunes that folder to the 14 newest dumps — copy these two somewhere else if a deploy may run before Oct 16.

3.7 **Checklist §9 license line (for #273).** Open `https://exercise.plated.blog/` in a browser. Pass: the opening screen shows "For California State Polytechnic University, Pomona — College of Business Administration instructional use only. All student profiles are fictional."

## 4. Close results — path A

Needs #326 deployed. The route below is the one #326's brief plans; **confirm the path and the response against the merged PR** before running.

```bash
for k in E11 E12; do      # the keys from 3.4
  curl -sS -b jar -X POST "$H/v1/exercise/instructor/events/$k/lock" \
    -H 'X-Exercise-Request: 1' | tee "close-$k.json"; echo
done
curl -sS -b jar "$H/v1/exercise/instructor/events" | tee after-close-events.json
```

Pass: both events read `unlocked: false` (or the closed state #326 names), with the close time shown.

Also needed once, before the first close, as the database owner: the `UPDATE` grant on `exercise_result_unlock` that #326 adds to `docs/operations/exercise-hosting.md` §3. Without it the route answers its refusal sentence. **VERIFY ON THE VM** with §3's privilege check.

## 4-C. Close results — path C (SQL, owner role)

Only with the owner's written approval of this exception. The runtime role `smartmatch_exercise` has no `DELETE` on this table by design; this runs as the owner role and bypasses that.

```bash
cd /opt/smartmatch/app
docker compose -f docker-compose.yml -f docker-compose.vm.yml exec -T db \
  psql -U smartmatch -d smartmatch -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
SELECT u.dataset_id, d.label, u.event_key, u.unlocked_at
  FROM exercise_result_unlock u JOIN exercise_dataset d ON d.id = u.dataset_id;
-- Paste the dataset_id printed above for the teams' file. Do not guess it.
DELETE FROM exercise_result_unlock
 WHERE dataset_id = '<dataset_id from the SELECT>'
   AND event_key IN ('E11', 'E12');
SELECT count(*) AS still_open FROM exercise_result_unlock
 WHERE dataset_id = '<dataset_id from the SELECT>';
ROLLBACK;   -- first pass. Change to COMMIT only after reading the output.
SQL
```

Run it once as written: it rolls back and changes nothing. Read the output. Pass: the `DELETE` reports at most 2 rows and `still_open` is 0. Then change `ROLLBACK` to `COMMIT`, run it again, and confirm `GET …/events` shows both `unlocked: false`. **VERIFY ON THE VM.** On a build with #326 do not use this: delete would discard the open/close times that build shows.

## 5. Clear Teams 1–4 — paths A and C

One team at a time. Each call clears that team's saved settings, lists, results, way of asking and refresh. Teams 5 and 6 are not named and are not touched.

```bash
for n in 1 2 3 4; do
  curl -sS -b jar -X POST "$H/v1/exercise/instructor/workspaces/$n/reset" \
    -H 'X-Exercise-Request: 1' | tee "clear-team-$n.json"; echo
done
```

Pass per team: the response shows `saved_setting_count: 0`, `result_run_count: 0`, `asking_choice: null`, `refreshed_at: null`. A team that never entered has no row to clear and is refused (**verify the exact answer on the VM**); record it.

Stop at the first unexpected answer. Do not retry in a loop.

## 6. Path B — switch every team to the Oct-2 file

Needs #339 deployed. This replaces §§4–5.

6.1 Upload on the instructor page (it sends the raw workbook; no form upload). Pass: "300 profiles, 12 events loaded" with the file name.
6.2 Re-read `GET …/datasets`; record the new row's `dataset_id`, `checksum`; compare the checksum with `sha256sum` of the Oct-2 file.
6.3 Switch:

```bash
curl -sS -b jar -X POST "$H/v1/exercise/instructor/datasets/<new dataset_id>/repoint" \
  -H 'X-Exercise-Request: 1' | tee repoint.json
```

Pass: `teams_moved` equals the number of teams listed in 3.5 and `teams_discarded` is 0. Every moved team is cleared and gets a new chance seed (a switch still does that; only a per-team clear keeps the seed). Both events are closed on the new file because nobody has opened them there.
6.4 Ann also asked: upload a copy with one column removed and confirm a plain error naming the column, with the old file still in use. Do it now, before §7.

## 7. Record the state after

Repeat 3.2–3.5 into `after-*.json`, then:

```bash
for n in 5 6; do diff "before-team-$n.json" "after-team-$n.json" && echo "team $n unchanged"; done
diff <(jq -S . before-datasets.json) <(jq -S . after-datasets.json) && echo "datasets unchanged"
curl -sS https://exercise.plated.blog/api/health     # same release as 2.1
```

Pass, paths A and C:
- Teams 1–4: zero settings, zero runs, no way of asking, not refreshed.
- Teams 5–6: no difference from before.
- Both events `unlocked: false`.
- Data files unchanged; every team still on the same `dataset_label`.
- `/api/health` release identical to 2.1 — nothing was redeployed mid-procedure.

Pass, path B: all six teams at zero on the new `dataset_label`; both events closed; release unchanged.

Then in a browser, as Team 1: the team page is back at the start, and both events say results are not open. Sign out:

```bash
curl -sS -b jar -X POST "$H/v1/exercise/instructor/logout" -H 'X-Exercise-Request: 1'; rm -f jar
```

## 8. If something goes wrong

- **A close or clear is refused.** Stop. Record the response body. Nothing was half-done: each call is one transaction.
- **Wrong team cleared, or work is needed back.** There is no API undo. Restore is manual and destructive:
  1. Decide with the owner. A full restore of `smartmatch-…-pre-oct16-cleanup.sql.gz` rewinds the **whole** database, CBA tables included, to the moment of the dump.
  2. Prefer the exercise-only dump: stop `api-exercise`, empty the eight `exercise_*` tables in one transaction, load `exercise-only-…sql.gz`, start `api-exercise`. This procedure is **not rehearsed and not automated** — rehearse it on a developer database before relying on it. **VERIFY ON THE VM.**
- **Containers missing.** A deploy or a reboot can remove them (see 2.4). Bring them back before anything else; the data is in the database, not the containers.
- **Release changed between 2.1 and 7.** A deploy ran mid-procedure. Re-run §3 and §7 fully; do not trust the earlier snapshot.

## 9. Evidence table

Fill in and attach to #323 (and #299 for Justin's list).

| Step | Result | Time (UTC) | Release SHA | Operator |
|---|---|---|---|---|
| 0 go-ahead (link) |  |  |  |  |
| 1 path chosen |  |  |  |  |
| 2.1 health before |  |  |  |  |
| 2.3 has #331 / #326 / #339 |  |  |  |  |
| 3.2 synthetic_data |  |  |  |  |
| 3.3 data file label / filename / checksum |  |  |  |  |
| 3.4 locks before |  |  |  |  |
| 3.5 teams 1–6 before |  |  |  |  |
| 3.6 backups (two file names) |  |  |  |  |
| 3.7 license line shown |  |  |  |  |
| 4 / 4-C / 6 results closed |  |  |  |  |
| 5 teams 1–4 cleared |  |  |  |  |
| 7 teams 5–6 unchanged |  |  |  |  |
| 7 locks after |  |  |  |  |
| 7 health after |  |  |  |  |

## 10. What this runbook depends on

| Issue | Why | State on 2026-10-06 |
|---|---|---|
| #326 | The close route and its grant. Without it, path A is impossible | Open, not merged |
| #331 | A cleared team keeps its chance seed, so checklist §8 passes | PR open |
| #339 | The Oct-2 workbook is accepted at upload (path B) | PR open |
| #337 | Matching-rule changes; carries a migration. Deploying it is a schema change — do it before this runbook, never during | PR open |
| #299 | Justin's test evidence uses this before/after record | Open |

Related: [`exercise-hosting.md`](exercise-hosting.md) §3 (the role and its grants), §7 (day-of-class steps), §9 (deploy checklist); [`deploy-runbook.md`](deploy-runbook.md) (rollback); [`vm-deploy.md`](vm-deploy.md).
