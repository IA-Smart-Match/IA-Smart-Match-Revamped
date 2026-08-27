# PR #3 — verification evidence

What was run, what it produced, and what could not be verified here. Commands
are quoted so a reader can re-run them rather than take this document's word.

Environment: WSL2 / Ubuntu 24.04, Python 3.12.3, PostgreSQL 16.2, Terraform
1.9.8, no root. Worktree `.claude/worktrees/pr3` on
`claude/pr1-blockers-todos-er5heu`.

---

## 1. Branch integration

    git merge origin/main --no-commit --no-ff    # clean auto-merge
    git commit --no-edit                         # afd80c8

`.github/workflows/verify.yml` was the only file needing resolution, and the
merge kept both sides. Verified rather than assumed:

| Required element | Evidence |
|---|---|
| PR #2 — gitleaks as a tool, not the licensed action | `verify.yml:272`, `go install github.com/zricethezav/gitleaks/v8@v8.30.1`. The only other mention of `gitleaks-action` is the comment at `:260` explaining why it is not used. |
| PR #2 — `.gitleaks.toml` | present at the repository root; `git diff origin/main` empty |
| PR #2 — regenerated runtime lock | `requirements/runtime.txt`; `git diff origin/main` empty |
| PR #3 — environment isolation | `verify.yml:135-143`, a **step** inside the `isolation:` job (`:109`) — not a job of its own. The plan called these "two jobs"; that half is a job and a step. Both gate every pull request, which is what the requirement was about. |
| PR #3 — supply-chain / SBOM job | `verify.yml:199`, `supply-chain:` — its own job: license policy plus a CycloneDX 1.5 SBOM |

**Baseline before any new implementation:** `make check` green; 676 passed,
1 skipped, 368 deselected. Integration separately: 368 passed. Total 1,044
passed, 0 failed.

---

## 2. A5 — `job.owning_unit_id`, and one authorizer

Migration `0006` adds the column; `smartmatch_api.job_authz` is the single
authorizer behind job status, job events, re-drive and abandon.

Read off the **live** schema rather than the migration source:

    \d job
    owning_unit_id | uuid | not null
    "fk_job_owning_unit" FOREIGN KEY (tenant_id, owning_unit_id)
        REFERENCES org_unit(tenant_id, id) ON DELETE RESTRICT

The composite reference is what makes a cross-tenant owning unit
unrepresentable rather than merely rejected.

The evaluation order is the policy's own, called rather than restated. The actor
exception is applied only after `evaluate()` returns a denial that is *not*
`principal_suspended`, `tenant_mismatch`, or `explicit_resource_deny` — so it
cannot override any of the three. Re-drive and abandon do not get it at all.

**Request and response shapes are unchanged.** The OpenAPI diff in `7e27268` is
docstring-only — two `description` strings, no schema, parameter, or status-code
change.

---

## 3. F12 — the redundant constraint

`0007` drops `uq_user_account_tenant_subject` and keeps the global constraint
that made it redundant (ADR-0008). Read off the live database:

    SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
     WHERE conrelid='user_account'::regclass AND contype='u';

    uq_user_account_external_subject | UNIQUE (external_subject)
    uq_user_account_tenant_id        | UNIQUE (tenant_id, id)

`uq_user_account_tenant_subject` is gone; global subject uniqueness is intact.

---

## 4. Gates

All run at `7e27268`.

| Gate | Command | Result |
|---|---|---|
| Formatting | `make format-check` | 134 files formatted |
| Lint | `make lint` | all checks passed |
| Strict typing | `make typecheck` | no issues, 45 source files |
| Import contracts | `make imports` | 4 kept, 0 broken |
| Unit / authz / contract / golden | `pytest -m "not integration"` | **714 passed, 1 skipped** |
| Integration | `pytest -m integration` | **380 passed** |
| Forbidden scan | `make scan` | clean, 164 files |
| Memory ledger | `make memory` | clean, 3 records |
| OpenAPI drift | `make openapi-check` | in sync after regeneration |
| Licenses | `tools/supply_chain.py licenses` | 43 allowed, 4 recorded exceptions, 0 undetermined |
| Environment isolation | `tools/env_isolation_check.py` | 4 environments, 40 identifiers, none shared |
| Terraform format | `terraform fmt -check -recursive` | exit 0 |
| Terraform validate | per environment, `-backend=false` | valid in classroom, dev, staging, prod |
| Fresh migration | `alembic upgrade head` on an empty database | 0001 → 0007 clean |

Total: **1,094 passed, 1 skipped, 0 failed.**

### One failure worth recording, because the cause is not obvious

Three tests in `test_agent_memory_check.py` failed while `README.md` had
uncommitted changes, asserting `stale-source` and receiving `dirty-source`.
That is the checker behaving correctly — `is_dirty` short-circuits before the
blob comparison (`tools/agent_memory_check.py:363`) — and the tests depend on
the working tree being clean for the files they cite. They passed once the work
was committed. Nothing was changed to make them pass.

---

## 5. Independent evidence

### Revert-check: do the tests fail against the behaviour they claim to fix?

Method: keep tests at HEAD, revert only the commit's production files to its
parent, run the focused tests, restore. Run in a throwaway worktree against a
separate database so it could not collide with concurrent work.

| Case | Baseline | With production reverted | Verdict |
|---|---|---|---|
| J9 / J8 `3243e00` | 48 passed | **3 failed** — worker route boundary, and both stale-lease writes | tests pin the fix |
| J16 `41d47da` | 92 passed | **4 failed** — all four refusal-charging cases | tests pin the fix |
| F2b / F5 `80a07ea`, tools deleted | 101 passed | collection error | weak: proves import, not behaviour |
| F2b / F5 `80a07ea`, Terraform config reverted, tools kept | 52 passed | **1 failed** — `test_the_committed_environments_are_clean` | tests pin the fix |

This closes the caveat `3243e00` recorded against itself: that its per-test
revert-check evidence "was never reported". It has now been reported, by
something that did not write those tests.

### F9 / migration-manifest counts, re-measured

    pytest <file> --collect-only -q

| Entry | Claimed | Measured | Result |
|---|---|---|---|
| MM-003 `tests/unit/test_eli.py` | 22 | 22 | confirmed |
| MM-004 `tests/unit/test_ingest.py` | 21 | 21 | confirmed |
| MM-005 `tests/unit/test_feedback.py` | 21 | 21 | confirmed |

Measured in a pristine worktree at the merge commit, so a concurrent edit could
not have moved the number.

---

## 6. Independent re-verification

Every gate in §4 and every claim in §1–§3 was re-run and re-audited by a
reviewer that wrote none of this code, against `7e27268`. All eighteen claims
came back confirmed, each cited to `file:line`, with the foreign-key definition
and the `user_account` constraint set read off a database the reviewer built
itself rather than off the migration source. It also ran both downgrades and
re-upgraded, which §4's fresh-migration row does not cover.

It corrected one thing in this document: environment isolation is a *step*
inside the `isolation` job, not a separate job. §1 now says so.

### Adversarial review

Twenty hostile principal/job combinations, written without reusing the repo's
own tests, since those are the artifact under audit. **No exploitable defect
was found**, and the four specific attacks were traced to ground:

- The actor exception cannot override suspension, tenant mismatch, or an
  explicit deny — `_decide` raises at `job_authz.py:253` before reaching the
  actor branch at `:257`.
- A row with a `NULL` or unparseable owning-unit path is refused at `:229`
  before the policy is consulted. Four path shapes were tried against the
  strongest possible principal — the job's own actor holding a root `admin`
  membership — and all four were denied.
- `actor_id is None` cannot match a principal, both by the null guard at `:257`
  and because `ResolvedPrincipal.user_id` is non-optional.
- Re-drive and abandon genuinely lack the actor exception.

Also checked and sound: grant identifiers are canonical `str(UUID)` on both
sides, so an explicit deny cannot be defeated by casing; and `iawest.cpp.eng`
does not cover `iawest.cpp.engineering.ie`, because `OrgPath.contains` compares
label tuples rather than string prefixes.

### One latent fail-open, now closed

`_STRUCTURAL_DENIALS` is an allowlist: `_decide` raises for a reason *in* it and
lets the actor exception override any reason *not* in it. Nothing related that
set to the vocabulary `evaluate` can actually emit — the constant was referenced
only inside `job_authz.py`. A denial added to the policy later would have landed
silently on the **overridable** side, and a job's own actor would have read past
it.

Two tests now hold the two sets together. The vocabulary is read out of
`policy.py` by AST rather than restated, because a restatement would agree with
the original until the day it mattered. Both were shown to fail before being
kept:

| Mutation | Result |
|---|---|
| drop `explicit_resource_deny` from `_STRUCTURAL_DENIALS` | `test_a_new_denial_reason_must_choose_a_side` **fails**, and so does the behavioural `test_an_explicit_deny_blocks_the_jobs_own_actor[read]` |
| add a new denial reason to `policy.py` | both new tests **fail**, naming the undecided reason |

### Gaps recorded rather than closed

- **No test demonstrates SSE re-authorization behaviourally.** Every request
  re-runs `authorize_job_read` and the response is bounded, so the property
  holds by construction and the call is AST-verified — but nothing revokes a
  membership between two requests and asserts the reconnect is refused.
- **A reason-code precedence inversion, cosmetic and fail-closed.** Because the
  unusable-path refusal precedes `evaluate`, a suspended principal on a
  path-less row is denied `no_grant` rather than `principal_suspended`. Only the
  audit reason differs, and the row shape is unreachable from the four routes.
- `test_policy_matrix.py:975` asserts the shared authorizer is *among* a route's
  authorizers, not the only one. No private helper exists today — a repo-wide
  grep finds zero `_authorize*` definitions in the routers — so this is latent.

---

## 7. Four counts that were wrong, and are now right

Found while checking claims rather than by looking for them:

- `README.md`, `apps/web/README.md` and `docs/plans/remaining-foundation-r1-work.md`
  each said `apps/web/DESIGN.md` Part 2 lists **eight** decisions. It lists
  **eleven** (D-1…D-11).
- `apps/web/DESIGN.md` said the OpenAPI document describes **five** endpoints.
  It describes **seven** — measured, not counted by eye.

Correcting a factual count in `DESIGN.md` Part 1 does not resolve any decision
in Part 2, which remains open pending the UI team.

---

## 8. What could NOT be verified here

State these to whoever reviews the PR; none is a code defect.

- **`gh` CLI returns `HTTP 401: Bad credentials`.** PR #3 could not be read and
  **the PR summary was not updated**. The content intended for it is this file.
- **`git fetch` and `git push` fail authentication.** `origin/main` was merged
  from the local remote-tracking ref `cc7cfe4`, which carries both PR #2 fixes,
  but **could not be confirmed to be the newest `origin/main`**. Nothing has
  been pushed; the work is local commits on
  `claude/pr1-blockers-todos-er5heu`.
- **The environment had no PostgreSQL, no Terraform, no Docker daemon and no
  root.** PostgreSQL 16.2 was built from source into `~/pg16` with contrib
  `ltree` and `uuid-ossp`; Terraform was installed as a static binary. The test
  database is therefore not the CI database, and CI remains the authority.
- **Terraform `validate` ran with `-backend=false`.** It checks configuration
  validity, not that a plan would apply against real infrastructure.

---

## 9. Adoption gates that remain open

Not blockers on this branch — decisions that belong to IA West. Recorded in
[`../decisions/pilot-decisions.md`](../decisions/pilot-decisions.md).

- D1 (factor registry / gate G1), D2 (ELI parameters), D3–D5 deferred.
- **D6 is not closed.** The coordinator is recorded as the *operational*
  administrator of reward availability; no budget holder is named and no budget
  exists.
- D7, D8, D9 have tentative positions only.
- **Q1 is closed as a *handling* decision, not an erasure.** The six legacy
  paths naming real people remain in the archive's history, so the MM-A09
  exposure is unchanged and still gates D9.
- D-0 and D-1…D-11 deferred; `apps/web/DESIGN.md` stays unresolved.
- FERPA is described as aligned with minimum-disclosure principles. **No
  compliance claim is made**, and formal institutional review is an open gate.

The prototype prompt pack is
[`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md). It is
non-authoritative, closes nothing, and its cross-role flow checklist is
deliberately unticked: the prompts have not been run and no prototype exists.
