# ADR-0002 — Package boundaries enforced by import-linter

**Status:** Accepted
**Date:** 17 August 2026
**Contract:** Architecture v1.1 §1.1, §4.1

## Context

Architecture v1.1 §1.1 specifies four strictly ordered layers, with deterministic
domain logic innermost. The legacy repository had no such separation:
`src/matching/factors.py` imported pandas and `src/config`, which read environment
variables; `src/feedback/acceptance.py` imported Streamlit and wrote CSVs from
inside what was nominally business logic.

The consequence was not theoretical. It meant the scoring rules could not be
tested without a pandas DataFrame, the feedback rules could not be tested without
a Streamlit session, and neither could be reasoned about without knowing what
else they touched.

A stated boundary that nothing checks is a boundary that erodes on the first
deadline.

## Decision

`smartmatch_domain` and `smartmatch_authz` import **no** framework, database
driver, provider SDK, filesystem module, or network library — including `os` and
`pathlib`. This is enforced by import-linter contracts in the root
`pyproject.toml` and run in CI as a required check.

Three contracts:

1. **Domain is pure** — forbids fastapi, starlette, sqlalchemy, alembic,
   pydantic_settings, httpx, requests, google, boto3, os, pathlib, socket,
   subprocess, and `smartmatch_providers`.
2. **Authz is pure** — the same, scoped to policy's needs.
3. **Layering** — providers may depend on domain types; domain may never depend
   on providers.

`include_external_packages = true` is required for contracts 1 and 2, since
"must not import FastAPI" names a third-party module.

## Consequences

**Good.** The domain test suite runs in well under a second with no fixtures, no
database, and no network. Every rule in `eli.py`, `consent.py`, `jobs.py`, and
`factor_registry.py` is testable by calling a function with plain values. When a
rule is wrong, the failing test points at the rule rather than at a mock.

**Cost.** Domain types cannot read configuration, so callers must pass values in
explicitly — `compute_eli` takes a `LoadInputs` rather than fetching engagements,
and `generate_ics` takes `generated_at` rather than reading the clock. This is
slightly more verbose at the call site and is the reason those functions are
deterministic under test.

**Enforcement is real, not decorative.** Verified by deliberately adding
`import os` to a domain module: the contract reported `BROKEN`. Anyone can repeat
this in ten seconds, and the README tells them how.

## Alternatives considered

**Convention plus code review.** Rejected: this is exactly what the legacy had.
Review catches the first violation and misses the fifth.

**Separate repositories per package.** Rejected: v1.1 §3.5 defers multiple
repositories until independent teams, release cadences, or security boundaries
justify the cost. None applies at pilot scale, and the coordination overhead
would be immediate.

**Runtime import hooks.** Rejected: fails at runtime rather than at review time,
which is later and more disruptive than a CI check.
