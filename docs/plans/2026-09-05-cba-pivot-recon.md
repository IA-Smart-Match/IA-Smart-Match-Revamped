# CBA pivot reconnaissance synthesis

**Date:** 2026-09-05  
**Mode:** planning/reconnaissance only; no implementation authorization  
**Authority:** [`docs/product/cba-smart-match-customer-requirements.md`](../product/cba-smart-match-customer-requirements.md)

## Baseline and evidence limits

- The current checkout is `main`, observed **4 commits behind `origin/main`**. This recon describes the working tree, including uncommitted/untracked prior-agent documentation. No fetch, pull, merge, rebase, reset, branch switch, commit, or push was performed.
- The migration chain in this tree ends at [`0021_outreach_schema.py`](../../db/migrations/versions/0021_outreach_schema.py). The checked-in OpenAPI contract has **25 paths and 27 operations**.
- `make` is unavailable in the observed PowerShell environment. No `make check` result is claimed. Baseline counts were obtained with a read-only Python command.
- The source customer document and the in-repository copy are text-equivalent after CRLF/LF normalization.
- Dispositions below are exclusive: **preserve** (working architecture/capability), **gate** (retain but keep off CBA paths), **build new** (implementation is missing or superseded), and **defer-OQ** (a product/architecture decision must precede implementation).

## Executive finding

The repository is not a greenfield. It already has a durable command/job pattern, tenant-scoped authorization, a backend-derived pilot login, immutable match runs, two implemented matching factors, read-only event catalog, import/review flow, consent-gated outreach, pipeline metrics, rewards, and the R/Y/G discovery direction. The CBA pivot should preserve those seams.

The largest gaps are the CBA data model and workflows: the current approved matcher is the superseded 70/30 lexical-topic/straight-line-kilometer model; event writes are absent; the contact contract lacks the CBA columns and classifications; student registration/calendar/feedback are not wired; and stored role strings and portal labels still describe the earlier IA-West personas. Neutral Topic scoring and virtual-event redistribution conflict with the accepted accountable-numbers policy and require an ADR before the CBA registry can merge.

## Matching

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Four dimensions and 30/25/15/30 defaults | The approved registry contains only `topic_relevance` 0.70 and `travel_burden` 0.30 ([`factor_registry.py:55-68`](../../python/smartmatch_domain/smartmatch_domain/factor_registry.py), [`factor_registry.py:150-175`](../../python/smartmatch_domain/smartmatch_domain/factor_registry.py)); the approved key set is exactly those two ([`factor_registry.py:191-196`](../../python/smartmatch_domain/smartmatch_domain/factor_registry.py)). | P0 | build new | CBA-MATCH-REGISTRY |
| Centralized, Connector-adjustable weights | `normalize_weights()` already accepts overrides, ignores non-scoring keys, and normalizes implemented factors ([`factor_registry.py:299-337`](../../python/smartmatch_domain/smartmatch_domain/factor_registry.py)); no persistence or Connector settings API exists. | P0/P1 | build new | CBA-MATCH-WEIGHTS |
| Industry and Role factors | No Industry or CBA Role factor is registered or scored; `scoring.py` calls only Topic and Travel ([`scoring.py:197-198`](../../python/smartmatch_domain/smartmatch_domain/scoring.py)). | P0 | build new | CBA-MATCH-INDUSTRY-ROLE |
| Semantic Topic, fit score, one-sentence reasoning | Topic uses normalized exact set overlap ([`topic_relevance.py:103-170`](../../python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py)); explanations preserve factor basis/state, but do not provide the requested semantic provider and purpose-built one-sentence Topic rationale ([`explanation.py:130-174`](../../python/smartmatch_domain/smartmatch_domain/explanation.py)). | P0 | build new | CBA-MATCH-TOPIC |
| Neutral Topic when evidence is thin | Current Topic returns `None` when expertise or event topics are absent ([`topic_relevance.py:112-130`](../../python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py)); ADR-0011 requires unknown to remain nonnumeric ([`ADR-0011:50-59`](../architecture/decisions/ADR-0011-accountable-numbers.md)). A customer-directed neutral value needs explicit provenance/policy. | P0 | defer-OQ | CBA-SCORING-ADR / OQ-CBA-004 |
| CPP-campus miles and 0–25/25–75/75+ bands | Current Travel is a Haversine **kilometer** penalty between two synthetic points, free to 16 km and saturated at 160 km ([`travel_burden.py:45-61`](../../python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py), [`travel_burden.py:128-169`](../../python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py)). It is not CPP-origin mile-band suitability. Exact band scores and boundary ownership are unresolved. | P0 | defer-OQ | CBA-SCORING-ADR / OQ-CBA-002, then CBA-MATCH-PROXIMITY |
| Virtual events ignore Proximity and redistribute 30% | Current scoring has no virtual-event conditional registry. ADR-0011/current explanations explicitly do not re-spread unknown factor weight ([`explanation.py:200-220`](../../python/smartmatch_domain/smartmatch_domain/explanation.py)). | P0 | defer-OQ | CBA-SCORING-ADR / OQ-CBA-001 and OQ-CBA-004 |
| Return approximately 2–3 candidates | The presentation constants are 2 and 3 ([`explanation.py:90-107`](../../python/smartmatch_domain/smartmatch_domain/explanation.py)); the optimizer is deterministic CP-SAT and requires an explicit portfolio size ([`optimizer.py:37-51`](../../python/smartmatch_domain/smartmatch_domain/optimizer.py), [`optimizer.py:170-207`](../../python/smartmatch_domain/smartmatch_domain/optimizer.py)). | P0 | preserve | CBA-MATCH-REGISTRY (regression ownership) |
| No prominent overall percentage | Existing explanation policy labels values “heuristic score” and forbids percentage presentation ([`explanation.py:20-39`](../../python/smartmatch_domain/smartmatch_domain/explanation.py)). | P0 interpretation | preserve | CBA-MATCH-REGISTRY (regression ownership) |
| Versioned, reproducible match runs | Match-run command, worker, snapshot, and API already exist; the API mounts `match_runs.router` ([`main.py:228-239`](../../services/api/smartmatch_api/main.py)). The CBA registry and formulas need new pins/golden approval rather than in-place reinterpretation. | P0 architecture | preserve | CBA-MATCH-REGISTRY |

## Roles, authorization, and terminology

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| One standard login; no role chooser | The login body accepts only email/password and forbids extras ([`auth.py:140-166`](../../services/api/smartmatch_api/routers/auth.py)); the frontend has one form and navigates to `/` after obtaining an opaque token ([`LoginPage.tsx:81-114`](../../apps/web/legacy-frontend/src/app/pages/LoginPage.tsx)). | P0 | preserve | CBA-ROLE-PRESENTATION (regression ownership) |
| Backend-assigned role and dashboard | Login returns no identity; the frontend resolves `/v1/me` and `/v1/me/portals` ([`LoginPage.tsx:30-38`](../../apps/web/legacy-frontend/src/app/pages/LoginPage.tsx)). Portal descriptors derive from active server memberships, and portal listing is explicitly not authorization ([`portals.py:24-46`](../../services/api/smartmatch_api/routers/portals.py)). | P0 | preserve | CBA-ROLE-PRESENTATION |
| Student, Event Host, Speaker Connector, Speaker presentation | Stored/seeded role strings are `student`, `coordinator`, `volunteer`, `admin`; portal labels remain “Event coordinator”, “Volunteer”, and “IA West admin” ([`portals.py:179-194`](../../services/api/smartmatch_api/routers/portals.py)). Stable storage strings, visible labels, and powers are separate concerns; labels must never widen authz. | P0 | build new | CBA-ROLE-PRESENTATION |
| CBA terminology and requested renames | Login and landing UI still contain IA-West text ([`LoginPage.tsx:121-151`](../../apps/web/legacy-frontend/src/app/pages/LoginPage.tsx)); routes and pages retain opportunities/volunteer/admin vocabulary ([`routes.tsx:110-143`](../../apps/web/legacy-frontend/src/app/routes.tsx)). | P0 | build new | CBA-TERMINOLOGY |
| Remove membership/dues concepts from CBA presentation | Membership is also the backend authorization record and must not be renamed away internally. Customer-facing chapter-membership/dues narrative must be removed or gated while authz membership rows remain. | P0 | build new | CBA-SCOPE-COMPOSITION |
| Preserve deny-by-default authorization | Existing unit routes load a tenant-scoped resource then require explicit role sets; events use `admin`/`coordinator` ([`events.py:94-108`](../../services/api/smartmatch_api/routers/events.py), [`events.py:275-310`](../../services/api/smartmatch_api/routers/events.py)). | P0 architecture | preserve | Every API track |

## Events, calendar, and registration

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Preserve event browse | The event API has two read-only routes; presentable event listing is `GET /v1/units/{unit_id}/events` ([`events.py:1-23`](../../services/api/smartmatch_api/routers/events.py), [`events.py:343-375`](../../services/api/smartmatch_api/routers/events.py)). It is currently limited to admin/coordinator, so a student browse read model/authorization is still needed. | P0 preserve/build | build new | CBA-STUDENT-EVENTS |
| Event Host creates a Speaker Request | The event router explicitly writes nothing and has only GET routes ([`events.py:1-23`](../../services/api/smartmatch_api/routers/events.py)). Fixture ingest is a worker seam, not a Host write contract. | P0 | build new | CBA-EVENT-REQUEST |
| Request includes multi-industry, multi-role, Topic, location, virtual flag | Current event response exposes title, description, time, and the separate ADR-0012 event tag vocabulary ([`events.py:181-201`](../../services/api/smartmatch_api/routers/events.py)). The 12 event type/speaker-function tags are not the 10 CBA career roles; CBA classification must be a distinct closed taxonomy. | P0 | build new | CBA-DATA-SCHEMA |
| Preserve registration intent | The student page says the registrations dataset has no current backend ([`StudentEvents.tsx:1-15`](../../apps/web/legacy-frontend/src/app/pages/student/StudentEvents.tsx), [`StudentEvents.tsx:39-53`](../../apps/web/legacy-frontend/src/app/pages/student/StudentEvents.tsx)). | P0 preserve/build | build new | CBA-STUDENT-EVENTS |
| Preserve calendar and keep month calendar at bottom of Events page | ICS domain/golden scaffolding exists, but the current student Events page contains only an unavailable registrations panel. The customer’s newer explicit placement requirement controls: preserve browse/agenda content and render the month calendar **below it**, not instead of it. | P0 | build new | CBA-STUDENT-EVENTS |
| Physical/virtual time and truthful event identity | Existing event reads preserve temporal precision/provenance and withhold unresolved/quarantined entries ([`events.py:139-179`](../../services/api/smartmatch_api/routers/events.py), [`events.py:350-370`](../../services/api/smartmatch_api/routers/events.py)). ADR-0012 requires manual entry to use the same deterministic identity/vocabulary invariants ([`ADR-0012:98-110`](../architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md)). | P0 architecture | preserve | CBA-EVENT-REQUEST |

## Contacts, import, and classification

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Import existing records, not external acquisition | `POST /v1/units/{unit_id}/imports` queues a durable command for admin/coordinator ([`imports.py:68-78`](../../services/api/smartmatch_api/routers/imports.py), [`imports.py:191-242`](../../services/api/smartmatch_api/routers/imports.py)); inline rows flow through quarantine/review. | P1 | preserve | CBA-IMPORT-CLASSIFY |
| CBA source columns and matching fields | The ratified professional contract currently requires `name` and `metro_region`, with company/title/expertise/initials/pronouns optional ([`columns.yaml:127-172`](../pilot-data/columns.yaml)). It lacks the customer’s email, alumni, graduation year, major, willingness, past engagement, primary classifications, Topic text, and city/ZIP contract. | P0/P1 | build new | CBA-DATA-SCHEMA |
| 20 NAICS sectors and 10 CBA role categories | Neither taxonomy exists in the current domain. ADR-0012’s 12-term event vocabulary is a different concept and must not be reused as CBA career roles. | P0 | build new | CBA-TAXONOMY |
| Speaker has one primary Industry and one primary Role; event is multi-select | Existing professional persistence links identity to units and stores `board_role`, not CBA primary classifications ([`professionals.py:130-168`](../../python/smartmatch_persistence/smartmatch_persistence/professionals.py)). Current event schema/read shape has generic mapped tags, not the required cardinalities. | P0 | build new | CBA-DATA-SCHEMA |
| Connector manually adds a contact | The import endpoint supports inline batches, but no unit-scoped professional/contact create operation exists in the mounted router set ([`main.py:228-244`](../../services/api/smartmatch_api/main.py)). | P0 | build new | CBA-CONTACT-MANAGEMENT |
| Infer classifications, then Connector corrects them | The worker validates columns and creates review items; it has no CBA company/title classifier or correction API. The filesystem-backed YAML contract is fail-closed ([`column_contract.py:1-13`](../../services/worker/smartmatch_worker/column_contract.py), [`column_contract.py:53-61`](../../services/worker/smartmatch_worker/column_contract.py)). | P0/P1 | build new | CBA-IMPORT-CLASSIFY and CBA-CONTACT-MANAGEMENT |
| Consent remains authoritative | Current outreach records use `contact_channel`; composition checks consent before rendering text ([`outreach.py:326-399`](../../services/api/smartmatch_api/routers/outreach.py)). New CBA contact entry/classification must not imply send eligibility. | P0 architecture | preserve | CBA-CONTACT-MANAGEMENT |

## Outreach, invitations, and handoff

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Preserve consented invitation path | The API can create/list drafts, queue a send, read a send/delivery events, and unsubscribe ([`outreach.py:316-438`](../../services/api/smartmatch_api/routers/outreach.py), [`outreach.py:515-640`](../../services/api/smartmatch_api/routers/outreach.py)). Worker-side consent is rechecked at delivery time. Fixture/live selection remains fail-closed. | P1 architecture | preserve | CBA-INVITATIONS |
| Batch invitations | Existing send is one approved draft at a time; no shortlist batch command is present. | P1 | build new | CBA-INVITATIONS |
| Track responses/acceptances | Delivery events track transport, not a Speaker’s invitation accept/decline response or engagement acceptance state. | P1 | build new | CBA-INVITATIONS |
| Confirmed-speaker handoff to Event Host | Pipeline has confirmed/attended stages but no CBA Host-facing handoff read model. `member_inquiry` remains a stored historical stage and is not a CBA outcome. | P1 | build new | CBA-HANDOFF-PIPELINE |
| No cold unknown-contact outreach | Legacy `Outreach.tsx`, `AgenticOutreachPanel`, specialist discovery helpers, and scraping acquisition copy use a different trust model. They must remain off CBA paths; they must not be adapted into the consented `/v1` path. | P0 boundary | gate | CBA-SCOPE-COMPOSITION |

## Student feedback

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Student rates a speaker; Connector can view | Existing [`feedback.py`](../../python/smartmatch_domain/smartmatch_domain/feedback.py) is coordinator feedback on match outcomes and weight proposals, not student-to-speaker feedback. No student rating route is mounted. | P0 | defer-OQ | CBA-STUDENT-FEEDBACK / OQ-CBA-003 |
| Do not over-design schema | Scale, fields, edits, anonymity, retention, and aggregation are unspecified in customer §16/§26. A decision record and authz contract must precede migration/API/UI. | P0 | defer-OQ | CBA-STUDENT-FEEDBACK / OQ-CBA-003 |

## Pipeline, metrics, discovery, and rewards

| CBA requirement | Current implementation and evidence | Priority | Disposition | Owning track |
|---|---|---:|---|---|
| Preserve R/Y/G discovery feed | The customer explicitly preserves it. Existing metric/pipeline architecture should be retained and relabeled, not redesigned because the customer changed. | P0 architecture | preserve | CBA-TERMINOLOGY |
| Preserve `matched`, `contacted`, `confirmed`, `attended` evidence | The domain sequence and persistence support all five historical stages ([`pipeline.py:45-88`](../../python/smartmatch_domain/smartmatch_domain/pipeline.py)); Wave 5 should reuse the four CBA-relevant stages. | P1 | preserve | CBA-HANDOFF-PIPELINE |
| `member_inquiry` narrative/writer | `member_inquiry` is a real stored stage ([`pipeline.py:45-73`](../../python/smartmatch_domain/smartmatch_domain/pipeline.py)), but CBA has no approved equivalent. Preserve history/schema, suppress its CBA narrative/tile, and prohibit new CBA writers unless an approved outcome decision renames/redefines it. | gated | gate | CBA-SCOPE-COMPOSITION |
| Rewards/points remain | Rewards routes and durable redemption behavior are mounted ([`main.py:228-239`](../../services/api/smartmatch_api/main.py)); customer §4 says **Keep**, while §25 places only refinements/wording in P2. Do not disable the entire capability merely because chapter membership is removed. Keep truthful ledger-backed surfaces; gate only IA-West wording, unfunded/incomplete controls, or claims that do not hold. | P2 refinement | preserve | CBA-REWARDS-REFINEMENT |
| Discoverability/metric truth | ADR-0011’s canonical definitions, one owning query, and exact drill-down remain binding ([`ADR-0011:61-88`](../architecture/decisions/ADR-0011-accountable-numbers.md)). | cross-cutting | preserve | Every metrics/UI track |

## Gated scope

| Capability | Evidence and CBA disposition | Disposition | Owner |
|---|---|---|---|
| External speaker discovery, scraping, LinkedIn, external event discovery | Customer §20 prohibits it. G3 explicitly rejects LinkedIn and does not authorize live targets ([`g3-crawler-decision.md:73-94`](../decisions/g3-crawler-decision.md), [`g3-crawler-decision.md:271-277`](../decisions/g3-crawler-decision.md)). Preserve fixture parsing for tests; hide live crawl/acquisition controls. | gate | CBA-SCOPE-COMPOSITION |
| Cold outreach to unknown contacts | Legacy discovery/outreach UI must not be mounted on CBA paths. Consent-gated `/v1` outreach is preserved. | gate | CBA-SCOPE-COMPOSITION |
| Chapter membership and dues | Remove customer-facing narrative and writers; do not delete backend `membership` authorization records. | gate | CBA-SCOPE-COMPOSITION |
| Large branding-only work | CPP green/gold is P2 and must not delay functionality. `apps/web/DESIGN.md` Part 2 remains open ([`DESIGN.md:180-199`](../../apps/web/DESIGN.md)). | gate | CBA-REWARDS-REFINEMENT (copy only) / future design |
| Live providers and deployment | Current API settings default to fixtures and enforce classroom isolation ([`config.py:20-42`](../../services/api/smartmatch_api/config.py), [`config.py:59-91`](../../services/api/smartmatch_api/config.py)). No planning artifact authorizes live data, providers, credentials, or cloud apply. | gate | all tracks |

## Unified §25 ownership map

Each P0 checklist item is listed once below. “OQ → track” means the item is owned by the named track but cannot ship until the listed decision is approved.

| # | Customer §25 P0 item | Sole owner or decision dependency |
|---:|---|---|
| 1 | Replace IA West terminology with CBA terminology | CBA-TERMINOLOGY |
| 2 | Member → Student | CBA-TERMINOLOGY |
| 3 | Event Organizer / Volunteer → Event Host | CBA-ROLE-PRESENTATION |
| 4 | Chapter Admin → Speaker Connector | CBA-ROLE-PRESENTATION |
| 5 | Chapter Admin Dashboard → Connector Dashboard | CBA-TERMINOLOGY |
| 6 | Member Portal → Student Portal | CBA-TERMINOLOGY |
| 7 | Volunteer Opportunity → Speaker Request | CBA-TERMINOLOGY |
| 8 | Remove membership / dues references | CBA-SCOPE-COMPOSITION |
| 9 | Keep one standard login | CBA-ROLE-PRESENTATION (preserve/regression) |
| 10 | Assign roles from backend | CBA-ROLE-PRESENTATION (preserve/regression) |
| 11 | Add Industry matching dimension | CBA-MATCH-INDUSTRY-ROLE |
| 12 | Add Role matching dimension | CBA-MATCH-INDUSTRY-ROLE |
| 13 | Default weights 30 / 25 / 15 / 30 | CBA-MATCH-REGISTRY |
| 14 | Centralize weights in configurable settings | CBA-MATCH-WEIGHTS |
| 15 | Add 20 NAICS options | CBA-TAXONOMY |
| 16 | Add 10 role categories | CBA-TAXONOMY |
| 17 | Speaker one primary Industry | CBA-DATA-SCHEMA |
| 18 | Speaker one primary Role | CBA-DATA-SCHEMA |
| 19 | Connector corrects Industry | CBA-CONTACT-MANAGEMENT |
| 20 | Connector corrects Role | CBA-CONTACT-MANAGEMENT |
| 21 | Event multiple Industries | CBA-DATA-SCHEMA |
| 22 | Event multiple Roles | CBA-DATA-SCHEMA |
| 23 | AI Topic comparison | CBA-MATCH-TOPIC |
| 24 | One-sentence Topic reasoning | CBA-MATCH-TOPIC |
| 25 | Neutral Topic score for missing data | OQ-CBA-004 → CBA-MATCH-TOPIC |
| 26 | Distance scoring in miles | CBA-MATCH-PROXIMITY |
| 27 | 0–25 / 25–75 / 75+ bands | OQ-CBA-002 → CBA-MATCH-PROXIMITY |
| 28 | Ignore Proximity for virtual events | OQ-CBA-001/OQ-CBA-004 → CBA-MATCH-PROXIMITY |
| 29 | Return approximately 2–3 candidates | CBA-MATCH-REGISTRY (preserve/regression) |
| 30 | Event Host adds event | CBA-EVENT-REQUEST |
| 31 | Connector adds contact | CBA-CONTACT-MANAGEMENT |
| 32 | No external scraping/discovery | CBA-SCOPE-COMPOSITION |
| 33 | Student speaker feedback/ratings | OQ-CBA-003 → CBA-STUDENT-FEEDBACK |
| 34 | Month calendar at bottom of Events page | CBA-STUDENT-EVENTS |

## Priority summary

- **P0:** scope composition; CBA terminology and persona presentation; taxonomies/schema; scoring ADR; four-factor matching; Host request creation; Connector contact creation/correction; student feedback decision and implementation; student browse/registration/calendar composition.
- **P1:** import classification; adjustable weights; batch invitations; responses; confirmed-speaker handoff.
- **P2:** CPP visual changes and CBA rewards/points wording/refinements. Existing truthful rewards behavior remains available unless a specific defect requires a narrow gate.

