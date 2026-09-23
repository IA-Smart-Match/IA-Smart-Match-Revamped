# B26 T2 — `0038_speaker_availability`, mirror, repository

**Next action:** write `tests/integration/test_speaker_availability_migration.py` (§4) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §3 intro, §3.1, §7 row 2, §8 row T2.
Depends on T1 (`origin/feat/b26-t1:docs/plans/b26-tracks/T1-plan.md` §2): `AvailabilityStatement`,
`UnavailableWindow` from `smartmatch_domain.speaker_availability`. Branch `feat/b26-t2`.

## 1. Files

| Path | Change |
|---|---|
| `db/migrations/versions/0038_speaker_availability.py` | **New.** `revision = "0038_speaker_availability"`, `down_revision = "0037_exercise_tables"` (`0037_exercise_tables.py:98`). Hand-written, no autogenerate (ADR-0004). No transaction code: `env.py` runs one transaction per revision (ADR-0009). |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | Mirror both tables after `speaker_profile` (`:2124`); add both to `__all__` (`:25-84`). Same constraint names as the migration. |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_availability.py` | **New.** Repository (§3). Pattern: `match_weight_settings.py:195-311` (`SELECT … FOR UPDATE`, version compare, insert-or-update, session per call, never commits). |
| `tests/integration/test_speaker_availability_migration.py` | **New.** Shape, upgrade/downgrade, every CHECK, FKs, CASCADE (§4.1). |
| `tests/integration/test_speaker_availability_repository.py` | **New.** Repository contract (§4.2). Precedent split: `test_cba_meeting_migration.py` + `test_cba_meetings_repository.py`. |
| `tests/integration/test_check_constraints.py` | Add 6 keys to `CHECK_CONSTRAINT_DEFINITIONS` (`:76`) and `BEHAVIOURAL_COVERAGE` (`:766`) under a "migration 0038" block; `:2826`/`:2852` fail otherwise. |
| `tests/integration/conftest.py` | `_TENANT_SCOPED_TABLES` (`:101`): add `speaker_availability_window`, `speaker_availability` above `speaker_profile` (`:111`). |
| Head pins, 4 files | `HEAD_REVISION`/`_HEAD_REVISION = "0037_exercise_tables"` → `"0038_speaker_availability"`: `test_cba_contact_schema.py:150`, `test_cba_weight_settings_persistence.py:189`, `test_event_filed_by_migration.py:78`, `test_host_organization_migration.py:84` (+ their "chains to" comments). |
| `README.md:35` | "37 Alembic revisions, head `0037_exercise_tables`" → 38 / `0038_speaker_availability`; recount `:36`'s "115 integration" (drift tests are parametrized per mirrored table). |
| `docs/operations/supabase-setup.md:162` | "must land at `0037_exercise_tables`" → `0038_speaker_availability`. (`supabase-maintenance.md:98` already says "or later" — leave.) |
| `docs/operations/exercise-hosting.md:706-716` | Step 2 only (C6): heading "Confirm the migration head is `0038_speaker_availability`", both `grep` commands on `0038_speaker_availability`, pass/fail text ("past `0038`"), head citation → `0038_speaker_availability.py` `down_revision = "0037_exercise_tables"` line. The owner has uncommitted edits to this file in the parent checkout: touch no other line. |

Drift test needs no edit: `test_schema_matches_migration.py:51` parametrizes over `schema.METADATA.tables`;
`:225` enumerates DB tables and fails any `tenant_id` table without a tenant-aligned composite FK.

## 2. DDL

### `speaker_availability`

| Column | Type | Null | Default |
|---|---|---|---|
| `tenant_id` | uuid | no | — |
| `professional_id` | uuid | no | — |
| `invitations_paused_until` | date | yes | — |
| `declared_capacity_hours_per_90_days` | numeric(5,1) | yes | — (never a default, Q6) |
| `version` | integer | no | `1` |
| `updated_source` | text | no | — |
| `updated_by_user_id` | uuid | no | — |
| `created_at`, `updated_at` | timestamptz | no | `now()` (C8) |

- PK `speaker_availability_pkey (tenant_id, professional_id)`.
- FK `fk_speaker_availability_profile (tenant_id, professional_id) → speaker_profile (tenant_id, professional_id) ON DELETE CASCADE`.
- FK `fk_speaker_availability_updated_by (tenant_id, updated_by_user_id) → user_account (tenant_id, id) ON DELETE RESTRICT` — composite, as `match_weight_setting` (`schema.py:2514-2518`) and `fk_speaker_profile_*_classified_by` (`:2275-2287`). A plain FK fails `test_schema_matches_migration.py:225` (C4).
- `ck_speaker_availability_source`: `updated_source IN ('speaker', 'connector')`.
- `ck_speaker_availability_capacity`: `declared_capacity_hours_per_90_days IS NULL OR (declared_capacity_hours_per_90_days > 0 AND declared_capacity_hours_per_90_days <= 720)`.
- `ck_speaker_availability_version`: `version >= 1` (C2; precedent `ck_match_weight_setting_version`, `schema.py:2527`).

### `speaker_availability_window`

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | uuid | no | — (repository supplies `uuid4()`) |
| `tenant_id`, `professional_id` | uuid | no | — |
| `starts_on`, `ends_on` | date | no | — (inclusive) |
| `created_source` | text | no | — |
| `created_by_user_id` | uuid | no | — |
| `created_at` | timestamptz | no | `now()` |

- PK `speaker_availability_window_pkey (id)`.
- FK `fk_speaker_availability_window_statement (tenant_id, professional_id) → speaker_availability (tenant_id, professional_id) ON DELETE CASCADE`.
- FK `fk_speaker_availability_window_created_by (tenant_id, created_by_user_id) → user_account (tenant_id, id) ON DELETE RESTRICT`.
- `ck_speaker_availability_window_order`: `ends_on >= starts_on`.
- `ck_speaker_availability_window_span`: `ends_on - starts_on <= 366` (date − date is integer days; matches T1 `WINDOW_MAX_SPAN_DAYS`).
- `ck_speaker_availability_window_source`: `created_source IN ('speaker', 'connector')`.
- `uq_speaker_availability_window_range UNIQUE (tenant_id, professional_id, starts_on, ends_on)` — a constraint, not a unique index, so `test_unique_constraints_match` sees it.
- Index `ix_speaker_availability_window_ends (tenant_id, professional_id, ends_on)` — not mirrored (`schema.py` declares no indexes; drift test skips them).

**Upgrade order:** create `speaker_availability`, then `speaker_availability_window`, then the index. No data written.
**Downgrade:** `op.drop_index("ix_speaker_availability_window_ends")`, `op.drop_table("speaker_availability_window")`, `op.drop_table("speaker_availability")`. Nothing else touched.

`test_check_constraints.py` pins: paste the **actual** `pg_get_constraintdef` output after the first upgrade — do not hand-predict (PostgreSQL renders `IN` as `= ANY (ARRAY[…'::text])` and numeric literals as `(0)::numeric`).

## 3. Repository — `smartmatch_persistence/speaker_availability.py`

```python
class AvailabilitySource(StrEnum):          # C7: move to domain if T1 wants it
    SPEAKER = "speaker"; CONNECTOR = "connector"

class StaleSpeakerAvailabilityError(RuntimeError): ...   # T3 → 409 speaker_availability_stale

@dataclass(frozen=True, slots=True)
class StoredWindow:
    starts_on: date; ends_on: date
    created_source: AvailabilitySource; created_by_user_id: uuid.UUID; created_at: datetime

@dataclass(frozen=True, slots=True)
class StoredSpeakerAvailability:
    tenant_id: uuid.UUID; professional_id: uuid.UUID
    statement: AvailabilityStatement        # T1 type; unavailable ordered by (starts_on, ends_on)
    windows: tuple[StoredWindow, ...]       # same order; per-window source for §4.1's response
    version: int; updated_source: AvailabilitySource; updated_by_user_id: uuid.UUID
    created_at: datetime; updated_at: datetime

class SpeakerAvailabilityRepository:
    def get(self, session, *, tenant_id, professional_id) -> StoredSpeakerAvailability | None
    def get_many(self, session, *, tenant_id, professional_ids: Collection[uuid.UUID]
                 ) -> Mapping[uuid.UUID, StoredSpeakerAvailability]
    def upsert(self, session, *, tenant_id, professional_id, statement: AvailabilityStatement,
               source: AvailabilitySource, actor_user_id: uuid.UUID,
               expected_version: int | None, now: datetime | None = None
               ) -> StoredSpeakerAvailability
```

- **`get`**: `None` = no row = "said nothing" (`UNKNOWN`). A row with no windows is a real answer (`AVAILABLE`).
- **One statement per read, `get` and `get_many` alike.** The engine runs READ COMMITTED (`engine.py:233-240` sets no isolation level), so two queries can straddle a writer's commit and return fields at version *n* with windows at *n+1*. Both reads are one query:
  `SELECT a.*, w.starts_on, w.ends_on, w.created_source, w.created_by_user_id, w.created_at FROM speaker_availability a LEFT JOIN speaker_availability_window w ON w.tenant_id = a.tenant_id AND w.professional_id = a.professional_id WHERE a.tenant_id = :t AND a.professional_id = ANY(:ids) ORDER BY a.professional_id, w.starts_on, w.ends_on`.
  `LEFT JOIN` keeps a row with zero windows (all `w.*` NULL → `unavailable = ()`). The join also carries `w.tenant_id = a.tenant_id`. Grouped in Python by `professional_id`. `get` = `get_many` with one id.
- **`get_many`** (T4's pool read): absent key = no row. Empty input → `{}` with no query. No N+1.
- **`upsert`**, one caller transaction, never commits:
  1. `SELECT … FOR UPDATE` the row.
  2. `expected_version is None` means "I believe there is no row" (C1). Mismatch either way → `StaleSpeakerAvailabilityError`.
  3. No row: `INSERT … ON CONFLICT (tenant_id, professional_id) DO NOTHING RETURNING` at version 1; nothing returned (a concurrent first write won) → stale error, not `IntegrityError`.
  4. Row exists: `UPDATE … SET version = version + 1, updated_source, updated_by_user_id, updated_at, pause, capacity`.
  5. **Window replace, keyed by `(starts_on, ends_on)`**: delete stored ranges absent from `statement.unavailable`; insert new ranges with `created_source = source`, `created_by_user_id = actor_user_id`; keep unchanged ranges and their original provenance.
  6. Version bumps on every accepted call, even an identical one (matches `match_weight_settings.py:257`).
- **Does not validate.** Caller runs T1 `validate_availability_statement` first (limits, horizon, duplicates → 422). A duplicate range reaching the DB raises `IntegrityError` on `uq_speaker_availability_window_range` — a caller bug.
- Unknown or other-tenant `professional_id` → FK `IntegrityError`. T3 checks the profile's unit first and returns 404.
- Capacity crosses as `Decimal` (`sa.Numeric(5, 1)` default `asdecimal=True`).

## 4. TDD tests

Where: `tests/integration/`, marker `pytest.mark.integration`. Fixtures `engine`, `tenant_id` (`conftest.py:228`, `:393`) skip when no Postgres.
Upgrade/downgrade tests use `migration_harness.scratch_database` + `alembic` (`test_host_organization_migration.py` shape).
CI runs them: `.github/workflows/verify.yml:52` (postgres:16 service), `:107` `alembic upgrade head`, `:117` `pytest tests/ -m "not e2e"`.

### 4.1 `test_speaker_availability_migration.py`

1. `test_upgrade_from_0037_creates_both_tables_and_writes_no_row` (scratch, seeded speaker_profile survives).
2. `test_downgrade_drops_both_tables_and_keeps_speaker_profile` (scratch).
3. `test_upgrade_is_repeatable_after_a_downgrade` (scratch).
4. `test_capacity_rejects_zero` / `test_capacity_rejects_negative` / `test_capacity_rejects_720_1`.
5. `test_capacity_accepts_null_0_1_and_720` (permitted half; `NULL` = not stated).
6. `test_capacity_rounds_before_check` — `720.04` stored as `720.0`, `0.04` → `0.0` refused (pins numeric(5,1); C5).
7. `test_updated_source_rejects_unknown` / `_accepts_speaker_and_connector`.
8. `test_version_rejects_zero` / `test_version_defaults_to_one`.
9. `test_window_rejects_end_before_start` / `test_window_accepts_single_day`.
10. `test_window_rejects_span_367` / `test_window_accepts_span_366`.
11. `test_window_source_rejects_unknown` / `_accepts_both`.
12. `test_window_rejects_duplicate_range` / `test_window_accepts_overlapping_distinct_ranges`.
13. `test_availability_for_other_tenant_profile_is_refused` (profile in tenant B, row in tenant A).
14. `test_updated_by_from_other_tenant_is_refused`; `test_window_created_by_from_other_tenant_is_refused`.
15. `test_window_for_other_tenant_statement_is_refused`; `test_window_without_statement_is_refused`.
16. `test_deleting_speaker_profile_cascades_to_availability_and_windows`.
17. `test_deleting_statement_cascades_to_windows`.
18. `test_deleting_updating_user_account_is_restricted` (the statement's `updated_by`).
19. `test_deleting_window_creator_account_is_restricted` — the window's `created_by` is a **different** account from the statement's `updated_by`; deleting it is refused, so the window FK's RESTRICT is proven on its own.
20. `test_window_ends_index_exists` — `inspector.get_indexes("speaker_availability_window")` holds `ix_speaker_availability_window_ends` on exactly `(tenant_id, professional_id, ends_on)`. The drift test does not compare indexes.

Plus the 6 `test_check_constraints.py` entries pointing `BEHAVIOURAL_COVERAGE` at tests 4–11.

### 4.2 `test_speaker_availability_repository.py`

1. `test_get_returns_none_when_no_row`.
2. `test_first_upsert_with_none_creates_version_1`.
3. `test_first_upsert_with_version_raises_stale`.
4. `test_upsert_with_none_when_row_exists_raises_stale`.
5. `test_upsert_with_old_version_raises_stale_and_writes_nothing`.
6. `test_upsert_bumps_version_and_sets_provenance`.
7. `test_window_replace_keeps_unchanged_provenance_deletes_absent_inserts_new`.
8. `test_empty_windows_clears_all_windows_but_keeps_row` (stated, nothing blocked).
9. `test_capacity_round_trips_as_decimal`; `test_null_pause_and_capacity_round_trip`.
10. `test_get_many_returns_only_present_ids_in_one_query` (count via `before_cursor_execute`; `get` also issues exactly 1).
10b. `test_get_many_keeps_a_row_with_zero_windows` (LEFT JOIN, `unavailable == ()`).
11. `test_get_many_empty_input_issues_no_query`.
12. `test_get_many_never_returns_other_tenant_rows`.
13. `test_concurrent_first_writes_one_wins_other_stale` (two sessions).
14. `test_repository_never_commits` (rollback leaves no row).
15. `test_read_is_one_committed_state_under_concurrent_write` — regression for the two-query race. Row at v1 with windows A. An `after_cursor_execute` hook on the reader's connection, firing once after the reader's **first** statement, commits v2 (different pause, capacity, windows B) from a second session. Assert the result is entirely v1: fields, `version == 1` and windows A. A two-query read fails here (v1 fields with B windows). Repeat for `get`.

Run one file at a time: `$VENV/bin/python -m pytest tests/integration/test_speaker_availability_migration.py -q`.
A local skip (no Postgres) is not proof; CI is.

## 5. Commit milestones

1. `test: failing T2 migration and repository tests` — both new test files + `test_check_constraints.py` entries.
2. `feat(db): 0038 speaker_availability, window table and schema mirror` — migration, `schema.py`, `conftest.py`, 4 head pins.
3. `feat: speaker availability repository` — `speaker_availability.py`; repository file green.
4. `docs: 0038 head in README, supabase-setup and exercise-hosting` — `README.md:35-36`, `supabase-setup.md:162`, `exercise-hosting.md:706-716` (those lines only).

## 6. Contradictions and choices

| # | Issue | Options | Chosen |
|---|---|---|---|
| C1 | §3.1 says "the `matching_weights.py` pattern", whose `expected_version` is optional and `None` = blind write (`match_weight_settings.py:250`). Two writers (Speaker, Connector) make a blind write a lost update. | (a) `None` = "expect no row"; always checked. (b) copy blind-write. | **(a).** T3's GET returns `version: null` when `stated: false`; client echoes it. |
| C2 | §3.1 lists no `version` CHECK. | (a) add `ck_speaker_availability_version` (`>= 1`); (b) omit. | **(a)**, precedent `ck_match_weight_setting_version`. |
| C3 | §3.1 names neither the window CHECKs, the window FK to `user_account`, nor the index. | Names in §2. | As §2. |
| C4 | §3.1 "FK → `user_account`" reads as plain. | Composite only: plain fails `test_schema_matches_migration.py:225`. | Composite. |
| C5 | `numeric(5,1)` rounds before the CHECK: `720.04` passes, `0.04` fails. | T1 C3 rejects > 1 decimal at the domain; DB test pins the rounding. | Both. |
| C6 | §3 says "README revision count/head". Head is also pinned in 4 tests and `supabase-setup.md:162`. `exercise-hosting.md:706-712` asserts `0037` **is** head and fails after 0038; that file has uncommitted edits in the parent checkout. | (a) update it in T2; (b) leave to its owner. | **(a) — ruled by the dispatcher (Codex review round 1).** Lines 706-716 only. |
| C7 | T1's `AvailabilityStatement` has no per-window source; §4.1 response needs it. `AvailabilitySource` has no home. | Wrapper `StoredSpeakerAvailability` + enum in persistence; or enum in domain. | Persistence; move if T1 adds one. **Align with T1.** |
| C8 | §3.1 gives timestamps no default. | `server_default now()` (every table in `schema.py`) + repository passes `now`. | Both. |
| C9 | `schema.py:22-24` says FKs are left unnamed in the mirror; `speaker_profile` names its 0028 FKs. | Name in both / migration only. | Both; drift ignores FK names. |
| C10 | T6b-1 (`0039`) and T8a (`0040`) start day one; T8a does not depend on T2. | First to merge takes head + 1; others renumber `revision`, `down_revision`, 4 pins, docs. | Parent §11 row 5. |

---

**Next action (under two minutes):** create `tests/integration/test_speaker_availability_migration.py` with tests 4–5.
