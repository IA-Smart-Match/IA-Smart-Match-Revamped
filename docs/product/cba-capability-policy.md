# CBA product-scope capability policy

**Status:** Implemented (Wave 0, `CBA-SCOPE-POLICY`)
**Implementation:** [`python/smartmatch_domain/smartmatch_domain/product_scope.py`](../../python/smartmatch_domain/smartmatch_domain/product_scope.py)
**Customer source:** [`cba-smart-match-customer-requirements.md`](cba-smart-match-customer-requirements.md) §§1, 3–4, 17, 20–22
**Register of open decisions:** [`docs/plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md)

This is the one place that answers "which product is this, and which named
capabilities does it offer". API composition and frontend navigation both read
these decisions. Neither invents its own.

## Product scope is not deployment Edition

Two values, deliberately, and neither derives from the other:

| | `Edition` | `ProductScope` |
|---|---|---|
| Question it answers | Which **deployment** is this? | Which **product** is this? |
| Values | `dev`, `staging`, `classroom`, `production` | `cba`, `ia_west_legacy`, `class_exercise` |
| What it decides | Whether a provider credential may exist here; which adapters may be constructed | Which named capabilities the product offers |
| Enforced by | [`config.py`](../../services/api/smartmatch_api/config.py) boot validation, the `smartmatch_providers` registry, [`tools/env_isolation_check.py`](../../tools/env_isolation_check.py) | The capability table below |
| Environment variable | `SMARTMATCH_EDITION` | `SMARTMATCH_PRODUCT_SCOPE` |

A classroom deployment can run either product. The CBA product can run in any
edition. Folding them into one flag would let a deployment knob silently change
a product decision — and let a product decision silently change what may hold a
credential.

**Nothing in this policy can enable live providers, live data, or a cloud
deploy.** `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`, and
`ALLOW_CLOUD_DEPLOY=false` remain the mandatory defaults, owned by the
environment and the edition rules. The capability vocabulary deliberately names
none of them: a capability called `live_email` would be a second door into a
gate that already has an owner, and a test refuses any capability name matching
`live|deploy|terraform|credential|secret`.

## The capability table

`cba` is the default. An unconfigured process runs the **narrower** product, so
a missing environment variable cannot widen what the system offers.

| Capability | `cba` | `ia_west_legacy` | `class_exercise` | Why |
|---|:--:|:--:|:--:|---|
| `authenticated_login` | on | on | **off** | Customer §3: one standard login, no portal chooser, roles assigned in the backend. |
| `event_reads` | on | on | **off** | Customer §22 preserves event browsing. |
| `speaker_request_intake` | on | on | **off** | Customer §12 (an Event Host files a Speaker Request) and §13 (a Speaker Connector reads the queue). Separate from `event_reads` because it is a write, and from `operator_record_import` because a host stating a new intention is not an operator loading records the institution already holds. |
| `speaker_contact_management` | on | on | **off** | Customer §13 (a Speaker Connector adds, lists, reads and edits a professional contact) and §§7-8 (the Connector corrects an assigned classification). Separate from `speaker_request_intake` because the two are opposite ends of one arrow and either is coherent alone — requests without a roster is a Connector answering from outside the system, and a roster without requests is a directory. Emphatically not `consented_outreach`: a contact *record* is not a contact *channel*, nothing here creates consent or makes anybody writable-to, and an address typed on the create form is discarded and reported back as withheld (OQ-CBA-011). Not `external_speaker_acquisition` either — every record is typed by a person about somebody the institution already knows, which is the manual, inside-the-system growth §20 permits. |
| `match_runs` | on | on | **off** | Customer §1: matching occurs between records already in the system. |
| `discovery_metrics` | on | on | **off** | Customer §17 keeps the R/Y/G discovery feed and forbids redesigning it merely because the target customer changed. |
| `consented_outreach` | on | on | **off** | Customer §22 preserves the speaker invitation workflow. Consent stays authoritative and is re-checked at delivery. |
| `rewards_ledger` | on | on | **off** | Customer §4: "Rewards / points — **Keep**". Only wording and refinements are P2. |
| `operator_record_import` | on | on | **off** | Customer §20: the lists grow manually, inside the system. This is the opposite of acquisition. |
| `external_speaker_acquisition` | **off** | on | **off** | Customer §20: no finding speakers on the internet, no LinkedIn or other scraping, no automatic external event discovery. |
| `cold_unknown_contact_outreach` | **off** | on | **off** | Customer §20: no cold outreach to unknown speakers, no external CRM/contact-acquisition system. |
| `chapter_membership_dues` | **off** | on | **off** | Customer §4 and §20 remove chapter membership and dues **as a product concept**. |
| `member_inquiry_narrative` | **off** | on | **off** | CBA has no approved equivalent outcome; the stored stage and its history are preserved, the narrative is not offered. |
| `class_exercise` | **off** | **off** | on | ADR-0025 D1: the Spring 2027 class exercise — a no-login team surface and an instructor surface over the `exercise_` tables. Granted **only** in `class_exercise`, and that scope grants nothing else. Not a share of `match_runs`: a match run is an immutable, versioned, tenant-scoped run over records a principal entered, and the exercise has none of those four things. `off` under `ia_west_legacy` even though that is the *wider* scope, because "wider" means a superset of the same product's capabilities — the exercise was never part of that product. |
| `speaker_portal` | **off** | **off** | **off** | B26 T6b-1: Speaker accounts — a Speaker Connector invites a contact, the contact activates a `speaker` login from a one-time `/s/{token}` link. Built and **staged off in every scope**. Turning it on is a reviewed edit to the policy rows, never an env var, seed or compose file. **Turn-on rule (C5, owner-confirmed):** T6b-5 merged **and** parent plan §10 rows 1 (Ann/Pia/Lisa), 2 (named privacy owner) and 4 (pilot hostname) cleared. Requires `authenticated_login`, `consented_outreach` and `speaker_contact_management` in the same scope (asserted at import). B26 T6b-2 adds the Speaker's own routes under the same capability, `{speaker}` only, subject always the profile bound to the login: `GET`/`PATCH /v1/me/availability`, `GET /v1/me/invitations`, `POST /v1/me/invitations/{invitation_id}/response`, `GET /v1/me/engagements`. |

### The third column is a third product

`class_exercise` (ADR-0025) is not "CBA with things switched off". It is the
Spring 2027 classroom exercise: six teams, about 300 made-up profiles, no
account, no tenant, no consent question. It shares the *matching mechanism* with
the CBA product and shares no data with it at all, and ADR-0025 D1 requires that
it never run in the same process as real records.

That requirement is what the column enforces. Every capability that implies an
authenticated CBA router or a CBA datum is `off`, so
`services/api/smartmatch_api/main.py` mounts none of those routers and
`get_current_principal` is **unreachable rather than bypassed** — ADR-0025 D9
rejected a per-route bypass inside the CBA scope for exactly this reason.

Two entries are worth pausing on, because the exercise plainly does read events
and plainly does rank. `event_reads` and `match_runs` name the *CBA* catalog and
the *CBA* tenant-scoped, versioned match run; the exercise reads
`exercise_event` rows and ranks `exercise_profile` rows through its own routers
and its own registry. A `True` in either cell would mount the CBA routers, which
is the process mixing this column exists to prevent.

The five infrastructure routers (`jobs`, `redrive`, `engagement`, `review`, and
the unit-scoped review queue) are not a product capability of their own, but
every route behind them resolves a principal — so they ride
`authenticated_login`. Under `cba` and `ia_west_legacy` that mounts exactly what
mounting them unconditionally did; under `class_exercise` it is what makes the
route table honest.

### Three distinctions the table depends on

1. **Consented outreach is not cold outreach.** They share a word and nothing
   else. One sends an approved draft to a contact whose consent is on record;
   the other contacts someone who never agreed to be contacted. A gate keyed on
   the word "outreach" would remove a working, in-scope capability.
2. **`chapter_membership_dues` is a product concept, never the backend
   `membership` record.** The authorization row that carries a principal's
   tenant and roles is untouched, and must stay untouched. Removing the
   customer-facing membership narrative is a §4 terminology decision; renaming
   the authorization table is not authorized by anything.
3. **`member_inquiry_narrative` gates the claim, not the data.** The stage
   remains in `smartmatch_domain.pipeline`, in migration `0011_pipeline_record`,
   and in every row already written. What CBA does not do is present it as a
   funnel outcome or write new ones.

## Fail-closed, and never silent

* Every capability carries an explicit `True`/`False` for **every** scope. A
  policy that treats "absent" as "disabled" is fail-closed but silent: a
  capability could end up gated because someone forgot it rather than because
  someone decided. Adding a capability without classifying it fails at import.
* An **unknown** capability or scope name raises `CapabilityScopeError` rather
  than returning `False`. Answering an unknown name with "disabled" would let a
  typo read as a correctly closed gate for as long as nobody looked.
* An unrecognised `SMARTMATCH_PRODUCT_SCOPE` value fails validation and the
  process does not boot. It never falls back to a default.

## A UI gate is not authorization

Hiding a link removes a **claim**, not an access path. Anyone can type a URL or
call the API directly, and the frontend policy stops none of that — nor is it
meant to. Authorization is enforced server-side, per route, deny-by-default and
tenant-scoped (`smartmatch_authz`), and this policy neither widens nor narrows
it.

What the policy prevents is the product *advertising* something it does not do
this phase. Navigation to a scraping console the customer put out of scope is a
false claim about the product long before it is a security question.

**No capability may ever be derived from a role label**, and no `false` here is
a substitute for a server-side check.

## How it is read

| Reader | File | How |
|---|---|---|
| API composition | [`services/api/smartmatch_api/main.py`](../../services/api/smartmatch_api/main.py) | `CAPABILITY_SCOPED_ROUTERS` pairs each capability-serving router with its capability, and `PRINCIPAL_BEARING_INFRASTRUCTURE_ROUTERS` carries the five that ride `authenticated_login`. `routers_for(settings)` is the whole mounting rule as one function, and the application is built from it. |
| API configuration | [`services/api/smartmatch_api/config.py`](../../services/api/smartmatch_api/config.py) | `Settings.product_scope`, `Settings.capability_enabled()`, `Settings.enabled_capabilities()`. |
| Frontend | [`apps/web/legacy-frontend/src/lib/productScope.ts`](../../apps/web/legacy-frontend/src/lib/productScope.ts) | `isCapabilityEnabled()` / `enabledCapabilities()` over a mirror of the Python table. |

The frontend file is a **mirror**, not a second opinion.
[`tests/unit/test_cba_scope_policy.py`](../../tests/unit/test_cba_scope_policy.py)
parses it and asserts it matches the Python policy capability for capability, so
editing one without the other fails. That is what keeps "one policy, read in two
places" true rather than aspirational.

## What this policy does *not* do

* It implements no CBA feature. Wave 0 establishes the policy; the later waves
  consume it.
* It changes no mounted route, no OpenAPI contract, and no migration. Under the
  default `cba` scope every classified router is enabled, so the served surface
  is exactly what it was. The capabilities CBA gates own **no router at all** —
  they were never mounted, and `CAPABILITY_SCOPED_ROUTERS` is the declaration
  that says so on purpose rather than by accident.
* It removes no navigation.
  `apps/web/legacy-frontend/src/app/routes.tsx` is unchanged; Wave 1's
  `CBA-SCOPE-COMPOSITION` owns surface composition and is the first consumer of
  the frontend adapter.
* It deletes no code, data, or history. Gated capabilities remain in the
  repository under the scope that owns them, which is why `ia_west_legacy`
  exists as a named scope rather than the gated capabilities being deleted.

## Local and default behaviour

With no configuration at all:

* `SMARTMATCH_PRODUCT_SCOPE` unset → `cba`.
* `SMARTMATCH_EDITION` unset → `dev`, with `use_fixture_providers` true.
* The four CBA-gated capabilities are off; the seven preserved ones are on.
* `ALLOW_LIVE_PROVIDERS`, `ALLOW_LIVE_DATA`, and `ALLOW_CLOUD_DEPLOY` remain
  false. This document authorizes no change to any of them.

To run the legacy product locally, set
`SMARTMATCH_PRODUCT_SCOPE=ia_west_legacy`. That is a product-scope change only:
it grants no credential, enables no live provider, and moves no deployment
boundary.

`SMARTMATCH_PRODUCT_SCOPE=class_exercise` runs the class-exercise product
instead. It grants exactly one capability and removes every authenticated CBA
router from the route table; it likewise grants no credential, enables no live
provider, and moves no deployment boundary.
