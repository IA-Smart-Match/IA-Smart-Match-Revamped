"""Fill an empty class-exercise database from Ann's fixture file (CE-SEED).

Owner design "A", 2026-09-25: **the database comes first, and Ann's fixture
file is the fallback that fills an empty database.** The exercise reads its
students and events from ``exercise_dataset`` and its two child tables; before
this module, every fresh developer or test database stayed empty until someone
uploaded the file by hand on the instructor page.

Two ways in, one code path
==========================

* ``make exercise-seed`` runs :func:`main`
  (``python -m smartmatch_api.exercise_seed [--file PATH] [--force]``).
* ``SMARTMATCH_EXERCISE_SEED_ON_START=true`` makes the API's ``lifespan`` call
  :func:`seed_on_start` once — developer machines only; see the guard below.

Both end in :func:`seed_exercise_dataset`, which does exactly what the
instructor upload (``routers/exercise_instructor.py``, ``upload_dataset``)
does: :func:`~smartmatch_domain.exercise.ingest.parse_exercise_file`, then
:meth:`ExerciseDatasetRepository.create_dataset`, then one commit. There is no
separate "activate" step to reuse, because there is no ``is_active`` column:
the active dataset *is* the newest row
(:func:`~smartmatch_persistence.exercise.workspace_repository.active_dataset`),
so storing a file is what makes it active, here as on the upload. The upload
handler is therefore untouched — its two calls already live outside the router,
in the domain and the repository, and this module calls the same two.

Idempotent by default
=====================

"Empty" means :func:`active_dataset` answers ``None``. When it does not, the
seed stores nothing and says so in one line, whoever put the dataset there —
an instructor's upload is never replaced, re-pointed or deleted. ``--force``
stores Ann's file as one more dataset regardless; it never deletes one.

The check and the write run under one transaction-level advisory lock, so two
API processes starting together cannot both see an empty table and both seed.

What it may say (ADR-0025 D6)
=============================

Counts and the dataset's label, nothing else. The withheld columns
(``EXERCISE_WITHHELD_FIELDS``) are read by the parser and written by the
repository, and neither returns them in anything this module prints or logs. A
failure on start is logged as the exception's *type* only: a driver message can
carry ``[parameters: …]``, every value of every row.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.ingest import IngestRefusal, parse_exercise_file
from smartmatch_domain.product_scope import Capability
from smartmatch_persistence.engine import create_db_engine
from smartmatch_persistence.exercise.dataset_repository import (
    ExerciseDatasetRepository,
    ExerciseDatasetWriteError,
)
from smartmatch_persistence.exercise.workspace_repository import active_dataset
from smartmatch_providers import Edition
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import Session

from smartmatch_api.config import Settings, get_settings

__all__ = [
    "DEFAULT_SEED_FILE",
    "SEED_LABEL",
    "SEED_LOCK_KEY",
    "SeedOutcome",
    "auto_seed_refusal",
    "main",
    "seed_exercise_dataset",
    "seed_on_start",
]

_LOGGER = logging.getLogger(__name__)

#: Ann's full file, as committed for the golden tests. Resolved from this
#: module's own path, so it exists in a repository checkout and nowhere else —
#: ``Dockerfile.api`` copies ``python/`` and ``services/api/`` only, which is one
#: more reason the start-up seed cannot run inside a built image.
DEFAULT_SEED_FILE: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "exercise"
    / "SmartMatch_Student_Body_300.xlsx"
)

#: What a seeded dataset is called on the instructor page, so nobody mistakes
#: it for a file they uploaded.
SEED_LABEL: Final[str] = "Ann's student body (seeded)"

#: The advisory-lock key the seed's check-then-write takes. Derived like
#: ``WORKSPACE_MEMBERSHIP_LOCK_KEY``: the first eight bytes of a SHA-256 of a
#: name nothing else hashes, read as PostgreSQL's signed ``bigint``.
SEED_LOCK_KEY: Final[int] = int.from_bytes(
    hashlib.sha256(b"exercise_dataset:seed").digest()[:8], "big", signed=True
)

#: Hosts that are this machine. A seed-on-start against anything else is
#: refused: the pilot VM's exercise database is ``db``, a compose service name.
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """What one seed did: stored a dataset, or found one and left it alone."""

    seeded: bool
    label: str
    profile_count: int
    event_count: int

    def line(self) -> str:
        """One line for a terminal or a log: counts and a label, nothing else."""
        if self.seeded:
            return (
                f"Seeded exercise dataset {self.label!r}: "
                f"{self.profile_count} profiles, {self.event_count} events."
            )
        return f"An exercise dataset is already active ({self.label!r}); nothing seeded."


def seed_exercise_dataset(
    session: Session,
    content: bytes,
    *,
    source_filename: str,
    force: bool = False,
) -> SeedOutcome | IngestRefusal:
    """Store ``content`` as the active dataset if there is none, and commit.

    Args:
        session: A fresh session. Committed when a dataset is stored; rolled
            back otherwise, which releases the advisory lock either way.
        content: The workbook's bytes.
        source_filename: Stored as a label, as the upload stores the browser's.
        force: Store a new dataset even when one is active. Deletes nothing.

    Returns:
        The outcome, or the parser's refusal — the same one-sentence refusal
        the instructor upload would have answered with.

    Raises:
        ExerciseDatasetWriteError: if the database refuses the write. Its text
            is the repository's scrubbed sentence, never the driver's.
    """
    session.execute(sa.select(sa.func.pg_advisory_xact_lock(SEED_LOCK_KEY)))
    existing = active_dataset(session)
    if existing is not None and not force:
        session.rollback()
        return SeedOutcome(seeded=False, label=existing.label, profile_count=0, event_count=0)
    parsed = parse_exercise_file(content)
    if isinstance(parsed, IngestRefusal):
        session.rollback()
        return parsed
    summary = ExerciseDatasetRepository().create_dataset(
        session, parsed, label=SEED_LABEL, source_filename=source_filename
    )
    session.commit()
    return SeedOutcome(
        seeded=True,
        label=summary.label,
        profile_count=parsed.report.profile_count,
        event_count=parsed.report.event_count,
    )


# ---------------------------------------------------------------------------
# On start
# ---------------------------------------------------------------------------


def auto_seed_refusal(settings: Settings) -> str | None:
    """Why this process must not seed on start, or ``None`` when it may.

    An allow-list of a host-run developer API rather than a list of things a
    production box might look like. ``SMARTMATCH_EDITION`` alone cannot be the
    guard: the pilot VM's compose file pins it to ``dev``. So every one of
    these must hold, and each is a signal the VM gives independently:

    1. ``SMARTMATCH_EXERCISE_COOKIE_SECURE`` is not ``true`` — the VM hard-sets
       it (``docker-compose.exercise.yml``), because it is served over TLS;
    2. ``SMARTMATCH_EDITION`` is ``dev``;
    3. ``SMARTMATCH_RELEASE`` is its unset default, ``dev`` — the VM passes
       ``vm-unknown`` or a commit, the compose stack ``compose-dev``;
    4. fixture providers are on and no provider credential is configured;
    5. ``SMARTMATCH_DATABASE_URL`` names this machine — the VM's is ``db``;
    6. the process runs the class exercise at all.

    The sentence names the setting and never its value, so a database URL's
    password cannot reach a log line.
    """
    if settings.exercise_cookie_secure is True:
        return "SMARTMATCH_EXERCISE_COOKIE_SECURE is true, which marks a TLS host"
    if settings.edition is not Edition.DEV:
        return "SMARTMATCH_EDITION is not dev"
    if settings.release != "dev":
        return "SMARTMATCH_RELEASE is set, which marks a built image or a VM"
    if not settings.use_fixture_providers:
        return "SMARTMATCH_USE_FIXTURE_PROVIDERS is false"
    if settings.email_api_key or settings.routes_api_key:
        return "a provider credential is configured"
    if not _database_is_local(settings.database_url):
        return "SMARTMATCH_DATABASE_URL does not name a database on this machine"
    if not settings.capability_enabled(Capability.CLASS_EXERCISE):
        return "SMARTMATCH_PRODUCT_SCOPE does not run the class exercise"
    return None


def _database_is_local(database_url: str) -> bool:
    """Whether every host the URL names is loopback or a local socket directory.

    libpq also takes the host from the query string (``?host=db``,
    ``?hostaddr=10.0.0.5``), where ``URL.host`` does not see it, so those are
    read too. A value there may be a tuple when the key repeats.
    """
    try:
        url = make_url(database_url)
    except ArgumentError:
        return False
    hosts: list[str] = [url.host] if url.host else []
    for key in ("host", "hostaddr"):
        value = url.query.get(key)
        if isinstance(value, str):
            hosts.extend(value.split(","))
        elif value is not None:
            hosts.extend(part for item in value for part in item.split(","))
    return all(host in _LOOPBACK_HOSTS or host.startswith("/") for host in hosts)


def seed_on_start(
    settings: Settings,
    session_factory: Callable[[], Session],
    *,
    seed_file: Path = DEFAULT_SEED_FILE,
) -> None:
    """Seed an empty database once at start-up, if allowed. Never raises.

    Off unless ``SMARTMATCH_EXERCISE_SEED_ON_START`` is set, and refused by
    :func:`auto_seed_refusal` under any production signal. Whatever happens is
    at most one log line; a failure does not stop the API, because the seed is
    a convenience and the instructor upload remains the way in.
    """
    if not settings.exercise_seed_on_start:
        return
    refusal = auto_seed_refusal(settings)
    if refusal is not None:
        _LOGGER.warning("exercise seed on start refused: %s", refusal)
        return
    try:
        content = seed_file.read_bytes()
        with session_factory() as session:
            outcome = seed_exercise_dataset(session, content, source_filename=seed_file.name)
    except Exception as error:  # the API must start whatever the seed does
        _LOGGER.warning("exercise seed on start failed: %s", type(error).__name__)
        return
    if isinstance(outcome, IngestRefusal):
        _LOGGER.warning("exercise seed on start refused the file: code=%s", outcome.code)
        return
    _LOGGER.info("exercise seed on start: %s", outcome.line())


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="exercise-seed",
        description=("Store Ann's exercise file as the active dataset when the database has none."),
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_SEED_FILE,
        help="Another .xlsx to seed from (default: Ann's 300-row fixture).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Add a new dataset even when one is active. Never deletes one.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, database_url: str | None = None) -> int:
    """Run the seed once. Exit 0 when seeded or already seeded, 1 otherwise.

    ``database_url`` is for tests; the command reads ``SMARTMATCH_DATABASE_URL``
    like the API does, and deliberately takes no URL flag, so a password never
    has to appear on a command line.
    """
    args = _parse_args(argv)
    path: Path = args.file
    try:
        content = path.read_bytes()
    except OSError as error:
        print(f"exercise-seed: cannot read {path}: {error.strerror}", file=sys.stderr)
        return 1
    engine = create_db_engine(database_url or get_settings().database_url)
    try:
        with Session(engine, expire_on_commit=False) as session:
            outcome = seed_exercise_dataset(
                session, content, source_filename=path.name, force=args.force
            )
    except ExerciseDatasetWriteError as error:
        print(f"exercise-seed: {error}", file=sys.stderr)
        return 1
    except SQLAlchemyError as error:
        # The type only: a driver message can carry row values (ADR-0025 D6).
        print(f"exercise-seed: database error ({type(error).__name__})", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    if isinstance(outcome, IngestRefusal):
        print(f"exercise-seed: {path.name} was refused: {outcome.message}", file=sys.stderr)
        return 1
    print(f"exercise-seed: {outcome.line()}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through `make exercise-seed`
    raise SystemExit(main())
