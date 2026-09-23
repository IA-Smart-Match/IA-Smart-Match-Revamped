# B26 T6b-1 — Speaker accounts (`0039_speaker_portal`, invite / revoke / activate, `/s/{token}`)

**Next action:** get rulings on C1–C5 (§9), then write `tests/unit/test_speaker_portal_composition.py` and the §7 files and commit them red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1, §2, §3 intro, §3.2, §4.2, §4.5 (boundary), §6 invite row, §7 row 6, §8, §10, §11.
Branch `feat/b26-t6b-1`. Implementation branches from `main` **after T2 merges** (`0038_speaker_availability` is on `feat/b26-t2`, not merged) and after T6a merges (`_TOKEN_PAGE_HEADERS`, the `/i/` form parser, the Vite `^/i/` proxy and `viteProxy.test.tsx` are T6a's).

## 0. Boundaries (stated, not implied)

1. **New-login mode only.** Activation sets a password on the contact's own `user_account` (`account_user_id = professional_id`). Existing-login mode, `find_or_add_role`, credential `FOR UPDATE` locking, the other-tenant invite pre-check (`409 speaker_portal_address_in_other_tenant`) and unbind are **T6b-5**.
2. **No second credentialed account, ever.** If any credentialed account (any tenant — `load_by_email` is global, `pilot_auth.py:103-159`) other than the contact account holds the channel address, activation refuses with the generic `400 speaker_portal_invitation_invalid` and writes nothing. T6b-5 turns the one-account-in-this-tenant case into existing-login mode.
3. **`lifted_at` is schema only.** `0039` adds `suppression_record.lifted_at/lifted_by_user_id`; no T6b-1 code sets them, so every send-eligibility read is unchanged. Readers T6b-3 must change: Appendix A.
4. **`SPEAKER_PORTAL` is off** in all three scopes. No seed, env var or compose file turns it on. Turning it on needs T6b-5 merged and §10 rows 1, 2, 4 cleared (C5).
5. No `/v1/me/*` Speaker routes (T6b-2), no consent routes (T6b-3), no portal shell (T6b-4).

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0039_speaker_portal.py` | **New.** `revision = "0039_speaker_portal"`, `down_revision = "0038_speaker_availability"`. Hand-written (ADR-0004), no transaction code (ADR-0009). §2. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | Mirror: new table after `speaker_profile` (`:2124`); two columns + FK + CHECK on `speaker_profile` (`:2124-2340`); two columns + FK + CHECKs on `suppression_record` (`:2076-2104`), source CHECK widened (`:2097-2101`); `__all__` (`:41`). Partial unique indexes mirrored as `sa.Index(..., unique=True, postgresql_where=...)`. |
| `python/smartmatch_domain/smartmatch_domain/product_scope.py` | `Capability.SPEAKER_PORTAL = "speaker_portal"` after `:230`; `False` in CBA (`:247-267`), IA_WEST_LEGACY (`:270-295`), CLASS_EXERCISE (`:315-330`); import-time assert: on ⇒ `AUTHENTICATED_LOGIN`, `CONSENTED_OUTREACH`, `SPEAKER_CONTACT_MANAGEMENT` on. |
| `apps/web/legacy-frontend/src/lib/productScope.ts` | `speaker_portal: false,` after `:96` (parity test `test_cba_scope_policy.py:259`). |
| `python/smartmatch_domain/smartmatch_domain/speaker_portal.py` | **New.** `INVITATION_TTL = timedelta(days=7)`, token derive/hash (§4), `check_new_password` (§5), `PortalAccessStatus` (`none/invited/expired/active`) + `derive_status(...)`, `ACTIVATION_URL_SENTINEL`. |
| `python/smartmatch_domain/smartmatch_domain/outreach.py` | Template `cba.speaker_portal_invite.v1` in `TEMPLATES` (`:341-417`), placeholders `{professional_name, unit_name, expires_on, activation_url}` — `activation_url` is always `ACTIVATION_URL_SENTINEL` (C1). |
| `python/smartmatch_domain/smartmatch_domain/pilot_credentials.py` | Re-export nothing new; `check_new_password` reuses `MINIMUM_PASSWORD_LENGTH` (`:114`). |
| `python/smartmatch_domain/smartmatch_domain/role_presentation.py` | `"speaker"` row in `_PRESENTATION` (`:145-189`): persona `SPEAKER`, label "Speaker", portal "Speaker Portal"; fix `Persona.SPEAKER` doc (`:119-122`). |
| `apps/web/legacy-frontend/src/lib/roleLabels.ts` | Mirror row (checked by `test_role_presentation.py:158`). |
| `services/api/smartmatch_api/routers/portals.py` | `_PORTAL_FOR_ROLE["speaker"] = ("speaker", "/speaker-portal")` (`:280`); `_ROLE_PRIORITY` (`:301`) and `_PORTAL_ORDER` (`:308`) insert `speaker` after `volunteer`; `INVITATION_ONLY_ROLES = frozenset({"speaker"})` (C3). |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_portal.py` | **New.** `SpeakerPortalRepository` (never commits): `revoke_live`, `insert_invitation`, `current_for_profile`, `lock_by_token_hash` (`FOR UPDATE`), `binding_for_profile`, `other_credentialed_account_exists(email, excluding_user_id)`, `bind_new_login(...)` (email update, membership insert, profile bind, invitation accept). |
| `services/api/smartmatch_api/speaker_portal_activation.py` | **New.** `activate_new_login(session, *, token, new_password, now) -> IssuedSession`; shared by the JSON and form routes (§5). |
| `services/api/smartmatch_api/routers/speaker_portal.py` | **New.** `router` (Connector: invite, revoke, access), `public_router` (`/v1/speaker-portal/activate`), `pages_router` (`GET`/`POST /s/{token}`). Bare module-level `APIRouter(...)` assignments (`test_policy_matrix.py:8924`). |
| `services/api/smartmatch_api/main.py` | Three rows in `CAPABILITY_SCOPED_ROUTERS` (`:338-659`) under `Capability.SPEAKER_PORTAL`. Nothing else: `routers_for` (`:661-684`) already drops them. |
| `services/api/smartmatch_api/config.py` | `speaker_portal_token_secret: SecretStr | None = None` (`SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET`); `require_speaker_portal_token_secret(settings)` called at import in `main.py` only when the capability is on (pattern: `:239`, `main.py:699-700`). |
| `services/worker/smartmatch_worker/outreach.py` | `OutreachSendCommand` (`:127-166`) gains optional `speaker_portal_invitation_id`; handler (`:271-400`) replaces the sentinel in `body_text` only, at send, for `cba.speaker_portal_invite.v1` (C1). `config.py` gains the same secret. |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerPortalInvite.tsx` | **New.** §6. Rendered from `ContactRow` (`CoordinatorSpeakerContacts.tsx:136-230`) only when `isCapabilityEnabled("speaker_portal")`. |
| `apps/web/legacy-frontend/src/lib/api.ts` | `fetchSpeakerPortalAccess`, `inviteSpeakerToPortal`, `revokeSpeakerPortalInvitation` after `fetchSpeakerContactChannels` (`:4042-4053`). |
| `apps/web/legacy-frontend/src/lib/principal.ts` | `PortalKind` (`:83`) gains `"speaker"`. |
| `apps/web/legacy-frontend/vite.config.ts` | `"^/s/"` in `server.proxy` and `preview.proxy` (`:54-85`), T6a's pattern; touch only those blocks. |
| `apps/web/legacy-frontend/src/app/routes.tsx` | `/speaker-portal` placeholder route (L4 / L6 option a), one page `SpeakerPortalPlaceholder.tsx`. |
| Tests | §7. Plus: `tests/integration/test_check_constraints.py` (`:76`, `:766`: 9 new keys, `ck_suppression_record_source` text `:193`); `tests/integration/conftest.py` `_TENANT_SCOPED_TABLES` insert `"speaker_portal_invitation"` after `"cba_invitation_batch"` (`:121`); head pins `0038_speaker_availability` → `0039_speaker_portal` in the 4 files T2 edits (`test_cba_contact_schema.py:150`, `test_cba_weight_settings_persistence.py:189`, `test_event_filed_by_migration.py:78`, `test_host_organization_migration.py:84`). |
| Docs | `README.md:35-36` (39 revisions, head `0039_speaker_portal`); `docs/operations/supabase-setup.md:162`; `docs/operations/exercise-hosting.md` step-2 head lines only (T2's C6 rule); `apps/web/DESIGN.md:38-52, :150-152, :372-374`; `docs/decisions/pilot-login-decision-2026-09-04.md:68-70` amendment (L3); `docs/product/cba-capability-policy.md` new row; `pilot_auth.py:171-175` docstring. |

## 2. DDL — `0039_speaker_portal`

**`speaker_portal_invitation`**: `id uuid` PK `speaker_portal_invitation_pkey`; `tenant_id`, `professional_id`, `contact_channel_id`, `issued_by_user_id uuid NOT NULL`; `token_hash bytea NOT NULL`; `issued_at timestamptz NOT NULL DEFAULT now()`; `expires_at timestamptz NOT NULL`; `accepted_at`, `revoked_at timestamptz NULL`; `bound_account_user_id uuid NULL`; `binding_mode text NULL`.

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

**`speaker_profile`** adds `account_user_id uuid NULL`, `account_bound_at timestamptz NULL`;
`fk_speaker_profile_account (tenant_id, account_user_id) → user_account (tenant_id, id) RESTRICT`;
`ck_speaker_profile_account_bound`: `(account_user_id IS NULL) = (account_bound_at IS NULL)`;
`uq_speaker_profile_account`: `CREATE UNIQUE INDEX … (tenant_id, account_user_id) WHERE account_user_id IS NOT NULL`.

**`suppression_record`** adds `lifted_at timestamptz NULL`, `lifted_by_user_id uuid NULL`;
`fk_suppression_record_lifted_by (tenant_id, lifted_by_user_id) → user_account (tenant_id, id) RESTRICT`;
`ck_suppression_record_lifted`: `(lifted_at IS NULL) = (lifted_by_user_id IS NULL) AND (lifted_at IS NULL OR lifted_at >= suppressed_at)`;
drop and recreate `ck_suppression_record_source`: `source IN ('unsubscribe_link','one_click','coordinator','bounce','complaint','speaker_portal')`.

**Downgrade** (reverse order): drop `ck_suppression_record_lifted`, `fk_suppression_record_lifted_by`, both columns; recreate the 5-value source CHECK (fails loudly if a `speaker_portal` row exists — T6b-1 writes none); drop `uq_speaker_profile_account`, `ck_speaker_profile_account_bound`, `fk_speaker_profile_account`, both columns; drop `speaker_portal_invitation`. No `membership.role` CHECK exists (`schema.py:166-188`), so `speaker` needs no DDL.

## 3. Routes

Connector routes: `router = APIRouter(prefix="/v1/units", tags=["speaker-portal"])`. Authorizer `_authorize_speaker_portal` = `load_unit_or_404` (`units.py:44`) + `assert_allowed(..., required_roles=_SPEAKER_PORTAL_ROLES)`, `_SPEAKER_PORTAL_ROLES = frozenset({"admin", "coordinator"})` (shape of `cba_contacts.py:624-663`). Profile lookup `SpeakerContactRepository.get` (`persistence/cba_contacts.py:561`) scoped by unit; miss → `404 speaker_contact_not_found`. Quota first (`charge_quota`, `dependencies.py:286`).

| Route | Auth / roles | Request | Success | Errors |
|---|---|---|---|---|
| `POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/portal-invitations` | principal; `{admin, coordinator}` | `{ "contact_channel_id": uuid }`, `extra="forbid"` | `202 { invitation_id, status: "invited", expires_at, job_id, events_url, replayed }` | `404 speaker_contact_not_found`; `409 speaker_portal_already_active` (profile bound); `422 speaker_portal_channel_not_eligible` (unknown id, other professional/unit, not email, or `is_send_eligible` false — `consent.py:261`); `403`; `429 rate_limited` |
| `DELETE …/portal-invitations/current` | same | — | `200 { "revoked": bool }` (false = nothing live; idempotent, `logout`'s shape) | `404 speaker_contact_not_found`; `429` |
| `GET …/portal-access` | same | — | `200 { status, contact_channel_id?, issued_at?, expires_at?, bound_at? }`; `status ∈ none, invited, expired, active` (L4) | `404`; `429` |
| `POST /v1/speaker-portal/activate` | **none** (`UNAUTHENTICATED_ROUTES`) | `{ "token": str 16–128, "new_password": str 1–1024 }`, `extra="forbid"` | `200 { access_token, token_type: "bearer", expires_at }` (`LoginResponse` shape, `auth.py:169-187`) | `400 speaker_portal_invitation_invalid` (unknown, expired, accepted, revoked, profile already bound, address held by another credentialed account — one code, one message); `422 password_too_weak` (checked **before** the token, so it is no oracle); `422` validation; `429 rate_limited` |
| `GET /s/{token}` | none | — | `200 text/html`: password + confirm form, `method="post"`, no `action`, token never in HTML; T6a's `_TOKEN_PAGE_HEADERS` | — (identical bytes for every token) |
| `POST /s/{token}` | none | form-urlencoded `new_password`, `confirm_password`, hand-parsed with T6a's parser and 1024-byte cap | `200 text/html` "Your Speaker account is ready" + link to `/login`; **no session** (C4) | `400` html (same bytes as any invalid token); `422` html (weak / mismatch); `413`; `429` |

Invite steps, in order: quota → authorize → profile (404) → `binding_for_profile` (409) → channel via `ContactChannelRepository.get` (`contacts.py:254`) and match `professional_id` + `owning_unit_id` + `channel_kind == 'email'` + `is_send_eligible` (422) → `revoke_live` → mint `invitation_id`, derive token, `insert_invitation` (`expires_at = now + 7d`) → `compose_draft` (template §1) → `create_draft(status=APPROVED, approved_by=principal)` (precedent `cba_invitations.py:910-929`) → `submit_command(OUTREACH_SEND_COMMAND_TYPE, owning_unit_id=unit.id, payload={"draft_id", "speaker_portal_invitation_id"}, idempotency_key=f"speaker-portal-invitation:{invitation_id}")` (`commands.py:87`), which commits revoke + insert + draft + job as one transaction. No invite-time "email in use" check (L1).

Rate limits: `speaker_portal.invite` 20/min, `speaker_portal.read` 120/min (per principal); activation uses `LoginAttemptLimiter` (`pilot_auth.py:305`) with `RateLimit("speaker_portal.activate", 10, 5 min)` and `caller_key = "speaker_portal.activate:" + client host` — the table keys on `caller_key` only (`schema.py:1696-1708`), so an unprefixed key would share `/v1/auth/login`'s counter. Charged and committed first (`auth.py:226-261`).

**Authz rows.** `test_route_roles.py`: three literal rows `_SPEAKER_PORTAL = frozenset({"admin", "coordinator"})`, extend the exact-set test (`:201-212`), add `test_speaker_portal_roles_matches_the_live_constant`. `test_policy_matrix.py`: three `Operation`s (`speaker_portal.invite`, `.revoke`, `.read`) with full `MATRIX` rectangles copied from the speaker-contact rows; `UNAUTHENTICATED_ROUTES` (`:384`) gains `GET /s/{token}`, `POST /s/{token}`, `POST /v1/speaker-portal/activate` with reasons. The ledger is AST-derived (`:360`), so rows are required even while unmounted.

## 4. Token handling

1. 256 bits: `token = base64url(HMAC-SHA256(secret, "speaker-portal:" + invitation_id))` — 32-byte digest, 43 chars. Pattern: `unsubscribe_token` (`worker/outreach.py:185-202`).
2. Stored: `token_hash = sha256(token.encode())` → `bytea(32)`, `uq_…_token_hash`. The token itself is stored nowhere — not in `outreach_draft.body` (the draft carries `ACTIVATION_URL_SENTINEL`), not in the job payload (only the invitation id).
3. Rendered once, by the worker, into `SendRequest.body_text` (`worker/outreach.py:373-387`): `{outreach_public_base_url}/s/{token}`. A re-drive derives the same token.
4. Expiry: `expires_at = issued_at + 7 days`, checked in SQL (`expires_at > now`) inside the locked read; the CHECK caps it at 7 days.
5. Never echoed: not in `/s` HTML, not in any response body or header, not logged; `Cache-Control: no-store`, `Referrer-Policy: no-referrer` (T6a headers).
6. One-time: `accepted_at` set in the activation transaction; a new invite or `DELETE …/current` sets `revoked_at`.
7. Secret: `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET` in API and worker. Required at API import only when the capability is on; worker raises `PolicyFailure("speaker_portal_secret_missing")` when it meets this template without one (no synthetic fallback — a forgeable activation link is an account takeover).

## 5. Activation transaction (`activate_new_login`)

1. Charge `LoginAttemptLimiter`, commit (ADR-0015).
2. `check_new_password(new_password)`: length ≥ `MINIMUM_PASSWORD_LENGTH` (12) and ≤ 1024, not all whitespace → else `422 password_too_weak`. Pure, before any token read.
3. `lock_by_token_hash`: `SELECT … FROM speaker_portal_invitation JOIN speaker_profile JOIN contact_channel JOIN org_unit WHERE token_hash = :h FOR UPDATE OF speaker_portal_invitation` → none, `accepted_at`/`revoked_at` set, `expires_at <= now`, or `speaker_profile.account_user_id IS NOT NULL` → `400`.
4. `SELECT pg_advisory_xact_lock(hashtextextended('speaker-portal-email:' || lower(:address), 0))` — serializes two new-login activations for one address (the only lock new-login needs; row locks on existing credentials are T6b-5).
5. `other_credentialed_account_exists(address, excluding_user_id=professional_id)` → `400` (boundary 2). Also `400` if the contact account is suspended.
6. `UPDATE user_account SET email = :address, version = version + 1 WHERE tenant_id, id = professional_id`. `ensure_account` is `ON CONFLICT DO NOTHING` (`professionals.py:115-126`), so a later contact edit cannot reset it.
7. `PilotCredentialRepository.upsert(user_id=professional_id, password=derive_password_hash(pw, salt=new_salt()))` (`pilot_auth.py:161`).
8. `INSERT membership (id, tenant_id, user_id=professional_id, granted_path=org_unit.path of the profile's owning unit, role='speaker', valid_from=now)`.
9. `UPDATE speaker_profile SET account_user_id = professional_id, account_bound_at = now WHERE … AND account_user_id IS NULL` — 0 rows → rollback, `400`.
10. `UPDATE speaker_portal_invitation SET accepted_at = now, bound_account_user_id = professional_id, binding_mode = 'new_login' WHERE id AND accepted_at IS NULL AND revoked_at IS NULL`.
11. JSON route: `PilotSessionRepository.issue` (`SESSION_TTL`, `pilot_credentials.py:108`). Form route: skip.
12. One `commit`. Any exception → `get_session` rollback; nothing from steps 6–11 persists.

## 6. Frontend contract — "Invite to portal"

- Gate: `isCapabilityEnabled("speaker_portal")`; false in the build, so the component never mounts. Vitest mocks `lib/productScope` to cover the on-states.
- Reads: `useScopedQuery({ resource: "speaker-portal-access", params: [unitId, professionalId] })`; channels through the existing `fetchSpeakerContactChannels` only when the panel opens. Eligible = `send_eligible && channel_kind === "email"`.
- States: loading; `none` → "Invite to portal" (disabled, reason shown, when no eligible channel: "No email address this Speaker agreed to receive"); `invited` → "Invited · link expires {date}", "Send a new link", "Revoke"; `expired` → "Link expired", "Invite again"; `active` → "Portal active since {date}", no revoke (unbind is T6b-5); error by `ApiRequestError.code`.
- Writes: `useMutation`, submit disabled while pending, no optimistic state, invalidate only `["speaker-portal-access", unitId, professionalId]`. `409 speaker_portal_already_active` → refetch + "This Speaker already has portal access"; `422 speaker_portal_channel_not_eligible` → "That address can no longer be emailed". Revoke asks for confirmation.
- A11y: channel choice is a `<fieldset>` + `<legend>Send the link to</legend>` of radios named by address; one `role="status"` region; errors `role="alert"` + `aria-describedby`; buttons ≥ 44px (`min-h-11`).

## 7. Tests (TDD — all committed red in milestone 1)

Local: one file at a time; CI runs `pytest tests/ -m "not e2e"` with Postgres and `vitest run`.

| File | Level | Tests |
|---|---|---|
| `tests/unit/test_speaker_portal_domain.py` | unit | `test_token_is_256_bits_urlsafe`, `test_token_is_stable_per_invitation_and_secret`, `test_token_hash_is_32_byte_sha256`, `test_invitation_ttl_is_seven_days`, `test_password_policy_rejects_short_blank_and_overlong`, `test_password_policy_accepts_twelve_chars`, `test_status_none_invited_expired_active` |
| `tests/unit/test_speaker_portal_template.py` | unit | `test_invite_template_is_in_the_closed_registry`, `test_composed_body_carries_the_sentinel_not_a_token` |
| `tests/unit/test_outreach_send_speaker_portal.py` | unit (worker, fakes) | `test_worker_renders_the_activation_link_at_send_only`, `test_draft_body_is_unchanged_after_send`, `test_missing_secret_is_a_terminal_policy_failure`, `test_other_templates_are_untouched` |
| `tests/unit/test_speaker_portal_composition.py` | unit | `test_speaker_portal_is_off_in_every_scope`, `test_routes_unmounted_when_off` (`routers_for(Settings())` and `smartmatch_api.main.app.routes` hold none of the 6 paths), `test_openapi_document_has_no_speaker_portal_paths` (`contracts/openapi/smartmatch.json`), `test_routes_mount_when_on` (settings stub overriding `capability_enabled`), `test_capability_requires_login_outreach_and_contacts` |
| `tests/unit/test_role_presentation.py`, `test_compose_dev_principals.py`, `test_cba_scope_policy.py` | unit | `STORED_ROLES` gains `speaker` (`:52`); `:104-113` becomes `test_the_speaker_role_presents_as_the_speaker_persona`; `:93-110` exempts `INVITATION_ONLY_ROLES`; `SPEAKER_PORTAL` listed as staged-off, not in `DISABLED_UNDER_CBA` (`:79`) |
| `tests/authz/test_route_roles.py`, `tests/authz/test_policy_matrix.py` | authz | §3 rows; `test_every_route_is_either_authenticated_or_declared_public` covers the 3 public routes |
| `tests/contract/test_portals_api.py` | contract (DB) | `test_speaker_membership_lists_the_speaker_portal`, `test_host_default_portal_stays_volunteer_with_speaker_role` |
| `tests/contract/test_speaker_portal_api.py` (app built with the stub settings; `integration` mark) | contract (DB) | `test_invite_returns_202_and_one_live_invitation`, `test_invite_draft_body_holds_no_token`, `test_invite_refuses_ineligible_channel` (param: suppressed, not `active_candidate`, other professional, other unit, unknown), `test_invite_other_unit_profile_is_404`, `test_invite_bound_profile_is_409`, `test_second_invite_revokes_the_first`, `test_revoke_is_idempotent`, `test_access_status_transitions`, `test_activate_new_login_binds_and_issues_session`, `test_activated_speaker_sees_speaker_membership_in_me`, `test_activate_refuses_every_bad_token_identically` (param: unknown, expired, accepted, revoked — same status and bytes), `test_weak_password_is_422_for_any_token`, `test_activate_refuses_address_held_by_a_credentialed_account` (nothing written: email, credential, membership, invitation unchanged), `test_activate_never_echoes_the_token`, `test_activation_is_rate_limited_separately_from_login`, `test_s_page_is_identical_for_every_token`, `test_s_form_activates_without_issuing_a_session` |
| `tests/integration/test_speaker_portal_migration.py` | integration | every §2 CHECK (accept + refuse), each composite FK refuses a cross-tenant row, `test_one_live_invitation_per_profile`, `test_one_profile_per_account`, `test_source_admits_speaker_portal`, `test_downgrade_then_upgrade_round_trips` |
| `tests/integration/test_speaker_portal_activation.py` | integration | `test_activation_is_atomic` (fail step 8 → nothing from steps 6–10 persists), `test_concurrent_activation_of_one_token_binds_once`, `test_concurrent_new_login_for_one_address_creates_one_credential` |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerPortalInvite.test.tsx` | Vitest | `renders nothing when the capability is off`, `disables invite with a reason when no channel is eligible`, `sends the chosen channel id and shows Invited from the response`, `maps 409 and 422 codes to their messages`, `revoke asks first and invalidates only the access key`, `active state offers no revoke` |
| `apps/web/legacy-frontend/src/viteProxy.test.tsx` (T6a's) | Vitest | `/s/abc` matches in both proxies; `/speaker-portal`, `/settings`, `/s` do not |

## 8. Commit milestones

1. `test: T6b-1 failing tests` — every §7 file red; ledgers updated.
2. `feat: 0039_speaker_portal migration and schema mirror` — migration, mirror, check-constraint table, conftest order, head pins, README / ops head lines.
3. `feat: speaker portal domain and repository` — `speaker_portal.py` (domain + persistence), capability, role presentation, portal mapping, `productScope.ts`, `roleLabels.ts`.
4. `feat: speaker portal invite, revoke, access and activation routes` — routers, activation service, `main.py` rows, config secret.
5. `feat: speaker_portal_invite template and late-bound activation link` — template + worker.
6. `feat: Invite to portal button and speaker portal placeholder` — frontend, `api.ts`, `principal.ts`, Vite proxy.
7. `docs: speaker role in DESIGN.md and pilot-login amendment` — §1 docs rows.

## 9. Contradictions

**Must decide**

| # | Conflict | Options | Recommend |
|---|---|---|---|
| C1 | §4.2 sends via `outreach.send`, which sends `draft.body` verbatim (`worker/outreach.py:373-376`); the `/i/` precedent renders its token into the body (`cba_invitations.py:860-880`). `GET /v1/units/{unit_id}/outreach/drafts` returns `body` to every Connector in the unit (`routers/outreach.py:205-221`, `:505`). A token in the body lets a Connector set the Speaker's password. | (a) random token in body (precedent); (b) HMAC-derived token, sentinel in body, worker renders at send (§4); (c) random token in body, hide this template from draft reads | **(b).** (a) is an account takeover; (c) still leaves it in the DB and in any future draft read. |
| C2 | "Off by default" has no mechanism: capabilities are per-scope constants (`product_scope.py:244-338`), and the module forbids deployment knobs deciding product scope (`:17-20`). | (a) `False` in all 3 scopes; enabling is a reviewed code change; tests mount via a settings stub; (b) new env flag | **(a).** |
| C3 | Adding `speaker` to `_PORTAL_FOR_ROLE` fails `test_compose_dev_principals.py:106` (one compose principal per portal role). | (a) `INVITATION_ONLY_ROLES` exemption; (b) seed a compose Speaker — contradicts §2 non-goal 3 | **(a).** |
| C4 | §4.2 "issue a session" at activation; the `/s` form runs under T6a's `default-src 'none'` CSP with no JS, and the SPA holds a bearer token in `localStorage`. | (a) JSON route issues a session; form route activates and links to `/login`; (b) inline script with a CSP hash | **(a).** |
| C5 | Before T6b-5, a Host whose email matches gets a link that always fails (boundary 2). | Enabling `SPEAKER_PORTAL` requires T6b-5 merged + §10 rows 1, 2, 4 | Confirm as the enable gate. |

**Later (resolved here, recorded)**

1. L1 — §7 row 6 "email-in-use 409" vs the owner's Email-clash ruling (no `409 speaker_portal_email_in_use`): owner ruling wins; generic `400` at activation.
2. L2 — §3.2 "every send-eligibility read changes in the same PR" vs the dispatcher: T6b-3 owns it (Appendix A).
3. L3 — `pilot-login-decision-2026-09-04.md:68-70` and `pilot_auth.py:171-175` say no endpoint sets a password or grants a role; Q2 = B supersedes; amend both in milestone 7.
4. L4 — §6 needs Invited / Active / Expired, §4.2 has no read route: add `GET …/portal-access`. L6: `/speaker-portal` has no page until T6b-4 — L6 option (a) one-screen placeholder, (b) NotFound behind an off flag; recommend (a).
5. L5 — existing, outside T6b-1: `/i/` tokens sit in `cba.speaker_invitation.v1` draft bodies that same-unit Connectors can list, so a Connector can answer as the Speaker. Raise a card for T6a / T6b-2.

## 10. Out of scope

Existing-login mode, `find_or_add_role`, credential `FOR UPDATE`, other-tenant invite pre-check, unbind (T6b-5); `/v1/me/*` Speaker routes (T6b-2); opt-in/out and every `lifted_at` reader (T6b-3); portal shell and switcher (T6b-4/5); delivery status on the invitation row; e2e click-through (§7 row 13); retention of expired invitations (D5).

## Appendix A — `suppression_record` readers T6b-3 must change

1. `python/smartmatch_persistence/smartmatch_persistence/contacts.py:124-157` `_selectable()` → `suppressed` for `get`/`list_for_unit`/`list_for_professional` (feeds `cba_contact_channels` `send_eligible`, `choose_invitation_channel`, `outreach_contacts`, and T6b-1's invite check).
2. `python/smartmatch_persistence/smartmatch_persistence/outreach.py:217-283` `load_recipient` (join `:239-258`) → worker delivery gate (`worker/outreach.py:303`), dispatch (`cba_invitations.py:1092`), drafts/sends (`routers/outreach.py:415, :566, :625`).
3. `outreach.py:730-740` `is_suppressed` → `cba_contact_channels.py:570`.
4. `outreach.py:683-728` `suppress`: `ON CONFLICT (uq_suppression_record_address) DO NOTHING` would swallow a re-suppression of a lifted row — must re-open it (`lifted_at = NULL`, new `suppressed_at`, `source`). Writers: `routers/outreach.py:861`, `routers/outreach_contacts.py:694`.
5. `uq_suppression_record_address` (`schema.py:2096`) keeps one row per address, so a lift-then-re-suppress overwrites history; T6b-3 decides whether that is acceptable.

**Next action (under two minutes):** answer C1 with (b) or pick another option in the dispatcher thread.
