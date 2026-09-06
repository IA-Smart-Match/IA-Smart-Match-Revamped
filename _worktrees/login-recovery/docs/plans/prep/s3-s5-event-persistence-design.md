# S3–S5 event persistence design (prep)

**Status:** design prep — **no migration, no tables, no crawler**.  
**Gates:** G3 (crawler), Dr. Wang optional URL/contact columns (separate).  
**Domain contract:** `python/smartmatch_domain/smartmatch_domain/events.py`

## Purpose

Describe how ADR-0010 and ADR-0012 land in PostgreSQL once G3 closes, without
choosing tag terms or building the crawl adapter. One owner should own
`tests/integration/test_check_constraints.py` when event migrations start.

## Proposed tables (expand phase)

### `event`

| Column | Type | Notes |
|---|---|---|
| `tenant_id`, `id` | composite PK | ADR-0004 tenant scoping |
| `owning_unit_id` | FK → `org_unit` | Host org unit for identity key |
| `title_normalized` | text | `normalize_title()` output |
| `starts_at` | timestamptz nullable | Exact instant when known |
| `timezone` | text nullable | IANA zone |
| `time_precision` | enum | `exact`, `date_only`, `unresolved` |
| `identity_key` | text nullable | **null when unresolved** — no publish |
| `review_status` | enum | includes quarantine / approved |
| `created_at`, `updated_at` | timestamptz | audit |

**Constraints (behavioural tests required):**

- `identity_key IS NULL` when `time_precision = 'unresolved'`.
- No `publishable` or `matchable` status when `identity_key IS NULL`.
- Unique `(tenant_id, identity_key)` where `identity_key IS NOT NULL`.

### `event_provenance`

Separate from title (ADR-0012). One row per source observation.

| Column | Notes |
|---|---|
| `source_url` | Fetch target |
| `fetched_at` | Wall time |
| `extractor_version` | Pin for replay |
| `raw_snapshot_ref` | Object storage pointer, not inline HTML |

### `event_tag` / `quarantined_tag`

- Mapped tags: FK to closed vocabulary version (S5).
- Quarantined: raw string + review queue status; **never** in match/read APIs.

## `attendance_record.event_id` FK

Deferred until `event` identity exists. Migration order:

1. Create `event` + provenance + tag tables.
2. Backfill or null `attendance_record.event_id` during expand.
3. Add composite FK `(tenant_id, event_id)` in a later migration.

## Identity resolution flow

```
extracted title + host unit + resolved date window
        → resolve_identity_key()
        → upsert on (tenant_id, identity_key)
        → attach provenance row (never mutate title with URL text)
```

Duplicate sources with the same key update one event (ADR-0012 acceptance test).

## Worker / import boundary

- Crawl jobs are durable commands on the worker — not API routes.
- Import path (`validate_columns`) remains separate from crawl extraction.
- Unmapped tags and unresolved dates stop at quarantine — no metric drill-down.

## Test matrix (to add after approval)

| Test | Proves |
|---|---|
| Unresolved date cannot publish | CHECK + API 4xx |
| Two sources, one key → one row | upsert behaviour |
| Unmapped tag not in read model | repository filter |
| Provenance not in title | column separation |
| Tenant isolation | cross-tenant deny |

## References

- `docs/security/crawler-threat-model-draft.md`
- `docs/architecture/decisions/ADR-0010-event-temporal-model.md`
- `docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md`
- `tests/unit/test_events.py`
