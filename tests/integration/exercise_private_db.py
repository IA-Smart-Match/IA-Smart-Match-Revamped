"""A privately named, seeded database for the exercise gate tests.

``migration_harness.scratch_database`` sweeps every ``smartmatch_scratch_*``
database on entry, which kills another agent's or run's live database. These
tests name theirs after the configured database plus a suffix of their own, so
the sweep never matches it and two files never share one.

Not a test module (no ``test_`` prefix).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from migration_harness import alembic, connected
from smartmatch_api.exercise_seed import seed_exercise_dataset
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.unit.exercise_workbooks import ANN_FULL_FILE

_SUFFIX = re.compile(r"^[a-z0-9_]{1,20}$")


@contextmanager
def seeded_private_database(engine: Engine, suffix: str) -> Iterator[sessionmaker[Session]]:
    """Create ``<configured db>_<suffix>``, migrate and seed it, drop it afterwards."""
    assert _SUFFIX.match(suffix), suffix
    name = f"{engine.url.database}_{suffix}"
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            url = engine.url.set(database=name)
            alembic(url, "head", expect_success=True)
            with connected(url) as scratch:
                factory = sessionmaker(
                    bind=scratch, expire_on_commit=False, future=True, autoflush=False
                )
                with factory() as session:
                    outcome = seed_exercise_dataset(
                        session, ANN_FULL_FILE.read_bytes(), source_filename=ANN_FULL_FILE.name
                    )
                assert getattr(outcome, "seeded", None) is True, outcome
                yield factory
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()
