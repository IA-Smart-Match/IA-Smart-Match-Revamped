"""Engine and session construction."""

from __future__ import annotations

import logging
import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

__all__ = [
    "DEFAULT_HIDE_PARAMETERS",
    "DEFAULT_MAX_OVERFLOW",
    "DEFAULT_POOL_RECYCLE",
    "DEFAULT_POOL_SIZE",
    "DEFAULT_POOL_TIMEOUT",
    "create_db_engine",
    "create_session_factory",
    "resolve_hide_parameters",
    "resolve_pool_settings",
]

_LOGGER = logging.getLogger(__name__)

#: Steady-state connections one process keeps open. Sized for the single-VM
#: appliance (docker-compose), where the API and the worker are each one
#: uvicorn process against one ``postgres:16`` with the image default
#: ``max_connections = 100``:
#:
#:     (20 + 10) API + (20 + 10) worker = 60 <= 100 - 3 superuser-reserved
#:
#: leaving 37 for the one-shot migrate/seed containers, an operator's psql, and
#: host-side pytest. It is *not* sized for autoscaled Cloud Run, where the
#: database-side count is ``instances x pool_size``; that deployment must set
#: ``SMARTMATCH_DB_POOL_SIZE`` / ``SMARTMATCH_DB_MAX_OVERFLOW`` down to suit its
#: own instance ceiling, which is why these are environment-configurable rather
#: than constants.
DEFAULT_POOL_SIZE = 20

#: Connections opened beyond ``pool_size`` under burst and discarded when
#: returned. Burst headroom, not capacity: a request holds its connection for
#: its whole lifetime (``get_session``), so a fan-out of N concurrent requests
#: wants N connections. Beyond ``pool_size + max_overflow`` callers queue for
#: ``pool_timeout`` rather than fail, which is the correct answer on 2 vCPU —
#: more backends than cores does not add throughput, it adds context switching.
DEFAULT_MAX_OVERFLOW = 10

#: Seconds a caller waits for a connection before ``TimeoutError``. Long enough
#: that a short burst queues and drains instead of erroring.
DEFAULT_POOL_TIMEOUT = 30

#: Seconds after which a pooled connection is recycled, below any idle timeout a
#: managed database is likely to impose.
DEFAULT_POOL_RECYCLE = 1800

#: Whether an engine built here withholds bound values from the text of the
#: errors and log lines it produces. On, and the default everywhere.
#:
#: SQLAlchemy renders a ``DBAPIError`` as the statement **plus**
#: ``[parameters: …]`` — every bound value of the failed statement. Anything
#: that then logs the exception, returns its text, or lets a test runner print
#: it has published those values without a line of code naming them. For the
#: class exercise that is the withheld ``true interests`` column ADR-0025 D6
#: promises never leaves the server; for the CBA track it is real names, email
#: addresses and invitation tokens landing in the server log.
#:
#: With this on, the same exception reads ``[SQL parameters hidden due to
#: hide_parameters=True]``. Nothing else moves: the SQL text, the exception
#: class, the constraint the database named, and ``exc.orig`` (and so
#: ``exc.orig.diag.constraint_name``) are all exactly what they were. The
#: values remain on the exception object for a debugger; what changes is what
#: gets *rendered*. The same suppression applies to ``echo=True`` output, so
#: turning echo on is not a way around this.
#:
#: Per-repository scrubbing stays where it exists — it additionally nulls the
#: exception's ``__context__``, which this flag does not do. This is the floor
#: under those modules, and the only protection for every repository that has
#: no scrubber of its own.
DEFAULT_HIDE_PARAMETERS = True

#: What a deployment may spell to mean each answer for
#: ``SMARTMATCH_DB_HIDE_PARAMETERS``. Compared case-insensitively after
#: stripping, because these arrive from shells, ``.env`` files and compose
#: interpolation, all of which pass through whatever was typed.
_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSY_ENV_VALUES = frozenset({"0", "false", "no", "off"})


def _int_from_env(name: str, default: int) -> int:
    """Read a non-negative integer from the environment.

    An unset or empty variable takes ``default``. A value that is not a
    non-negative integer raises rather than silently reverting to the default:
    a deployment that meant to cap its pool and typed the number wrong must
    fail to boot, not quietly run with the wrong ceiling.

    Raises:
        ValueError: when the variable is set to anything but a non-negative
            integer.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _bool_from_env(name: str, default: bool) -> bool:
    """Read a boolean from the environment, falling back to ``default``.

    Deliberately unlike :func:`_int_from_env`, which raises on a malformed
    value. The two variables are not symmetric. A mistyped pool ceiling must
    stop the boot, because the deployment meant to cap something and now has
    not. A mistyped *privacy* flag must not stop the boot — refusing to start
    over a misspelled debugging switch is worse than the misspelling — and must
    especially not fall through to the permissive answer, which would publish
    the very values the flag exists to withhold.

    So an unreadable value warns, naming the variable and what it could not
    read, and returns ``default``. Callers pass the safe direction as the
    default, which makes an unparseable value fail closed.

    Args:
        name: The environment variable to read.
        default: The answer for an unset, empty or unreadable value.

    Returns:
        The parsed boolean, or ``default``.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUTHY_ENV_VALUES:
        return True
    if value in _FALSY_ENV_VALUES:
        return False
    _LOGGER.warning(
        "%s could not be read as a boolean (got %r); using %r. Accepted values: %s.",
        name,
        raw,
        default,
        ", ".join(sorted(_TRUTHY_ENV_VALUES | _FALSY_ENV_VALUES)),
    )
    return default


def resolve_hide_parameters() -> bool:
    """Whether engines built here withhold bound values from rendered text.

    ``SMARTMATCH_DB_HIDE_PARAMETERS`` overrides
    :data:`DEFAULT_HIDE_PARAMETERS`. Read here rather than through either
    service's pydantic ``Settings`` for the same reason the pool settings are:
    this package is shared by the API, the worker and the ``tools/`` scripts,
    and each has its own settings object or none at all.

    Set it to a falsy value **only** for a local debugging session, never on a
    shared or deployed environment: it puts every bound value of every failed
    statement back into the server log.

    Returns:
        ``True`` when parameters are hidden. An unset, empty or unreadable
        value is ``True`` — see :func:`_bool_from_env`.
    """
    return _bool_from_env("SMARTMATCH_DB_HIDE_PARAMETERS", DEFAULT_HIDE_PARAMETERS)


def resolve_pool_settings() -> dict[str, int]:
    """Pool sizing from the environment, falling back to the defaults above.

    Read here rather than through either service's pydantic ``Settings`` because
    this package is shared by the API, the worker, and the ``tools/`` scripts,
    and each of those has its own settings object (or none at all). One reader
    means one place a deployment can tune, and no caller has to plumb it.

    Raises:
        ValueError: when any of the variables is set to a non-integer.
    """
    return {
        "pool_size": _int_from_env("SMARTMATCH_DB_POOL_SIZE", DEFAULT_POOL_SIZE),
        "max_overflow": _int_from_env("SMARTMATCH_DB_MAX_OVERFLOW", DEFAULT_MAX_OVERFLOW),
        "pool_timeout": _int_from_env("SMARTMATCH_DB_POOL_TIMEOUT", DEFAULT_POOL_TIMEOUT),
        "pool_recycle": _int_from_env("SMARTMATCH_DB_POOL_RECYCLE", DEFAULT_POOL_RECYCLE),
    }


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build an engine with pool settings resolved from the environment.

    ``pool_pre_ping`` is on because a managed database closes idle connections
    and an instance can sit idle between requests; without it the first query
    after an idle period fails on a stale connection.

    Pool sizing comes from :func:`resolve_pool_settings` — see the module
    constants for what the defaults are sized against and why a per-deployment
    override exists.

    ``hide_parameters`` comes from :func:`resolve_hide_parameters` and is on
    unless a deployment turns it off — see :data:`DEFAULT_HIDE_PARAMETERS` for
    what it withholds and why. Note that it also covers ``echo``: SQLAlchemy
    suppresses the parameter tuple in echo output under the same flag, so
    passing ``echo=True`` does not reopen the door.

    Raises:
        ValueError: when a pool environment variable holds a non-integer.
    """
    return create_engine(
        database_url,
        echo=echo,
        hide_parameters=resolve_hide_parameters(),
        pool_pre_ping=True,
        future=True,
        **resolve_pool_settings(),
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
