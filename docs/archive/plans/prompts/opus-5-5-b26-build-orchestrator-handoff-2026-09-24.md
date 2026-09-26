# B26 build orchestrator — handoff (2026-09-24, ~10:00 PDT)

Output style: follow ~/.claude/rules/common/subagent-output.md (i-have-adhd)

You are the **B26 top orchestrator** (Opus 5.5). You don't write feature code. You dispatch Opus track orchestrators and fixers, rule on cross-track questions, keep the ledger and write the final report. The owner merges; you never merge.

- Repo: `/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped` (WSL; source under `python/`, `services/`, `apps/web/legacy-frontend/`, `db/`, `tools/`).
- Background: `docs/archive/plans/prompts/opus-5-5-b26-build-orchestrator-handoff-2026-09-22.md` (role, pipeline).
- Ledger: `docs/plans/b26-tracks/LEDGER.md` on branch `docs/b26-ledger`, worktree `.claude/worktrees/b26-ledger`, last commit `a35493d6`, stale.
- Memory: `b26-build-wave-state-2026-09-22.md`.

**All 16 tracks have a PR.** Each is Opus-reviewed APPROVE with CI green. What remains is 3 owner rulings to apply, a stack sync, and the final report.

---

## 1. PR table (all open, none merged)

| Track | PR | Branch | Head | CI | Review | Worktree (`.claude/worktrees/`) |
|---|---|---|---|---|---|---|
| T1 | #210 | feat/b26-t1 | 2c89266b | 10/10 | APPROVE | agent-af93be6a3beecb25d |
| T7 | #211 | feat/b26-t7 | 4225d64d | 10/10 | APPROVE | agent-a20a5fdb6774064a7 |
| T2 `0038_speaker_availability` | #212 | feat/b26-t2 | 1ca64299 | 10/10 | APPROVE | agent-a37a5031a362099a8 |
| T6a | #213 | feat/b26-t6a | 6e1857fb | 10/10 | APPROVE (security) | agent-a09e5a74130348692 |
| T8b | #214 | feat/b26-t8b | 55624cdd | 10/10 | APPROVE | agent-a1e66ef42d01b2a41 |
| T3 | #215 | feat/b26-t3 | 8aacf50e | 10/10 | APPROVE | agent-af8b51cfdba51c68c |
| T5 | #216 | feat/b26-t5 | cc2ac502 | 10/10 | APPROVE | b26-t5 |
| T6b-1 `0039_speaker_portal` | #217 | feat/b26-t6b-1 | d5a39b48 | 10/10 | APPROVE (security) | agent-ac08185d91afe1891 |
| T8a `0040_booking_cancellation` | #218 | feat/b26-t8a | a622fb10 | 10/10 | APPROVE | agent-a2fb62b676e9666d3 |
| T6b-2 | #219 | feat/b26-t6b-2 | ee1c0fd6 | 10/10 | APPROVE (security) | b26-t6b-2 |
| T4 `0041_batch_speaker_request` | #220 | feat/b26-t4 | 0237b79b | 10/10 | APPROVE | agent-aed5d2b25e7831f62 |
| T8c (3.0.0 proposed, not current) | #221 | feat/b26-t8c | a4ccfa5d | 10/10 | APPROVE | b26-t8c |
| T6b-3 (top risk) | #222 | feat/b26-t6b-3 | 2fce6d23 | 10/10 | APPROVE (security, round 2) | b26-t6b-3 |
| T6b-4 | #223 | feat/b26-t6b-4 | ee8ccd97 | 10/10 | APPROVE (a11y, round 2) | b26-t6b-4 |
| T6b-5 | #224 | feat/b26-t6b-5 | 727b85fa | 10/10 | APPROVE (round 2), with 2 rulings to apply | b26-t6b-5 |
| T8d | #225 | feat/b26-t8d | f2cfb8d5 | 10/10 | APPROVE (round 2) | b26-t8d |

**Migration chain:** `0038_speaker_availability` → `0039_speaker_portal` → `0040_booking_cancellation` → `0041_batch_speaker_request`.
- Alembic revision ids must be ≤ 32 characters (`varchar(32)`).
- `0039` also carries: the T6b-2 `speaker_portal` response channel, the T6b-3 lift-source CHECK and `contact_channel_speaker_choice`, and the T6b-5 unbind columns.

**Owner merge order:**
1. #210, #212, #215, #216
2. #217, #218
3. #220
4. #219
5. #222
6. #223
7. #224
8. #221
9. #225

#211, #213 and #214 are independent.

## 2. Owner rulings not yet applied (2026-09-24)

| # | Ruling | Applies to |
|---|---|---|
| R-A | **Load numbers do not go on the API wire.** Connector- and Speaker-facing JSON carries only band + reason (+ `used_in_matching`). `completed_hours`, `confirmed_hours`, capacity and utilization stay in the stored run payload only, for audit. The candidate block's `multiplier` / `composite_before_load` are scores, not load hours; keep them unless a reviewer argues otherwise. | #221 T8c (`LoadBlockView`, `ExcludedCandidateView.load`), #225 T8d (`CandidateLoadBlockView`, the availability `load` field, api.ts types) |
| R-B | **Seed merge is volunteer-only.** `tools/seed_pilot_logins.py:281-295` adds roles to a login it did not create only when the seed entry is `volunteer` **and** the holder's active roles are within {speaker, volunteer}. Anything else raises `SeedConflictError`. | #224 T6b-5 |
| R-C | **Existing-login binding uses an allow-list of {volunteer}.** It requires an active `volunteer` membership and no active admin/coordinator/student role. A login with no role is refused (generic 400 at activation, 409 at invite). Replace `test_invite_to_an_expired_staff_role_is_accepted` with a refusal test. | #224 T6b-5 |
| R-D | **CI timeout.** Open a separate one-line PR against main (`ci:`) raising the python job's `timeout-minutes` at `.github/workflows/verify.yml:49` from 15 to 25. The owner merges it first. #224's python job took 14m13s; one run already timed out with every test passing. | new PR |

Earlier rulings (all applied): Opus replaces Codex; T6b-1 R8; T4 C1/C12; T6b-3 OQ-1–4; T6b-5 Q1–Q5; T8b window; T8a C1/C3; the T6a proxy. They are all recorded in the ledger and in memory.

## 3. Stack sync needed

1. **T4 × T6b.** T4 requires a Speaker Request on every batch. After T4 merges, 17 tests fail in T6b-2's `tests/contract/test_speaker_self_api.py` and T6b-3's suppression send-path tests, because their helpers create batches with no request.
   - T8d fixed this on its own branch only, in commit `a006fe3a`.
   - **#219 and #222 must merge `origin/feat/b26-t4` and port that helper fix**, or they break `main` when merged after #220.
2. **The cascade, in order** (merges only; push fast-forward; CI to 10/10 after each):

   | Step | Branch | Merges in | Extra work |
   |---|---|---|---|
   | 1 | T8c | — | apply R-A |
   | 2 | T6b-2 | T4 | port `a006fe3a` helpers |
   | 3 | T6b-3 | T6b-2 | port helpers |
   | 4 | T6b-4 | T6b-3 (at 2fce6d23 or later) | — |
   | 5 | T6b-5 | T6b-4 | apply R-B, R-C |
   | 6 | T8d | T8c, T6b-4 | apply R-A to its own views |

   - Each PR's first body line "Stacked: merge #… first" must be updated to add the new parents (e.g. #219 now needs #220 first).

## 4. Do this now

Dispatch in one message, in parallel. Each agent is Opus with "Reasoning effort: HIGH" and gets the §6 brief.

1. **CI PR (R-D).** Small agent, or do it yourself:
   - `git worktree add .claude/worktrees/ci-timeout -b ci/python-job-timeout origin/main`
   - edit `verify.yml:49` from 15 to 25
   - open the PR `ci: raise python job timeout to 25 minutes`
   - Tell the owner to merge it first.
2. **Sync orchestrator.** Run §3 steps 1→4 and 6, in order, in their worktrees (T6b-5 is handled by item 3).
   - For R-A: write tests first asserting the numeric keys are absent from every API response. Keep them in the stored payload.
   - Re-run an Opus delta review on each changed PR, at most 2 rounds.
3. **T6b-5 fixer.** Worktree `b26-t6b-5`. Apply R-B and R-C test-first.
   - Then wait for the sync orchestrator's push of T6b-4, and merge `origin/feat/b26-t6b-4` again.
   - Run an Opus security delta review, then get CI 10/10.

When all are green: update the ledger, then write the **final report** (§5).

## 5. Final-report contents

- **Every PR:** track, PR number, CI state, review verdict. Take it from the table above plus the new ci: PR.
- **Guardrails verified:**
  - `SPEAKER_PORTAL` is off by default in every scope.
  - Registry 3.0.0 is `proposed`; `REGISTRY_VERSION` and `CURRENT_CBA_REGISTRY` stay 2.0.0. The flip not done is `CURRENT_CBA_REGISTRY: Final[FactorRegistry] = CBA_REGISTRY_3` in `factor_registry.py`.
  - The 2.0.0 virtual hash is pinned per Python interpreter: 3.11 = `sha256:62524878…792b74c` (prod), 3.12 = `sha256:0b27df1f…`.
- **Stakeholder gates (all open):**
  1. Ann/Pia/Lisa: `SPEAKER_PORTAL` stays off.
  2. A named privacy owner, which also covers the Connector self-invite risk.
  3. IA West review of D2: 3.0.0 stays `proposed`.
  4. The pilot hostname.
  5. Retention (D5).
- **Owner checks:**
  - T5 browser pass at 360/1440 px.
  - T8d browser pass with `SPEAKER_PORTAL` on.
  - The interpreter risk: moving prod to Python 3.12 changes new virtual-run hashes. Record it in ADR-0027 before the flip.
- **Follow-up cards:**
  - `/i/` token exposure in drafts
  - Cloudflare rate-limit rule on POST `/i/*` and `/v1/speaker-invitations/respond`
  - OQ-CBA-044 mail-scanner auto-submit
  - T8a undo cancellation
  - `frontend-broken-buttons.md` lines 111/112/157
  - delete branch `feat/b26-t2-plan`
  - `cba.speaker_invitation.v1` into SYSTEM_ONLY_TEMPLATES
  - extraction upsert rewrites a request's `origin`
  - `ExactTime` DST compare at `events.py:264`
  - `DELETE …/availability`
  - batched roster availability
  - Connector wording for the Speaker-wins 409s
  - Full re-check at compose
  - band "changed since run"
  - `factor_registry.py` split after the flip
  - provider exception text reaching `failure_reason` on portal sends
  - T4 origin-flip backfill gap
  - EAI (non-ASCII) login address can't lift own unsubscribe (T6b-3 LOW-5)
  - Volunteer drawer lacks `inert` (T6b-5 LOW)
  - `PagedList` double live-region (T6b-4 LOW)
- **Local hazards:**
  - `refs/backup/scaffold-jwks-core` holds a gitleaks finding; never push it.
  - Leftover private DB `smartmatch_b26_t6b5`; drop it when T6b-5 closes.
  - Local branch `feat/b26-t8d-web` is unpushed and can be deleted.

## 6. Shared brief for every track orchestrator or fixer (paste in full)

> You own ONE B26 branch, from its current state to green and reviewed. The owner merges; you never merge.
>
> **Environment**
> - Python: `VENV=<repo>/.venv`, with `PYTHONPATH=python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence:services/api:tools`.
> - Run one pytest file at a time; never a full suite on /mnt/c.
> - Database: a private Postgres DB `smartmatch_b26_<track>_x`, dropped at the end. If a scratch DB vanishes mid-test (concurrent agents), rerun once.
> - Vitest: rsync the frontend to /tmp (no node_modules), run `npm ci` in the background, then `npx vitest run --pool=threads <file>`. Files must match `src/**/*.test.tsx`, fireEvent only.
>
> **Git rules**
> - Merge, never rebase. Push fast-forward only; never force-push, never rewrite history.
> - Before every push: `gitleaks git --log-opts="origin/main..HEAD" -c .gitleaks.toml .` must report 0 leaks. Never name a variable or SQL bind `key`, `token`, `secret` or `password` next to a string literal.
> - Regenerate OpenAPI with `make openapi VENV=$VENV`; never edit it by hand.
> - Run `ruff format`, including on `.md` files.
> - Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
> - Edit PR bodies with `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/N -F body=@file`. Bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
>
> **TDD:** every change has a red commit (failure excerpt in the body), then a green one (pass counts in the body).
>
> **Review:** after changes, run an Opus delta review (`security-reviewer` for T6b-*, `code-reviewer` otherwise). Fix CRITICAL, HIGH and MEDIUM test-first, at most 2 rounds; record LOWs in the PR body.
>
> **Guardrails**
> - `SPEAKER_PORTAL` stays OFF by default.
> - Registry 3.0.0 stays proposed, not current.
> - `speaker` and `volunteer` never widen each other.
> - No new migration.
> - Don't touch another track's worktree.
> - `docs/plans/frontend-broken-buttons.md` is out of bounds.
>
> **Report:** PR, CI x/y, verdict, shas, full list of files changed, deviations, blockers.
