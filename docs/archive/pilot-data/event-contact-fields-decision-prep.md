# Event URL and published contact fields — decision prep (Dr. Wang)

**Status:** optional in `columns.yaml` — **no fixtures, no ingest wiring**.  
**Classification:** human-decision-required (plan §5.6).  
**Privacy:** ADR-0014 — "published" is provenance, not consent for platform disclosure.

## Fields awaiting collect/drop decision

Choose **separately** for each:

| Column (events.optional) | Collect? | Notes |
|---|---|---|
| `Public URL` | TBD | Link to public event page |
| `Point(s) of Contact (published)` | TBD | Named contact — PII |
| `Contact Email / Phone (published)` | TBD | Direct contact — PII |

## Synthetic sample rows (not real PII)

### Absent URL and contacts

```json
{
  "Event / Program": "Intro to Robotics",
  "Category": "Workshop",
  "Host / Unit": "Cal Poly Pomona"
}
```

### Valid public URL only

```json
{
  "Event / Program": "Careers in AI Panel",
  "Category": "Panel",
  "Public URL": "https://example.edu/events/ai-panel-2026"
}
```

### Named contact without direct email/phone

```json
{
  "Event / Program": "Mentor Night",
  "Category": "Networking",
  "Point(s) of Contact (published)": "Campus Programs Office"
}
```

### Email and phone (if collected — requires privacy review)

```json
{
  "Event / Program": "Volunteer Orientation",
  "Category": "Training",
  "Contact Email / Phone (published)": "programs@example.edu; (555) 010-0200"
}
```

## Validation expectations (if collected)

- URL: HTTPS preferred; reject `javascript:` and internal schemes.
- Contact fields: never merge into event title, tags, or metric drill-down.
- Redaction rules for exports and minimum-disclosure roles (tie to metrics authz
  decision).

## UI / API consumers today

| Consumer | Field used | Source |
|---|---|---|
| `Opportunities.tsx` `mapEventToOpportunity` | `Public URL` when present | legacy `/api/data/*` (not pilot import) |
| Metrics drill-down | none for events | S12 not started |
| Crawl adapter (future) | must not put contact in title | ADR-0012 |

## After decision

**Drop:** remove from `columns.yaml` optional, update README, adjust fixtures.

**Collect:** add valid/invalid fixtures, validation findings, role/minimum-disclosure
tests **before** worker wiring.

## Do not build yet

- No ingest of contact fields without Dr. Wang + privacy owner approval.
- No rendering in public opportunity payloads without explicit policy.

## References

- `docs/pilot-data/columns.yaml` (`open_questions` second item)
- `docs/architecture/decisions/ADR-0014-disclosure-consent.md`
- `apps/web/legacy-frontend/src/app/pages/Opportunities.tsx` (legacy path only)
