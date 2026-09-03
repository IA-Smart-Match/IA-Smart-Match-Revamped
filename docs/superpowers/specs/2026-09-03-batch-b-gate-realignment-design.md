# Batch B gate realignment design

**Date:** 2026-09-03  
**Status:** Approved for implementation  
**Scope:** Correct the four findings from the review of
`189bb965...77d2b1e` without changing the concurrent uncommitted G1 work.

## Why this is a realignment, not missing planning

The affected features already have substantial designs and implementation
plans. The defect is that implementation advanced beyond the authorization
boundaries those documents state.

| Feature | Existing design and plan | Prototype already implemented | Decision or contract still missing |
|---|---|---|---|
| Rewards | ADR-0013, the engagement model, the P7 rewards plan, and the D6 decision record define the intended ledger, catalog, and delivery sequence. | Commit `c075817` added domain and persistence repositories, reversal-target migration `0014`, and tests. | D7 earn policy and calibration, funded catalog content, fulfilment commitments, and read/redemption roles. The D6 record explicitly withholds authorization for L1-L4 behavior. |
| Institutional JWKS | The P2 institutional-sign-in plan defines A0-A4 and the worksheet defines every required configuration field. | Commit `b2ce05a` added an isolated verifier core, static-key port, and unit tests. | Approved issuer, audience, JWKS retrieval and rotation policy, client-flow contract, configuration approver, runtime signature backend, fetching, and application wiring. The plan permits A0 only until these exist. |
| Pipeline conversions | ADR-0011 defines registered names, one owning query, unknown handling, and aggregate/drill-down reconciliation. | Commit `55464a4` computes four conversion ratios in the browser from registered stage counts. | Registered conversion definitions and server-owned queries. The implementation diverged from an existing contract; planning is not absent. |

The prototype work remains recoverable from its commits. Removing it from the
current tree does not discard the design or prevent selective restoration after
the gates close.

## Corrective design

### Rewards

Remove the rewards domain module, persistence repository, and their focused
tests from the pilot branch. Restore the schema model to the authorized state.
Do not delete migration `0014`, because a developer database may already report
that revision as applied. Add migration `0015` that removes the reversal target,
self-reference, and supporting uniqueness constraint; its downgrade recreates
the exact `0014` structure.

This correction does not add a reward route, catalog seed, earn policy,
redemption path, or database append-only trigger. The prototype can later be
recovered from `c075817` and revised against the ratified D7 and role decisions.

This removal is a narrow rolling-deploy exception to ADR-0009. The repository's
deployment boundary in `CONTRIBUTING.md` states that nothing here is deployed,
so no deployed release or older running process ever included either the
`c075817` rewards repository or migration `0014`; no runtime can depend on
`reverses_entry_id`. Revision `0015` exists only to preserve continuity for
local developer databases that may already report `0014` applied. If `0014`
had reached a deployed environment, removing its contract would require a
later release after all older processes had stopped depending on it. This
exception clarifies only the approved `0015` correction and is not a general
waiver of ADR-0009's expand/contract rule.

### Institutional JWKS

Remove the verifier module and its focused tests. Keep the A0 worksheet and its
source-backed inventory, but remove statements that describe the unauthorized
A1 prototype as current implementation. All unresolved configuration and
approval fields remain explicitly outstanding. The existing fixture verifier
and current runtime behavior remain unchanged.

The verifier prototype remains recoverable from `b2ce05a`. After the worksheet
is approved, useful pieces may be restored and checked against the actual IdP
contract instead of treating generic static-key verification as pilot evidence.

### Pipeline conversions

Remove `stageConversionMetric` and the user-visible conversion-rate tiles.
Retain the five registered funnel metrics and their drill-downs. Extend the
frontend contract guard so a client-side stage-ratio implementation fails the
test. Conversion rates may return only as registered metrics with server-owned
queries.

### Authoritative documentation

Update the README capability table to say explicitly that user authentication
uses the fixture verifier and has no committed JWKS implementation, and that
student engagement has base schema/design only with no catalog repository,
earning service, ledger fold, or routes. Documentation must describe the final
tree without assigning readiness credit to preserved Git history.

## Change and commit boundaries

The existing uncommitted edits to `Volunteers.tsx`,
`VolunteerAssignments.tsx`, and `api.ts` belong to the concurrent G1 fix and
will not be edited, staged, or committed by this work.

This design document is one commit. The corrective implementation is a second
commit. Review-driven corrections will be amended into the implementation
commit so the corrective change remains atomic.

## Verification

The implementation must run focused frontend, migration, rewards-removal, and
JWKS-removal guards first. It must then run `make check`, `make migrate-check`,
`make openapi-check`, and `make test-integration`, plus frontend typecheck and
build. Each result will be reported as passed, failed, skipped, or unrun. A
skipped PostgreSQL lane is not passing evidence.

## Success criteria

1. No rewards or JWKS prototype implementation remains in the final source tree.
2. A database at revision `0014` can advance through corrective revision `0015`.
3. No browser-computed pipeline conversion metric is rendered or exported.
4. The README precisely describes the remaining fixture/schema-only posture.
5. The concurrent G1 work remains byte-for-byte outside this commit.
