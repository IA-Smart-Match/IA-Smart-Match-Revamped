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
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    #: Included in the health response so a deployment can be identified without
    #: exposing topology.
    release: str = Field(default="dev", description="Release identifier")

    @property
    def allowed_service_accounts(self) -> frozenset[str]:
        """The allowlist, parsed. Empty when unset, which means "refuse everyone"."""
        return frozenset(
            entry.strip() for entry in self.task_service_accounts.split(",") if entry.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    """Return the process-wide worker settings, validated once at first use."""
    return WorkerSettings()
