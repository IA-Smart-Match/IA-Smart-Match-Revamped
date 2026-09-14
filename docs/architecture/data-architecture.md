# Data Architecture

**Stage 1 §8.** Commit `c72dced`.

---

## 1. Stores

| Store | Role | Status |
|---|---|---|
| **PostgreSQL 16** | The *only* store. Business data **and** coordination state: job lifecycle, transactional outbox, idempotency, concurrency leases, rate-limit counters, budgets, SSE cursors | Operational |
| Redis, Pub/Sub, BigQuery | Deferred with objective adoption triggers | Absent by decision (`smartmatch_persistence/__init__.py`) |
| GCS buckets | Evidence + artifacts | Placeholder Terraform only |

**INFERRED — this is a correct decision for pilot scale, and it is the decision
that most constrains scale.** Putting the queue, the rate limiter and the lease
table in the same database as the business data means one transaction can span
"record the intent" and "enqueue the work" — which is exactly what makes the
transactional outbox (ADR-0005) sound, and what makes the whole system
crash-safe without distributed-transaction machinery. The price is that
`rate_limit_counter` (fan-in 21) and `outbox_record` are write-hot rows in the
same instance as everything else. See §7.

---

## 2. Shape (OBSERVED, `schema.py`, 2,691 lines)

| Metric | Count |
|---|---:|
| Tables | **43** |
| `nullable=False` columns | 283 |
| `CheckConstraint` | **119** |
| `UniqueConstraint` | 49 |
| `ForeignKey` | 81 |
| — `ondelete="RESTRICT"` | **68** |
| — `ondelete="CASCADE"` | 13 |
| — `ondelete="SET NULL"` | **0** |
| `JSONB` columns | 8 |
| `ltree` columns | 3 |
| Indexes declared in `schema.py` | **0** (by design — see §5) |
| Indexes created in migrations | 33 |
| Alembic revisions | 33 (`0001` → `0033`), linear |

**OBSERVED — the constraint density is the story.** 119 check constraints across
43 tables, with 68 of 81 foreign keys set to `RESTRICT`, is a schema that
refuses bad states at the database rather than trusting application code. Zero
`SET NULL` means no relationship is silently severed. Two dedicated integration
suites test this directly: `test_check_constraints.py` (43 tests) and
`test_event_schema_constraints.py` (54 tests).

**This is the strongest data-integrity posture the audit found in any layer.**

---

## 3. Ownership map (INFERRED — see §8 for why it is inferred)

| Context | Tables |
|---|---|
| **Identity & Access** | `tenant`, `org_unit`, `user_account`, `membership`, `resource_grant`, `pilot_credential`, `pilot_session`, `pilot_login_attempt` |
| **Work substrate** | `job`, `job_event`, `outbox_record`, `idempotency_record`, `redrive_record`, `concurrency_lease`, `rate_limit_counter` |
| **Budget** | `tenant_budget`, `spend_ceiling_bucket`, `spend_reservation` |
| **Event catalog** | `event`, `event_tag`, `event_registration`, `discovery_review_item` |
| **Ingestion & review** | `import_batch`, `review_item`, `pipeline_record` |
| **Matching** | `match_run`, `match_weight_setting`, `match_weight_setting_revision` |
| **Speaker relationship** | `speaker_profile`, `professional_unit_relationship`, `speaker_request_classification`, `contact_channel`, `contact_channel_transition` |
| **Outreach** | `outreach_draft`, `outreach_send`, `delivery_event`, `suppression_record`, `cba_invitation_batch`, `cba_invitation` |
| **Engagement & rewards** | `attendance_record`, `point_ledger_entry`, `reward_item`, `redemption`, `student_speaker_feedback` |

---

## 4. Tenancy and isolation

**OBSERVED.** Isolation is enforced by **composite tenant-safe keys**, not by a
session variable or row-level security. `tests/integration/test_schema_matches_migration.py`
states the design directly: *"the composite tenant-safe keys in v1.1 §2.2 are
the point of the schema, and reflection would not reliably preserve them."*

Authorization scope is an `ltree` path with two GiST indexes
(`ix_org_unit_path_gist`, `ix_membership_path_gist`) — so "does this membership
cover this unit's subtree" is one indexed operator, not an application-side
tree walk.

**OBSERVED.** ADR-0008 (*globally unique external subject*) plus migration
`0007` (*drop redundant tenant subject*) record a deliberate change: an external
subject identifier is unique globally, not per-tenant. `scan_forbidden.py`'s
allowlist notes an ADR *"names the archived pattern to argue why a tenant-scoped
lookup revives it"* — i.e. tenant-scoping the subject lookup was identified as a
security regression and is now scanned for.

Verified by `tests/integration/test_tenant_isolation.py` and
`tests/authz/test_policy_matrix.py` (41 tests).

---

## 5. Indexes — the one real gap in an otherwise strong schema

**OBSERVED.** `schema.py` declares **zero** indexes. All 33 live in Alembic
migrations. And `test_schema_matches_migration.py` explicitly does **not**
compare them:

> *"Index sets are not compared because `schema.py` declares no indexes on
> purpose."*

**Consequence.** The parity guard that catches a drifted column, constraint or
foreign key is blind to indexes. Concretely:

- Dropping `ix_outbox_claimable` in a migration passes every gate in
  `verify.yml`. The dispatcher's `SKIP LOCKED` claim would degrade to a
  sequential scan over the outbox on every pass — a silent, progressive
  production slowdown with a green CI.
- A reader of `schema.py` — the natural place to look — sees no indexes at all
  and cannot tell whether a query is supported.

**Assessment: compounding architectural debt.** Not a correctness risk today
(the indexes exist and are well chosen — `ix_outbox_claimable`,
`ix_job_running_lease`, `ix_job_tenant_status`, `ix_rate_limit_window_start`,
two GiST path indexes, and `ix_speaker_profile_unit_folded_name` for
case-folded name lookup all match the access patterns the audit traced). But
the guard that keeps everything *else* honest stops at the index boundary, and
indexes are precisely where silent regressions live.

**RECOMMENDATION.** Declare indexes in `schema.py` alongside their tables and
extend the parity test to compare index sets by name. This puts them where a
reader looks and under the guard that already exists.
→ `risk-register.md` R-12, Stage 2 increment **M7**.

---

## 6. Derived data and source-of-truth rules

**OBSERVED — well handled.** The audit specifically looked for derived values
stored without a stated source of truth. The three main derived quantities all
have explicit rules:

| Derived value | Source of truth | Rule |
|---|---|---|
| Student point balance | `point_ledger_entry` (append-only) | `rewards.fold_balance(entries)` — computed, never stored. Migration `0015` *removed* unauthorized ledger reversal |
| Match score | the `match_run` snapshot | Reproducible from `weights_fingerprint` + `inputs_fingerprint` + `MatchRunPins`. ADR-0011: a number carries provenance or is `null` |
| Funnel metrics | `pipeline_record` + `attendance_record` | ADR-0013: attendance is the **only** input to points. The funnel's writer (`routers/pipeline.py`) and reader (`routers/metrics.py`) are deliberately co-located under one capability |

**OBSERVED.** `attendance_record` is cited by the funnel and by feedback
eligibility and by the points ledger — three consumers, one writer
(`routers/attendance.py`, added when OQ-102 closed on 2026-09-07). `main.py`'s
router table argues this explicitly, and `student_events.py` deliberately writes
`event_registration` and never `attendance_record`. **Registration is not
attendance** is a real, enforced invariant.

---

## 7. Scaling hotspots (INFERRED)

| Table | Pattern | Assessment |
|---|---|---|
| `rate_limit_counter` | Written on **every** request through 20 routers; fan-in 21 | Fixed-window in PostgreSQL by decision (ADR-0006). Correct at pilot scale, and the first table to become a write bottleneck. The ADR exists, so this is a known trade, not an oversight |
| `outbox_record` | Written per command; claimed by `SKIP LOCKED` on every dispatch pass | Well-indexed (`ix_outbox_claimable`). Health depends entirely on that index (§5) |
| `job_event` | Append-only, per job, streamed by `GET /v1/jobs/{id}/events` | **No retention policy found.** Grows without bound |
| `point_ledger_entry` | Append-only, balance folded on read | Correct design; `fold_balance` cost grows linearly per student. Fine for a pilot; a snapshot-plus-delta scheme is the eventual answer, and should **not** be built yet |
| `zcta_centroids` | 1,894 lines of in-process Python data | Not a database concern; loaded per process. Regenerable via `make zcta-centroids`, with a CI staleness check |

**UNKNOWN — retention.** No retention or archival policy was found for
`job_event`, `delivery_event`, `contact_channel_transition`,
`pilot_login_attempt`, or `match_run` snapshots. All are append-only. At pilot
volume this does not matter; it is listed so the absence is a recorded decision
rather than an oversight. → `risk-register.md` R-13.

---

## 8. Ownership ambiguity — the structural finding

**OBSERVED.** All 43 tables are defined in one 2,691-line module. Nothing in
the repository states which context or service owns which table.

The consequence is concrete and already visible:

- `routers/match_runs.py` both submits a command **and** writes rows directly
  (`dependency-analysis.md` §4). `worker/handlers.py:handle_match_run_create`
  also writes match-run rows. Two writers, no declared owner.
- `attendance_record` has one writer today, but nothing prevents a second, and
  ADR-0013's invariant (attendance is the only input to points) depends on
  that single writer.
- Splitting `schema.py` is currently impossible to do well, because there is no
  ownership statement to split *along*.

**RECOMMENDATION.** Declare table ownership as data — a table-to-context map,
checked by a test — before any structural change to `schema.py`. Ownership is
the prerequisite; the file split is the optional consequence.
→ Stage 2 **AP-03**.

---

## 9. Migration practice

**OBSERVED — strong.**

| Property | Evidence |
|---|---|
| Linear chain, no branching | `0001` → `0033`, each `down_revision` naming its predecessor |
| One transaction per migration | **ADR-0009**, and a header comment in the versions: *"this revision commits — not until the whole `alembic upgrade` run does"* |
| Applies from empty on every PR | `verify.yml`: `cd db && alembic upgrade head` |
| Code/database parity guarded | `test_schema_matches_migration.py` — whole-schema, symmetric, both directions (its docstring records that an earlier version checked a hard-coded list of five tables and therefore passed anything not on the list) |
| Data migrations tested | `test_pipeline_provenance_migration.py`, `test_match_run_scoring_mode_migration.py`, `test_event_filed_by_migration.py`, plus `migration_harness.py` |
| Reversals recorded | `0014` added a ledger reversal target; `0015` removed unauthorized reversal — the history is legible as a decision, not a patch |

**UNKNOWN — rollback.** Downgrade paths were not audited, and no evidence was
found that any `downgrade()` is exercised. Migrations are forward-tested only.
→ `risk-register.md` R-14.
