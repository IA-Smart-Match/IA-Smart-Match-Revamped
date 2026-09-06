# P7/D6 — rewards schema and append-only verification

**Scope:** Slice V6 (P7), boundary only. This is a **verify-only** record: it
adds no schema, no migration, no trigger, and no test. Where a guard was found
absent, that absence is reported here, per the D6 permitted implementation
boundary ("If a database append-only guard is found absent, that gap is
reported rather than added under this session").

## Fixed point and environment

- Branch: `friday-deliverable-828`
- Commit: `93a93f8cc1a52101053266171d35cb296c42d087`
- Environment: WSL, repository `.venv` (Python 3.12.3, pytest 9.1.1)
- **PostgreSQL:** contrary to the working assumption stated in this task's
  instructions ("No PostgreSQL available"), a local PostgreSQL 16 instance
  (`postgresql.service`, cluster `main`, port 5432) was running and reachable
  in this environment, with a `smartmatch` database and role already
  provisioned and already migrated to head `0011_pipeline_record` (confirmed by
  `SELECT version_num FROM alembic_version`; the `0009_engagement_schema`
  tables this record verifies are therefore present as part of that history,
  alongside `0010_spend_reservation` and `0011_pipeline_record`) (confirmed by
  `\dt` listing `alembic_version` alongside `attendance_record`,
  `point_ledger_entry`, and `reward_item`). Both the unit-level schema tests
  and the PostgreSQL-backed integration tests were therefore run for real,
  and this record's verdicts are evidenced by their actual output plus direct
  `psql` inspection of the live schema — not inferred from source alone.

## Files inspected

- `python/smartmatch_persistence/smartmatch_persistence/schema.py`
- `db/migrations/versions/0009_engagement_schema.py`
- `tests/unit/test_engagement_schema.py`
- `tests/integration/test_engagement_schema_constraints.py`

No file in this list was edited. No migration, schema module, or test was
added, changed, or removed as part of this verification.

## Commands run

```text
.venv/bin/python -m pytest tests/unit/test_engagement_schema.py -q
```
Result: **5 passed.**

```text
.venv/bin/python -m pytest tests/integration/test_engagement_schema_constraints.py -q
```
Result: **31 passed** (PostgreSQL-backed; none skipped).

```text
PGPASSWORD=smartmatch psql -h localhost -U smartmatch -d smartmatch -c "\d point_ledger_entry"
PGPASSWORD=smartmatch psql -h localhost -U smartmatch -d smartmatch -c "\d reward_item"
PGPASSWORD=smartmatch psql -h localhost -U smartmatch -d smartmatch -c "SELECT t.tgname AS name FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE c.relname = 'point_ledger_entry' AND NOT t.tgisinternal UNION ALL SELECT rulename AS name FROM pg_rules WHERE tablename = 'point_ledger_entry';"
PGPASSWORD=smartmatch psql -h localhost -U smartmatch -d smartmatch -c "\dt"
```
Results are reported inline against each check below.

---

## Check 1 — `reward_item.budget_owner_id` is `NOT NULL`, no server default; the null-owner test exists and asserts it

**Verdict: CONFIRMED.**

- Declaration: `python/smartmatch_persistence/smartmatch_persistence/schema.py:495`
  — `sa.Column("budget_owner_id", _UUID, nullable=False)`, no `server_default`
  argument (contrast with `funded` five lines below at
  `schema.py:500`, which does carry
  `server_default=sa.text("false")`). Same shape in the migration itself:
  `db/migrations/versions/0009_engagement_schema.py:222`
  (`sa.Column("budget_owner_id", postgresql.UUID(as_uuid=True), nullable=False)`,
  no default).
- Live schema confirms it: `psql \d reward_item` reports `budget_owner_id |
  uuid | not null |` with an empty `Default` column, vs. `funded | boolean |
  not null | false`.
- Unit-level pin: `tests/unit/test_engagement_schema.py:74-82`,
  `test_reward_item_budget_owner_id_is_not_nullable`, asserts
  `schema.reward_item.c.budget_owner_id.nullable is False` directly against
  the `sa.Table` object — **passed**.
- The behavioral test named in the task exists and asserts the null rejection:
  `tests/integration/test_engagement_schema_constraints.py:292-298`,
  `test_reward_item_rejects_a_null_budget_owner`, inserts a row with
  `budget_owner_id=None` inside `pytest.raises(IntegrityError, match=r"(?i)null
  value|not-null|budget_owner_id")` — **passed** against the live database.
- Companion coverage also present and passing: `test_reward_item_rejects_an_omitted_budget_owner`
  (`tests/integration/test_engagement_schema_constraints.py:410-421`, an
  omitted column rather than an explicit `NULL`), and
  `test_a_reward_cannot_be_stripped_of_its_owner_after_it_is_written`
  (`tests/integration/test_engagement_schema_constraints.py:483-505`, `NOT
  NULL` also governs `UPDATE ... SET budget_owner_id = NULL`, not just
  `INSERT`).

## Check 2 — is `point_ledger_entry` append-only at the database level, or only by convention?

**Verdict: BY CONVENTION ONLY. No database-level guard exists.** This is the
gap the task asked to be reported rather than closed.

- What actually enforces "append-only" today is the **absence of any mutable
  bookkeeping column** — no `status`, no `version`, no `updated_at`, no
  `balance` (`schema.py:452-479`; migration
  `db/migrations/versions/0009_engagement_schema.py:186-216`). That is a real
  but structural-not-behavioral guarantee: it removes the *field* an
  application would naturally overwrite, but it does not stop a raw `UPDATE
  point_ledger_entry SET amount = ... WHERE id = ...` or a `DELETE FROM
  point_ledger_entry WHERE id = ...` from succeeding at the database level.
  Nothing in PostgreSQL itself refuses either statement.
- The migration's own docstring says this plainly:
  `db/migrations/versions/0009_engagement_schema.py:9-13` lists `redemption`
  (S9) as deferred, and the `point_ledger_entry` section
  (`0009_engagement_schema.py:96-98`) states append-only is "enforced by what
  is absent" — a comment, not a constraint.
- The test suite already asserts the absence directly, and says explicitly
  that closing it is out of scope for this session:
  `tests/integration/test_engagement_schema_constraints.py:616-648`,
  `test_the_ledger_has_no_database_level_append_only_guard_yet`. It queries
  `pg_trigger` and `pg_rules` for any non-internal trigger or rule on
  `point_ledger_entry` and asserts the result is empty, with this docstring
  (`:619-631`):

  > "Append-only on `point_ledger_entry` is structural (the test above) and
  > conventional (ADR-0013), and it is **not** enforced by the database: no
  > trigger and no rule refuses an `UPDATE` or a `DELETE` on this table
  > today. Migration `0009` records that as a non-blocking note and
  > `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` card **L2** owns the fix,
  > which is gated and not authorized by the D6 pilot-scope record — that
  > record says a missing guard is to be *reported*, not added. This test is
  > the report, in the only form that cannot go stale unnoticed. **When L2
  > lands, this test fails**, and that is the intended behaviour."

  This test **passed** in this run (part of the 31/31 above), which — per its
  own docstring — is itself the confirmation that the gap is still open.
- Independent confirmation against the live database (not just the test),
  run directly in `psql`:

  ```text
  SELECT t.tgname AS name FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    WHERE c.relname = 'point_ledger_entry' AND NOT t.tgisinternal
  UNION ALL
  SELECT rulename AS name FROM pg_rules WHERE tablename = 'point_ledger_entry';
  ```
  Result: **`(0 rows)`.** No trigger, no rule, on the actual provisioned table.

**What this gap would cost to leave.** As things stand, nothing at the
database layer stops an `UPDATE` or `DELETE` against `point_ledger_entry` —
only application discipline (no route or service issues one today) and the
missing `status`/`version`/`updated_at` columns (which remove the *obvious*
thing to mutate but not the ability to mutate `amount`, `reason`, or
`source_attendance_id` directly, or to delete the row outright) stand between
the current schema and a silent balance rewrite. A `BEFORE UPDATE OR DELETE`
trigger that raises, or an equivalent `RULE`, is the fix — that is exactly
what plan card **L2** (`docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`,
superseded for scope but not for content) already scopes, and exactly what
`test_the_ledger_has_no_database_level_append_only_guard_yet` is written to
start failing against once it lands. **No such trigger or rule is added by
this session.**

## Check 3 — `amount <> 0` check constraint and the composite foreign key

**Verdict: CONFIRMED, both present and correct.**

- `ck_point_ledger_entry_amount_nonzero`: declared at `schema.py:478`
  (`sa.CheckConstraint("amount <> 0", ...)`) and in the migration at
  `db/migrations/versions/0009_engagement_schema.py:214-216`. Live schema
  confirms it verbatim: `psql \d point_ledger_entry` lists `"ck_point_ledger_entry_amount_nonzero"
  CHECK (amount <> 0)`. Behaviorally proven by
  `tests/integration/test_engagement_schema_constraints.py:249-256`
  (`test_point_ledger_entry_rejects_a_zero_amount`, expects
  `IntegrityError` matching the constraint name) and
  `:259-271` (`test_point_ledger_entry_accepts_a_positive_credit_and_a_negative_reversal`,
  proving signed reversal entries — not deletes or updates — are the correction
  path). Both **passed**.
- Composite foreign key: `schema.py:473-477` —
  `sa.ForeignKeyConstraint(["tenant_id", "source_attendance_id"],
  ["attendance_record.tenant_id", "attendance_record.id"],
  ondelete="RESTRICT")`; migration at
  `db/migrations/versions/0009_engagement_schema.py:198-203`. Live schema
  confirms it: `"point_ledger_entry_tenant_id_source_attendance_id_fkey"
  FOREIGN KEY (tenant_id, source_attendance_id) REFERENCES
  attendance_record(tenant_id, id) ON DELETE RESTRICT`. It is composite (not a
  bare `source_attendance_id -> attendance_record.id`) so a source id from
  another tenant cannot be cited — the same pattern `reward_item`'s
  `budget_owner_id` FK uses. Behaviorally proven by
  `tests/integration/test_engagement_schema_constraints.py:274-284`
  (`test_point_ledger_entry_source_must_reference_a_real_attendance_record`,
  a fabricated `uuid.uuid4()` source is refused) and
  `:598-613` (`test_the_attendance_a_ledger_entry_derives_from_cannot_be_deleted`,
  `ON DELETE RESTRICT` is exercised directly with a live `DELETE` statement).
  Both **passed**.

## Check 4 — is a balance a fold over the ledger, or a stored mutable column?

**Verdict: CONFIRMED — fold only. No balance column exists anywhere in the schema.**

- `point_ledger_entry` has no `balance` column (`schema.py:452-479` — the
  full column list is `id, tenant_id, amount, source_attendance_id, reason,
  actor_id, occurred_at`), and no other table in the schema has one either.
  This is checked generically, not just for this table:
  `tests/unit/test_engagement_schema.py:34-52`,
  `test_no_table_has_a_balance_column`, iterates every table in
  `schema.METADATA.tables` and fails if any column name contains `"balance"`
  (case-insensitive substring match, so `student_balance` or `pointsBalance`
  would also be caught) — **passed**.
- Live confirmation: `psql \dt` lists all 22 tables in the migrated
  `smartmatch` database (`attendance_record`, `point_ledger_entry`,
  `reward_item`, `tenant_budget`, `spend_ceiling_bucket`,
  `spend_reservation`, etc.); none is a rewards-balance table, and `\d
  point_ledger_entry` / `\d reward_item` above show no `balance` column on
  either.
- The migration's own docstring is explicit about this being the point of the
  design, not an accident: `db/migrations/versions/0009_engagement_schema.py:19-22`
  — "a balance is a fold over an append-only ledger, computed server-side,
  never stored. **There is no balance column on this table, or on any other
  table this migration touches.**" Schema-file comment at `schema.py:459-461`
  says the same thing at the point of declaration.
- No fold implementation (the code that would sum `point_ledger_entry.amount`
  per subject into a balance on request) exists in this repository today —
  confirmed by the absence of any such module in
  `python/smartmatch_persistence` or `services/api`, and by the D6 boundary
  itself, which does not authorize building one (card **L1**, ledger fold, is
  explicitly gated and out of scope for this session).

## A table named in the task that does not exist: `redemption`

The task's read-first list refers to "the redemption table" in `schema.py`.
**No such table exists.** `redemption` is one of the three tables (with
`event` and `disclosure_consent`) that
`db/migrations/versions/0009_engagement_schema.py:8-13` explicitly defers —
"`redemption` … is S9 and deferred" (`0009_engagement_schema.py:119`, and
again at `:159`) — and the live `\dt` listing above has no `redemption` row.
This is consistent with the D6 boundary, which authorizes no redemption
behavior. Nothing about `redemption` could be verified because there is
nothing yet to verify; this is recorded rather than treated as a check that
silently passed.

## Summary table

| # | Check | Verdict | Primary evidence |
|---|---|---|---|
| 1 | `reward_item.budget_owner_id` NOT NULL, no default; null-owner test exists | **CONFIRMED** | `schema.py:495`; `tests/integration/test_engagement_schema_constraints.py:292-298` (passed) |
| 2 | `point_ledger_entry` append-only at the DB level | **GAP — convention only, no trigger/rule** | live `pg_trigger`/`pg_rules` query: 0 rows; `tests/integration/test_engagement_schema_constraints.py:616-648` (passed, and passing *is* the confirmation of the gap) |
| 3 | `amount <> 0` check + composite FK | **CONFIRMED, both correct** | `schema.py:473-478`; live `\d point_ledger_entry`; integration tests (passed) |
| 4 | Balance is a fold, not a stored column | **CONFIRMED** | `tests/unit/test_engagement_schema.py:34-52` (passed); live `\dt`/`\d` show no balance column |

## References

- `docs/decisions/d6-rewards-budget-decision-record.md`
- `docs/decisions/pilot-decisions.md` §D6
- `docs/plans/prep/blocked-work-register-830.md` §"P7 — D6/D7 rewards"
- `docs/architecture/decisions/ADR-0011-accountable-numbers.md`
- `python/smartmatch_persistence/smartmatch_persistence/schema.py`
- `db/migrations/versions/0009_engagement_schema.py`
- `tests/unit/test_engagement_schema.py`
- `tests/integration/test_engagement_schema_constraints.py`
