# B26 T3 — Connector availability `GET`/`PATCH`, OpenAPI, `api.ts` adapter

**Next action:** `git fetch origin && git merge origin/feat/b26-t2` on `feat/b26-t3`, then write `tests/unit/test_speaker_availability_models.py` (§6) red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2, §4 intro, §4.1, §6 (adapter only), §7 row 3, §8 T3.
Inputs, as built: `origin/feat/b26-t2` (PR #212, head `358da818`, already carries T1 / PR #210):
`python/smartmatch_domain/smartmatch_domain/speaker_availability.py` (T1) and
`python/smartmatch_persistence/smartmatch_persistence/speaker_availability.py` (T2, migration `0038`).

**Branch strategy (stacked).** The implementer merges `origin/feat/b26-t2` into `feat/b26-t3` first — a merge, not a rebase, so the pushed plan commit stays. The T3 PR targets `main` and its body opens with **"Merge #210 and #212 first."** After both land, merge `main` into `feat/b26-t3` so the diff shows T3 only.

## 1. Files

| Path | Change |
|---|---|
| `services/api/smartmatch_api/routers/speaker_availability_models.py` | **New.** Models (§2), `statement_from_request`, `availability_error`, `stale_error`, `availability_response`. No router. Shared with T6b-2's `/v1/me/availability` (precedent `manual_events_models.py`). |
| `services/api/smartmatch_api/routers/speaker_availability.py` | **New.** `router = APIRouter(prefix="/v1/units", tags=["speaker-contacts"])` (bare module-level assignment: `test_policy_matrix.py:8924` guard); `_roster: Final = SpeakerContactRepository()`, `_availability: Final = SpeakerAvailabilityRepository()`; the two routes (§3). |
| `services/api/smartmatch_api/main.py` | Add `speaker_availability` to the `smartmatch_api.routers` import (`:47-84`); add `(speaker_availability.router, Capability.SPEAKER_CONTACT_MANAGEMENT)` to `CAPABILITY_SCOPED_ROUTERS` right after `cba_contacts.router` (`:444`), with a comment: roster data, sends nothing, so not `CONSENTED_OUTREACH` (same argument as `student_speaker_feedback.connector_router`, `:542-551`). |
| `contracts/openapi/smartmatch.json` | Regenerated: `make openapi VENV=$VENV` (`Makefile:356-359`); CI runs `--check` (`.github/workflows/verify.yml:127`). |
| `apps/web/legacy-frontend/src/lib/api.ts` | Types + 2 functions (§5), placed after `fetchSpeakerContactChannels` (`:4042-4052`). |
| `tests/authz/test_policy_matrix.py` | 2 `Operation` rows after `speaker_contact.channel.transition` (`:2100-2114`); 2 `MATRIX` aliases after `:8366`. |
| `tests/authz/test_route_roles.py` | 2 `ROUTE_ROLE_LEDGER` rows (`:71-80`), a `_SPEAKER_CONTACT` literal beside `:61-63`, 1 live-constant test, exact-set test (`:201-212`) extended. |
| Tests (new) | `tests/unit/test_speaker_availability_models.py`, `tests/contract/test_speaker_availability_api.py`, `tests/unit/test_speaker_availability_openapi_contract.py`, `tests/unit/test_frontend_speaker_availability_contract.py`, `apps/web/legacy-frontend/src/lib/speakerAvailabilityApi.test.tsx`. |

**Reused, not edited:** `cba_contacts._authorize_speaker_contacts(session, principal, unit_id) -> uuid.UUID` (`cba_contacts.py:624-663`, roles `_SPEAKER_CONTACT_ROLES` `:252`), `SPEAKER_CONTACT_READ_RATE_LIMIT` / `SPEAKER_CONTACT_WRITE_RATE_LIMIT` (`:258-263`), `cba_contacts._not_found()` (`:957`), `SpeakerContactRepository.get(session, *, tenant_id, owning_unit_id, professional_id)` (`smartmatch_persistence/cba_contacts.py:561`), `charge_quota(session, principal, limit)` (`dependencies.py:286`), `ApiError(*, status_code, code, message, details=None)` (`errors.py:49`), `utc_now()` (`utils.py:10`, returns `datetime.now(UTC)`).

**Imports from T2/T1 as built:**
`from smartmatch_persistence.speaker_availability import AvailabilitySource, SpeakerAvailabilityRepository, StaleSpeakerAvailabilityError, StoredSpeakerAvailability`;
`from smartmatch_domain.speaker_availability import AvailabilityStatement, AvailabilityStatementInvalid, UnavailableWindow, validate_availability_statement`.

## 2. Models (`speaker_availability_models.py`)

Decimal convention: **JSON number**. No route exposes a `Decimal` today (`grep Decimal services/api` is empty); `matching_weights.py:180-247` uses `float`; parent §4.1 shows `24.0`. The request takes `StrictFloat | StrictInt` (a bool or string is `invalid_request`), converted with `Decimal(str(v))` (T1 hand-off, `T1-plan.md:124`; a raw float raises `TypeError` in `AvailabilityStatement.__post_init__`) so `24.05` stays `24.05` and fails the 1-decimal rule. The response is `float(stored_decimal)`.

```python
class AvailabilityWindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_on: date
    ends_on: date


class SpeakerAvailabilityUpdateRequest(BaseModel):
    """Full replace. Every key is required; null clears. No subject field (MM-A01)."""

    model_config = ConfigDict(extra="forbid")
    # Required, nullable. null = "I read stated: false" (T2 C1). StrictInt: lax int
    # would turn `true` into version 1 and "3" into 3.
    expected_version: StrictInt | None
    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: StrictFloat | StrictInt | None
    unavailable: list[AvailabilityWindowInput]  # no max_length: the domain says too_many


class AvailabilityWindowView(BaseModel):
    starts_on: date
    ends_on: date
    source: Literal["speaker", "connector"]  # StoredWindow.created_source.value


class SpeakerAvailabilityResponse(BaseModel):
    professional_id: uuid.UUID
    stated: bool  # false = no row; UI says "Not stated", never "Available"
    version: int | None  # null exactly when stated is false
    invitations_paused_until: date | None  # stored value, even if already past
    declared_capacity_hours_per_90_days: float | None
    unavailable: list[AvailabilityWindowView]  # from stored.windows, T2 order (starts_on, ends_on)
    updated_source: Literal["speaker", "connector"] | None
    updated_at: datetime | None
```

Helpers (all pure, unit-tested without a DB):

- `statement_from_request(body, stored: StoredSpeakerAvailability | None, today: date) -> AvailabilityStatement` — §3 step 6.
- `availability_error(exc: AvailabilityStatementInvalid) -> ApiError` — table below.
- `stale_error() -> ApiError` — 409, fixed message, no `details`.
- `availability_response(professional_id: uuid.UUID, stored: StoredSpeakerAvailability | None) -> SpeakerAvailabilityResponse`.

Not stated → `stated=false`, `version`/pause/capacity/`updated_source`/`updated_at` null, `unavailable=[]`. `updated_by_user_id` and window `created_by_user_id` are **not** returned (§4.1 does not list them). T8 later adds `load`, an additive field.

**Error codes, both routes.** Envelope `{"error": {"code", "message", "details"?}}`.

| Status | Code | When | `details` |
|---|---|---|---|
| 401 | `unauthenticated` | no/invalid bearer (`dependencies.py:182-202`) | — |
| 422 | `invalid_request` | body shape: missing key, extra key, bad date, non-number capacity, non-int version (`errors.py:225-242`) | `{"fields", "field_count"}` |
| 429 | `rate_limited` | quota spent (`dependencies.py:254`) | — |
| 404 | `unit_not_found` | unit not in caller's tenant (`units.py:44`, `load_unit_or_404`) | — |
| 403 | `forbidden` | role/path refused (`errors.py:106-118`) | `{"reason"}` |
| 404 | `speaker_contact_not_found` | profile unknown or in another unit | — |
| 409 | `speaker_availability_stale` | `expected_version` ≠ stored version (null ≠ existing row; int ≠ no row), or lost race | — (C9) |
| 422 | the four domain codes below | T1 `validate_availability_statement` | below |

Rows are in evaluation order. `invalid_request` is raised by FastAPI while it resolves the body, **before** the handler runs, so it precedes quota, 404, 403 and 409 (existing behaviour for every body route).

**Domain mapping** (`availability_error`): `code = exc.code.value` (T1 pins these strings = §4.1 codes: `test_error_code_values_match_api_codes`, `tests/unit/test_speaker_availability.py:534`). Fixed message per code; never echo the value (`errors.py:39-46` rule).

| `exc.code` | `exc.field` | `exc.index` | API `details` |
|---|---|---|---|
| `CAPACITY_INVALID` (≤0, >720, not finite, >1 decimal) | `declared_capacity_hours_per_90_days` | None | `{"field": "declared_capacity_hours_per_90_days"}` |
| `PAUSE_INVALID` (before today, after today + 12 months) | `invitations_paused_until` | None | `{"field": "invitations_paused_until"}` |
| `TOO_MANY_WINDOWS` (>20) | `unavailable` | None | `{"field": "unavailable", "limit": 20}` (`MAX_WINDOWS`) |
| `WINDOW_INVALID` (order, span >366, end after today + 18 months, duplicate → later index) | `unavailable` | i | `{"field": "unavailable", "index": i}` |

`index` is the **request** index: `statement_from_request` builds `unavailable` in request order, never sorted. Only the first failure is reported (T1 order: capacity, pause, count, windows).

## 3. Routes and semantics (`speaker_availability.py`)

`GET /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability` → 200 `SpeakerAvailabilityResponse`.
`PATCH` same path, body `SpeakerAvailabilityUpdateRequest` → 200 `SpeakerAvailabilityResponse` (the stored row read back).
Handler params as `list_speaker_contact_channels` (`cba_contact_channels.py:460-472`): `principal: CurrentPrincipal`, `session: DbSession`, `unit_id` / `professional_id: Annotated[uuid.UUID, Path()]`.

Handler order (ADR-0015 quota first; `cba_contact_channels.py:486-493` shape):

1. `charge_quota(session, principal, SPEAKER_CONTACT_READ_RATE_LIMIT)` for GET, `..._WRITE_RATE_LIMIT` for PATCH (shared `speaker_contact.*` buckets).
2. `owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)` → 404 `unit_not_found` / 403.
3. `_roster.get(session, tenant_id=principal.tenant_id, owning_unit_id=owning_unit_id, professional_id=professional_id)`; `None` → `raise _not_found()`. Checked first so T2's FK `IntegrityError` is never reached for an unknown id (T2 module docstring).
4. `stored = _availability.get(session, tenant_id=principal.tenant_id, professional_id=professional_id)`. GET returns `availability_response(professional_id, stored)` here.
5. PATCH only — **stale pre-check:** `body.expected_version != (stored.version if stored else None)` → `raise stale_error()`. Stale wins over a domain-invalid body: re-reading fixes both, and the drop rule (6) needs a current `stored`.
6. `now = utc_now()`; `today = now.date()` — **the UTC date (C1)**. `statement = statement_from_request(body, stored, today)`:
   - capacity `Decimal(str(v))` or `None`; windows `tuple(UnavailableWindow(w.starts_on, w.ends_on) for w in body.unavailable)`, request order;
   - **expired-pause drop rule** (`T1-plan.md:125`): if `body.invitations_paused_until < today` **and** `stored` is not `None` **and** it equals `stored.statement.invitations_paused_until` → use `None`. Any other past date, or a past date with no row → kept, so the validator returns `pause_invalid`.
7. `validate_availability_statement(statement, today)`; `except AvailabilityStatementInvalid as exc: raise availability_error(exc) from exc`.
8. `result = _availability.upsert(session, tenant_id=principal.tenant_id, professional_id=professional_id, statement=statement, source=AvailabilitySource.CONNECTOR, actor_user_id=principal.user_id, expected_version=body.expected_version, now=now)`. `except StaleSpeakerAvailabilityError` (lost race after step 5; T2 re-checks under `SELECT … FOR UPDATE`) → `raise stale_error() from exc`.
9. `session.commit()` (`get_session` rolls back on exit, `dependencies.py:63-77`; precedent `matching_weights.py:447`); return `availability_response(professional_id, result)`.

Semantics: `updated_source = 'connector'` on every accepted PATCH; new windows get `created_source = 'connector'`; unchanged `(starts_on, ends_on)` keep their original source (T2 `_replace_windows`). **Full replace:** an omitted window is deleted; `null` pause/capacity clears; `unavailable: []` keeps `stated: true` (said free). The version bumps on every accepted PATCH, even an identical one (T2 §3 step 6). Past windows are accepted. GET does not hide a past pause; T5 renders it as expired.

## 4. Authz

Roles `{admin, coordinator}` via the imported `_authorize_speaker_contacts` — one authorizer for all §13 routes (the `cba_contact_channels.py:89-96` argument). A profile in another unit or tenant → 404 `speaker_contact_not_found`, identical to unknown; an unknown or other-tenant unit → 404 `unit_not_found`. No availability row is read or written before step 3 passes. `_authorize_speaker_contacts` is already in the matrix's authorizer registry (`test_policy_matrix.py:8532`): no edit there.

`test_policy_matrix.py`: copy the `speaker_contact.channel.create` row (`:2073-2084`) twice:
`key="speaker_contact.availability.read", method="GET"` and `key="speaker_contact.availability.update", method="PATCH"`, both `path="/v1/units/{unit_id}/speaker-contacts/{professional_id}/availability"`, `module="smartmatch_api.routers.speaker_availability"`, `authorizer="_authorize_speaker_contacts"`, `roles_constant="_SPEAKER_CONTACT_ROLES"`, `authorizer_module="smartmatch_api.routers.cba_contacts"`, `required_roles=frozenset({"admin", "coordinator"})`, `resource_type="org_unit"`, `unit_scoped=True`.
Cells: `MATRIX["speaker_contact.availability.read"] = MATRIX["speaker_contact.read"]`, `MATRIX["speaker_contact.availability.update"] = MATRIX["speaker_contact.update"]` — same function, so disagreement must be unrepresentable (the `:8355-8366` precedent). `test_every_authenticated_route_has_a_matrix_row` (`:8994`) fails until both rows exist; `test_the_route_calls_the_authorizer_the_matrix_names` (`:9081`) checks each handler calls `_authorize_speaker_contacts` by that name.

`test_route_roles.py`: `_SPEAKER_CONTACT = frozenset({"admin", "coordinator"})` (a literal, its own object — `test_every_job_route_shares_the_same_role_set_in_the_ledger` compares by `is`); ledger rows `("GET", path): _SPEAKER_CONTACT`, `("PATCH", path): _SPEAKER_CONTACT`; `test_speaker_contact_roles_matches_the_live_constant` (`cba_contacts._SPEAKER_CONTACT_ROLES == _SPEAKER_CONTACT`); both keys added to the exact set at `:203-212`.

## 5. `api.ts` adapter

```ts
export type SpeakerAvailabilitySource = "speaker" | "connector";
export interface SpeakerAvailabilityWindow { starts_on: string; ends_on: string } // YYYY-MM-DD
export interface SpeakerAvailabilityWindowView extends SpeakerAvailabilityWindow {
  source: SpeakerAvailabilitySource;
}
export interface SpeakerAvailability {
  professional_id: string;
  stated: boolean;
  version: number | null;
  invitations_paused_until: string | null;
  declared_capacity_hours_per_90_days: number | null;
  unavailable: SpeakerAvailabilityWindowView[];
  updated_source: SpeakerAvailabilitySource | null;
  updated_at: string | null;
}
export interface SpeakerAvailabilityUpdatePayload {
  expected_version: number | null; // required, not optional: echo `version` from the read
  invitations_paused_until: string | null;
  declared_capacity_hours_per_90_days: number | null;
  unavailable: SpeakerAvailabilityWindow[];
}
export type SpeakerAvailabilityErrorCode =
  | "speaker_availability_stale" | "speaker_availability_window_invalid"
  | "speaker_availability_too_many_windows" | "speaker_availability_pause_invalid"
  | "speaker_availability_capacity_invalid" | "speaker_contact_not_found";
export async function fetchSpeakerAvailability(unitId: string, professionalId: string): Promise<SpeakerAvailability>;
export async function updateSpeakerAvailability(unitId: string, professionalId: string, payload: SpeakerAvailabilityUpdatePayload): Promise<SpeakerAvailability>;
```

Both call `requestJson<SpeakerAvailability>(path, init, { authenticated: true })` (`:484`): GET with `{ method: "GET" }`, PATCH with `{ method: "PATCH", body: JSON.stringify(payload) }` (precedent `:4651`). Both ids through `encodeURIComponent`; no normalizing, no default, no retry. Errors surface as `ApiRequestError` (`:330`) with `status`, `code` and `details` intact. JSDoc cites the §2 table. Types are generic so T6b-2's `/v1/me/availability` adapter reuses them.

## 6. TDD tests

CI: python job `pytest tests/ -m "not e2e"` with Postgres (`verify.yml:51-53`, `:117`); web job `npm run test:components` = `vitest run` over `src/**/*.test.tsx` only (`vitest.config.ts:36`). `tests/*.test.ts` (`node --test`) is **not** in CI, so the adapter test is a `.test.tsx`. Locally: one file at a time.

**Unit — `tests/unit/test_speaker_availability_models.py`** (no DB)
1. `test_request_requires_all_four_keys` (parametrized) · `test_request_forbids_extra_keys` (`professional_id`, `updated_source`, `version`)
2. `test_capacity_float_parses_via_str` (`24.05` → `Decimal("24.05")`) · `test_capacity_int_becomes_decimal` · `test_capacity_bool_and_string_rejected` · `test_expected_version_bool_and_string_rejected` (`true`, `"3"`)
3. `test_expired_pause_equal_to_stored_is_dropped` · `test_expired_pause_different_from_stored_is_kept` · `test_expired_pause_without_row_is_kept` · `test_today_and_future_pause_never_dropped`
4. `test_windows_keep_request_order`
5. `test_availability_error_maps_each_code` (4 cases: status 422, code, exact `details`) · `test_error_message_never_contains_the_value` · `test_stale_error_is_409_without_details`
6. `test_response_for_no_row_is_not_stated` · `test_response_maps_sources_and_capacity_as_float` (build `StoredSpeakerAvailability` / `StoredWindow` directly)

**Contract — `tests/contract/test_speaker_availability_api.py`** (`pytestmark = pytest.mark.integration`; `engine` fixture skips when `SELECT 1 FROM speaker_availability LIMIT 1` fails; `ctx` shape of `test_contact_lifecycle_api.py:75-300`, token and subject built at runtime). **Teardown** deletes `speaker_availability_window`, then `speaker_availability`, ahead of `speaker_profile` and `user_account` (their `created_by` / `updated_by` FKs are RESTRICT). Date tests pin the clock with `monkeypatch.setattr("smartmatch_api.routers.speaker_availability.utc_now", ...)` so a run across UTC midnight cannot flake.
1. `test_get_unstated_is_stated_false_with_null_version`
2. `test_first_patch_with_null_expected_version_creates_version_1`
3. `test_patch_sets_connector_source_on_row_and_new_windows`
4. `test_patch_is_full_replace` (omitted window deleted, unchanged window keeps source) · `test_empty_windows_stays_stated_true` · `test_null_pause_and_capacity_clear`
5. `test_stale_version_is_409_and_writes_nothing` · `test_null_expected_version_on_existing_row_is_409` · `test_version_on_missing_row_is_409` · `test_stale_wins_over_domain_invalid_body`
6. `test_capacity_invalid` (`0`, `-1`, `720.1`, `24.05`) · `test_capacity_bounds_accepted` (`0.1`, `720`) · `test_capacity_is_a_json_number_in_response`
7. `test_pause_yesterday_422` · `test_pause_today_ok` · `test_pause_at_12_months_ok_and_day_after_422` · `test_today_is_the_utc_date` (clock `2026-10-06T03:00Z`, i.e. 5 Oct in Pacific: pause `2026-10-05` → 422 `pause_invalid`; `2026-10-06` → 200)
8. `test_expired_pause_resent_unchanged_is_stored_null` (past date set by SQL) · `test_expired_pause_changed_is_422`
9. `test_21_windows_too_many_20_ok` · `test_window_invalid_reports_request_index` (order, span 367, horizon, duplicate → later index)
10. `test_unknown_professional_404` · `test_sibling_unit_profile_404_and_nothing_written` · `test_other_tenant_unit_404_unit_not_found` (GET and PATCH each)
11. `test_volunteer_and_student_get_403` (HTTP smoke; the matrix owns the rectangle) · `test_invalid_body_is_invalid_request`

**Authz** — `test_policy_matrix.py` rows (§4) run through every existing shape test. `test_route_roles.py`: `test_speaker_contact_roles_matches_the_live_constant`; exact-set test gains both rows.

**OpenAPI — `tests/unit/test_speaker_availability_openapi_contract.py`** (shape of `test_speaker_pipeline_openapi_contract.py`): both methods published on the path; request `required` = all 4 keys and `additionalProperties: false`; no `professional_id` in the request; `expected_version` is `anyOf [integer, null]`; response `version` and capacity nullable, capacity `anyOf` holds `number`.

**Frontend** — `tests/unit/test_frontend_speaker_availability_contract.py` (source scan, `_code_only` as `test_frontend_invitation_compose_contract.py:53`): both functions and the URL exist; `expected_version: number | null;` with no `?`; no numeric capacity literal.
`src/lib/speakerAvailabilityApi.test.tsx` (first `.test.tsx` under `src/lib`; Vitest, `vi.stubGlobal("fetch", ...)`; token set with `storeSmartmatchBearerToken(runtime-built value)` and cleared after): GET URL encoded + `Authorization`; PATCH method and exact body; 409 → `ApiRequestError.code === "speaker_availability_stale"`; 422 keeps `details.index`.

## 7. Commit milestones

0. `chore: merge origin/feat/b26-t2 into feat/b26-t3` — stacked base (T1 + T2).
1. `test: failing T3 availability API, authz and adapter tests` — all §6 files, red.
2. `feat: speaker availability request/response models and error mapping` — models file; unit file green.
3. `feat: connector availability GET/PATCH routes` — router + `main.py`; authz green locally, contract green in CI.
4. `chore: regenerate OpenAPI for speaker availability` — `make openapi VENV=$VENV`; OpenAPI test green.
5. `feat: speaker availability api.ts adapter` — `api.ts`; frontend contract + Vitest green (`npx vitest run --pool=threads src/lib/speakerAvailabilityApi.test.tsx` from a Linux-FS copy).

PR body: first line **"Merge #210 and #212 first."**; ends with the Claude Code line.

## 8. Contradictions

| # | Issue | Options | Status |
|---|---|---|---|
| C1 | "today" has no zone. UTC rejects a Connector's local-today pause after 17:00 Pacific. | (a) UTC date; (b) pilot zone setting (none exists); (c) floor `utc_today − 1`. | **Decided (orchestrator): (a) UTC** — `utc_now().date()`, same as T4 and T8's UTC run date. Pinned by contract test 7 `test_today_is_the_utc_date`. |
| C2 | `main` §4.1 says "Order, span or horizon" and "≤ 0 or > 720"; `origin/feat/b26-t2` (from T1) already rewrites both (duplicate; not finite; >1 decimal). | Follow T1's text. | Decided: T1 text; lands with #210/#212. |
| C3 | Parent §4 says `test_policy_matrix.py` "derives" the row. It derives the **route set** (`test_every_authenticated_route_has_a_matrix_row`, `:8994`), but `OPERATIONS` (`:1001`) and `MATRIX` (`:2728`) are hand-written, and `test_route_roles.py:201-212` pins an exact set. | Add rows by hand (§4). | Decided. |
| C4 | `matching_weights` makes `expected_version` optional (null = blind write, `:252-262`); T2 C1 makes null mean "expect no row" (built: `upsert` compares `expected_version != stored_version`). | Required-but-nullable in the request, `StrictInt`. | Decided (T2 C1). |
| C5 | Stale and domain-invalid in one PATCH: which answers? | 409 first / 422 first. | Decided: 409 first (§3 step 5). Body-shape 422 still precedes both (FastAPI). |
| C6 | Capacity as JSON number vs string. | Number / string. | Decided: number in, `Decimal(str(v))`; number out. |
| C7 | `AvailabilitySource` home. | Persistence / domain. | Resolved by T2 as built: `smartmatch_persistence.speaker_availability`. |
| C8 | Profile deleted between step 3 and the upsert → FK `IntegrityError` → 500. | Map to 404 / leave. | Later: leave (CASCADE race, pilot scale). |
| C9 | The draft put `{"current_version"}` in the 409. T2's `StaleSpeakerAvailabilityError` carries no version, so the race path would need a re-read; and a version without the data invites a blind retry that overwrites the other writer. | Re-read for it / drop it. | Decided: **no `details`** on 409 (precedent `matching_weights_stale`); the client re-reads with GET (T5 stale state). |
| C10 | Pydantic lax `date` accepts a JSON integer as a Unix timestamp (`0` → 1970-01-01). | Strict dates / leave. | Later: leave. The adapter sends strings; a 1970 pause fails `pause_invalid`, a 1970 window is a harmless past window. |

---

**Next action (under two minutes):** `git fetch origin && git merge origin/feat/b26-t2`, then create `tests/unit/test_speaker_availability_models.py` with tests 1–2.
