# Rewards catalog worksheet (D6 / D7 prep)

**Status:** human completion required — **do not seed listable catalog rows**.  
**Gates:** D6 (budget owner per item), D7 (calibration N), S6/S7 before S8/S9.  
**Schema proof:** migration `0009` + `tests/integration/test_engagement_schema_constraints.py`

## Purpose

Capture the accountable catalog content stakeholders must approve before any
`reward_item` rows become listable. Empty cells are intentional — engineering
must not invent owners, funding, or point costs.

## Economy parameters (D7 — workshop)

| Parameter | Proposed default | Approved value | Owner |
|---|---|---|---|
| Points per verified attendance | 25 (ADR-0013 proposal) | | |
| Calibration N ("cheapest reward reachable within N events") | 3 (ADR-0013 proposal) | | |

## Catalog items (complete one row per shippable item)

Legacy names (`studentRewardsCatalog.ts`) are **discussion input only** — costs
2,500–45,000 vs 25 pts/event made every item unreachable (Fix #15).

| Item display name | `points_cost` | `fulfilment_cost` (USD) | `budget_owner_id` (`user_account`) | `funded` (yes/no) | Fulfilment notes |
|---|---:|---:|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

**Rules (schema-enforced — do not weaken):**

- `budget_owner_id NOT NULL` — `test_reward_item_rejects_a_null_budget_owner`
- `funded NOT NULL` — `test_reward_item_rejects_a_null_funded_state`
- `points_cost > 0` — positive cost constraint

## Post-approval engineering (not now)

1. S6/S7: attendance → ledger fold (append-only, no balance column).
2. S8: listing API returns **only** funded, owned items.
3. S9: redemption durable command (`requested → approved → fulfilled | denied | expired`).
4. Live-catalog test: cheapest listed item reachable within approved N events.
5. Retire `studentPoints.ts` and `studentRewardsCatalog.ts` — server values only.

See `docs/plans/prep/s8-s9-engagement-api-contract.md`.

## References

- `docs/architecture/decisions/ADR-0013-attendance-derived-engagement.md`
- `docs/architecture/engagement-model.md`
- `db/migrations/versions/0009_engagement_schema.py`
