> DRAFT — needs Danny (BrooklynD23) decision. Nothing here is decided.

# #323 — Oct-16 reset runbook (re-authored draft)

Replaces nothing yet. It restates `docs/operations/exercise-oct16-cleanup-runbook.md` against `origin/main` @ `122b01b0` and adds read-only pre-flight scripts. It authorizes no write.

## Context and sources

| Fact | Source |
|---|---|
| Ledger row: execution gated on Danny's 4 answers + #326 deploy state | issue #323 (last comment, BrooklynD23 2026-10-06) |
| Four answers needed: path A/B/C; deployed commit; may Teams 5-6 be cleared; written go-ahead | same comment; `docs/plans/open-questions/oct14-deferred.md` (OQ-OCT14-03) |
| Existing runbook, 298 lines, never run | `docs/operations/exercise-oct16-cleanup-runbook.md:3` |
| #326 close route merged to main (PR #345: merge `783a1244`, feature commit `98e52381`) | `git log origin/main` |
| #331 seed-preserve merged to main (PR #344, `dd6df303`) | `git log origin/main` |
| Close route is `POST /v1/exercise/instructor/events/{event_key}/lock` | `services/api/smartmatch_api/routers/exercise_instructor.py:439` |
| Per-team clear is `POST .../workspaces/{team_number}/reset` | `exercise_instructor.py:559` |
| File switch is `POST .../datasets/{dataset_id}/repoint` | `exercise_instructor.py:302` |
| Health route returns the release | `services/api/smartmatch_api/main.py:760` |
| `closed_at` column for the close time | `db/migrations/versions/0045_exercise_result_unlock_closed_at.py` |

Changes since the 2026-10-07 text of the existing runbook: its section 10 said #331 was "PR #344 open, not merged"; main now contains it (`dd6df303`). The close route is no longer a guess: it exists at `exercise_instructor.py:439`, so the "confirm the path against the merged PR" caveat at existing runbook line 163 can be reduced to checking the response body.

**Merged is not deployed.** Main containing #326/#331 says nothing about what runs on the VM. The deployed SHA is UNKNOWN to this draft; Danny records it (Q2).

## 0. Stop conditions (unchanged from the existing runbook, lines 13-24)

Do not write anything if any holds:

1. No written go-ahead naming date, operator, path (A/B/C) and release SHA.
2. `GET /v1/exercise` does not say `synthetic_data: true`, or the host is not the one named in the go-ahead.
3. Data-file checksum does not match Ann's file.
4. `/api/health` release is not the SHA in the go-ahead.
5. Path A and the deployed build lacks the close route.
6. No fresh, verified backup.

There is no undo. Recovery is a database restore (section 8).

## 1. Paths (owner picks; this draft picks none)

| Path | What it does | Needs deployed | Teams 5-6 | Verify on VM |
|---|---|---|---|---|
| A | Close Northline and Harbor, then clear Teams 1-4 one at a time | #326 + its `UPDATE` grant, #331 | untouched | grant, deployed SHA |
| B | Upload Ann's Oct-2 file, repoint every team; both events start closed | #339, #331 | cleared too | deployed SHA |
| C | Path A, close done in SQL as DB owner | #331 | untouched | owner-role URL, dataset_id |

Rules that hold on every path:

- Close results before clearing teams (A and C). Existing runbook line 39 explains why.
- If the Oct-2 file is switched at all, switch first. A repoint clears all six teams (`exercise_instructor.py:302`), so a later switch undoes a path-A clean-up and wipes Teams 5-6.
- Issue #323 says leave Teams 5-6 alone; path B cannot. Needs Danny's written acceptance (Q3).

## 2. Confirm what is deployed

| Step | Command | Where | Verify on VM |
|---|---|---|---|
| 2.1 release from outside | `323-preflight/01-health-release.sh --base-url <url> --execute` | operator machine | yes: the host name is not in this draft |
| 2.2 release on the VM | `git -C /opt/smartmatch/app rev-parse HEAD`; `cat /opt/smartmatch/release.env`; health on the loopback port | VM | yes, VM only |
| 2.3 build contains #326/#331/#339 | `git merge-base --is-ancestor <merge-sha> <release>` using `98e52381`/`3f9298cc` (#326), `dd6df303` (#331) | any clone | no |
| 2.4 containers up | compose `ps` with all three `-f` files (existing runbook lines 77-84) | VM | yes, VM only |

Health value `vm-unknown` or `dev` proves nothing (existing runbook line 52; `scripts/vm/deploy.sh:431` exports the release; `release.env` is written at `:311`).

## 3. Record the state before (read-only)

Run, from your own machine, with the instructor cookie in the environment (never pasted into a ticket):

```
export EXERCISE_INSTRUCTOR_COOKIE='<name=value>'   # from a login you did by hand
cd docs/plans/sweep-drafts/323-preflight
./01-health-release.sh     --base-url "$URL" --execute
./02-dataset-checksum.sh   --base-url "$URL" --execute /path/to/ann-workbook.xlsx
./03-events-and-teams.sh   --base-url "$URL" --execute ~/oct16-cleanup
```

Each script is dry-run unless `--execute`; all issue GET only. They do not log in: the login is a POST and stays a manual step (existing runbook 3.1).

3.6 Backup, VM only, immediately before the first write. Keep the `pipefail` form and the two dumps (full + `exercise_*` only) from the existing runbook lines 140-157. Verify on VM: DB URL variable, owner role name, `gzip -t` on both files. `deploy.sh` prunes to 14 dumps (`scripts/vm/deploy.sh:128` `BACKUP_RETAIN=14`, pg_dump at `:405`, prune at `:741-743`): copy the two files elsewhere.

3.7 License line on the opening screen (checklist 9 / #273): browser check, no script.

## 4. Writes (operator only; no script in this draft writes)

- Path A close: `POST .../events/{key}/lock` for each of Northline and Harbor, header `X-Exercise-Request: 1`, keys read from the events response, not assumed (existing runbook 3.4 says E11/E12 in Ann's file). The `UPDATE` grant on `exercise_result_unlock` must be applied by the DB owner first. Verify on VM.
- Path C close: the SQL in existing runbook lines 184-195, ROLLBACK first. Recorded exception to least privilege. Do not use on a build with #326: it would discard the open/close times.
- Path A/C clear: `POST .../workspaces/{n}/reset` for n=1,2,3,4, one at a time, stop at the first unexpected answer. A never-entered team is refused; record it.
- Path B: upload on the instructor page, compare checksum, `POST .../datasets/{id}/repoint`; pass is `teams_moved` equals the team count from 3 and `teams_discarded` 0.

## 5. Record the state after, and compare

Re-run script 03 into a second directory; `diff` Teams 5-6 JSON before/after (path A/C), expect zero settings and runs for Teams 1-4, both events `unlocked: false`, health release identical to 2.1. Sign-out is a POST: manual.

## 6. Rollback

1. A refused close/clear: stop, record the body. Each call is one transaction.
2. Wrong team cleared: no API undo. Full restore rewinds the whole database including CBA tables; the exercise-only restore (stop `api-exercise`, empty eight `exercise_*` tables, load dump) is not rehearsed. Verify on VM; rehearse on a developer database first.
3. Release changed mid-run: redo sections 3 and 5; discard earlier snapshots.

## 7. Evidence table (attach to #323 and #299)

| Step | Result | Time (UTC) | Release SHA | Operator |
|---|---|---|---|---|
| go-ahead (link) | | | | |
| path chosen | | | | |
| health before | | | | |
| has #326 / #331 / #339 | | | | |
| synthetic_data | | | | |
| data file label / filename / checksum | | | | |
| locks before | | | | |
| teams 1-6 before | | | | |
| backups (two file names, gzip -t result) | | | | |
| results closed (A/C) or repoint (B) | | | | |
| teams 1-4 cleared | | | | |
| teams 5-6 unchanged | | | | |
| locks after | | | | |
| health after | | | | |

## Steps that can only be verified on the VM

Deployed SHA and release env; loopback health; container state and which compose/override is in use (existing runbook line 84); the `UPDATE` grant; backup commands and owner role; the exercise-only restore; passcode file location.

## Open questions

1. Which path, A, B or C? Danny.
2. Which commit is deployed for the run-through, and does it contain #331 and #326? Danny (records it from the VM).
3. May Teams 5-6 be cleared? Danny. Yes means path B is allowed; no forces A or C.
4. Written go-ahead: date, operator, path. Danny.
5. Is the Oct-2 file going live before Oct 16? If yes, path B ordering applies. Danny with Ann.
6. If path C: is the owner-role SQL exception accepted in writing? Danny.
