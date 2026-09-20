"""The engine's `hide_parameters` switch, proved against a real PostgreSQL.

The unit suite proves the flag reaches `create_engine`. That is not the claim
that matters. The claim that matters is what an operator reads after a write
fails, and only a database can produce it: a driver error, wrapped by
SQLAlchemy, rendered to text.

So this module makes a statement fail with a value bound into it and reads the
result three ways — the exception's text, the `sqlalchemy.engine` log, and the
exception's class — with the flag on, and then once more with it off. The last
one is not redundant. Without it, "the value is absent" could pass for the
entirely wrong reason: a sentinel the failing statement never bound at all.

**And it pins what the flag does not cover.** SQLAlchemy can only suppress its
own rendering. PostgreSQL writes its own `DETAIL:` line, which for a CHECK or
NOT NULL violation is `Failing row contains (…)` — the whole row, values and
all — and that text arrives inside the driver's exception, below the layer this
flag operates on. `test_the_servers_own_detail_line_is_not_covered` states that
in an assertion so it is discovered here rather than in a log. It is the reason
the per-repository scrubbers in `smartmatch_persistence.exercise` stay: they
never render the driver's exception at all, which is the only complete answer.

Everything here happens in a table this module creates and drops. It asserts
nothing about the product schema, needs no migration, and names no product
column.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from smartmatch_persistence.engine import create_db_engine
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

_HIDE_PARAMETERS_VAR = "SMARTMATCH_DB_HIDE_PARAMETERS"

#: The value bound into the failing statement, and the thing whose presence or
#: absence in rendered text is the whole test. A neutral string on purpose: no
#: withheld column, no personal datum, nothing a failing run could print that
#: anyone would mind reading. It is long and unique so a substring search for it
#: cannot match by accident.
_SENTINEL = f"sentinel-value-{uuid.uuid4().hex}"

#: SQLAlchemy's replacement text. Asserted on so that "no sentinel" is backed by
#: a positive statement about *why* it is missing.
_SUPPRESSION_NOTICE = "hide_parameters=True"

_TABLE_NAME = f"hide_parameters_probe_{uuid.uuid4().hex[:12]}"
_PRIMARY_KEY_NAME = f"pk_{_TABLE_NAME}"
_CHECK_NAME = f"ck_{_TABLE_NAME}_label_is_short"

#: Two ways to refuse a row, because they leak differently.
#:
#: The primary key refusal is the ordinary shape of a failed write — a second
#: click, a replayed job, a re-run import — and PostgreSQL's ``DETAIL`` for it
#: names only the key (``Key (id)=(1) already exists``). Everything else the
#: statement bound is visible *only* through SQLAlchemy's rendering, which is
#: exactly what this flag governs.
#:
#: The CHECK refusal is the shape whose ``DETAIL`` dumps the whole failing row,
#: and it is here to pin that limitation rather than to hide from it.
_PROBE = sa.Table(
    _TABLE_NAME,
    sa.MetaData(),
    sa.Column("id", sa.Integer, nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("id", name=_PRIMARY_KEY_NAME),
    sa.CheckConstraint(sa.text("length(label) <= 200"), name=_CHECK_NAME),
)

#: The row the probe table starts with, so a second insert of the same key is
#: refused. Its label is not the sentinel: the sentinel must only ever enter the
#: database through the statement that fails.
_INCUMBENT_ID = 1


def _engine_or_skip(*, hide: bool | None) -> Engine:
    """An engine from the shared factory, or skip when no database is reachable.

    Built through `create_db_engine` rather than `create_engine` on purpose:
    the flag is a property of *the factory the services use*, and a test that
    built its own engine would prove nothing about them.

    `monkeypatch` is not used because this is also called from a module-scoped
    fixture, where a function-scoped fixture is not available; the variable is
    restored in a `finally` instead.
    """
    previous = os.environ.get(_HIDE_PARAMETERS_VAR)
    if hide is None:
        os.environ.pop(_HIDE_PARAMETERS_VAR, None)
    else:
        os.environ[_HIDE_PARAMETERS_VAR] = "true" if hide else "false"
    try:
        engine = create_db_engine(DATABASE_URL)
    finally:
        if previous is None:
            os.environ.pop(_HIDE_PARAMETERS_VAR, None)
        else:
            os.environ[_HIDE_PARAMETERS_VAR] = previous
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        engine.dispose()
        pytest.skip(f"no PostgreSQL available at {DATABASE_URL}: {exc}")
    return engine


@pytest.fixture(scope="module")
def probe_table() -> Iterator[None]:
    """Create the probe table with its incumbent row, and drop it afterwards.

    Dropped in a `finally` and with `IF EXISTS`, so a killed run leaves at most
    one uniquely-named two-column table rather than something a later run
    collides with.
    """
    engine = _engine_or_skip(hide=None)
    try:
        with engine.begin() as conn:
            _PROBE.create(conn)
            conn.execute(sa.insert(_PROBE).values(id=_INCUMBENT_ID, label="incumbent"))
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP TABLE IF EXISTS "{_TABLE_NAME}"'))
        engine.dispose()


def _refused_duplicate(engine: Engine) -> IntegrityError:
    """Bind the sentinel into a statement the primary key must refuse."""
    with pytest.raises(IntegrityError) as excinfo, engine.begin() as conn:
        conn.execute(sa.insert(_PROBE).values(id=_INCUMBENT_ID, label=_SENTINEL))
    return excinfo.value


@pytest.mark.usefixtures("probe_table")
def test_a_refused_write_names_the_constraint_and_not_the_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With the flag on, the operator keeps the diagnosis and loses the data.

    All four assertions are the point together:

    - the constraint name survives, so the error is still actionable;
    - the suppression notice is present, so the absence below is explained
      rather than coincidental;
    - the bound value is gone from the exception text;
    - and gone from the engine's own log, which is the other way it escapes —
      `echo=True` and a `DEBUG`-level `sqlalchemy.engine` logger print the
      parameter tuple, and the same flag suppresses that too.
    """
    engine = _engine_or_skip(hide=True)
    try:
        with caplog.at_level(logging.DEBUG, logger="sqlalchemy.engine"):
            exc = _refused_duplicate(engine)
    finally:
        engine.dispose()

    rendered = str(exc)
    assert _PRIMARY_KEY_NAME in rendered
    assert _SUPPRESSION_NOTICE in rendered
    assert _SENTINEL not in rendered

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENTINEL not in logged


@pytest.mark.usefixtures("probe_table")
def test_hiding_parameters_changes_only_the_text() -> None:
    """The exception class and the driver's own error are untouched.

    This is the "no behaviour change" half of the claim. Code that branches on
    the exception type, or reads `exc.orig.diag.constraint_name` — which
    `smartmatch_persistence.spend` does — must be unaffected, and the flag must
    not have quietly turned a refusal into some other failure.
    """
    engine = _engine_or_skip(hide=True)
    try:
        exc = _refused_duplicate(engine)
    finally:
        engine.dispose()

    assert isinstance(exc, IntegrityError)
    assert getattr(exc.orig, "diag", None) is not None
    assert exc.orig.diag.constraint_name == _PRIMARY_KEY_NAME  # type: ignore[union-attr]


@pytest.mark.usefixtures("probe_table")
def test_the_switch_is_real() -> None:
    """With the variable off, the value comes back.

    Without this case the first test could pass against a statement that never
    bound the sentinel in the first place. It is the control, and it is also the
    documented rollback: this is what a deployment gets if it turns the flag
    off.
    """
    engine = _engine_or_skip(hide=False)
    try:
        exc = _refused_duplicate(engine)
    finally:
        engine.dispose()

    rendered = str(exc)
    assert _SENTINEL in rendered
    assert _SUPPRESSION_NOTICE not in rendered


@pytest.mark.usefixtures("probe_table")
def test_the_servers_own_detail_line_is_not_covered() -> None:
    """A known limitation, asserted rather than assumed.

    `hide_parameters` is a SQLAlchemy rendering switch. PostgreSQL composes its
    own message, and for a CHECK or NOT NULL violation that message carries
    `DETAIL: Failing row contains (…)` — the values of the refused row. That
    text is already inside `exc.orig` before SQLAlchemy sees it, so the flag
    cannot remove it, and `str(exc)` reproduces it above the suppressed
    parameter line.

    Consequences, which is why this test exists rather than a comment:

    1. The flag is the floor, not the ceiling. The per-repository scrubbers in
       `smartmatch_persistence.exercise` stay, because never rendering the
       driver's exception is the only complete answer.
    2. A module that logs `str(exc)` for a CHECK-refused write still publishes
       the row. Reviewers should read that as a finding, not as covered.

    If a future change makes the server's DETAIL suppressible — a driver
    option, or a PostgreSQL setting — this test fails, which is the right way to
    learn that the answer improved.
    """
    engine = _engine_or_skip(hide=True)
    try:
        with pytest.raises(IntegrityError) as excinfo, engine.begin() as conn:
            conn.execute(sa.insert(_PROBE).values(id=_INCUMBENT_ID + 1, label="x" * 201))
    finally:
        engine.dispose()

    rendered = str(excinfo.value)
    assert _CHECK_NAME in rendered
    assert _SUPPRESSION_NOTICE in rendered, "SQLAlchemy's own rendering is still suppressed"
    assert "Failing row contains" in rendered, (
        "the server's DETAIL line is outside this flag's reach; "
        "see this test's docstring before treating the flag as sufficient"
    )
