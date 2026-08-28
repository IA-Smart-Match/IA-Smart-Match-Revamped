# Implementation plan — A1b institutional sign-in

**Date:** 2026-08-28 · **Plan id:** P2 · **Worktree branch:** `plan/a1b-sign-in`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

## Standing constraints (restated; do not override)

- No push, no PR, no live providers, no production credentials, no
  production-readiness claims. Nothing is deployed.
- The browser must never assert tenant, user, or role as authentication input.
- No click may report successful sign-in without server agreement.
- Do not revive `mockLogin`, role-in-body POSTs, or browser-asserted roles.

## Stop-gate

A1b requires an identity-provider decision that is operational, not code:
which IdP (institutional OIDC/SSO), its issuer, audience, JWKS endpoint, and
key-rotation policy. Before any card beyond A0 runs, the executor MUST find a
committed decision artifact (expected under `docs/decisions/`) naming:

1. the IdP and environment (a development/test tenant is acceptable and
   expected — live production SSO is out of scope under standing constraints);
2. issuer URL, audience, and JWKS retrieval approach;
3. the owner who approved the configuration.

If absent: run card A0 only (preparation), then stop and report
"IdP decision artifact missing".

## Current state (facts an executor can verify)

- Fix #7A landed (`169b95d`): `LoginPage.tsx` has no role cards; sign-in is a
  truthful unavailable state. `tests/unit/test_frontend_auth_contract.py`
  guards against regression.
- The backend verification seam exists (A1a): bearer verification with a test
  fixture; `GET /v1/me` returns server-assigned identity and memberships
  (`tests/contract/test_me.py` proves the caller cannot pick tenant/user/role).
- `apps/web/legacy-frontend/src/lib/api.ts` already attaches a bearer from
  `VITE_SMARTMATCH_BEARER_TOKEN` or `sessionStorage["smartmatch_bearer_token"]`
  (`smartmatchAuthHeaders`, ~line 324) and exposes `fetchMe()` (~line 1652).
- Residual defect this plan closes: portal layouts/pages still read
  `sessionStorage["iaw_session"]` with fallback identities (`stu-001`,
  `coord-001`, `shana-demarinis`). These are development-only leftovers.

## Task cards

### Card A0 — preparation (runs regardless of stop-gate)

- **Fence:** new file `docs/decisions/a1b-idp-configuration-worksheet.md`; audit
  output committed as part of this card.
- **Work:** (1) write the IdP worksheet listing the fields the decision must
  supply (issuer, audience, JWKS, rotation, session lifetime, logout); leave
  values blank for the human. (2) Inventory every read of
  `sessionStorage["iaw_session"]` and every fallback identity literal across
  `apps/web/legacy-frontend/src/` (ripgrep for `iaw_session`, `stu-001`,
  `coord-001`, `shana-demarinis`) and record the file list in the worksheet so
  card A3's fence is exact.
- **Tests:** none (documentation card).

### Card A1 — backend verifier configuration (after stop-gate)

- **Fence:** the A1a verification seam module in `services/api/` (locate via
  the existing bearer-verification fixture used by `tests/contract/test_me.py`)
  plus its settings/env wiring; **do not** touch routers.
- **Work:** wire issuer/audience/JWKS from configuration (environment
  variables documented in the repo's settings pattern), keeping the existing
  test fixture path working for CI. Verification failures must map to the
  standard error envelope; no fallback identity on failure.
- **Tests:** unit tests for issuer/audience/expiry/rotation rejection paths;
  `tests/contract/test_me.py` stays green.

### Card A2 — frontend sign-in flow (parallel with A1 after contract agreed)

- **Fence:** `apps/web/legacy-frontend/src/app/pages/LoginPage.tsx`, new
  `src/app/hooks/useSession.ts` (or equivalent), `src/lib/api.ts` (auth header
  section only).
- **Work:** replace the unavailable state with the real IdP redirect/PKCE flow
  per the decision artifact. On return, store the bearer in
  `sessionStorage["smartmatch_bearer_token"]` (the key `api.ts` already reads),
  call `fetchMe()`, and derive the UI's identity/memberships exclusively from
  the response. Sign-out clears the token and any cached data.
- **Hard rules:** no role/tenant/user in any request body or query; UI shows
  signed-in state only after `fetchMe()` succeeds.
- **Tests:** update `tests/unit/test_frontend_auth_contract.py` deliberately —
  it currently asserts the unavailable state; invert that assertion in the same
  commit that lands the real flow. Keep the no-role-selector assertions.

### Card A3 — remove fallback identities (after A2)

- **Fence:** exactly the file list produced by card A0's audit (portal
  layouts/pages reading `iaw_session`).
- **Work:** remove `sessionStorage["iaw_session"]` reads and all fallback
  identities. Route guards become UX only — an unauthenticated visitor is sent
  to `/login`; API authorization remains authoritative. Portal pages that
  cannot render without identity show a truthful signed-out state, never a
  canned identity.
- **Tests:** extend the frontend auth contract test to assert `iaw_session`
  and the three fallback literals appear nowhere in `src/`.

### Card A4 — verification join

- Run the evidence ladder below; record results in the worksheet.

## Evidence ladder

1. `python -m pytest tests/unit/test_frontend_auth_contract.py tests/contract/test_me.py -q`
2. `make check` if available (no-database)
3. In `apps/web/legacy-frontend`: `npm run typecheck`; `npm run build` where
   the filesystem permits (DrvFs may block `npm ci` — CI is the authoritative
   clean-install proof, per `docs/plans/orchestrator-handoff.md`)
4. Manual acceptance: `/login` performs the real flow against the development
   IdP; direct portal URLs without a session redirect to `/login`; no request
   carries a browser-chosen role.

## Done means

- Sign-in succeeds only through the IdP; identity and memberships come from
  `GET /v1/me`.
- No fallback identity, `iaw_session` read, or role assertion remains in the
  frontend source.
- The auth contract test guards the new invariants.
- CI web job (install, typecheck, build, audit) is green — CI-only proof.
