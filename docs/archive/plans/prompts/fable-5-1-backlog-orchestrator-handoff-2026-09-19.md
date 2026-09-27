# Fable 5.1 backlog orchestrator — handoff, 2026-09-19

Continuation of [`fable-5-1-backlog-orchestrator.md`](fable-5-1-backlog-orchestrator.md).
That file's XML block is still the operating contract (role, gates, serial
resources, iteration loop, ledger, Phase F audit). This file replaces its
**wave train**, corrects three stale claims, and carries the rulings, lessons,
and review follow-ups the first session produced.

Paste the block below as the first message of a fresh Fable 5.1 session.

---

```text
/goal Continue the backlog orchestration for IA-Smart-Match-Revamped. Read docs/archive/plans/prompts/fable-5-1-backlog-orchestrator-handoff-2026-09-19.md first, then docs/archive/plans/prompts/fable-5-1-backlog-orchestrator.md — the second file's XML block is your operating contract; the handoff file overrides its wave train and its stale claims. Read every artifact in the contract's authoritative-inputs table before first dispatch.

Mission: finish the class-exercise base under accepted ADR-0025 via one subagent per track, one independently reviewed PR per track to main. Foundation already merged (PRs #164–#181): scope, migration 0037, public router, team workspaces, FactorRegistry value object, exercise matching domain, simulation domain, ingest core, scope hardening. Remaining: instructor page + passcode session + dataset upload/re-point/unlock, matching API (ranked list, saved settings, compare, download), results API (lock, one-run, comparison panels, asking choice, refresh, round two), then mount the frontend screens incl. the #161/#162 components. Also: register row for reason-line wording, the recorded docs/ops follow-ups, and OQ-CE-REFRESH once Ann's check-in notes exist.

Hard gates — never dispatch implementation for: any OQ-SC/OQ-SE register row (no STUDENT_REGISTRY, no student→event ranking), G3 crawler, D6/D7 rewards, S12 opportunities metric, A1b IdP, metrics role-gating, board_role, published contact fields, speaker accounts, AMP adapter, Handshake, native mobile. Docs-only packets are allowed; code is not.

Rules: a safe default permits building TO the default but never closes the question — mark every placeholder in code with its OQ ID. Owner ruling 2026-09-18: Ann's sample file has not arrived; build to design spec §2's PLACEHOLDER columns, close no vocabulary in code, OQ-CE-01 stays OPEN. Never invent a number: OQ-CE-03's eight coefficients stay None and results refuse until Chau and Ann supply them. Exercise scope has no login and touches no CBA tables, routers, or auth (ADR-0025 D1/D2); hidden_true_interests never leaves the server (D6); no numeric score reaches a screen (D8). One Alembic revision per migration PR, head+1, serial queue. Regenerate OpenAPI; never hand-edit. ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, ALLOW_CLOUD_DEPLOY=false. No merging, no force-push, no skipped hooks, no production-readiness claims. A denied push or gh call means STOP and surface it — re-running it in any other form is a retry, and never push on a subagent's behalf.

Verify each subagent's PR URL, file list, CI result, migration head, and OpenAPI diff yourself, then run an independent review agent, before calling a track ready. I merge; you do not. Call UpdateGoal complete only when every unblocked track is merged or blocked with owner evidence, the gated list is provably untouched, and the contract's Phase F audit passes.
```

---

## Baseline at handoff (verify, do not trust)

| Fact | Value at 2026-09-19 |
|---|---|
| `origin/main` | `38f3e4be` (merge of #179) |
| Migration head | `0037_exercise_tables` |
| OpenAPI | 83 ops — the export builds the default CBA scope, so exercise routes correctly do **not** appear |
| Open PRs | none |
| `make imports` | 7 contracts kept |
| Owner's checkout | `README.md` modified, `LICENSE` and the two prompt files untracked — not yours; never stage them |

## Corrections to the original contract

1. **"84 TODO/FIXME markers" is false.** 26 marker-shaped matches, 0 actionable
   (`docs/plans/todo-disposition-register.md`). The 83 figure is pytest
   skip/xfail sites (`docs/plans/skip-site-inventory-2026-09-18.md`). Track done.
2. **"G1 REGISTRY_STATUS stays proposed" is stale.** Code and the G1 worksheet
   say `approved`; owner confirmed 2026-09-18 that `approved` is the contract.
   G1 is no longer a gate. G3 (live fetch gated on the S6a evidence pass) and
   A1b (pilot login does not close it) **remain gated**.
3. **"Do not dispatch CE-INGEST before the sample exists" is overridden** by the
   owner ruling above. Ingest core is merged.
4. PRs #160–#163 were merged before session one began; #163 got a post-merge
   review and its fixes shipped as #166.

## Owner rulings in force (2026-09-18)

- An agent may edit `factor_registry.py` only for the behaviour-preserving
  parameterisation — done in #173. `CBA_REGISTRY` and every CBA constant stay
  bit-identical; `tests/unit/test_factor_registry.py` and `test_scoring.py` are
  never edited.
- ADR-0015 quota-vs-spend amendment owner: GitHub user **BrooklynD23**.
- `/u/{token}` and `/i/{token}` are gated out of the exercise scope — done in #176.
- The owner squash-merges; commit hygiene inside a PR is not worth rewriting history for.

## What is merged (exercise)

| Area | Where |
|---|---|
| Scope + capability | `smartmatch_domain/product_scope.py`; `main.py` `routers_for` / `app_level_routers_for` |
| Tables (0037) | `smartmatch_persistence/exercise/schema.py`; `exercise_profile_public_columns()` is the only safe projection |
| Routers | `routers/exercise_public.py` (`GET /v1/exercise`), `routers/exercise_workspace.py` (enter, current, reset) |
| The one DB door | `services/api/smartmatch_api/exercise_dependencies.py` — routers import only this; one `ignore_imports` edge per repository |
| Errors | `exercise_errors.py` (`ExerciseError`, plain sentences) |
| Repositories | `workspace_repository.py` (incl. `active_dataset`, `repair_token_hash`, `reset_team`), `dataset_repository.py` (`create_dataset`, `load_simulation_profiles` = sole reader of the withheld column) |
| Domain | `exercise/{matching,registry,reasons,markers,determinism,simulation,asking,ingest,layout,workspace_token}.py`, `student_factors/` |
| Registry | `EXERCISE_REGISTRY` version `exercise-0.1.0`, registers only on import of `exercise.registry`; never reachable from the CBA process |
| Frontend (props only) | `apps/web/legacy-frontend/src/app/pages/exercise/` — `ExerciseResultsChart`, `ProfilePointsCounter`, `ProfileCardMockup`, list-coverage notice |

## Wave train (replaces the original)

Max 3 implementation agents; `main.py`, `exercise_dependencies.py`,
`pyproject.toml` exercise contracts, `tests/authz/test_policy_matrix.py`,
`config.py`, `routes.tsx`, the migration queue, and the OQ-CE register are
**serial** — one PR at a time each.

```
WAVE A (start here)
 1. CE-INSTRUCTOR → feat/exercise-instructor-page            [SERIAL: main.py, deps, contracts, ledger, config]
    Passcode from SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE (OQ-CE-07), PBKDF2 +
    opaque session via smartmatch_domain/pilot_credentials.py — NOT routers/auth.py.
    httpOnly cookie, rate-limited (see "open design points"). Powers: upload a
    data file (mounts ingest: POST /v1/exercise/instructor/datasets), set invite
    limit, unlock results per event, list/open any team's saved runs, reset one
    team, re-point teams at a dataset, refresh-all (stub until 3).
    Carries these review follow-ups: re-point must delete a workspace's overlay/
    settings/runs BEFORE updating dataset_id; log constraint name + dataset id
    on a scrubbed write failure; tighten the ingest integration fixture gate to
    GITHUB_ACTIONS=="true"; extend the column-name AST guard to layout.py;
    confirm with a test that punctuation-only list entries are not stored as "".
 2. OQ-CE-12 ROW → docs/oq-ce-12-reason-line-wording         [SERIAL: OQ-CE register]
    One register row: the three placeholder tie sentences, the capitalise-and-
    full-stop treatment of Ann's two phrases, and the tie-line-vs-major-only
    precedence flag. Docs only. Parallel with 1.
 3. CE-MATCHING-API → feat/exercise-matching-api             [after 1 merges — same serial files]
    Ranked list for an event (rank, reason, marker, factor keys — no number),
    who-is-on-the-list counts + coverage notice, saved settings (≤3 per
    workspace+event, enforced in the repository; fourth refused with a
    sentence), compare ?a=&b=, list.csv via csv.writer into StringIO with
    CSV-injection guarding (= + - @). year_rank comes from the dataset, never
    a hard-coded vocabulary (OQ-CE-01).

WAVE B
 4. CE-RESULTS-API → feat/exercise-results-api               [after 3]
    Lock + UNIQUE one-run rule, three comparison panels, seats_empty,
    asking-choice, per-team refresh, instructor refresh-all, round two.
    Results REFUSE with the OQ-CE-03 sentence until coefficients exist —
    that is correct behaviour, not a bug to work around.
 5. DOCS-FOLLOWUPS → docs/exercise-followups                 [parallel]
    ADR-0025 D5 says "dataset id"; spec §4.4 and the code use the dataset
    checksum. Student-recommender plan :46 and contracts doc :339 still
    describe a defaulted FactorRegistry.mode_vocabulary. registry_hash naming
    clash (ADR-0016 vs student-recommender-contracts.md ~:330) — record, do
    not resolve.

WAVE C
 6. CE-MOUNT → feat/exercise-mount-components                [SERIAL: routes.tsx]
    Entry, event picker, matching, asking-for-more, results, instructor.
    Call /v1/exercise/... literally (cookie Path=/v1/exercise; an /api prefix
    silently gets no cookie). Send X-Exercise-Request: 1 on every exercise POST.
    Mirror the workspace token pointer to localStorage per spec §15. No CBA
    portal shell, no SessionGate. SyntheticDataMarker on every screen.
 7. ENGINE-HIDE-PARAMETERS → fix/engine-hide-parameters       [own PR; touches CBA logs]
    hide_parameters=True in smartmatch_persistence/engine.py — needs the
    owner's yes first because it changes CBA error logs.

BLOCKED / WAITING ON PEOPLE
 - OQ-CE-REFRESH: Ann's 9/18 check-in notes and the 20-row sample (then the
   300-row file, due 9/25). When the sample lands in tests/fixtures/, closing
   OQ-CE-01 is a one-object change to PLACEHOLDER_LAYOUT plus the year_rank map.
 - OQ-CE-03: eight quantities from Chau + Ann (the register row lists four):
   true_fit_lift, frequent_attender_lift, same_major_lift, chance_spread,
   attend_given_signup, base_signup_rate, frequent_attender_events,
   true_interest_share_of_fit.
```

## Open owner decisions (build to current behaviour until answered)

1. Should per-team **reset** move behind the instructor passcode? Today anyone
   who types a team number can reset that team; Session 2 has no backup.
2. On re-entry, should a team's **existing workspace** win over the newest
   dataset? Today a new entry lands on the newest; old cookies keep the old one.
3. **Rate limiting** for no-login exercise routes (OQ-CE-06, owner Danny): the
   repo limiter needs a principal or `smartmatch_persistence`, both forbidden to
   exercise routers. Options: proxy/edge limiting on the VM, or a
   persistence-free in-process limiter. The instructor passcode route needs an
   answer before it ships — if none, build the in-process limiter as a marked
   OQ-CE-06 placeholder and say so.
4. Hosting: set `SMARTMATCH_EXERCISE_COOKIE_SECURE=true` on the HTTPS VM;
   `SMARTMATCH_EXERCISE_WORKSPACE_SECRET` required in the exercise scope; a
   DB role with GRANT on `exercise_*` only is the real D2 control.
5. `hide_parameters=True` on the shared engine (track 7).
6. Questions for Ann recorded on PRs #177, #179, #180: half-rounding in
   `select_share`; file layout, list separator, class_year values, key-vs-title
   for past events, "card with nothing on it", column spellings; reason-line
   wording and precedence.

## Lessons that cost time in session one

- **Every subagent card needs:** worktree isolation; the parent venv path
  (`<repo>/.venv/bin/...` or `make X VENV=<repo>/.venv`); "commit after every
  milestone"; explicit staging (no `git add -A`); push by explicit branch name;
  the denied-push STOP rule spelled out (one agent retried with a different
  refspec — surfaced to the owner, who kept the PR).
- **The /mnt/c mount wedges** full `make check`, full pytest, and cold mypy for
  30–90 min. Cards must say: targeted test files only, `timeout 900`, mypy with
  `--cache-dir ~/.cache/mypy-<track>`, **one pytest process at a time** (the
  migration harness sweeps every `smartmatch_scratch_%` DB on entry). CI proves
  the suite. `npm ci` takes 10–20 min there; run once, in the background.
- **Integration tests locally:** Docker is unavailable; PostgreSQL 16 is on
  5432. Agents create their own scratch DB, migrate, point tests at it, drop it.
  Never run deletes against the default dev DB.
- **`gh pr edit` fails silently** here (Projects-classic GraphQL). Use
  `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/<n> -F body=@file`.
  `gh pr checks` has no `--json`; parse the tab-separated output.
- **Independent review earns its keep.** It found: a fail-open registry gate
  (#173), an invented coefficient and a p=1.0 draw bug (#177), two leaks of the
  withheld column through exception text and dataclass repr (#179), a
  secret-rotation lockout (#181), an untruthful tie sentence (#180), a weakened
  naming guard (#176). Always re-review after fix commits on anything touching
  G1 modules, auth-adjacent code, or the withheld column.
- **An adversarial second-model pass on plans is worth it.** Codex
  (`gpt-6-astra`) rejected all seven tracks of an Opus plan as written; two were
  real blockers. Run the companion from the parent checkout, never a worktree.
- **Rate limits kill agents mid-edit.** Resume with SendMessage; their worktrees
  survive. Tell resumed agents to `git status`/`git diff` first and commit
  before continuing.
- import-linter cannot express `routers.exercise_*`; every new exercise router
  must be added **by hand to both exercise contracts**, and every new exercise
  repository needs its own single `ignore_imports` edge from
  `exercise_dependencies`. Nothing fails if you forget — put it on the card.
- The route ledger only sees `router = APIRouter(...)` as a bare module-level
  assignment in `routers/*.py`. No subpackages, no annotated assignment.

## First actions for the next session

1. CreateGoal (if the tool exists; session one had none — the reply ledger was the record).
2. `git fetch origin`; confirm the baseline table above.
3. Read the contract's authoritative inputs, plus PR bodies #176, #177, #179,
   #180, #181 (they hold the follow-ups and owner questions verbatim).
4. Ask the owner the two reset/re-entry decisions **once**, then dispatch
   CE-INSTRUCTOR and the OQ-CE-12 docs row without waiting for the answer.
5. Post the ledger every turn in the contract's output format.
