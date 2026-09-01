# G1 / G3 / D6 fail-closed diagnosis and remedy plan

**Branch:** `friday-deliverable-828`  
**Audience:** Composer 2.5 implementation agent  
**Status:** executable preparation plan; it does not approve G1, G3, D6, or D7  
**Scope:** preserve honest fail-closed behavior, improve its executable guards,
and describe the implementation sequence that becomes available after written
human decisions. Do not launch matching, crawling, or rewards from this plan.

## 1. Executive verdict

None of the three closed surfaces is a product-code bug.

- **G1 matching/scoring:** intentional gate, explicitly enforced by
  `factor_registry.assert_registry_approved()` and by the absence of any match
  route. The legacy engine is itself defective (maximum score 0.90), so making
  a score appear by porting it would introduce a bug.
- **G3 crawler/event pipeline:** intentional capability absence, not a runtime
  gate exception. The event and engagement routers are empty; OpenAPI exposes
  no event/crawl/discovery route; there is no Python crawl HTTP client. Pure
  event identity, time, provenance, and quarantine contracts are present, but
  persistence and crawling intentionally are not.
- **D6 shippable rewards:** intentional gate with schema enforcement plus
  capability absence. Migration `0009` can store a proposed reward only when a
  real same-tenant owner is named and the funded state is non-null; it defaults
  omitted funding to false. There is no rewards/redemptions route or list
  service, and the D6 worksheet deliberately contains no catalog rows.

Engineering preparation is substantially complete. The remaining unblockers
are workshops and written approvals. Composer may strengthen guard tests and
decision seams now; it must not manufacture approvals or launch substitute
features.

## 2. Evidence and exact refusal paths

### 2.1 G1 — matching/scoring

**Verdict:** intentional gate. The current state is correct.

The direct refusal is:

1. `python/smartmatch_domain/smartmatch_domain/factor_registry.py`
   - `REGISTRY_STATUS = "proposed"` at line 59.
   - `assert_registry_approved()` at lines 256–272 compares the status with
     `"approved"` and raises `RegistryNotApprovedError`.
   - Only `engagement_load` is marked implemented; all other proposed scoring
     factors and all Stage A factors remain unimplemented.
2. `tests/unit/test_factor_registry.py::test_registry_is_not_yet_approved`
   requires the exact exception while G1 is open.
3. `tests/unit/test_matching_fail_closed.py` pins the proposed status, calls
   the guard, and rejects match/score/rank paths in committed OpenAPI.
4. `contracts/openapi/smartmatch.json` has no match, score, or rank operation.

Important nuance: there is no production scoring service that currently calls
the guard. The repository contains the guard required for every future
user-visible scoring path, but matching itself has not been implemented.
Therefore G1 closes through both an explicit exception at the domain seam and
the stronger fact that no HTTP capability exists.

The reason is documented in
`docs/plans/critical-path-matching-gate.md` and the module header: the legacy
registry declared nine weighted factors but computed seven, making 0.90 the
maximum attainable total. Characterizing or porting that engine is prohibited.
ADR-0011 additionally forbids treating missing evidence as zero.

**Missing human artifact**

- D1 needs a specifically named IA West program owner, not only the repository's
  self-assigned interim owner.
- That owner must approve the final factor list and weights.
- Q6 must decide the fate of `historical_conversion` and `student_interest`.
- Approved golden outputs must classify the 43% tie, Topic Relevance 0%, and
  Match Depth 0, including measured-zero versus unknown.
- The approval must name ongoing weight governance.

`docs/plans/workshops/g1-factor-registry-workshop-packet.md` is preparation,
not approval. `docs/decisions/pilot-decisions.md` explicitly says D1 is
tentative and no substantive registry is approved.

**Must remain closed until:** the named program owner commits or signs a
reviewable D1/G1 decision artifact containing all outputs above.

### 2.2 G3 — crawler/event pipeline

**Verdict:** intentional gate implemented by absence of capability and by
fail-closed domain outcomes, not by a `G3NotApprovedError`.

The exact closed paths are:

1. `services/api/smartmatch_api/routers/events.py` constructs an `APIRouter`
   but declares no handlers.
2. `services/api/smartmatch_api/main.py` includes that empty router, so a
   future event handler would be visible in OpenAPI; today there is none.
3. `contracts/openapi/smartmatch.json` exposes only health, unsubscribe, jobs,
   identity, imports, and metrics operations. It contains no event, crawl, or
   discovery catalog operation.
4. `tests/unit/test_matching_fail_closed.py` function
   `test_openapi_exposes_no_match_scoring_or_crawler_routes` rejects a
   committed `/crawl` path.
5. No Python API/worker module contains a crawler network adapter. The archived
   React `CrawlerFeed` and `CrawlerContext` are not backend capabilities.
6. `smartmatch_domain.events.resolve_identity_key()` returns `None` for
   `UnresolvedTime`, so an unresolved event has no comparable identity.
7. `smartmatch_domain.events.resolve_tag()` returns `QuarantinedTag` for an
   unmapped value, and `matchable_tags()` returns mapped tags only.

Accepted ADR-0010 and ADR-0012 settle the output invariants, but ADR-0012
explicitly leaves the actual controlled vocabulary and its owner undecided.
`docs/security/crawler-threat-model-draft.md` is clearly marked unsigned and
forbids crawl HTTP implementation.

**Missing human artifacts**

- G3 approval of the agent evaluation set and pass/fail criteria.
- Explicit allowed tools and domains.
- Extraction limits: pages, depth, bytes, and wall time.
- Per-run/per-tenant rate and cost ceilings plus escalation behavior.
- A named owner and versioning process for vocabulary growth.
- A named security reviewer must sign the R3 threat model, including SSRF, DNS
  rebinding, redirects, private/link-local addresses, response limits, parser
  isolation, credential handling, egress, and audit/provenance.

**Must remain closed until:** both the G3 control decision and named security
reviewer sign-off are committed. Vocabulary-dependent S5 work also waits for
the named vocabulary owner and approved terms.

### 2.3 D6 — shippable rewards

**Verdict:** intentional gate. The schema foundation exists; a shippable
catalog does not.

The exact closed paths are:

1. `db/migrations/versions/0009_engagement_schema.py::upgrade()` creates
   `reward_item` with:
   - `budget_owner_id NOT NULL`, no default;
   - composite foreign key `(tenant_id, budget_owner_id)` to
     `user_account(tenant_id, id)`;
   - `funded NOT NULL`, default false;
   - positive `points_cost` and non-negative `fulfilment_cost` checks.
2. `tests/integration/test_engagement_schema_constraints.py` proves null owner,
   null funded state, and nonexistent/cross-tenant owner inserts fail. It also
   proves a real owner with `funded=true` is representable.
3. `services/api/smartmatch_api/routers/engagement.py` declares no handlers.
4. `contracts/openapi/smartmatch.json` has no rewards, catalog, balance, or
   redemption operation.
5. `docs/pilot-data/rewards-catalog-worksheet.md` leaves item, owner, funding,
   cost, and calibration cells blank on purpose.

The database does not prohibit an explicitly unfunded row; it safely defaults
omitted funding to false. The shipping refusal is the combination of no list
API and the future S8 rule that only owned, funded rows may be listed. Do not
misstate `funded=false` as an insert constraint.

**Missing human artifacts and dependencies**

- D6: a named human budget owner, represented by a real same-tenant
  `user_account`, for every proposed listable item.
- Written confirmation that each item is funded and can be fulfilled.
- D7: program-owner ratification of points per verified attendance, calibration
  N, item point costs, and catalog content. The values in
  `pilot-decisions.md` remain tentative.
- S6/S7 behavior: attendance-backed point derivation and the server-side
  append-only ledger fold must exist before S8/S9.
- Before route work, product/security must settle reward read and redemption
  roles; the prep contract labels these TBD.

**Must remain closed until:** the budget owner(s) sign D6, the program owner
ratifies D7/catalog content, and S6/S7 are implemented and verified. A
coordinator role is not a budget owner, and an arbitrary UUID is not ownership.

## 3. What Composer may implement now

Only preparation that cannot be mistaken for launch:

1. Strengthen the executable fail-closed contract tests described in Slice 1.
2. Add validation tooling for completed workshop artifacts only if it validates
   explicit fields and does not infer approval from document existence.
3. Add synthetic test fixtures for event persistence and reward APIs, clearly
   unused by production and containing no real URLs, contacts, owners, funding,
   or catalog promises.
4. Keep docs and implementation seams current as decisions arrive.

Do not implement a scoring formula, event migration, crawler adapter, network
call, rewards list/redemption route, catalog row, or rewards UI in the pre-
approval track. Those are post-decision slices below.

## 4. Ordered Composer 2.5 slices

Composer must stop after Slice 2 unless the required signed artifacts are
present in the repository and a human explicitly authorizes the applicable
post-decision track.

### Slice 1 — strengthen gate contract tests

**Goal:** make all three currently absent product surfaces executable
contracts, without adding product behavior.

**Files**

- Modify `tests/unit/test_matching_fail_closed.py`.
- Optionally rename it to `tests/unit/test_gated_product_surfaces_fail_closed.py`
  only if all references and test discovery remain clear; a rename is not
  required.

**Changes**

1. Import and assert `RegistryNotApprovedError`, replacing the broad
   `pytest.raises(Exception)`.
2. Keep the existing proposed-status and exact G1 guard assertions.
3. Parse committed OpenAPI and assert the exact forbidden route families are
   absent:
   - match runs, matching, scores, and ranks;
   - crawl, crawler, discovery jobs, and event catalog routes;
   - rewards, reward catalog, balances, and redemptions.
4. Prefer explicit path-segment checks over accidental substring matches.
   `/v1/units/{unit_id}/metrics` must not fail because a description happens
   to contain the word “match.”
5. Add a source-level assertion that `events.router.routes` and
   `engagement.router.routes` are empty if that assertion is stable under
   FastAPI. Otherwise, rely on the generated OpenAPI path set.
6. Add comments naming the human gate that deliberately changes each assertion.

**Tests**

- `pytest tests/unit/test_matching_fail_closed.py`
- `make openapi-check`
- `make check`

**Acceptance**

- The test fails if any match/crawl/event-catalog/reward/redemption route appears
  before its assertion is deliberately changed.
- G1 checks the exact exception type.
- No application, schema, OpenAPI, or frontend behavior changes.

### Slice 2 — decision-artifact validation seam

**Goal:** make workshop completion reviewable without pretending a blank or
tentative document is approval.

**Files**

- Add `tests/unit/test_gate_decision_artifacts.py`.
- Update the three prep artifacts only if their required-output headings are
  inconsistent:
  - `docs/plans/workshops/g1-factor-registry-workshop-packet.md`
  - `docs/security/crawler-threat-model-draft.md`
  - `docs/pilot-data/rewards-catalog-worksheet.md`

**Changes**

- Assert all prep files retain an unmistakable unapproved/draft marker.
- Assert the G1 packet names every required decision field.
- Assert the G3 draft names every control and reviewer-sign-off field.
- Assert the D6/D7 worksheet contains owner, funded, fulfilment, point-cost, and
  N fields and retains its “do not seed” warning.
- Do not make tests pass by looking only for the words “approved” or “signed.”
  These tests protect packet completeness, not institutional authority.

**Tests**

- `pytest tests/unit/test_gate_decision_artifacts.py`
- `make check`

**Acceptance**

- Removing a required field or the unapproved warning fails the no-database
  suite.
- A blank worksheet still passes; blankness is the honest pre-workshop state.
- No status, owner, value, or sign-off is inserted by Composer.

### G1 post-decision track — only after D1/G1 approval

1. **M1 approval landing**
   - Touch `factor_registry.py`, `test_factor_registry.py`,
     `test_matching_fail_closed.py`, MM-002, and approved golden fixtures.
   - Copy the approved factors/weights exactly; set an approved registry version
     and status; deliberately invert the fail-closed tests.
   - Require each stakeholder symptom to have approved expected output and
     unknown-versus-zero classification.
2. **M2–M6 factors and eligibility**
   - Implement only approved factors.
   - Normalize over exactly implemented scoring factors.
   - Keep D3-dependent travel behavior unavailable or explicitly coarse and
     labelled; never fabricate route mileage.
3. **M7–M10 execution**
   - CP-SAT only for portfolio optimization.
   - Persist immutable `match_run` input and version snapshots through the
     durable command path.
   - Add per-factor explanations and scenario comparison.
4. **HTTP/UI**
   - Add routes only after M8 exists, update policy matrix with each route,
     regenerate OpenAPI/client, and show registry version plus “heuristic score.”

**Acceptance:** all approved goldens pass; no proposed or unimplemented factor
carries weight; unknown remains distinct from zero; no legacy characterization
or demo fallback exists.

### G3 post-decision track — only after G3 + R3 sign-off

1. Land S3 event persistence and mirror it in `schema.py`.
2. Add S4 deterministic identity/upsert and structured provenance.
3. Add S5 approved vocabulary versions, quarantined tags, and review queue.
4. Add the composite attendance-to-event FK in a later migration.
5. Prove unresolved events cannot publish/match and quarantined tags cannot
   enter read/match results.
6. Only then add a worker-only crawl adapter implementing the signed allowlist,
   address/redirect revalidation, byte/time/depth/rate/cost limits, parser
   isolation, audit, and escalation controls.
7. Add HTTP command/status surfaces only if the signed G3 artifact calls for
   them; update authorization matrix and OpenAPI in the same slice.

**Acceptance:** duplicate sources upsert one event; provenance never enters the
title; unresolved events and quarantined tags cannot publish; every signed
security control has a denial test; API handlers never fetch arbitrary URLs.

### D6 post-decision track — only after D6/D7 and S6/S7

1. Implement and test the attendance-derived ledger fold and compensation path.
2. Add an S8 repository/service query filtering to `funded=true` with a valid
   owner; derive balances on the server.
3. Add S9 durable, idempotent redemption transitions and audit.
4. Add approved synthetic catalog fixtures for tests; seed no production data
   in migrations.
5. Add a live-catalog calibration test using the ratified N and earn policy.
6. Add authorized routes, policy-matrix rows, OpenAPI/client generation, and
   finally UI backed only by server values.
7. Remove `studentPoints.ts` and `studentRewardsCatalog.ts` when no caller
   remains.

**Acceptance:** every listed item is owned, funded, and fulfillable; the
ratified reachability property passes; the browser never computes/decrements a
balance; redemption is durable, authorized, auditable, and idempotent.

## 5. Explicit do-not list

- Do not set `REGISTRY_STATUS = "approved"` because a workshop packet exists.
- Do not treat `docs/decisions/pilot-decisions.md` as IA West ratification.
- Do not invent expected scores, classify unknown as zero, or port/characterize
  the legacy matching engine.
- Do not expose a score, rank, match run, or matching UI before G1.
- Do not add event/crawl/discovery catalog routes, a crawl worker, or any crawl
  HTTP/network call while G3 or the threat model is unsigned.
- Do not choose tag terms or a vocabulary-growth owner in code.
- Do not render or match on quarantined tags or unresolved events.
- Do not insert a dummy `budget_owner_id`, use a coordinator role as the owner,
  or seed placeholder catalog rows.
- Do not weaken `budget_owner_id`, `funded`, tenant FK, point-cost, or fulfilment
  constraints.
- Do not ship an unfunded/unowned item, copy legacy point costs, or adopt
  tentative D7 numbers as approved.
- Do not add reward/redemption routes or UI before D6/D7 and S6/S7.
- Do not compute points or decrement balances in the browser.
- Do not hand-edit generated OpenAPI output; change routes, regenerate, and run
  the drift check only in an authorized post-decision slice.
- Do not use real PII, real crawl targets, live providers, production
  credentials, or make a production-readiness claim.

## 6. Handoff and stop conditions

The first Composer 2.5 assignment is **Slice 1 — strengthen gate contract
tests**. It is independently useful, no-database, and cannot be confused with a
product launch.

After Slice 2, Composer reports the three workshop artifacts still required and
stops. It may enter a post-decision track only when:

1. the corresponding decision artifact is committed and explicitly ratified or
   signed by the named human owner/reviewer;
2. every dependency listed for that track is satisfied; and
3. the human directing the implementation explicitly authorizes that track.

If those conditions are absent, the honest result is: engineering preparation
is done; workshops are the blocker.
