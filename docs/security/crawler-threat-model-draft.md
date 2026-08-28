# Crawler threat model — draft for G3 workshop

**Status:** draft for stakeholder/security review — **not signed, not implemented**.  
**Gate:** G3 (`docs/plans/remaining-engineering-implementation-plan.md` §5.2).  
**Related ADRs:** ADR-0003 (no agents in foundation), ADR-0010, ADR-0012, MM-A08 (archived).

## Scope

This document enumerates threats and required controls for a **future** constrained
crawler adapter. It does **not** authorize HTTP crawl code, worker routes, UI, or
live provider calls. Implementation waits on G3 approval and R3 sign-off.

## Non-goals (explicit)

- No port of legacy `CrawlerFeed`, `CrawlerContext`, or `POST /api/crawler/start`.
- No tag vocabulary terms chosen in this draft (S5 / G3 owner).
- No production egress configuration or credentials.

## Trust boundaries

```
[ Internet URLs ] --> [ Crawl adapter (sandboxed) ] --> [ Event ingest service ]
                              |                                    |
                              v                                    v
                     [ Allowlist / budget ]              [ event + provenance tables ]
                              |                                    |
                              v                                    v
                     [ Human review queue ]              [ Quarantined tags only ]
```

Untrusted input enters at URL fetch and response body. Trusted output is
structured event fields + provenance — never scraped text in titles (ADR-0012).

## Threat catalog

| ID | Threat | Required control | Test expectation (post-G3) |
|---|---|---|---|
| T-01 | SSRF to internal/metadata IPs | Block private, link-local, loopback, metadata ranges; no raw IP literals in allowlist without review | Unit + integration deny cases |
| T-02 | DNS rebinding | Re-resolve host before connect; pin resolved IP to policy | Integration with rebinding fixture |
| T-03 | Redirect chains to internal | Re-validate each hop; max redirects; same policy per hop | Redirect chain test |
| T-04 | Response bomb (size/time) | Byte and time ceilings; streaming cap | Oversized body refused |
| T-05 | Parser escape / RCE | Parser isolation; no `eval`; structured extractors only | Fuzz/smoke on parser boundary |
| T-06 | Credential leakage | No secrets in URLs/logs; redact in audit | Log scan in CI |
| T-07 | Tool sprawl | Closed tool allowlist per G3 eval set | Allowlist enforcement test |
| T-08 | Cost runaway | Per-run and per-tenant budget; human escalation | Budget exceeded → quarantine |
| T-09 | Open-ended tags | Map through `TagVocabulary`; unmapped → quarantine | Unmapped never in read API |
| T-10 | Unresolved dates published | `unresolved` → no identity key; no publish/match transition | DB constraint + API refusal |

## Adapter interface (implementation prep)

Domain contracts already exist in `python/smartmatch_domain/smartmatch_domain/events.py`:

- `resolve_identity_key` — deterministic key or refuse when date unresolved
- `EventProvenance` — URL, fetch time, extractor version (never merged into title)
- `resolve_tag` / `QuarantinedTag` — closed vocabulary with quarantine path

A future adapter must:

1. Accept only URLs on an approved allowlist (host + path patterns).
2. Return extraction artifacts separate from normalized event fields.
3. Never call the network from API request handlers — worker/command path only.
4. Write provenance as columns, not title suffixes.

See `docs/plans/prep/s3-s5-event-persistence-design.md` for persistence shape.

## Workshop decisions required (G3)

- [ ] Agent evaluation set and pass/fail criteria.
- [ ] Allowed tools and domains (explicit list).
- [ ] Extraction budget: max pages, depth, bytes, wall time per job.
- [ ] Rate and cost ceilings; escalation when exceeded.
- [ ] Vocabulary growth owner and versioning process (S5).
- [ ] Security reviewer sign-off on this threat model (R3).

## References

- `docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md`
- `docs/architecture/decisions/ADR-0010-event-temporal-model.md`
- `docs/migration/migration-manifest.yaml` (MM-A08)
- `python/smartmatch_domain/smartmatch_domain/events.py`
- `tests/unit/test_events.py`
