# B26 T6b-5 — one login, two roles (existing-login activation, `find_or_add_role`, unbind, portal switcher)

**Next action:** wait for the §0 start gate, then run milestone 0 (`git merge origin/feat/b26-t6b-2`).

**Revision 1, 2026-09-23.** Planning only. No source file, route or migration is written by this document.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §4.5 (the design; followed), §4.2 item 3, §6 switcher row, §7 row 8b, §8, §11 risks 2 and 2b.
Inputs: T6b-1 plan `origin/feat/b26-t6b-1` @ `3e9a7ef4` (rev 3 + round-2 gate fixes); T6b-2 plan `origin/feat/b26-t6b-2` @ `8805cdc3` (rev 2); T6b-3 plan `origin/feat/b26-t6b-3` (operation keys only). T6b-4 had not pushed a plan when this was written; §6.3 names the slots it must keep.
Line numbers are `main` @ `1909278f` unless a track is named. T6b-1/T6b-2 code is named by symbol, because it is not written yet.

## 0. Branch, stack, start gate, merge order

**Two halves, one branch (`feat/b26-t6b-5`).**

| Half | Milestones | Stacks on | Can start when |
|---|---|---|---|
| Backend: `find_or_add_role`, seed tool, existing-login mode, locks, invite pre-check, unbind, authz | 0–10 | `origin/feat/b26-t6b-2` (which merges T8a → T6b-1 → T2 → T1, and T3) | T6b-2's implementation is pushed (its milestone 4 green) |
| Switcher UI | 11–13 | the backend half + `origin/feat/b26-t6b-4` | T6b-4's `SpeakerPortalLayout.tsx` is pushed |
| Docs | 14 | — | after 13 |

1. Milestone 0: `git merge origin/feat/b26-t6b-2`. A merge, not a rebase, so the pushed plan commit stays (T3 and T6b-2's pattern). `contracts/openapi/smartmatch.json` is never hand-merged: take either side, then `make openapi VENV=$VENV`.
2. If `origin/feat/b26-t6b-3` is pushed with code by then, merge it too (its 3 `me.contact_channels.*` operations join the §5 permit set). If not, §5 names what to add when it lands.
3. Milestone 11: `git merge origin/feat/b26-t6b-4` (or `main`, if T6b-4 has merged).

**Merge order into `main`:** #210 (T1) → #212 (T2) → T6b-1 → T8a → T3 → T6b-2 → T6b-3 → T6b-4 → **T6b-5**. PR body line 1: **"Merge the T6b-2 and T6b-4 PRs (and their stacks) first."** After they land, merge `main` into `feat/b26-t6b-5` so the diff is T6b-5 only.

**Split rule.** If milestone 10 is green and T6b-4 has not pushed its shell, open PR A (backend, milestones 0–10) at once and carry milestones 11–13 on `feat/b26-t6b-5-switcher` as PR B. The `SPEAKER_PORTAL` turn-on rule (T6b-1 §0 item 4, C5) needs **both** merged.

**Migration head.** No new migration if Q2 (§11) is folded into `0039`. Otherwise `0041_speaker_portal_unbind` (or current head + 1), and every head pin moves in the same commit.

## 1. Rules this plan implements (decided; restated so tests can cite them)

| # | Rule | Source |
|---|---|---|
| R-A | The Speaker identity stays `speaker_profile.professional_id`. Never re-keyed. | §4.5 item 1 |
| R-B | The login is `speaker_profile.account_user_id`: the contact account (new login) or the Host's existing account (existing login). A merged contact account stays credential-less with its `.invalid` email. | §4.5 item 2 |
| R-C | `load_by_email` does not change (`pilot_auth.py:103-159`): `None` unless exactly one credentialed account holds the address. | §4.5 item 3 |
| R-D | Activation never creates a second credential for an address that has one. It locks the matching `pilot_credential` rows `FOR UPDATE`. | §4.5 item 3 |
| R-E | Ambiguous address → generic `400 speaker_portal_invitation_invalid` at activation. | §4.5 item 4 |
| R-F | Other-tenant holder → generic `400` at activation; `409 speaker_portal_address_in_other_tenant` at invite. | §4.5 item 5 |
| R-G | Every credential-creating path calls one `find_or_add_role(email, role, path)`. `tools/seed_pilot_logins.py` moves onto it. A test fails if any module outside it inserts `pilot_credential`. | §4.5 item 6, §11 risk 2b |
| R-H | Existing-login mode: `{token, existing_password}`. Wrong password → `401 speaker_portal_credentials_invalid`, counted by `LoginAttemptLimiter`, token not consumed. | §4.2 item 3 |
| R-I | Unbind: `speaker` membership `valid_until = now`, `account_user_id` cleared. The Host role is untouched. | §4.5 Unbinding |
| R-J | `volunteer` before `speaker` in `_PORTAL_ORDER`, so `default_portal` stays the Host portal. | §4.5 switcher |
| R-K | Switcher: a link (no server call); hidden with one portal; keyboard-operable button with `aria-expanded`; `aria-current` on the current portal; last choice in `localStorage` inside try/catch, `default_portal` the fallback. | §4.5, §6 |
| R-L | Suspending the account suspends both roles; the Connector UI says so. | §4.5 |

## 2. Files

| Path | Change |
|---|---|
| `python/smartmatch_persistence/smartmatch_persistence/login_accounts.py` | **New. The only writer of `pilot_credential`** (insert, update, delete). `lock_address`, `holders_for_address`, `find_or_add_role`, `rotate_own_password`, `retire_login`; types `AddressState`, `LoginHolder`, `AddressHolders`, `NewLogin`, `RoleGrant`; errors `AddressAmbiguous`, `AddressInOtherTenant`, `NoLoginForAddress`, `AccountAlreadyCredentialed`. §3. |
| `python/smartmatch_persistence/smartmatch_persistence/pilot_auth.py` | **Remove `PilotCredentialRepository.upsert`** (`:161-206`); the class keeps `load_by_email`, unchanged (R-C). Module docstring gains: "credentials are written only by `login_accounts`". The `upsert` docstring's "no endpoint sets a password" (`:172-175`) goes with it (T6b-1 L3 already amends it). |
| `services/api/smartmatch_api/speaker_portal_activation.py` (T6b-1's) | `activate_new_login` becomes `activate(session, *, token, new_password, existing_password, secret, now, issue_session) -> ActivationResult`. Mode chosen under locks (§4). The new-login writes go through `find_or_add_role(create=NewLogin(...))`. T6b-1's inline advisory lock moves to `login_accounts.lock_address`. |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_portal.py` (T6b-1's) | `other_credentialed_account_exists` is deleted (replaced by `holders_for_address`). New: `lock_bound_profile_invitation` (the accepted invitation that made the binding, `FOR UPDATE`), `login_bound_elsewhere(tenant_id, account_user_id, excluding_professional_id)`, `active_roles(tenant_id, user_id, now)`, `unbind(...)` (§4.4). `bind_new_login` becomes `bind(professional_id, account_user_id, mode, now)`. |
| `services/api/smartmatch_api/routers/speaker_portal.py` (T6b-1's) | `ActivateRequest` gains `existing_password` (exactly one of the two, §4.1). Invite adds the pre-check (§4.3). New `DELETE …/portal-access` (unbind). `GET …/portal-access` gains `login_shared`. `/s/{token}` GET renders the form the mode needs; POST accepts either form (§4.2). |
| `tools/seed_pilot_logins.py` | `seed_role_logins` (`:222-311`) resolves each address through `login_accounts` (§3.4). The `repository.upsert` call (`:293-298`) and the `PilotCredentialRepository` import (`:92`) go. |
| `tools/seed_pilot.py` | `_ensure_membership_set` (`:143-221`) ignores rows whose role is in `INVITATION_ONLY_ROLES`: they are granted by activation, not by a seed. New read-only `verify_membership_set(...)` (the check half, `:181-207`), which `seed_pilot_logins` calls before it adds roles through `find_or_add_role`. `seed_pilot()` itself (the `seed` service's single principal) is unchanged. |
| `services/api/smartmatch_api/routers/portals.py` | No logic change (T6b-1 already inserts `speaker` after `volunteer`, `:301`, `:308`). One import-time assert: `_PORTAL_ORDER.index("volunteer") < _PORTAL_ORDER.index("speaker")`, with the R-J reason. |
| `apps/web/legacy-frontend/src/app/components/PortalSwitcher.tsx` | **New.** §6. |
| `apps/web/legacy-frontend/src/lib/portalChoice.ts` | **New.** `PORTAL_CHOICE_KEY = "smartmatch.portal.lastChoice"`, `readRememberedPortal(granted)`, `rememberPortal(portal)`, `forgetRememberedPortal()`. Every storage access in try/catch (the `workspacePointer.ts:44-76` shape). |
| `apps/web/legacy-frontend/src/app/pages/Home.tsx` | `:81-83`: target = remembered portal if the server granted it, else `default_portal`, else `portals[0]`. Still navigates to `target.home_path`. |
| `apps/web/legacy-frontend/src/app/hooks/useSession.tsx` | `signOut` (`:66`) calls `forgetRememberedPortal()` before `signOutOfSession()`. |
| `apps/web/legacy-frontend/src/app/components/VolunteerPortalLayout.tsx` | Two slots (§6.3). |
| `apps/web/legacy-frontend/src/app/components/SpeakerPortalLayout.tsx` (T6b-4's) | The same two slots (§6.3). |
| `apps/web/legacy-frontend/src/lib/principal.ts` | `PortalKind` (`:83`) already gains `"speaker"` in T6b-1. No change. |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerPortalInvite.tsx` (T6b-1's) | Active state: "Remove portal access" (confirm), the shared-login and suspension sentence (R-L), and the two new 409 messages (§7). |
| `apps/web/legacy-frontend/src/lib/api.ts` | `unbindSpeakerPortal(unitId, professionalId)`; `SpeakerPortalAccess.login_shared: boolean \| null`; the two error codes in the invite error union. |
| `db/migrations/versions/0039_speaker_portal.py` (T6b-1's) **or** new `0041_speaker_portal_unbind.py` | `speaker_portal_invitation.unbound_at`, `unbound_by_user_id` + FK + 3 CHECKs (§4.4). Q2 decides where. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | Mirror of the two columns. |
| Tests | §8. |
| Docs | `apps/web/DESIGN.md` (role table: one login may hold Host + Speaker; switcher), `docs/decisions/pilot-login-decision-2026-09-04.md` (amend: `login_accounts` is the one credential writer), `docs/operations/vm-deploy.md` (suspension suspends both roles; seed-logins on a merged address; unbind), `docs/architecture/GLOSSARY.md` "Speaker" (a login may also be an Event Host's). |

## 3. `login_accounts` — the one credential writer

### 3.1 Contracts

```python
class AddressState(StrEnum):
    NONE = "none"  # no credentialed account holds the address, in any tenant
    ONE_IN_TENANT = "one_in_tenant"
    OTHER_TENANT = "other_tenant"  # exactly one holder, in another tenant
    AMBIGUOUS = "ambiguous"  # two or more holders, in any tenants


@dataclass(frozen=True, slots=True)
class LoginHolder:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    external_subject: str
    suspended: bool
    password: StoredPassword


@dataclass(frozen=True, slots=True)
class AddressHolders:
    state: AddressState
    holder: LoginHolder | None  # set only for ONE_IN_TENANT


@dataclass(frozen=True, slots=True)
class NewLogin:
    """The existing, credential-less account to credential when no login holds the address."""

    user_id: uuid.UUID
    password: StoredPassword


@dataclass(frozen=True, slots=True)
class RoleGrant:
    user_id: uuid.UUID
    external_subject: str
    login_created: bool
    role_added: bool


def lock_address(session: Session, *, address: str) -> None: ...


def holders_for_address(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    address: str,
    lock: bool,
    also_lock_user_id: uuid.UUID | None = None,
) -> AddressHolders: ...


def find_or_add_role(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    email: str,
    role: str,
    path: str,
    now: datetime,
    create: NewLogin | None = None,
) -> RoleGrant: ...


def rotate_own_password(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    password: StoredPassword,
    now: datetime,
) -> None: ...


def retire_login(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> None: ...
```

None of them commits. Every timestamp is a parameter (T6b-1 R6).

### 3.2 Behaviour

**`lock_address`**: `SELECT pg_advisory_xact_lock(hashtextextended('login-address:' || lower(btrim(:address)), 0))`. It replaces T6b-1 §5 step 8's inline `'speaker-portal-email:'` key; every caller changes in the same commit, and a test pins that nothing else spells a `pg_advisory_xact_lock` over an address. Re-entrant within one transaction (PostgreSQL advisory locks stack), so a caller that already holds it may call `find_or_add_role`.

**`holders_for_address`**: `user_account JOIN pilot_credential ON (tenant_id, user_id)` `WHERE lower(btrim(user_account.email)) = lower(btrim(:address))`, **all tenants** (`load_by_email` is global). With `lock=True`: `OR (pilot_credential.tenant_id = :tenant AND pilot_credential.user_id = :also_lock_user_id)`, `ORDER BY pilot_credential.id FOR UPDATE OF pilot_credential`. The extra row is the contact account's own credential, locked in the same statement so the order is by id and fixed. Classification counts address holders only: 0 → `NONE`; 1 in `tenant_id` → `ONE_IN_TENANT`; 1 elsewhere → `OTHER_TENANT`; ≥ 2 → `AMBIGUOUS` (even when split across tenants).

**`find_or_add_role`**, in order:

1. `lock_address(email)`; `holders_for_address(lock=True)`.
2. `AMBIGUOUS` → `AddressAmbiguous`. `OTHER_TENANT` → `AddressInOtherTenant`.
3. `ONE_IN_TENANT` → target = the holder. `create` must be `None` or name the holder, else `AccountAlreadyCredentialed` (a caller asked to create a login the address already has).
4. `NONE` → `create is None` → `NoLoginForAddress`. Otherwise the `create.user_id` account must exist in `tenant_id`, not be suspended, and hold **no** credential (`AccountAlreadyCredentialed` otherwise: T6b-1's round-2 rule, "a contact account that is already credentialed is never re-passworded"). Then `UPDATE user_account SET email = btrim(:email), version = version + 1`; `INSERT pilot_credential` (plain insert, no `ON CONFLICT`: a conflict here is a bug and should raise).
5. Role: if an **active** membership `(tenant_id, target, role, granted_path = :path::ltree)` exists (`valid_from IS NULL OR valid_from <= :now`, `valid_until IS NULL OR valid_until > :now`) → `role_added=False`. Else `INSERT membership(id, tenant_id, user_id=target, granted_path=:path, role, valid_from=NULL, valid_until=NULL, created_at=:now)`.

`valid_from` is `NULL`, not `now` (a change from T6b-1 §4.6, C4 in §10): `created_at` already records the grant time, the seed's `verify_membership_set` treats a non-null `valid_from` as a foreign grant (`seed_pilot.py:193-199`), and unbind's `valid_until = now` then always satisfies `ck_membership_valid_window` (`schema.py:184-187`).

**`rotate_own_password`**: `UPDATE pilot_credential SET algorithm, iterations, salt, password_hash, updated_at WHERE tenant_id AND user_id`; 0 rows → `NoLoginForAddress`. Only the seed tool calls it, and only for its own subject (§3.4).

**`retire_login`**: `UPDATE pilot_session SET revoked_at = :now WHERE tenant_id, user_id AND revoked_at IS NULL`, then `DELETE FROM pilot_credential WHERE tenant_id, user_id`. Used by unbind for a new-login binding (§4.4).

### 3.3 The single-writer guard (R-G)

`tests/unit/test_login_account_writers.py`, over `python/`, `services/`, `tools/`, `scripts/` and `db/` (not `tests/`, whose fixtures may write rows):

1. `test_only_login_accounts_inserts_pilot_credential`: AST over every `.py`. A `Call` whose callee name (`Name.id` or `Attribute.attr`) is `insert` and whose first argument is an attribute or name `pilot_credential` is a hit; so is any string constant matching `(?i)\binsert\s+into\s+pilot_credential\b`. Allowed file: `smartmatch_persistence/login_accounts.py`. Plus a regex pass over `.sh` and `.sql`.
2. `test_only_login_accounts_updates_or_deletes_pilot_credential`: the same for `update` / `delete` callees and `UPDATE` / `DELETE FROM` text.
3. `test_no_module_calls_a_credential_upsert`: no `.upsert(` on anything named `PilotCredentialRepository` remains, and `PilotCredentialRepository` has no `upsert` attribute.
4. `test_the_guard_catches_each_shape`: runs the detector on 5 planted snippets (`sa.insert(schema.pilot_credential)`, `pg_insert(schema.pilot_credential)`, `insert(pilot_credential)` after `from … import pilot_credential`, an f-string `"INSERT INTO pilot_credential …"`, a `.sh` heredoc) and on 2 clean ones. The shape of `test_the_router_shape_guard_would_actually_catch_each_shape` (`test_policy_matrix.py:8948`).
5. `test_only_login_accounts_takes_an_address_lock`: no other module contains `pg_advisory_xact_lock` together with `email` or `address`.

### 3.4 `tools/seed_pilot_logins.py` on `find_or_add_role`

Per configured entry (subject `S`, address `E`, roles `R = entry.roles`, password `P`), inside the existing `acquire_seed_lock` transaction:

1. Tenant and unit through `seed_pilot`'s `_existing_or_insert_tenant` / `_existing_or_insert_unit` (unchanged).
2. `lock_address(E)`; `holders_for_address(lock=True)`.
3. By state:

| State | Seed does | Outcome line (stdout unless noted) |
|---|---|---|
| `NONE` | `_existing_or_insert_account(S, E)` (unchanged; refuses a changed email), `verify_membership_set(S, R)`, then `find_or_add_role(E, R[0], create=NewLogin(S_id, derive(P)))` and `find_or_add_role(E, r)` for each further role | "login ready for E (roles …)" |
| `ONE_IN_TENANT`, holder is `S` | `verify_membership_set(S, R)` (ignores invitation-only roles); `find_or_add_role(E, r)` for each role; `rotate_own_password(S_id, derive(P))` — rotation stays the seed's right over its **own** subject | "login ready for E (roles …); password rotated" |
| `ONE_IN_TENANT`, holder is not `S` | `find_or_add_role(E, r)` for each role on the holder; **no** password change; no `S` account is created | stderr: "E already signs in as another login; roles … added to it; `<password_var>` was not applied" (Q4) |
| `OTHER_TENANT` / `AMBIGUOUS` | nothing | `SeedConflictError` naming the role and `<email_var>`, never the other tenant or account ids |

Why `_ensure_membership_set` must change even without the merge rule: `seed-logins` runs on every VM deploy and its exit code gates the release (`scripts/vm/deploy.sh:382-399`). Today a Host login that gains a `speaker` row (with `valid_from` set, per T6b-1 §5 step 12) makes the next run raise `SeedConflictError` ("external subject already has a different membership", `seed_pilot.py:193-207`), and the deploy rolls back. Ignoring `INVITATION_ONLY_ROLES` rows closes that.

This also closes T6b-1 §11's residual: the seed's credential writes now take the same address lock and row locks as activation.

## 4. Activation, invite pre-check, unbind

### 4.1 `POST /v1/speaker-portal/activate`

Request `ActivateRequest` (`extra="forbid"`): `token` (str 16–128), `new_password` (str 1–1024, optional), `existing_password` (str 1–1024, optional). A model validator requires **exactly one** of the two → otherwise `422 invalid_request`.

| Status | Code | When |
|---|---|---|
| 200 | — | `LoginResponse` for the **bound login** (the contact account, or the Host's account) |
| 400 | `speaker_portal_invitation_invalid` | Every T6b-1 refusal, plus R-E, R-F, and §4.2's existing-login refusals. One code, one message, identical bytes. |
| 401 | `speaker_portal_credentials_invalid` | Existing-login mode, wrong `existing_password`. `WWW-Authenticate: Bearer` (the login route's header, `auth.py:300`). Token not consumed. |
| 409 | `speaker_portal_activation_mode_mismatch` | The body carried the other password field. `details: {"expected": "existing_password" \| "new_password"}`. Reached only after the token is verified (§4.2 step 8), so only the invitee learns the mode (Q5). Nothing written. |
| 422 | `password_too_weak` | `new_password` fails `check_new_password`; checked before the token (T6b-1 step 2). `existing_password` has no policy check. |
| 429 | `rate_limited` | T6b-1's `speaker_portal.activate:<host>` bucket, 10 / 5 min, charged and committed first. |

### 4.2 The transaction, with the lock order

**Lock order (every path, §4.5):** `speaker_profile` row → `speaker_portal_invitation` row → address advisory lock → `pilot_credential` rows (by id) → writes.

1. Charge `LoginAttemptLimiter`, commit. **Every** attempt is counted, so a wrong `existing_password` is counted (R-H).
2. Body shape (exactly one password field).
3. `new_password` present → `check_new_password` → `422`.
4. `is_well_formed_token` → `400`.
5. `find_invitation_id_by_token_hash` (no lock) → `400` on miss.
6. `lock_profile` `FOR UPDATE`.
7. `lock_invitation` `FOR UPDATE` + T6b-1 step 6's refusals, **minus** its last bullet ("contact account already credentialed"), which moves to step 10.
8. `hmac.compare_digest(token, derive_token(secret, invitation.id))` → `400`.
9. `lock_address(address)`; `holders = holders_for_address(lock=True, also_lock_user_id=professional_id)`. `contact_credentialed` = the contact account's row was among the locked rows.
10. Choose the mode:

| `holders.state` | Extra condition | Mode |
|---|---|---|
| `NONE` | `contact_credentialed` | `400` (T6b-1 round-2 rule, unchanged) |
| `NONE` | otherwise | **new login** |
| `ONE_IN_TENANT` | holder ≠ contact account **and** `contact_credentialed` | `400` (R-B: a merged contact account must stay credential-less) |
| `ONE_IN_TENANT` | holder bound to another profile (`login_bound_elsewhere`) | `400` (`uq_speaker_profile_account`: one login, one Speaker) |
| `ONE_IN_TENANT` | holder holds an active `admin`, `coordinator` or `student` membership | `400` (Q1) |
| `ONE_IN_TENANT` | otherwise | **existing login** |
| `OTHER_TENANT`, `AMBIGUOUS` | — | `400` (R-E, R-F) |

11. Mode ≠ supplied field → `409 speaker_portal_activation_mode_mismatch`. Roll back; the token stays live.
12. **Existing login:** `verify_password(existing_password, holder.password)`; false → `401`, roll back (token not consumed; the attempt is already committed in step 1). Then `holder.suspended` → `400`.
13. **Both modes:** `grant = find_or_add_role(email=address, role="speaker", path=<profile unit path>, now, create=NewLogin(professional_id, derive(new_password)) if new login else None)`. It re-takes the address lock and re-reads the same locked rows (re-entrant, same answer). New login: `grant.user_id == professional_id` and `login_created`; existing: `grant.user_id == holder.user_id`.
14. `bind(professional_id, account_user_id=grant.user_id, now)`: `UPDATE speaker_profile SET account_user_id, account_bound_at = :now WHERE … AND account_user_id IS NULL`. 0 rows → `400`. `IntegrityError` on `uq_speaker_profile_account` → `400` (defence in depth behind step 10).
15. `UPDATE speaker_portal_invitation SET accepted_at = :now, bound_account_user_id = grant.user_id, binding_mode = 'new_login' | 'existing_login'`.
16. JSON route: issue a `pilot_session` for `grant.user_id`. Form route: no session (T6b-1 C4).
17. One commit.

Existing login writes **no** `user_account.email`, **no** credential, and **no** new account. The contact account keeps its `.invalid` email and no credential (R-B).

**`/s/{token}` pages.**

- `GET` renders the **new-password form** (T6b-1's bytes) for every token except a live, verified one whose step-10 answer is existing login; that one gets the **existing-password form** ("This email address already signs in to SmartMatch. Enter that password to add your Speaker access."; `autocomplete="current-password"`). Reads only, no locks, no writes, no limiter charge. Token never in the HTML.
- `POST` accepts `new_password` + `confirm_password`, **or** `existing_password`. It maps `401` to the existing form with "That password does not match." (status 401), and `409` to the other form (status 409).
- Success page, existing login: "Speaker access is added to your SmartMatch login. Sign in, or reload SmartMatch if you are already signed in, then use Switch portal."

This narrows T6b-1's `test_s_page_is_identical_for_every_token` to "identical for every token that is not a live existing-login invitation" (C1 in §10: the parent's "the landing page only asks for the password the mode needs" wins). The only party who can see the difference holds a live 256-bit token.

### 4.3 Invite pre-check (R-F)

T6b-1's invite (§3.2 there), new step **5b** after the channel checks and before `revoke_live`: `holders_for_address(tenant_id, address, lock=False)`. Advisory only; activation decides.

| State | Answer |
|---|---|
| `OTHER_TENANT` | `409 speaker_portal_address_in_other_tenant` |
| `AMBIGUOUS` | `409 speaker_portal_address_ambiguous` (Q3), message "This address matches more than one login. Fix that before inviting." (§4.5 item 4) |
| `ONE_IN_TENANT`, holder has an active staff or student role | `409 speaker_portal_address_is_staff_login` (Q1) |
| otherwise | continue |

### 4.4 Unbind — `DELETE /v1/units/{unit_id}/speaker-contacts/{professional_id}/portal-access`

Roles `{admin, coordinator}` (`_authorize_speaker_portal`, T6b-1). Quota: T6b-1's write bucket (`speaker_portal.invite`, 20/min). Response `200 {"unbound": bool}`: `false` when nothing was bound (idempotent, the revoke route's shape). Errors: `404 speaker_contact_not_found`, `403`, `429`.

1. `charge_quota`; authorize; `now = utc_now()` once.
2. `lock_profile` `FOR UPDATE`. `account_user_id IS NULL` → `{"unbound": false}`.
3. `lock_bound_profile_invitation`: the accepted invitation with `bound_account_user_id = account_user_id AND unbound_at IS NULL`, `FOR UPDATE`.
4. `login = account_user_id`. If `login == professional_id` (a new-login binding): `lock_address(<contact account email>)`, `holders_for_address(lock=True, also_lock_user_id=login)`, `retire_login(login, now)`. The contact account goes back to credential-less, its sessions end, and a later re-invite runs new-login cleanly (Q-3 in §11).
5. `UPDATE membership SET valid_until = :now WHERE tenant_id, user_id = login, role = 'speaker', valid_until IS NULL OR valid_until > :now`. Every active `speaker` row on that login: only activation grants `speaker`, and one login speaks for at most one profile. **No other role's row is touched** (R-I).
6. `UPDATE speaker_profile SET account_user_id = NULL, account_bound_at = NULL`.
7. `UPDATE speaker_portal_invitation SET unbound_at = :now, unbound_by_user_id = principal.user_id`.
8. Commit.

The next request by that login loses the Speaker portal: `PrincipalRepository` loads memberships per request (`principals.py:105-135`) and the policy treats `valid_until` as exclusive (`policy.py:188-192`). `/v1/me/*` Speaker routes answer `404 speaker_profile_not_linked` (T6b-2 §2.1). `GET …/portal-access` answers `none`, so the Connector can invite again.

**DDL** (Q2 decides `0039` or `0041`): `unbound_at timestamptz NULL`, `unbound_by_user_id uuid NULL`; `fk_speaker_portal_invitation_unbound_by (tenant_id, unbound_by_user_id) → user_account (tenant_id, id) RESTRICT`; `ck_speaker_portal_invitation_unbound_pair`: `(unbound_at IS NULL) = (unbound_by_user_id IS NULL)`; `ck_speaker_portal_invitation_unbound_after_accept`: `unbound_at IS NULL OR (accepted_at IS NOT NULL AND unbound_at >= accepted_at)`. Two more keys for `test_check_constraints.py`.

**`GET …/portal-access`** gains `login_shared: bool | null`: `true` when `status = active` and the binding is `existing_login`, `false` for `new_login`, `null` otherwise. A bool, never the login id (T6b-2's rule: the Connector view hides the login).

### 4.5 Lock order, all paths

| Path | Order |
|---|---|
| Invite (T6b-1) | profile → invitation(s). Pre-check reads, locks nothing. |
| Activation, both modes | profile → invitation → address lock → `pilot_credential` rows by id → writes (`user_account`, `pilot_credential`, `membership`, `speaker_profile`, `speaker_portal_invitation`, `pilot_session`) |
| Unbind | profile → accepted invitation → [new login only: address lock → `pilot_credential` row] → writes |
| Seed tool | seed advisory lock → address lock → `pilot_credential` rows by id → writes |
| Login (`/v1/auth/login`) | none (reads) |

Global order: seed lock < profile < invitation < address lock < `pilot_credential`. Every path takes an ordered subsequence, so there is no cycle. The advisory lock stops a second **insert** at the address (every inserter goes through `find_or_add_role`, §3.3); `FOR UPDATE` stops a concurrent **update or delete** of an existing holder's credential between verify and bind. Both are needed; neither alone closes R-D.

## 5. Authorization

**`tests/authz/test_policy_matrix.py`:**

1. Shape `host_and_speaker_at_owning_unit`: `memberships=(_member(OWNING_UNIT, "volunteer"), _member(OWNING_UNIT, "speaker"))`, "one login holding the Event Host and Speaker roles (T6b-5)". Appended to `SHAPES` (`:2573`), not to `_ACTIVE_OWNING_UNIT_SHAPES`.
2. Its column is **derived**, then pinned literally. After the `MATRIX` literal and before the alias (`:8366`): each row's cell = `permit` if `volunteer_at_owning_unit` or `speaker_at_owning_unit` permits, else `deny("no_grant")`. Every cell still runs through the real authorizer in `test_the_matrix_describes_what_the_code_does` (`:9483`), so the derivation asserts nothing by itself.
3. `HOST_AND_SPEAKER_PERMITS`: a literal frozenset. 6 Host keys (`metrics.read`, `metrics.speaker_pipeline`, `speaker_request.create`, `speaker_request.list_own`, `host_organization.read_own`, `host_organization.upsert_own`) + T6b-2's 5 `speaker_self.*` = 11; 14 once T6b-3's 3 `me.contact_channels.*` are on the base. `test_the_two_membership_shape_permits_exactly_host_and_speaker_operations`.
4. `test_neither_membership_widens_the_other`: for every operation, the two-membership cell permits **iff** one of the single-membership cells does. This is §4.5's "neither widens the other".
5. `test_the_speaker_exclusion_does_not_knock_out_the_host_on_metrics`: `metrics.read` permits for the two-membership shape through the `volunteer` row, although rule 8 (T6b-1 R8) skips the `speaker` row.
6. Operation `speaker_portal.unbind` (`DELETE …/portal-access`), rectangle copied from `speaker_portal.revoke` including both new columns. `test_route_roles.py`: one literal row with `_SPEAKER_PORTAL`, exact-set test extended.

**`tests/authz/test_policy_negatives.py`:** `test_a_suspended_two_membership_principal_is_denied_everywhere` (R-L: `principal_suspended` on a Host operation and on a Speaker operation), `test_an_expired_speaker_row_leaves_the_host_row_working` (the unbind shape).

## 6. Portal switcher (milestones 11–13, after T6b-4)

### 6.1 `PortalSwitcher`

Props: `current: PortalKind`, `placement: "sidebar" | "header"`.

- Reads `usePortalAccess()`. Renders **nothing** unless `status === "ready"` and `mapping.portals.length >= 2`.
- A native `<button type="button" aria-expanded={open} aria-controls={listId}>` with visible text "Switch portal" (the header placement shows an icon plus the same text in `sr-only`). `min-h-11` (44px target).
- Pattern: **disclosure navigation**, not `role="menu"`. The items are page links, and `role="menu"` would promise arrow-key roving focus the links do not need. Keyboard: Enter/Space toggle (native button), Tab moves through links, Escape closes and returns focus to the button, focus leaving the component closes it, a pointer-down outside closes it.
- The list: `<ul id={listId}>` of `<li><Link to={p.home_path} aria-current={p.portal === current ? "true" : undefined}>{p.display_name}</Link></li>`, in the server's order. `aria-current="true"`, not `"page"`: the link targets the portal's home, and the user may be on a sub-page.
- Selecting a link calls `rememberPortal(p.portal)`, closes, and lets `Link` navigate. **No fetch, no `requestJson`, no mutation.**
- Names come from `display_name` only (`test_the_portal_shells_show_the_server_s_own_portal_name`, `test_frontend_auth_contract.py:557`). No persona string literal.
- `useId()` for `listId`, so two instances never share an id.

### 6.2 Remembered choice

- `portalChoice.ts` stores the portal id (`"volunteer"`, `"speaker"`) only. Never a user id, token or principal key (`principalKey.ts:36-39`).
- `readRememberedPortal(granted)` returns a value only if it is in `granted` (the server's `portals[].portal`); anything else reads as `null`. Every `localStorage` access is inside try/catch; a throw reads as `null` or is ignored.
- `Home.tsx` (`:81-83`): `mapping.portals.find(p => p.portal === readRememberedPortal(ids)) ?? mapping.portals.find(p => p.portal === mapping.default_portal) ?? mapping.portals[0]`. It still navigates to `target.home_path` (`test_home_navigates_to_the_server_reported_path_and_composes_none`).
- Sign-out forgets it (`useSession.tsx:66`), so the next person on a shared browser starts at `default_portal`.
- Customer §3 ("no portal chooser", `product_scope.py:124`) is about sign-in: the login page stays two fields (`test_the_login_screen_names_no_role_at_all`). The switcher only lists portals the server already granted; it grants nothing.

### 6.3 Header slots (coordination with T6b-4)

| Shell | Slot 1 — desktop (`placement="sidebar"`) | Slot 2 — mobile (`placement="header"`) |
|---|---|---|
| `VolunteerPortalLayout.tsx` (main) | Sidebar footer, between the identity block's closing `</div>` (`:169`) and the Sign out `<button>` (`:170`). Wrapped `hidden lg:block`. | The mobile header's right-hand spacer `<div className="w-6" />` (`:193`) is replaced by the switcher; with one portal it renders nothing and the spacer's width is kept by a `min-w-6` wrapper. |
| `SpeakerPortalLayout.tsx` (T6b-4) | Same position: identity block → **switcher** → Sign out. | Same position: the mobile header's right-hand slot. |

**Request to T6b-4:** build the speaker shell with the volunteer shell's structure (sidebar footer identity block followed by Sign out; mobile header `[menu button] [logo] [right slot]`). If it deviates, T6b-5 uses the equivalent positions and records them in the PR body. One instance is visible per breakpoint: `hidden lg:block` in the sidebar, and the mobile header is already `lg:hidden` (`:183`).

The Connector and Student shells get no switcher: under Q1 a staff or student login is never merged with a Speaker role, so they cannot hold two portals from this track.

### 6.4 Freshness

`PortalAccessProvider` fetches once per principal per page load (`usePortalAccess.tsx:83-129`). A Host already signed in when they activate in another tab sees the switcher after a reload; the success page says so (§4.2). A fresh sign-in is a new principal key, so `/v1/me` and `/v1/me/portals` are fetched anew (parent §4.5 "activation invalidates"). No provider change.

## 7. Connector UI (`SpeakerPortalInvite.tsx`, T6b-1's)

| State / code | Shows |
|---|---|
| `active`, `login_shared = true` | "Portal active since {date}. This Speaker signs in with the login they also use as an Event Host. Suspending that login suspends both." + "Remove portal access" |
| `active`, `login_shared = false` | "Portal active since {date}. Suspending this login suspends the Speaker's portal access." + "Remove portal access" |
| Remove portal access | Confirm dialog: "Remove {name}'s Speaker portal access? Their Event Host access, if any, stays." `useMutation`, pending-disabled, invalidates only `["speaker-portal-access", unitId, professionalId]`. |
| `409 speaker_portal_address_in_other_tenant` | "This address signs in to another SmartMatch organization. Choose a different address." |
| `409 speaker_portal_address_ambiguous` | "This address matches more than one login. Fix that before inviting." |
| `409 speaker_portal_address_is_staff_login` | "This address belongs to a staff or student login and cannot also be a Speaker login." |

R-L has no other home: **no route or UI suspends an account today** (the only `suspended` writers are seeds and operators). `vm-deploy.md` gets the same sentence under the operator's suspension procedure, and any future suspend UI must show it.

## 8. TDD list

Local rule: one file at a time; DB tests on a private database `smartmatch_b26_t6b5`, dropped after. Password and token literals built at runtime (forbidden-behaviour scanner). Vitest from a Linux-FS copy: `npx vitest run --pool=threads <file>`. CI proves the suite.

### 8.1 Parent §7 row 8b, item by item

| # | Row 8b item | Test (file :: name) |
|---|---|---|
| 1 | Existing-login: right password binds and adds `speaker` | `tests/contract/test_speaker_portal_api.py::TestExistingLogin::test_right_password_binds_the_host_login_and_adds_speaker` (bound = Host id, `binding_mode = existing_login`, one new active `speaker` row at the profile unit path, Host email / credential / `volunteer` row byte-identical, contact account still credential-less with its `.invalid` email) |
| 2 | Wrong password → 401, token not consumed, attempt counted | `…::test_wrong_password_is_401_and_the_token_stays_live` (then the right password succeeds with the same token), `…::test_wrong_password_attempts_are_counted_by_the_activation_limiter` (10 wrong → 11th is 429 with the right password; `/v1/auth/login`'s counter unchanged) |
| 3 | New-login refused when a credentialed account holds the address | `…::test_new_password_for_a_held_address_is_409_and_writes_nothing` (`details.expected == "existing_password"`; no credential, email, membership or invitation change); `…::test_existing_password_for_a_free_address_is_409` |
| 4 | Ambiguous and other-tenant refused | `…::test_ambiguous_address_is_the_generic_400` and `…::test_other_tenant_address_is_the_generic_400` (both byte-identical to an unknown token); `…::test_invite_precheck_other_tenant_is_409`; `…::test_invite_precheck_ambiguous_is_409` |
| 5 | Concurrent activations → one binding | `tests/integration/test_speaker_portal_activation.py::test_two_invitations_to_one_host_address_bind_once` (two profiles, two threads, right password: one `200`, one `400`, one binding); `::test_concurrent_new_login_and_seed_at_one_address_leave_one_credential` (closes T6b-1 §11's residual); `::test_a_credential_update_waits_for_the_activation_lock` (a second connection's `UPDATE pilot_credential` blocks until commit) |
| 6 | `/v1/me/*` resolves via `account_user_id` in both modes | `tests/contract/test_speaker_self_api.py::test_availability_and_invitations_after_existing_login_activation` and `::test_after_new_login_activation` (end to end through activate; rows keyed by `professional_id`; a portal answer's `recorded_by` is the login; the Connector batch view still shows `recorded_by_user_id: null` and no Host id in the raw body) |
| 7 | Host routes unchanged | `tests/contract/test_speaker_portal_merge_host_routes.py::test_host_routes_answer_the_same_before_bind_after_bind_and_after_unbind` (`speaker_request.list_own`, `host_organization.read_own`: identical status and body at all three points); `::test_host_can_still_file_a_request_after_bind` |
| 8 | Policy matrix two-membership shape | §5 items 1–6 |
| 9 | `/v1/me/portals` lists both | `tests/contract/test_portals_api.py::test_a_merged_login_lists_volunteer_then_speaker_and_defaults_to_volunteer`; `tests/unit/test_portal_order.py::test_volunteer_precedes_speaker` |
| 10 | Switcher hidden with one portal | `src/app/components/PortalSwitcher.test.tsx::renders nothing with one portal` (and while loading, and when unavailable) |

### 8.2 The rest

**`tests/integration/test_login_accounts.py`** (DB):

1. `test_none_with_create_credentials_the_account_and_adds_the_role`
2. `test_one_in_tenant_adds_the_role_once` (second call: `role_added=False`, one row)
3. `test_an_expired_role_row_gets_a_new_active_row` (the old row untouched)
4. `test_ambiguous_raises_and_writes_nothing` · `test_other_tenant_raises_and_writes_nothing`
5. `test_create_for_an_already_credentialed_account_raises` · `test_create_when_the_address_is_held_raises`
6. `test_addresses_match_case_and_whitespace_insensitively_and_are_stored_trimmed`
7. `test_the_address_lock_serializes_two_writers` (two connections; the second's `lock_address` blocks until the first commits; timeout-bounded)
8. `test_retire_login_revokes_sessions_and_deletes_the_credential` · `test_rotate_own_password_updates_only_that_row`
9. `test_inserted_memberships_have_null_valid_from_and_created_at_now`

**`tests/unit/test_login_account_writers.py`:** §3.3 items 1–5.

**`tests/unit/test_seed_pilot_logins.py`** (rewritten recorder: patches `lock_address`, `holders_for_address`, `find_or_add_role`, `rotate_own_password` instead of `seed_pilot` + `PilotCredentialRepository`, `:62-89`). Kept: the 8 existing tests' assertions. New:

1. `test_a_free_address_creates_the_login_through_find_or_add_role`
2. `test_the_seeds_own_login_gets_its_roles_and_a_rotated_password`
3. `test_a_foreign_login_gets_the_roles_and_keeps_its_password` (stderr names the variable, never the password)
4. `test_ambiguous_or_other_tenant_address_is_a_conflict_error`
5. `test_the_connector_login_adds_coordinator_and_admin_in_one_transaction`

**`tests/integration/test_seed_pilot_logins_db.py`** (new, DB): `test_rerun_after_a_host_gains_speaker_succeeds_and_leaves_speaker_alone`; `test_seed_at_an_activated_speakers_address_creates_no_second_credential` (`load_by_email` still returns the one login); `test_two_runs_are_idempotent`.

**`tests/unit/test_seed_pilot.py`:** `test_membership_set_ignores_invitation_only_roles`; `test_a_foreign_non_invitation_role_is_still_a_conflict`.

**Unbind** (`tests/contract/test_speaker_portal_api.py::TestUnbind`):

1. `test_unbind_expires_only_the_speaker_row_and_clears_the_binding` (`valid_until == now`; `volunteer` row byte-identical; `account_user_id` and `account_bound_at` null; `unbound_at`, `unbound_by_user_id` set)
2. `test_next_request_loses_speaker_routes_and_portal` (`/v1/me/availability` → 404 `speaker_profile_not_linked`; `/v1/me/portals` lists `volunteer` only; same bearer token)
3. `test_new_login_unbind_retires_the_contact_login` (sessions revoked, credential gone, `/v1/auth/login` → 401)
4. `test_reinvite_after_unbind_works_in_both_modes`
5. `test_unbind_is_idempotent` · `test_unbind_other_unit_is_404` · `test_portal_access_reports_login_shared`

**Suspension:** `tests/contract/test_me_suspended.py::test_a_suspended_merged_login_is_refused_on_host_and_speaker_routes`.

**`/s` pages:** `test_s_page_asks_for_the_existing_password_only_for_a_live_existing_login_token`, `test_s_page_is_identical_for_every_other_token` (replaces T6b-1's all-token test), `test_s_form_existing_password_activates_without_a_session`, `test_s_form_wrong_existing_password_is_the_401_page_and_keeps_the_token`.

**Frontend (Vitest, `*.test.tsx` only — CI's glob):**

- `src/app/components/PortalSwitcher.test.tsx`: renders nothing with one portal, while loading, and when unavailable; lists `display_name`s in server order; `aria-expanded` toggles; Escape closes and returns focus; `aria-current="true"` only on `current`; links point at `home_path`; clicking stores the choice; a throwing `localStorage` still navigates; **no `fetch` call** on open or select (`vi.stubGlobal("fetch", spy)`).
- `src/lib/portalChoice.test.tsx`: validated read; unknown value → `null`; getItem, setItem and removeItem throwing are all silent.
- `src/app/pages/Home.test.tsx`: a granted remembered portal wins; an ungranted one is ignored; a throwing storage falls back to `default_portal`.
- `src/app/pages/coordinator/SpeakerPortalInvite.test.tsx` (T6b-1's file): the 3 new 409 messages; remove-access confirm and single-key invalidation; the shared-login sentence names suspension.
- `tests/unit/test_frontend_portal_switcher_contract.py` (source scan): `PortalSwitcher.tsx` imports no `api` function and calls no `fetch`; both layouts render `<PortalSwitcher`; `portalChoice.ts` touches `localStorage` only inside `try`.

## 9. Milestones (red → green, one commit each, pushed)

| # | Commit | Red → green |
|---|---|---|
| 0 | `chore: merge origin/feat/b26-t6b-2 into feat/b26-t6b-5` (+ T6b-3 if pushed) | — |
| 1 | `test: login_accounts and the single pilot_credential writer (red)` | §8.2 `test_login_accounts.py`, `test_login_account_writers.py` |
| 2 | `feat: login_accounts is the one pilot_credential writer` | Module; `upsert` removed; T6b-1 new-login activation routed through `find_or_add_role`; advisory lock moved. T6b-1's activation tests stay green. |
| 3 | `test: seed-pilot-logins on find_or_add_role (red)` | §8.2 seed tests |
| 4 | `feat: seed-pilot-logins uses find_or_add_role; seeds ignore invitation-only roles` | green |
| 5 | `test: existing-login activation, mode choice and locking (red)` | §8.1 items 1–5, `/s` page tests |
| 6 | `feat: existing-login activation mode with credential row locks` | green |
| 7 | `test: invite pre-check and portal-access unbind (red)` | §8.1 item 4 pre-check, `TestUnbind`, migration CHECK keys |
| 8 | `feat: other-tenant invite pre-check and unbind` | Route, repository, DDL (or `0041`), `login_shared`, Connector UI rows (§7), `api.ts` |
| 9 | `test: two-membership authz shape and merged-login contract tests` | §8.1 items 6–9, §5. **Expected green on arrival**: they prove no policy change is needed. The commit body says so; any red here is a bug to fix in this milestone. |
| 10 | `docs: T6b-5 backend notes in pilot-login decision and vm-deploy` | — |
| 11 | `chore: merge origin/feat/b26-t6b-4` | — |
| 12 | `test: portal switcher and remembered landing (red)` | §8.2 frontend |
| 13 | `feat: portal switcher in the Event Host and Speaker shells` | green; `npx tsc --noEmit -p .` |
| 14 | `docs: one login, two roles in DESIGN.md and GLOSSARY` | — |

Before each push: `$VENV/bin/ruff format` and `ruff check` on touched Python and this plan.

## 10. Contradictions and rulings taken here

| # | Conflict | Ruling |
|---|---|---|
| C1 | T6b-1: `GET /s/{token}` is byte-identical for every token. Parent §4.2: "the landing page only asks for the password the mode needs." | **Parent wins** (the orchestrator's "follow §4.5"). Identical for every token except a live existing-login one (§4.2). Only a live 256-bit token holder sees the difference. |
| C2 | T6b-1 §5 step 6 refuses any credentialed contact account. Existing login needs a finer rule. | Kept for new login; for existing login, refused unless the contact account is the holder itself (§4.2 step 10). |
| C3 | T6b-1 §5 step 8's advisory lock key `'speaker-portal-email:'`. | Renamed `'login-address:'` inside `lock_address`; one function, all callers in one commit. |
| C4 | T6b-1 §4.6 writes `membership.valid_from = now`. | `NULL` for every `find_or_add_role` insert (§3.2). `created_at` keeps the grant time; unbind and seed reconciliation both need it. |
| C5 | T6b-1 §11 self-invite mitigation: "the Connector's own login address is credentialed, so activation refuses it". Existing-login mode would now accept it with the Connector's own password. | Q1: refuse holders with an active `admin`, `coordinator` or `student` membership. |
| C6 | `test_seed_pilot_logins.py` monkeypatches `seed_pilot` and `PilotCredentialRepository` (`:62-89`). | Rewritten recorder (§8.2); the 8 behaviours it pins are kept. |

## 11. Open questions (each with a recommendation)

**Decide before milestone 5**

| # | Question | Recommendation |
|---|---|---|
| Q1 | Which existing logins may existing-login mode bind? | **Event Host logins only.** Refuse a holder with any active `admin`, `coordinator` or `student` membership: generic `400` at activation, `409 speaker_portal_address_is_staff_login` at invite. The owner's rule names Host + Speaker; binding a Connector's own login would reopen T6b-1's self-invite risk with no second mailbox needed. |
| Q2 | Where do `unbound_at` / `unbound_by_user_id` go? | **Fold into `0039`** if it is not on `main` yet (T6b-2 C2's precedent); otherwise `0041`. Without them, who removed a Speaker's access is unrecorded. |
| Q3 | Should a new-login unbind also delete the contact account's credential and end its sessions? | **Yes.** It restores "the contact account cannot sign in on its own" (§4.5 item 2) and lets a re-invite take the new-login path. The rule as written (membership + `account_user_id`) leaves a role-less login that blocks re-invites. |

**Decide before milestone 3 / 7**

| # | Question | Recommendation |
|---|---|---|
| Q4 | The seed finds its address already held by a different login. | **Add the seed's roles to that login, never change its password, report on stderr.** Refusing would fail `seed-logins` and roll back every VM deploy (`deploy.sh:382-399`). |
| Q5 | New codes `409 speaker_portal_activation_mode_mismatch` (with `details.expected`) and `409 speaker_portal_address_ambiguous`. | **Accept both.** The first is reached only by a live-token holder, after verification, and writes nothing; the second is parent §4.5 item 4's "Connector sees …" message. |

## 12. Risks

| Risk | Mitigation | Residual |
|---|---|---|
| Wrong person bound (parent risk 2) | Password of the existing login + the token + Q1 + `uq_speaker_profile_account` + unbind with actor | A Host who shares their password with someone else. Accepted. |
| A future account-creation path adds a second credential (risk 2b) | `find_or_add_role`; §3.3 guard over `python/`, `services/`, `tools/`, `scripts/`, `db/` | Direct SQL by an operator. `vm-deploy.md` says to use the seed tool. |
| A merged seed login (Q4) is under another subject, so `seed_pilot_engagement`'s `pilot-login-*` subject lookups (`tools/seed_pilot_engagement.py:148`) miss it | The seed's stderr line names it | Engagement seed skips that login. Accepted for the pilot; noted in `vm-deploy.md`. |
| A Host signed in elsewhere sees the Speaker portal only after reload | Success page says so (§6.4) | None. |
| `seed-logins` fails the deploy after the first merge | `_ensure_membership_set` ignores invitation-only roles (§3.4); DB test | None once milestone 4 lands. |

## 13. Out of scope

- An account suspension route or UI (none exists; §7).
- Merging staff or student logins with a Speaker role (Q1).
- The self-request exclusion for a merged Host (T4's Q8 rule; it keys on `account_user_id`, so it applies unchanged).
- A switcher in the Connector and Student shells.
- Re-fetching `/v1/me/portals` on tab focus.

---

**Next action (under two minutes):** ask the orchestrator to rule on Q1 and Q2, the two that change activation and `0039`.
