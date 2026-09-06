# Remaining engineering implementation plan

**Branch:** `friday-deliverable-828`  
**Planning baseline:** `docs/plans/remaining-engineering-brief.md` at commit
`0784a7d`  
**Status:** planning only; this document does not authorize implementation,
deployment, a pull request, or a push.

## 1. Outcome and guardrails

This plan sequences the eight remaining engineering items without turning an
open product or security decision into code. Wave 3C is complete at `4edcec2`
and is intentionally not re-planned here.

The immediate implementation slice is the frontend half of stakeholder Fix #7:
remove every caller-chosen role affordance while leaving sign-in visibly
unavailable until A1b supplies a real identity-provider integration. It is
likely the only substantial UI engineering item in this set that can close
without G1, G3, D6/D7, or S12.

Standing rules for every wave:

- Matching remains fail-closed while
  `factor_registry.REGISTRY_STATUS == "proposed"`. Never port or characterize
  against the legacy scoring engine, whose maximum attainable score is 0.90.
- Unknown values remain `null`/unknown with a reason. Never turn missing
  evidence into zero, a count, a rank, or a progress bar.
- Authorization may stay the same or become narrower only after an explicit
  decision. Never replace unit-scoped authorization with authentication alone,
  and never bypass tenant isolation, active-membership windows, suspension, or
  explicit deny.
- ADR-0014 minimum disclosure applies to underlying rows and contact data.
  Aggregate access does not automatically authorize row-level payload access.
- No unresolved event date, quarantined tag, scraped contact detail, unfunded
  reward, unowned reward, or unapproved match score reaches a publishable list.
- No live providers, production credentials, live data, or production-readiness
  claim. Nothing is deployed.

## 2. Classification

| # | Item | Classification | Why |
|---|---|---|---|
| 1 | Matching/scoring (G1) | **blocked-on-stakeholder** | D1/G1 requires a named program owner to approve factors, weights, and golden cases. |
| 2 | Crawler/event pipeline (G3, S4/S5) | **blocked-on-stakeholder** | G3, the crawler threat model, the tool allowlist/eval set/cost controls, and the vocabulary-growth owner are not approved. |
| 3 | Shippable rewards catalog (D6) | **blocked-on-stakeholder** | D6 must name budget owners and D7 must choose calibration N; S6/S7 also precede S8/S9. |
| 4 | Metrics role-gating vs ungated | **human-decision-required** | Product/security must decide aggregate and drill-down roles under ADR-0014. Current behavior is intentional and tested. |
| 5 | `board_role` model | **human-decision-required** | Dr. Wang must decide professional attribute versus unit relationship. |
| 6 | Optional event URL/contact fields | **human-decision-required** | Dr. Wang must choose collect/drop per field; published contacts also need privacy review. |
| 7 | Login caller-chosen role cards | **implement-now** | The misleading role-selection UI can be removed without an IdP and without changing backend authorization. A1b remains a separate blocked follow-up. |
| 8 | Two opportunities pages agree | **blocked-on-stakeholder** | A written metric definition is missing; S12/S1, and possibly G1/S3-S5, must provide one owning evidence query. |

“Blocked-on-stakeholder” means engineering capacity is not the limiting factor.
For each such item, the preparation below is safe, but the plan explicitly says
where implementation must stop.

## 3. Sequenced waves

### Wave A — close the safe frontend defect now

Implement Fix #7A only, as specified in section 4. Do not pretend that removing
the role picker completes A1b or creates a working login.

### Wave B — run decision workshops in parallel

These are calendar-critical and can proceed concurrently:

1. D1/G1 factor-registry workshop.
2. G3 crawler security and governance workshop.
3. D6/D7 rewards ownership and economy workshop.
4. Metrics aggregate/drill-down authorization decision.
5. Dr. Wang pilot-column workshop for `board_role`, public URL, and published
   contacts.
6. Product definition workshop for the canonical “opportunities” metric.

Each workshop must produce a committed decision artifact or other written,
reviewable approval. Meeting notes that leave alternatives open do not unblock
engineering.

### Wave C — apply narrow decisions with independent value

After the corresponding written decisions:

1. Apply the metrics authorization decision and its executable policy-matrix
   changes.
2. Update `columns.yaml`, fixtures, and README for Dr. Wang’s decisions.
3. Wire the ratified pilot column contract into worker validation as a separate
   J10/import-execution slice; do not bury this in the documentation change.
4. Configure A1b and replace the truthful unavailable-login state with the real
   institutional sign-in flow.

These slices do not require matching scores, crawler output, rewards content, or
opportunity counts.

### Wave D — build evidence foundations after gates close

1. G1: M1, then M2-M6, M7, M8, and M9/M10.
2. G3/R3: S3 persistence, event table and constraints, S4 identity, S5 tags and
   review queue, then the constrained crawler adapter.
3. D6/D7 plus S6/S7: S8 listing and S9 redemption.
4. Approved opportunities definition plus its dependencies: S12 owning
   persistence/query, metric registration, API drill-down, then both UI
   subscribers.

Do not parallelize migrations that both need
`tests/integration/test_check_constraints.py` without assigning one owner for
that shared constraint registry.

### Wave E — integration and release evidence

For each backend/schema slice, run the local no-database gate and then require
PostgreSQL CI before merge. For web slices, require typecheck and build in CI.
No push occurs unless a human asks for it.

## 4. Implement-now: Fix #7A, remove caller-chosen login roles

### Scope

Close the visible caller-chosen-role defect without inventing an authentication
flow. This slice removes role cards, role query parameters, canned identities,
and role/email submission controls. It does not wire OIDC, assign a principal,
or authorize a portal.

### File-level steps

1. `apps/web/legacy-frontend/src/app/pages/LoginPage.tsx`
   - Delete `ROLES`, all canned emails, role icons, `useSearchParams`,
     `selectedRole`, the manual email/role form, and `handleLogin`.
   - Replace “Demo Access / Choose your portal” with one neutral sign-in panel.
   - Until A1b exists, render a non-interactive unavailable state that clearly
     says institutional sign-in is not connected. Do not render an enabled
     button that only produces a fake success or a local session.
   - Keep only navigation back to the public landing page. Do not write
     `sessionStorage`, navigate to a portal, or accept any role/user/tenant value.

2. `apps/web/legacy-frontend/src/app/pages/LandingPage.tsx`
   - Replace every `/login?role=...` link with `/login`.
   - Replace role-specific CTA labels (“Student Portal”, “Event Coordinator”,
     “Start Matching”) where they imply role selection or working matching with
     a neutral “Sign in” action.
   - This slice need not redesign the landing page, but it must not route a
     caller toward a chosen role.

3. `tests/unit/test_frontend_auth_contract.py` (new temporary migration guard)
   - Add a no-database source-contract test over `LoginPage.tsx` and
     `LandingPage.tsx`.
   - Assert there is no `?role=`, `useSearchParams`, caller role selector,
     `iaw_session` write, or the four canned login emails.
   - Assert the login page contains the truthful unavailable state until A1b.
   - Keep this narrow. It is not a substitute for W7/Vitest/Playwright.

4. Follow-up after A1b, not part of Fix #7A:
   - Configure the live verifier/JWKS/audience/rotation in the existing A1a
     verification seam.
   - Attach the bearer to the generated client and obtain identity and
     server-assigned memberships from `GET /v1/me`.
   - Add route guards as UX only; API authorization remains authoritative.
   - Remove `sessionStorage["iaw_session"]` reads and all fallback identities
     (`stu-001`, `coord-001`, `shana-demarinis`) across portal layouts/pages.
   - Do not revive `mockLogin`, post a role in a body, or store a role asserted
     by the browser.

### Tests and verification

- `pytest tests/unit/test_frontend_auth_contract.py`
- `make check` (no-database suite; does not prove integration behavior)
- In `apps/web/legacy-frontend`: `npm run typecheck`
- CI web job: locked install, typecheck, Vite build, and audit
- Manual acceptance: `/login`, `/login?role=student`, and every landing CTA
  show the same neutral state and create no session.

DrvFs note: `npm ci` may fail on `/mnt/c` with `ENOTEMPTY`/`ENOENT`. Use the
documented WSL-native install plus `node_modules` symlink for local typecheck;
CI remains the clean install/build proof.

### Acceptance criteria

- No role cards, role dropdown, demo email, or role-specific login query remains.
- The browser cannot submit tenant, user, or role as authentication input.
- No click reports successful sign-in without server agreement.
- Existing backend 404/contract tests for the archived MM-A01 caller-selected
  identity route remain green.
- A1b is still visibly open; the change does not claim full authentication is
  complete.

### Risks

- Removing cards while leaving role-specific query CTAs would preserve the
  defect invisibly; test both files together.
- Replacing the cards with an enabled dead button would exchange one dishonest
  interaction for another.
- Fix #7A does not cure direct portal URLs that still use fallback identities.
  Keep those routes development-only and schedule their removal with A1b; do
  not broaden backend access to accommodate them.

## 5. Blocked and decision-required items

### 5.1 Matching/scoring (G1) — blocked-on-stakeholder

**Required workshop/decision**

- Name the D1/G1 program owner.
- Approve the exact factor list and weights, including the fate of
  `historical_conversion` and `student_interest`.
- Approve golden cases before scoring code, including the exact 43% tie,
  “Topic Relevance 0%”, and “Match Depth 0”; each zero must be classified as
  measured zero or unknown under ADR-0011.
- Record weight governance and who may change approved weights. D3 separately
  governs route-matrix terms for `travel_burden`.

**Safe engineering preparation**

- Prepare a workshop packet from
  `python/smartmatch_domain/smartmatch_domain/factor_registry.py`,
  `tests/unit/test_factor_registry.py`, MM-002, and the three stakeholder
  symptoms.
- Draft golden-case input/output schemas without assigning expected scores.
- Preserve the failing `assert_registry_approved()` and
  `test_registry_is_not_yet_approved`.

**After written approval**

- M1: update `factor_registry.py`, invert the gate test deliberately, and land
  approved golden cases.
- M2-M6: implement only approved factors; absent/unimplemented factors have no
  silent weight.
- M7: use CP-SAT, never an LLM, for portfolio optimization.
- M8: persist immutable `match_run` snapshots with registry/weight/optimizer and
  route-estimate version pins.
- M9/M10: explanations and scenario comparison; scores display registry version
  and “heuristic score” provenance.

**Acceptance**

- Written approval is in-repo; Q6 is answered.
- Implemented scoring weights normalize to one over exactly implemented factors.
- Every factor has approved goldens; unknown and zero remain distinct.
- No legacy score characterization or demo fallback exists.

**Do not build yet:** do not flip `REGISTRY_STATUS`, port the legacy engine,
implement optimizer-backed match runs, or expose any score/rank until G1 closes.

### 5.2 Crawler/event pipeline (G3, S4/S5) — blocked-on-stakeholder

**Required workshop/decision**

- Approve G3’s agent evaluation set, allowed tools/domains, extraction budget,
  rate/cost ceilings, and human escalation behavior.
- Complete and sign the R3 threat model covering SSRF, DNS rebinding, redirect
  chains, private/link-local IPs, egress, response limits, parser isolation,
  credentials, and audit/provenance.
- Choose the closed role/type vocabulary and its versioning/growth owner.

**Safe engineering preparation**

- Threat-model and adapter-interface documentation only.
- Persistence design for S3-S5 using ADR-0010/0012:
  `event`, structured provenance, deterministic identity uniqueness, mapped
  tags, quarantined raw tags, and review status.
- Migration/test matrix design, including the eventual composite FK from
  `attendance_record.event_id` to `event`.
- Reuse pure contracts in `smartmatch_domain.events`; do not choose actual tag
  terms in code.

**After written approval**

- Add event tables in a new expand-phase migration and mirror them in
  `python/smartmatch_persistence/smartmatch_persistence/schema.py`.
- Add repository/service adapters that compute the identity key before insert,
  update on duplicate keys, store provenance separately, and refuse publish or
  match transitions for `unresolved`.
- Add mapped/quarantined tag persistence and a human review queue.
- Add the attendance FK after event identity exists.
- Only then implement the crawl adapter behind the approved allowlist and
  controls; do not port `CrawlerFeed`, `CrawlerContext`, or legacy endpoints.

**Tests/acceptance**

- PostgreSQL constraints reject publishable/matchable unresolved events.
- Two sources with one deterministic key update one event.
- Unmapped tags persist for review but never enter read/match results.
- Provenance URL/fetch time/extractor version never enters the title.
- Security tests cover blocked addresses, redirect revalidation, bounded
  response size/time, and tool allowlist enforcement.

**Do not build yet:** no crawler route, crawl worker, crawl UI, network call, or
actual tag vocabulary before G3 and the threat-model review.

### 5.3 Shippable rewards catalog (D6/D7) — blocked-on-stakeholder

**Required workshop/decision**

- D6: name the accountable `user_account` budget owner for each proposed item
  and confirm funded balance/fulfilment commitment.
- D7: choose N for “cheapest reward reachable within N events”; ADR-0013’s 3 is
  a proposal, not approval.
- Confirm the catalog content; legacy item names are discussion input only and
  legacy point costs do not carry forward.

**Safe engineering preparation**

- Demonstrate migration `0009` refusing null owner/funded state.
- Prepare a catalog worksheet that leaves owner, funding, point cost, and N
  blank for human completion.
- Design S8/S9 API and durable-command contracts without creating listable
  production content.

**After written approval and S6/S7**

- Implement the server-side ledger fold and append-only compensation path.
- Add S8 listing that returns only funded, owned items.
- Add S9 durable redemption command and transitions
  `requested -> approved -> fulfilled | denied | expired`.
- Add the live-catalog calibration test using approved N.
- Retire `studentPoints.ts` and `studentRewardsCatalog.ts`; render server values
  only and progress only toward reachable items.

**Acceptance**

- Every listed item has a named owner and funded balance.
- Cheapest listed reward satisfies approved N against the server points policy.
- Browser never computes or decrements a balance.
- Redemption is durable, authorized, auditable, and idempotent.

**Do not build yet:** no listable catalog content, redemption UI, or repriced
legacy catalog before D6/D7 and S6/S7.

### 5.4 Metrics authorization — human-decision-required

**Required decision**

Product/security must decide `metrics.read` and `metrics.drill_down` separately.
The decision record must answer:

1. May any active unit membership read aggregates?
2. May a bare unit resource grant read aggregates?
3. Which roles may read underlying rows such as `review_item.row_data`?
4. Must particular metrics have a stricter drill-down policy than others?

Minimum-disclosure default for the decision meeting: keep aggregate access as-is
only if explicitly approved, and gate row-level drill-down to named operational
roles (initial comparison: `admin`/`coordinator`). This is a recommendation, not
authorization to edit code.

**Safe engineering preparation**

- Inventory every current and planned drill-down row field and classify its
  sensitivity; specifically include imported `row_data`.
- Draft an ADR-0014 policy amendment comparing: both ungated, both gated, or
  split aggregate/drill-down.
- Prepare expected policy-matrix deltas without changing current assertions.

**After decision**

- `services/api/smartmatch_api/routers/metrics.py`: use separate aggregate and
  drill-down authorizers/constants if policies differ; continue loading the
  unit and calling `assert_allowed`.
- `tests/authz/test_policy_matrix.py`: remove only the operations that became
  gated from `INTENTIONALLY_UNGATED_OPERATIONS`, set role constants, and update
  every matrix cell plus negative tests.
- `tests/contract/test_metrics.py`: add endpoint-level refusal tests while
  preserving aggregate/drill-down equality for authorized callers.
- Update the decision record and regenerate/check
  `contracts/openapi/smartmatch.json` only if response documentation changes.

**Acceptance**

- The committed policy names roles separately for aggregate and rows.
- Wrong-role, sibling-unit, suspended, cross-tenant, expired-membership, and
  explicit-deny cases are tested.
- No option becomes “any authenticated user”; unit scope always remains.
- Authorized drill-down count still equals the aggregate.

**Do not build yet:** current intentional ungating remains until the explicit
product/security decision. Do not silently mirror imports or silently bless the
status quo.

### 5.5 `board_role` ownership — human-decision-required

**Required Dr. Wang decision**

- Is `board_role` intrinsic to a professional, or scoped to that professional’s
  relationship with one unit/chapter?
- If relationship-scoped: can a person have multiple simultaneous roles, and
  what are effective dates/source semantics?

**Safe engineering preparation**

- Bring two sample exports showing the behavior of one person in two units.
- Draft both column/schema shapes and an expand-phase migration outline.
- Keep `board_role` optional in `columns.yaml` as the explicitly documented
  holding position.

**After decision**

- Flat choice: update `columns.yaml` commentary/fixtures and bind the worker’s
  `validate_columns` arguments to the ratified contract.
- Relationship choice: update `columns.yaml`; add a tenant/unit-anchored
  relationship table in a new migration and `schema.py`; add fixture,
  schema-drift, tenant-isolation, and migration tests; then wire import mapping.

**Acceptance**

- The decision and multiplicity/effective-date semantics are written.
- Fixtures cover the chosen shape and reject the discarded interpretation.
- Worker validation uses the ratified required/optional columns.

**Do not build yet:** no permanent professional column or unit-relationship
schema before Dr. Wang answers.

### 5.6 Optional public URL/contact fields — human-decision-required

**Required Dr. Wang/privacy decision**

Choose collect or drop separately for:

- `Public URL`
- `Point(s) of Contact (published)`
- `Contact Email / Phone (published)`

If collecting contacts, privacy/records must define purpose, minimization,
retention, correction, and who may view/export them. “Published” is provenance,
not consent for platform disclosure or outreach.

**Safe engineering preparation**

- Supply sample rows with absent URL, valid public URL, named contact, email,
  and phone values; do not use real PII.
- Draft validation and redaction expectations.
- Inventory UI/API consumers; today `Opportunities.tsx` reads public URL only
  from the legacy path.

**After decision**

- Drop choice: remove fields from `docs/pilot-data/columns.yaml` optional list,
  update `docs/pilot-data/README.md`, and update fixture verification.
- Collect choice: add synthetic valid/invalid fixtures, validation findings, and
  role/minimum-disclosure tests before worker wiring.
- Keep contact data out of event titles, tags, metric drill-downs, and public
  opportunity payloads unless the approved policy explicitly permits it.

**Acceptance**

- Every field has an explicit collect/drop decision.
- Collected contact data has purpose, retention, audience, and tests.
- No scraped/published contact is treated as contact consent or disclosure
  consent.

**Do not build yet:** do not ingest, render, or expose contact fields before Dr.
Wang and the privacy owner approve collection and disclosure behavior.

### 5.7 Two opportunities pages agree (Fix #5) — blocked-on-stakeholder

**Required workshop/decision**

- Write the canonical metric definition. “Opportunities” alone is invalid under
  ADR-0011.
- Decide whether it means events eligible for publication, events in a match
  pool, or events with a candidate above a score floor.
- If a score floor is included, this item inherits G1.
- Decide which variants deserve distinct registered names rather than UI
  filters.

**Safe engineering preparation**

- Inventory every current use of “opportunities” in `Dashboard.tsx`,
  `Pipeline.tsx`, `Opportunities.tsx`, and `METRIC_REGISTER`.
- Draft metric-register entries with definitions left for workshop completion.
- Design one S12 evidence/read model capable of returning both aggregate and
  exact constituent rows.
- Keep current pipeline metrics `null` with `PIPELINE_UNKNOWN_REASON`.

**After definition and upstream evidence**

- Add S12 persistence in a new migration/`schema.py`; define one lifecycle and
  owning query for Matched -> Contacted -> Confirmed -> Attended -> Member
  Inquiry.
- `smartmatch_domain/metrics.py`: register the approved canonical opportunity
  metric/variants with one owning-query identifier.
- `routers/metrics.py`: bind the identifier to a storage-backed row query; derive
  aggregate from those same rows.
- `tests/contract/test_metrics.py`: prove clicked N returns exactly N rows,
  including zero and non-zero cases, unit isolation, and authorization.
- `apps/web/legacy-frontend/src/lib/api.ts` and metrics helpers/hooks: consume
  only the registered metric API.
- `Opportunities.tsx`, `Dashboard.tsx`, and `Pipeline.tsx`: remove client-side
  CSV/crawler merges and subscribe to the same registered metric or clearly
  named variants. Remove fabricated dates/roles and hide unresolved events.
- Keep matcher actions absent until G1.

**Acceptance**

- One written definition maps to one owning query.
- All surfaces display the same metric value or explicitly different registered
  names.
- Drill-down row count equals aggregate and is unit-scoped.
- Unknown remains unknown until evidence exists; unresolved dates and
  quarantined tags never list.

**Do not build yet:** no opportunity metric, total, list rewrite, or S12-backed
claim before the definition and evidence dependencies close. Do not “fix” the
disagreement by making both pages consume the same fabricated client merge.

## 6. Verification and delivery gates

### Local

- `make check` runs `pytest tests/ -m "not integration"` and therefore does not
  prove PostgreSQL behavior.
- Run focused unit/authz/contract tests for the slice.
- `make openapi-check` whenever route/response contracts change.
- For web work, run `npm run typecheck`; run `npm run build` where the local
  filesystem permits.

### CI and PostgreSQL

CI supplies PostgreSQL 16, applies all migrations from an empty database, and
runs full `pytest tests/`. Any migration, owning query, engagement constraint,
or drill-down contract is merge-blocked until that CI job is green. A local
green `make check` is insufficient.

The CI web job performs locked install, typecheck, Vite build, and audit. This is
the authoritative clean-build check when DrvFs prevents `npm ci`.

### Git/remote

- Keep implementation slices reviewable and decision artifacts separate where
  useful.
- Never commit `.claude/`, credentials, `.env` files, real PII, or provider
  tokens.
- Do not push or open a pull request unless a human explicitly asks.
- Nothing in this plan constitutes a production-readiness statement.

## 7. Recommended next slice and ordered backlog

**Recommended next implementation slice:** Wave A / Fix #7A — remove the
caller-chosen role UI and role-bearing login links, add the narrow source
contract test, then typecheck. It has immediate stakeholder value, changes no
backend authorization, and does not depend on fabricated metrics or unavailable
domain data.

Ordered backlog:

1. Fix #7A caller-chosen-role UI removal.
2. Decision packet/workshops: D1/G1, metrics authz, G3, D6/D7, Dr. Wang columns,
   and canonical opportunities definition.
3. Apply metrics role decision and Dr. Wang column decisions.
4. A1b real sign-in plus removal of fallback browser identities.
5. G1-approved M1-M10 matching sequence.
6. G3-approved S3-S5 event persistence, review queue, and constrained crawler.
7. S6/S7 plus D6/D7-approved S8/S9 rewards catalog/redemption.
8. Approved S12/S1 opportunity owning query and shared frontend subscribers.

