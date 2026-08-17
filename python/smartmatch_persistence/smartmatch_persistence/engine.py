"""Engine and session construction."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["create_db_engine", "create_session_factory"]


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build an engine with settings suited to Cloud Run.

    ``pool_pre_ping`` is on because Cloud SQL closes idle connections and a Cloud
    Run instance can sit idle between requests; without it the first query after
    an idle period fails on a stale connection.

    ``pool_size`` is deliberately small. Each Cloud Run instance gets its own
    pool, so the database-side connection count is ``instances × pool_size`` and
    a generous per-instance pool exhausts Cloud SQL's limit under autoscale long
    before it helps throughput.
    """
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        future=True,
    )


def create_session_factory(database_url: str, *, echo: bool = False) -> sessionmaker[Session]:
    """Build a session factory.

    ``expire_on_commit=False`` so values read inside a transaction stay usable
    after it commits — repositories return plain dataclasses, and re-fetching
    them to read an attribute would be a needless round trip.
    """
    return sessionmaker(
        bind=create_db_engine(database_url, echo=echo),
        expire_on_commit=False,
        future=True,
    )
