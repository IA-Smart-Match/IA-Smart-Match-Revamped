# S8 / S9 engagement API contract (design prep)

**Status:** design only — **no routes, no listable catalog, no redemption UI**.  
**Gates:** D6, D7, S6 (attendance), S7 (ledger fold).

## S8 — reward listing

**Route (proposed):** `GET /v1/units/{unit_id}/rewards`

**Authorization:** unit-scoped; role set TBD (likely student read + coordinator
admin — separate from metrics authz decision).

**Response shape (proposed):**

```json
{
  "unit_id": "uuid",
  "items": [
    {
      "id": "uuid",
      "display_name": "string",
      "points_cost": 0,
      "reachable": true,
      "budget_owner_display": "string"
    }
  ],
  "balance": null,
  "unknown_reason": "optional — when ledger not available for principal"
}
```

**Rules:**

- Only rows with `funded = true` and non-null `budget_owner_id`.
- `balance` from server ledger fold only — browser never computes points.
- `reachable` derived from approved N (D7) and current balance; unknown if
  balance unknown (ADR-0011).

## S9 — redemption command

**Route (proposed):** `POST /v1/units/{unit_id}/redemptions` (durable command)

**Body:** `{ "reward_item_id": "uuid", "idempotency_key": "string" }`

**State machine:** `requested → approved → fulfilled | denied | expired`

**Properties:**

- Idempotent on `idempotency_key`.
- Authorized per role (coordinator approval step TBD).
- Audit trail via command path + `redemption` table CHECK constraints.

## Explicit non-build

- No seed data in migrations.
- No OpenAPI entries until D6/D7 close and S6/S7 land.
- No weakening of `0009` nullability constraints.

## References

- `docs/pilot-data/rewards-catalog-worksheet.md`
- `docs/architecture/engagement-model.md`
- `tests/integration/test_engagement_schema_constraints.py`
