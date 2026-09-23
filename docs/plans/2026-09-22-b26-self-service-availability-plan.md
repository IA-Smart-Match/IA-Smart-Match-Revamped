# B26 — self-service availability for professionals (2026-09-22)

**Next action:** start T1, T6b-1, T6a, T7 and T8a in parallel. No owner question is open.

**Status:** planning only. No source file, route, or migration is written by this
document. **Revision 3, 2026-09-22:** the owner answered all six first-round
questions, then Q7 (band penalties) and the email-clash question, the same day.

**Decisions recorded (owner, 2026-09-22)**

| # | Decision |
|---|---|
| B26 | DECIDED 2026-09-22 (owner): option B — build self-service availability; plan at `docs/plans/2026-09-22-b26-self-service-availability-plan.md`. |
| Q2 | **B — Speakers get invitation-only accounts.** A Speaker Connector clicks "Invite to portal"; the Speaker gets a one-time email link, sets a password, and the account binds to the existing contact record and its `contact-professional:` subject. |
| OQ-CBA-043 | **Yes.** A signed-in Speaker sees their own invitations, accepted engagements and upcoming events. |
| OQ-CBA-035 | **Yes, self-service.** A signed-in Speaker opts their own channels in and out, recorded with `consent_source = 'self_service'`. The Speaker's choice wins over a Connector-recorded state. |
| Q1 / D2 | **Centered 90-day utilization.** load = (hours completed in the last 45 days + hours **confirmed** in the next 45 days) ÷ declared capacity hours per 90 days. A cancelled booking drops out immediately. Bands: Light < 50% no penalty; Moderate 50–80% small penalty; Heavy 80–100% large penalty; Full > 100% filtered out at Stage A. No horizon or weight parameter. |
| Q3 | (a) The Host Profile page shows the Host's own record and a link to Organization, and drops the dead panel. |
| Q4 | (a) The availability verdict is stored at run time, with a note if availability changed since. Compose and dispatch re-check current state. |
| Q5 | (a) Provenance only (who, when) plus the run-time snapshot. |
| Q6 | Collect declared capacity **now**, in hours per rolling 90 days, in the T2 migration. Remove `eli.py`'s `40.0` default. |
| Q7 | **(A) Light × 1.00 · Moderate × 0.90 · Heavy × 0.70, multiplicative.** Exactly 50% is Moderate, exactly 80% is Heavy, exactly 100% is Heavy, Full is strictly above 100% (the rule `evaluate_cap` already uses). Registry `3.0.0` still needs its normal approval and IA West review. |
| Unknown load | No penalty, not filtered, labelled "load not measurable". |
| Q8 | **(a) Exclude the requester from their own request's pool**, reported in the run's `excluded` list as "filed this request". |
| Email clash | **One login, two roles.** A person who is both an Event Host and a Speaker with the same email gets one account holding both roles, plus a portal switcher. No `409 speaker_portal_email_in_use` end state (§4.5, track T6b-5). |

**Still open:** no owner question. Five stakeholder dependencies remain (§10).
**Migrations:** `0038_speaker_availability`, `0039_speaker_portal`,
`0040_speaker_booking_cancellation`, on top of head `0037_exercise_tables`. If
another revision lands first, take current head plus one and keep one head.
**Out of bounds:** `docs/plans/frontend-broken-buttons.md`. PR #208 owns its B26 row.

---

## 1. The premise, checked against the code

The first-round premise was an editor on `VolunteerProfile.tsx` feeding ELI. Five
facts decided the shape of the answer, and the owner's decisions resolve each.

| # | Fact | Evidence | Resolved by |
|---|---|---|---|
| 1 | The volunteer portal's user is an **Event Host**, and an Event Host is not a speaker. | `role_presentation.py:152-158` maps `volunteer` → "Event Host"; `docs/architecture/GLOSSARY.md` "Event Host … Does **not** mean: A speaker"; `VolunteerProfile.tsx:42` says "Your Event Host record." | Q2 = B (Speaker portal) and Q3 = a (Host page close-out, T7). |
| 2 | The person matching scores is a **Speaker**, and a Speaker has no account today. | `apps/web/DESIGN.md` "Speakers are contact records, not accounts"; `speaker_profile.professional_id` → a `user_account` with subject `contact-professional:<uuid>` (`smartmatch_domain/cba_contacts.py:176`) and a placeholder `.invalid` email; `speaker_respond` is unauthenticated "by design". | T6b: the contact's own `user_account` becomes the login (real email, password, `speaker` membership) — or, when the address already signs in as an Event Host, that existing account gains the `speaker` role (§4.5). No new identity row either way. |
| 3 | **ELI has no caller.** | Only `tests/unit/test_eli.py` imports `compute_eli`. The registry's 7 `FactorSpec`s are 4 CBA factors, 2 retired G1 factors and `availability` (`factor_registry.py:297-394`). | T8: the owner's centered-utilization rule, a band table, and a new major registry version. |
| 4 | **The Stage A `availability` filter is registered and unwired.** | `factor_registry.py:380-394` (`ELIGIBILITY`, weight 0, `implemented=True`); `apply_availability_filter` has no caller outside `tests/unit/test_eligibility.py`. | T4 wires it with no registry bump. |
| 5 | Nothing stores availability, workload or capacity for anyone. | `schema.py`; `user_account` is `id, tenant_id, external_subject, email, suspended, created_at, version`. | T2 (`0038`). |

Three more facts the plan relies on:

- **The invitation token page has no controls.** `GET /i/{token}`
  (`services/api/smartmatch_api/main.py:799-836`) returns an `<h1>` and "Choose
  below to accept or decline", then nothing. Speakers without a portal account
  still get these links, so T6a fixes the page.
- **Nothing can cancel a Speaker booking.** `pipeline_record` has
  `confirmed_at` and `attended_at` but no cancellation; `event` has no cancelled
  state. The owner's "cancelled bookings drop out immediately" needs one — T8a.
- **Event hours are known only for exact events with an end.** `event.ends_at`
  exists only at `time_precision = 'exact'` (`ck_event_end_after_start`). A
  `date_only` event has no duration, and ADR-0011 forbids counting it as 0 — §5.2.

"DESIGN.md §1.6" pointed to the pre-CBA `apps/web/DESIGN.md` (`e60fce33`), replaced
in `3a83cad1`. The obligation lives on in architecture v1.1 §5.1 (`eli.py:77`,
`eli.py:266`). T6b updates DESIGN.md's role table, which currently says no stored
role maps to a speaker.

## 2. Goal, scope and constraints

**Goal.** A Speaker signs in, sees the data used about them — availability,
capacity, invitations, engagements, current load band, contact preferences — and
corrects it. Availability removes them from invitation on those dates now (Stage A,
T4). Load feeds scoring once T8 lands. Every run records what it used.

**Who may do what**

| Principal | Availability + capacity | Own invitations / engagements | Own channel consent | Route family |
|---|---|---|---|---|
| Speaker (`speaker`, new) | read, write own | read; answer invitations | opt in / out | `/v1/me/*` |
| Speaker Connector (`admin`, `coordinator`) in the profile's unit | read, write | existing Connector routes | record, but cannot override the Speaker (§4.4) | `/v1/units/{unit_id}/speaker-contacts/{professional_id}/…` |
| Event Host (`volunteer`) | no | no | no | — (OQ-CBA-042's narrow reading) |
| Student | no | no | no | — |

**Non-goals**

1. No weekly recurrence and no times of day (§3.4).
2. No free-text reason on availability. `PROHIBITED_INPUTS` forbids
   `health_inference` and `protected_characteristic`, which a reason box collects.
3. No self-registration. Accounts exist only by Connector invitation.
4. No live identity provider. Speaker accounts ride the pilot password path
   (`pilot_credential`, `pilot_session`); A1b stays deferred.
5. No re-ranking by availability. Program direction (G1, 2026-09-03) stays "match
   first, then availability". Load is different: the owner put Full at Stage A.
6. No availability revision table (Q5 = a).

**Privacy and consent constraints**

- Availability is dates only; capacity is one number. Nothing else is asked.
- Event Hosts never see availability, capacity, load, or a verdict naming a Speaker.
- A Speaker sees only rows keyed to their own `professional_id`. No path or body
  field names the subject (MM-A01); it is always the profile whose
  `account_user_id = principal.user_id` (§3.2).
- Self-service consent writes `contact_channel_transition` with
  `consent_source = 'self_service'` and the Speaker as `actor_user_id`. Consent and
  availability stay separate: pausing invitations is not an opt-out.
- Retention for windows and invitations follows D5, still deferred (§10).

## 3. Data model

ADR-0004 (hand-written Core tables and migrations, drift test), ADR-0009 (one
transaction per migration), composite tenant keys throughout. Each migration
updates README's revision count and head in the same PR.

### 3.1 `0038_speaker_availability` (T2)

**`speaker_availability`** — one row per Speaker who has stated anything.

| Column | Type | Null | Notes |
|---|---|---|---|
| `tenant_id`, `professional_id` | uuid | no | PK `speaker_availability_pkey`; FK → `speaker_profile` **CASCADE** |
| `invitations_paused_until` | date | yes | `NULL` = not paused. Compared with the run or compose date, not the event date. |
| `declared_capacity_hours_per_90_days` | numeric(5,1) | yes | Q6. `NULL` = not stated — never a default. |
| `version` | integer | no, default 1 | `expected_version` on PATCH, the `matching_weights.py` pattern |
| `updated_source` | text | no | `'speaker'` or `'connector'` |
| `updated_by_user_id` | uuid | no | FK → `user_account` **RESTRICT**. With accounts, every writer has one. |
| `created_at`, `updated_at` | timestamptz | no | |

CHECKs: `ck_speaker_availability_source`;
`ck_speaker_availability_capacity`: `declared_capacity_hours_per_90_days IS NULL OR
(declared_capacity_hours_per_90_days > 0 AND declared_capacity_hours_per_90_days <= 720)`.
720 is 8 hours a day for 90 days; above it is a typo, not a capacity.

**`speaker_availability_window`** — dates a Speaker cannot speak.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | uuid | no | PK |
| `tenant_id`, `professional_id` | uuid | no | FK → `speaker_availability` **CASCADE** |
| `starts_on`, `ends_on` | date | no | Inclusive |
| `created_source`, `created_by_user_id` | text, uuid | no | As above |
| `created_at` | timestamptz | no | |

CHECKs: `ends_on >= starts_on`; `ends_on - starts_on <= 366`; source vocabulary.
`uq_speaker_availability_window_range` on `(tenant_id, professional_id, starts_on,
ends_on)`. Index `(tenant_id, professional_id, ends_on)`.

Domain limits (a CHECK cannot read the clock): 20 windows per Speaker; `ends_on` at
most 18 months ahead; pause at most 12 months ahead.

**Why a row with nothing blocked matters:** it separates "said they are free"
(`AVAILABLE`) from "said nothing" (`UNKNOWN`).

### 3.2 `0039_speaker_portal` (T6b-1)

**`speaker_portal_invitation`** — the one-time link.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | uuid | no | PK |
| `tenant_id`, `professional_id` | uuid | no | FK → `speaker_profile` **RESTRICT** |
| `contact_channel_id` | uuid | no | FK `(tenant_id, contact_channel_id)` → `contact_channel (tenant_id, id)`; the address the link went to and the account's future login email |
| `token_hash` | bytea | no | SHA-256 of a 256-bit token; `octet_length = 32`; unique |
| `issued_by_user_id` | uuid | no | FK → `user_account` **RESTRICT** (the Connector) |
| `issued_at`, `expires_at` | timestamptz | no | 7-day expiry |
| `accepted_at`, `revoked_at` | timestamptz | yes | At most one set (CHECK) |

Partial unique index: one live invitation per Speaker
(`WHERE accepted_at IS NULL AND revoked_at IS NULL`). Issuing a new one revokes the
old one in the same transaction.

**`speaker_profile`** gains `account_user_id` (uuid, null) and `account_bound_at`
(timestamptz, null), set together: the login that speaks for this profile. FK
`(tenant_id, account_user_id)` → `user_account` **RESTRICT** — composite, so a
profile can never bind to an account in another tenant. Partial unique index
`uq_speaker_profile_account` on `(tenant_id, account_user_id) WHERE account_user_id
IS NOT NULL`: one login speaks for at most one Speaker. `professional_id` never
changes, so every row that already references it — invitations, pipeline records,
feedback, stored match runs — is untouched.

**`speaker_portal_invitation`** also records the binding for audit:
`bound_account_user_id` (uuid, null) and `binding_mode` (`'new_login'` |
`'existing_login'`, null), set together with `accepted_at` (CHECK).

**`suppression_record`** gains `lifted_at` and `lifted_by_user_id` (both nullable,
set together), and its `source` CHECK gains `'speaker_portal'`. This is what lets a
Speaker's own opt-in undo their own opt-out (§4.4). Every send-eligibility read
changes to `lifted_at IS NULL` in the same PR — the largest risk in T6b (§10).

No change to `contact_channel` or `contact_channel_transition`: both CHECKs already
admit `self_service`, and `actor_user_id` is already `NOT NULL`.

### 3.3 `0040_speaker_booking_cancellation` (T8a)

`pipeline_record` gains `cancelled_at` (timestamptz, null) and
`cancelled_by_user_id` (uuid, null, FK → `user_account` RESTRICT), set together.
CHECK: `cancelled_at IS NULL OR confirmed_at IS NOT NULL` — only a confirmed booking
can be cancelled. A cancellation is a transition, not a delete (the
`event_registration.status` precedent). It sits outside
`ck_pipeline_record_stage_order`, which stays unchanged.

### 3.4 Why dates, not recurrence (unchanged from revision 1)

`apply_availability_filter` reads one of three states per Speaker per event. A
`date_only` event has no time of day, so a weekly pattern cannot be evaluated
against it; a date window can be evaluated against any resolved event. Capacity is
now an ELI input (Q6), in the unit the owner's rule uses: hours per 90 days.

## 4. API

Errors use `{ "error": { "code", "message", "details"? } }` through `ApiError`.
Writes charge quota first (ADR-0015). Each new route gets a literal row in
`tests/authz/test_route_roles.py`; `test_policy_matrix.py` derives it.

### 4.1 Connector availability (T3)

`GET` / `PATCH /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability`,
roles `{admin, coordinator}`. The profile must sit in `unit_id`, otherwise
`404 speaker_contact_not_found`.

```json
{
  "expected_version": 3,
  "invitations_paused_until": "2027-01-10",
  "declared_capacity_hours_per_90_days": 24.0,
  "unavailable": [{ "starts_on": "2026-11-02", "ends_on": "2026-11-06" }]
}
```

Response adds `professional_id`, `stated` (false = no row, shown as "Not stated",
never "Available"), `version`, per-window `source`, `updated_source`,
`updated_at`. After T8 it also carries `load` (§5.2).

| Status | Code | When |
|---|---|---|
| 404 | `speaker_contact_not_found` | Unknown, or in another unit |
| 409 | `speaker_availability_stale` | `expected_version` not current |
| 422 | `speaker_availability_window_invalid` | Order, span or horizon |
| 422 | `speaker_availability_too_many_windows` | More than 20 |
| 422 | `speaker_availability_pause_invalid` | Past, or more than 12 months ahead |
| 422 | `speaker_availability_capacity_invalid` | ≤ 0 or > 720 |

### 4.2 Speaker accounts and invitation flow (T6b-1)

1. **Invite.** `POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/portal-invitations`,
   roles `{admin, coordinator}`, body `{ "contact_channel_id": "…" }`. The channel
   must belong to this Speaker and be send-eligible now (`is_send_eligible`). The
   email goes through the existing `outreach.send` command with a new closed
   template, `speaker_portal_invite` — no second send path. Returns `202`.
   `DELETE …/portal-invitations/current` revokes.
   Refusals: `409 speaker_portal_already_active`,
   `422 speaker_portal_channel_not_eligible`.
2. **Landing page.** `GET /s/{token}`: a server-rendered password form. Changes
   nothing and never echoes the token (the `/i/{token}` rules).
3. **Activate.** `POST /v1/speaker-portal/activate`, unauthenticated. Two modes,
   chosen by the server, never by the client — §4.5 has the full design:
   - **New login** (no credentialed account holds the address):
     `{ "token", "new_password" }`. Set the contact account's `email` to the
     channel address; upsert `pilot_credential`; bind
     `account_user_id = professional_id`.
   - **Existing login** (exactly one credentialed account in this tenant holds
     the address): `{ "token", "existing_password" }`. Verify that password; bind
     `account_user_id` to that account. No password is set or changed.

   Both modes, in one transaction: insert `membership(role='speaker',
   granted_path=<profile unit path>)` on the bound account; mark the invitation
   accepted with `bound_account_user_id` and `binding_mode`; issue a session.
   `ensure_account` uses `ON CONFLICT DO NOTHING` (`professionals.py`), so a later
   contact edit does not reset the email.
   Refusals: `400 speaker_portal_invitation_invalid` (one code for unknown,
   expired, used or revoked — no oracle); `401 speaker_portal_credentials_invalid`
   for a wrong existing password (counted by `LoginAttemptLimiter`, token not
   consumed); `422 password_too_weak`. The landing page only asks for the
   password the mode needs.
4. **Portal mapping.** `role_presentation.py` adds `speaker` → "Speaker";
   `portals.py` `_PORTAL_FOR_ROLE["speaker"] = ("speaker", "/speaker-portal")`, and
   `_ROLE_PRIORITY` and `_PORTAL_ORDER` gain it. DESIGN.md's role table and its
   "no speaker account" sentences are updated.
5. **Gate.** A new `Capability.SPEAKER_PORTAL` in `product_scope.py`, **off by
   default**, mounts the invite and activate routes. It is turned on for real
   Speakers only after the §10 stakeholder dependency clears.

### 4.3 The Speaker's own routes (T6b-2)

Role `{speaker}`. The subject is the one `speaker_profile` whose
`account_user_id = principal.user_id` — the same lookup for a new login and a
merged one. A caller with no bound profile gets `404 speaker_profile_not_linked`.

| Route | Returns |
|---|---|
| `GET` / `PATCH /v1/me/availability` | §4.1 body and response. `updated_source = 'speaker'`. |
| `GET /v1/me/invitations` | Own `cba_invitation` rows: event title, date in the event's zone, status, response. Never another Speaker, never the batch. |
| `POST /v1/me/invitations/{invitation_id}/response` | `{ "response": "accept" \| "decline" }`; same `record_response` rules as the token route; `404` for an invitation that is not theirs. |
| `GET /v1/me/engagements?when=upcoming\|past` | Own `pipeline_record` rows with `confirmed_at` set: event, confirmed / attended / cancelled. |

### 4.4 Self-service channel consent (T6b-3)

| Route | Effect |
|---|---|
| `GET /v1/me/contact-channels` | Own channels: address, state, whether sendable, who set it last (`speaker` / `connector`). |
| `POST /v1/me/contact-channels/{channel_id}/opt-in` | Transition to `consented` then `active_candidate` with `consent_source = 'self_service'`, actor = Speaker; lifts a suppression whose source is `speaker_portal`, `unsubscribe_link` or `one_click`. |
| `POST /v1/me/contact-channels/{channel_id}/opt-out` | Writes `suppression_record(source='speaker_portal')`. Immediate and prospective (ADR-0014 rule 2). |

**The Speaker's choice wins.**

- A Connector transition to `consented` or `active_candidate` on a channel whose
  latest Speaker action is an opt-out → `409 speaker_contact_channel_speaker_opted_out`.
- A Connector transition away from `active_candidate` on a channel the Speaker
  opted in → `409 speaker_contact_channel_speaker_opted_in`.
- **Never overridden by either side:** `bounce` and `complaint` suppressions. A
  Speaker opt-in cannot lift them, because they are facts about delivery, not choices.

### 4.5 One login, two roles (T6b-5)

The owner's rule: one person, one email, one account, both roles.

**Identity binding.**

1. The Speaker's identity stays `speaker_profile.professional_id` (the
   `contact-professional:<uuid>` account). It is never re-keyed: re-keying would
   touch every referencing table and break stored runs' subject ids.
2. The **login** is `speaker_profile.account_user_id`. For a new login it is the
   contact account itself; for a merged one it is the Host's existing account. The
   contact account then stays credential-less with its `.invalid` email, so it can
   never sign in on its own.
3. `load_by_email` does **not** change. It still returns `None` unless exactly one
   credentialed account holds the address. The merge keeps that true: activation
   never creates a second credential for an address that already has one. The
   activation transaction locks the matching `pilot_credential` rows
   (`SELECT … FOR UPDATE`) so two concurrent activations cannot both take the
   new-login path.
4. If the address is already **ambiguous** (two credentialed accounts — possible
   only from legacy seed data), activation refuses with the generic `400` and the
   Connector sees "address matches more than one login; fix before inviting".
5. If the one credentialed account is in **another tenant**, there is nothing to
   merge — tenancy is structural (composite keys, ADR-0004). The new-login path
   would create an ambiguous address, so activation refuses with the generic
   `400`, and the Connector invite route pre-checks and returns
   `409 speaker_portal_address_in_other_tenant`. Single-tenant pilot: not expected.
6. **Every future account-creation path** (seed tools, a later Host sign-up) must
   call one shared `find_or_add_role(email, role, path)` instead of inserting a
   second credentialed account. T6b-5 moves `tools/seed_pilot_logins.py` onto it.

**Session and role checks.**

- One `pilot_session`, one principal. `PrincipalRepository` loads every
  membership on each request, so the new `speaker` role appears on the next
  request without a new login.
- Route authorization is unchanged: each route's `required_roles` is checked
  against memberships covering the resource path. A `volunteer` membership opens
  Host routes, a `speaker` membership opens `/v1/me/*` Speaker routes, and
  neither widens the other. `test_policy_matrix.py` gains a two-membership
  principal shape.
- Suspending the account suspends both roles. That is correct (one person), and
  the Connector UI says so before suspending.
- Frontend cache keys already start with the principal key, so both portals share
  one principal. Activation invalidates `/v1/me` and `/v1/me/portals`.

**Portal switcher.**

- `GET /v1/me/portals` already returns one descriptor per portal and merges
  deterministically (`portals.py`). With both roles it returns `volunteer` and
  `speaker`. `_PORTAL_ORDER` puts `volunteer` before `speaker`, so
  `default_portal` stays the Host portal for an existing Host.
- A "Switch portal" menu in both shells' header lists `portals[]`, shown only when
  there are two or more. It is a link, not a role change: nothing is sent to the
  server. The last choice is remembered in `localStorage` as a convenience only
  (wrapped in try/catch; `default_portal` is the fallback).

**Audit.** `speaker_portal_invitation` records who invited, when, which login was
bound and by which mode; `speaker_profile.account_bound_at` records when. The
membership row itself has no granter column, so the invitation row is the record
of why the `speaker` role exists.

**Unbinding.** Revoking portal access (Connector) sets `valid_until = now()` on the
`speaker` membership and clears `account_user_id`. The Host role is untouched.

## 5. How it feeds matching and ELI

### 5.1 Availability → Stage A filter (T4, no registry bump)

1. **T1 domain:** `availability_state_for_event(statement, event_dates, as_of)`;
   `AvailabilityEvidence` gains an optional `reason`.
2. **Run creation:** `create_match_run` reads each pool candidate's availability,
   computes a verdict for the request's event, and stores it in the command payload
   under `availability` (Q4 = a).
3. **Read:** each shortlisted Speaker shows the stored verdict, plus "changed since
   this run" when the current verdict differs. A run with no `availability` key
   says "not recorded for this run".
4. **Compose and dispatch** re-check the current verdict and report an `EXCLUDED`
   Speaker as not invitable, the way `classify_recipient` reports a consent gap.

| Situation | Verdict |
|---|---|
| No `speaker_availability` row | `UNKNOWN` → `UNDETERMINED` |
| Event `unresolved` | `UNKNOWN` → `UNDETERMINED` |
| `invitations_paused_until >= as_of` | `BLACKED_OUT` → `EXCLUDED` |
| A window overlaps the event's local dates | `BLACKED_OUT` → `EXCLUDED` |
| Otherwise | `AVAILABLE` → `ELIGIBLE` |

`availability` is already declared at weight 0, and the filter runs after the
shortlist without reordering it. So `registry_hash`, `inputs_fingerprint` and
`REGISTRY_VERSION` (`2.0.0-approved-oq-cba-004`) are unchanged. Golden case
`G-CBA-13-availability-leaves-hash-and-pool-alone`.

### 5.2 Load → ELI 2.0.0 and registry 3.0.0 (T8)

**Formula (T8b, `eli.py`, `ELI_FORMULA_VERSION` 1.1.0 → 2.0.0).** Replaces the
45-day half-life decay and the modifier points; both were parameters the owner's
rule does not have. No stored snapshot references 1.1.0 (there is no
`eli_snapshot` table and no caller), so replacing it strands nothing.

```text
as_of      = the run date (UTC date of run creation)
completed  = Σ event hours, pipeline_record.attended_at set, event local date in [as_of − 45, as_of)
confirmed  = Σ event hours, confirmed_at set, cancelled_at NULL (attended or not),
             event local date in [as_of, as_of + 44]
utilization = (completed + confirmed) / declared_capacity_hours_per_90_days   -- unrounded
```

- The window is 90 days: `[as_of − 45, as_of)` + `[as_of, as_of + 44]`. An event on
  `as_of` that is already attended counts as confirmed (owner, 2026-09-23).
- A cancelled booking (`cancelled_at` set, T8a) counts in neither sum from the
  moment it is cancelled.
- Event hours = `ends_at − starts_at` for an exact event with an end. Travel hours
  stay 0, recorded as unavailable (D3: no route provider).
- `LoadInputs.declared_capacity_hours` loses its `40.0` default and becomes
  optional; `LoadModifier` is deleted (manual blackout now lives in §5.1).

**Bands — decided 2026-09-22 (owner, Q7 = A).**

| Band | Utilization | Stage A | Stage B multiplier |
|---|---|---|---|
| Light | `u < 0.50` | pass | × 1.00 |
| Moderate | `0.50 ≤ u < 0.80` | pass | × 0.90 |
| Heavy | `0.80 ≤ u ≤ 1.00` | pass | × 0.70 |
| Full | `u > 1.00` | removed from the pool before the solve, reported in `excluded` | — |
| Unknown | capacity not stated, or an in-window engagement has no known hours and the known hours alone do not exceed 100% | pass | × 1.00, labelled "load not measurable" |

`u > 1.00` for Full matches `evaluate_cap`'s existing `utilization > 1.0`. If the
known hours alone exceed capacity, the Speaker is Full even with unknown hours —
that bound is certain, so ADR-0011 allows it.

**Registry (T8c).**

1. A new `FactorSpec` `engagement_load`, kind `PENALTY`, weight 0 in the weighted
   sum. Its effect is a multiplier on the composite, so utilities stay in
   `[0, 1]` as `PortfolioCandidate` requires, and the four CBA weights and
   `normalize_weights` are unchanged.
2. `FactorRegistry` gains a versioned `LoadBandTable` (cut points, ownership,
   multipliers). For 3.x, `registry_hash` covers weights **and** the band table.
   For 1.1.1 and 2.0.0 the hash function is unchanged.
3. `REGISTRY_VERSION` → `3.0.0-approved-b26-eli` once approved. Major, because a
   penalty makes scores incomparable with 2.x (ADR-0016's reasoning). Until
   approval, the 3.0.0 registry is declared with status `proposed`, and runs keep
   using 2.0.0.
4. **Pinned runs stay reproducible.** `SUPERSEDED_REGISTRY_VERSION` becomes a set
   holding `1.1.1-approved-g1-m6j` and `2.0.0-approved-oq-cba-004`.
   `registry_for_version` resolves each; a stored run is read at its own pin, not
   re-scored and not re-labelled. `SCORING_MODE_VERSION` stays `1.0.0`: both modes
   admit the same factors as before, and ELI applies in both.
5. The load is folded into `inputs_fingerprint` through the post-penalty
   utilities, which it already covers. Each candidate's explanation gains a `load`
   block (band, completed hours, confirmed hours, capacity, unrounded utilization).
   `explanation_from_payload` accepts its absence for 1.x and 2.x payloads.
6. **Golden cases:** `G-CBA-14` band boundaries (0.4999 / 0.5000 / 0.7999 /
   0.8000 / 1.0000 / 1.0001); `G-CBA-15` Full removed before the solve;
   `G-CBA-16` cancelled booking drops out; `G-CBA-17` unknown capacity scores
   neutral and is labelled; `G-CBA-18` a 2.0.0 run stays readable and keeps its
   hash; `G-CBA-19` same weights, 2.x vs 3.x → different `registry_hash`.
7. v1.1 §1.3's "authorized, expiring override" of the hard cap is **not** built
   here. Full is not overridable until a later card adds it (§11).

## 6. Frontend

All reads use `useScopedQuery` with the principal first in the key; writes use
`useMutation` with pending-disabled submit, no optimistic update, and invalidation
of only the affected keys. Errors branch on `ApiRequestError.code`. WCAG 2.2 AA.

| Surface | Track | What it has |
|---|---|---|
| `CoordinatorSpeakerContacts` availability panel | T5 | Pause date, capacity, windows. States: loading; **Not stated**; stated, nothing blocked; windows; stale (`speaker_availability_stale` keeps input, says "Someone changed this"); error; denied. |
| `CoordinatorSpeakerContacts` "Invite to portal" | T6b-1 | Pick an eligible email channel; shows Invited / Active / Expired; "Revoke". Hidden when `SPEAKER_PORTAL` is off. |
| `CoordinatorMatchRuns` / `CoordinatorInvitations` | T4, T8d | "Available", "Unavailable on this date (Speaker's statement)", "Paused until …", "Availability not stated", "changed since this run"; after T8, a band word (Light / Moderate / Heavy / Full / Load not measurable), never a number (OQ-CBA-005). |
| `/speaker-portal` shell | T6b-4 | Home (upcoming engagements, open invitations), Invitations (answer), Engagements (upcoming / past), Availability (same form as T5 plus the Speaker's own load band after T8), Contact preferences (opt in / out per channel). |
| Portal switcher (both shells) | T6b-5 | "Switch portal" menu listing `/v1/me/portals`; hidden with one portal; keyboard-operable menu button with `aria-expanded`; current portal marked `aria-current`. |
| `/i/{token}` | T6a | Working accept / decline form for Speakers without an account. |
| `VolunteerProfile.tsx` | T7 | Host's own record (email, role, unit), link to Organization; the dead `/api/portals/volunteers/{id}` panel is removed. |

Accessibility details for the forms: native `<input type="date">` and
`<input type="number">` with visible labels; each window a `<fieldset>` with a
`<legend>`; remove buttons named with their dates; one `role="status"` region for
save results; errors in `role="alert"` linked with `aria-describedby`; logical
keyboard order. Opt-in / opt-out are real buttons with the channel address in the
accessible name, and an opt-out asks for confirmation.

## 7. Tests — TDD order

Each track writes failing tests first. Locally, run targeted files one at a time
(full runs wedge on `/mnt/c`); CI proves the suite.

| Order | Track | Test first | Level |
|---|---|---|---|
| 1 | T1 | `test_speaker_availability.py`: every §5.1 row; inclusive edges; multi-day events; limits | unit |
| 2 | T2 | `test_speaker_availability_migration.py`: every CHECK incl. capacity 0 / 720.1; cross-tenant FK; CASCADE | integration |
| 3 | T3 | `test_speaker_availability_api.py`: all §4.1 codes; other-unit 404; `stated:false` | contract + authz |
| 4 | T4 | `test_match_runs_api.py` verdict stored and "changed since"; `test_cba_invitations_api.py` compose/dispatch re-check; `G-CBA-13` | contract + golden |
| 5 | T6a | `/i/{token}` renders controls, never echoes the token; POST identical for every token | contract |
| 6 | T6b-1 | Invite needs an eligible channel; one live invitation; activation is atomic; invalid/expired/used/revoked all one code; email-in-use 409; capability off → routes unmounted | contract + integration |
| 7 | T6b-2 | Each `/v1/me/*` route returns only own rows; another Speaker's invitation → 404; `volunteer` and `coordinator` denied | contract + authz |
| 8 | T6b-3 | Opt-out suppresses immediately; opt-in lifts only own-source suppressions; bounce/complaint never lifted; both 409s; every send-eligibility read honours `lifted_at` | contract + integration |
| 8b | T6b-5 | Existing-login activation: right password binds and adds `speaker` membership; wrong password → 401, token not consumed, attempt counted; new-login path refused when a credentialed account holds the address; ambiguous and other-tenant addresses refused; concurrent activations → one binding; `/v1/me/*` resolves via `account_user_id` in both modes; Host routes unchanged; policy matrix two-membership shape; `/v1/me/portals` lists both; switcher hidden with one portal | contract + integration + authz + Vitest |
| 9 | T8a | Cancel only a confirmed booking; cancellation is a transition | integration + contract |
| 10 | T8b | `test_eli.py` rewritten: centered window edges (day −46, −45, −1, 0, +44, +45), cancellation, unknown hours, lower-bound Full, no default capacity | unit |
| 11 | T8c | `test_factor_registry.py`: 3.0.0 proposed until approved; superseded set; hash coverage; `G-CBA-14`…`19` | unit + golden |
| 12 | T5, T6b-4, T7 | Vitest: states, stale path keeps input, principal-key isolation; source guard that no `/api/portals/volunteers` call remains | frontend unit |
| 13 | all | `tests/e2e/test_pilot_clickthrough.py`: Connector invites → Speaker activates → blocks a date → run shows "Unavailable" → batch refuses; Speaker opts out → invitation not sendable | e2e |

## 8. Tracks

Each track is its own PR against `main`.

| Track | Scope | Estimate | Depends on |
|---|---|---|---|
| **T1** | Domain: availability verdict, `reason` on `AvailabilityEvidence`, limits | 0.5 day | — |
| **T2** | `0038_speaker_availability` incl. capacity, mirror, repository | 1.5 days | T1 |
| **T3** | Connector availability `GET`/`PATCH`, OpenAPI, `api.ts` adapter | 1.5 days | T2 |
| **T4** | Stage A wiring: run payload, "changed since", compose/dispatch re-check, `G-CBA-13`; the self-request exclusion (Q8 = a) | 2.5 days | T2 |
| **T5** | Connector availability panel | 1 day | T3 |
| **T6a** | `/i/{token}` page fix only — working accept/decline controls. The token-link availability route is **dropped**: signed-in Speakers edit through `/v1/me/availability`. | 1 day | — |
| **T6b-1** | Speaker accounts: `0039` (invitation table, suppression lift), `speaker` role and portal mapping, invite / revoke / activate routes, `speaker_portal_invite` template, `/s/{token}` page, `SPEAKER_PORTAL` capability, Connector "Invite to portal" button, DESIGN.md role table | 3.5 days | — |
| **T6b-2** | `/v1/me/availability`, `/v1/me/invitations` (+ response), `/v1/me/engagements` | 2 days | T3, T6b-1 |
| **T6b-3** | Self-service channel consent, Speaker-wins rule, `lifted_at` across every send-eligibility read | 2 days | T6b-1 |
| **T6b-4** | `/speaker-portal` frontend: Home, Invitations, Engagements, Availability, Contact preferences | 3 days | T6b-2, T6b-3 |
| **T6b-5** | One login, two roles: existing-login activation mode, credential locking, `find_or_add_role` (seed tools moved onto it), other-tenant pre-check, revoke/unbind, two-membership authz tests, portal switcher | 2.5 days | T6b-1, T6b-2; switcher UI after T6b-4 |
| **T7** | `VolunteerProfile` close-out (Q3 = a) | 0.5 day | — |
| **T8a** | `0040_speaker_booking_cancellation`, Connector "Cancel booking" route and button | 1.5 days | — |
| **T8b** | `eli.py` 2.0.0: centered utilization, bands, no default capacity | 1 day | — (pure domain; branches from `main`) |
| **T8c** | Registry 3.0.0: band table (Q7 = A), hash coverage, superseded set, Full pre-solve, penalty in scoring, explanation `load` block, `G-CBA-14`…`19` | 3 days | T8a, T8b; registry approval before it becomes current |
| **T8d** | Load band on Connector run views and on the Speaker's Availability page | 1 day | T8c, T6b-4 |

**Total: 28 engineer-days.** Critical paths:

1. T6b-1 → T6b-2 → T6b-4 → T6b-5 (switcher) — **11 days**. T8d (1 day) hangs off
   T6b-4 in parallel with T6b-5.
2. T1 → T2 → T8c → T8d — 6 days of work, with T8b (1 day) in parallel from day
   one, plus waiting for registry 3.0.0 approval before it becomes the current scoring.

T1–T5, T6a, T7, T8a and T8b can run in parallel from day one. T6b-5's backend half
(activation mode, locking, `find_or_add_role`) can start as soon as T6b-2 lands.

## 9. Owner questions

### Q7 — decided 2026-09-22: (A)

Light × 1.00 · Moderate × 0.90 · Heavy × 0.70, multiplicative on the composite.
Exactly 50% is Moderate, exactly 80% is Heavy, exactly 100% is Heavy, and Full is
strictly above 100% (the rule `evaluate_cap` already uses). Unknown load: no
penalty, not filtered, labelled "load not measurable". These values go into
registry `3.0.0` and its hash. **Still required:** that registry's normal approval
and IA West review (§10 row 3).

### Q8 — decided 2026-09-22: (a)

A person is excluded from the pool of a Speaker Request they filed themselves,
and the run reports them in its `excluded` list as "filed this request". Built in
T4 as a Stage A check before the solve: `event.filed_by_user_id =
speaker_profile.account_user_id`. It changes no weight and no registry version, so
`2.0.0` stays current until `3.0.0` is approved. A genuine self-nomination is added
by the Connector by hand.

Tests (T4): the requester's own request excludes them with that reason; another
Host's request does not; a Speaker with no bound login is never excluded by this
rule.

## 10. Stakeholder dependencies still standing

None of these is decided by the owner's answers.

| # | Dependency | What waits on it | Evidence |
|---|---|---|---|
| 1 | **Ann, Pia and Lisa on Speaker accounts.** The backlog row records Ann on 2026-09-15: "cleaner than what we have… also phase two. Please log it in the backlog; I will bring it to Pia and Lisa." No answer from Pia or Lisa is recorded. | Turning `SPEAKER_PORTAL` on for real Speakers. The build (T6b) can proceed with the flag off. | `docs/plans/backlog.md` |
| 2 | **A named privacy owner.** OQ-CBA-035 and OQ-CBA-043 name "the named privacy owner" as a co-owner. None is named (D5, D8). | Storing Speakers' real emails and passwords, and self-service consent, beyond the pilot. | `cba-phase-deferred.md`, `pilot-decisions.md` D5/D8 |
| 3 | **IA West review of the D2 rule.** D1–D9 are "tentative, interim-owned, pending IA West review". | Treating T8's scores as ratified rather than tentative. | `pilot-decisions.md` |
| 4 | **The pilot hostname.** Invite links use `outreach_public_base_url`; the stable address is still open (owner-open-decisions #2). | Sending any `speaker_portal_invite`. | `owner-open-decisions-2026-09-19.md` |
| 5 | **Retention periods (D5).** | Pruning ended windows, expired invitations and cancelled bookings. | `pilot-decisions.md` D5 |

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | Adding `lifted_at` to `suppression_record` misses one send-eligibility read, and a lifted-then-resuppressed address gets mail. | T6b-3 greps every reader and adds a contract test per send path; delivery-time re-check stays. |
| 2 | The merge binds a Speaker profile to the wrong person's login. | Existing-login mode requires that login's password; the token proves control of the invited address; one live invitation per Speaker; `uq_speaker_profile_account`; binding recorded with mode and actor; Connector can unbind. |
| 2b | A later account-creation path inserts a second credentialed account for a merged address, and `load_by_email` then locks that person out. | One shared `find_or_add_role`; a test that fails if any module outside it inserts `pilot_credential`. |
| 3 | Full is not overridable, but v1.1 §1.3 expects an authorized, expiring override. | Labelled in the run as "Full (no override available)"; override is a follow-up card. |
| 4 | Most events are `date_only`, so most loads are "not measurable". | Surfaced as that, not as zero. T8d shows Connectors which engagements lack an end time, so the gap is visible and fixable. |
| 5 | A parallel PR takes `0038`–`0040`. | Take head plus one at rebase; one head only. |

---

**Next action (under two minutes):** open the T1 branch and write `tests/unit/test_speaker_availability.py` first.
