# ADR-0001 — Single monorepo for the SmartMatch platform

**Status:** Accepted
**Date:** 17 August 2026
**Contract:** Architecture v1.1 §3.5, orchestrator contract §11

## Context

The platform comprises a web app, an API service, a private worker, three pure
Python packages, a database schema, infrastructure definitions, and a generated
API client. These could live in one repository or several.

## Decision

One repository, `smartmatch-platform`, laid out per §11 of the orchestrator
contract.

## Rationale

The generated-client pipeline is the deciding factor. Architecture v1.1 §1.11
makes OpenAPI the contract source of truth with the TypeScript client generated
from it and never hand-written. In a single repository, a route change and its
regenerated client land in one commit and one CI run can prove they agree — which
is what `make openapi-check` does. Split across repositories, that check becomes a
cross-repository dance with a window in which the two disagree.

v1.1 §3.5 additionally lists multiple repositories as **deferred**, with the
adoption trigger being independent teams, release cadences, or security
boundaries. None applies at pilot scale.

## Consequences

**Good.** Atomic changes across the API surface, its contract, and its client. One
CI configuration. One dependency policy. Architectural boundaries are enforced by
import-linter (ADR-0002) rather than by repository walls, which is stricter — a
repository boundary would not have prevented the domain from importing pandas.

**Cost.** CI runs more than strictly necessary for a change touching one package.
Acceptable at this size; revisit when the trigger in v1.1 §3.5 fires.

**Reversible.** Package boundaries are already explicit and enforced, so
extracting a package later is a move, not an untangling.
