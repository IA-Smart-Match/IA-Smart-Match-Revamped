"""Every CHECK constraint is exercised by the write it exists to refuse.

`test_schema_matches_migration.py::test_check_constraints_match` compares CHECK
constraints between the schema mirror and the database **by name only**.
PostgreSQL rewrites the expression on the way in, so the definitions are not
comparable as text, and reflection does not report the columns. That test
therefore catches a constraint added, dropped, or renamed on one side — and
nothing about what the constraint actually says.

The gap that leaves is concrete: a constraint re-added under the same name with
an **inverted** expression keeps its name and stays green. This file closes it,
for all eight, by attempting the forbidden write and asserting the database
refuses it — and, just as importantly, by attempting the *permitted* write and
asserting it succeeds. The second half is what catches inversion: an inverted
`ck_budget_non_negative` reading `spent < 0` would still refuse `spent = -1` for
the wrong reason, and would refuse `spent = 0`, which is where it fails.

**The `NOT VALID` half of the gap needs a different instrument, and this is the
correction to the record.** `docs/plans/remaining-foundation-r1-work.md` (F10)
and the docstring of `test_check_constraint_names_match` both say a constraint
re-added as `NOT VALID` "stays green". That is true of the name-only test and it
is *equally true of a write test*: verified against PostgreSQL 16.15, a
`NOT VALID` CHECK rejects new inserts and updates exactly as a validated one
does. What `NOT VALID` skips is the initial scan of rows already present — so
the constraint is enforced from that point on, and has simply never been checked
against the existing data. No attempted write can distinguish the two. So
`test_every_check_constraint_is_validated` below reads
`pg_constraint.convalidated` directly, which is the only thing that can. Both
documents are corrected in the same commit as this file.

**The expression itself is pinned too**, for the class of weakening no write can
reach: a vocabulary quietly widened, or a threshold moved. See
`CHECK_CONSTRAINT_DEFINITIONS`.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Every CHECK constraint in the schema, keyed by ``(table, name)`` and mapped to
#: the exact expression PostgreSQL renders for it.
#:
#: **Keyed by table as well as name, because a name is not an identity.**
#: PostgreSQL permits the same constraint name on two different tables —
#: verified by adding a second ``ck_outbox_status`` to ``job``, which both
#: meta-tests below missed entirely while they compared bare names. A ninth
#: constraint reusing an existing name was invisible.
#:
#: **The expression is pinned, and that is what closes the weakening class.**
#: Attempted writes prove a constraint refuses the values a test happens to try.
#: They cannot prove it refuses the ones it does not: adding ``'audit'`` to
#: ``ck_resource_grant_effect``, or ``'cancelled'`` to ``ck_outbox_status``, or
#: relaxing either numeric clause to ``>= -0.5``, passes every behavioural test
#: in this file. Comparing the rendered definition catches all of them at once.
#:
#: The rendering is PostgreSQL's, not ours — ``status IN (...)`` comes back as
#: ``status = ANY (ARRAY[...])``. That makes this a poor tool for comparing the
#: schema mirror against the database, which is why
#: ``test_schema_matches_migration.py`` deliberately does not do it. Here both
#: sides are the *database*, so the rendering is stable and the comparison is
#: exact. It is pinned against PostgreSQL 16; a major-version upgrade that
#: changed the normalisation would fail this test, and reviewing that diff on
#: purpose is the intended behaviour rather than a cost.
CHECK_CONSTRAINT_DEFINITIONS = {
    ("job", "ck_job_status"): (
        "CHECK ((status = ANY (ARRAY['queued'::text, 'dispatched'::text, "
        "'running'::text, 'succeeded'::text, 'partial'::text, "
        "'failed_provider'::text, 'failed_budget'::text, 'failed_policy'::text, "
        "'cancelled'::text, 'timed_out'::text, 'redrive_pending'::text, "
        "'abandoned'::text])))"
    ),
    ("membership", "ck_membership_valid_window"): (
        "CHECK (((valid_until IS NULL) OR (valid_from IS NULL) OR (valid_until > valid_from)))"
    ),
    ("outbox_record", "ck_outbox_status"): (
        "CHECK ((status = ANY (ARRAY['pending'::text, 'leased'::text, "
        "'dispatched'::text, 'failed'::text])))"
    ),
    ("rate_limit_counter", "ck_rate_limit_count_non_negative"): "CHECK ((count >= 0))",
    ("redrive_record", "ck_redrive_authorship_complete"): (
        "CHECK (((redriven_at IS NULL) = (redriven_by IS NULL)))"
    ),
    ("resource_grant", "ck_resource_grant_effect"): (
        "CHECK ((effect = ANY (ARRAY['allow'::text, 'deny'::text])))"
    ),
    ("tenant_budget", "ck_budget_ceiling_non_negative"): "CHECK ((ceiling >= (0)::numeric))",
    ("tenant_budget", "ck_budget_non_negative"): (
        "CHECK (((spent >= (0)::numeric) AND (reserved >= (0)::numeric)))"
    ),
}

#: Where each constraint's forbidden and permitted writes are attempted. Six are
#: in this file. The other two are covered, thoroughly, by modules that predate
#: it, and are recorded here rather than duplicated — a reader asking "is
#: ``ck_job_status`` exercised?" gets an answer without grepping.
BEHAVIOURAL_COVERAGE = {
    ("job", "ck_job_status"): (
        "test_job_states_match_domain.py — reads the admitted set out of the "
        "catalogue and compares it to JobState both directions, and inserts one "
        "job per legal state; test_tenant_isolation.py::"
        "test_job_status_check_rejects_an_unknown_state for the refusal"
    ),
    ("tenant_budget", "ck_budget_ceiling_non_negative"): "this file",
    ("membership", "ck_membership_valid_window"): "this file",
    ("outbox_record", "ck_outbox_status"): "this file",
    ("rate_limit_counter", "ck_rate_limit_count_non_negative"): "this file",
    ("redrive_record", "ck_redrive_authorship_complete"): "this file",
    ("resource_grant", "ck_resource_grant_effect"): "this file",
    ("tenant_budget", "ck_budget_non_negative"): "this file",
}


# ---------------------------------------------------------------------------
# Row builders. Each returns the id of a row the constraint under test can hang
# off, so the test body contains only the value that is actually in question.
# ---------------------------------------------------------------------------


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"ck-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_job(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status) "
            "VALUES (:id, :tenant_id, 'noop', 'queued')"
        ),
        {"id": job_id, "tenant_id": tenant_id},
    )
    return job_id


def _insert_membership(conn, tenant_id, user_id, valid_from, valid_until) -> None:
    conn.execute(
        text(
            "INSERT INTO membership "
            "(id, tenant_id, user_id, granted_path, role, valid_from, valid_until) "
            "VALUES (:id, :tenant_id, :user_id, 'root'::ltree, 'coordinator', "
            ":valid_from, :valid_until)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "valid_from": valid_from,
            "valid_until": valid_until,
        },
    )


def _insert_grant(conn, tenant_id, user_id, effect: str) -> None:
    conn.execute(
        text(
            "INSERT INTO resource_grant "
            "(id, tenant_id, user_id, resource_type, resource_id, effect) "
            "VALUES (:id, :tenant_id, :user_id, 'job', :resource_id, :effect)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "resource_id": uuid.uuid4(),
            "effect": effect,
        },
    )


def _insert_outbox(conn, tenant_id, job_id, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO outbox_record (id, tenant_id, job_id, task_name, status) "
            "VALUES (:id, :tenant_id, :job_id, :task_name, :status)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "job_id": job_id,
            "task_name": f"task-{uuid.uuid4().hex[:12]}",
            "status": status,
        },
    )


def _insert_redrive(conn, tenant_id, job_id, redriven_at, redriven_by) -> None:
    conn.execute(
        text(
            "INSERT INTO redrive_record "
            "(id, tenant_id, job_id, attempt_history, redriven_at, redriven_by) "
            "VALUES (:id, :tenant_id, :job_id, '[]'::jsonb, :redriven_at, :redriven_by)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "job_id": job_id,
            "redriven_at": redriven_at,
            "redriven_by": redriven_by,
        },
    )


# ---------------------------------------------------------------------------
# ck_membership_valid_window — (until IS NULL) OR (from IS NULL) OR (until > from)
# ---------------------------------------------------------------------------

_EARLY = "2026-01-01T00:00:00+00:00"
_LATE = "2026-06-01T00:00:00+00:00"


def test_membership_window_rejects_an_end_before_its_start(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_membership_valid_window"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, _LATE, _EARLY)


def test_membership_window_rejects_a_zero_length_window(engine: Engine, tenant_id) -> None:
    """The constraint is `>`, not `>=`.

    A membership valid from an instant until that same instant grants nothing,
    and a constraint written `>=` would let it through. Nothing else in this
    file distinguishes the two operators.
    """
    with pytest.raises(IntegrityError, match="ck_membership_valid_window"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, _EARLY, _EARLY)


@pytest.mark.parametrize(
    ("valid_from", "valid_until", "description"),
    [
        (_EARLY, _LATE, "an ordinary bounded window"),
        (None, _LATE, "open at the start"),
        (_EARLY, None, "open at the end"),
        (None, None, "unbounded"),
    ],
)
def test_membership_window_accepts_every_legitimate_shape(
    engine: Engine, tenant_id, valid_from, valid_until, description: str
) -> None:
    """The inversion check: an inverted constraint refuses these.

    The two `NULL` escapes are part of the expression, so a constraint rewritten
    without them would pass the rejection tests above and fail here.
    """
    with engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, valid_from, valid_until)


# ---------------------------------------------------------------------------
# ck_resource_grant_effect — effect IN ('allow', 'deny')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("effect", ["maybe", "ALLOW", "Deny", "", "allow "])
def test_resource_grant_rejects_an_effect_outside_the_vocabulary(
    engine: Engine, tenant_id, effect: str
) -> None:
    """Authorization reads this column; a value it does not know is not safe.

    The case variants and the trailing space are deliberate. A constraint
    relaxed to `lower(trim(effect)) IN (...)` would accept them, and the
    authorization code compares the literal, so it would then read a grant it
    does not recognise as neither allow nor deny.
    """
    with pytest.raises(IntegrityError, match="ck_resource_grant_effect"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_grant(conn, tenant_id, user, effect)


@pytest.mark.parametrize("effect", ["allow", "deny"])
def test_resource_grant_accepts_both_effects(engine: Engine, tenant_id, effect: str) -> None:
    """Both halves of the vocabulary, so a narrowed list fails here.

    `deny` in particular: a constraint reduced to `effect = 'allow'` would pass
    every rejection test above.
    """
    with engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_grant(conn, tenant_id, user, effect)


# ---------------------------------------------------------------------------
# ck_outbox_status — status IN ('pending', 'leased', 'dispatched', 'failed')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["claimed", "PENDING", "", "done"])
def test_outbox_rejects_a_status_outside_the_lifecycle(
    engine: Engine, tenant_id, status: str
) -> None:
    """`claimed` is the interesting one — it is the word the code does not use.

    The dispatcher's claim sets `leased`. A status the claim query never selects
    for is a row no dispatcher will ever pick up, and the constraint is what
    stops one being written.
    """
    with pytest.raises(IntegrityError, match="ck_outbox_status"), engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_outbox(conn, tenant_id, job, status)


@pytest.mark.parametrize("status", ["pending", "leased", "dispatched", "failed"])
def test_outbox_accepts_every_lifecycle_status(engine: Engine, tenant_id, status: str) -> None:
    """All four, because the dispatcher writes all four.

    ADR-0005 makes `pending → leased → dispatched | failed` the outbox's whole
    lifecycle. A constraint that lost one of them would break the dispatcher at
    the transition that writes it, and pass every rejection test above.
    """
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_outbox(conn, tenant_id, job, status)


# ---------------------------------------------------------------------------
# ck_redrive_authorship_complete — (redriven_at IS NULL) = (redriven_by IS NULL)
# ---------------------------------------------------------------------------

_ACTOR = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def test_redrive_rejects_a_time_with_no_author(engine: Engine, tenant_id) -> None:
    """A re-drive that happened, with nobody accountable for it."""
    with (
        pytest.raises(IntegrityError, match="ck_redrive_authorship_complete"),
        engine.begin() as conn,
    ):
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, _LATE, None)


def test_redrive_rejects_an_author_with_no_time(engine: Engine, tenant_id) -> None:
    """The other half. A constraint written as a one-way implication —
    `redriven_at IS NULL OR redriven_by IS NOT NULL` — passes the test above and
    fails here, which is the whole reason both directions are written out."""
    with (
        pytest.raises(IntegrityError, match="ck_redrive_authorship_complete"),
        engine.begin() as conn,
    ):
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, None, _ACTOR)


def test_redrive_accepts_a_parked_row_that_has_not_been_redriven(engine: Engine, tenant_id) -> None:
    """Both `NULL` — the state every redrive_record is written in first."""
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, None, None)


def test_redrive_accepts_a_complete_authorship_pair(engine: Engine, tenant_id) -> None:
    """Both set — the state a re-drive moves it to."""
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, _LATE, _ACTOR)


# ---------------------------------------------------------------------------
# ck_budget_non_negative — spent >= 0 AND reserved >= 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["spent", "reserved"])
@pytest.mark.parametrize("amount", ["-1", "-0.0001"])
def test_budget_rejects_a_negative_amount(
    engine: Engine, tenant_id, column: str, amount: str
) -> None:
    """Both columns, because the constraint is a conjunction of two clauses.

    A constraint that lost the `reserved >= 0` half would still refuse a
    negative `spent`. Parametrising over the column is what makes each clause
    independently load-bearing.

    `-0.0001` is the smallest negative `numeric(12,4)` can hold. Sampling only
    `-1` would leave a clause relaxed to `>= -0.5` passing.
    """
    with pytest.raises(IntegrityError, match="ck_budget_non_negative"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, "
                f"{column}) VALUES (:tenant_id, 'email', 100, -1)"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_accepts_zero_and_positive_amounts(engine: Engine, tenant_id) -> None:
    """Zero is the boundary, and an inverted constraint refuses it."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, spent, reserved) "
                "VALUES (:tenant_id, 'email', 100, 0, 0)"
            ),
            {"tenant_id": tenant_id},
        )
        conn.execute(
            text(
                "UPDATE tenant_budget SET spent = 10, reserved = 5 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_rejects_a_negative_amount_on_update(engine: Engine, tenant_id) -> None:
    """A refund that overshoots is the realistic way this goes negative.

    Every other test here inserts. The reservation path *updates* — `spent =
    spent - x` on release — and a CHECK declared on a column is enforced on both,
    so this pins that the release path cannot drive the row below zero either.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, spent) "
                "VALUES (:tenant_id, 'email', 100, 5)"
            ),
            {"tenant_id": tenant_id},
        )

    with pytest.raises(IntegrityError, match="ck_budget_non_negative"), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE tenant_budget SET spent = spent - 10 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


# ---------------------------------------------------------------------------
# ck_budget_ceiling_non_negative — ceiling >= 0
# ---------------------------------------------------------------------------
#
# `test_tenant_isolation.py::test_budget_ceiling_cannot_go_negative` already
# refuses a ceiling of -5. That is a rejection test and nothing else: it leaves
# the permitted side unproven, so an inverted constraint passes it, and it
# samples one value a long way from the boundary, so a constraint relaxed to
# `ceiling >= -1` passes it too. These close both gaps.


@pytest.mark.parametrize("ceiling", ["-5", "-1", "-0.0001"])
def test_budget_ceiling_rejects_any_negative_value(engine: Engine, tenant_id, ceiling: str) -> None:
    """Including the value just below the boundary.

    `-0.0001` is the smallest negative the column's `numeric(12,4)` scale can
    represent. Sampling only `-5` leaves every relaxation between the boundary
    and that value undetected.
    """
    with (
        pytest.raises(IntegrityError, match="ck_budget_ceiling_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                f"VALUES (:tenant_id, 'email', {ceiling})"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_ceiling_accepts_zero(engine: Engine, tenant_id) -> None:
    """Zero is the boundary, and an inverted constraint refuses it.

    A ceiling of zero is also meaningful rather than degenerate: it is how a
    provider is switched off without deleting the row.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                "VALUES (:tenant_id, 'email', 0)"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_ceiling_rejects_going_negative_on_update(engine: Engine, tenant_id) -> None:
    """Lowering a ceiling is an UPDATE, which is how this would really happen."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                "VALUES (:tenant_id, 'email', 10)"
            ),
            {"tenant_id": tenant_id},
        )

    with (
        pytest.raises(IntegrityError, match="ck_budget_ceiling_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "UPDATE tenant_budget SET ceiling = ceiling - 20 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


# ---------------------------------------------------------------------------
# ck_rate_limit_count_non_negative — count >= 0
# ---------------------------------------------------------------------------


def _insert_counter(conn, tenant_id, count: int) -> None:
    conn.execute(
        text(
            "INSERT INTO rate_limit_counter "
            "(tenant_id, subject, operation, window_start, count) "
            "VALUES (:tenant_id, :subject, 'redrive', :window_start, :count)"
        ),
        {
            "tenant_id": tenant_id,
            "subject": unique_subject(f"ck-{uuid.uuid4().hex[:8]}"),
            "window_start": _EARLY,
            "count": count,
        },
    )


def test_rate_limit_count_rejects_a_negative_count(engine: Engine, tenant_id) -> None:
    """A negative counter is quota the caller has not spent — S-008's shape.

    The limiter increments; nothing decrements. A count below zero would mean
    the window grants more requests than the limit allows, which is the failure
    the limiter exists to prevent.
    """
    with (
        pytest.raises(IntegrityError, match="ck_rate_limit_count_non_negative"),
        engine.begin() as conn,
    ):
        _insert_counter(conn, tenant_id, -1)


def test_rate_limit_count_accepts_zero_and_above(engine: Engine, tenant_id) -> None:
    """Zero is the value every window starts at, so an inverted check breaks the
    limiter on its first write rather than on some edge case."""
    with engine.begin() as conn:
        _insert_counter(conn, tenant_id, 0)
        _insert_counter(conn, tenant_id, 1)


def test_rate_limit_count_rejects_going_negative_on_update(engine: Engine, tenant_id) -> None:
    """The decrement no code performs today, refused by the database anyway."""
    with engine.begin() as conn:
        _insert_counter(conn, tenant_id, 1)

    with (
        pytest.raises(IntegrityError, match="ck_rate_limit_count_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE rate_limit_counter SET count = count - 5 WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


# ---------------------------------------------------------------------------
# The catalogue, for the two things no attempted write can reach
# ---------------------------------------------------------------------------


def _live_check_constraints(engine: Engine) -> dict[tuple[str, str], tuple[str, bool]]:
    """Every CHECK in `public`, keyed by `(table, name)`.

    Keyed by both because PostgreSQL allows one name on two tables, and a
    dictionary keyed on the name alone silently keeps whichever row came last.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.relname, c.conname, pg_get_constraintdef(c.oid), c.convalidated "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE c.contype = 'c' AND n.nspname = 'public'"
            )
        ).all()
    found: dict[tuple[str, str], tuple[str, bool]] = {}
    for table, name, definition, validated in rows:
        key = (table, name)
        assert key not in found, f"{table}.{name} is defined twice, which should be impossible"
        found[key] = (definition, validated)
    return found


def test_every_check_constraint_is_validated(engine: Engine) -> None:
    """`NOT VALID` is invisible to every attempted write in this file.

    Verified against PostgreSQL 16.15: a CHECK added `NOT VALID` rejects new
    inserts and updates identically to a validated one. What `NOT VALID` skips
    is the initial scan of rows already in the table — so the constraint is
    enforced from that moment on, and simply **was never checked** against the
    existing data. That is weaker than saying the old rows violate it; they may
    or may not, and nobody has looked. Either way the schema is asserting
    something it has not established, which is what this test refuses.

    No write can tell the difference. `pg_constraint.convalidated` is the only
    thing that can, which is why this reads the catalogue instead of attempting
    anything.
    """
    found = _live_check_constraints(engine)

    missing = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - set(found))
    assert not missing, f"these CHECK constraints are not in the database at all: {missing}"

    unvalidated = sorted(key for key, (_, validated) in found.items() if not validated)
    assert not unvalidated, (
        "these CHECK constraints are NOT VALID, so they have never been checked "
        f"against the rows already in their table: {unvalidated}"
    )


@pytest.mark.parametrize("key", sorted(CHECK_CONSTRAINT_DEFINITIONS))
def test_the_constraint_expression_is_exactly_as_declared(
    engine: Engine, key: tuple[str, str]
) -> None:
    """The expression itself, which no attempted write can pin.

    A write test proves a constraint refuses the values it tried. It says
    nothing about the values it did not: `ck_resource_grant_effect` widened to
    admit `'audit'`, `ck_outbox_status` widened to admit `'cancelled'`, or
    either numeric clause relaxed to `>= -0.5`, passes every behavioural test in
    this file. Enumerating the counterexamples is hopeless — the space is every
    string and every number. Comparing the rendered definition closes the whole
    class in one assertion.

    This does not replace the behavioural tests. A definition that reads
    correctly and is not enforced — `NOT VALID`, or a constraint on a column the
    writes do not touch — passes here and fails there. The two are load-bearing
    in different directions.
    """
    found = _live_check_constraints(engine)
    assert key in found, f"{key[0]}.{key[1]} is not in the database"
    definition, _ = found[key]
    assert definition == CHECK_CONSTRAINT_DEFINITIONS[key], (
        f"{key[0]}.{key[1]}'s expression has changed.\n"
        f"  expected: {CHECK_CONSTRAINT_DEFINITIONS[key]}\n"
        f"  actual:   {definition}"
    )


def test_this_file_covers_every_check_constraint_in_the_schema(engine: Engine) -> None:
    """A new CHECK constraint added without a behavioural test fails here.

    Without this, F10's coverage is a claim about a moment rather than a
    property of the schema: the eight constraints that existed when it was
    written stay covered, and the ninth arrives untested.

    **Every CHECK in `public` counts, not every CHECK named `ck_*`.** The first
    version filtered on `conname LIKE 'ck\\_%'`, which made it blind to exactly
    the constraint most likely to be added by someone unfamiliar with the
    convention. Verified: one named `chk_probe_wrong_prefix`, and an unnamed one
    PostgreSQL auto-named `job_command_type_check`, both passed. Dropping the
    filter enforces the naming convention here too.
    """
    actual = set(_live_check_constraints(engine))

    uncovered = sorted(actual - set(CHECK_CONSTRAINT_DEFINITIONS))
    assert not uncovered, (
        "these CHECK constraints are not declared in "
        f"tests/integration/test_check_constraints.py: {uncovered}"
    )

    stale = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - actual)
    assert not stale, f"this file declares CHECK constraints that no longer exist: {stale}"


def test_every_declared_constraint_says_where_it_is_exercised(engine: Engine) -> None:
    """Declaring a constraint's expression is not the same as testing its behaviour.

    `CHECK_CONSTRAINT_DEFINITIONS` pins what a constraint *says*. It would be
    satisfied by a constraint nothing ever writes against. `BEHAVIOURAL_COVERAGE`
    is the second half — where the forbidden and permitted writes for each one
    actually live — and this keeps the two lists in step, so a constraint cannot
    be added to the first and quietly left out of the second.
    """
    undocumented = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - set(BEHAVIOURAL_COVERAGE))
    assert not undocumented, (
        f"these constraints have a pinned expression but no record of where "
        f"their behaviour is exercised: {undocumented}"
    )
    orphaned = sorted(set(BEHAVIOURAL_COVERAGE) - set(CHECK_CONSTRAINT_DEFINITIONS))
    assert not orphaned, f"BEHAVIOURAL_COVERAGE names constraints that are not declared: {orphaned}"
