# Orchestrator handoff

**For:** the next orchestrating session (Opus 5, high effort)
**From:** the session that ran Wave A and launched Wave B
**Branch:** `claude/smart-match-v1-migration-sp1t49` in both
`BrooklynD23/IA-Smart-Match-Revamped` and
`BrooklynD23/Nebiux-Team-IA-West-SmartMatch`
**State at handoff:** Wave A committed and pushed through `a0a3e29`; Wave B in
flight.

Read this before reading the plan file. It records what is *true now*, what is
*in motion*, and the traps that have already cost time. The approved plan lives
at `/root/.claude/plans/idempotent-conjuring-crayon.md`; the authoritative
backlog is `docs/plans/remaining-foundation-r1-work.md`.

---

## Standing constraints — these are not negotiable

From the migration orchestrator contract supplied by the user:

- `ALLOW_REMOTE_PUSH=false`, `ALLOW_CLOUD_DEPLOY=false`,
  `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`.
- **One recorded deviation:** the session-level branch instruction requires
  pushing to `claude/smart-match-v1-migration-sp1t49`, which overrides
  `ALLOW_REMOTE_PUSH=false` **for that feature branch only**. No other remote
  write is authorized.
- The legacy repository at `/home/user/Nebiux-Team-IA-West-SmartMatch`
  (`bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42`) is **read-only evidence**. Never
  modify it. Verify with `git status --porcelain` after any work that reads it.
- No production credentials, no live PII, no live provider calls.
- **Never declare production readiness.** Nothing is deployed.
- **Do not open a pull request** unless the user explicitly asks.
- §6 of the contract: an agent may not approve its own port.

---

## Where the work actually stands

### Landed and pushed

| Commit | What |
|---|---|
| `bde3f71` | ADR-0004..0007 |
| `703a36b` | Three defects that made failure states invisible |
| `ed47376` | Containerization, with CI asserting on the built image |
| `a0a3e29` | Independent port review; one entry of four approved |

Gates at `a0a3e29`: ruff format + check, `mypy --strict` (38 files), 4 import
contracts, **323 passed / 1 skipped**, forbidden-behavior scan clean (110
files), OpenAPI current.

### In flight at handoff

Three background agents were running. **Verify their state before assuming
anything** — two earlier waves were killed mid-flight by an account spend limit,
once leaving a 669-line file that did not parse.

| Agent | Task | Owns |
|---|---|---|
| Defect planner | `docs/plans/defect-remediation.md` | that file only; read-only elsewhere |
| B1 | Worker execution + OIDC (J6/J7) | `services/worker/**`, `tests/integration/test_worker_execution.py`, `tests/contract/test_worker_boundary.py` |
| B2 | Re-drive command (J4) | `persistence/redrive.py`, `persistence/__init__.py`, `api/routers/redrive.py`, one line of `api/main.py`, `tests/integration/test_redrive.py` |

**First actions on picking this up:** `git status --porcelain`, then
`git log --oneline -6`, then run the full gate set. If an agent died mid-write,
**reject the partial output and re-task it** rather than repairing it — that
rule is in the plan for a reason.

### Not started

- **Wave C — identity model.** Design settled with the user: a **globally unique
  `external_subject`**. A draft migration is written and parse-checked at
  `/tmp/claude-0/-home-user/d8ac6fc2-95fc-5574-a251-6484b6b2ac3d/scratchpad/0003_draft.py`.
  It **must fail loudly** on duplicate subjects rather than deduplicating — that
  is the whole point, and the draft raises with the offending subjects named
  rather than letting PostgreSQL emit a one-key error. Still to do: mirror the
  constraint in `schema.py`, update the `principals.py` docstring to say the
  constraint is what makes `.one_or_none()` safe, and add tests.

  > **Correction to an earlier version of this document.** It said the drift
  > test would catch the new constraint if it were not mirrored in `schema.py`.
  > **That is false, and relying on it would have been a silent gap.** The drift
  > test compares column *name sets*, checks composite foreign keys are
  > composite, and asserts three specifically-named unique constraints exist on
  > `job_event`, `outbox_record`, and `idempotency_record`. Nothing compares
  > unique constraints as a set, and Wave C adds **no column** — so an unmirrored
  > constraint on `user_account` is invisible to CI in both directions.
  > **Do F7 before Wave C**, or mirror the constraint by hand knowing nothing
  > verifies that you did.
  **Why:** `PrincipalRepository.load_by_subject` filters on `external_subject`
  alone and calls `.one_or_none()`, while the constraint is only
  `(tenant_id, external_subject)` — so one IdP subject with accounts in two
  tenants raises `MultipleResultsFound` and 500s every authenticated request.
- **The defect backlog** — F7, F8, F9 (29 port findings), A5. The planner agent
  above is producing the remediation plan.

---

## The user's process requirements

These were given explicitly and must carry forward:

1. **Staged commits.** One coherent stage per commit, with a message that
   explains *why*.
2. **An audit before every commit.** Run the `code-review` skill at `high` on
   the staged diff. **Verify each finding against the code before acting on
   it** — reviews err in both directions.
3. **A documentation agent at the end of every wave** — Sonnet, low effort —
   to update documentation, design decisions, known bugs, and architecture
   diagrams so they reflect the repository as it actually is.
4. **Hand off to a fresh Opus 5 high orchestrator** when context gets long.

### On the audit gate

`code-review` **is** available as a skill. An earlier check with `ListSkills`
returned nothing and led to a wrong conclusion that it was absent — `ListSkills`
returns only claude.ai skills, not local ones. Invoke it with
`Skill(skill="code-review", args="high")`.

It earned its place: at high effort it found **five real defects in work that
had already passed all six gates**, including one where a fix had recreated the
original bug's shape one layer down. Do not skip it, and do not substitute your
own read for it.

---

## Traps that have already cost time

- **PostgreSQL and Docker do not survive** an agent dying or a daemon restart.
  Re-run `make db-up` and restart `dockerd` before trusting a test count. A run
  reporting *"216 passed, 107 skipped"* means the database is down and the
  integration suite silently skipped — **not** that things pass.
- **`curl` to `127.0.0.1` goes through the agent proxy** and fails with exit 56.
  Use `curl --noproxy '*'`. Never disable TLS verification or unset
  `HTTPS_PROXY`.
- **`docker manifest inspect` fails against Docker Hub here** even for valid
  digests. Check `docker images --digests` against the local mirror instead.
  A digest that looks fabricated may be fine — verify before accusing.
- **`git add -A` before scanning, not after.** `tools/scan_forbidden.py` reads
  tracked *and* untracked-not-ignored files; scanning first is how a violation
  once shipped past a locally-clean run.
- **Ruff reformats between edits**, so multi-line edit anchors go stale. Match
  one distinctive line, or rewrite the whole function.
- **`Row.count` is the tuple method, not the column.** Label ambiguous columns
  in `RETURNING`. Strict typing caught this; nothing else did.
- **`IN (SELECT … LIMIT n FOR UPDATE SKIP LOCKED)` re-executes** in PostgreSQL
  and claims every row. Use a CTE. Observed here: a `limit=2` claim took all 5.
- **`sa.func.make_interval(secs=…)` does not work** — SQLAlchemy's generic
  `func` emits no named arguments. Compute intervals in Python.
- **`str(engine.url)` masks the password** as `***`. Use
  `render_as_string(hide_password=False)`.
- **Do not assert controls that do not exist.** A test asserting unit-scoped job
  reads had to be corrected: `job` carries no owning unit (that is backlog A5).
- **Stray wheels.** 28 MB of pandas/numpy wheels were once downloaded into the
  repository root by tooling run from the wrong directory. `*.whl` and
  `*.tar.gz` are now gitignored; if you see them again, something is running
  with the wrong cwd.

---

## What I would not trust without re-checking

Stated plainly, because a handoff that only lists successes is not useful:

- **Four ADRs were committed as `bde3f71` outside my visible actions.** Contents
  verified clean (exactly the four files, correctly ordered before the fix
  commit), but I did not issue that commit and cannot account for it. If
  something similar appears, inspect before building on it.
- **F-29 in `port-verification.md`** reports 5 pre-existing dispatcher test
  failures against a 295-test baseline. Those were an artifact of reading the
  file while another agent was mid-edit; the suite is green now (26 dispatcher
  tests pass). The finding is stale, not wrong at the time.
- **The `/u/{token}` 200 response** now advertises `application/json` alongside
  `text/html`. The seven error responses are correct (JSON only), which was the
  harmful half; the success response carries a cosmetic extra media type. Fix it
  properly if you touch that route.
- **The port review's severity ratings are its own.** Where the remediation plan
  disagrees with them, the plan was asked to argue the case — read the argument,
  do not defer to either automatically.
- **ADR-0004 understates the schema divergence.** It names `org_unit.tenant_id`
  as the example of a `schema.py` foreign key missing the migration's
  `ondelete`. In fact **all seven** tenant-parent foreign keys in `schema.py`
  carry no `ondelete`, while the migrations deliberately specify `RESTRICT` for
  some and `CASCADE` for others — so the hand-written mirror cannot represent a
  distinction the database is actually making. Verified by count. The ADR is not
  wrong, it is narrower than the truth; widen it when F7 lands.

---

## The shape that has worked

Waves of agents with **strictly disjoint file ownership**, an explicit allowlist
per agent, agents that never commit, and an orchestrator that verifies every
claim before staging. Every rule in that list was earned by a failure.

The single highest-value habit: **verify the agent's claim against the code
before acting on it.** In this session that caught a fabricated-looking digest
that was real, a real digest verification that failed for proxy reasons, a
"green" test run that was silently skipping the database, a CI gate that could
never have passed, and a test that could not fail.
