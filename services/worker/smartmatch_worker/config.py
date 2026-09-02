"""Worker configuration.

Read from the environment, validated once, and — this is the part that matters —
carrying **no default that would make the worker easier to reach**. There is no
default audience and no default service-account allowlist, so a deployment that
forgets to configure task identity gets a worker that refuses every delivery
rather than one that accepts any.

That asymmetry is deliberate and is the same rule the API's ``Settings`` follows
(v1.1 §3.3): a missing setting must degrade towards refusal, never towards
access. The database URL is the exception, and only because its default points
at a developer's own machine and grants nothing.

The batch sizes and the job lease are not exceptions to that rule; they are
outside it. None of them decides who may reach this service — they tune how much
one scheduled pass does and how patient the stalled-job sweep is — so each
carries a working default and a stated failure direction, which for
``job_lease_seconds`` is the one that matters (see below).
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from smartmatch_persistence.jobs import DEFAULT_JOB_LEASE

__all__ = ["WorkerSettings", "get_settings"]


class WorkerSettings(BaseSettings):
    """Runtime configuration for the worker service."""

    model_config = SettingsConfigDict(
        env_prefix="SMARTMATCH_",
        env_file=".env",
        extra="ignore",
    )

    #: Synchronous PostgreSQL DSN. The local default carries no credentials of
    #: consequence and points at a developer's own machine.
    database_url: str = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

    #: The audience Cloud Tasks mints its OIDC tokens for: this service's
    #: deployed URL. **No default.** Cloud Run services in one project routinely
    #: share a service account, so audience is the only thing that distinguishes
    #: a token minted for this worker from one minted for a sibling service.
    task_audience: str | None = Field(
        default=None,
        description="This worker's URL, as configured on the Cloud Tasks queue",
    )

    #: Comma-separated service-account addresses permitted to deliver tasks.
    #: **No default**, because an empty allowlist must mean "nobody", and any
    #: default would mean "somebody nobody chose".
    #:
    #: A string rather than a set: environment variables are strings, and
    #: pydantic-settings parses a collection-typed field as JSON — so a
    #: perfectly reasonable ``a@x,b@y`` would fail to boot with a JSON error
    #: that names neither the setting's purpose nor its format.
    task_service_accounts: str = Field(
        default="",
        description="Comma-separated dispatcher service accounts allowed to invoke this worker",
    )

    #: Comma-separated service-account addresses permitted to drive the
    #: scheduled dispatcher pass (J8). **No default**, for the same reason
    #: ``task_service_accounts`` has none, and kept as a separate setting rather
    #: than reusing that one: Cloud Tasks and Cloud Scheduler are different
    #: callers reaching different endpoints, and one allowlist would mean that
    #: granting the queue permission to deliver a task also granted it
    #: permission to drive dispatch. Nothing needs both, so nothing gets both by
    #: default.
    scheduler_service_accounts: str = Field(
        default="",
        description="Comma-separated Cloud Scheduler service accounts allowed to run a pass",
    )

    #: The audience Cloud Scheduler mints its OIDC tokens for. **No default and
    #: no fall back to** ``task_audience``: a fallback would mean a deployment
    #: that configured only the queue silently accepted queue-minted tokens on
    #: the dispatch endpoint, which is the asymmetry this module exists to
    #: refuse. In practice both are this service's URL and both are set.
    scheduler_audience: str | None = Field(
        default=None,
        description="This worker's URL, as configured on the Cloud Scheduler job",
    )

    #: Outbox rows claimed per scheduled pass.
    dispatch_batch_size: int = Field(
        default=20,
        gt=0,
        description="Outbox rows claimed per scheduled dispatcher pass",
    )

    #: Jobs timed out per scheduled pass by the J9 sweep. A bound on one
    #: transaction's length, not a throttle on recovery — a backlog larger than
    #: this is cleared by the passes that follow.
    sweep_batch_size: int = Field(
        default=100,
        gt=0,
        description="Jobs timed out per scheduled pass by the stalled-job sweep",
    )

    #: How long a worker's claim on a job stays good without the handler
    #: reporting progress, in seconds (J9).
    #:
    #: **This bounds silence, not duration.** A handler that emits progress is
    #: never swept however long it runs; a handler that says nothing for longer
    #: than this is timed out while it may still be working, and its eventual
    #: outcome is discarded. So the failure direction of a value that is too low
    #: is *terminating live work*, and of one that is too high is *a stuck job
    #: staying invisible for longer* — which is why the default is generous
    #: rather than tight, and why this is the one lease worth raising before
    #: shipping a slow handler.
    job_lease_seconds: int = Field(
        default=int(DEFAULT_JOB_LEASE.total_seconds()),
        gt=0,
        description="How long a claimed job may go without reporting progress",
    )

    #: Filesystem path to the ratified pilot column contract
    #: (``docs/pilot-data/columns.yaml``), read by
    #: :mod:`smartmatch_worker.column_contract`.
    #:
    #: Empty means "resolve it relative to this checkout", which is right for a
    #: developer running from the repository and wrong for an image, where
    #: there is no repository. ``Dockerfile.worker`` therefore copies the file
    #: in and sets this explicitly. It is not an access-control setting — the
    #: failure direction of a bad value is a *refused import*, never a
    #: permissive one, because a contract that cannot be read raises rather
    #: than falling back to validating nothing.
    column_contract_path: str = Field(
        default="",
        description="Path to columns.yaml; empty resolves relative to the checkout",
    )

    #: Included in the health response so a deployment can be identified without
    #: exposing topology.
    release: str = Field(default="dev", description="Release identifier")

    @property
    def allowed_service_accounts(self) -> frozenset[str]:
        """The allowlist, parsed. Empty when unset, which means "refuse everyone"."""
        return frozenset(
            entry.strip() for entry in self.task_service_accounts.split(",") if entry.strip()
        )

    @property
    def allowed_scheduler_accounts(self) -> frozenset[str]:
        """The scheduler allowlist, parsed. Empty when unset, meaning "refuse everyone"."""
        return frozenset(
            entry.strip() for entry in self.scheduler_service_accounts.split(",") if entry.strip()
        )

    @property
    def job_lease(self) -> timedelta:
        """:attr:`job_lease_seconds` as the ``timedelta`` the repository wants."""
        return timedelta(seconds=self.job_lease_seconds)


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    """Return the process-wide worker settings, validated once at first use."""
    return WorkerSettings()
