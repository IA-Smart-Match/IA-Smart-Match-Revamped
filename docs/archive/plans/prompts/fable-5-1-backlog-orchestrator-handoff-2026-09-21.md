# Fable 5.1 backlog orchestrator — handoff, 2026-09-21

Continuation of [`fable-5-1-backlog-orchestrator-handoff-2026-09-19.md`](fable-5-1-backlog-orchestrator-handoff-2026-09-19.md)
and [`fable-5-1-backlog-orchestrator.md`](fable-5-1-backlog-orchestrator.md).
The second file's XML block is still the operating contract. The 09-19 handoff
still holds for owner rulings of 09-18, the "what is merged" map, and the
session lessons. **This file replaces its wave train, its open-decisions list,
and adds the rulings and lessons of session two.**

Paste the block below as the first message of a fresh Fable 5.1 session.

---

```text
/goal Continue the backlog orchestration for IA-Smart-Match-Revamped. Read docs/archive/plans/prompts/fable-5-1-backlog-orchestrator-handoff-2026-09-21.md first, then the 2026-09-19 handoff, then docs/archive/plans/prompts/fable-5-1-backlog-orchestrator.md — the last file's XML block is your operating contract; the newest handoff overrides older wave trains and stale claims. Read every artifact in the contract's authoritative-inputs table before first dispatch.

Mission: finish the class-exercise base under accepted ADR-0025 via one subagent per track, one independently reviewed PR per track to main. Merged so far (PRs #164–#188): scope, migration 0037, public router, team workspaces, FactorRegistry value object, matching domain, simulation domain, ingest core, scope hardening, instructor page + passcode session + dataset upload/re-point/unlock (#184), reset-behind-passcode and existing-workspace-wins rulings (#186), engine hide_parameters env-switchable (#185), OQ-CE-12 register row (#182), two docs follow-ups (#183, #187), matching API — events, ranked list, who-is-on-the-list, saved settings, compare, CSV (#188). Remaining: results API (lock, one-run, three comparison panels, seats_empty, asking choice, per-team refresh, instructor refresh-all replacing the stub, round two); then mount the frontend screens incl. the #161/#162 components; the exercise hosting doc once the owner answers hosting decisions 1+2; split routers/exercise_instructor.py (898 lines); OQ-CE-REFRESH once Ann's check-in notes and sample exist.

Hard gates — never dispatch implementation for: any OQ-SC/OQ-SE register row (no STUDENT_REGISTRY, no student→event ranking), G3 crawler, D6/D7 rewards, S12 opportunities metric, A1b IdP, metrics role-gating, board_role, published contact fields, speaker accounts, AMP adapter, Handshake, native mobile. Docs-only packets are allowed; code is not.

Rules: a safe default permits building TO the default but never closes the question — mark every placeholder in code with its OQ ID. Ann's sample has not arrived: build to design spec §2's PLACEHOLDER columns, close no vocabulary in code, OQ-CE-01 stays OPEN — the class-year tie-break order is the EMPTY mapping (PLACEHOLDER_CLASS_YEAR_RANK) until Ann answers, so Ann's "ordered by year" sentence is never printed today. Never invent a number: OQ-CE-03's eight coefficients stay None and results refuse until Chau and Ann supply them. Exercise scope has no login and touches no CBA tables, routers, or auth (ADR-0025 D1/D2); hidden_true_interests never leaves the server — not in a field, Field description, HANDLER DOCSTRING, log, exception text, repr or CSV (D6); no numeric score reaches a screen (D8). One Alembic revision per migration PR, head+1, serial queue. Regenerate OpenAPI; never hand-edit. ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, ALLOW_CLOUD_DEPLOY=false. No merging, no force-push, no skipped hooks, no production-readiness claims. A denied push or gh call means STOP and surface it — re-running it in any other form is a retry, and never push on a subagent's behalf. A push REJECTED as non-fast-forward means someone else is on the branch: STOP, identify the commits, ask the owner.

Verify each subagent's PR URL, file list, CI result, migration head, and OpenAPI diff yourself, then run an independent review agent (and re-review after every fix round on anything touching locks, auth-adjacent code, or the withheld column) before calling a track ready. I merge; you do not. Call UpdateGoal complete only when every unblocked track is merged or blocked with owner evidence, the gated list is provably untouched, and the contract's Phase F audit passes.
```

---

## Baseline at handoff (verify, do not trust)

| Fact | Value at 2026-09-21 |
|---|---|
| `origin/main` | `748dc55c` (merge of #188) |
| Migration head | `0037_exercise_tables` — no exercise migration since |
| OpenAPI | 83 ops — the export builds the CBA scope, so exercise routes correctly do **not** appear |
| Open PRs | none |
| `make imports` | 7 contracts kept |
| Owner's checkout | `README.md` modified; untracked: `LICENSE`, the prompt files in `docs/plans/prompts/`, `docs/archive/plans/owner-open-decisions-2026-09-19.md`, `docs/archive/plans/2026-09-19-pr188-review-fix-plan.md` — not yours; never stage them |
| Worktrees | ~30 under `.claude/worktrees/` — all session-two branches are merged; safe for the owner to prune, never prune one holding unpushed commits |

## Merged in session two

| PR | Track | Notes |
|---|---|---|
| #182 | OQ-CE-12 register row | reason-line wording + precedence, OPEN, owner Ann |
| #183 | DOCS-FOLLOWUPS | ADR-0025 D5 → dataset checksum; shipped `mode_vocabulary`; `registry_hash` clash logged as B-10 |
| #184 | CE-INSTRUCTOR | `routers/exercise_instructor.py` (+ `_models`), `exercise_rate_limit.py`, `exercise/instructor_session.py`, `exercise/instructor_repository.py`. Stateless signed 12 h session; raw `text/csv` upload; in-process limiter `PLACEHOLDER OQ-CE-06`; instructor cookie Secure by default |
| #185 | ENGINE-HIDE-PARAMETERS | `SMARTMATCH_DB_HIDE_PARAMETERS` default on; Alembic env.py covered. **Floor, not ceiling:** PostgreSQL's own `DETAIL: Failing row contains (…)` is not suppressed — the per-repository scrubbers stay. Owner question recorded as adr-backlog **B-11**. Codex `gpt-6-astra` reviewed; Devin skipped by owner |
| #186 | Rulings + #184 LOWs | team reset route removed (instructor-only); `entry_dataset_for` (existing workspace wins); `WORKSPACE_MEMBERSHIP_LOCK_KEY` advisory lock; B-10 cites ADR-0016 Proposal 9 |
| #187 | DOCS-FOLLOWUPS-2 | dated "as shipped" notes in the design spec; `.env.example` gains the instructor passcode var |
| #188 | CE-MATCHING-API | `routers/exercise_matching{,_models,_csv,_weights}.py`, `exercise/settings_repository.py`, `team_view_repository.py`, `instructor_rows.py`. 7 routes under `/v1/exercise/workspaces/current/…`. `SAVED_SETTING_LOCK_KEY`. Two contributors worked its last round (see lessons) |

## Owner rulings in force (added 2026-09-19 → 09-21)

- Per-team reset is behind the instructor passcode. Shipped #186.
- On re-entry a team's existing workspace wins; only a re-point moves a team. Shipped #186.
- `hide_parameters` on, env-switchable. Shipped #185.
- Devin audit on #185: skipped by the owner; Codex review accepted.
- Class-year order: the orchestrator applied the standing rulings (invent nothing, close no vocabulary) → empty mapping. The owner was told and did not overrule; still theirs to overrule.
- Global lock order, every exercise path: **membership key → saved-settings key → row locks** (row locks include `FOR UPDATE`, `UPDATE`/`DELETE`, and the FK `FOR KEY SHARE` an insert takes). The per-path table lives on `SAVED_SETTING_LOCK_KEY`'s docstring — any new path that touches workspace / settings / overlay / runs rows must be added to it.

## Wave train (replaces the 09-19 one)

Max 3 implementation agents. Serial (one PR at a time each): `main.py`,
`exercise_dependencies.py`, `pyproject.toml` exercise contracts,
`tests/authz/test_policy_matrix.py`, `config.py`, `routes.tsx`, the migration
queue, the OQ-CE register.

```
WAVE A (start here)
 1. (done) #188's merged head aaf45bcf was independently re-reviewed READY:
    merge integrity clean (no test lost or shadowed, d5ae265c's logic survived
    the extractions), one saved-settings acquire in repoint_workspaces, both
    lock tests real, D6/D8/D1/D2 clean. THREE LOW items to carry into track 2:
    (a) tests/unit/test_exercise_matching_router.py `_models_in_modules()`
        (~:1378) still walks only (exercise_matching, exercise_matching_models)
        — widen it to the same module tuple as the source walks so a response
        model added to _csv/_weights cannot escape the D6/D8 field walk;
    (b) the NOWAIT-probe rationale overstates the mechanism — SQLAlchemy
        invalidates on is_disconnect(), not on every OperationalError; a
        lock_timeout more usually leaves a failed transaction. Correct the
        sentence; the conclusion stands;
    (c) the lock order is described in three places (the SAVED_SETTING_LOCK_KEY
        walk, repoint_workspaces' docstring, reset_team's docstring) — keep the
        table as the one source and make the other two pure cross-references.
 2. CE-RESULTS-API → feat/exercise-results-api          [SERIAL files; start here]
    Lock + UNIQUE one-run rule ("This team has already run results for this
    event."), three comparison panels (team list / email everyone / round-one),
    seats_empty = 60 − 8 − attended as named constants, asking-choice,
    per-team refresh (once, after the choice), instructor refresh-all REPLACING
    the refusing stub, round two with non_responding excluded. Results REFUSE
    with the OQ-CE-03 sentence until coefficients exist — correct behaviour.
    `load_simulation_profiles` stays the ONLY reader of the withheld column.
    Overlay writes join the lock-order table. Half-rounding in `select_share`
    is Ann's question (OQ-CE-04) — keep current behaviour, marked.
    Do NOT add to routers/exercise_instructor.py (898 lines) — see 4.
 3. EXERCISE-HOSTING-DOC → docs/exercise-hosting        [parallel; needs owner decisions 1+2]
    Spec §17 points at docs/operations/vm-deploy.md, which describes no
    exercise hosting at all. Write the exercise section: scope var, the three
    exercise env vars, DB role with GRANT on exercise_* only, cookie Secure,
    proxy rate limiting (OQ-CE-06), 5-second budget measured on the address.
    Also carry: the `.env.example` wording nit from #187's review ("A value
    that is long enough only before stripping is refused").

WAVE B
 4. SPLIT-INSTRUCTOR-ROUTER → refactor/exercise-instructor-session   [SERIAL: pyproject contracts]
    Move the passcode/session block (~230 lines: _LOGIN_LIMITER, _client_key,
    instructor_login, _too_many_attempts, _passcode_refused, instructor_logout,
    _set_instructor_cookie) into its own router-package module. Behaviour-
    preserving; both import contracts by hand; ledger still sees both routers.
    Best done BEFORE or inside 2 if refresh-all needs room.
 5. CE-MOUNT → feat/exercise-mount-components           [SERIAL: routes.tsx; after 2]
    Entry, event picker, matching, asking-for-more, results, instructor.
    Call /v1/exercise/... literally (cookie Path; an /api prefix silently gets
    no cookie). X-Exercise-Request: 1 on every exercise POST/PUT/DELETE.
    Reset button on the INSTRUCTOR page only. Upload sends a raw text/csv body
    with label/source_filename query params (owner decision 3 still open — if
    it flips to multipart, one handler + one screen change). Show
    unrankable_profile_count beside the who-is-on-the-list table and
    unlisted_class_years somewhere honest. localStorage mirror per spec §15.
    No CBA portal shell, no SessionGate. SyntheticDataMarker on every screen.

BLOCKED / WAITING ON PEOPLE
 - OQ-CE-REFRESH: Ann's check-in notes + the 20-row sample (then the 300-row
   file, due 9/25). Closing OQ-CE-01 = one object in layout.py + filling
   PLACEHOLDER_CLASS_YEAR_RANK + the year_rank map.
 - OQ-CE-03: eight coefficients from Chau + Ann. Gates the Oct 16 milestone.
 - adr-backlog B-10 (registry_hash naming) and B-11 (repo-wide "error text
   never carries bound values"; `_int_from_env` also echoes a raw value in a
   ValueError) — owner decisions, recorded, not built.
```

## Open owner decisions

The full list — 21 decisions with options, recommendations and ready-to-paste
messages for Ann and Chau — is in `docs/archive/plans/owner-open-decisions-2026-09-19.md`
(untracked) and at https://claude.ai/artifact/1uF9fSM3VFZpcnrScrFNHP (private
to the owner). Still unanswered and blocking soonest:

1. Hosting settings on the VM (cookie Secure, workspace secret, `exercise_*`-only DB role).
2. The site's stable address (OQ-CE-06).
3. Upload shape: keep raw `text/csv` (recommended) or multipart.
4. Instructor session: keep the signed cookie (recommended) or a session table.
5. Send the Chau message (coefficients, default weights, points) and the Ann message (10 questions).

Ask 1–4 **once** at session start; build to current behaviour meanwhile.

## Lessons that cost time in session two

- **Hand-back reports sometimes never arrive** — only the stop notice does. Do
  not wait: verify from the branch (`git log`, `gh pr view`, `gh pr checks`),
  and if you need the text, SendMessage the agent "re-send your final report,
  no new work". Never read the `.output` JSONL.
- **A second actor can push to your agent's branch** (another Claude window, a
  Devin session — commits carry this machine's git identity plus a
  `Co-Authored-By` trailer). Symptom: push rejected non-fast-forward. STOP,
  show the owner the commits, get the other side frozen, then MERGE the remote
  in (never rebase a pushed branch, never force). Tell cards: "if main moved,
  merge origin/main".
- **Agent pushes can be denied by the auto-mode classifier** ("Out-of-Place
  Publication") even with the owner's relayed yes — a relayed quote is not a
  grant. The owner pushes by hand: `! git -C <worktree> push origin <branch>`.
  If the owner merges before a follow-up commit is pushed, fold it into the
  next PR (#183's citation fix rode in #186).
- **Fix rounds introduce defects.** #188 round 1 added a lock that created the
  wait-for cycle it claimed to exclude; only the re-review caught it. Lock
  analysis must include row locks and FK `FOR KEY SHARE`, not just advisory keys.
- **A NOWAIT / lock_timeout probe cannot observe lock ORDER here**: the timeout
  surfaces as `OperationalError`, SQLAlchemy invalidates the pooled connection,
  and the probe sees a free row either way. Read the statement sequence with a
  `before_cursor_execute` listener instead. Blocking probes are fine for "is
  the key held at all".
- **FastAPI publishes handler docstrings** as OpenAPI descriptions — D6 covers prose.
- **pydantic quotes dict keys in error `loc`** and the shared `errors.py`
  reflects them: bound caller-supplied keys with a `mode="before"` validator,
  not after validation.
- **Parallel agents' integration runs collide**: the scratch harness sweeps
  every `smartmatch_scratch_%` database. Cards: name scratch DBs outside that
  pattern, `pgrep -af pytest` first (mind the self-match trap), create AND
  migrate your own DB, set `SMARTMATCH_DATABASE_URL`, drop it after; in a
  worktree set `PYTHONPATH` to the worktree packages so alembic does not
  resolve the parent's editable install. Namespace scratchpad files per track.
- **npm audit `400 Invalid package tree`** in the `web` job is a registry-side
  flake documented in `verify.yml` — `gh run rerun <id> --failed`.
- **Devin MCP** fails with "no org_id could be resolved from your token": the
  user-scope `devin` server needs an `X-Org-Id` header (owner runs
  `claude mcp remove devin -s user` + re-add with both headers, then restarts).
  `mjinno09/devin-mcp` was audited clean but has no PR-review tool — not useful.
  The owner was advised to rotate the Devin key.
- **Codex** (`gpt-6-astra`) via the `codex:codex-rescue` agent works from the
  parent checkout and found a real defect on #185 (a warning that logged the
  raw env value). Worth using on anything touching logs or secrets.
- **Files creep past 800 lines in fix rounds.** Put "report line counts of every
  changed file" in every card's return format.

## First actions for the next session

1. CreateGoal if the tool exists; otherwise the reply ledger is the record.
2. `git fetch origin`; confirm the baseline table.
3. Read the contract's authoritative inputs plus PR bodies #184, #186, #188
   (route tables, lock-order table, notes for CE-RESULTS-API and CE-MOUNT).
4. Ask owner decisions 1–4 once.
5. Dispatch CE-RESULTS-API immediately (it carries #188's three LOW review
   items); dispatch EXERCISE-HOSTING-DOC only if decisions 1+2 are answered;
   SPLIT-INSTRUCTOR-ROUTER waits for CE-RESULTS-API (shared pyproject contracts)
   unless refresh-all needs the room first.
6. Post the ledger every turn in the contract's output format.
