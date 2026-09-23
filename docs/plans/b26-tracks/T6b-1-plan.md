# B26 T6b-1 — Speaker accounts (`0039_speaker_portal`, invite / revoke / activate, `/s/{token}`)

**Next action:** branch `feat/b26-t6b-1-impl` from `origin/feat/b26-t2` and run milestone 1 (§9): migration tests red, then `0039`.

**Revision 3, 2026-09-23.** Applies the Opus plan review R1–R11 and its nits, and the owner ruling R8 (2026-09-23). Map: R1 §4.1, §5, §6.2 · R2 §6.2 · R3 §3.3 · R4 §4.5 · R5 §3.2, §5 · R6 §4.6 · R7 §2 · R8 §3.4 · R9 §3.5 · R10 §4.2 · R11 §5. Revision 2 settled C1–C5 (§9).

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1, §2, §3 intro, §3.2, §4.2, §4.5 (boundary), §6 invite row, §7 row 6, §8, §10, §11.

**Base and merge order.** The implementation branch stacks on `feat/b26-t2` (PR #212, which already merges `feat/b26-t1`, PR #210). The PR body says **"merge #210 and #212 first"**. T6a (PR #213, `feat/b26-t6a`) is **not** a prerequisite; §3.5 says how the two compose whichever merges first.

**Line numbers** are `main` @ `1909278f` unless marked "T2". On the T2 base, `schema.py` shifts +2 lines: `speaker_profile` is at T2 `:2126`, `speaker_availability_window` at T2 `:2392`, and `suppression_record` at T2 `:2078-2106`.

## 0. Boundaries (stated, not implied)

1. **New-login mode only.** Activation sets a password on the contact's own `user_account` (`account_user_id = professional_id`). Existing-login mode, `find_or_add_role`, credential `FOR UPDATE` locking, the other-tenant invite pre-check (`409 speaker_portal_address_in_other_tenant`) and unbind are **T6b-5**.
2. **No second credentialed account, ever.** Activation refuses with the generic `400 speaker_portal_invitation_invalid` and writes nothing when any credentialed account other than the contact account holds the channel address. This applies in any tenant, because `load_by_email` is global (`pilot_auth.py:103-159`). Addresses are compared as `lower(btrim(…))` on both sides (R5). T6b-5 turns the one-account-in-this-tenant case into existing-login mode.
3. **`lifted_at` is schema only.** `0039` adds `suppression_record.lifted_at/lifted_by_user_id`. No T6b-1 code sets them, so every send-eligibility read is unchanged. Appendix A lists the readers T6b-3 must change.
4. **`SPEAKER_PORTAL` is off** in all three scopes (C2). No seed, env var or compose file turns it on; turning it on is a reviewed edit to the policy rows. **Turn-on rule (C5, owner-confirmed):** T6b-5 merged **and** parent §10 rows 1 (Ann/Pia/Lisa), 2 (named privacy owner) and 4 (pilot hostname) cleared. The same sentence goes in the `Capability.SPEAKER_PORTAL` docstring.
5. **No email reaches a Speaker in this track.** The worker's fixture provider records a send in process memory and delivers nothing (`smartmatch_providers/fixtures.py:26-45`). The template is `ContentStatus.SYNTHETIC`, the default in `outreach.py:296`, so `assert_send_allowed` refuses it in live mode. A real Speaker gets a working link only after both of these land: reviewed copy, and the live provider (OQ-002). That work is out of scope (§12).
6. No `/v1/me/*` Speaker routes (T6b-2), no consent routes (T6b-3), no portal shell (T6b-4).

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0039_speaker_portal.py` | **New.** `revision = "0039_speaker_portal"`, `down_revision = "0038_speaker_availability"` (T2's file, `:43`). Hand-written (ADR-0004), no transaction code (ADR-0009). §2. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | Mirror. New table after `speaker_availability_window` (T2 `:2392`). On `speaker_profile` (T2 `:2126`): two columns, an FK and a CHECK. On `suppression_record` (T2 `:2078-2106`): two columns, an FK and CHECKs, and the source CHECK widened. Add to `__all__` (`:41`). Partial unique indexes as `sa.Index(..., unique=True, postgresql_where=...)`. |
| `python/smartmatch_domain/smartmatch_domain/product_scope.py` | `Capability.SPEAKER_PORTAL = "speaker_portal"` after `CLASS_EXERCISE` (`:230`), with a docstring that states the C5 turn-on rule. `False` in CBA (`:247`), IA_WEST_LEGACY (`:270`) and CLASS_EXERCISE (`:315`). An import-time assert: if it is on, then `AUTHENTICATED_LOGIN` (`:126`), `CONSENTED_OUTREACH` (`:185`) and `SPEAKER_CONTACT_MANAGEMENT` (`:171`) are on. |
| `apps/web/legacy-frontend/src/lib/productScope.ts` | `speaker_portal: false,` after `class_exercise: false,` (`:96`). Parity test: `test_cba_scope_policy.py:259`. |
| `python/smartmatch_domain/smartmatch_domain/speaker_portal.py` | **New.** `INVITATION_TTL = timedelta(days=7)`; `TOKEN_DERIVATION_LABEL = "speaker-portal:v1:"`; `derive_token(secret, invitation_id)`; `token_hash(token)`; `is_well_formed_token(token)`; `MAXIMUM_PASSWORD_LENGTH = 256`; `check_new_password`; `PortalAccessStatus` (`none/invited/expired/active`) and `derive_status(...)`; `ACTIVATION_URL_SENTINEL`; `ACTIVATABLE_CHANNEL_STATES = frozenset({CONSENTED, ACTIVE_CANDIDATE})`. The API and the worker both import it: there is one derivation label (§4.1). |
| `python/smartmatch_domain/smartmatch_domain/outreach.py` | Template `cba.speaker_portal_invite.v1` in `TEMPLATES` (`:341-417`). Placeholders `$professional_name`, `$unit_name`, `$expires_on`, `$activation_url` (`string.Template` syntax). The invite route always passes `activation_url = ACTIVATION_URL_SENTINEL`. `SYSTEM_ONLY_TEMPLATES: Final[frozenset[str]] = frozenset({"cba.speaker_portal_invite.v1"})` (§3.3). |
| `python/smartmatch_domain/smartmatch_domain/role_presentation.py` | `"speaker"` row in `_PRESENTATION` (`:145`): persona `SPEAKER`, label "Speaker", portal "Speaker Portal". Fix the `Persona.SPEAKER` doc (`:119-122`). |
| `apps/web/legacy-frontend/src/lib/roleLabels.ts` | Mirror row (checked by `test_role_presentation.py:158`). |
| `python/smartmatch_authz/smartmatch_authz/policy.py` | **Rule 8, `excluded_roles`** (R8, §3.4). New keyword on `evaluate` (`:264`) and `assert_allowed` (`:405`). Adds reason code `membership_role_excluded` and a module-docstring paragraph. |
| `services/api/smartmatch_api/routers/metrics.py` | `_AGGREGATE_EXCLUDED_ROLES: Final = frozenset({"speaker"})`, passed as `excluded_roles=` by `_authorize_aggregate_read` (`:405-441`). Update the docstring. |
| `services/api/smartmatch_api/routers/portals.py` | `_PORTAL_FOR_ROLE["speaker"] = ("speaker", "/speaker-portal")` (`:280`). Insert `speaker` after `volunteer` in `_ROLE_PRIORITY` (`:301`) and `_PORTAL_ORDER` (`:308`). Add `INVITATION_ONLY_ROLES = frozenset({"speaker"})` (C3). |
| `services/api/smartmatch_api/token_pages.py` | **New** (R9, R4, §3.5). `TOKEN_PAGE_HEADERS`, `FORM_MEDIA_TYPE`, `token_page(...)`, `FormRead` + `read_urlencoded_form(...)`, `TokenPathRedactingFilter` + `install_access_log_redaction()`. No `APIRouter`. |
| `services/api/smartmatch_api/routers/outreach.py` | `create_draft` (`:384`): a template in `SYSTEM_ONLY_TEMPLATES` → `400 template_not_composable`. `send_draft` (`:583`): a draft with such a template → `409 outreach_draft_system_only` (R3, §3.3). |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_portal.py` | **New.** `SpeakerPortalRepository`. It never commits, and every timestamp is a parameter (R6). Methods: `lock_profile` (`FOR UPDATE`), `find_invitation_id_by_token_hash` (no lock), `lock_invitation` (`FOR UPDATE`), `revoke_live`, `insert_invitation`, `current_for_profile`, `get_for_send`, `other_credentialed_account_exists`, `bind_new_login`. |
| `services/api/smartmatch_api/speaker_portal_activation.py` | **New.** `activate_new_login(session, *, token, new_password, secret, now, issue_session) -> IssuedSession | None`. The JSON route and the form route both call it (§5). |
| `services/api/smartmatch_api/routers/speaker_portal.py` | **New.** Three routers, each a bare module-level `APIRouter(...)` assignment (`test_policy_matrix.py:8924`): `router` (Connector: invite, revoke, access), `public_router` (`/v1/speaker-portal/activate`), `pages_router` (`GET`/`POST /s/{token}`). |
| `services/api/smartmatch_api/main.py` | Three rows in `CAPABILITY_SCOPED_ROUTERS` (`:338`) under `Capability.SPEAKER_PORTAL`; `routers_for` (`:661`) already drops them. Call `check_speaker_portal_startup(get_settings())` next to `:699-700`. Call `install_access_log_redaction()` once, at import. If #213 has merged, rewire `/i/` onto `token_pages` (§3.5). |
| `services/api/smartmatch_api/config.py` | `speaker_portal_token_secret: SecretStr | None = None` (`SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET`). `check_speaker_portal_startup(settings) -> str | None` beside `require_exercise_workspace_secret` (`:239`), §4.2. |
| `services/worker/smartmatch_worker/outreach.py` | `OutreachSendCommand` (`:127-166`) gains optional `speaker_portal_invitation_id`. `build_outreach_send_handler` (`:210`) gains `speaker_portal_token_secret: str | None` and `speaker_portal_enabled: bool`. The handler runs the §6.2 gate after `assert_send_allowed` (`:328-349`) and before building `SendRequest` (`:373-387`). It renders the link into `body_text` only. |
| `services/worker/smartmatch_worker/config.py` | `WorkerSettings` (`:186`) gains `product_scope: ProductScope = DEFAULT_PRODUCT_SCOPE`, imported from `smartmatch_domain.product_scope` (the API's import, `config.py:19-22`). It also gains `speaker_portal_token_secret: SecretStr | None` beside `outreach_unsubscribe_secret` (`:431-434`), and `check_worker_speaker_portal_startup(settings) -> str | None` (R10). |
| `services/worker/smartmatch_worker/main.py` | In `create_app` (`:321`), call `check_worker_speaker_portal_startup(resolved)` before the `build_outreach_send_handler` wiring (`:468-489`), and pass both results in. |
| `docker-compose.yml` | Pass `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET: ${SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET:-}` into the `api` (`:433`) and `worker` (`:516`) `environment` blocks. An empty value counts as missing. This passes the secret through; it does not turn the capability on. |
| `.env.example` | A new commented block after the exercise secret (`:191`). `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET=`: required only when `SPEAKER_PORTAL` is on; api and worker must hold the same value; at least 32 chars; generate it with `python -c "import secrets; print(secrets.token_urlsafe(48))"`; rotating it kills live invitations. |
| `docs/operations/vm-deploy.md` | New subsection "Speaker portal token secret": where it is set (api + worker), the fail-fast rule, rotation (§4.3), access-log redaction (§4.5), the shared rate-limit bucket (§3.2). |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerPortalInvite.tsx` | **New.** §7. Rendered from `ContactRow` (`CoordinatorSpeakerContacts.tsx:136`) only when `isCapabilityEnabled("speaker_portal")`. |
| `apps/web/legacy-frontend/src/lib/api.ts` | `fetchSpeakerPortalAccess`, `inviteSpeakerToPortal`, `revokeSpeakerPortalInvitation` after `fetchSpeakerContactChannels` (`:4042`). |
| `apps/web/legacy-frontend/src/lib/principal.ts` | `PortalKind` (`:83`) gains `"speaker"`. |
| `apps/web/legacy-frontend/vite.config.ts` | `"^/s/"` in `server.proxy` and `preview.proxy` (`:54-85`), each entry placed **after** the `/v1` entry (§3.5). |
| `apps/web/legacy-frontend/src/app/routes.tsx` | `/speaker-portal` placeholder route (L4 / L6 option a) plus one page, `SpeakerPortalPlaceholder.tsx`. It is **gated**: spread in only when `isCapabilityEnabled("speaker_portal")`, so when the capability is off the path falls to `NotFound`. This departs on purpose from the file's "mount unconditionally" precedent (`:405-410`), because no page may exist for a role nothing can grant. |
| Tests | §8. Also: `tests/integration/test_check_constraints.py` (9 new keys, and the `ck_suppression_record_source` text). `tests/integration/conftest.py` `_TENANT_SCOPED_TABLES`: insert `"speaker_portal_invitation"` after `"cba_invitation_batch"` (T2 `:120`). Move the head pins `0038_speaker_availability` → `0039_speaker_portal` in the **5** files T2 edits: `test_cba_contact_schema.py` (T2 `:155`), `test_cba_weight_settings_persistence.py` (T2 `:194`), `test_event_filed_by_migration.py` (T2 `:83`), `test_exercise_schema_migration.py` (T2 `:55`), `test_host_organization_migration.py` (T2 `:89`). |
| Docs | `README.md:35` (39 revisions, head `0039_speaker_portal`). `docs/operations/supabase-setup.md:162`. `docs/operations/exercise-hosting.md` step-2 head lines only (T2 `:706-713`, T2's C6 rule). `apps/web/DESIGN.md:38-52, :150-152, :372-374`. Amend `docs/decisions/pilot-login-decision-2026-09-04.md:68-70` (L3). Amend `docs/decisions/metrics-authorization-decision-draft.md` §4 to add the R8 exception. `docs/product/cba-capability-policy.md`: new row. `pilot_auth.py:171-175` docstring. |

## 2. DDL — `0039_speaker_portal`

**`speaker_portal_invitation`** columns:

- `id uuid` PK `speaker_portal_invitation_pkey`
- `tenant_id`, `professional_id`, `contact_channel_id`, `issued_by_user_id`: `uuid NOT NULL`
- `token_hash bytea NOT NULL`
- `issued_at timestamptz NOT NULL`, with **no `DEFAULT`** (R6): a caller that forgets to pass it fails on NOT NULL instead of quietly using the database clock
- `expires_at timestamptz NOT NULL`
- `accepted_at`, `revoked_at`: `timestamptz NULL`
- `bound_account_user_id uuid NULL`
- `binding_mode text NULL`

| Name | Definition |
|---|---|
| `uq_speaker_portal_invitation_token_hash` | `UNIQUE (token_hash)` |
| `fk_speaker_portal_invitation_profile` | `(tenant_id, professional_id) → speaker_profile (tenant_id, professional_id) ON DELETE RESTRICT` |
| `fk_speaker_portal_invitation_channel` | `(tenant_id, contact_channel_id) → contact_channel (tenant_id, id) RESTRICT` (`uq_contact_channel_tenant_id`) |
| `fk_speaker_portal_invitation_issued_by` | `(tenant_id, issued_by_user_id) → user_account (tenant_id, id) RESTRICT` |
| `fk_speaker_portal_invitation_bound_account` | `(tenant_id, bound_account_user_id) → user_account (tenant_id, id) RESTRICT` |
| `ck_speaker_portal_invitation_token_hash` | `octet_length(token_hash) = 32` |
| `ck_speaker_portal_invitation_window` | `expires_at > issued_at AND expires_at <= issued_at + interval '7 days'` |
| `ck_speaker_portal_invitation_one_outcome` | `accepted_at IS NULL OR revoked_at IS NULL` |
| `ck_speaker_portal_invitation_outcome_after_issue` | `(accepted_at IS NULL OR accepted_at >= issued_at) AND (revoked_at IS NULL OR revoked_at >= issued_at)` |
| `ck_speaker_portal_invitation_binding` | `(accepted_at IS NULL) = (bound_account_user_id IS NULL) AND (accepted_at IS NULL) = (binding_mode IS NULL)` |
| `ck_speaker_portal_invitation_binding_mode` | `binding_mode IS NULL OR binding_mode IN ('new_login', 'existing_login')` |
| `ck_speaker_portal_invitation_new_login_self` | `binding_mode IS DISTINCT FROM 'new_login' OR bound_account_user_id = professional_id` |
| `uq_speaker_portal_invitation_live` | `CREATE UNIQUE INDEX … (tenant_id, professional_id) WHERE accepted_at IS NULL AND revoked_at IS NULL` |

**`speaker_profile`** adds:

- columns `account_user_id uuid NULL` and `account_bound_at timestamptz NULL`
- `fk_speaker_profile_account (tenant_id, account_user_id) → user_account (tenant_id, id) RESTRICT`
- `ck_speaker_profile_account_bound`: `(account_user_id IS NULL) = (account_bound_at IS NULL)`
- `uq_speaker_profile_account`: `CREATE UNIQUE INDEX … (tenant_id, account_user_id) WHERE account_user_id IS NOT NULL`

**`suppression_record`** adds:

- columns `lifted_at timestamptz NULL` and `lifted_by_user_id uuid NULL`
- `fk_suppression_record_lifted_by (tenant_id, lifted_by_user_id) → user_account (tenant_id, id) RESTRICT`
- `ck_suppression_record_lifted`: `(lifted_at IS NULL) = (lifted_by_user_id IS NULL) AND (lifted_at IS NULL OR lifted_at >= suppressed_at)`
- drop and recreate `ck_suppression_record_source`: `source IN ('unsubscribe_link','one_click','coordinator','bounce','complaint','speaker_portal')`

That is 9 new CHECK keys for `test_check_constraints.py` (7 on the invitation table, 1 on the profile, 1 lifted CHECK), plus the new text of the recreated `ck_suppression_record_source`.

**Downgrade (R7).** Its first statement is a guard, following `0019_redemption_durability.py:414-440`: `SELECT count(*) FROM speaker_portal_invitation WHERE accepted_at IS NOT NULL`. If the count is above 0, raise `RuntimeError`. The message names the count and says a downgrade would orphan `speaker` memberships and passwords set through activation, which have no FK back to this table. Only then, in reverse order:

1. Drop `ck_suppression_record_lifted`, `fk_suppression_record_lifted_by` and both columns.
2. Recreate the 5-value source CHECK. This fails loudly if a `speaker_portal` row exists; T6b-1 writes none.
3. Drop `uq_speaker_profile_account`, `ck_speaker_profile_account_bound`, `fk_speaker_profile_account` and both columns.
4. Drop `speaker_portal_invitation`.

No `membership.role` CHECK exists (`schema.py:166-188`), so `speaker` needs no DDL.

## 3. Routes

### 3.1 Contracts

Connector routes: `router = APIRouter(prefix="/v1/units", tags=["speaker-portal"])`.

- Authorizer `_authorize_speaker_portal`: `load_unit_or_404` (`services/api/smartmatch_api/units.py:44`) + `assert_allowed(..., required_roles=_SPEAKER_PORTAL_ROLES)`, with `_SPEAKER_PORTAL_ROLES = frozenset({"admin", "coordinator"})`. Same shape as `_authorize_speaker_contacts`, `routers/cba_contacts.py:624`.
- Quota is charged first (`charge_quota`, `dependencies.py:286`).
- `now = utc_now()` (`utils.py:10`) is read **once** per request and passed down (R6, §4.6).

| Route | Auth / roles | Request | Success | Errors |
|---|---|---|---|---|
| `POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/portal-invitations` | principal; `{admin, coordinator}` | `{ "contact_channel_id": uuid }`, `extra="forbid"` | `202 { invitation_id, status: "invited", expires_at, job_id, events_url }`. **No `replayed`** (nit: every call mints a new invitation id and therefore a new job idempotency key, so a replay cannot happen and the field would always be `false`). | `404 speaker_contact_not_found`; `409 speaker_portal_already_active` (profile bound); `409 speaker_portal_invitation_conflict` (`uq_speaker_portal_invitation_live` violation, R5); `422 speaker_portal_channel_not_eligible` (unknown id, other professional or unit, not email, or `is_send_eligible` false, `consent.py:261`); `403`; `429 rate_limited` |
| `DELETE …/portal-invitations/current` | same | — | `200 { "revoked": bool }` (`false` = nothing live; idempotent, `logout`'s shape) | `404 speaker_contact_not_found`; `429` |
| `GET …/portal-access` | same | — | `200 { status, contact_channel_id?, issued_at?, expires_at?, bound_at? }`, with `status ∈ none, invited, expired, active` (L4) | `404`; `429` |
| `POST /v1/speaker-portal/activate` | **none** (`UNAUTHENTICATED_ROUTES`) | `{ "token": str 16–128, "new_password": str 1–1024 }`, `extra="forbid"`. The 1024 bound only limits parsing; the policy limit is 256 (§5 step 2). | `200 { access_token, token_type: "bearer", expires_at }` (`LoginResponse` shape, `auth.py:169`) | `400 speaker_portal_invitation_invalid`, one code and one message for every §5 refusal; `422 password_too_weak` (checked **before** the token, so it is no oracle); `422` validation; `429 rate_limited` |
| `GET /s/{token}` | none | — | `200 text/html`: password and confirm form, `method="post"`, no `action`, `autocomplete="new-password"`, token never in the HTML. Uses `TOKEN_PAGE_HEADERS`. | — (identical bytes for every token) |
| `POST /s/{token}` | none | `application/x-www-form-urlencoded` `new_password`, `confirm_password`, read by `read_urlencoded_form(max_bytes=2048, max_fields=4)` | `200 text/html` "Your Speaker account is ready" plus a link to `/login`; **no session** (C4) | `400` html (same bytes for every invalid token); `422` html (weak, or passwords differ); `413` html (body over 2048 bytes); `429` |

**Form cap arithmetic (R9).** Two 256-character ASCII passwords, fully percent-encoded, come to 2 × 768 + 31 bytes of names and separators = 1567 bytes, which is under 2048. A 256-character password of multi-byte characters can go over and gets the `413` page. That is accepted and documented in the page text.

### 3.2 Invite order, locks and rate limits (R5, R6)

Invite steps, in order:

1. `charge_quota`.
2. Authorize.
3. `lock_profile(tenant_id, owning_unit_id=unit.id, professional_id)`: `SELECT … FROM speaker_profile … FOR UPDATE`. A miss returns `404`. This is the **first lock** in both invite and activation.
4. `account_user_id IS NOT NULL` → `409 speaker_portal_already_active`.
5. Load the channel through `ContactChannelRepository.get` (`contacts.py:254`). Match `professional_id`, `owning_unit_id`, `channel_kind == 'email'` and `is_send_eligible`; any mismatch → `422`.
6. `revoke_live(revoked_at=now)`.
7. Mint `invitation_id = uuid4()`. Call `insert_invitation(issued_at=now, expires_at=now + INVITATION_TTL, token_hash=token_hash(derive_token(secret, invitation_id)))`. An `IntegrityError` whose `diag.constraint_name == "uq_speaker_portal_invitation_live"` → `409 speaker_portal_invitation_conflict`; any other constraint re-raises. Pattern: `spend.py:346-353`. The profile lock makes this unreachable in practice; the mapping is defence in depth.
8. `compose_draft` with `activation_url = ACTIVATION_URL_SENTINEL`.
9. `create_draft(status=APPROVED, approved_by=principal, approved_at=now)`. Precedent: `cba_invitations.py:910-929`.
10. `submit_command(OUTREACH_SEND_COMMAND_TYPE, owning_unit_id=unit.id, payload={"draft_id", "speaker_portal_invitation_id"}, idempotency_key=f"speaker-portal-invitation:{invitation_id}")` (`commands.py:87`). This commits the revoke, the insert, the draft and the job as one transaction.

There is no invite-time "email in use" check (L1).

**Rate limits:**

- `speaker_portal.invite` 20/min and `speaker_portal.read` 120/min, per principal.
- Activation (JSON and form share one limit) uses `LoginAttemptLimiter` (`pilot_auth.py:305`) with `RateLimit("speaker_portal.activate", 10, 5 min)` and `caller_key = "speaker_portal.activate:" + client host`. The table keys on `caller_key` only (`schema.py:1696-1708`), so an unprefixed key would share `/v1/auth/login`'s counter. The attempt is charged and committed first (`auth.py:224-259`).

**The shared bucket behind the proxy (nit, documented, not fixed).** On the VM the chain is Cloudflare Tunnel → Vite at `127.0.0.1:5173` → api (`vm-deploy.md:92-96`). The app parses no `X-Forwarded-For` (`auth.py:200-205`), so every activation attempt carries the Vite hop's address. In practice there is **one** 10-per-5-minutes bucket for all Speakers, as `/v1/auth/login` already has. The consequences:

- It is a denial-of-service lever: one caller can stall every activation for 5 minutes.
- It is not a guessing risk: the token is 256 bits.
- The real per-client limit belongs at the edge, which `exercise-hosting.md` §5 already says for the exercise.

`vm-deploy.md` gets this paragraph. The per-client edge rule is a follow-up card (§12).

### 3.3 System-only templates (R3)

`SYSTEM_ONLY_TEMPLATES` (domain, §1) names the templates only a system flow may compose or send.

1. `POST /v1/units/{unit_id}/outreach/drafts` (`routers/outreach.py:384`) checks `body.template_id in SYSTEM_ONLY_TEMPLATES` right after `_authorize_outreach` and before `load_recipient`. A match → `400 template_not_composable`, with nothing read or written. Without this, a Connector could compose the portal template with any `activation_url`, which is a phishing link in an institutional email.
2. `POST …/outreach/drafts/{draft_id}/send` (`:583`) checks `draft.template_id in SYSTEM_ONLY_TEMPLATES` right after the draft 404 check. A match → `409 outreach_draft_system_only`, and no job is submitted. Without this, the invite's approved draft could be re-sent with no invitation id; the worker would refuse it (§6.2), but the Connector should hear at the moment they act.
3. The invite route calls `compose_draft` directly and is the only composer of this template.
4. `cba.speaker_invitation.v1` has the same phishing shape: a caller-supplied `response_url` through the generic compose route. It is **not** added here, because that would change a shipped route's behaviour. It goes to the `/i/` card (§12) and is an open item.

### 3.4 Authorization rows and the Speaker column (R8, owner ruling 2026-09-23)

**Ruling.** A speaker-only principal is refused `metrics.read` and `metrics.speaker_pipeline`, the two membership-only operations (`test_policy_matrix.py:2504`). Both call `_authorize_aggregate_read`, the only policy call with no `required_roles` in `services/api` (checked by AST over every `assert_allowed`/`evaluate` call). Every other operation already refuses `speaker` on its role set.

**Mechanism: policy rule 8, `excluded_roles`**, parallel to rule 7's `tenant_wide_roles`:

- `evaluate(..., excluded_roles: frozenset[str] = frozenset())`. Path 1 and Path 1b skip an active membership whose role is in `excluded_roles`.
- The denial is distinct and countable. If nothing allowed, and at least one active, non-blank membership that **covers** the resource was skipped only for exclusion, the reason is `membership_role_excluded` instead of `no_grant`.
- Precedence is unchanged. Suspension, tenant mismatch and explicit deny are decided first. Path 2 is unaffected, so with `require_membership=True` a grant still gives `resource_grant_lacks_membership`.
- `ValueError` if `excluded_roles` intersects `required_roles` or `tenant_wide_roles`. A role cannot be both excluded and admitted.
- `metrics.py` passes `excluded_roles=_AGGREGATE_EXCLUDED_ROLES` (`{"speaker"}`).

The alternative was rejected: enumerating `required_roles = {admin, coordinator, student, volunteer}` would turn a membership-only operation into a role-gated one and silently refuse every future role. The decision record's §4 ("any active unit membership with a role") would then be false. Rule 8 is the narrow exception the owner ruled.

**`test_policy_matrix.py` changes:**

1. **Shape** `speaker_at_owning_unit`: `memberships=(_member(OWNING_UNIT, "speaker"),)`, described as "a Speaker's own login: an active `speaker` membership at the owning unit, invitation-only (T6b-1)". It is appended to `SHAPES` (`:2573`). It is **not** added to `_ACTIVE_OWNING_UNIT_SHAPES` (`:9512`), so no existing wrong-role assertion changes.
2. **Full MATRIX column**, one cell in each of the 74 existing rows plus the 3 new ones = 77 cells. All deny.
   - `metrics.read` (and `metrics.speaker_pipeline` through the alias at `:8366`) → `deny("membership_role_excluded", why=<owner ruling 2026-09-23>)`.
   - The other 75 → `deny("no_grant")`, the reason every `volunteer_at_owning_unit` role-gated cell carries today (68 of them).
   - The 5 operations that admit `volunteer` (`metrics.read`, `speaker_request.create`, `speaker_request.list_own`, `host_organization.read_own`, `host_organization.upsert_own`) do not admit `speaker`, and their cells say so explicitly.
3. **`Operation` fields** `excluded_roles_constant: str | None = None` and `excluded_roles: frozenset[str] = frozenset()`, set on both metrics rows to `"_AGGREGATE_EXCLUDED_ROLES"` / `{"speaker"}`. `_authorize` (`:8413`) passes `excluded_roles=operation.excluded_roles`.
4. **New tests:**
   - `test_the_authorizer_passes_the_excluded_roles_the_matrix_names`: source and live object, both directions, modelled on `:9339`.
   - `test_every_excluded_role_operation_is_declared` (`EXCLUDED_ROLE_OPERATIONS = {"metrics.read", "metrics.speaker_pipeline"}`).
   - `test_a_speaker_membership_reaches_no_operation`: every row's Speaker cell denies, checked by `_observe`.
5. **Ledgers.**
   - Three `Operation`s (`speaker_portal.invite`, `.revoke`, `.read`), with rectangles copied from the speaker-contact rows plus the Speaker cell.
   - `UNAUTHENTICATED_ROUTES` (`:384`) gains `GET /s/{token}`, `POST /s/{token}` and `POST /v1/speaker-portal/activate`, with reasons.
   - The ledger is AST-derived (`:360`), so the rows are required even while the routes are unmounted.
   - `AUTHENTICATED_ONLY_ROUTES` (`:870`) is unchanged. Its three routes (`/v1/me`, `/v1/me/portals`, `/v1/auth/logout`) answer a Speaker as any principal, pinned by §8's contract tests.

**`tests/authz/test_policy_negatives.py`** gains `test_an_excluded_role_is_refused_with_its_own_reason`, `test_an_excluded_role_never_outranks_suspension_tenant_or_explicit_deny`, `test_excluded_roles_cannot_overlap_required_or_tenant_wide`, and `test_a_second_non_excluded_membership_still_permits` (speaker + volunteer at the owning unit → permit through volunteer; the two-membership shape itself is T6b-5).

**`test_route_roles.py`:** three literal rows with `_SPEAKER_PORTAL = frozenset({"admin", "coordinator"})`, the exact-set test extended (`:201-212`), and `test_speaker_portal_roles_matches_the_live_constant`.

### 3.5 `token_pages.py` and T6a (R9)

The new module `services/api/smartmatch_api/token_pages.py` holds only generic, token-free helpers:

- `TOKEN_PAGE_HEADERS`: T6a's five headers verbatim (`Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `X-Content-Type-Options: nosniff`, and the CSP `default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`).
- `FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"`.
- `token_page(title, heading, body_html, *, status_code) -> HTMLResponse`: byte-identical to T6a's `_token_page`.
- `FormRead` (frozen dataclass: `outcome: FormReadOutcome` of `OK | TOO_LARGE | INVALID`, `fields: Mapping[str, tuple[str, ...]]`).
- `async def read_urlencoded_form(request, *, max_bytes: int, max_fields: int) -> FormRead`. It **never raises**. It covers `Content-Length` over the cap, the buffered body over the cap, `ClientDisconnect`, a wrong media type, `UnicodeDecodeError` and `parse_qs(..., keep_blank_values=True, max_num_fields=max_fields)` raising `ValueError`. It is T6a's `_read_answer_form` minus the `response` classification.
- `TokenPathRedactingFilter` and `install_access_log_redaction()` (§4.5).

The `/s` wrappers live in `routers/speaker_portal.py`: `read_urlencoded_form(max_bytes=2048, max_fields=4)`, then exactly one `new_password` and exactly one `confirm_password`, or the `400`-shaped "use the form" page.

**Composition with T6a (#213).** T6b-1 never edits T6a's `/i/` hunk unless T6a is already on `main`:

| When implementation starts | T6b-1 does | T6a does |
|---|---|---|
| **#213 merged** (rebase the stack onto `main` first) | Moves `_TOKEN_PAGE_HEADERS`, `_FORM_MEDIA_TYPE`, `_token_page` and the body-reading half of `_read_answer_form` out of `main.py` into `token_pages.py`. `_read_answer_form` becomes a thin `Depends` wrapper: `read_urlencoded_form(max_bytes=1024, max_fields=4)` plus the `response` → `FormOutcome` map. Extends T6a's `viteProxy.test.tsx` with `/s/` cases. **Proof: T6a's `tests/contract/test_cba_invitations_api.py` and `test_api_health.py` pass unchanged.** | Nothing. |
| **#213 not merged** | Creates `token_pages.py` with the helpers, copied from `origin/feat/b26-t6a:services/api/smartmatch_api/main.py`. Leaves `main.py`'s `/i/` code alone. Adds a standalone `src/viteProxySpeakerPortal.test.tsx` with the same matcher as T6a's. | On its rebase after T6b-1: delete its private copies and import from `token_pages` (same wrapper as the left column). Fold the two proxy tests into one. |

Known textual overlap in both cases: the `main.py` import block (T6a inserts `from smartmatch_api.dependencies import DbSession` under the `config` import that T6b-1 extends) and adjacent `vite.config.ts` proxy entries. Both resolve as a union. The PR body lists them.

## 4. Token handling (C1 = b, owner-ruled)

### 4.1 Shape (R1, nit: one versioned label)

1. 256 bits. `token = base64url_nopad(HMAC-SHA256(secret, TOKEN_DERIVATION_LABEL + str(invitation_id)))`, with `TOKEN_DERIVATION_LABEL = "speaker-portal:v1:"`: a 32-byte digest, 43 characters. The pattern is `unsubscribe_token` (`worker/outreach.py:185-202`). `derive_token` lives in `smartmatch_domain.speaker_portal`, and the worker **imports** it; there is no second copy. A later `v2` label is a new derivation, not an edit.
2. Stored: `token_hash = sha256(token.encode()).digest()` → `bytea(32)`, `uq_…_token_hash`. The token itself is stored nowhere. It is not in `outreach_draft.body` (the draft carries `ACTIVATION_URL_SENTINEL`) and not in the job payload (only the invitation id).
3. Verified against the secret, not only the hash (R1).
   - Activation looks the row up by `token_hash`, then requires `hmac.compare_digest(token, derive_token(secret, invitation.id))`.
   - The worker requires `hmac.compare_digest(token_hash(derive_token(secret, invitation.id)), invitation.token_hash)` before it sends.
   - Rotating the secret therefore kills every live link on both sides, and a worker whose secret differs from the API's refuses instead of mailing a dead link.
4. Rendered once, by the worker, into `SendRequest.body_text` (`worker/outreach.py:373-387`) as `{outreach_public_base_url}/s/{token}`. A re-drive derives the same token.
5. Expiry: `expires_at = now + 7 days`, checked in SQL as `expires_at > :now` with the injected `now` (§4.6). The CHECK caps it at 7 days.
6. Never echoed: not in the `/s` HTML, not in any response body or header, not in application logs, and redacted from the access log (§4.5). Headers `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
7. One-time: `accepted_at` is set in the activation transaction; a new invite or `DELETE …/current` sets `revoked_at`.
8. The secret is `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET`, at least 32 characters. The API and the worker both read it and must hold the same value. It has **no synthetic fallback**, unlike `SYNTHETIC_UNSUBSCRIBE_SECRET`: a forgeable activation link lets someone else take over the account.

### 4.2 Startup validation (R10)

`check_speaker_portal_startup(settings: Settings) -> str | None` in `services/api/smartmatch_api/config.py`:

- Capability off → returns `None` without reading the secret.
- Capability on → returns the unwrapped secret.
- Capability on with the secret missing, blank or shorter than 32 → raises `ValueError`. The message names `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET` and the minimum length and quotes no part of the value.

`ValueError` matches `require_exercise_workspace_secret`, `config.py:239-275`. It is a plain function so tests call it with a `Settings` stub, not by importing `main`.

`check_worker_speaker_portal_startup(settings: WorkerSettings) -> str | None` in `services/worker/smartmatch_worker/config.py` follows the same contract, reading the capability from `is_capability_enabled(settings.product_scope, Capability.SPEAKER_PORTAL)`.

| Process | `SPEAKER_PORTAL` | Secret | Result |
|---|---|---|---|
| API (`main.py`, at import, next to `:699-700`) | on | missing, empty or < 32 chars | `ValueError`; the process does not boot |
| API | off | anything | Boots; the secret is not read |
| Worker (`create_app`, `main.py:321`, before `:468`) | on (its own `product_scope`) | missing, empty or < 32 chars | `ValueError`; the worker does not boot |
| Worker | off | anything | Boots; `speaker_portal_enabled=False` goes to the handler |
| Worker, at send | off, or secret `None` | a job with `speaker_portal_invitation_id`, or a `cba.speaker_portal_invite.v1` draft, arrives | Terminal `PolicyFailure` `speaker_portal_disabled` / `speaker_portal_secret_missing` (§6.2); nothing is sent |

### 4.3 Rotation

The token is derived, never stored, and both sides verify against the current secret (§4.1 item 3). So **rotating the secret invalidates every live invitation.** Activation answers the generic `400`, and a re-drive of an old send is refused with `speaker_portal_token_mismatch` instead of mailing a dead link. The procedure goes in `vm-deploy.md`:

1. Set the new value on api and worker together.
2. Restart both.
3. Run `UPDATE speaker_portal_invitation SET revoked_at = now() WHERE accepted_at IS NULL AND revoked_at IS NULL;` so that Connectors see "Invite again" instead of a stale "Invited". This is an operator's statement; the `now()` rule (§4.6) binds application code.
4. Re-invite anyone still waiting.

Accepted invitations and active logins are unaffected, because once the account is active a Speaker signs in with the password.

### 4.4 Where the token never appears (each point has a test in §8)

`outreach_draft.body` and `subject`; `GET /v1/units/{unit_id}/outreach/drafts`; `job.payload`; `outreach_send`; the `202` invite response; `GET …/portal-access`; the `/s` HTML; application logs; the uvicorn access log.

### 4.5 Access log (R4) — redact, keep the log

**Decision: redact, do not disable.** `token_pages.install_access_log_redaction()` adds one `TokenPathRedactingFilter` to `logging.getLogger("uvicorn.access")`. It is idempotent: it checks for an existing instance. `main.py` calls it at import.

- The filter rewrites the record's path argument (`record.args[2]`, uvicorn's `'%s - "%s %s HTTP/%s" %d'`) with `^/(s|i|u)/[^/?#]+` → `/\1/<redacted>`. `/speaker-portal` and `/settings` are untouched.
- It returns `True`, so the line is still logged with its method, status and client.

Why not `--no-access-log`:

1. The API is started from three places: `Dockerfile.api:148`, `Makefile:384` and `scripts/reset_pilot_dataset.sh:391`. Each would need the flag, and a fourth launcher added later would leak silently.
2. The access log is the only per-request trace in `./smartmatch.sh logs` (`vm-deploy.md:1005-1024`). Losing it for every route to protect three is the wrong trade.
3. The redaction also closes the same leak for the `/i/` and `/u/` tokens that ship today.

Order is safe: uvicorn configures logging in `Config.__init__`, before it imports the app, so a filter added at app import survives, including under `--reload`.

Outside this repository's control: Cloudflare's edge logs see full URLs. Vite does not log proxied paths by default. Both are noted in `vm-deploy.md`.

### 4.6 One clock (R6)

Every timestamp T6b-1 writes or compares comes from one `now` read at the top of the request (API) or taken from `clock()` (worker, `worker/outreach.py:219`, already injected):

- the invitation's `issued_at`, `expires_at`, `revoked_at` and `accepted_at`
- `speaker_profile.account_bound_at`
- `membership.valid_from` and `membership.created_at`
- `PilotCredentialRepository.upsert(now=)` (`pilot_auth.py:161-168`)
- `PilotSessionRepository.issue(issued_at=, expires_at=)` (`:212-221`)
- `LoginAttemptLimiter.check(now=)` (`:317`)
- `create_draft(approved_at=)`
- the expiry comparison `expires_at > :now`

No T6b-1 SQL calls `now()`. Two server defaults remain, both in unchanged code paths: `outreach_draft.created_at` and `job.created_at`.

## 5. Activation transaction (`activate_new_login`)

Lock order is **profile → invitation → address advisory lock**, the same as invite's profile → invitation (R5). No path takes them in the other order.

1. Charge `LoginAttemptLimiter`, commit (ADR-0015).
2. `check_new_password(new_password)`: length from `MINIMUM_PASSWORD_LENGTH` (12, `pilot_credentials.py:114`) to `MAXIMUM_PASSWORD_LENGTH` (256), and not all whitespace. Otherwise `422 password_too_weak`. Pure, and before any token read. The form route also checks `new_password == confirm_password` here (`422` page).
3. `is_well_formed_token(token)` (43 urlsafe characters), else `400` with no database read. This is the same timing residual as T6a's form route (T6a plan §5), documented.
4. `find_invitation_id_by_token_hash(sha256(token))`, which takes no lock. A miss → `400`.
5. `lock_profile(tenant_id, professional_id)` `FOR UPDATE`, found through the invitation's own `(tenant_id, professional_id)`.
6. `lock_invitation(id)`: `SELECT … FROM speaker_portal_invitation JOIN speaker_profile JOIN contact_channel JOIN org_unit … FOR UPDATE OF speaker_portal_invitation`. Refuse with `400` when any of these holds:
   - the row is gone
   - `accepted_at` or `revoked_at` is set
   - `expires_at <= :now`
   - `speaker_profile.account_user_id IS NOT NULL`
   - `contact_channel.channel_kind <> 'email'`
   - `contact_channel.contact_state NOT IN ('consented', 'active_candidate')` (**R11**, `ACTIVATABLE_CHANNEL_STATES`)
7. `hmac.compare_digest(token, derive_token(secret, invitation.id))`, else `400` (**R1**: a rotated secret lands here).
8. `SELECT pg_advisory_xact_lock(hashtextextended('speaker-portal-email:' || lower(btrim(:address)), 0))`. This serializes two new-login activations for one address, and it is the only lock new-login needs; row locks on existing credentials are T6b-5.
9. `other_credentialed_account_exists(address, excluding_user_id=professional_id)`: `user_account JOIN pilot_credential WHERE lower(btrim(user_account.email)) = lower(btrim(:address)) AND user_account.id <> :excluding`, across all tenants. A hit → `400` (boundary 2). Also `400` if the contact account is suspended.
10. `UPDATE user_account SET email = btrim(:address), version = version + 1 WHERE tenant_id, id = professional_id`. Stored trimmed, so `load_by_email`'s `lower(email) = lower(strip(input))` (`pilot_auth.py:137`) matches. `ensure_account` is `ON CONFLICT DO NOTHING` (`professionals.py:115-126`), so a later contact edit cannot reset it.
11. `PilotCredentialRepository.upsert(user_id=professional_id, password=derive_password_hash(pw, salt=new_salt()), now=now)`.
12. `INSERT membership (id, tenant_id, user_id=professional_id, granted_path=<org_unit.path of the profile's owning unit>, role='speaker', valid_from=now, created_at=now)`.
13. `UPDATE speaker_profile SET account_user_id = professional_id, account_bound_at = :now WHERE … AND account_user_id IS NULL`. 0 rows → roll back and answer `400`.
14. `UPDATE speaker_portal_invitation SET accepted_at = :now, bound_account_user_id = professional_id, binding_mode = 'new_login' WHERE id AND accepted_at IS NULL AND revoked_at IS NULL`.
15. JSON route: `new_session_token()`, then `PilotSessionRepository.issue(token_hash=hash_session_token(t), issued_at=now, expires_at=now + SESSION_TTL)` (`pilot_credentials.py:108`, `:201`, `:213`). Form route: skip.
16. One `commit`. On any exception, `get_session` rolls back and nothing from steps 10–15 persists.

**Every `400` above is the same status, code, message and bytes.** §8 parameterises this.

## 6. Worker (C1, R1, R2, R10)

### 6.1 Command

`OutreachSendCommand.read` accepts an optional `speaker_portal_invitation_id`, read with `_read_uuid` (`:168-181`). A malformed value joins `problems` and ends in `invalid_command_payload`, as today.

### 6.2 Invitation gate (R2)

The gate runs inside the handler's own session, after `assert_send_allowed` (`:328-349`) and before `SendRequest` (`:373`). The trigger is **pairing**: the draft's template is in `SYSTEM_ONLY_TEMPLATES`, **or** the payload carries an invitation id. When the gate is triggered, every check below must pass.

Each refusal:

- calls `_record_refusal(..., event_type=BLOCKED, disposition=BLOCKED, reason=<code>, now=now)`
- raises a **terminal** `PolicyFailure(reason=<code>)` (`handlers.py:167`)
- sends nothing

| # | Check | Reason code |
|---|---|---|
| 1 | Capability on in the worker's `product_scope` | `speaker_portal_disabled` |
| 2 | Secret configured | `speaker_portal_secret_missing` |
| 3 | Template is `cba.speaker_portal_invite.v1` **and** an invitation id is present; either without the other fails | `speaker_portal_invitation_pairing` |
| 4 | `get_for_send(tenant_id=job.tenant_id, invitation_id)` finds it, and the lookup is tenant-scoped | `speaker_portal_invitation_not_found` |
| 5 | The invitation profile's `owning_unit_id == draft.owning_unit_id == job.owning_unit_id` | `speaker_portal_invitation_unit_mismatch` |
| 6 | Live: `accepted_at IS NULL AND revoked_at IS NULL` | `speaker_portal_invitation_not_live` |
| 7 | Unexpired: `expires_at > now` | `speaker_portal_invitation_expired` |
| 8 | `invitation.contact_channel_id == draft.contact_channel_id` | `speaker_portal_channel_mismatch` |
| 9 | `draft.body.count(ACTIVATION_URL_SENTINEL) == 1` and `ACTIVATION_URL_SENTINEL not in draft.subject` | `speaker_portal_sentinel_invalid` |
| 10 | `compare_digest(token_hash(derive_token(secret, id)), invitation.token_hash)` (**R1**) | `speaker_portal_token_mismatch` |

When all 10 pass, `body_text = draft.body.replace(ACTIVATION_URL_SENTINEL, f"{base}/s/{token}")`, and `draft.body` in the database is untouched.

Drafts that trigger nothing (every other template, with no invitation id) take today's path unchanged. A sentinel string that a caller typed into another template's placeholder is inert: it is never replaced, because gate 3 is not triggered.

## 7. Frontend contract — "Invite to portal"

- **Gate:** `isCapabilityEnabled("speaker_portal")`. It is false in the build, so the component never mounts and `/speaker-portal` is `NotFound`. Vitest mocks `lib/productScope` to cover the on-states.
- **Reads:** `useScopedQuery({ resource: "speaker-portal-access", params: [unitId, professionalId] })`. Channels come through the existing `fetchSpeakerContactChannels`, and only when the panel opens. Eligible = `send_eligible && channel_kind === "email"`.
- **States:**
  - loading
  - `none` → "Invite to portal". Disabled with the reason shown when no channel is eligible: "No email address this Speaker agreed to receive".
  - `invited` → "Invited · link expires {date}", "Send a new link", "Revoke".
  - `expired` → "Link expired", "Invite again".
  - `active` → "Portal active since {date}", with no revoke (unbind is T6b-5).
  - error, by `ApiRequestError.code`.
- **Writes:** `useMutation`; submit disabled while pending; no optimistic state; invalidate only `["speaker-portal-access", unitId, professionalId]`. Error mapping:
  - `409 speaker_portal_already_active` → refetch, then "This Speaker already has portal access".
  - `409 speaker_portal_invitation_conflict` → refetch, then "Another invitation was just sent. Refresh and try again".
  - `422 speaker_portal_channel_not_eligible` → "That address can no longer be emailed".
  - Revoke asks for confirmation.
- **Fixture notice:** while the worker is in fixture mode no email is delivered (boundary 5). The component shows no delivery claim beyond "Invited".
- **A11y:** the channel choice is a `<fieldset>` + `<legend>Send the link to</legend>` of radios named by address; one `role="status"` region; errors use `role="alert"` + `aria-describedby`; buttons are at least 44px (`min-h-11`).

## 8. Tests (TDD per milestone)

Run one file at a time locally. CI runs `pytest tests/ -m "not e2e"` with Postgres, and `vitest run`. Build token-shaped literals at runtime (forbidden-behaviour scanner).

| File | Level | Tests |
|---|---|---|
| `tests/integration/test_speaker_portal_migration.py` | integration | Every §2 CHECK (accept and refuse). Each composite FK refuses a cross-tenant row. `test_one_live_invitation_per_profile`, `test_one_profile_per_account`, `test_source_admits_speaker_portal`, `test_issued_at_has_no_default` (R6), `test_downgrade_then_upgrade_round_trips`, `test_downgrade_refuses_while_an_accepted_invitation_exists` (R7: the row survives, and the message names the count). |
| `tests/unit/test_speaker_portal_domain.py` | unit | `test_token_is_256_bits_urlsafe`, `test_token_is_stable_per_invitation_and_secret`, `test_token_changes_with_the_secret`, `test_derivation_label_is_versioned` (`"speaker-portal:v1:"`), `test_token_hash_is_32_byte_sha256`, `test_well_formed_token_is_43_urlsafe_chars`, `test_invitation_ttl_is_seven_days`, `test_password_policy_rejects_short_blank_and_over_256`, `test_password_policy_accepts_12_and_256`, `test_status_none_invited_expired_active`, `test_activatable_states_are_consented_and_active_candidate` |
| `tests/unit/test_speaker_portal_template.py` | unit | `test_invite_template_is_in_the_closed_registry`, `test_invite_template_is_system_only`, `test_composed_body_carries_the_sentinel_exactly_once_and_not_in_subject` |
| `tests/unit/test_role_presentation.py`, `test_compose_dev_principals.py`, `test_cba_scope_policy.py` | unit | `STORED_ROLES` gains `speaker` (`:52`). `:104` becomes `test_the_speaker_role_presents_as_the_speaker_persona`. `test_compose_dev_principals.py:93-110` exempts `INVITATION_ONLY_ROLES`. `SPEAKER_PORTAL` is listed as staged-off and is not in `DISABLED_UNDER_CBA` (`:80`). |
| `tests/unit/test_speaker_portal_composition.py` | unit | `test_speaker_portal_is_off_in_every_scope`; `test_routes_unmounted_when_off` (`routers_for(Settings())` and `smartmatch_api.main.app.routes` hold none of the 6 paths); `test_openapi_document_has_no_speaker_portal_paths` (`contracts/openapi/smartmatch.json`); `test_routes_mount_when_on` (a settings stub overriding `capability_enabled`); `test_capability_requires_login_outreach_and_contacts` |
| `tests/authz/test_policy_negatives.py` | authz | The 4 rule-8 tests (§3.4) |
| `tests/authz/test_policy_matrix.py`, `tests/authz/test_route_roles.py` | authz | The §3.4 shape, the 77-cell Speaker column, the `excluded_roles` source check and declaration table, `test_a_speaker_membership_reaches_no_operation`, the 3 operations, 3 `UNAUTHENTICATED_ROUTES` rows, and the route-roles rows. `test_every_route_is_either_authenticated_or_declared_public` covers the 3 public routes. |
| `tests/contract/test_metrics.py` | contract (DB) | `test_speaker_only_principal_is_refused_aggregates` (`/metrics` and `/speaker-pipeline`, 403), `test_host_with_speaker_role_still_reads_aggregates` |
| `tests/unit/test_token_pages.py` | unit | `test_read_form_refuses_declared_and_actual_oversize`, `test_read_form_refuses_wrong_media_type_bad_utf8_and_too_many_fields`, `test_read_form_never_raises` (param: disconnect), `test_token_page_is_byte_stable_and_carries_the_headers`, `test_access_log_filter_redacts_s_i_u_tokens` (param: `/s/x`, `/i/x?y`, `/u/x`), `test_access_log_filter_leaves_other_paths` (`/speaker-portal`, `/settings`, `/v1/units/…`), `test_install_is_idempotent_and_attached_after_importing_main` |
| `tests/unit/test_speaker_portal_secret.py` | unit | `test_check_speaker_portal_startup_refuses_on_without_secret` (param: unset, empty, whitespace, 31 chars; the message does not quote the value); `test_check_speaker_portal_startup_returns_secret_when_on`; `test_check_speaker_portal_startup_is_none_when_off`; the same three for `check_worker_speaker_portal_startup`; `test_worker_settings_default_to_the_api_product_scope` (`DEFAULT_PRODUCT_SCOPE`); `test_env_example_documents_the_secret`; `test_compose_passes_the_secret_to_api_and_worker` |
| `tests/contract/test_outreach.py` | contract (DB) | `test_generic_compose_refuses_a_system_only_template` (400 `template_not_composable`, no draft row), `test_generic_send_refuses_a_system_only_draft` (409 `outreach_draft_system_only`, no job) |
| `tests/unit/test_outreach_send_speaker_portal.py` | unit (worker, fakes, fixed `clock`) | `test_worker_renders_the_activation_link_at_send_only`; `test_draft_body_is_unchanged_after_send`; `test_every_gate_refusal_is_terminal_and_sends_nothing` (param over the 10 §6.2 codes: the provider's `sent` stays empty, the send is `BLOCKED`, and the failure is a `PolicyFailure`); `test_other_templates_are_untouched`; `test_sentinel_in_another_template_is_inert`; `test_worker_and_api_derive_the_same_token` (one import, one label) |
| `tests/contract/test_portals_api.py` | contract (DB) | `test_speaker_membership_lists_the_speaker_portal`, `test_host_default_portal_stays_volunteer_with_speaker_role` |
| `tests/contract/test_speaker_portal_api.py` (app built with the stub settings; `integration` mark) | contract (DB) | See the lists below. |
| `tests/integration/test_speaker_portal_activation.py` | integration | `test_activation_is_atomic` (fail step 12, and nothing from steps 10–14 persists); `test_concurrent_activation_of_one_token_binds_once`; `test_concurrent_new_login_for_one_address_creates_one_credential`; `test_invite_and_activation_take_the_profile_lock_first` (two sessions, no deadlock: an invite blocked behind an activation's profile lock proceeds after commit and gets `409 speaker_portal_already_active`) |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerPortalInvite.test.tsx` | Vitest | `renders nothing when the capability is off`, `disables invite with a reason when no channel is eligible`, `sends the chosen channel id and shows Invited from the response`, `maps 409 and 422 codes to their messages` (including `speaker_portal_invitation_conflict`), `revoke asks first and invalidates only the access key`, `active state offers no revoke` |
| `apps/web/legacy-frontend/src/app/routes.test.tsx` (new) | Vitest | `speaker-portal is not routed when the capability is off`, `speaker-portal renders the placeholder when on` (mocked) |
| Proxy test (§3.5: T6a's `viteProxy.test.tsx`, or the standalone file) | Vitest | `/s/abc` matches in both proxies; `/speaker-portal`, `/settings` and `/s` do not |

`tests/contract/test_speaker_portal_api.py` covers the invite and read routes:

- `test_invite_returns_202_and_one_live_invitation` (the body has no `replayed`)
- `test_invite_stores_explicit_timestamps_from_one_clock` (R6: `issued_at == frozen now`, `expires_at == now + 7d`)
- `test_invite_draft_body_holds_only_the_placeholder`
- `test_outreach_drafts_list_never_contains_the_token` (raw text search for the token and its `sha256` hex)
- `test_job_payload_and_invite_response_never_contain_the_token`
- `test_invite_refuses_ineligible_channel` (param: suppressed, not `active_candidate`, other professional, other unit, unknown)
- `test_invite_other_unit_profile_is_404`
- `test_invite_bound_profile_is_409`
- `test_live_unique_violation_maps_to_409_conflict` (the repository is forced past the profile lock; R5)
- `test_second_invite_revokes_the_first`
- `test_revoke_is_idempotent`
- `test_access_status_transitions`

It covers activation:

- `test_activate_new_login_binds_and_issues_session`
- `test_activated_speaker_sees_speaker_membership_in_me`
- `test_activation_stores_the_trimmed_address_and_login_works` (R5)
- `test_activate_refuses_every_bad_token_identically`, parameterised over: unknown, malformed, expired, accepted, revoked, profile already bound, address held by another credentialed account, address held with different case and surrounding whitespace (R5), contact account suspended, channel `rejected`, channel `stale`, channel `discovered` (R11), and rotated secret (R1). Every case gives the same status and bytes.
- `test_rotating_the_secret_invalidates_a_live_invitation` (derive under secret A, rebuild the app stub with secret B, get `400`)
- `test_weak_password_is_422_for_any_token` (param: 11 chars, 257 chars, blank)
- `test_activate_refuses_address_held_by_a_credentialed_account` (nothing written: email, credential, membership and invitation unchanged)
- `test_activate_never_echoes_the_token`
- `test_activation_is_rate_limited_separately_from_login`

It covers the `/s` pages:

- `test_s_page_is_identical_for_every_token`
- `test_s_form_activates_without_issuing_a_session`
- `test_s_form_refuses_mismatched_confirmation`
- `test_s_form_body_over_2048_bytes_is_413`
- `test_s_form_accepts_two_256_char_ascii_passwords`

## 9. Commit milestones

Each milestone is one commit: its tests are written first and run red locally (the red run is noted in the commit body), then the code makes them green. The migration comes first.

1. `feat: 0039_speaker_portal migration and schema mirror`. Migration with the R7 guard, the mirror, `test_speaker_portal_migration.py`, the check-constraint table, conftest order, the 5 head pins, and the README / supabase / exercise-hosting head lines.
2. `feat: speaker portal domain, capability, template and role mapping`. `smartmatch_domain/speaker_portal.py`, `SYSTEM_ONLY_TEMPLATES` and the template, the capability and its docstring, role presentation, the portal mapping, `productScope.ts`, `roleLabels.ts`, and the unit tests.
3. `feat: refuse the speaker role on aggregate metrics reads`. Policy rule 8, `metrics.py`, the matrix shape and column, the negatives, `test_metrics.py`, and the metrics decision amendment (R8).
4. `refactor: token_pages module with read_urlencoded_form and access-log redaction`. `token_pages.py`, the `main.py` install call, the `/i/` rewire if #213 has merged (§3.5), and `test_token_pages.py` (R4, R9).
5. `feat: speaker portal invite, revoke, access and activation routes`. The persistence repository, the activation service, the routers, the `main.py` rows, `check_speaker_portal_startup`, the outreach-router system-only guards, the authz ledgers, and the contract and integration tests (R1, R3, R5, R6, R11).
6. `feat: late-bound activation link and invitation gate in the outreach worker`. The worker command, the gate, worker config, `check_worker_speaker_portal_startup`, compose passthrough, `.env.example`, and the worker tests (R1, R2, R10).
7. `feat: Invite to portal button and gated speaker portal placeholder`. Frontend, `api.ts`, `principal.ts`, the Vite proxy, and the route gate.
8. `docs: speaker role in DESIGN.md, pilot-login amendment, token secret ops`. The §1 docs rows and the `vm-deploy.md` section (secret, rotation, access log, shared bucket, fixture provider).

## 10. Contradictions — all ruled (final)

| # | Conflict | Ruling |
|---|---|---|
| C1 | §4.2 sends through `outreach.send`, which sends `draft.body` exactly as stored (`worker/outreach.py:373-376`). The `/i/` precedent renders its token into the body (`cba_invitations.py:860-880`), and `GET /v1/units/{unit_id}/outreach/drafts` returns `body` to every Connector in the unit (`routers/outreach.py:205-221`, `:505`). | **(b), owner.** HMAC token, placeholder in the body, the worker renders the link at send; the DB stores SHA-256(token). Revision 3 adds verification against the secret on both sides (R1) and the worker gate (R2). |
| C2 | Nothing makes "off by default" work: capabilities are per-scope constants (`product_scope.py:244-338`), and the module forbids deployment settings deciding product scope (`:17-20`). | **(a).** `False` in all 3 scopes; turning it on is a reviewed code change; tests mount the routes through a settings stub. |
| C3 | Adding `speaker` to `_PORTAL_FOR_ROLE` fails `test_compose_dev_principals.py:106`. | **(a).** `INVITATION_ONLY_ROLES` exemption; no compose Speaker is seeded. |
| C4 | §4.2 says "issue a session", but the `/s` form has no JS under the token-page CSP. | **(a).** The JSON route issues the session; the form route activates and links to `/login`. |
| C5 | Before T6b-5, a Host whose email matches gets a link that always fails. | **Confirmed turn-on rule:** T6b-5 merged **and** parent §10 rows 1, 2 and 4 cleared. Recorded in §0 item 4 and in the `Capability.SPEAKER_PORTAL` docstring. |
| R8 | The metrics decision §4 says "any active unit membership with a role", and a `speaker` membership is one. | **Owner, 2026-09-23: deny.** Policy rule 8, `excluded_roles={"speaker"}` on `_authorize_aggregate_read`; the decision record is amended. |

**Later items (accepted as written)**

1. L1: §7 row 6 "email-in-use 409" versus the owner's email-clash ruling. The owner's ruling wins; activation returns the generic `400`.
2. L2: §3.2 "every send-eligibility read changes in the same PR". T6b-3 owns it (Appendix A).
3. L3: `pilot-login-decision-2026-09-04.md:68-70` and `pilot_auth.py:171-175` say no endpoint sets a password or grants a role. Q2 = B supersedes both; amend them in milestone 8.
4. L4: §6 needs Invited / Active / Expired, but §4.2 has no read route, so add `GET …/portal-access`. L6: `/speaker-portal` gets a one-screen placeholder until T6b-4, and the route is capability-gated.
5. L5: the `/i/` token exposure goes to a separate card (§12).

## 11. Risks

| Risk | Likelihood / impact | Mitigation in T6b-1 | Residual / owner |
|---|---|---|---|
| **Connector self-invite.** A Connector records a speaker channel at a mailbox they control, marks it consented, invites it, and activates a Speaker login they operate. Once T6b-2 ships, that login can act as the Speaker. | Low / Medium | The Connector's own login address is credentialed, so activation refuses it (boundary 2) and they need a second mailbox. `speaker_portal_invitation.issued_by_user_id` and the channel's consent `actor_user_id` record who did it. The capability stays off until C5's rows clear. | Accepted for the pilot. Detection query in `vm-deploy.md`: invitations whose `issued_by_user_id` also recorded the channel's consent. The privacy owner (parent §10 row 2) decides whether the issuer must differ from the consent recorder. |
| API and worker hold different secrets | Medium / Low | The worker refuses with `speaker_portal_token_mismatch` (§6.2 #10) instead of mailing a dead link; startup checks both processes. | An operator reads the job failure; `vm-deploy.md` says to set both together. |
| Shared activation rate bucket behind the Vite hop (§3.2) | Medium / Low (availability only) | Its own `caller_key` prefix, off login's counter. | Edge per-client rule: follow-up card. |
| Tokens in logs | Low / High | Access-log redaction (§4.5), `hide_parameters=True` (`vm-deploy.md:1005`), no application log of the token. | Cloudflare edge logs are outside the repo. |
| Fixture provider delivers nothing (boundary 5) | Certain / Low | Documented in the UI (no delivery claim), `vm-deploy.md` and this plan. `FixtureEmailProvider.sent` holds the rendered link in worker memory only, never persisted or logged. | Live provider (OQ-002) and reviewed copy, outside this track. |
| Downgrade after activations | Low / High | The R7 guard raises before any DDL. | — |

## 12. Out of scope

- **`/i/` token exposure: separate card (owner ruling), not fixed here.** Evidence:
  - `cba_invitations.py:860` mints `secrets.token_urlsafe(32)`.
  - `:862-880` renders `_response_url(token)` (`:516-522`, `…/i/{token}`) into the `cba.speaker_invitation.v1` draft body.
  - `:910-929` stores that body in `outreach_draft`.
  - `routers/outreach.py:505` (`list_drafts`) returns `DraftResponse.body` (`:219`) to any `{admin, coordinator}` in the unit.
  - The repository filters by unit only (`persistence/outreach.py:349-380`).
  - Effect: a same-unit Connector can read the link and answer as the Speaker.
  - **Added by Revision 3:** the generic compose route also accepts `cba.speaker_invitation.v1` with a caller-chosen `response_url` (`routers/outreach.py:437-450`, `outreach.py:321-330` says it must be server-composed, and nothing enforces that). The same card should add it to `SYSTEM_ONLY_TEMPLATES`.
- An edge per-client rate limit for `/s`, `/i` and `/v1/auth/login` (§3.2).
- Existing-login mode, `find_or_add_role`, credential `FOR UPDATE`, the other-tenant invite pre-check, and unbind (T6b-5), plus the two-membership matrix shape.
- `/v1/me/*` Speaker routes (T6b-2).
- Opt-in/out and every `lifted_at` reader (T6b-3).
- The portal shell and switcher (T6b-4/5).
- Delivery status on the invitation row.
- The e2e click-through (parent §7 row 13).
- Retention of expired invitations (D5).
- A second secret for key rollover (rotation is kill-and-reinvite, §4.3).
- Live email delivery and review of the template copy (boundary 5).

## Appendix A — `suppression_record` readers T6b-3 must change

1. `python/smartmatch_persistence/smartmatch_persistence/contacts.py:124-157` `_selectable()` → `suppressed` for `get`/`list_for_unit`/`list_for_professional`. It feeds `cba_contact_channels` `send_eligible`, `choose_invitation_channel`, `outreach_contacts`, and T6b-1's invite check.
2. `python/smartmatch_persistence/smartmatch_persistence/outreach.py:217-283` `load_recipient` (join `:239-258`) → the worker delivery gate (`worker/outreach.py:303`), dispatch (`cba_invitations.py:1092`), and drafts/sends (`routers/outreach.py:415, :566, :625`).
3. `outreach.py:730-740` `is_suppressed` → `cba_contact_channels.py:570`.
4. `outreach.py:683-728` `suppress`: `ON CONFLICT (uq_suppression_record_address) DO NOTHING` would swallow a re-suppression of a lifted row. It must re-open the row (`lifted_at = NULL`, new `suppressed_at`, `source`). Writers: `routers/outreach.py:861`, `routers/outreach_contacts.py:694`.
5. `uq_suppression_record_address` (`schema.py:2096`) keeps one row per address, so a lift followed by a re-suppress overwrites history. T6b-3 decides whether that is acceptable.

**Next action (under two minutes):** confirm with the owner whether `cba.speaker_invitation.v1` joins `SYSTEM_ONLY_TEMPLATES` on the `/i/` card (§12).
