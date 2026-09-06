"""Run real migrations against a throwaway database.

Some things a migration does can only be exercised on a database that is *not*
the one the suite runs against, because the state under test no longer exists
there. ``0003``'s duplicate-subject guard needs a database holding the duplicates
its constraint forbids; ``0006``'s backfill needs one holding pre-backfill job
rows. Both are gone from the dev database the moment the migration has been
applied to it.

So this module builds a scratch database, brings it to a chosen revision, lets
the caller fill it, and then runs Alembic for real — as a subprocess, exactly as
an operator would. Nothing about the migration is stubbed or re-implemented: the
assertions callers make are on the process's exit status and on the text a human
would actually read.

Extracted from ``test_principal_identity.py``, which held the only copy and
still holds the only *caller* of ``0003``'s guard. The second migration needing
a scratch database is the moment a private copy becomes two copies, and two
copies of a database-dropping sweep is not a thing to have.

Not a ``conftest.py``, and not fixtures. The callers need the scratch database at
different points in their own setup, and a fixture would have to guess. These are
functions and one context manager.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

REPO_ROOT = Path(__file__).resolve().parents[2]

#: PostgreSQL's ``insufficient_privilege``. The *only* condition under which a
#: caller declines to exercise a migration, checked as a SQLSTATE rather than by
#: catching the exception class it arrives as: SQLAlchemy wraps it as
#: ``ProgrammingError``, psycopg raises it as ``InsufficientPrivilege``, and
#: neither name is the thing being tested for.
INSUFFICIENT_PRIVILEGE = "42501"

#: PostgreSQL's ``object_in_use``: the database is connected to. The sweep below
#: treats it as "not mine to remove" rather than as a failure.
_OBJECT_IN_USE = "55006"

#: Name prefix for the throwaway databases this module creates. Used both to
#: build a name and to recognise a leaked one, so the two cannot disagree about
#: what these tests own.
_SCRATCH_PREFIX = "smartmatch_scratch_"

#: The exact shape this module creates. The sweep drops only names matching it,
#: which keeps it to databases these tests made — and, because the pattern admits
#: nothing but the prefix and twelve hex digits, means a name can be interpolated
#: into ``DROP DATABASE`` without any question of what a catalog entry might
#: contain.
_SCRATCH_NAME = re.compile(rf"^{re.escape(_SCRATCH_PREFIX)}[0-9a-f]{{12}}$")


@contextmanager
def scratch_database(engine: Engine) -> Iterator[sa.engine.URL]:
    """Yield the URL of an empty database, and drop it afterwards.

    Skips the calling test — rather than failing it — in exactly one case: the
    test role lacks the privilege to create a database, which is a gap in the
    environment and not a defect in the migration. Every other database failure,
    including a server restart or ``too many clients already``, propagates
    loudly and deliberately: these are the only tests that exercise the
    migration guards at all, so a skip that a flake can produce would leave a
    guard unverified while CI stayed green.

    Leaked databases from runs that were killed before the ``finally`` are swept
    on the way in. On this project being killed mid-run is routine rather than
    exceptional, and each leak carries a fresh random name, so leaks accumulate
    quietly instead of colliding and announcing themselves.
    """
    name = f"{_SCRATCH_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        try:
            with admin.connect() as conn:
                _drop_leaked_scratch_databases(conn)
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        except DBAPIError as exc:  # pragma: no cover - environment dependent
            if getattr(exc.orig, "sqlstate", None) != INSUFFICIENT_PRIVILEGE:
                raise
            pytest.skip(
                f"{engine.url.username} lacks the privilege to create a database, so "
                f"this migration cannot be exercised here: {exc.orig}"
            )

        try:
            yield engine.url.set(database=name)
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        # Outermost, so the AUTOCOMMIT connection to ``postgres`` is returned
        # even when the create above skips the test — ``pytest.skip`` raises a
        # ``BaseException``, which an ``except`` clause alone does not survive.
        admin.dispose()


def _drop_leaked_scratch_databases(admin: sa.Connection) -> None:
    """Remove scratch databases an earlier run was killed before dropping.

    Scoped by :data:`_SCRATCH_NAME` to databases these tests created, in the same
    spirit as ``conftest._clean_dispatch_state``: clean up what an interrupted
    run left behind, and nothing that belongs to somebody else.

    ``DROP DATABASE`` is issued **without** ``FORCE``. A database still connected
    to is one a concurrently running suite is using, and terminating its backends
    to tidy up would be a worse bug than the leak. PostgreSQL refuses with
    ``object_in_use`` (``55006``) in that case and the name is left alone; any
    other failure is re-raised.
    """
    leaked = [
        name
        for name in admin.execute(text("SELECT datname FROM pg_database")).scalars()
        if _SCRATCH_NAME.match(name)
    ]
    for name in leaked:
        try:
            admin.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != _OBJECT_IN_USE:
                raise


def alembic(
    url: sa.engine.URL,
    revision: str,
    *,
    expect_success: bool,
    command: str = "upgrade",
) -> subprocess.CompletedProcess[str]:
    """Run ``alembic <command> <revision>`` against ``url`` the way an operator would.

    ``sys.executable -m alembic`` rather than a path to the console script, so
    the interpreter running the tests is the one running the migration and there
    is no virtualenv layout to guess. ``render_as_string(hide_password=False)``
    because the default masks the password as ``***``, which the subprocess would
    then try to authenticate with.

    Args:
        expect_success: Asserted here rather than by the caller, so a migration
            that was supposed to refuse and quietly succeeded fails at the call
            that ran it instead of three assertions later.
    """
    env = dict(os.environ, SMARTMATCH_DATABASE_URL=url.render_as_string(hide_password=False))
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=REPO_ROOT / "db",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success:
        assert completed.returncode == 0, f"{command} to {revision} failed: {completed.stderr}"
    else:
        assert completed.returncode != 0, (
            f"{command} to {revision} succeeded and should not have: {completed.stdout}"
        )
    return completed


@contextmanager
def connected(url: sa.engine.URL) -> Iterator[Engine]:
    """An engine on ``url``, disposed afterwards.

    Disposal matters more here than it usually would: the scratch database is
    dropped by :func:`scratch_database`, and a pooled connection still open to it
    is what turns that drop into ``object_in_use``.
    """
    scratch = create_engine(url)
    try:
        yield scratch
    finally:
        scratch.dispose()


def applied_revision(url: sa.engine.URL) -> str:
    """The revision the database records as applied.

    Asserted after a refusal to prove the failed migration did not record itself
    — the difference between "it stopped" and "it stopped after doing half of
    it".
    """
    with connected(url) as scratch, scratch.connect() as conn:
        revision: str = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        return revision
