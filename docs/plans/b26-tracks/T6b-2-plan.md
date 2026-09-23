# B26 T6b-2 — the Speaker's own routes (`/v1/me/availability`, `/v1/me/invitations`, `/v1/me/engagements`)

**Next action:** get an orchestrator ruling on C2 (portal answers' `response_channel`) **before T6b-1 milestone 1 lands `0039`**. Then wait for the §0 start gate.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2 (privacy, MM-A01), §4 intro, §4.1 (body and response reused), §4.3, §7 row 7, §8 T6b-2.
Inputs: T3 plan `origin/feat/b26-t3` @ `f8c12bfb`; T6b-1 plan `origin/feat/b26-t6b-1` @ `edd9f464` (rev 3); T8a plan `origin/feat/b26-t8a` @ `09ca1455`; T6a code `origin/feat/b26-t6a` @ `6e1857fb`.
Line numbers are `main` @ `1909278f` unless a track is named.

## 0. Branch, stack and start gate

**Stack.** T6b-2 writes no migration, but it reads `0039` (T6b-1: `speaker_profile.account_user_id`) and `0040` (T8a: `pipeline_record.cancelled_at`), and it calls T3's availability helpers. So:

1. On `feat/b26-t6b-2` (this plan commit, from `origin/main`): `git merge origin/feat/b26-t8a`. T8a already stacks T6b-1 → T2 → T1, so this one merge brings `0038`–`0040`. A merge, not a rebase, so the pushed plan commit stays (T3's pattern).
2. `git merge origin/feat/b26-t3`. T3 also stacks on T2, so the common base is T2. Expected textual conflicts, all resolved as a union:
   - `main.py` (`CAPABILITY_SCOPED_ROUTERS` rows and the router import list)
   - `tests/authz/test_policy_matrix.py` (`OPERATIONS`, `MATRIX`, the dispatch tuple)
   - `tests/authz/test_route_roles.py` (ledger rows, exact set)
   - `apps/web/legacy-frontend/src/lib/api.ts` (adjacent adapters)
   - `contracts/openapi/smartmatch.json`: **never hand-merge**. Take either side, then `make openapi VENV=$VENV`.
3. The PR targets `main`. Body line 1: **"Merge #210, #212, then the T6b-1, T8a and T3 PRs first."** After they land, merge `main` into `feat/b26-t6b-2` so the diff is T6b-2 only.
4. Migration head stays `0040_speaker_booking_cancellation` (or `0041` if T4 merged first). T6b-2 touches no head pin.

**Start gate** (implementation, not this plan). All pushed on their branches:

| Track | Needed from it | Milestone |
|---|---|---|
| T6b-1 | `0039`, `speaker` in `role_presentation`, `Capability.SPEAKER_PORTAL`, `speaker_at_owning_unit` matrix shape, `SpeakerPortalRepository` | 1, 2, 3, 5 |
| T8a | `0040` + mirror, `PipelineRecordRow.cancelled_at` | 2, 3 |
| T3 | `speaker_availability_models.py` incl. the write helper (C1), T3's router | 2, 3 |

## 1. Files

| Path | Change |
|---|---|
| `services/api/smartmatch_api/routers/speaker_self.py` | **New.** `router = APIRouter(prefix="/v1/me", tags=["speaker-portal"])`, a bare module-level assignment (`test_policy_matrix.py:8924` guard). `_SPEAKER_SELF_ROLES: Final = frozenset({"speaker"})`; `SPEAKER_SELF_READ_RATE_LIMIT` (`speaker_self.read`, 120/min) and `SPEAKER_SELF_WRITE_RATE_LIMIT` (`speaker_self.write`, 30/min), the `cba_contacts.py:258-263` numbers; `MAX_ROWS = 200` (the G3 cap, `cba_contacts.py:265-272`); `_authorize_speaker_self` (§3.1); the 5 handlers (§2); pure view builders `engagement_state`, `invitation_view`, `engagement_view`. |
| `services/api/smartmatch_api/main.py` | Import `speaker_self`; add `(speaker_self.router, Capability.SPEAKER_PORTAL)` to `CAPABILITY_SCOPED_ROUTERS` (`:338`) right after T6b-1's three `SPEAKER_PORTAL` rows. Comment: the Speaker's own reads and writes, off with the rest of the portal. |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_portal.py` (T6b-1's) | `BoundSpeakerProfile` (frozen: `professional_id`, `owning_unit_id`, `owning_unit_path: str`) and `SpeakerPortalRepository.find_bound_profile(session, *, tenant_id, account_user_id) -> BoundSpeakerProfile \| None`: `speaker_profile JOIN org_unit` on `(tenant_id, owning_unit_id)`, `WHERE speaker_profile.tenant_id = :tenant AND account_user_id = :login`. At most one row (`uq_speaker_profile_account`). No lock. |
| `python/smartmatch_persistence/smartmatch_persistence/cba_invitations.py` | `SpeakerInvitationRow` (frozen; only the fields §2.2 renders, the `_to_invitation` docstring rule `:585-592`). `InvitationRepository.list_for_professional(session, *, tenant_id, professional_id, limit)` and `get_for_professional(session, *, tenant_id, professional_id, invitation_id)`: `cba_invitation JOIN cba_invitation_batch` on `(tenant_id, batch_id)`, `WHERE tenant_id, professional_id, status = 'dispatched'`; list ordered `dispatched_at DESC, id DESC`, `LIMIT :limit`. If T4's `speaker_request_id` exists on the base: `LEFT JOIN event` on `(tenant_id, speaker_request_id)` for `resolved_date`, `time_zone` (C3). |
| `python/smartmatch_persistence/smartmatch_persistence/pipeline.py` | `SpeakerEngagementRow` (frozen) and `PipelineRepository.list_engagements_for_speaker(session, *, tenant_id, professional_id, today, when, limit)` (§2.4). `list_confirmed_speakers` is **not** reused: T8a C1 makes it drop cancelled rows, and the Speaker must see them. |
| `python/smartmatch_domain/smartmatch_domain/product_scope.py` | `Capability.SPEAKER_PORTAL` docstring gains: "also mounts the Speaker's own `/v1/me/*` routes (T6b-2)". |
| `apps/web/legacy-frontend/src/lib/api.ts` | 5 adapters and their types (§6), placed after T3's `updateSpeakerAvailability`. |
| `docs/product/cba-capability-policy.md` | T6b-1's `SPEAKER_PORTAL` row gains the 5 routes. |
| Under C2 = (b) only | `cba_invitations.py:294` `channel` description and `api.ts:3091` JSDoc gain `speaker_portal`. |
| Tests | §7. |

**Reused, not edited:** domain `record_response` (`smartmatch_domain/cba_invitations.py:357`), `InvitationRepository.record_response` (`smartmatch_persistence/cba_invitations.py:518`), `_speaker_response` (`routers/cba_invitations.py:525`), `charge_quota` (`dependencies.py:286`), `assert_allowed`, `ApiError` (`errors.py:49`), `utc_now` (`utils.py:10`), T3's `SpeakerAvailabilityUpdateRequest`, `SpeakerAvailabilityResponse`, `statement_from_request`, `availability_response`, `stale_error` and the write helper (C1).

## 2. Contracts

Envelope `{"error": {"code", "message", "details"?}}`. **No route takes a subject:** the only path parameter is `invitation_id`; the only query parameter is `when`. Every body model is `extra="forbid"`.

### 2.1 Shared refusals (all 5 routes, in evaluation order)

| Status | Code | When |
|---|---|---|
| 401 | `unauthenticated` | No or bad bearer (`dependencies.py:182-202`) |
| 422 | `invalid_request` | Body or query shape. FastAPI raises it before the handler, so before quota. |
| 429 | `rate_limited` | Quota spent. Charged first (ADR-0015), so an unlinked caller pays too. |
| 404 | `speaker_profile_not_linked` | No `speaker_profile` has `account_user_id = principal.user_id` in the caller's tenant. Any role, bound or not to anything else (C4). No `details`. |
| 403 | `forbidden` `{"reason"}` | Bound, but no active `speaker` membership covers the profile's unit: `no_grant`, `principal_suspended`, `explicit_resource_deny` (`errors.py:106-118`). |

### 2.2 `GET /v1/me/invitations`

Own `cba_invitation` rows with `status = 'dispatched'` (C9). 200:

```json
{
  "invitations": [
    {
      "invitation_id": "0b6c2f0e-…",
      "event": {
        "title": "Accounting Society Spring Mixer",
        "date_text": "Thursday 12 March 2027",
        "local_date": null,
        "time_zone": null
      },
      "dispatched_at": "2026-10-01T17:00:00Z",
      "status": "accepted_invitation",
      "response": { "recorded_at": "2026-10-02T09:14:00Z", "recorded_by": "speaker" },
      "answerable": false
    }
  ],
  "truncated": false
}
```

| Field | Source | Rule |
|---|---|---|
| `event.title` | `cba_invitation_batch.event_name` | What the invitation said, verbatim |
| `event.date_text` | `cba_invitation_batch.event_date` | Verbatim, never parsed (`schema.py:2596-2601`) |
| `event.local_date`, `event.time_zone` | `event.resolved_date`, `event.time_zone` via T4's `batch.speaker_request_id` | The date in the event's own zone (`events.resolved_date`, `smartmatch_domain/events.py:336`). `null` when the batch names no request, the event is unresolved, or T4 is not on the base (C3). |
| `dispatched_at` | `cba_invitation.dispatched_at` | When the send was queued. Not proof of delivery. |
| `status` | `response_status` | `awaiting_response` · `accepted_invitation` · `declined_invitation` |
| `response` | `response_recorded_at`, `response_channel` | `null` while awaiting. `recorded_by`: `speaker_link` or `speaker_portal` → `"speaker"`; `connector_recorded` → `"speaker_connector"`. Never a user id. |
| `answerable` | `status == awaiting_response` | |
| `truncated` | read `MAX_ROWS + 1` | `MAX_ROWS = 200` |

**Never returned** (checked by the OpenAPI test's exact property set): `batch_id`, `match_run_id`, `template_id`, batch `created_by_user_id`, other recipients, `skip_reason`, `contact_channel_id`, `recipient_address`, `outreach_draft_id`, `outreach_send_job_id`, delivery facts, `response_recorded_by_user_id`, `professional_id`, `owning_unit_id`.

### 2.3 `POST /v1/me/invitations/{invitation_id}/response`

Request `{"response": "accept" | "decline"}` (`SpeakerOwnResponseRequest`, `extra="forbid"`). 200:

```json
{ "invitation": { "…": "the §2.2 item, after the write" }, "recorded": true }
```

| Status | Code | When |
|---|---|---|
| 200 | — | First answer: `recorded: true`. Same answer again: `recorded: false`, nothing written, `recorded_at` unchanged. |
| 404 | `speaker_invitation_not_found` | Unknown id, **another Speaker's**, another tenant's, or own but `pending`/`skipped`. One code, one message, identical bytes (the Connector route's code, `routers/cba_invitations.py:1196-1201`). |
| 409 | `speaker_invitation_already_answered` | A different answer is already recorded. Row unchanged. Message from `InvitationResponseConflict` (OQ-CBA-044 stays closed). |
| 422 | `invalid_request` | Missing, extra or unknown `response` |

Plus §2.1. Accepting writes only `cba_invitation`: no pipeline stage, no consent change (the token route's rule, `routers/cba_invitations.py:1280-1289`). The hand-off route stays the only path from an acceptance to `pipeline_record`.

### 2.4 `GET /v1/me/engagements?when=upcoming|past`

`when` defaults to `upcoming`; any other value → 422 `invalid_request`. Own `pipeline_record` rows (`subject_id = professional_id`) with `confirmed_at IS NOT NULL`, **cancelled included**. 200:

```json
{
  "when": "upcoming",
  "as_of": "2026-09-23",
  "engagements": [
    {
      "engagement_id": "5d0e…",
      "event": {
        "title": "ACCT 4100 guest lecture",
        "local_date": "2026-10-14",
        "time_zone": "America/Los_Angeles",
        "time_precision": "exact",
        "starts_at": "2026-10-14T17:00:00Z",
        "ends_at": "2026-10-14T18:15:00Z"
      },
      "state": "cancelled",
      "confirmed_at": "2026-09-20T16:02:00Z",
      "attended_at": null,
      "cancelled_at": "2026-09-22T21:40:00Z"
    }
  ],
  "truncated": false
}
```

| Rule | Value |
|---|---|
| `as_of` | `utc_now().date()` — UTC, as T3 C1, T4 and T8b |
| Join | `LEFT JOIN event ON (tenant_id, id) = (pipeline_record.tenant_id, opportunity_event_id)`. `opportunity_event_id` has no FK (`schema.py:686-690`); a missing row gives `event: null`. |
| `upcoming` | `event.resolved_date IS NULL OR event.resolved_date >= :as_of` — unknown date is never "past" (C8) |
| `past` | `event.resolved_date < :as_of` |
| Order | upcoming: `resolved_date ASC NULLS LAST, starts_at ASC NULLS LAST, id`; past: `resolved_date DESC, starts_at DESC NULLS LAST, id` |
| `state` | `cancelled` if `cancelled_at`; else `attended` if `attended_at`; else `confirmed`. T8a's `ck_pipeline_record_cancellation_not_attended` makes the first two exclusive. |
| Cap | `MAX_ROWS + 1` read → `truncated` |

**Never returned:** `cancelled_by_user_id`, `owning_unit_id`, `matched_provenance`, `matched_at`, `contacted_at`, `member_inquiry_at`, `attended_attendance_id`, event `description`, location, `filed_by_user_id`, anything naming a Host or another Speaker.

### 2.5 `GET` / `PATCH /v1/me/availability`

Parent §4.1 body and response, unchanged: T3's `SpeakerAvailabilityUpdateRequest` and `SpeakerAvailabilityResponse`. Differences from T3's Connector route:

| Aspect | T3 Connector route | T6b-2 Speaker route |
|---|---|---|
| Subject | path `{professional_id}` in `{unit_id}` | the bound profile (§3.1), no path parameter |
| Source written | `AvailabilitySource.CONNECTOR` | `AvailabilitySource.SPEAKER`: `updated_source = 'speaker'`; new windows `created_source = 'speaker'`; unchanged `(starts_on, ends_on)` keep their source (T2 `_replace_windows`) |
| 404 | `speaker_contact_not_found`, `unit_not_found` | `speaker_profile_not_linked` only |
| Quota | `speaker_contact.read` / `.write` | `speaker_self.read` / `.write` |

Everything else is T3's, byte for byte: 409 `speaker_availability_stale` with no `details`; the four 422 domain codes and their `details`; stale wins over a domain-invalid body; UTC "today"; the expired-pause drop rule; full replace; `stated: false` for no row.

## 3. Handlers

### 3.1 `_authorize_speaker_self(session, principal) -> BoundSpeakerProfile`

One authorizer for all 5 operations: one persona, one resource (the `_authorize_speaker_contacts` arrangement, `cba_contacts.py:624-663`). Every handler calls it **by name** (`test_the_route_calls_the_authorizer_the_matrix_names`, `test_policy_matrix.py:9081`).

```python
def _authorize_speaker_self(session: Session, principal: CurrentPrincipal) -> BoundSpeakerProfile:
    bound = _portal.find_bound_profile(
        session, tenant_id=principal.tenant_id, account_user_id=principal.user_id
    )
    if bound is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_profile_not_linked",
            message="No Speaker profile is linked to this account.",
        )
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(bound.owning_unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(bound.owning_unit_path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_SELF_ROLES,
    )
    return bound
```

- The subject comes from `principal.user_id` only. The lookup reads nothing from the request, so the 404 is no oracle.
- **Rows are keyed by `bound.professional_id`, never by `principal.user_id`.** In T6b-5's merged login they differ.
- T6b-1 grants the `speaker` membership at the profile unit's path (T6b-1 §5 step 12), so the membership covers exactly this resource.
- No `require_membership` (the role set is non-empty, S-007); no `tenant_wide_roles`; no `excluded_roles`.
- T6b-3 reuses this authorizer for `/v1/me/contact-channels*` through the matrix's `authorizer_module` field.

### 3.2 Order, every handler

1. `charge_quota(session, principal, <READ or WRITE limit>)`.
2. `bound = _authorize_speaker_self(session, principal)`.
3. Route work, scoped by `principal.tenant_id` and `bound.professional_id`.
4. Writes: `session.commit()`, then answer. Reads never commit.

### 3.3 `PATCH /v1/me/availability`

1. Quota (write), authorize.
2. `stored = _availability.get(session, tenant_id=…, professional_id=bound.professional_id)`.
3. `now = utc_now()`; `today = now.date()`.
4. T3's shared path, and nothing else: stale pre-check → `statement_from_request(body, stored, today)` → the write helper (C1) with `source=AvailabilitySource.SPEAKER`, `actor_user_id=principal.user_id`, `expected_version=body.expected_version`, `now=now`.
5. Commit; return `availability_response(bound.professional_id, result)`.

T6b-2 never calls `validate_availability_statement` or `SpeakerAvailabilityRepository.upsert` itself. A source-guard test enforces it (§7.5).

### 3.4 `POST /v1/me/invitations/{invitation_id}/response`

1. Quota (write), authorize.
2. `row = _invites.get_for_professional(session, tenant_id=…, professional_id=bound.professional_id, invitation_id=…)`; `None` → 404 `speaker_invitation_not_found`.
3. `resulting, changed = record_response(SpeakerResponse(row.response_status), _speaker_response(body.response))`; `InvitationResponseConflict` → 409 `speaker_invitation_already_answered`.
4. `changed` → `wrote = _invites.record_response(..., response_channel=_PORTAL_RESPONSE_CHANNEL, recorded_at=utc_now(), recorded_by_user_id=<C2>)`.
5. **Lost race** (`wrote is False`, a token-link or Connector answer landed between steps 2 and 4): re-read once and rerun step 3 on the fresh row. Same answer → `recorded: false`; different → 409. The Connector route ignores this return value today (`routers/cba_invitations.py:1228-1238`); not fixed here.
6. Commit when written; re-read the item; return it with `recorded`.

`_PORTAL_RESPONSE_CHANNEL` is `"speaker_portal"` with `recorded_by_user_id=principal.user_id` under C2 = (b), or `"speaker_link"` with `None` under (a). One constant, one keyword.

### 3.5 Reads

- `GET /v1/me/availability`: quota (read), authorize, `_availability.get`, `availability_response(bound.professional_id, stored)`.
- `GET /v1/me/invitations`: `list_for_professional(limit=MAX_ROWS + 1)`, map with `invitation_view`.
- `GET /v1/me/engagements`: `list_engagements_for_speaker(today=utc_now().date(), when=when, limit=MAX_ROWS + 1)`, map with `engagement_view`.

## 4. Authz rows

### 4.1 `tests/authz/test_policy_matrix.py`

1. **5 `Operation`s**, after the `host_organization.*` block (ends `:1831`). Shared fields: `module="smartmatch_api.routers.speaker_self"`, `authorizer="_authorize_speaker_self"`, `roles_constant="_SPEAKER_SELF_ROLES"`, `authorizer_module=None`, `required_roles=frozenset({"speaker"})`, `resource_type="org_unit"`, `unit_scoped=True`.

   | key | method | path |
   |---|---|---|
   | `speaker_self.availability.read` | GET | `/v1/me/availability` |
   | `speaker_self.availability.update` | PATCH | `/v1/me/availability` |
   | `speaker_self.invitation.list` | GET | `/v1/me/invitations` |
   | `speaker_self.invitation.respond` | POST | `/v1/me/invitations/{invitation_id}/response` |
   | `speaker_self.engagement.list` | GET | `/v1/me/engagements` |

   The comment says: `evaluate` has no self-scope, so "these rows are yours" is asserted over HTTP in `tests/contract/test_speaker_self_api.py` (the `host_organization.read_own` division of labour, `:8707-8721`).
2. **Dispatch tuple** (`:8486-8725`): add `"_authorize_speaker_self"`, with a comment on the same terms as the host-organization names.
3. **One full `MATRIX` row** for `speaker_self.availability.read`, and 4 aliases after `:8366`: `MATRIX[k] = MATRIX["speaker_self.availability.read"]`. Same function, same constant, so disagreement is unrepresentable.

   | Shape | Cell | Why (short) |
   |---|---|---|
   | `speaker_at_owning_unit` (T6b-1) | **permit** | The cell this track exists for; the route then returns only the bound profile's rows |
   | `admin_at_org_root` | `no_grant` | A Connector uses T3's route |
   | `coordinator_at_owning_unit` | `no_grant` | Read first: the role is the only thing refusing it |
   | `coordinator_at_sibling_unit`, `admin_at_sibling_unit` | `no_grant` | Wrong role and wrong path |
   | `student_at_owning_unit` | `no_grant` | |
   | `volunteer_at_owning_unit` | `no_grant` | An Event Host is not a Speaker (OQ-CBA-042 narrow reading; GLOSSARY) |
   | `member_with_no_memberships`, `expired_coordinator_at_owning_unit`, `job_actor_without_role` | `no_grant` | |
   | `resource_grant_only` | `resource_grant_lacks_required_role` | S-007 |
   | `admin_with_explicit_deny`, `job_actor_with_explicit_deny` | `explicit_resource_deny` | |
   | `suspended_admin` | `principal_suspended` | |
   | `cross_tenant_coordinator` | `tenant_mismatch` | |

4. **Replace T6b-1's `test_a_speaker_membership_reaches_no_operation`** (T6b-1 §3.4 item 4), which T6b-2 makes false. New: `SPEAKER_SELF_OPERATIONS: frozenset[str]` (the 5 keys) and `test_a_speaker_membership_reaches_only_its_own_operations`: the `speaker_at_owning_unit` cell permits exactly `SPEAKER_SELF_OPERATIONS`, checked by `_observe`. Plus `test_every_speaker_self_operation_names_only_the_speaker_role`.
5. `_wrong_role_shape_for` picks `student_at_owning_unit` for all 5; no change.

### 4.2 `tests/authz/test_route_roles.py`

1. `_SPEAKER_SELF = frozenset({"speaker"})`, a literal (compared with `is`, `:128-150`).
2. 5 `ROUTE_ROLE_LEDGER` rows (`:71-80`); the exact-set test (`:201-212`) gains them.
3. `test_speaker_self_roles_matches_the_live_constant` (`speaker_self._SPEAKER_SELF_ROLES == _SPEAKER_SELF`).
4. **Fix the persona collision (C5).** `test_every_gated_role_set_holds_only_stored_role_strings` (`:225-248`) asserts `not (roles & personas)`, and `Persona.SPEAKER == "speaker"` (`role_presentation.py:118-123`). Change it to `not (roles & (personas - stored_roles))`: a persona value that **is** a stored role is that role; the check targets presentation-only values (`event_host`, `speaker_connector`). Add `test_persona_values_that_are_stored_roles_are_exactly_student_and_speaker`, so a third collision fails loudly.

## 5. OpenAPI

`SPEAKER_PORTAL` is off in every scope (T6b-1 C2), so `make openapi` builds the app without these routes. **`contracts/openapi/smartmatch.json` does not change**; CI's `--check` (`verify.yml:127`) stays green.

- T6b-1's `test_openapi_document_has_no_speaker_portal_paths` and `test_routes_unmounted_when_off` gain the 4 T6b-2 paths.
- The schema is proven on an app built with the capability on: `FastAPI()` + `EXCEPTION_HANDLERS` + `routers_for(<T6b-1's capability-on settings stub>)` → `.openapi()` (the `test_exercise_instructor_router.py:307-327` pattern). If T6b-1's stub is file-local, copy it: a `Settings` subclass whose `capability_enabled` returns `True` for `SPEAKER_PORTAL`.
- Every route declares `responses` for 403 / 404 / 409 / 429 with `ErrorEnvelope`.

## 6. `api.ts` adapters (consumed by T6b-4)

```ts
export type MyInvitationStatus = "awaiting_response" | "accepted_invitation" | "declined_invitation";
export interface MyInvitationEvent {
  title: string; date_text: string; local_date: string | null; time_zone: string | null;
}
export interface MyInvitationResponse { recorded_at: string; recorded_by: "speaker" | "speaker_connector" }
export interface MyInvitation {
  invitation_id: string; event: MyInvitationEvent; dispatched_at: string;
  status: MyInvitationStatus; response: MyInvitationResponse | null; answerable: boolean;
}
export interface MyInvitationList { invitations: MyInvitation[]; truncated: boolean }
export interface MyInvitationAnswerResult { invitation: MyInvitation; recorded: boolean }
export type EngagementWhen = "upcoming" | "past";
export type MyEngagementState = "confirmed" | "attended" | "cancelled";
export interface MyEngagementEvent {
  title: string; local_date: string | null; time_zone: string | null;
  time_precision: "exact" | "date_only" | "unresolved"; starts_at: string | null; ends_at: string | null;
}
export interface MyEngagement {
  engagement_id: string; event: MyEngagementEvent | null; state: MyEngagementState;
  confirmed_at: string; attended_at: string | null; cancelled_at: string | null;
}
export interface MyEngagementList { when: EngagementWhen; as_of: string; engagements: MyEngagement[]; truncated: boolean }
export type SpeakerSelfErrorCode =
  | "speaker_profile_not_linked" | "speaker_invitation_not_found" | "speaker_invitation_already_answered"
  | Exclude<SpeakerAvailabilityErrorCode, "speaker_contact_not_found">;

export async function fetchMyAvailability(): Promise<SpeakerAvailability>;
export async function updateMyAvailability(payload: SpeakerAvailabilityUpdatePayload): Promise<SpeakerAvailability>;
export async function fetchMyInvitations(): Promise<MyInvitationList>;
export async function answerMyInvitation(invitationId: string, response: "accept" | "decline"): Promise<MyInvitationAnswerResult>;
export async function fetchMyEngagements(when: EngagementWhen): Promise<MyEngagementList>;
```

- All call `requestJson<T>(path, init, { authenticated: true })` (`api.ts:484`). PATCH and POST send `JSON.stringify(body)`.
- `invitationId` goes through `encodeURIComponent`; `when` through `URLSearchParams`.
- **No adapter takes a professional id or a unit id** (MM-A01). The source scan pins this.
- `SpeakerAvailability` and `SpeakerAvailabilityUpdatePayload` are T3's types, reused.
- Errors stay `ApiRequestError` (`api.ts:330`) with `status`, `code`, `details`. No retry, no default, no normalizing.
- T6b-4 query resources (principal first, `useScopedQuery`): `"my-availability"`, `"my-invitations"`, `"my-engagements"` + `when`. An answer invalidates `"my-invitations"` only.

## 7. TDD list

Local rule: one file at a time; DB tests on a private database (`smartmatch_b26_t6b2`), dropped after. Token and subject literals built at runtime (forbidden-behaviour scanner). CI proves the suite.

### 7.1 Unit — `tests/unit/test_speaker_self_views.py` (no DB)

1. `test_engagement_state_is_cancelled_then_attended_then_confirmed`
2. `test_recorded_by_maps_each_channel` (`speaker_link`, `speaker_portal` → `speaker`; `connector_recorded` → `speaker_connector`; awaiting → `response is None`)
3. `test_answerable_only_while_awaiting`
4. `test_invitation_view_field_set_is_exact` and `test_engagement_view_field_set_is_exact` (no batch, canceller, unit or other-person field)
5. `test_request_models_forbid_extra_keys` (`professional_id`, `user_id`, `unit_id`, `channel` each → 422)

### 7.2 Integration — `tests/integration/test_speaker_self_reads.py` (repositories)

1. `test_find_bound_profile_returns_profile_and_unit_path` · `test_find_bound_profile_is_tenant_scoped` · `test_unbound_login_finds_nothing`
2. `test_invitations_are_own_dispatched_rows_only` (excluded: `pending`, `skipped`, another professional, another tenant)
3. `test_invitations_order_newest_first_and_honour_limit`
4. `test_get_for_professional_refuses_another_professionals_invitation`
5. `test_engagements_include_cancelled_and_attended_exclude_unconfirmed`
6. `test_engagement_buckets_by_event_local_date` (as_of fixed: yesterday → past; today → upcoming; unresolved → upcoming; missing event row → upcoming with no event)
7. `test_rows_are_keyed_by_professional_not_login` (profile bound by SQL to a different login L; rows keyed to L are not returned)

### 7.3 Contract — `tests/contract/test_speaker_self_api.py`

Marked `integration`; app from §5's capability-on builder; real rows and `FixtureTokenVerifier` (the `test_host_organizations_api.py` shape). A coordinator composes and dispatches over HTTP (`test_cba_invitations_api.py` helpers `roster_contact` `:88`, `create_batch` `:195`, `dispatch` `:219`, `respond` `:243`). Speakers are bound by SQL (`account_user_id`, `account_bound_at`, `membership(role='speaker')` at the profile unit's path). Clock pinned with `monkeypatch.setattr("smartmatch_api.routers.speaker_self.utc_now", …)`.

**Subject and roles**

1. `test_unlinked_caller_is_404_on_every_route` (parametrized: 5 routes × `volunteer`, `coordinator`, `student`, `admin`; exact code `speaker_profile_not_linked`)
2. `test_bound_login_without_speaker_membership_is_403` (volunteer and coordinator logins; `reason == "no_grant"`)
3. `test_expired_speaker_membership_is_403` · `test_suspended_speaker_is_403_principal_suspended` · `test_unauthenticated_is_401`
4. `test_quota_is_charged_before_the_404` (the `speaker_self.*` counter moves for an unlinked caller)
5. `test_merged_login_resolves_to_the_bound_profile` (login ≠ `professional_id`; T6b-5's shape, built by SQL)
6. `test_one_activated_speaker_reads_own_availability` (end to end through T6b-1's `POST /v1/speaker-portal/activate`)

**Own rows only**

7. `test_invitations_list_only_own_rows` (Speakers A and B in one unit, plus an unbound contact; A's ids == A's dispatched ids)
8. `test_pending_and_skipped_invitations_are_not_listed`
9. `test_invitation_json_carries_no_batch_or_other_speaker_field` (exact key set; B's name and address absent from the raw body)
10. `test_engagements_list_only_own_rows`
11. `test_query_parameters_cannot_select_another_speaker` (`?professional_id=<B>` on the GETs returns A's data)

**Cross-Speaker 404**

12. `test_answering_another_speakers_invitation_is_404_and_writes_nothing`
13. `test_that_404_is_byte_identical_to_an_unknown_id`
14. `test_own_undispatched_invitation_is_404`

**Response rules**

15. `test_accept_records_the_portal_channel_and_actor` (C2 decides the asserted values)
16. `test_repeating_the_same_answer_is_200_and_keeps_the_first_time`
17. `test_a_different_second_answer_is_409_and_changes_nothing`
18. `test_a_link_answer_then_a_different_portal_answer_is_409` (T6a `/i/{token}` first)
19. `test_a_lost_race_is_classified_not_silent` (monkeypatch a concurrent write between read and update)
20. `test_accepting_writes_no_pipeline_stage_and_no_consent`
21. `test_bad_response_body_is_422` (`"maybe"`, missing, extra key)

**Availability**

22. `test_get_unstated_is_stated_false`
23. `test_patch_writes_speaker_source_on_row_and_new_windows`
24. `test_connector_window_keeps_its_source_after_a_speaker_replace`
25. `test_connector_route_reads_the_speakers_write` (T3's GET shows `updated_source: "speaker"`)
26. `test_stale_version_is_409_without_details` · `test_each_domain_code_is_422_with_t3_details` (4 cases) · `test_today_is_the_utc_date`
27. `test_patch_body_naming_a_professional_is_422_invalid_request`

**Engagements**

28. `test_upcoming_and_past_split_on_local_date_vs_utc_today` · `test_when_defaults_to_upcoming` · `test_bad_when_is_422`
29. `test_cancelled_booking_shows_cancelled_without_canceller` · `test_attended_booking_shows_attended` · `test_contacted_only_journey_is_not_listed`

**Composition**

30. `test_routes_unmounted_when_capability_off` (default `Settings()`, all 5 → 404 route-not-found) · `test_routes_mounted_when_on`

### 7.4 Authz

§4.1 and §4.2 rows run through every existing matrix test. New: `test_a_speaker_membership_reaches_only_its_own_operations`, `test_every_speaker_self_operation_names_only_the_speaker_role`, `test_speaker_self_roles_matches_the_live_constant`, `test_persona_values_that_are_stored_roles_are_exactly_student_and_speaker`.

### 7.5 OpenAPI and source guards

`tests/unit/test_speaker_self_openapi_contract.py` (the `test_speaker_pipeline_openapi_contract.py` shape):

1. `test_the_five_operations_are_published_when_on`
2. `test_no_parameter_names_a_subject` (only `invitation_id` and `when`)
3. `test_request_bodies_forbid_additional_properties`
4. `test_invitation_and_engagement_items_have_exact_property_sets`
5. `test_when_is_an_enum_of_upcoming_and_past` · `test_committed_contract_has_none_of_the_four_paths`

`tests/unit/test_speaker_self_source_guard.py` (AST over `routers/speaker_self.py`):

1. `test_availability_goes_through_t3s_helper_only` (no `validate_availability_statement`, no `.upsert(`, no `AvailabilitySource.CONNECTOR`; the helper and `AvailabilitySource.SPEAKER` are referenced)
2. `test_every_handler_calls_the_authorizer_before_any_repository`
3. `test_no_handler_reads_principal_user_id_as_a_row_key` (repository calls pass `bound.professional_id`)
4. `test_the_token_helper_is_not_used` (`answer_by_token` absent: it swallows conflicts)

### 7.6 Frontend

- `tests/unit/test_frontend_speaker_self_contract.py` (source scan, `_code_only` as `test_frontend_invitation_compose_contract.py:53`): the 5 functions and URLs exist; none has a parameter named `professionalId`, `unitId` or `userId`; `fetchMyEngagements` takes `EngagementWhen`.
- `apps/web/legacy-frontend/src/lib/speakerSelfApi.test.tsx` (Vitest, `vi.stubGlobal("fetch", …)`, token set with `storeSmartmatchBearerToken(<runtime value>)` and cleared): each URL, method and body; `Authorization` sent; `invitationId` encoded; 404 `speaker_profile_not_linked` and 409 `speaker_invitation_already_answered` surface as `ApiRequestError.code`; 422 keeps `details`. Run from a Linux-FS copy: `npx vitest run --pool=threads src/lib/speakerSelfApi.test.tsx`.

## 8. Commit milestones (red → green, one commit each, pushed)

0. `chore: merge origin/feat/b26-t8a into feat/b26-t6b-2`, then `chore: merge origin/feat/b26-t3 into feat/b26-t6b-2` (§0; `make openapi` if the JSON conflicted).
1. `test: T6b-2 own-row reads and view builders (red)` — §7.1, §7.2. Body records the red run.
2. `feat: bound-profile lookup, own invitations and engagements reads` — repositories, `speaker_self.py` view builders; §7.1–7.2 green.
3. `test: T6b-2 Speaker routes, authz rows and OpenAPI (red)` — §7.3–7.5, matrix and ledger rows.
4. `feat: /v1/me Speaker routes under SPEAKER_PORTAL` — router, `main.py`, matrix dispatch entry, persona fix, T6b-1 test replaced, capability docstring; §7.3–7.5 green (contract in CI).
5. `test: speaker self-service api.ts adapters (red)` → 6. `feat: speaker self-service api.ts adapters` — §7.6 green.
7. `docs: SPEAKER_PORTAL policy row lists the Speaker's own routes` (+ C2 (b) channel docs).

Before each push: `$VENV/bin/ruff format` and `ruff check` on touched Python and this plan; `npx tsc --noEmit -p .` after milestone 6.

## 9. Contradictions and decisions

| # | Issue | Decision / recommendation |
|---|---|---|
| C1 | The dispatcher names a T3 helper `write_statement(session, …, statement, today, …)` that validates then upserts. T3's plan @ `f8c12bfb` has no such function: its steps 5–8 (stale pre-check, build, validate, upsert, `StaleSpeakerAvailabilityError` → 409) are inline in the route (T3 §3). | **Ask T3 to export it** in its milestone 2: `write_statement(session, *, tenant_id, professional_id, statement, today, source, actor_user_id, expected_version, now) -> StoredSpeakerAvailability`, raising T3's `ApiError`s, never committing. If T3 lands without it, T6b-2's milestone 0 adds `refactor: extract write_statement from the connector availability route` (no behaviour change; T3's contract file proves it). |
| C2 | `ck_cba_invitation_response_channel` admits only `speaker_link` and `connector_recorded`; `ck_cba_invitation_response_actor` requires `recorded_by_user_id` **iff** `connector_recorded` (`schema.py:2739-2746`, `0029:143-153`). A portal answer has an account behind it, which `0029`'s rationale says a `speaker_link` never has. | **Recommend (b):** fold into T6b-1's `0039`, which is not yet written: channel gains `speaker_portal`; actor CHECK becomes `(response_channel IN ('connector_recorded','speaker_portal')) = (response_recorded_by_user_id IS NOT NULL)`. Answers are then attributable, and Connectors can tell a portal answer from a link click. **Fallback (a)** if `0039` has already landed: record `speaker_link` with no actor; no migration in T6b-2. Needs an orchestrator ruling before T6b-1 milestone 1. |
| C3 | "Date in the event's zone": an invitation's only event data is the batch's typed `event_name` / `event_date` text (`schema.py:2596-2601`, `cba_handoff.py:54-60`). An event link arrives only with T4's `0041` (`batch.speaker_request_id`), and T6b-2 does not stack on T4. | Contract carries both now: `date_text` (what the email said) and nullable `local_date` + `time_zone` (from the event row). If T4 is on the base at milestone 2, join it; if not, ship `null` and add ledger follow-up "T6b-2 FU: fill `local_date` from `speaker_request_id`". The response shape does not change either way. |
| C4 | Parent §4.3: unbound → `404 speaker_profile_not_linked`. §7 row 7: `volunteer` and `coordinator` "denied". The resource (the profile's unit) is only known after the lookup. | Lookup first. Unbound → 404 for **every** role; bound without an active covering `speaker` membership → 403 `no_grant`. The matrix covers the 403 half, the contract tests both. No oracle: the lookup reads only the caller's own id. |
| C5 | `Persona.SPEAKER.value == "speaker"`, so any `{speaker}` ledger row fails `test_every_gated_role_set_holds_only_stored_role_strings` (`test_route_roles.py:243-248`). | Narrow to presentation-only personas (§4.2 item 4). |
| C6 | T6b-1's planned `test_a_speaker_membership_reaches_no_operation` becomes false once these rows exist. | Replace it in milestone 4 (§4.1 item 4). |
| C7 | A different second answer: the token route answers 200 silently (anti-oracle); the Connector route answers 409. | 409. The caller is the authenticated owner, so there is nothing to hide, and "your first answer is final" matches T6a's page text. |
| C8 | `upcoming` / `past` need a "today" and a rule for unknown dates. | UTC today (T3 C1, T4, T8b) against the event's **local** date, the rule T8b's window uses. Unknown or missing date → `upcoming` (never silently "past"). Residual: an evening event west of UTC reads `past` after 00:00 UTC on its own day. |
| C9 | Which invitations count as "own"? | `status = 'dispatched'` only. `pending` was never sent; `skipped` would disclose a Connector's internal reason (`unavailable_on_date`, `channel_suppressed`). |
| C10 | The routes are unmounted by default, so the committed OpenAPI cannot show them. | Committed contract unchanged; schema proven on a capability-on app (§5). |

## 10. Out of scope

- Consent routes (T6b-3), portal pages (T6b-4), existing-login binding and unbinding (T6b-5).
- The Speaker's load band on the availability page (T8d adds `load` to T3's response).
- A Speaker cancelling their own booking or changing an answer (OQ-CBA-044).
- Paging past 200 rows.
- Fixing the Connector response route's ignored lost-race return value (§3.4 step 5).

---

**Next action (under two minutes):** post C2 to the orchestrator: "fold `speaker_portal` into `0039` (b), or record portal answers as `speaker_link` (a)?"
