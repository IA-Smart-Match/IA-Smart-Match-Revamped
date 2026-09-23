# B26 — self-service availability for professionals (2026-09-22)

**Next action:** the owner answers **Q2** (who edits) in §9. Tracks T1–T5 and T7
can start before that answer; T6 cannot.

**Status:** planning only. No source file, route, or migration is written by this
document.
**Decision:** DECIDED 2026-09-22 (owner): option B — build self-service
availability; plan at `docs/plans/2026-09-22-b26-self-service-availability-plan.md`.
**Still open:** D2's sub-question (committed vs completed load), which is **Q1**
below. The owner's decision does not answer it.
**Migration:** `0038_speaker_availability`, on top of head `0037_exercise_tables`.
If another revision lands first, take current head plus one and keep one head.
**Out of bounds:** `docs/plans/frontend-broken-buttons.md`. PR #208 owns its B26 row.

---

## 1. The premise, checked against the code

The decision says: professionals correct their own availability on
`VolunteerProfile.tsx`, through a new `/v1/me/availability`, and the result feeds
ELI and matching. Five facts in the code change how that can be built.

| # | Fact | Evidence | Consequence |
|---|---|---|---|
| 1 | The volunteer portal's user is an **Event Host**, and an Event Host is not a speaker. | `role_presentation.py:152-158` maps `volunteer` → "Event Host"; `docs/architecture/GLOSSARY.md` "Event Host … Does **not** mean: A speaker"; `VolunteerProfile.tsx:42` says "Your Event Host record." | An editor on `VolunteerProfile` would edit data about a person that matching never scores. |
| 2 | The person matching scores is a **Speaker**, and a Speaker has no account. | `apps/web/DESIGN.md` "Speakers are contact records, not accounts: no stored role maps to a speaker"; `speaker_profile.professional_id` → a `user_account` whose subject is `contact-professional:<uuid>` (`smartmatch_domain/cba_contacts.py:176`), which no identity provider issues; `routers/cba_invitations.py` `speaker_respond` is unauthenticated "by design" for the same reason. | `/v1/me/*` has no Speaker to answer for today. A Speaker can reach the system only through a token link. |
| 3 | **ELI has no caller.** | `grep compute_eli` → only `tests/unit/test_eli.py`. The registry has no ELI factor: its 7 `FactorSpec`s are 4 CBA factors, 2 retired G1 factors, and `availability` (`factor_registry.py:297-394`). `feedback.py:24` records that `engagement_load` "never existed here". | "Feeds ELI" is not a wiring job. ELI needs an engagement-hours source, D2's answer, a new registry version, and an approval. That is track T8, and it is gated. |
| 4 | **The Stage A `availability` filter exists, is registered, and is unwired.** | `factor_registry.py:380-394` (`availability`, `ELIGIBILITY`, weight 0, `implemented=True`); `eligibility.apply_availability_filter` has no caller outside `tests/unit/test_eligibility.py`. | This is where self-service availability can feed matching **now**, with no weight change and no registry bump (§5). |
| 5 | Nothing stores availability or workload for any principal. | `schema.py` has no such column or table; `user_account` is `id, tenant_id, external_subject, email, suspended, created_at, version`. | New tables are needed — §3. |

Two more facts the plan relies on:

- **The invitation token page has no controls.** `GET /i/{token}`
  (`services/api/smartmatch_api/main.py:799-836`) returns an `<h1>` and "Choose
  below to accept or decline", then nothing — no form, no button, no script. The
  token-link route for Speakers works only if a client can post to it. T6 variant
  A has to fix this first.
- **"DESIGN.md §1.6" no longer exists.** The citation points to the pre-CBA
  `apps/web/DESIGN.md` (commit `e60fce33`, "1.6 Four audiences"), which said
  professionals must "see and correct the availability and workload data used
  about them". Commit `3a83cad1` replaced that file. The obligation survives in
  architecture v1.1 §5.1 (cited at `eli.py:77` and `eli.py:266`). Current
  `DESIGN.md` does not track status, so this plan does not edit it.

**How the plan resolves the conflict:** the data model is keyed on the entity
matching measures, `speaker_profile (tenant_id, professional_id)`. The
Connector-side write and the Stage A wiring (T1–T5) do not depend on who the
self-service editor is, so they ship first. Who edits from where — a Speaker by
token link, a Speaker account, or the Event Host — is **Q2**, and only T6 waits on
it. `VolunteerProfile` gets a truthful close-out (T7) under every answer.

## 2. Goal and non-goals

**Goal.** A Speaker's own statement of when they cannot speak is stored against
their `speaker_profile`, can be corrected by them and by their Speaker Connector,
and removes them from invitation for events on those dates through the existing
Stage A `availability` filter. Every run records which verdict it used.

**Who may write**

| Principal | Write | Read | Route family |
|---|---|---|---|
| Speaker Connector (`admin`, `coordinator`) in the profile's `owning_unit_id` | yes | yes | `/v1/units/{unit_id}/speaker-contacts/{professional_id}/availability` |
| Speaker, Q2 = A (token link) | add only | **no** | `POST /v1/speaker-invitations/availability` |
| Speaker, Q2 = B (Speaker account) | yes | own only | `GET` / `PATCH /v1/me/availability` |
| Event Host (`volunteer`) | no | no | — (OQ-CBA-042's narrow reading: a Host does not learn a named person's availability) |
| Student | no | no | — |

**Non-goals**

1. No ELI wiring until Q1 is answered and T8 is approved.
2. No workload, hours, or capacity field until T8 (Q6). Nothing consumes one.
3. No weekly recurrence and no times of day (§3.3).
4. No free-text reason. A reason box collects health and family detail that
   `PROHIBITED_INPUTS` (`health_inference`, `protected_characteristic`) forbids
   any factor from reading.
5. No change to contact consent. Pausing invitations is not a suppression, and
   unsubscribing stays the only way to stop mail (`consent.py`, ADR-0014's split).
6. No re-ranking. Program direction (G1, 2026-09-03) is "match first, then
   availability"; this plan keeps it.

**Privacy and consent constraints**

- Dates only. No reason, no location, no calendar import.
- Event Hosts never see availability, a window, or a verdict naming a Speaker.
- The token route never reads back what is stored: a forwarded email must not
  reveal a person's diary.
- Each row records who wrote it (`speaker` or `connector`) and, for a
  Connector, which account (ADR-0011 rule 1, the migration `0028` pattern).
- Retention follows D5, which is still deferred. No retention job is added;
  §10 lists the risk.

## 3. Data model — migration `0038_speaker_availability`

Follows ADR-0004 (hand-written Core table, hand-written migration, drift test),
ADR-0009 (one transaction per migration), and the composite tenant key used
throughout `schema.py`.

### 3.1 `speaker_availability` — one row per Speaker who has said anything

| Column | Type | Null | Notes |
|---|---|---|---|
| `tenant_id` | uuid | no | |
| `professional_id` | uuid | no | |
| `invitations_paused_until` | date | yes | `NULL` = not paused. Compared with the run date, not the event date (§5.1). |
| `version` | integer | no, default 1 | Optimistic concurrency; `expected_version` on PATCH, the `matching_weights.py` pattern. |
| `updated_source` | text | no | `'speaker'` or `'connector'` |
| `updated_by_user_id` | uuid | yes | Required when source is `connector`; `NULL` for a token-link write (no account exists). |
| `created_at`, `updated_at` | timestamptz | no, `now()` | |

Constraints:

- `speaker_availability_pkey` on `(tenant_id, professional_id)` — a natural key,
  one row per Speaker, the `speaker_profile` shape.
- FK `(tenant_id, professional_id)` → `speaker_profile (tenant_id, professional_id)`
  **ON DELETE CASCADE**: availability is a statement belonging to the profile, as
  `host_organization_member` belongs to its organization.
- FK `(tenant_id, updated_by_user_id)` → `user_account (tenant_id, id)` **RESTRICT**,
  named `fk_speaker_availability_updated_by` (the `0028` reason: deleting an
  account must not erase who made a judgment).
- `ck_speaker_availability_source`: `updated_source IN ('speaker','connector')`.
- `ck_speaker_availability_actor`:
  `updated_source <> 'connector' OR updated_by_user_id IS NOT NULL`.

**Why a row with no windows matters.** It is what separates "said they are free"
(`AVAILABLE`) from "said nothing" (`UNKNOWN`). Without it, every Speaker with no
windows would read as available — the unknown-as-pass error
`eligibility.py`'s docstring rules out.

### 3.2 `speaker_availability_window` — dates a Speaker cannot speak

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | uuid | no | PK `speaker_availability_window_pkey` |
| `tenant_id`, `professional_id` | uuid | no | |
| `starts_on`, `ends_on` | date | no | Inclusive both ends. |
| `created_source` | text | no | `'speaker'` or `'connector'` |
| `created_by_user_id` | uuid | yes | Same arm as above. |
| `created_at` | timestamptz | no | |

Constraints:

- FK `(tenant_id, professional_id)` → `speaker_availability` **CASCADE**.
- FK `(tenant_id, created_by_user_id)` → `user_account` **RESTRICT**.
- `ck_speaker_availability_window_order`: `ends_on >= starts_on`.
- `ck_speaker_availability_window_span`: `ends_on - starts_on <= 366`.
- `ck_speaker_availability_window_source` and `_actor`, as in §3.1.
- `uq_speaker_availability_window_range` on
  `(tenant_id, professional_id, starts_on, ends_on)`: the same window twice is one
  statement, which makes a repeated token-link post idempotent.
- `ix_speaker_availability_window_lookup` on `(tenant_id, professional_id, ends_on)`
  for "windows still in force".

Domain-level validation (a CHECK cannot read the clock): at most **20** windows per
Speaker; `ends_on` no more than **18 months** ahead of today; a pause no more than
**12 months** ahead. These limits live in `smartmatch_domain` constants, and
`tests/integration` binds them to the API's 422s.

**No `owning_unit_id`.** Availability is a fact about a person, not a unit's
record, so it reaches a unit through `speaker_profile.owning_unit_id`. That is
the W1 student-profile argument (`2026-09-13-w1-student-interest-profile-plan.md` §3).

### 3.3 Coarse or structured — the choice and why

**Chosen: date windows plus a pause.** Rejected: weekly recurrence, times of
day, and "max engagements per term".

| Consumer | What it can read | What that rules in or out |
|---|---|---|
| `eligibility.apply_availability_filter` | One `AvailabilityState` per Speaker: `AVAILABLE` / `BLACKED_OUT` / `UNKNOWN` | Anything finer must reduce to one of three states per event. A date window reduces cleanly; a weekly pattern does not (see next row). |
| `event` temporal model (ADR-0010) | `resolved_date`, `on_date`, `starts_at`/`ends_at` only at `exact`, nothing at `unresolved` | A `date_only` event has no time, so "Tuesdays after 5 pm" cannot be evaluated against it. Date windows can be evaluated against any resolved event. |
| `eli.LoadInputs` | `declared_capacity_hours` and `LoadModifier.MANUAL_BLACKOUT` | Counts per term are not an ELI input. Capacity is an ELI input, but ELI has no caller (§1 fact 3), so it waits for T8 (Q6). |

The pause exists because "don't invite me until January" is the most common
thing a busy professional says. Without it, a Speaker would have to guess a
window covering every future event date.

### 3.4 Migration hygiene

- `schema.py` mirrors both tables with every constraint name, and
  `tests/integration/test_schema_matches_migration.py` covers them automatically.
- Downgrade drops both tables. It is lossless only while no row exists, and the
  docstring says so.
- README's "37 Alembic revisions, head `0037_exercise_tables`" row moves to 38 and
  `0038_speaker_availability` in the same PR.
- ADR-0019's `ownership.py` is decided but not built (`ls
  python/smartmatch_persistence/smartmatch_persistence` shows no such module). If
  it exists when T2 starts, both tables register as owned by
  `smartmatch_persistence.speaker_availability` with writer `api`.

## 4. API

All errors use `{ "error": { "code", "message", "details"? } }` through `ApiError`.
Every write charges quota first (ADR-0015), the order `cba_contacts.py` uses.

### 4.1 Connector routes (T3)

`GET /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability`
`PATCH /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability`

- Roles: `{admin, coordinator}`, a new literal row each in
  `tests/authz/test_route_roles.py`. Authorized against the loaded unit's path;
  the profile must have `owning_unit_id = unit_id`, otherwise
  `404 speaker_contact_not_found` (the existing code — no oracle across units).
- PATCH replaces the whole statement, the way the contact PATCH does:

```json
{
  "expected_version": 3,
  "invitations_paused_until": "2027-01-10",
  "unavailable": [{ "starts_on": "2026-11-02", "ends_on": "2026-11-06" }]
}
```

- Response, both routes:

```json
{
  "professional_id": "…",
  "stated": true,
  "version": 4,
  "invitations_paused_until": "2027-01-10",
  "unavailable": [{ "starts_on": "2026-11-02", "ends_on": "2026-11-06", "source": "speaker" }],
  "updated_source": "connector",
  "updated_at": "2026-09-22T18:04:11Z"
}
```

  `stated: false` with empty fields means no row exists. That is not "available",
  and the UI says "Not stated".
- Error codes:

| Status | Code | When |
|---|---|---|
| 404 | `speaker_contact_not_found` | Unknown id, or a profile in another unit |
| 409 | `speaker_availability_stale` | `expected_version` is not current |
| 422 | `speaker_availability_window_invalid` | `ends_on < starts_on`, span > 366 days, or beyond the horizon |
| 422 | `speaker_availability_too_many_windows` | More than 20 windows |
| 422 | `speaker_availability_pause_invalid` | Pause in the past or more than 12 months ahead |
| 403 / 429 | existing policy / quota codes | |

- Audit: the row's `updated_source` / `updated_by_user_id` / `updated_at`, and
  each window's creator. Whether older versions are kept is **Q5**.

### 4.2 Self-service, variant A — token link (T6a, if Q2 = A)

`POST /v1/speaker-invitations/availability`, unauthenticated by design, like
`/v1/speaker-invitations/respond`:

```json
{ "token": "…", "unavailable": [{ "starts_on": "…", "ends_on": "…" }], "pause_until": null }
```

- **Add only.** A window or pause is added; nothing is removed or read back. A
  Speaker who made a mistake tells their Connector.
- **Identical response for every token**: `200 {"recorded": true}`, the anti-oracle
  posture of `speaker_respond`. A malformed body still gets a 422; a well-formed
  body with an unknown token writes nothing.
- The token resolves to one invitation, then to that invitation's Speaker. Writes
  record `created_source = 'speaker'` with a `NULL` actor.
- A cap of 10 added windows per invitation token bounds a leaked link.
- Prerequisite: `/i/{token}` renders working accept/decline controls plus an
  "I can't do these dates" section. Today it renders neither (§1).

### 4.3 Self-service, variant B — Speaker account (T6b, if Q2 = B)

`GET /v1/me/availability` and `PATCH /v1/me/availability` — the owner's name,
and the right one for this variant. PATCH matches the `matching_weights`
precedent (`expected_version`, 409 on stale). Same body and response as §4.1.

- Requires a new stored role (proposed: `speaker`), a mapping in `portals.py`
  `_PORTAL_FOR_ROLE`, a credential path for contacts, and a link from the
  account to exactly one `speaker_profile`. `404 speaker_profile_not_linked`
  when the caller has none.
- No path or body field names the subject (MM-A01). The subject is
  `principal.user_id` resolved to its linked profile.
- This is the backlog item "invitation-only speaker accounts" (Ann: "phase two …
  I will bring it to Pia and Lisa") and OQ-CBA-043's identity. It is not
  buildable on this owner's decision alone.

### 4.4 OpenAPI and client

1. `make openapi` regenerates `contracts/openapi/smartmatch.json`, and
   `make openapi-check` gates it.
2. Typed adapters go in `apps/web/legacy-frontend/src/lib/api.ts` with contract
   coverage, until the ADR-0020 generated client replaces them.
3. A new `ErrorEnvelope` code list in each route's `responses=`.

## 5. How it feeds matching and ELI

### 5.1 Now: the Stage A `availability` filter (T4)

1. **Domain (T1).** `smartmatch_domain/speaker_availability.py` adds
   `availability_state_for_event(statement, event_dates, as_of) -> AvailabilityEvidence`.
   `eligibility.AvailabilityEvidence` gains an optional `reason`, so a verdict can
   say "paused until 10 Jan" or "event date unresolved" instead of the fixed
   string it returns today.
2. **At run creation (API).** `create_match_run` already reads every candidate's
   `speaker_profile`. It also reads their availability, computes one verdict per
   pool candidate for the request's event, and stores them in the command payload
   under a new `availability` key, beside `candidates` and `explanations`.
3. **At read.** `read_match_run` annotates each shortlisted Speaker with the
   stored verdict. A run with no `availability` key says "availability was not
   recorded for this run". It is not shown as `UNDETERMINED`, because that would
   claim an evaluation that never happened.
4. **At batch compose and at dispatch.** `cba_invitations` reports a Speaker whose
   **current** verdict is `EXCLUDED` as not invitable, with the reason, the way
   `classify_recipient` reports a consent gap. Re-checked at dispatch: a pause
   added after composing must stop the send.

Verdict rules:

| Situation | State |
|---|---|
| No `speaker_availability` row | `UNKNOWN` → `UNDETERMINED` |
| Event `time_precision = 'unresolved'` | `UNKNOWN` → `UNDETERMINED` ("event date unresolved") |
| `invitations_paused_until >= as_of` (the run or compose date) | `BLACKED_OUT` → `EXCLUDED` |
| Any window overlaps the event's local dates (`resolved_date` through the local date of `ends_at` when exact) | `BLACKED_OUT` → `EXCLUDED` |
| Otherwise | `AVAILABLE` → `ELIGIBLE` |

**Registry and reproducibility — no bump.**

- `availability` is already declared, `implemented=True`, weight 0. Wiring it
  changes no weight, so `weights_fingerprint` and `registry_hash` are unchanged
  and `REGISTRY_VERSION` stays `2.0.0-approved-oq-cba-004`.
- The filter runs after the shortlist and never reorders it, so
  `inputs_fingerprint` (event, pool, utilities, size, seed, weights) is unchanged.
  `_reconstruct_shortlist` still re-derives the same selection.
- Runs pinned to `1.1.1-approved-g1-m6j` or `2.0.0-approved-oq-cba-004` before T4
  read exactly as they do now, plus the "not recorded" line.
- Whether the verdict is the one stored at run time or re-read live is **Q4**.

**Golden cases.** Add `tests/golden/matching/cba/G-CBA-13-availability-leaves-hash-and-pool-alone.json`:
the same pool with and without availability rows gives identical `registry_hash`,
`inputs_fingerprint`, and shortlist order, and differs only in the verdicts. No
existing case changes. `G-CBA-10` (payload round trip) is untouched because
explanations are not modified.

### 5.2 Later: ELI (T8, gated)

What ELI still needs, none of which this decision provides:

| Need | Where it would come from | Blocker |
|---|---|---|
| Engagement records (`occurred_on`, `event_hours`, `travel_hours`) | `pipeline_record` rows whose `subject_id` is the Speaker (`routers/cba_handoff.py:445`): `attended_at` = completed, `confirmed_at` = committed | **Q1 / D2**: count committed or not |
| `event_hours` | `event.ends_at - starts_at`, only when `time_precision = 'exact'` and `ends_at` is set | Unknown hours for other events cannot become 0 (ADR-0011); needs a rule |
| `travel_hours` | Route matrix | D3: no provider, so `0.0`, recorded as unavailable (`eli.py` `EngagementRecord`) |
| `declared_capacity_hours` | A new column in a later migration | **Q6**; also `LoadInputs` defaults it to `40.0` (`eli.py:160`) while its own docstring says the caller "must not substitute one" — T8 removes the default |
| `MANUAL_BLACKOUT` modifier | From this plan's windows | None — ready once T8 starts |
| Stage A cap override ("authorized, expiring") | Not built | Needs its own table and route |
| Scoring change | A new `FactorSpec`, a major bump (`3.0.0-approved-<gate>`), because a penalty makes scores incomparable with 2.x (ADR-0016's reasoning) | Owner approval; new golden cases; `2.0.0` runs stay readable through `registry_for_version`, as `1.1.1` runs do now |

## 6. Frontend

### 6.1 Connector panel (T5) — `CoordinatorSpeakerContacts.tsx`

- A read panel plus an "Edit availability" form on the contact detail.
- Read through `useScopedQuery` with key `[principalKey, "speaker-availability", unitId, professionalId]`.
- Write through `useMutation`, pending-disabled submit, and invalidation of that
  one key only. No optimistic update.
- Errors: branch on `ApiRequestError.code` — `speaker_availability_stale` shows
  "Someone changed this. Reload to see their version." and keeps the user's input;
  the 422 codes attach to the offending row.
- States: loading; **Not stated** (`stated: false`, never "Available"); stated
  with no windows ("No dates blocked"); windows listed; error; denied.
- Accessibility (WCAG 2.2 AA, DESIGN.md): native `<input type="date">` with a
  visible label per field; each window row is a `<fieldset>` with a `<legend>`
  ("Unavailable from … to …"); "Remove" buttons have accessible names that include
  the dates; save result announced in one `role="status"` region; errors in
  `role="alert"` next to the field and linked with `aria-describedby`; keyboard
  order field → field → remove → add → save.

### 6.2 Match run and invitations (inside T4)

- `CoordinatorMatchRuns`: each shortlisted Speaker shows "Available", "Unavailable
  on this date (Speaker's statement)", "Paused until 10 Jan", or "Availability not
  stated". No numbers and no weights (OQ-CBA-005).
- `CoordinatorInvitations`: excluded Speakers are listed as not invitable, with
  the reason, the same shape as a consent gap.

### 6.3 Speaker self-service (T6)

- **A:** a static, server-rendered form on `/i/{token}` (no React bundle, no
  token echoed into HTML). The token comes from `location` at submit. After
  submit it shows the same "Recorded" message whatever happened.
- **B:** a new Speaker shell and a Profile page with the §6.1 form, the same
  hooks keyed on the principal.

### 6.4 `VolunteerProfile.tsx` (T7)

Under Q2 = A or B, availability is not an Event Host capability. The page drops
the dead `PortalDatasetUnavailable` panel for `/api/portals/volunteers/{id}`,
shows the Host's own record (signed-in email, role, unit), and links to
`VolunteerOrganization`. The B26 row then closes as "not a Host capability; see
this plan". Q3 asks the owner to confirm.

## 7. Tests — TDD order per track

Each track writes its failing tests first, then the code. Locally, run the
targeted files one at a time (full runs wedge on `/mnt/c`); CI proves the suite.

| Order | Track | Test first | Level |
|---|---|---|---|
| 1 | T1 | `tests/unit/test_speaker_availability.py`: each row of the §5.1 verdict table; window overlap at both inclusive edges; multi-day exact events; unresolved event; horizon, span, and count limits; `PROHIBITED_INPUTS` has no field here | unit |
| 2 | T1 | `tests/unit/test_eligibility.py`: optional `reason` passes through; default reasons unchanged | unit |
| 3 | T2 | `tests/integration/test_speaker_availability_migration.py`: every CHECK rejects its bad row; cross-tenant FK refused; CASCADE from profile; duplicate window refused by `uq_…`; `connector` without actor refused. The drift test covers the mirror | integration |
| 4 | T2 | `tests/integration/test_speaker_availability_repository.py`: stale version refused; replace is atomic | integration |
| 5 | T3 | `tests/contract/test_speaker_availability_api.py`: 200/404/409/422/403/429 bodies; profile in another unit → 404; `stated:false` shape | contract |
| 6 | T3 | `tests/authz/test_route_roles.py` rows; `test_policy_matrix.py` derives the new routes; volunteer and student denied | authz |
| 7 | T4 | `tests/contract/test_match_runs_api.py`: verdicts stored and read; old run → "not recorded"; `G-CBA-13` | contract + golden |
| 8 | T4 | `tests/contract/test_cba_invitations_api.py`: paused Speaker not invitable at compose; pause added after compose stops dispatch | contract |
| 9 | T5 | Vitest: states, stale-version path keeps input, key isolation across principals (`queryClient.principal-isolation.test.ts` pattern) | frontend unit |
| 10 | T6a | contract: identical response for real / unknown / used tokens; add-only; per-token cap; `/i/{token}` renders controls and never echoes the token | contract |
| 11 | T7 | Vitest + `tests/unit/test_frontend_*_contract.py` source guard: no `/api/portals/volunteers` call remains | frontend unit |
| 12 | T4–T6 | `tests/e2e/test_pilot_clickthrough.py`: Connector blocks a date → run shows "Unavailable" → batch refuses | e2e |

## 8. Tracks

Each track is its own PR against `main`.

| Track | Scope | Estimate | Depends on |
|---|---|---|---|
| **T1** | Domain: `speaker_availability.py`, `reason` on `AvailabilityEvidence`, limits as constants | 0.5 day | — |
| **T2** | Migration `0038_speaker_availability`, `schema.py` mirror, repository, README count | 1.5 days | T1 |
| **T3** | Connector `GET`/`PATCH` routes, OpenAPI, `api.ts` adapter, authz ledger | 1.5 days | T2 |
| **T4** | Stage A wiring: run payload, read annotation, compose and dispatch checks, `G-CBA-13` | 2.5 days | T2 (T3 for the e2e step) |
| **T5** | Connector availability panel on `CoordinatorSpeakerContacts` | 1 day | T3 |
| **T6a** | Speaker token-link add-only route plus working `/i/{token}` controls | 2 days | T2, Q2 = A |
| **T6b** | Speaker accounts, role, portal, `/v1/me/availability`, Speaker profile page | 6–8 days | T2, T3, Q2 = B, backlog item approved by Ann / Pia / Lisa, OQ-CBA-043 |
| **T7** | `VolunteerProfile` truthful close-out | 0.5 day | Q3 |
| **T8** | ELI: capacity column (`0039_*`), engagement source, new registry version, cap override, golden cases | 4–6 days | Q1 (D2), Q6, T2, owner approval of the new registry |

Without T6b and T8, the total is about **9.5 days**. T1 → T2 → T3 is the
critical path; T4 and T5 run in parallel after it.

## 9. Owner questions

### Q1 (D2 sub-question — still OPEN). Do committed future engagements count toward a Speaker's load, or only completed ones?

- **(a) Completed only.** `attended_at` rows count; `confirmed_at` for a future
  event does not. This is what `eli.py` does today: it refuses future-dated records.
- **(b) Completed plus committed, within a forward horizon.** Needs two new
  parameters: the horizon in days and the weight of a future engagement.
- **(c) Committed counts toward the Stage A hard cap only, never the Stage B penalty.**

**Recommendation: (a).** It adds no parameter, it is the behaviour already tested,
and the self-service windows now cover forward unavailability directly — which is
what counting commitments was meant to approximate. Revisit after a term of data.
Only T8 waits on this.

### Q2. Who is the professional who edits their availability?

- **(A) The Speaker, through their invitation link, add-only; plus their
  Connector.** No account, no new role. Uses the existing token posture. The
  Speaker cannot see what is stored (the OQ-CBA-043 concern about a link that
  reveals a person's history).
- **(B) The Speaker, through a Speaker account and `/v1/me/availability`.** Fully
  meets "see and correct". Needs the "invitation-only speaker accounts" backlog
  item, which Ann called phase two, plus OQ-CBA-043 and OQ-CBA-035.
- **(C) The Event Host, on `VolunteerProfile`.** Buildable today, but nothing
  reads it: hosts are not scored, so it would collect data with no consumer
  (D8's minimum-disclosure position).

**Recommendation: (A) now, (B) when the speaker-accounts item is approved.** The
§3 tables serve both unchanged. Do not build (C).

### Q3. What does the Event Host's Profile page show, given availability is not a Host capability?

- **(a)** Drop the dead panel; show the Host's own record and a link to
  Organization; close B26 as "not a Host capability".
- **(b)** Leave the page as it is until Speaker accounts exist.
- **(c)** Build a Host availability editor anyway (only if Q2 = C).

**Recommendation: (a).** The current panel names a legacy endpoint that will never
exist in this repository.

### Q4. Does a match run show the availability verdict from when it ran, or current availability?

- **(a) Stored at run time**, with a note when current availability now differs.
- **(b) Read live** every time the run is opened.
- **(c) Show both side by side.**

**Recommendation: (a).** A run is an immutable snapshot (`match_run` in the
glossary). A verdict that changes after the fact makes "why wasn't she invited?"
unanswerable. Invitation compose and dispatch still check current state.

### Q5. Keep a history of availability changes?

- **(a) Provenance only** — who wrote the current row and when — plus the run-time
  snapshot from Q4. This is OQ-CBA-008's "provenance, no history" pattern.
- **(b) An append-only revision table**, like `match_weight_setting_revision`.
- **(c) Nothing beyond `updated_at`.**

**Recommendation: (a).** The run snapshot already answers disputes about a
decision. A revision log keeps a person's diary longer with no reader and no
retention rule (D5).

### Q6. Collect declared capacity (hours) now, or only with ELI?

- **(a) Only with T8**, in a later migration.
- **(b) Now**, as hours per rolling 90 days (`eli.py`'s window).
- **(c) Now**, as maximum engagements per term.

**Recommendation: (a).** Nothing reads capacity until ELI is wired. Its unit
depends on D2's window, which may change. And (c) is not an ELI input at all.

## 10. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | The owner expects an editor on `VolunteerProfile` and reads T7 as a reversal. | §1 states the evidence. Q2 and Q3 make it an explicit choice. |
| 2 | A leaked invitation link lets a stranger block a Speaker's dates. | Add-only, capped at 10 windows per token, Connector can remove, no read-back. |
| 3 | Speakers who never state availability stay `UNDETERMINED`, and Connectors read that as "available". | UI says "Availability not stated" and never "Available" for that state. |
| 4 | Stored windows accumulate with no retention rule (D5 deferred). | Record as a D5 input. Windows that ended are ignored by every verdict. |
| 5 | Migration number collides with a parallel PR. | Take head plus one at rebase; one head only. |

---

**Next action (under two minutes):** reply on the PR with "Q2: A" (or B or C).
