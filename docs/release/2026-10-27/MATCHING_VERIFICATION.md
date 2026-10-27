# Matching verification, class exercise (Agent C)

- Revision under test: **4fc80d0** (working tree at this commit; the VM revision)
- origin/main at time of writing: **763e666** (PR #444, migration 0049). Not tested here; see section 6.
- Fixture: `tests/fixtures/exercise/SmartMatch_Student_Body_300_10022026.xlsx`
  - sha256 `57cb47e7a04dd331b15bc1f2ae68975e3b551397972b33b145f3ec9be02f9866` (also the dataset checksum)
  - 300 profiles, 12 events, 230 profiles with no card (`stated_interests is None`)
  - Fictional profiles (tests/fixtures/exercise/README.md)
- Timestamp: 2026-10-27 21:35 UTC (`date -u`)
- Python 3.12.3 venv at `.venv` (see section 4 for why not 3.13)
- Not run: docker, integration tests (need PostgreSQL), e2e. Makefile not changed. Nothing committed or pushed.

## 1. Algorithm (what the code does)

Classification: **rule-based, deterministic ranking, plus a seeded (not random) simulation**. The list is fully determined by the file, the weights and the dataset checksum. The "chance" is a SHA-256 digest of (team seed, event key, profile number, purpose); no `random` module is used.

Inputs
- Dataset: parsed by `parse_exercise_file` (`python/smartmatch_domain/smartmatch_domain/exercise/ingest.py:141`). Cards, hidden true interests and hidden true career goal are carried on `ParsedProfile` (`layout.py`).
- Team state: weights (`registry.py:162` defaults 3/3/2/2; `registry.py:303` validation, whole numbers 0-10 for new requests, all-zero refused) and an overlay card per profile (round-two refresh only).
- Team seed: `new_workspace_seed()` = `secrets.randbits(63)` (`workspace_token.py:142`), stored per team. The seed is the only per-team state the simulation reads (`simulation.py` docstring, behaviour 5).

Eligibility
- A profile is rankable only if it has a major and a class year (`services/api/smartmatch_api/routers/exercise_matching_models.py:261-325`, `_profile_evidence` / `rankable_set`). Others are counted, not ranked.
- No card is allowed; a profile without a card can only score on major and past events.

Scoring (`exercise/matching.py:180` `score_exercise_pair`)
- Four factors: same major, stated-interest overlap, career-goal fit, past-event topic overlap.
- Value = sum over known factors of (normalised weight x factor value). Unknown factors contribute nothing and their weight is not re-spread (ADR-0016; module docstring).
- Weights are normalised by `normalize_weights` (`registry.py:384` `exercise_applied_weights`).

Ranking and cut (`matching.py:291` `_exercise_ranked`, `matching.py:474` `rank_profiles_for_event`, `matching.py:521` `exercise_ranked_list`)
- Sort key ascending: (value is None, -value, -information rank, -class-year rank, fixed-order position).
- Fixed-order position (`matching.py:412` `_fixed_order`): Ann's `tiebreak_order` when every profile has one (this file does); otherwise `exercise_permutation` (`determinism.py:63`), a SHA-256 order seeded by the dataset checksum.
- List = first `invite_limit` entries. `invite_limit <= 0` is refused.
- Tie-break reasons are read from the whole ranked set before the cut (`exercise_ranked_list`).

Simulation (`exercise/simulation.py`)
- Coefficients (`EXERCISE_SIMULATION_COEFFICIENTS`, line 479): base sign-up 0.05; true-fit lift 0.50, split 0.7 interests / 0.3 career goal (so 35 and 15 in 100); attender lift 0.05 for >=1 past event and 0.10 for >=3 (`many_attender_lift`, `many_attender_events=3`); same-major lift 0.05; mass notice 0.20; CBACH notice 0.60 (listed profiles only); attend given sign-up 0.65.
- Per profile: noticed = mass draw < 0.20, or (listed and CBACH draw < 0.60). Sign-up probability = clamp(0.05 + lift, 0, 1); sign-up if the signup draw is below it. Attend if the attend draw is below 0.65 (`_outcome`, `simulation.py:567`; `_sign_up_lift`, `simulation.py:549`; `_uniform`, `simulation.py:510`).
- The 8 pre-registered students attend at 0.65 from the same kind of draw (`existing_attended`, `simulation.py:682`).
- Team run and mass-only run use the same draws, so a listed profile's mass outcome is unchanged by being on the list.
- Lift shown to a team (`exercise_results_compare.py:45` `_row`): team sign-ups who were not mass-email sign-ups.

Round one vs round two
- Same ranker, same weights, same simulation. Round one is Northline (first exercise event by `sequence`), round two is Harbor.
- Round two's card state comes from a refresh (`exercise_results_refresh.py`, `refresh_one_team` at line 265). `select_share` (`asking.py:206`) picks card completers: 30% / 55% / 80% of no-card profiles for better_recommendations / small_reward / required (`asking.py:80`). Under required only, 15% of all no-card profiles stop responding (`asking.py:92`). Salts: `card_completion`, `non_responding` (refresh module, lines 76-77). Share counts use round-half-up.
- A completed card copies the hidden true interests and, via `copied_card_career_goal` (`asking.py:126`, shipped HIDDEN_GOAL), the hidden true career goal. Round-one attendees gain the round-one event's topics (topic_gainers).
- The simulation reads hidden truth, never cards (ADR-0025 D6). So a refresh changes results only through the round-two ranked list.

Persistence (migration 0037 unless noted)
- One result run per (workspace, event): `uq_exercise_result_run_workspace_event` (line 328). Round is CHECK IN (1, 2) (line 342).
- Asking choice limited to better_recommendations / small_reward / required (line 233); refresh requires a choice (`ck_exercise_team_workspace_refresh_after_choice`).
- Saved settings: unique name per (workspace, event).
- Matching lists are computed on request and memoised per process; they are not stored.
- Default invite limit: 0037 set 30; **0047** (`_move(30, 60)`) sets the default to 60 and moves files still at 30. A file an instructor set to another value is left alone. The instructor route `set_invite_limit` (`services/api/smartmatch_api/routers/exercise_instructor.py:261`) still exists at 4fc80d0.

## 2. Claim-by-claim check of docs/exercise/2026-10-28-write-up.md

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Each team picks weights (major, interest, past events, goal), default 3/3/2/2 | AGREE | registry.py:142-162 |
| 2 | Weights rank students; top 60 form the list | AGREE for the code path, with a caveat | matching.py:474 cuts at invite_limit. Default 60 from 0047. Instructor can change it at 4fc80d0; 0049 on origin/main fixes it at 60 |
| 3 | Notice: 20 in 100 mass, 60 in 100 CBACH | AGREE | simulation.py:484-485 |
| 4 | Sign-up starts at 5 in 100 | AGREE | simulation.py:480 |
| 5 | +35 when a true interest matches the topic | AGREE | true_fit_lift 0.50 x 0.7 = 0.35 (simulation.py:481, 488) |
| 6 | +15 for a fitting career goal | AGREE | 0.50 x 0.3 = 0.15 (same lines) |
| 7 | +5 (1-2 past events), +10 (3+) | AGREE | simulation.py:482, 489; many_attender_events=3 |
| 8 | +5 for the targeted major | AGREE | simulation.py:483 |
| 9 | Attend 65 in 100; the 8 pre-registered attend at 65 too | AGREE | simulation.py:486; existing_attended simulation.py:682 |
| 10 | Fixed draw, same list gives same answer twice | AGREE (verified) | CSV run1_equals_run2 True on all rows, and identical CSV across PYTHONHASHSEED values |
| 11 | "The list's value is the lift" (sign-ups added over mass-only) | AGREE | exercise_results_compare.py:45-56 |
| 12 | Asking happens at the start of round two, after round one | AGREE | refresh module; impact analysis sec 5.5 |
| 13 | 230 students without a card | AGREE | counted from the fixture: 230 (`stated_interests is None`) |
| 14 | 69 / 127 / 184 completed; 35 stopped responding | AGREE with the shares | 230x0.30=69; 230x0.55=126.5 -> 127 (half up); 230x0.80=184; 230x0.15=34.5 -> 35. Actual counts from the run would come from the DB, not run here |
| 15 | Section 2 table ("5,000 simulated runs", Northline 7.2/5.3/9.4/13.8; Harbor columns) | UNVERIFIED | No script in the repo produces these numbers. docs/plans/2026-10-06-results-rule-impact-analysis.md says its scripts are scratch files. The "Best possible" row does not match that analysis (13.0/9.7 there, 13.8 here, different scale). Not reproduced. |
| 16 | "Ann's estimates agree within 0.3" | UNVERIFIED | Same reason; the 0.3 comparison is to a sample result file not checked here |
| 17 | "Major first stays flat" / "Interest first ... 13.7" | UNVERIFIED | Depends on row 15 |

## 3. Test commands and results (4fc80d0, working tree)

Commands (venv from python3.12):
- `.venv/bin/pytest tests/unit -k exercise -q -p no:cacheprovider -o addopts=""` gives **1440 passed, 2 failed, 4698 deselected** in 80 s.
- `.venv/bin/pytest tests/golden/exercise -p no:cacheprovider -o addopts="" -q` gives **66 passed**.
- Two failures: `tests/unit/test_exercise_workspace_router.py::test_the_secret_is_required_in_no_other_scope[cba]` and `[legacy_pilot]`. Cause is environmental: the gitignored repo-root `.env` sets `SMARTMATCH_EXERCISE_WORKSPACE_SECRET`, so `Settings` reads a non-None secret. With `.env` moved aside, both tests pass (2 passed). `.env` was restored unchanged. Not a code defect.
- Integration tests were not run (need PostgreSQL; no docker per instructions).

Fixture run
- Script: `docs/release/2026-10-27/matching_fixture_run.py`
- Output: `docs/release/2026-10-27/MATCHING_TEST_RESULTS.csv` (4 rows, all PASS)
- Run twice in process (same output) and once more under PYTHONHASHSEED=987 (CSV byte-identical).

| test_id | round | setting | asking | list | unique | list signed up (of 60) | mass email alone signed up (of 300) | list added | list attended |
|---|---|---|---|---|---|---|---|---|---|
| R1-NL-balanced | 1 | 3/3/2/2 | - | 60 | 60 | 20 | 7 | 16 | 8 |
| R1-NL-major-first | 1 | major first | - | 60 | 60 | 12 | 7 | 11 | 4 |
| R2-HB-balanced-before | 2 | 3/3/2/2 | none | 60 | 60 | 8 | 16 | 5 | 6 |
| R2-HB-balanced-after | 2 | 3/3/2/2 | small_reward | 60 | 60 | 16 | 16 | 9 | 11 |

Notes on the numbers
- "mass-only sign-ups" is the mass email over all 300, as the compare route defines it, so it is the same across round-one rows within the same seed.
- These are single-seed results (seed 20261027). The write-up's 5,000-seed averages are not reproduced.
- Round-two "after" uses a modelled overlay (see section 5), so its numbers are a check of the logic, not of the DB refresh.

Checks in the script (all PASS)
- List size exactly 60; no duplicate students.
- Ranking order non-increasing by value; value equals the applied-weight dot product (recomputed).
- Adjacent tied values follow information, then class year, then Ann's tiebreak_order (the file carries tiebreak_order, so the checksum permutation is not used here).
- `rank_profiles_for_event` and `exercise_ranked_list` return the same order.

## 4. Setup defects found

- `make setup` fails on Python 3.13: `Makefile:25` runs `python3 -m venv`, which picks 3.13.17 here, and smartmatch-domain requires `<3.13`. Evidence: `/tmp/claude-0/setup.log` ("requires a different Python: 3.13.17 not in '<3.13,>=3.11'"). The Makefile has no interpreter override. Fixed locally by building `.venv` with `/usr/bin/python3.12` and running the same install lines. Makefile not changed, per instructions.

## 5. Limitations

- Round-two refresh is modelled in memory (select_share, copied_card_career_goal, topic gainers) and not run through the DB repository (`apply_refresh`). Its selection follows the same salts and shares.
- Simulation and ranking are the production functions; input assembly mirrors `exercise_matching_models.py` and `exercise_results_models.py`, but uses `ParsedProfile` directly, not the DB rows.
- Invite limit 60 is set in the script as a constant. At 4fc80d0 the value is 60 by default (0047) but the instructor route can change it. The script does not read the dataset row.
- "Ann's estimates agree within 0.3" and the 5,000-run table are not verified.
- Integration and e2e tests not run.

## 6. What origin/main 763e666 changes (migration 0049, PR #444)

- `db/migrations/versions/0049_exercise_invite_limit_fixed.py` (on origin/main only): moves every data file's `invite_limit` to 60, then narrows `ck_exercise_dataset_invite_limit` from `>= 1` to `= 60`. Downgrade widens the check again.
- Reason in the migration: Ann Wang, 2026-10-22 (#413): "List size: 60, fixed for this class. No instructor setting needed." The instructor route that changed it is removed.
- Effect on this verification: at 4fc80d0 the list size can still be changed by an instructor. On origin/main it cannot. The fixture run here uses 60, which matches both.
- The matching logic (scoring, weights, tie-break, simulation coefficients) is not changed by 0049; only the invite limit's storage and constraint. Not re-tested on 763e666.

## 7. Risks and next steps

- Re-run the fixture script and unit/golden tests on 763e666 once the VM deploy decision is made. Expect the same CSV for the matching rows, since 0049 changes only the invite limit storage.
- Find or commit the script that produced the write-up's 5,000-run table, or remove that table before 2026-10-28.
- Fix `Makefile` setup to use Python 3.12 (owner decision; not done here).
- The `.env` in the repo root affects two unit tests; a clean clone would not show this.
