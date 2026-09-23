# B26 T3 — Connector availability `GET`/`PATCH`, OpenAPI, `api.ts` adapter

**Next action:** rebase `feat/b26-t3` onto `origin/feat/b26-t2` (T1 + T2 code), then write `tests/unit/test_speaker_availability_models.py` (§6) red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2, §4 intro, §4.1, §6 (adapter only), §7 row 3, §8 T3.
Inputs: T1 code `origin/feat/b26-t1:python/smartmatch_domain/smartmatch_domain/speaker_availability.py` and its plan; T2 plan `origin/feat/b26-t2:docs/plans/b26-tracks/T2-plan.md` §3 (no T2 code on the branch at 2026-09-23).
**Branch base:** T3 is implemented on top of T2's branch until T2 merges, then rebased onto `main`. T2 needs T1 underneath it; if T2 is not yet on T1, base on a merge of both.

## 1. Files

| Path | Change |
|---|---|
| `services/api/smartmatch_api/routers/speaker_availability_models.py` | **New.** Request/response models (§2), `statement_from_request`, `availability_error`, `availability_response`. No router. Shared with T6b-2's `/v1/me/availability` (precedent `manual_events_models.py`). |
| `services/api/smartmatch_api/routers/speaker_availability.py` | **New.** `router = APIRouter(prefix="/v1/units", tags=["speaker-contacts"])`; the two routes (§3). |
| `services/api/smartmatch_api/main.py` | Import; add `(speaker_availability.router, Capability.SPEAKER_CONTACT_MANAGEMENT)` right after `cba_contacts.router` (`:444`), with a comment: roster data, sends nothing, so not `CONSENTED_OUTREACH` (same argument as `student_speaker_feedback.connector_router`, `:551`). |
| `contracts/openapi/smartmatch.json` | Regenerated: `make openapi VENV=$VENV` (`Makefile:356-359`); CI runs `--check` (`.github/workflows/verify.yml:127`). |
| `apps/web/legacy-frontend/src/lib/api.ts` | Types + 2 functions (§5), placed after `fetchSpeakerContactChannels` (`:4042-4052`). |
| `tests/authz/test_policy_matrix.py` | 2 `Operation` rows after `speaker_contact.channel.transition` (`:2100-2114`); 2 `MATRIX` aliases beside `:8366`. |
| `tests/authz/test_route_roles.py` | 2 ledger rows, `_SPEAKER_CONTACT` literal, 1 live-constant test, exact-set test (`:201-212`) extended. |
| Tests (new) | `tests/contract/test_speaker_availability_api.py`, `tests/unit/test_speaker_availability_models.py`, `tests/unit/test_speaker_availability_openapi_contract.py`, `tests/unit/test_frontend_speaker_availability_contract.py`, `apps/web/legacy-frontend/src/lib/speakerAvailabilityApi.test.tsx`. |

Reused, not edited: `cba_contacts._authorize_speaker_contacts` (`cba_contacts.py:624-663`, roles `_SPEAKER_CONTACT_ROLES` `:252`), `SPEAKER_CONTACT_READ_RATE_LIMIT`/`SPEAKER_CONTACT_WRITE_RATE_LIMIT` (`:258-263`), `SpeakerContactRepository.get` (`smartmatch_persistence/cba_contacts.py:561`), `charge_quota` (`dependencies.py:286`), `ApiError` (`errors.py:48`), `utc_now` (`utils.py:10`). T2's `SpeakerAvailabilityRepository`, `AvailabilitySource`, `StaleSpeakerAvailabilityError`, `StoredSpeakerAvailability`.

## 2. Models (`speaker_availability_models.py`)

Decimal convention: **JSON number**. No route exposes a `Decimal` today (`grep Decimal services/api` is empty); `matching_weights.py:180-247` uses `float`; parent §4.1 shows `24.0`. The request takes `StrictFloat | StrictInt` (a bool or string is `invalid_request`), converted with `Decimal(str(v))` (T1 hand-off) so `24.05` stays `24.05` and fails the 1-decimal rule. The response is `float(stored_decimal)`.

```python
class AvailabilityWindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_on: date
    ends_on: date


class SpeakerAvailabilityUpdateRequest(BaseModel):
    """Full replace. Every key is required; null clears. No subject field (MM-A01)."""

    model_config = ConfigDict(extra="forbid")
    expected_version: int | None  # required; null = "I read stated: false" (T2 C1)
    invitations_paused_until: date | None
    declared_capacity_hours_per_90_days: StrictFloat | StrictInt | None
    unavailable: list[AvailabilityWindowInput]  # no max_length: the domain says too_many


class AvailabilityWindowView(BaseModel):
    starts_on: date
    ends_on: date
    source: Literal["speaker", "connector"]  # StoredWindow.created_source


class SpeakerAvailabilityResponse(BaseModel):
    professional_id: uuid.UUID
    stated: bool  # false = no row; UI says "Not stated", never "Available"
    version: int | None  # null exactly when stated is false
    invitations_paused_until: date | None  # stored value, even if already past
    declared_capacity_hours_per_90_days: float | None
    unavailable: list[AvailabilityWindowView]  # T2 order: (starts_on, ends_on)
    updated_source: Literal["speaker", "connector"] | None
    updated_at: datetime | None
```

Not stated → `stated=false`, `version`/pause/capacity/`updated_source`/`updated_at` null, `unavailable=[]`. `updated_by_user_id` is **not** returned (§4.1 does not list it). T8 later adds `load`, an additive field.

**Error codes, both routes.** Envelope `{"error": {"code", "message", "details"?}}`.

| Status | Code | When | `details` |
|---|---|---|---|
| 401 | `unauthenticated` | no/invalid bearer (`dependencies.py:184`) | — |
| 429 | `rate_limited` | quota spent (`dependencies.py:254`) | — |
| 404 | `unit_not_found` | unit not in caller's tenant (`units.py:44`) | — |
| 403 | `forbidden` | role/path refused (`errors.py` authz handler) | `{"reason"}` |
| 404 | `speaker_contact_not_found` | profile unknown or in another unit | — |
| 422 | `invalid_request` | body shape: missing key, extra key, bad date, non-number capacity | `{"fields", "field_count"}` |
| 409 | `speaker_availability_stale` | `expected_version` ≠ stored version (null ≠ existing row; int ≠ no row) | `{"current_version": int \| null}` |
| 422 | the four domain codes below | T1 `validate_availability_statement` | below |

**Domain mapping** (`availability_error(exc: AvailabilityStatementInvalid) -> ApiError`): `code = exc.code.value` (T1 pins these strings = §4.1 codes, T1 test 37). Fixed message per code; never echo the value (`errors.py:40-46` rule).

| `exc.code` | `exc.field` | `exc.index` | API `details` |
|---|---|---|---|
| `CAPACITY_INVALID` (≤0, >720, not finite, >1 decimal) | `declared_capacity_hours_per_90_days` | None | `{"field": "declared_capacity_hours_per_90_days"}` |
| `PAUSE_INVALID` (past, >12 months) | `invitations_paused_until` | None | `{"field": "invitations_paused_until"}` |
| `TOO_MANY_WINDOWS` (>20) | `unavailable` | None | `{"field": "unavailable", "limit": 20}` |
| `WINDOW_INVALID` (order, span >366, horizon >18 months, duplicate → later index) | `unavailable` | i | `{"field": "unavailable", "index": i}` |

`index` is the **request** index: `statement_from_request` builds `unavailable` in request order, never sorted. Only the first failure is reported (T1 order: capacity, pause, count, windows).

## 3. Routes and semantics (`speaker_availability.py`)

`GET /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability` → 200 `SpeakerAvailabilityResponse`.
`PATCH` same path, body `SpeakerAvailabilityUpdateRequest` → 200 `SpeakerAvailabilityResponse` (the stored row read back).

Handler order (ADR-0015 quota first; `cba_contact_channels.py:466-490` shape):

1. `charge_quota` — read limit for GET, write limit for PATCH (shared `speaker_contact.*` buckets).
2. `_authorize_speaker_contacts(session, principal, unit_id)` → 404 `unit_not_found` / 403.
3. `SpeakerContactRepository.get(tenant, owning_unit_id, professional_id)`; `None` → `cba_contacts._not_found()` (`:957`). Checked first so T2's FK `IntegrityError` is never reached for an unknown id.
4. `stored = SpeakerAvailabilityRepository.get(...)`. GET returns `availability_response(professional_id, stored)` here.
5. PATCH only — **stale pre-check:** `body.expected_version != (stored.version if stored else None)` → 409. Stale wins over an invalid body: re-reading fixes both, and the drop rule (6) needs a current `stored`.
6. `today = utc_now().date()`; `statement = statement_from_request(body, stored, today)`:
   - capacity `Decimal(str(v))` or `None`; windows as `UnavailableWindow`, request order;
   - **expired-pause drop rule** (T1 hand-off): if `body.invitations_paused_until < today` **and** `stored` exists **and** it equals `stored.statement.invitations_paused_until` → use `None`. Any other past date, or a past date with no row → kept, so the validator returns `pause_invalid`.
7. `validate_availability_statement(statement, today)` → 422 via `availability_error`.
8. `upsert(..., statement, source=AvailabilitySource.CONNECTOR, actor_user_id=principal.user_id, expected_version=body.expected_version, now=utc_now())`. `StaleSpeakerAvailabilityError` (lost race after step 5) → the same 409.
9. `session.commit()` (`get_session` rolls back otherwise, `matching_weights.py:447`); return the upsert's read-back.

Semantics: `updated_source = 'connector'` on every accepted PATCH; new windows get `source = 'connector'`; unchanged `(starts_on, ends_on)` keep their original source (T2 §3 step 5). **Full replace:** an omitted window is deleted; `null` pause/capacity clears; `unavailable: []` keeps `stated: true` (said free). The version bumps on every accepted PATCH, even an identical one (T2 step 6). Past windows are accepted. GET does not hide a past pause; T5 renders it as expired.

## 4. Authz

Roles `{admin, coordinator}` via the imported `_authorize_speaker_contacts` — one authorizer for all §13 routes (the `cba_contact_channels.py:89-97` argument). A profile in another unit or tenant → 404 `speaker_contact_not_found`, identical to unknown; an unknown or other-tenant unit → 404 `unit_not_found`. No row is read or written before step 3 passes.

`test_policy_matrix.py`: `Operation(key="speaker_contact.availability.read", method="GET", ...)` and `key="speaker_contact.availability.update", method="PATCH"`, both `module="smartmatch_api.routers.speaker_availability"`, `authorizer="_authorize_speaker_contacts"`, `roles_constant="_SPEAKER_CONTACT_ROLES"`, `authorizer_module="smartmatch_api.routers.cba_contacts"`, `required_roles={"admin","coordinator"}`, `resource_type="org_unit"`, `unit_scoped=True` (copy `:2073-2084`). Cells: `MATRIX[...read] = MATRIX["speaker_contact.read"]`, `MATRIX[...update] = MATRIX["speaker_contact.update"]` — same function, so disagreement must be unrepresentable (the `:8366` precedent).

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

Both call `requestJson(..., { authenticated: true })` (`:484`), both ids through `encodeURIComponent`, PATCH body `JSON.stringify(payload)` with no normalizing, no default, no retry. Errors surface as `ApiRequestError` (`:330`) with `code` and `details` intact. JSDoc cites the §2 table. Types are generic so T6b-2's `/v1/me/availability` adapter reuses them.

## 6. TDD tests

CI: python job `pytest tests/ -m "not e2e"` with Postgres (`verify.yml:52`, `:117`); web job `npm run test:components` = Vitest `src/**/*.test.tsx` only (`vitest.config.ts:36`). `tests/*.test.ts` (`node --test`) is **not** in CI, so the adapter test is a `.test.tsx`. Locally: one file at a time.

**Unit — `tests/unit/test_speaker_availability_models.py`** (no DB)
1. `test_request_requires_all_four_keys` (parametrized) · `test_request_forbids_extra_keys` (`professional_id`, `updated_source`, `version`)
2. `test_capacity_float_parses_via_str` (`24.05` → `Decimal("24.05")`) · `test_capacity_int_becomes_decimal` · `test_capacity_bool_and_string_rejected`
3. `test_expired_pause_equal_to_stored_is_dropped` · `test_expired_pause_different_from_stored_is_kept` · `test_expired_pause_without_row_is_kept` · `test_today_and_future_pause_never_dropped`
4. `test_windows_keep_request_order`
5. `test_availability_error_maps_each_code` (4 cases: status 422, code, exact `details`) · `test_error_message_never_contains_the_value`
6. `test_response_for_no_row_is_not_stated` · `test_response_maps_sources_and_capacity_as_float`

**Contract — `tests/contract/test_speaker_availability_api.py`** (`pytest.mark.integration`; skip when `SELECT 1 FROM speaker_availability` fails; `_Context` shape of `test_contact_lifecycle_api.py:47-260`)
1. `test_get_unstated_is_stated_false_with_null_version`
2. `test_first_patch_with_null_expected_version_creates_version_1`
3. `test_patch_sets_connector_source_on_row_and_new_windows`
4. `test_patch_is_full_replace` (omitted window deleted, unchanged window keeps source) · `test_empty_windows_stays_stated_true` · `test_null_pause_and_capacity_clear`
5. `test_stale_version_is_409_and_writes_nothing` · `test_null_expected_version_on_existing_row_is_409` · `test_version_on_missing_row_is_409` · `test_stale_wins_over_invalid_body`
6. `test_capacity_invalid` (`0`, `-1`, `720.1`, `24.05`) · `test_capacity_bounds_accepted` (`0.1`, `720`) · `test_capacity_is_a_json_number_in_response`
7. `test_pause_yesterday_422` · `test_pause_today_ok` · `test_pause_at_12_months_ok_and_day_after_422`
8. `test_expired_pause_resent_unchanged_is_stored_null` (past date set by SQL) · `test_expired_pause_changed_is_422`
9. `test_21_windows_too_many_20_ok` · `test_window_invalid_reports_request_index` (order, span 367, horizon, duplicate → later index)
10. `test_unknown_professional_404` · `test_sibling_unit_profile_404_and_nothing_written` · `test_other_tenant_unit_404_unit_not_found` (GET and PATCH each)
11. `test_volunteer_and_student_get_403` (HTTP smoke; the matrix owns the rectangle) · `test_invalid_body_is_invalid_request`

**Authz** — `test_policy_matrix.py` rows (§4) run through all existing shape tests. `test_route_roles.py`: `test_speaker_contact_roles_matches_the_live_constant`; exact-set test gains both rows.

**OpenAPI — `tests/unit/test_speaker_availability_openapi_contract.py`**: both methods published; request `required` = all 4 keys and `additionalProperties: false`; no `professional_id` in the request; response `version` and capacity nullable, capacity a number.

**Frontend** — `tests/unit/test_frontend_speaker_availability_contract.py` (source scan, `_code_only` as `test_frontend_invitation_compose_contract.py`): both functions and the URL exist; `expected_version: number | null;` with no `?`; no numeric capacity literal. `src/lib/speakerAvailabilityApi.test.tsx` (Vitest, `vi.stubGlobal("fetch")`): GET URL encoded + `Authorization`; PATCH method and exact body; 409 → `ApiRequestError.code === "speaker_availability_stale"`; 422 keeps `details.index`.

## 7. Commit milestones

1. `test: failing T3 availability API, authz and adapter tests` — all §6 files, red.
2. `feat: speaker availability request/response models and error mapping` — models file; unit file green.
3. `feat: connector availability GET/PATCH routes` — router + `main.py`; authz green locally, contract green in CI.
4. `chore: regenerate OpenAPI for speaker availability` — `make openapi VENV=$VENV`; OpenAPI test green.
5. `feat: speaker availability api.ts adapter` — `api.ts`; frontend contract + Vitest green (`vitest run --pool=threads src/lib/speakerAvailabilityApi.test.tsx`).

## 8. Contradictions

| # | Issue | Options | Status |
|---|---|---|---|
| C1 | **"today" has no zone.** `utc_now().date()` rejects a Connector's local "today" pause after 17:00 Pacific. T1 left the zone to T4; T8 uses the UTC run date. | (a) UTC date everywhere, T4 matches; (b) a fixed pilot zone setting (none exists); (c) accept `utc_today − 1` as the pause floor. | **Must decide.** Recommend (a), same value in T4. |
| C2 | `main` §4.1 still says "Order, span or horizon" and "≤ 0 or > 720"; `origin/feat/b26-t1` rewrites both (duplicate; not finite; >1 decimal). | Follow T1's text. | Decided: T1 text; lands with T1's PR. |
| C3 | Parent §4 says `test_policy_matrix.py` "derives" the row. It does not: `OPERATIONS` (`:1001`) and `MATRIX` (`:2728`) are hand-written, and `test_route_roles.py:201-212` pins an exact route set. | Add rows by hand (§4, §6). | Decided. |
| C4 | `matching_weights` makes `expected_version` optional (null = blind write, `:252-262`); T2 C1 makes null mean "expect no row". | Required-but-nullable in the request. | Decided (T2 C1). |
| C5 | Stale and invalid in one PATCH: which answers? | 409 first (pre-check) / 422 first. | Decided: 409 first (§3 step 5). |
| C6 | Capacity as JSON number vs string. | Number (API convention) / string (exact decimal). | Decided: number in, `Decimal(str(v))`; number out. |
| C7 | T2 has no code yet; `AvailabilitySource` lives in persistence (T2 C7). | Start at milestone 1 now; milestones 2+ wait for T2 milestone 3. | Later: import from wherever T2 lands it. |
| C8 | Profile deleted between step 3 and the upsert → FK `IntegrityError` → 500. | Map to 404 / leave. | Later: leave (CASCADE race, pilot scale). |

---

**Next action (under two minutes):** `git fetch origin && git rebase origin/feat/b26-t2`, then create `tests/unit/test_speaker_availability_models.py` with tests 1–2.
