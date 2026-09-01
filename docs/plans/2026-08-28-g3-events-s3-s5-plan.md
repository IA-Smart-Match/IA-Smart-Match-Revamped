# Implementation plan — G3 event pipeline: S3–S5, review queue, constrained crawler

**Date:** 2026-08-28 · **Plan id:** P6 · **Worktree branch:** `plan/g3-events`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

> **Amended/superseded for scope — 31 August 2026.** This plan's cards are
> superseded for scope by
> `docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
> §7 (slice V3) and recorded in
> `docs/decisions/2026-08-31-session-ratification.md` §7. **Authorized now:**
> internal iCal/JSON-LD parsers, committed synthetic fixtures, and the
> contact-free `ContactFreeEventCandidate` public wrapper only — no runtime
> caller. **Cards S3–S6 below (persistence, deterministic identity/upsert,
> vocabulary/review queue, crawl adapter) remain gated on the unsigned
> P6/R3 stop-gate exactly as this plan already states below, and do not
> start early.** A later agent may not select a card from this file without
> first checking the current authorized boundary in the design and the
> ratification record — this file's continued existence is not permission to
> run its cards.

## Standing constraints (restated; permanent)

- No crawler route, crawl worker, crawl UI, or crawl network call before the
  stop-gate passes. Do not port `CrawlerFeed`, `CrawlerContext`, or any legacy
  `/api/crawler/*` endpoint (archived as MM-A08).
- ADR-0010/ADR-0012 invariants: unresolved events have no identity key and
  never publish or match; provenance never enters a title; unmapped tags are
  quarantined and never enter read/match results.
- **Latency invariant (shared with plan P4):** crawling runs worker-side via
  the durable job path only; no API request ever waits on a fetch. The legacy
  repository's 5–10 s Tavily-on-request-path behavior is prohibited.
- No live crawl targets, live providers, or real contact data in tests.
- No push, no PR, no production-readiness claims.

## Stop-gate (verify before any card)

Two committed artifacts are required:

1. **G3 decision** — successor to the workshop over
   `docs/security/crawler-threat-model-draft.md` and
   `docs/plans/prep/s3-s5-event-persistence-design.md`, ratified by a named
   owner, containing non-blank: approved agent evaluation set and pass/fail
   criteria; allowed tools and domains (explicit allowlist); extraction limits
   (pages, depth, bytes, wall time); per-run/per-tenant rate and cost ceilings;
   human escalation behavior; the named owner and versioning process for the
   closed tag vocabulary, with the approved initial terms.
2. **R3 threat-model sign-off** — the threat model no longer marked draft,
   signed by a **named security reviewer**, covering SSRF, DNS rebinding,
   redirect chains, private/link-local addresses, egress policy, response
   limits, parser isolation, credential handling, and audit/provenance.

If either is missing, tentative, or unsigned: **stop and report.** Cards
S3/S4 (persistence without vocabulary or crawling) still require gate passage
per the remedy plan; do not start them early without explicit human
authorization recorded in the artifact.

## Current state (verifiable)

- `services/api/smartmatch_api/routers/events.py` declares no handlers;
  OpenAPI has no event/crawl/discovery route.
- Pure domain contracts exist in `smartmatch_domain.events`:
  `resolve_identity_key()` returns `None` for `UnresolvedTime`;
  `resolve_tag()` quarantines unmapped values; `matchable_tags()` returns
  mapped tags only. `tests/unit/test_events.py` covers them.
- `attendance_record.event_id` has no FK — no `event` table exists yet.
- `tests/unit/test_matching_fail_closed.py` rejects committed crawl routes;
  its deliberate flip happens only in card S6b if the G3 artifact calls for
  HTTP surfaces.

## Task cards

### Card S3 — event persistence (serial migration resource)

- **Fence:** new expand-phase migration under `db/migrations/versions/`
  (number from the portfolio migration owner);
  `python/smartmatch_persistence/smartmatch_persistence/schema.py`;
  `tests/unit/test_engagement_schema.py`-style unit tests; new integration
  tests under `tests/integration/`.
- **Work:** `event` table per the prep design: tenant/unit anchoring, temporal
  columns with the ADR-0010 precision enum, `unresolved` status, structured
  provenance columns (source URL, fetch time, extractor version) separate from
  display fields, review status. CHECK constraints: unresolved events cannot
  hold publishable/matchable status.
- **Tests:** migration applies from empty DB; constraints reject
  publishable-unresolved rows (integration, CI-proof).

### Card S4 — deterministic identity and upsert (after S3)

- **Fence:** new repository/service module in `smartmatch_persistence` (or the
  repo's adapter layout) + tests; no router changes.
- **Work:** compute the ADR-0012 identity key (host org unit + normalized
  title + resolved date window) before insert; unique index on the key;
  duplicate keys update the existing event; unresolved events (key `None`)
  insert without identity and cannot be deduplicated into resolved ones.
  Provenance stored on write; never concatenated into the title.
- **Tests:** two synthetic sources with one deterministic key yield one event
  (integration); provenance fields never appear in title assertions.

### Card S5 — vocabulary, quarantine, review queue (parallel with S4 after S3)

- **Fence:** vocabulary data module in `smartmatch_domain` (terms **copied
  exactly from the G3 artifact** — the executor never invents terms), review
  queue repository + tests. **No migration in this card.** If tag/review
  persistence needs schema beyond what S3 created, that is a separate serial
  card **S5m**, which runs only after S5f and holds the portfolio migration
  slot listed in the index — S5 itself stays migration-free so it can run
  parallel to S4 safely.
- **Work:** persist mapped tags against vocabulary versions; quarantined raw
  tags persist for human review but never enter read or match results; review
  transitions (approve → maps to vocabulary term; reject → stays quarantined)
  are audited.
- **Tests:** unmapped tag round-trips to the queue and never surfaces in a
  read model (integration).

### Card S5f — attendance FK (after S4; serial migration resource)

- **Fence:** new migration adding the composite FK from
  `attendance_record.event_id` to `event`; integration tests.

### Card S6 — constrained crawl adapter (after S4/S5; worker-only)

- **S6a fence:** new worker-side module in `services/worker/` (or the repo's
  worker layout) + tests. Implements exactly the signed controls: domain
  allowlist checked before and after every redirect (revalidation), private/
  link-local address refusal at resolve time, byte/time/depth/page/rate/cost
  limits, parser isolation, structured audit records, escalation to the human
  queue per the artifact. Runs only through the durable job path. Tests use
  local fixtures/fake transports — never live targets.
- **S6b (conditional):** HTTP command/status surfaces **only if the signed G3
  artifact calls for them** — routes, policy-matrix rows, OpenAPI regeneration,
  and the deliberate flip of the fail-closed scan, all in one commit.

## Evidence ladder

1. Per-card focused pytest; `make check`
2. `make openapi-check` only if S6b runs
3. **CI-only proof:** all migrations from empty PostgreSQL; constraint,
   upsert, quarantine integration tests. Local Windows runs are insufficient.
4. Security acceptance: every control named in the signed threat model has a
   denial test (blocked address, redirect escape, size/time overrun, tool
   outside allowlist).

## Done means

- Unresolved events cannot publish or match (DB-enforced, CI-proven).
- Two sources, one key, one event. Provenance never in the title.
- Quarantined tags never reach read/match results; review queue works.
- Crawl adapter enforces every signed control; API handlers never fetch URLs.
- No card invented a vocabulary term, allowlist entry, or limit value.
