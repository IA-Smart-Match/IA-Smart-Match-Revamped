# B26 build orchestrator — handoff (2026-09-23)

Paste the `/goal` line first, then everything under "Prompt" as the first message.

## /goal line

```
/goal Build every track of the B26 plan (docs/plans/2026-09-22-b26-self-service-availability-plan.md §8: T1–T5, T6a, T6b-1…T6b-5, T7, T8a–T8d). Each track ships as its own PR against main, with green CI, a /codex-reviewed track plan, targeted tests passing and TDD evidence (red then green). Migrations 0038→0039→0040 land in order with no numbering collision. SPEAKER_PORTAL stays off for real Speakers, and registry 3.0.0 is shipped but not made current. The final report lists every PR, its CI state and anything still gated on stakeholders.
```

## Prompt

Output style: follow ~/.claude/rules/common/subagent-output.md (i-have-adhd)

You are the **B26 build orchestrator** (Opus 5.5), resuming mid-build. Read the original handoff first — it holds the role, model routing, per-track pipeline, wave plan, environment rules and guardrails, and all of it still applies:
`docs/archive/plans/prompts/opus-5-5-b26-build-orchestrator-handoff-2026-09-22.md` (untracked, parent checkout).

This file only adds **what changed and where each track stands**.

### 1. Changes to the process (owner-approved 2026-09-22 23:50 PDT)

1. **Codex hit its usage limit** (reset 2026-09-23 04:40 PDT). Owner ruling: an **Opus `code-reviewer` stands in for Codex** as the plan gate, implementers proceed, and **Codex re-reviews every track plan AND every PR diff after the reset, before a PR is called ready**. Nothing has had its Codex pass yet.
2. The Codex companion runs **one shared session**: queue Codex jobs one at a time. The `codex:codex-rescue` forwarder often returns only a job id; read the verdict with `node ~/.claude/plugins/cache/openai-codex/codex/1.0.4/scripts/codex-companion.mjs status <job>` and the job log, or `result <job>`.
3. Plan rounds: after 2 review rounds, the orchestrator applies the final fixes via the planner and verifies the diff itself instead of a third review.
4. **`ruff format --check` formats Python code blocks inside `.md` files.** Plan markdown has failed CI once. Every planner and implementer runs `ruff format` on its plan file.
5. CI runs only: python `pytest tests/ -m "not e2e"` (with Postgres), and web vitest on `src/**/*.test.tsx`. `node --test tests/*.test.ts` does **not** run in CI. The forbidden-behaviour scanner flags credential-shaped string literals in tests.
6. A local Postgres 16 is reachable. The T2 agent used a private DB (`smartmatch_b26t2`, dropped afterwards). Never touch the shared `smartmatch` DB.

### 2. Owner rulings made during the build (final)

| Track | Ruling |
|---|---|
| T6a | Add a `^/i/` Vite proxy to both `server.proxy` and `preview.proxy`. Ops sets `SMARTMATCH_OUTREACH_PUBLIC_BASE_URL` once the hostname is final. |
| T8a C1 | **C:** cancelled bookings drop out of `list_confirmed_speakers` **and** the `pipeline_confirmed` metric, recorded as an ADR-0011 register change. Hand-off replay on a cancelled booking → 409 `pipeline_record_cancelled`. |
| T8a C3 | New page `/coordinator-portal/bookings` (nav in the Coordinate group, `CalendarCheck` icon). |
| T6b-1 token | HMAC of the invitation id under the new secret `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET`. The draft body holds a placeholder, and the worker fills the link at send time. The DB stores SHA-256. |
| `/i/` exposure | The `/i/` response tokens sit in Connector-readable draft bodies. **Log a separate backlog card; not fixed in B26.** Not yet logged: add it to the ledger and the final report. |
| T8b C1 | A booking on the run day that is already attended **counts as upcoming**: any confirmed, not-cancelled booking in the forward window counts, attended or not. |
| T8b window | **Trim to exactly 90 days**: completed = [as_of−45, as_of), confirmed = [as_of, as_of+44]. |

Orchestrator rulings already sent: T1 verdict order follows parent §5.1; capacity is Decimal-only, finite, 0<v≤720, at most 1 decimal place; T2 `expected_version` None = expect no row; T7 guard is a fail-closed string guard; `frontend-broken-buttons.md` is out of bounds (PR #208 owns it; its stale lines 111, 112 and 157 are an owner follow-up).

### 3. Track state at handoff

| Track | State | Branch / PR | Next step |
|---|---|---|---|
| T1 | **PR #210**, CI 10/10 green @ `a4e2bbce`; Opus review APPROVE; all 5 findings fixed | `feat/b26-t1` | Codex plan + diff review, then tell the owner it's ready |
| T7 | **PR #211**, CI 10/10 green @ `4225d64d`; Opus review APPROVE; 4 LOW fixed | `feat/b26-t7` | Codex plan + diff review, then ready |
| T2 (`0038`) | **PR #212**, CI 10/10 green @ `358da818`. Stacked on T1 (T1 merged in); body says "merge #210 first" | `feat/b26-t2`; plan-only backup branch `feat/b26-t2-plan` (delete later) | Opus `python-reviewer` + `database-reviewer` on the diff, then Codex |
| T6a | **PR #213**, CI 10/10 green @ `6e1857fb` | `feat/b26-t6a` | Opus security-focused review, then Codex |
| T8a (`0040`) | Plan final @ `09ca1455` (Opus review changes applied; orchestrator did not diff-verify yet) | `feat/b26-t8a` | Waits on the `0039` merge (T6b-1). Verify the plan diff `aed86f33..09ca1455` |
| T6b-1 (`0039`) | Plan @ `3db1c42d`. **Opus review = CHANGES, 11 required** (below), not yet sent to the planner | `feat/b26-t6b-1` | 1) Ask the owner R8. 2) Send R1–R11 + nits to a planner. 3) Verify. 4) Implement after #212 merges |
| T3 | Plan @ `e1def09a`; C1 open | `feat/b26-t3` | Rule C1 = **UTC** (recommended, consistent with T8's UTC run date), then Opus review. Implement stacked on `feat/b26-t2` |
| T4 | Plan @ `a67d1c5c`; C1–C3 open | `feat/b26-t4` | Proposed: C1 (a) re-check only when the batch has a match run in the unit, (b) as a later card; C2 (b) availability now, Q8 as milestone 5 once `0039` is on main, else T4b; C3 (b) store `excluded` in the payload and return it on read; C7 → **UTC** (override the planner's event-zone proposal to match T3). Ask the owner about C1 if unsure; then Opus review |
| T8b | Plan @ `37b4b225`; owner rulings above **not yet sent to the planner** | `feat/b26-t8b` | Send: C1 = count as upcoming, window = 90 days, C2 (A) delete LoadModifier, C3 (A) unresolved date → unknown hours. Then Opus review. T8b doesn't depend on T2 (the planner verified it) |
| T5, T6b-2, T6b-3, T6b-4, T6b-5, T8c, T8d | Not started | — | Plan per the wave table. **T6b-2 must follow T8a** (it needs `cancelled_at`) |

**T6b-1 Opus review, required changes** (full text is in the review agent's report; re-derive by re-running the review if lost):
1. Activation must verify `compare_digest(token, derive_token(secret, id))`, so secret rotation actually kills links. The worker checks `sha256(derived) == token_hash` before sending.
2. The worker validates the invitation: tenant, live, unexpired, matching channel, template/id pairing, sentinel appears exactly once. Every refusal is a terminal PolicyFailure.
3. `SYSTEM_ONLY_TEMPLATES`: the generic compose route → 400 `template_not_composable`; the send route → 409 for that template (phishing vector).
4. Redact `/s|i|u/<token>` in the uvicorn access log, or disable the access log.
5. Lock order: profile `FOR UPDATE` first in invite and activation. Map `uq_…_live` → 409 `speaker_portal_invitation_conflict`. Use `lower(btrim(address))` everywhere.
6. Pass every timestamp explicitly from one injected `now`.
7. Downgrade raises if any accepted invitation exists.
8. **The `speaker` role is admitted by membership-only ops (`metrics.read`, `metrics.speaker_pipeline`) → owner ruling needed: deny `speaker` in `_authorize_aggregate_read` (recommended), or record the admission.** Add a `speaker_at_owning_unit` shape with a full MATRIX column.
9. Move the token-page helpers into `smartmatch_api/token_pages.py` with a generic `read_urlencoded_form`. Password max 256; form cap 2048.
10. Add testable `check_speaker_portal_startup(settings)` and a worker equivalent. The worker imports `ProductScope`/`DEFAULT_PRODUCT_SCOPE` from `smartmatch_domain`.
11. Activation also requires the channel state `consented|active_candidate`. Extend the identical-400 test parameters.
Nits: shared rate-limit bucket behind the proxy (document it); Connector self-invite risk row in §11; an Idempotency-Key or drop `replayed`; one versioned derivation `speaker-portal:v1:{id}` imported by the worker; the fixture provider sends nothing, so document that and gate the `/speaker-portal` SPA route on the capability.

### 4. Open items for the final report

- Owner follow-ups: the `frontend-broken-buttons.md` stale lines (111, 112, 157); the `/i/` token exposure card; a Cloudflare rate-limit rule on `POST /i/*` and `POST /v1/speaker-invitations/respond`; **mail-scanner auto-submit risk on `/i/` (OQ-CBA-044)**; T8a FU-1 (undo a cancellation); T4 C1(b) batch→request link card; delete `feat/b26-t2-plan`.
- Stakeholder gates (plan §10), all still open: Ann/Pia/Lisa (SPEAKER_PORTAL stays off); privacy owner; IA West D2 review (registry 3.0.0 stays proposed); pilot hostname; retention (D5).

### 5. Ledger and memory

- The ledger at `docs/plans/b26-tracks/LEDGER.md` on branch `docs/b26-ledger` (worktree `.claude/worktrees/b26-ledger`) is **stale** (it still says "planning"). Update it first from §3 above, then commit and push.
- Memory: `b26-build-wave-state-2026-09-22.md` in the project memory dir. Append a line at each wave boundary.

### 6. Start here

1. Check whether Codex has reset (`codex-companion.mjs status`). If it has, queue the Codex reviews one at a time: T1 → T7 → T2 → T6a (plan + diff each).
2. Ask the owner, by pop-up, T6b-1 R8 (speaker metrics access) and, if you want confirmation, T4 C1.
3. Send the pending rulings: T8b (to a planner), T3 C1 = UTC, T4 C1–C3/C7, T6b-1 R1–R11. Then run the Opus plan reviews.
4. Start Opus code reviews on PR #212 and PR #213.
5. Update the ledger.
