# T6a — `/i/{token}` accept / decline controls (B26)

**Next action:** dispatch the T6a builder: write the failing tests in §3, commit, then build §2.
**Parent:** `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1, §6 row `/i/{token}`, §7 row 5, §8 row T6a.
**Scope:** the page fix only. The token-link availability route is dropped (§8).
**Revision 2, 2026-09-22:** coordinator rulings applied — C1 proxy `^/i/` in T6a; C2 hand-parse with a body cap; C3 new `POST /i/{token}`; C4 as proposed. **Revision 3:** Opus review CHANGES applied (row 14 moved to Vitest on the real config; async-dependency / sync-route split; quota and ledger note; 5 nits). Implementation not started.

## 1. Files to touch

| File | Today | Change |
|---|---|---|
| `services/api/smartmatch_api/main.py:799-834` | `GET /i/{token}` (`invitation_response_page`, :814) returns `<h1>` + "Choose below…" and no form | Render the form (§2.1); add `POST /i/{token}` on `token_pages_router` (:753); fix the docstring (:821 says the page submits to `/v1/speaker-invitations/respond` — it cannot) |
| `services/api/smartmatch_api/routers/cba_invitations.py:1245-1313` | `speaker_respond`: JSON `SpeakerRespondRequest` (:440, `token` 16–256 chars, `response` accept/decline) → `resolve_response_token` → `record_response` → `{"recorded": true}` | Extract the body into `answer_by_token(session, token, verb) -> None`; `speaker_respond` and the new form route both call it. JSON contract unchanged |
| `python/smartmatch_domain/smartmatch_domain/cba_invitations.py:357` | `record_response` (first answer stands; different answer raises `InvitationResponseConflict`) | none — reused |
| `python/smartmatch_persistence/smartmatch_persistence/cba_invitations.py:492, :518` | `resolve_response_token` (cross-tenant); `record_response` (WHERE `status='dispatched'` AND `awaiting_response`) | none — reused |
| `tests/contract/test_api_health.py:73-100` | `/u/{token}` renders, no echo, GET-only. **No `/i/{token}` test exists** | Add the DB-free GET tests (§3 rows 1-5) |
| `tests/contract/test_cba_invitations_api.py:742` | `TestSpeakerRespondsThemselves` (JSON route, live Postgres, skips without it) | Add `TestSpeakerRespondsByForm` (§3 rows 6-12) |
| `tests/authz/test_policy_matrix.py:421, :431` | `UNAUTHENTICATED_ROUTES` has `GET /i/{token}` and the JSON POST | Add `("POST", "/i/{token}")` with its reason; reword the GET entry ("the answer is the POST below") |
| `contracts/openapi/smartmatch.json:7619` | documents GET only | `make openapi`; CI runs `openapi-check` |
| `apps/web/legacy-frontend/vite.config.ts:54-85` | `server.proxy` and `preview.proxy` forward `/api`, `/v1` only | Add `"^/i/": { target: apiProxyTarget, changeOrigin: true, agent: proxyAgent }` to **both** blocks. Touch only the two proxy blocks: the owner has uncommitted `allowedHosts` edits in the parent checkout |
| `apps/web/legacy-frontend/src/viteProxy.test.tsx` (new) | — | Vitest, `// @vitest-environment node`, imports the real config (§3 row 14). CI runs Vitest on `src/**/*.test.tsx` only (`vitest.config.ts:36`); Node 20 cannot run `.ts` under `node --test` |

`tests/unit/test_class_exercise_scope.py:400, :424-430` compares **paths**, so a POST on the same path keeps it green. Run it anyway.

## 2. Contract

### 2.1 `GET /i/{token}` — unchanged semantics, now with controls

- 200 `text/html; charset=utf-8`, same bytes for every token (real, invented, 3 chars, 300 chars). No state change, no DB read.
- One `<form method="post">` with **no `action` attribute**. The browser posts to the document's own URL, so the token travels in the path the Speaker already holds and is never written into the HTML. (An empty `action=""` is invalid HTML; omit it.)
- Two real buttons in that form: `<button type="submit" name="response" value="accept">Accept invitation</button>` and `…value="decline">Decline invitation</button>`. No JS, no hidden fields.
- Copy: keep "Neither choice changes whether you receive other messages." Add "Your first answer is final. To change it, contact the person who invited you." (OQ-CBA-044 is unanswered; a different second answer is refused.) No event, Speaker or unit detail — that would be an oracle.
- Markup: `<html lang="en">`, `<meta charset="utf-8">`, `<meta name="viewport" …>`, one `<h1>`, the instructions in `<p id="i-help">`, form `aria-describedby="i-help"`.

### 2.2 `POST /i/{token}` — new, form-urlencoded

- Body `application/x-www-form-urlencoded`, one field `response` = `accept` | `decline`.
- **Parse by hand** with `urllib.parse.parse_qs(body, keep_blank_values=True, max_num_fields=4)`. No new dependency: `python-multipart` is not in `requirements/runtime.txt`, and FastAPI `Form()` would fail at startup (§6 C2).
- **Async/sync split.** An `async def _read_answer_form(request: Request) -> FormOutcome` dependency does all body work and **never raises**; it returns `TOO_LARGE`, `INVALID`, `ACCEPT` or `DECLINE`. The route stays a plain `def` taking `DbSession` and the outcome, so the DB work runs in the threadpool.
- **Body cap:** `_TOKEN_FORM_MAX_BYTES = 1024`. The dependency first rejects a `Content-Length` above the cap, then reads `await request.body()` — `MaxBodySizeMiddleware` (`main.py:119`, `:280`) has already buffered it, so a chunked body is bounded by the global cap — and returns `TOO_LARGE` when `len(body) > 1024`. `TOO_LARGE` → 413 HTML, same bytes for every token.
- **Validation → `INVALID` → 400 HTML** "Choose Accept or Decline.": content type whose parsed media type (parameters such as `charset` ignored, case-insensitive) is not `application/x-www-form-urlencoded`; bytes that are not UTF-8; the `ValueError` `parse_qs` raises past `max_num_fields`; `response` missing, repeated or not `accept`/`decline`. All of it depends on the request body only, never the token, so it is not an oracle.
- Then: token length outside 16–256 → skip lookup; else `answer_by_token(...)` (same rules as the JSON route, `response_channel="speaker_link"`).
- Response: 200, **identical bytes for every token and outcome** — recorded, same answer again, different answer refused, invented, not dispatched, short/long. Copy: "Thank you. We have your answer." No redirect (a redirect target would need the token or a second page); a refresh re-POST is a no-op.
- **Errors are not swallowed.** A DB failure in `answer_by_token` propagates to the app's exception handler as a 500 JSON envelope. This is token-dependent (only a real token reaches the write); it is documented in the route docstring and §5, not hidden.
- **OpenAPI:** `openapi_extra` declares the `application/x-www-form-urlencoded` request body (`response`: enum accept/decline); `responses` declares `text/html` for 200, 400 and 413, and the `ErrorEnvelope` JSON for the inherited codes, in `unsubscribe_page`'s per-response style.

### 2.3 Headers on both methods (none are applied today)

The API sets no CSP or referrer header globally; only `/q/{public_token}` sets `Cache-Control: no-store` + `Referrer-Policy: no-referrer` (`routers/manual_events.py:602`). Add a shared `_TOKEN_PAGE_HEADERS` constant:
`Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`.

### 2.4 CSRF and no-JS

- No cookie, no session: the path token is the whole authorization, exactly as for the JSON route. A cross-site form can only forge an answer it already holds the token for — no new surface.
- GET stays safe for prefetchers and link scanners; they do not POST.
- No rate limit, for the reason documented at `cba_invitations.py:182-190`. **ADR-0015 quota-first does not apply: `charge_quota` keys by tenant+user and this route has no principal (`cba_invitations.py:182-190`). Unauthenticated routes are declared in `UNAUTHENTICATED_ROUTES`, not `test_route_roles.py`.** The same text goes into the `("POST", "/i/{token}")` reason in `tests/authz/test_policy_matrix.py`.
- **Ops follow-up (not T6a):** add a Cloudflare rate-limiting rule on `POST /i/*` (and `POST /v1/speaker-invitations/respond`) at the tunnel edge — the "edge rate limit" `cba_invitations.py:190` assumes.

## 3. TDD test list (contract)

| # | File | Test |
|---|---|---|
| 1 | `test_api_health.py` | `test_invitation_page_renders_accept_and_decline_controls` — one `form[method=post]`, no `action`, two `button[type=submit][name=response]` with values accept/decline |
| 2 | ″ | `test_invitation_page_does_not_echo_the_token` — `secret-token-value-0123456789` absent from body and headers |
| 3 | ″ | `test_invitation_page_is_identical_for_every_token` — parametrize real-shaped, 3-char, 300-char, `<script>` |
| 4 | ″ | `test_invitation_page_has_labelled_real_buttons` — visible text on both, `lang`, one `h1`, `aria-describedby` resolves |
| 5 | ″ | `test_token_pages_send_no_store_no_referrer_and_csp` (GET) and `test_invitation_path_serves_get_and_post_only` (`{"get","post"}`) |
| 6 | `test_cba_invitations_api.py` | `test_form_accept_records_the_answer_by_speaker_link` |
| 7 | ″ | `test_form_decline_records_the_answer` |
| 8 | ″ | `test_form_post_is_identical_for_every_token` — parametrize invented, short, long, already-answered same, already-answered different, undispatched; assert same status + bytes, stored row unchanged where expected |
| 9 | ″ | `test_form_post_does_not_echo_the_token` |
| 10 | ″ | `test_form_post_without_a_valid_response_is_400_for_any_token` — parametrize missing, `maybe`, repeated `response`, non-UTF-8, `text/plain`, a **5-field body** (`max_num_fields` `ValueError`); `application/x-www-form-urlencoded; charset=UTF-8` is accepted; same bytes for real vs invented token |
| 11 | ″ | `test_form_post_sends_the_token_page_headers` |
| 12 | ″ | `test_json_respond_route_is_unchanged` — existing `TestSpeakerRespondsThemselves` stays green (regression) |
| 12b | ″ | `test_form_post_over_the_body_cap_is_413_for_any_token` — 1025-byte body, with and without `Content-Length`; real vs invented token same bytes, nothing written |
| 13 | `test_policy_matrix.py` | ledger passes with the new `UNAUTHENTICATED_ROUTES` entry |
| 14 | `apps/web/legacy-frontend/src/viteProxy.test.tsx` | `// @vitest-environment node`; `import config from "../vite.config"`. Local matcher copying Vite 6.4.3's proxy rule, with a comment citing it: `(context[0] === "^" && new RegExp(context).test(url)) \|\| url.startsWith(context)`. For **both** `config.server.proxy` and `config.preview.proxy`: `/i/abc…` and `/i/abc?x=1` match; `/index.html`, `/images/x.png`, `/i`, `/inbox` do not; `/api/health`, `/v1/x` still match |

Run 14 with `npx vitest run --pool=threads src/viteProxy.test.tsx` from a Linux-filesystem copy of `apps/web/legacy-frontend` (no `node_modules` on `/mnt/c`).

Rows 6-12 need live Postgres (fixture skips otherwise); CI proves them. Run one file at a time.

## 4. Commit milestones

1. `test: T6a failing contract tests for /i/{token} controls` — rows 1, 4-11, 12b and 14 red; policy-matrix entry added (red until the route exists). Rows 2, 3 and 12 are regression guards that are **green before the change**.
2. `feat: /i/{token} accept/decline form and POST handler` — extract `answer_by_token`, add form, POST, body cap, headers; rows 1-13 green.
3. `feat: proxy /i/ token pages to the API in dev and preview` — `vite.config.ts` proxy blocks only; row 14 green.
4. `docs: T6a OpenAPI and docstrings` — `make openapi`; fix the stale GET docstring (`main.py:821`) and the `GET /i/{token}` policy-matrix reason (`test_policy_matrix.py:421-430`) to name `POST /i/{token}`.

## 5. Out of scope

- Token-link availability route (dropped; `/v1/me/availability` in T6b-2).
- `/s/{token}` activation page (T6b-1), `/u/{token}` form and the unsubscribe POST.
- Changing one's answer (OQ-CBA-044), invitation expiry, in-app rate limiting (edge limit is the ops follow-up in §2.4).
- **Timing differences (documented, not fixed):** a well-formed token costs a DB lookup and, for a real one, a write; a short/long token skips both. Response bytes are identical; latency is not. Same exposure as the JSON route today. Stated in the route docstring.
- **Write-failure 500 (documented, not fixed):** a DB error on a real token surfaces as a 500 envelope while an invented token cannot fail that way. Errors are not swallowed; stated in the route docstring.
- **Owner note — mail-scanner auto-submit (linked to OQ-CBA-044):** a security scanner that renders the page and submits forms would record an answer, and because the first answer is final it cannot be undone by the Speaker. T6a keeps GET safe; POST-submitting scanners are the residual risk. If the owner wants a mitigation (e.g. a confirm step, or allowing a change of answer via OQ-CBA-044), it is a follow-up.
- Showing invitation details on the page; e2e step 23 keeps using the JSON route.
- Setting `SMARTMATCH_OUTREACH_PUBLIC_BASE_URL`: ops sets it on the VM once the pilot hostname is final (parent plan §10 gate 4). T6a does not set it.
- Proxying `/u/{token}` (same gap, not this track).

## 6. Contradictions between plan and code — all ruled 2026-09-22

| # | Plan / prompt says | Code says | Ruling |
|---|---|---|---|
| C1 | `/i/{token}` is the Speaker's working link | Pilot tunnel → Vite 5173 (`docs/operations/classroom-vm-cloudflare-tunnel.md:52`), which proxies only `/api` and `/v1` (`vite.config.ts:54-85`); `SMARTMATCH_OUTREACH_PUBLIC_BASE_URL` is set nowhere, so links default to `http://localhost:8080/i/…` (`config.py:112`) | **Ruled (owner): (a).** T6a adds `"^/i/"` to `server.proxy` and `preview.proxy` (a plain `"/i"` key would catch `/index.html`); row 14 (Vitest, real config) guards it. Base URL: ops, §10 gate 4 |
| C2 | "server-rendered HTML form" | `python-multipart` absent from `requirements/runtime.txt` and the venv | **Ruled: (a).** Hand-parse with `parse_qs`, 1 KiB cap (§2.2). No new dependency |
| C3 | GET docstring (`main.py:821`) and policy-matrix reason (`:421-430`): the page submits to `POST /v1/speaker-invitations/respond` | That route takes JSON only; a no-JS form cannot send JSON, and a hidden token field would echo it | **Ruled: (a).** New `POST /i/{token}`; stale docstring and policy-matrix reason fixed in milestone 4 |
| C4 | Task asks "identical for unknown / expired / used" | `cba_invitation` response tokens have **no expiry**; states are unknown, answered-same, answered-different, not dispatched | **Ruled: accepted.** Test those four plus bad length |
| C5 | Parent plan §1 cites `main.py:799-836` | Route is `:799-834`; `:837+` is `APP_LEVEL_ROUTERS` commentary | Cosmetic; this plan cites `:799-834` |
