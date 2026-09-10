# Synthetic seed gap plan — why the pilot VM refuses every match run

**Date:** 2026-09-09
**Status:** Plan. Nothing here has been implemented.
**Scope:** diagnosis of `match_run_insufficient_scorable_candidates` on
`https://pilot.plated.blog`, an end-to-end audit of the synthetic dataset, and an
ordered plan to make a demo reachable.
**Evidence:** this repository at `origin/main` (`5fca1180`), plus read-only SQL
against the pilot VM taken 2026-09-09. Nothing was written to the VM.

---

## 1. Verdict: the engine is right. The data is wrong — but not in the way the error text suggests.

The observed refusal is **correct, deliberate behaviour**, and the reasoning is
worth stating because the error message points at the wrong remedy for this
particular failure.

The refusal is raised at
`services/api/smartmatch_api/routers/match_runs.py:923-945`. It fires when
`len(scorable) < portfolio_size`. A candidate is "scorable" only when **every**
factor in the run's scoring model produced a value; ADR-0011 forbids coercing an
absent factor to `0.0`, so one unknown factor makes the whole composite unknown
(`_partition_pool`, same file, and
`python/smartmatch_domain/smartmatch_domain/optimizer.py`).

The observed run reported **12 evaluated, 12 unscorable, 0 excluded**. `excluded
= 0` is the load-bearing number: exclusion is the §19 gate
(`services/api/smartmatch_api/match_run_evidence.py:400-408` calling
`match_ineligibility_reason`). Zero exclusions means **all 12 speakers passed the
§19 classification review** — so the message's closing advice ("Review the
classifications customer §19 requires") is, for this run, a false lead. The
speakers were fine. The **Speaker Request** was not.

### What actually went unknown

Read-only counts from the VM:

| Fact | Value |
|---|---|
| `event` rows | 63 |
| of which `origin='coordinator_entry'`, `is_virtual=false` | **60** |
| of which `origin='coordinator_entry'`, `is_virtual=true` | 3 |
| `speaker_request_classification` rows | **12**, spread over **3** events |
| `coordinator_entry` events with **zero** industry targets | **60** |
| `coordinator_entry` events with **zero** role targets | **60** |
| `speaker_profile` rows | 100 |
| `speaker_profile.location_postal_code` NOT NULL | **0** |
| `speaker_profile.prior_talk` NOT NULL | **0** |
| `match_run` rows | 3 — one per targeted event |
| API `SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED` | `false` |

For a request picked from the 60, **four factors go unknown at once**:

1. **Industry (30%)** — `score_industry_match` returns `None` with basis
   *"speaker request names no industry sectors"* when `requested_sectors` is
   empty (`python/smartmatch_domain/smartmatch_domain/factors/industry_match.py:243-249`).
   60 of 63 events have no targets. **This alone guarantees the refusal.**
2. **Role (25%)** — the identical branch at
   `python/smartmatch_domain/smartmatch_domain/factors/role_match.py:248-254`.
3. **Proximity (30%)** — those 60 events are **physical**, so the run resolves to
   `cba-physical-1`, which scores proximity. Proximity needs
   `speaker_profile.location_postal_code`, which is NULL on all 100 rows, so it
   returns `_unknown`
   (`python/smartmatch_domain/smartmatch_domain/factors/proximity.py:609-617`).
   This is the case `match_runs.py:60-75` documents in advance.
4. **Topic (15%)** — the API builds `FixtureSemanticTopicProvider()` per run
   (`match_runs.py:772-779`). Its recordings live in a per-instance dict
   populated only by `.record()`
   (`python/smartmatch_providers/smartmatch_providers/topic_semantics.py:182-214`),
   and **nothing in `services/`, `python/` or `tools/` ever calls `.record()`** —
   pinned by `tests/unit/test_topic_fixture_pilot_coverage.py:263-305`. So every
   speaker **with** topic text scores unknown, and only the ~12% with **no**
   topic text get §9's `policy_neutral` 0.5. This is exactly ADR-0017's finding
   and is the reason `docs/operations/pilot-dataset-rebuild.md:400-412` records a
   `422` as the **expected** outcome on the fixture path.

So the engine did the only honest thing available to it. **Do not make absent
evidence score as zero.** Every one of these four branches is a deliberate,
documented, test-pinned decision, and §9's neutral policy is scoped narrowly and
on purpose to an *observed absence*, never to a comparison that could not run.

### The one genuine application-level defect

`GET /v1/units/{unit_id}/speaker-requests` — the coordinator's "incoming Speaker
Requests" queue, and the picker on `CoordinatorMatchRuns.tsx` — filters on
**`origin = 'coordinator_entry'` and nothing else**
(`services/api/smartmatch_api/routers/speaker_requests.py:707-739`).

`event.origin` has a closed two-value vocabulary — `coordinator_entry` and
`extraction` (`python/smartmatch_persistence/smartmatch_persistence/events.py:144-150`).
An event arriving through the **CSV events import** is not an extraction, so it
is written as `coordinator_entry` and is therefore **indistinguishable from a
filed Speaker Request** on the only column the queue reads.

The result: the seed's 60 imported calendar events sit in the queue looking
exactly like Speaker Requests, and a coordinator who picks one is guaranteed the
refusal, because the filing path is the only thing that ever writes
`speaker_request_classification` rows (`SpeakerRequestDraft.__post_init__`
*requires* at least one industry and one role —
`python/smartmatch_domain/smartmatch_domain/speaker_requests.py:245-256` — and the
import path never goes through it).

That seam is a product decision, not a one-line fix. It is item **C1** below.

---

## 2. Gap table

`gen` = `tools/generate_pilot_dataset.py`; `plan` = `tools/pilot_dataset_plan.py`.

### 2a. Matching pipeline

| Entity | Required field | Required by | Seeded? | Consequence when missing |
|---|---|---|---|---|
| Speaker Request (`event`) | `speaker_request_classification` kind=`industry` | `industry_match.py:243-249` | **3 of 63** (`gen:1317`) | Industry unknown → composite unknown → **every** candidate unscorable |
| Speaker Request | `speaker_request_classification` kind=`role` | `role_match.py:248-254` | **3 of 63** (`gen:1318`) | Role unknown → same |
| Speaker Request | `description` non-blank | `cba_semantic_topic.py` | **yes, 63/63** | — |
| Speaker Request | `is_virtual` | `match_run_evidence.py:193-202` | 3 virtual (`gen:1316`, hard-coded); 60 imported are **physical** | Physical mode adds proximity, which no profile can satisfy |
| `speaker_profile` | `primary_industry_code` + `industry_taxonomy_version` | `match_run_evidence.py:403` | 84/100 (15% unclassified by design, `plan:143`) | Excluded `industry_classification_missing` — correct, deliberate |
| `speaker_profile` | `industry_classification_source='human'` | `cba_classification.py:428` | 67 human / 17 inferred / 16 null | Excluded `..._awaiting_review` — correct, deliberate (1-in-5 unreviewed, `gen:1202-1217`) |
| `speaker_profile` | `primary_role_code` + version + source | same | 92/100; 73 human | same |
| `speaker_profile` | `topic_text` **or** `prior_talk` | `cba_semantic_topic.py` | `topic_text` 84/100; `prior_talk` **0/100** | With topic text → **unknown** on the fixture path (not neutral). Without → `policy_neutral` 0.5 |
| `speaker_profile` | `location_postal_code` | `proximity.py:609-617` | **0/100 — structurally unreachable.** No import column maps to it; `plan` computes a lat/long that is never written | Every **physical** run is all-unscorable regardless of anything else |
| `speaker_profile` | `location_city` | proximity fallback | **0/100.** The import emits `metro_region`, which `_PROFESSIONAL_PROFILE_KEYS` does not map | same |
| topic comparison | a recording for (`description`, `topic_text`) | `topic_semantics.py:228-233` | **none exist anywhere** | Every documented speaker unknown; only undocumented ones score |

### 2b. Everything else

| Table | VM rows | Note |
|---|---|---|
| `event_registration` | **0** | Student "register for event" flow has no data |
| `reward_item` | **0** | Rewards catalogue empty by design (`gen:2632-2640`); needs `make seed-pilot-rewards` with owner-supplied values |
| `redemption` | **0** | Follows from the above |
| `point_ledger_entry` | 187 | Balances exist; nothing to spend them on |
| `outreach_draft` | 4 | Present on the VM, but **no seed path writes them** — the generator writes none. Provenance unknown; likely hand-made through the UI |
| `outreach_send`, `delivery_event`, `suppression_record` | **0** | Correct — dispatch is G4-gated, nothing is ever sent |
| `cba_invitation_batch` / `cba_invitation` | 3 / 9 | Healthy (6 pending, 3 skipped `no_contact_channel`) |
| `cba_meeting` | **0** | The meetings page (merged in #130) has no data |
| `student_speaker_feedback` | 12 | Healthy, over 4 speakers |
| `resource_grant`, `tenant_budget`, `spend_*` | **0** | Not exercised |

**Unit ownership is not a problem.** There is exactly one `org_unit`
(`pilot`, `08a229c4-…`), every owning-unit column on every populated table holds
that single id, and all 16 memberships are `granted_path='pilot'`. The recent
"repoint outreach/invitations/rewards to the granted unit" work (#139) has
nothing to trip over here.

### 2c. Rows exist, but not for the person logging in

This is a second, independent class of hollowness and it is easy to mistake for
"no data". Three surfaces are scoped by **`principal.user_id`**, not by unit, and
the generator writes their rows under accounts that **no demo login resolves
to**:

| Surface | Scoped by | Rows exist? | Why the demo user still sees nothing |
|---|---|---|---|
| Student points balance / redemptions | `_fold_balance_for(subject_id=principal.user_id)` (`routers/rewards.py:651`) | 187 `point_ledger_entry` | They belong to `synthetic-student:*` accounts (`gen:1146-1151`), not to `compose-pilot-student` or `pilot-login-student` |
| Student agenda + speaker feedback | `attendance_record` for *this* student at *this* event | 290 / 12 | Same — attendance is under the synthetic students. A demo student gets `403 student_feedback_not_eligible` |
| Event Host "my requests" | `filed_by_user_id == principal.user_id` (`routers/speaker_requests.py:768-771`) | 3 requests | The generator files **all** of them with the *coordinator* token (`gen:2513-2520`), so no host ever sees one |

There are also **eight distinct `user_account` rows** for what looks like four
people — four bearer-token principals (`compose-pilot-*`) and four browser-login
principals (`pilot-login-*`) — so a surface seeded against one is invisible to
the other. Compounding it, the compose `web` service hardcodes
`VITE_SMARTMATCH_BEARER_TOKEN` to the **coordinator** token, so the browser app
authenticates as the coordinator whichever portal you open unless you go through
`/login`.

### 2d. Two other things that are broken independently of data

- **The IA Admin section 404s, it does not render empty.** `/dashboard`,
  `/volunteers`, `/calendar`, `/outreach`, `/pipeline`
  (`apps/web/legacy-frontend/src/app/routes.tsx:336-345`) call legacy `/api/data/*`
  and `/api/calendar/*` endpoints (`apps/web/legacy-frontend/src/lib/api.ts:1133-1476`).
  **No backend serves `/api/*`.** These are dead routes, not thin ones.
- **`scripts/reset_pilot_dataset.sh:198-211` builds `SMARTMATCH_DEV_PRINCIPALS`
  from the coordinator token plus the feedback-student tokens only.** It drops
  `compose-student`, `compose-host` and `compose-admin`. An operator who rebuilds
  and then points compose at that database has three of four portal tokens 401ing.
- **`docker compose up` alone seeds almost nothing.** The compose one-shots
  (`seed`, `seed-principals`, `seed-logins`, `seed-review`) write only tenant,
  unit, 8 accounts, 4 credentials, 1 import batch and 2 pending review items.
  The 63 events and 100 profiles on the VM can only have come from a manual
  `scripts/reset_pilot_dataset.sh` run — the real dataset generator is **not
  wired into compose at all**. That is worth knowing before anyone rebuilds
  the VM expecting the data to come back.


---

## 3. The user's specific claim, confirmed

> "Synthetic data (events) do not have an industry they're looking for."

**Correct, and it is the primary cause.** The field is
`speaker_request_classification` — one row per target, `(tenant_id, event_id,
kind, code, taxonomy_version)`, `kind ∈ {industry, role}`, taxonomy versions
`cba-naics-2026-09-04` / `cba-roles-2026-09-04`
(`python/smartmatch_persistence/smartmatch_persistence/schema.py:2182-2240`).

It should come from the request-filing path — `POST
/v1/units/{unit_id}/speaker-requests`, whose body carries `industry_codes` and
`role_codes` and refuses an empty either
(`speaker_requests.py:245-256`). The generator does file 3 such requests
correctly (`gen:1294-1318`). The other 60 events came in through the **CSV events
import**, which has no §7/§8 columns at all
(`docs/pilot-data/columns.yaml` — required columns are `"Event / Program"` and
`"Category"`), and so writes no targets.

---

## 4. The plan

Ordered by what unblocks a demo soonest.

### (a) Seed-data-only — no application logic touched

| # | Item | File | Unblocks | Effort | Risk |
|---|---|---|---|---|---|
| **A1** | **Turn on ADR-0017's offline embedding model on the VM.** Add `SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=true` to the VM's `.env`, and add the same key to the **`worker`** service's `environment:` block, not only `api` — the VM's worker container has it set nowhere today. | VM `.env`; `docker-compose.yml:442` (add a `worker` twin) | Turns ~84 speakers from `unknown` to `measured` on §9. Without it, even a perfectly targeted request only scores the ~12% with no topic text. | 15 min | Low. Off-by-default flag, already approved (ADR-0017), no vendor, no network, no credential. It **does** change stored scores, so any before/after comparison must not mix the two. |
| **A2** | **Give the 60 imported events industry + role targets** — or, cleaner, **stop the import creating queue-visible pseudo-requests** and file real Speaker Requests instead. Preferred shape: raise `SPEAKER_REQUEST_COUNT` from 3 to ~10 and vary their targets, so the queue is full of things that actually work. | `gen:390`, `gen:1247-1324` | The match-run demo, end to end. | 2-3 h | Low if done by filing through the real API (validation stays in force). **Do not** INSERT `speaker_request_classification` rows directly — that bypasses `SpeakerRequestDraft` and mints the same class of half-valid row we are trying to remove. |
| **A3** | **File at least one physical Speaker Request** and give the roster ZIPs. Requires A4. | `gen:1316` | Exercises `cba-physical-1` and the OQ-CBA-024 ZIP-centroid table, which no seeded run has ever touched. | 1 h (after A4) | Low |
| **A4** | **Emit a Californian ZIP per professional** in the import rows so `speaker_profile.location_postal_code` is populated. Today `plan` computes a lat/long that is discarded, and `metro_region` is not mapped to `location_city`. | `plan:746`, `gen:694-730` | Proximity, the campus heatmap, and any §10 surface. | 2-3 h | Medium — check the ZIP is in the released centroid table, or the factor is still unknown and nothing improves. Keep `UNKNOWN_LOCATION_SHARE` so the honest-absence case stays reachable. |
| **A5** | **Seed `prior_talk`** on a share of profiles (0/100 today). | `gen:694-730` | Richer §9 evidence; the second topic-evidence column is currently dead. | 1 h | Low |
| **A6** | **Seed the reward catalogue.** `reward_item` and `redemption` are both 0, so 187 ledger entries have nothing to spend against. Needs owner-supplied values (see (c) D3). | `tools/seed_pilot_rewards.py` via `scripts/reset_pilot_dataset.sh` | Student rewards screen. | 30 min | Low |
| **A7** | **Seed `event_registration` and `cba_meeting`** (0 rows each). | `gen` phase C | Student registration flow; the meetings page shipped in #130. | 2-3 h | Low |
| **A8** | **Seed outreach drafts.** No seed path writes any; the VM's 4 rows have unexplained provenance. | `gen` | Outreach screen after a clean rebuild. | 1-2 h | Low |
| **A10** | **Re-point the self-scoped rows at the demo logins** — credit `point_ledger_entry` and write `attendance_record` for the account the student actually signs in as, and file at least one Speaker Request with the **host** token so `VolunteerMyRequests` is non-empty. | `gen:1146-1151`, `gen:2113-2118`, `gen:2513-2520` | Student rewards, student agenda, student feedback, Event Host my-requests — four screens that are empty today for a reason nobody would guess from looking at the row counts. | 3-4 h | Medium. Touches which principal performs which write; keep every write going through the real route so no authorization is bypassed. |
| **A11** | **Add the three missing tokens back to `SMARTMATCH_DEV_PRINCIPALS`** in the rebuild script. | `scripts/reset_pilot_dataset.sh:198-211` | Student, host and admin portals after a rebuild. | 15 min | Low. Looks like a straightforward omission; reported, not fixed. |
| **A9** | **Fix the stale strings and the drifted test.** (i) `gen:1732`, `:1764-1768`, `:2488`, `:2551` and `plan:216` still say "half the roster" after `CONTACT_CHANNEL_SHARE` moved to 0.75. (ii) `test_topic_fixture_pilot_coverage.py:393-408` guards the **event** description literal (`gen:1001`) while §9 actually compares the **Speaker Request** description (`gen:1319-1323`) — the guard passes over a pair set that no longer reflects reality. (iii) `pilot-dataset-rebuild.md:289-300` says 6 scored / 38 excluded; `local-dev-walkthrough.md:237-246` and ADR-0017 say 5 / 39. | as listed | Trust in the docs and the gate. | 1-2 h | Low. Reported, not fixed — see "Scope discipline". |

### (b) Needs an application or schema change

| # | Item | Why | Migration? |
|---|---|---|---|
| **B1** | **Distinguish an imported calendar event from a filed Speaker Request.** Options: (i) a third `event.origin` value, e.g. `import` — **needs a migration**, `ck_event_origin` is a CHECK constraint (`schema.py`, `events.py:144-150`); (ii) filter the queue on "has at least one `speaker_request_classification`" — **no migration**, but it silently hides imported events rather than naming them; (iii) leave the data alone and fix only the seed (A2). | The queue currently offers 60 events that cannot produce a shortlist. | (i) **yes**; (ii)/(iii) **no** |
| **B2** | **Pre-flight the request in the match-run UI.** `CoordinatorMatchRuns.tsx` already disables ineligible *contacts* and shows why. It does not check the *request*. A request with no targets could be flagged before submission — the data is already on the list response. | Turns a 422 after selecting 12 speakers into a disabled row with a reason. | **no** |
| **B3** | **Decide what to do with the dead IA Admin routes.** `/dashboard`, `/volunteers`, `/calendar`, `/outreach`, `/pipeline` call `/api/data/*` endpoints no backend serves. Either delete the routes or build the endpoints. | They error rather than render empty, which reads as a broken app. | **no** |
| **B4** | **Map `metro_region` → `location_city`** on ingest, or add a ZIP column to the import contract. | `metro_region` is a required import column that reaches nothing in `services/`. | **no** for the mapping; a new import column is a contract change |

**Migration warning.** Only **B1 option (i)** requires a migration. The pilot VM's
deploy path treats migrations as forward-only and irreversible
(`scripts/vm/deploy.sh`), and the current Alembic head is `0034_cba_meeting`.
Everything else in this plan — including all of section (a) — is data and
configuration only. **Recommendation: do not take B1(i) for the demo.** Take A2,
and revisit the origin vocabulary as its own card.

### (c) Needs a decision from you

| # | Question | Recommendation |
|---|---|---|
| **D1** | **Should `SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED` be `true` on the pilot VM?** ADR-0017 approved the model; nobody turned it on. Scores produced under it are not comparable with scores produced without it. | **Yes, turn it on**, and rebuild the dataset once afterwards so no stored run straddles the change. It is approved, offline, vendor-free and credential-free. This is the single highest-value change in the plan. |
| **D2** | **Should the imported 60 events appear in the Speaker Request queue at all?** This is the `event.origin` vocabulary question (B1). | Say they should **not**. Fix it in the seed first (A2, no migration); if a permanent distinction is wanted, that is a separate card with a migration. |
| **D3** | **What reward items, at what point costs?** `seed_pilot_rewards.py` requires every value and defaults nothing, deliberately. | Give me 3-5 item names and costs and A6 is 30 minutes. |
| **D4** | **Should §19 classification be mandatory at ingest?** Today it is not: 15% of the roster is left unclassified and 20% unreviewed, both on purpose, so the honest-absence states stay demonstrable. | **Keep it optional.** Those states are the product's differentiator. If the demo looks too empty, raise the *reviewed* share (`gen:1202-1217`) rather than making review mandatory. |
| **D6** | **Are the IA Admin routes in scope at all?** They call an API surface that does not exist. | Delete them from `routes.tsx` for the pilot. Building five legacy endpoints is not demo work. |
| **D5** | **Which industry vocabulary?** Already settled — released NAICS sectors at `cba-naics-2026-09-04`, roles at `cba-roles-2026-09-04`. | No decision needed. Flagging only so nobody re-opens it. |

---

## 5. Environment notes

- The 3 unit-test failures on the development machine are the known untracked
  local `.env`. Pre-existing, unrelated, not a regression, and not touched here.
- The VM was inspected **read-only**. No container was restarted, nothing was
  deployed, and nothing was written.
- This plan deliberately stays out of the files three other agents are working
  in: the `CoordinatorSpeakerFeedback` N+1 fan-out, DB connection-pool sizing,
  and the post-login portal redirect.
- The VM deploys `origin/deploy` (`scripts/vm/deploy.sh:87`); the local
  `production-VM` branch is behind `origin/main` by 17 commits, so confirm which
  SHA is actually live before reading any of the counts above as current.
