# PR 157 query-cache contract-test alignment

## Context

PR 157 replaces several hand-written `useEffect` and `useState` server reads
with principal-scoped TanStack Query reads. The frontend build, type check, and
web tests pass, but six Python source-contract tests still require implementation
tokens from the removed state setters or match a safe query-cache resource name
as though it were a forbidden API route.

The exact CI Python command reproduced the failure at PR head
`ac9d32ef0e1b91edee2bdb1decd6117193373919`: 6 failed, 7,682 passed, and 2
skipped.

## Design

Keep the production query-cache implementation unchanged. Update the three
affected Python source-contract test modules so each guard follows the new data
flow while preserving its original product or security invariant:

- The dashboard refusal guard will verify that the feedback query is converted
  through `queryToLoaded`, that the rendered component displays `state.error`,
  and that the shared query helper returns `ApiRequestError.message`.
- The missing-unit hook guard will accept the derived-state form used by the
  three migrated hooks: `unresolved` selects an `"idle"` status and a `null`
  load error. It will no longer require removed setter calls.
- The Connector feedback privacy guard will forbid the actual student feedback
  helpers and route prefix, not the substring used in a safe cache resource
  name. Its roster-failure guard will verify the distinct `rosterQuery.isError`
  to `loadError` path instead of requiring `setLoadError`.

The assertions remain source contracts because that is the established test
style in these modules. No compatibility dead code, dummy setters, cache-key
renames, API changes, or production behavior changes are included.

## Verification

Run the six previously failing tests first and confirm they pass. Then run the
affected Python contract modules, the frontend `npm test`, type check, and build,
and finally the exact CI Python suite against PostgreSQL 16. Formatting and lint
checks will cover the changed Python tests.
