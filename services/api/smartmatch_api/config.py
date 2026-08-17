"""API configuration and boot-time validation.

Architecture v1.1 §3.3 requires a boot-time assertion that ``edition ==
classroom`` implies fixture adapters, and §3.2 requires that environment
configurations share no project, database, queue, bucket, service-account, or
secret identifier.

Both are validated here at startup rather than trusted. A misconfigured
environment must fail to boot, not fail closed later under load.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from smartmatch_providers import Edition


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    No default points at a live service. An unconfigured deployment runs against
    fixtures and a local database, which is the only safe default.
    """

    model_config = SettingsConfigDict(
        env_prefix="SMARTMATCH_",
        env_file=".env",
        extra="ignore",
    )

    edition: Edition = Edition.DEV

    #: Synchronous PostgreSQL DSN. The local default carries no credentials of
    #: consequence and points at a developer's own machine.
    database_url: str = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

    #: Force fixture providers regardless of edition. Always true until the
    #: corresponding release gate opens.
    use_fixture_providers: bool = True

    email_api_key: str | None = None
    routes_api_key: str | None = None

    #: Included in the health response so a deployment can be identified without
    #: exposing topology.
    release: str = Field(default="dev", description="Release identifier")

    @model_validator(mode="after")
    def _validate_isolation(self) -> Settings:
        """Enforce the classroom isolation and credential rules at boot.

        Raises:
            ValueError: if a classroom deployment carries provider credentials
                or has fixture providers disabled.
        """
        if self.edition is Edition.CLASSROOM:
            if not self.use_fixture_providers:
                raise ValueError(
                    "edition=classroom requires use_fixture_providers=true "
                    "(architecture v1.1 §3.3)"
                )
            if self.email_api_key or self.routes_api_key:
                raise ValueError(
                    "edition=classroom must have no provider credentials in its "
                    "environment; found one. Check the secret bindings for this "
                    "project — classroom and production must share no secret "
                    "identifiers (architecture v1.1 §3.2)."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, validated once at first use."""
    return Settings()
