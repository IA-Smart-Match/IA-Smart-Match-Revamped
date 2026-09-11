# Rewards catalog worksheet (D6 / D7 prep)

**Status:** human completion required — seed only values the owner has written
into the table below, with `make seed-pilot-rewards`.  
**Gates:** D6 (budget owner per item), D7 (calibration N), S6/S7 before S8/S9.  
**Schema proof:** migration `0009` + `tests/integration/test_engagement_schema_constraints.py`

## Purpose

Capture the accountable catalog content stakeholders must approve before any
`reward_item` rows become listable. Empty cells are intentional — engineering
must not invent owners, funding, or point costs.

## Economy parameters (D7 — workshop)

| Parameter | Proposed default | Approved value | Owner |
|---|---|---|---|
| Points per verified attendance | 25 (ADR-0013 proposal) | 100 (pilot demo, provisional) | Danny Tran |
| Calibration N ("cheapest reward reachable within N events") | 3 (ADR-0013 proposal) | 3 (pilot demo, provisional) | Danny Tran |

**These two are provisional pilot-demo figures and ratify nothing.** They are
the values already in the code — `POINTS_PER_VERIFIED_ATTENDANCE = 100` and
`CALIBRATION_N_TENTATIVE = 3` in `smartmatch_domain.rewards`, both carried from
D7 verbatim — restated here so the catalog below can be *checked* against a
stated number instead of priced against an unstated one.
`smartmatch_domain.rewards.EARN_POLICY_RATIFIED` remains `False` and nothing in
this file moves it.

## Catalog items (complete one row per shippable item)

Legacy names (`studentRewardsCatalog.ts`) are **discussion input only** — costs
2,500–45,000 vs 25 pts/event made every item unreachable (Fix #15).

| Item display name | `points_cost` | `fulfilment_cost` (USD) | `budget_owner_id` (`user_account`) | `funded` (yes/no) | Fulfilment notes |
|---|---:|---:|---|---|---|
| Bronco Bookstore $10 Gift Card | 300 | 10.00 | `compose-pilot-admin` | yes | Digital code, emailed on fulfilment. The calibration floor. |
| CBA Career Closet Voucher | 600 | 35.00 | `compose-pilot-admin` | yes | One interview outfit, collected in person. |
| Professional Headshot Session | 1000 | 60.00 | `compose-pilot-admin` | yes | 15-minute slot at a scheduled campus shoot. |
| Lunch with a Visiting Executive Speaker | 1500 | 45.00 | `compose-pilot-admin` | yes | Six seats per visit; coordinator confirms the date. |
| CBA Leadership Summit VIP Pass | 2500 | 150.00 | `compose-pilot-admin` | **no** | Not funded for the pilot. Present so the catalog demonstrates D6's filter. |

### Why these costs, against how points are actually earned

The whole earn policy is `POINTS_PER_VERIFIED_ATTENDANCE`: **100 points per
verified attendance, and nothing else.** `smartmatch_domain.rewards`'s module
docstring is explicit that "streaks, logins, and referrals earn nothing,
deliberately", and ADR-0013 makes an `attendance_record` row the only input.
One attended event is therefore one 100-point step, and every cost below is
chosen as a whole number of events:

- **300 = 3 events.** The cheapest listed item sits exactly on D7's calibration
  property, `min(points_cost over listed items) <= N * points_per_event` with
  `N = 3`. `seed_pilot_rewards.py` prints that check as a report line; this row
  is the one that clears it.
- **600 = 6 events, 1000 = 10 events.** D7's two remaining recorded bands
  (`D7_TENTATIVE_POINT_BANDS = (300, 600, 1000)`), transcribed rather than
  invented, so the middle of the catalog is the decision record's own shape.
- **1500 = 15 events** is a term's worth of attendance for a student going to
  roughly one event a week: reachable, but only by someone who kept showing up.
- **2500 = 25 events** is deliberately out of reach within a pilot and is left
  **unfunded**, so it is also the catalog's proof that `listable_items` filters
  on `funded` — an unfunded item is not listed however many points a student
  has.

The spread is 300 → 2500, a little over 8×. Legacy `studentRewardsCatalog.ts`
ran 2,500–45,000 against 25 pts/event, which made every item unreachable (Fix
#15); at 100 pts/event this catalog's floor is three events and its funded
ceiling is fifteen.

`budget_owner_id` is the `external_subject` `compose-pilot-admin`, the seeded
administration principal — a real `user_account` row in the pilot tenant, which
is what `reward_item.budget_owner_id NOT NULL` requires. D6 names Danny Tran as
the accountable human; the column takes an account, and this is the account
that person signs in as on the pilot appliance.

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
