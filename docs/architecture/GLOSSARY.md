# Glossary

**Stage 2, writer A.** 8 September 2026. Published by migration increment
**M1**. Resolves the terminology hazard recorded in `domain-model.md` §4 and
the "write a glossary" disposition in `CURRENT_ARCHITECTURE_AUDIT.md` §16.

Every term below is given as: **what it means in its context** · **what it does
not mean** · **the code or table that anchors it**. Table names were read from
`python/smartmatch_persistence/smartmatch_persistence/schema.py`, which today
contains **44** `sa.Table` definitions (Stage 1 reports 43; the module is
authoritative).

---

## 0. Why a glossary and not a rename

A rename looks like the cheaper fix. It is not, and four independent pieces of
evidence say so.

1. **`domain-model.md` §4 names the collisions and rules renaming out.** Four
   unrelated things are called "event"; "review" is two quarantines; speaker /
   professional / contact / specialist are four names with overlapping
   referents. Its recommendation is explicit: *"Do not rename tables. Do
   produce a domain glossary."* The cost of a collision is paid by every new
   reader — a glossary is a one-time payment; a rename is a migration plus a
   re-verification of everything above it.

2. **ADR-0004 makes the table names load-bearing.** The schema is hand-written,
   not reflected, and *composite tenant-safe keys are the point*.
   `test_schema_matches_migration.py` states it directly: reflection *"would
   not reliably preserve them"*. A rename is therefore not a metadata edit; it
   is a hand-written change to a key structure that carries the tenancy
   guarantee, propagated through 81 foreign keys of which 68 are `RESTRICT`.

3. **33 migrations reference these names.** `0001`→`0033` is a linear chain,
   one transaction per migration (ADR-0009), applied from empty on every PR.
   Renaming a table means either rewriting history — which the parity guard
   compares against — or adding a rename migration whose only product is churn
   in the one file every persistence change already touches (R-20).

4. **ADR-0011 and the factor registry make names into recorded commitments.**
   `SUPERSEDED_G1_MODEL`, `SUPERSEDED_REGISTRY_VERSION` and
   `SUPERSEDED_SCORING_KEYS` exist because superseded identifiers are
   *retained* rather than deleted, so that a past score stays reproducible.
   A vocabulary that is deliberately append-only cannot be tidied by renaming.

There is a fifth, narrower reason. `tools/scan_cba_terminology.py` already
polices CBA-visible *copy* — it fails the build on "IA West", "chapter",
"Member Portal", "volunteer opportunity", "membership/dues" — and it is
deliberately **scoped** to the frontend source plus a named list of backend
files whose string literals are rendered. That scoping exists precisely so the
scanner does not demand renaming the authorization `membership` row or the
`ia_west_legacy` product scope. The repository has already decided that *copy*
and *identifiers* are governed differently. This glossary is the identifier
half of that decision.

---

## 1. The collisions in `domain-model.md` §4

### membership

| Context | Means | Does **not** mean | Anchor |
|---|---|---|---|
| Identity & Access / authz | A role assignment at an `OrgPath`, optionally covering the subtree. Assembled server-side into a `Principal` | Anything a user buys, renews, or lapses | `smartmatch_authz/policy.py:170`; table `membership` (`schema.py:165`); GiST index `ix_membership_path_gist` |
| IA-West legacy product | Chapter dues — a **retired** product concept | Anything the CBA product does | `scan_cba_terminology.py` fails the build on this word in CBA-visible copy, and carves the authz row out of its scan explicitly |

**Rule.** In this repository `membership` is authorization, always. Dues
vocabulary is a build failure in copy and does not exist in the schema.

### event — four unrelated things

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| `event` | Event Catalog | A real-world happening, with a value-typed time (`ExactTime` / `DateOnlyTime` / `UnresolvedTime`) and an `EventIdentityKey` for dedupe across ingestion sources | A message, a log record, or anything in the job path | table `event` (`schema.py:1052`); `domain/events.py`; ADR-0010, ADR-0012 |
| `job_event` | Work Substrate | One durable record in a job's lifecycle stream, read via `GET /v1/jobs/{id}/events` | A calendar event. Nothing here is user-facing content | table `job_event` (`schema.py:274`) |
| `delivery_event` | Outreach | A signal about one email delivery, arriving *after* the send | Proof that a send succeeded — the API returns a job id and reports no delivery status | table `delivery_event` (`schema.py:1875`); `DeliveryEventType` |
| `contact_channel_transition` | Speaker Relationship | The append-only **log** of consent-state changes on one channel — arguably a fourth "event" | The channel's current state, which is a column on `contact_channel` | table `contact_channel_transition` (`schema.py:1642`), migration `0023` |

**Rule.** Unqualified "event" means the real-world happening. The other three
are always written with their prefix, in prose as well as in code.

### speaker · professional · contact · specialist

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| `speaker_profile` | Speaker Relationship | The person a student hears from | Their relationship to any particular unit | table `speaker_profile` (`schema.py:1961`); index `ix_speaker_profile_unit_folded_name` |
| `professional_unit_relationship` | Speaker Relationship | One professional's relationship to one org unit | The person themselves | table `professional_unit_relationship` (`schema.py:974`) |
| `contact_channel` | Speaker Relationship (privacy core) | An addressable way to reach a person **plus its consent state** | A person, and never a licence to write to them — `is_send_eligible` decides that | table `contact_channel` (`schema.py:1565`); `domain/consent.py`; ADR-0014 |
| `cba_contacts` | CBA roster | The CBA-scoped roster surface — domain module, repository and router | A separate person entity | `routers/cba_contacts.py`, `routers/cba_contact_channels.py` |
| "Speaker Connector" | Customer vocabulary §13 | The **role** that maintains the roster | A table or a code symbol | customer requirements §13 |
| "Event Host" | Customer vocabulary §12 | The role that files a Speaker Request | A speaker | `routers/speaker_requests.py`; `Capability.SPEAKER_REQUEST_INTAKE` |
| `Specialist` | Frontend legacy types | **Retired IA-West term**, surviving as an exported TypeScript interface | Anything current. Also `CppEvent`, `CrawlerEvent` | `apps/web/legacy-frontend/src/lib/api.ts` |

**Rule.** `Specialist`, `CppEvent` and `CrawlerEvent` are types, not copy, so
the terminology scanner does not see them (`domain-model.md` §3.5). Read them
as dead vocabulary. They disappear with the M3 generated client and the M8
legacy-page decision, not by a rename.

### review — two quarantines

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| `review_item` | Ingestion & Review | The quarantine for a row an **import** produced, before it becomes real data | Anything about events discovered from a source | table `review_item` (`schema.py:812`); `routers/review.py` |
| `discovery_review_item` | Event Catalog | The quarantine for an **event discovered** by ingestion, before it is publishable | An imported record | table `discovery_review_item` (`schema.py:1271`) |

**Rule.** Both are quarantines and neither is code review. Never write "the
review queue" without saying which.

### match — three things

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| `match_run` | Matching | An **immutable snapshot of a decision**, reproducible from `weights_fingerprint` + `inputs_fingerprint` + `MatchRunPins` | A live query, or something to be recomputed on read | table `match_run` (`schema.py:1338`), migration `0018`; `domain/match_run.py` |
| `match_weight_setting` / `match_weight_setting_revision` | Matching | The **configuration** a run pins, and its revision history | The run itself | `schema.py:2310,2368`, migration `0027`; `scoring_mode` added `0032` |
| `industry_match`, `role_match` | Matching / factors | Individual **factors** contributing to one candidate's score | The run or its weights | `domain/factors/*` (6 modules), `domain/factor_registry.py` |

**Rule.** "Matching weights" configure; "match run" decides; "match" alone is
ambiguous and should not appear unqualified.

### scope — two things

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| `ProductScope` | Product policy | **Which product this is**, and which named capabilities the customer's current phase includes | Any deployment or environment fact. It can enable no live provider, no live data and no cloud deploy | `domain/product_scope.py`; values include `IA_WEST_LEGACY` |
| Authorization scope | Identity & Access | **Which org units** a principal reaches — an `ltree` path, subtree-covering or not | What the product offers. *Hiding a link removes a claim, not an access path* | `smartmatch_authz/policy.py:118 OrgPath`; two GiST indexes |

---

## 2. The command path vocabulary

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| **job** | Work Substrate | The unit of asynchronous work: one entity with **12** states — `queued`, `dispatched`, `running`, `succeeded`, `partial`, `failed_provider`, `failed_budget`, `failed_policy`, `cancelled`, `timed_out`, `redrive_pending`, `abandoned` | A thread, a cron entry, or a background task in process memory. Three distinct failure kinds are separate states so *why did this fail* is queryable, not greppable | `domain/jobs.py` (fan-in 17); table `job` (`schema.py:217`) |
| **command** | Work Substrate | A named intent submitted through `smartmatch_api.commands.submit_command`, recorded as `job` + `outbox_record` (+ `idempotency_record`) in **one transaction**. Three types reach the worker today: `import.create`, `match-run.create`, `outreach.send` | A function call, an RPC, or anything the API executes in-request. The API returns `202` and a job id, never a result | `smartmatch_api/commands.py`; `worker/handlers.py` `default_registry()`; `domain/match_run.py:75`, `domain/outreach.py:126` |
| **delivery** | Two contexts, and this is the trap | (a) **Task delivery** — Cloud Tasks handing one task to `POST /tasks/execute`, at-least-once, so a duplicate is the *normal* case answered `200`. (b) **Email delivery** — what a `delivery_event` reports about a message | Each other. A `200` on a task delivery says nothing about whether an email arrived | (a) `worker/main.py` docstring; (b) table `delivery_event` |
| **outbox** | Work Substrate | The transactional outbox: `outbox_record` rows written in the *same* transaction as the job, then claimed with `FOR UPDATE SKIP LOCKED` and turned into deterministically-named tasks | A queue product, and not a message broker. It is a table in the one PostgreSQL instance, by decision | table `outbox_record` (`schema.py:293`); index `ix_outbox_claimable`; ADR-0005, ADR-0007 |
| **lease** | Work Substrate | A time-bounded claim. Two of them: a **dispatcher lease** on an outbox row (`status=leased`, `lease_expires_at`), and a **job lease** written by `claim` and renewed by `TaskExecutor._emit` on each progress event | Ownership. `reclaim_stranded` treats an expired lease with spent attempts as failed; a `NULL` lease is *skipped*, not swept — it is what a release predating J9 wrote | `worker/dispatcher.py`, `worker/execution.py`; table `concurrency_lease`; index `ix_job_running_lease` |
| **generation** | Work Substrate | The counter that makes a re-driven attempt distinguishable: the new outbox row derives a *new* deterministic task name so it is not deduplicated against the original | A version of the data, or a schema version | ADR-0007 amendment; `command-path.md` §3 |
| **redrive** | Work Substrate | Moving a `failed_provider` or `timed_out` job to `redrive_pending`, then compare-and-set back to `queued` with a new generation. `POST /v1/jobs/{id}/redrive`, `Idempotency-Key` required, `409 redrive_conflict` on a lost race | A retry inside the worker — those are attempts. Redrive is an operator action with a recorded actor and reason | `routers/redrive.py`; table `redrive_record` (`schema.py:346`) |

---

## 3. Identity, scope and refusal

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| **principal** | Identity & Access | The authenticated actor, assembled **server-side** from `user_account` + `membership` after a subject is resolved | Anything in the request body. `scan_forbidden.py:61,166` makes reading `tenant_id` / `user_id` / `student_id` / `professional_id` from a payload a build failure (MM-A01) | `smartmatch_authz/policy.py:205`; `smartmatch_api/dependencies.py:86,119` |
| **unit** | Identity & Access | An `org_unit` — a node in the `ltree` hierarchy, and the prefix of **46 of 57** published paths | A deployment unit, a business unit in any external sense, or a test unit | table `org_unit` (`schema.py:118`); `units.load_unit_or_404`; `units.MAX_SUBTREE_UNITS` |
| **tenant** | Identity & Access | The isolation boundary, carried in **composite tenant-safe keys** rather than a session variable or row-level security | A customer account you can switch at runtime, and not a schema per customer | table `tenant` (`schema.py:106`); ADR-0004, ADR-0008, migration `0007`; `test_tenant_isolation.py` |

---

## 4. Gates — the WIP vocabulary that replaces `TODO`

There are **zero** `TODO`, `FIXME`, `HACK`, `XXX` markers and zero
`NotImplementedError`s repository-wide. Unfinished work is expressed as
*absence* and tracked by these named gates plus
`docs/plans/open-questions/*-deferred.md`. A gate is a **decision someone owes**,
not a task someone forgot.

| Gate | Owns the decision | Status | Anchor |
|---|---|---|---|
| **G1** — factor registry approval | Scoring policy owner | **CLOSED.** `REGISTRY_STATUS = "approved"` with a named approver | `domain/factor_registry.py:149,154`; `registry-supersession-record.md`. `main.py`'s docstring still says match-run commands "wait on G1" — stale, D1, corrected in M5 |
| **G2** — privacy / records review for live student data | The institution | **BLOCKED** (with D8) | `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` |
| **G3** — agent controls | Owner | Deferred. ADR-0003 excludes agents from Foundation regardless | `main.py` module docstring |
| **G4** — consent-origin policy | Owner | Carried by the R4 slice with implemented safe defaults | `docs/plans/open-questions/r4-outreach-deferred.md` |
| **G5** — Calendar API | Public-release planning | Deferred. The `.ics` download spends the one calendar permission granted and stops there | `docs/plans/open-questions/calendar-deferred.md`; `routers/calendar.py` |
| **A1b** — live institutional identity (JWKS against a real issuer) | The institution | Verifier written, 52 tests, **unwired**. `POST /v1/auth/login` against `pilot_credential` is the interim and *"is not A1b, does not unblock it"* | `main.py` docstring; `providers/jwks.py`; `test_static_jwks_verifier.py` |
| **F5** — GCP deploy | Owner | Deferred. Seven Terraform modules, four envs, deliberately non-applyable | `tools/env_isolation_check.py`; `docs/plans/open-questions/f5-deploy-deferred.md`. Also used as the label for the seven legacy pages in `capability-inventory.md` |
| **R2** — engagement | Owner | Attendance-summary slice shipped with safe defaults that fail toward *reporting less* | `docs/plans/open-questions/engagement-deferred.md` |
| **R4** — outreach | Owner | G4 slice shipped with safe defaults that fail toward *not sending* | `docs/plans/open-questions/r4-outreach-deferred.md` |
| **S12** — the opportunities funnel | Owner | Canonical metric + `pipeline_record` persistence | `docs/plans/2026-08-28-opportunities-s12-plan.md`; table `pipeline_record` (`schema.py:676`) |

**The asymmetry that defines every deferral.** A safe default is chosen so that
being wrong degrades toward *inaction* — not sending, reporting less, no
calendar entry — because a deferral that fails toward action costs a real
person something no later decision can undo. Nothing here is a placeholder that
reports success.

---

## 5. Provenance, evidence and the accountable-number vocabulary

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| **edition** | Deployment | `Edition` answers *which environment is this, and may it hold a provider credential*. It drives the classroom isolation assertions | `ProductScope`. *"A classroom deployment can run either product, and the CBA product can run in any edition"* — folding them would let a deployment knob silently change a product decision | `smartmatch_providers.Edition`; `smartmatch_api/config.py`; `domain/product_scope.py` §"Product scope is not deployment Edition" |
| **provenance** | Two contexts | (a) **Score provenance** — ADR-0011: a number carries where it came from or it is `null`. (b) **`EventProvenance`** — where an ingested event came from. (c) `pipeline_record` provenance, migration `0016` | A timestamp, or an audit log. Provenance is *attached to the value*, not recorded beside it | ADR-0011; `domain/explanation.py`; `domain/events.py`; `scan_forbidden.py:69` |
| **unknown** | Scoring / explanation | `FactorState.UNKNOWN` — the factor could not be evaluated. It renders as unknown and **never as `0`**, and no score is ever a percentage | Zero, absent, or "not applicable". A real zero is a zero | `domain/explanation.py:167`; e2e `test_11`, `test_12` |
| **policy_neutral** | Scoring / explanation | `FactorState.POLICY_NEUTRAL` — the value came from a **stated policy** rather than from measurement, and it always names the policy it applied | `UNKNOWN`. *"We could not evaluate one of these" outranks "one of these came from a policy"* as a caveat, so `unknown` wins when both are present | `domain/explanation.py:166,252,321`; `domain/cba_topic_explanation.py:106,141` |
| **measured** | Scoring / explanation | `FactorState.MEASURED` — from evidence. The member values match `FactorState` and `TopicEvidenceState` exactly, so a state crosses every boundary as the same string | An estimate | `domain/explanation.py:165` |
| **eligibility evidence** | Outreach | The record of *why* this recipient was writable-to **at composition time**, attached to the draft | Permission to send now. Consent is checked again at send | `domain/eligibility.py`; e2e `test_18`, `test_21` |

---

## 6. Appliance vs. topology

| Term | Context | Means | Does **not** mean | Anchor |
|---|---|---|---|---|
| **the appliance** | Deployment, current | The Docker Compose stack — `web`, `api`, `worker`, `scheduler`, `db`, one-shot `migrate` and seed services — that CI builds, probes and deploys to a VM over IAP, reached through Cloudflare Access. **This is what runs** | A demo, a dev-only convenience, or interim scaffolding beneath a real architecture. M7 / ADR-0022 states it is the production topology | `docker-compose.yml` (12 services), `docker-compose.vm.yml`, `build.yml` (`images` / `compose smoke` / `pilot e2e`), `deploy.yml` |
| **the topology** (GCP) | Deployment, design record | The Cloud Run + Cloud Tasks + Cloud Scheduler + Cloud SQL design across seven Terraform modules and four environments — **a forward design record, nothing applyable** | Something that has ever run. `env_isolation_check.py` fails CI on a `provider`, `backend`, `resource`, `module` or `data` block, committed state, a plan, a `.tfvars`, or a non-placeholder identifier | `infra/terraform/envs/dev/main.tf:1`; `tools/env_isolation_check.py`; R-18 |
| **the local development path** | Deployment, appliance-only | `LocalBearerTaskVerifier` + `LocalPostgresHttpTaskQueue` — durable PostgreSQL rows, **never** `FixtureTaskQueue`'s in-memory double — letting `docker compose up` exercise both HTTP boundaries | An implementation of Cloud Tasks or Cloud Scheduler. *"This is a developer appliance that emulates them locally, and it is never their implementation"* | `worker/main.py` docstring; `worker/local_tasks.py`, `worker/local_scheduler.py` |

**Why the distinction matters operationally.** Rollback, log destination and
deploy-time migration are answered for the appliance and unanswered for GCP. A
reader who takes the Terraform for the current architecture will look for
answers where none exist.

---

## 7. Table name index

The 44 `sa.Table` names in `schema.py`, by owning context
(`data-architecture.md` §3; the *writing service* axis is declared by M6).

| Context | Tables |
|---|---|
| Identity & Access | `tenant` · `org_unit` · `user_account` · `membership` · `resource_grant` · `pilot_credential` · `pilot_session` · `pilot_login_attempt` |
| Work substrate | `job` · `job_event` · `outbox_record` · `idempotency_record` · `redrive_record` · `concurrency_lease` · `rate_limit_counter` |
| Budget | `tenant_budget` · `spend_ceiling_bucket` · `spend_reservation` |
| Event catalog | `event` · `event_tag` · `event_registration` · `discovery_review_item` |
| Ingestion & review | `import_batch` · `review_item` · `pipeline_record` |
| Matching | `match_run` · `match_weight_setting` · `match_weight_setting_revision` |
| Speaker relationship | `speaker_profile` · `professional_unit_relationship` · `speaker_request_classification` · `contact_channel` · `contact_channel_transition` |
| Outreach | `outreach_draft` · `outreach_send` · `delivery_event` · `suppression_record` · `cba_invitation_batch` · `cba_invitation` |
| Engagement & rewards | `attendance_record` · `point_ledger_entry` · `reward_item` · `redemption` · `student_speaker_feedback` |

**`match_run` has one writer, not two** (OBSERVED 2026-09-08, correcting
`data-architecture.md` §8 and `domain-model.md` §6). `routers/match_runs.py:18-30`
records that nothing there inserts a `match_run` row and nothing there could —
`job_id` is a `NOT NULL` FK to `job` — and the router's only repository calls are
reads (`:1035`, `:1175`). The sole writer is
`worker/handlers.py:handle_match_run_create` (~`:1109`), via the insert-only
`smartmatch_persistence.match_runs`. What the API writes around a run is the
*request*: `job`, `outbox_record`, `idempotency_record`, and the
`match_weight_setting`/`match_weight_setting_revision` rows the run reads. Those
first three are **declared two-service tables by design** — along with
`job_event` and `spend_reservation`, the API records intent and the worker
transitions state (ADR-0005, ADR-0015 A1) — so single-writer is the rule for
`match_run` and the exception is declared, not hidden. Which is exactly why
ownership is declared per table rather than inferred per feature (AP-03, R-20,
ADR-0019, M6), not by a rename.
