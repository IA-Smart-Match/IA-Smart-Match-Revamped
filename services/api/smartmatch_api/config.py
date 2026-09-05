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
from smartmatch_domain.product_scope import (
    DEFAULT_PRODUCT_SCOPE,
    Capability,
    ProductScope,
    enabled_capabilities,
    is_capability_enabled,
)
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

    #: Which *product* this process runs — a different question from ``edition``,
    #: which is which *deployment* it is.
    #:
    #: ``edition`` decides whether a provider credential may exist here.
    #: ``product_scope`` decides which named capabilities the product offers.
    #: The two never derive from one another: a classroom deployment can run
    #: either product, and the CBA product can run in any edition. Folding them
    #: into one flag would let a deployment knob change a product decision.
    #:
    #: Defaults to the narrower product, so a missing environment variable
    #: cannot widen what the system offers. An unrecognised value fails
    #: validation and the process does not boot — see
    #: ``smartmatch_domain.product_scope``.
    product_scope: ProductScope = DEFAULT_PRODUCT_SCOPE

    #: Synchronous PostgreSQL DSN. The local default carries no credentials of
    #: consequence and points at a developer's own machine.
    database_url: str = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

    #: Force fixture providers regardless of edition. Always true until the
    #: corresponding release gate opens.
    use_fixture_providers: bool = True

    #: Local-pilot bearer tokens mapped to their stable external subjects.
    #:
    #: This is intentionally not an account-authentication system: it has no
    #: password, expiry, or revocation. It exists only to make a local fixture
    #: verifier accept a finite, explicitly configured set of test principals.
    #: It must never be present outside development.
    dev_principals: dict[str, str] = Field(default_factory=dict)

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
                    "edition=classroom requires use_fixture_providers=true (architecture v1.1 §3.3)"
                )
            if self.email_api_key or self.routes_api_key:
                raise ValueError(
                    "edition=classroom must have no provider credentials in its "
                    "environment; found one. Check the secret bindings for this "
                    "project — classroom and production must share no secret "
                    "identifiers (architecture v1.1 §3.2)."
                )
        if self.dev_principals:
            if self.edition is not Edition.DEV:
                raise ValueError(
                    "dev_principals may only be configured for edition=dev; "
                    "staging, classroom, and production must reject local pilot tokens."
                )
            if not self.use_fixture_providers:
                raise ValueError(
                    "dev_principals require fixture providers; no live verifier exists."
                )
            if any(not token or not subject for token, subject in self.dev_principals.items()):
                raise ValueError("dev_principals keys and values must be non-empty strings.")
        return self

    def capability_enabled(self, capability: Capability) -> bool:
        """Whether this process's product scope offers ``capability``.

        The one adapter between configuration and the policy. Callers ask this
        rather than comparing ``product_scope`` to a literal, so that adding a
        scope never means hunting for equality checks — and so that an unknown
        capability name raises here too, rather than reading as "disabled".

        This is a *product* question, never an authorization one: a route that
        stays mounted still enforces its own deny-by-default authorization, and
        no capability may be derived from a role label.
        """
        return is_capability_enabled(self.product_scope, capability)

    def enabled_capabilities(self) -> frozenset[Capability]:
        """Every capability this process's product scope offers."""
        return enabled_capabilities(self.product_scope)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, validated once at first use."""
    return Settings()
