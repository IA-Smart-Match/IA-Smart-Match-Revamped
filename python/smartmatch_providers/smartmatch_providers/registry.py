"""Provider construction, with classroom isolation enforced.

Architecture v1.1 §3.3 lists five isolation mechanisms. This module implements
the third — **configuration validation**: a boot-time assertion that
``edition == classroom`` implies fixture adapters. The other four (absent
credentials, restricted egress, deployment policy, CI tests) live outside the
application, and none of them is sufficient alone.

The assertion is written to fail closed. A classroom deployment that somehow
acquired credentials still cannot construct a live client, because the edition
check happens before the credential check and raises rather than warning.
"""

from __future__ import annotations

from smartmatch_providers.base import (
    Edition,
    EmailProvider,
    ProviderConfigurationError,
    RouteMatrixProvider,
)
from smartmatch_providers.fixtures import FixtureEmailProvider, FixtureRouteMatrixProvider

__all__ = ["build_email_provider", "build_route_matrix_provider"]

#: Editions that may never construct a live provider client, regardless of what
#: credentials happen to be present in the environment.
_FIXTURE_ONLY_EDITIONS: frozenset[Edition] = frozenset({Edition.CLASSROOM})


def _assert_fixture_only(edition: Edition, provider_kind: str) -> None:
    """Raise if a live client is being built under a fixture-only edition."""
    if edition in _FIXTURE_ONLY_EDITIONS:
        raise ProviderConfigurationError(
            f"edition {edition.value!r} may not construct a live {provider_kind} client. "
            "Classroom isolation is enforced in code, not by configuration convention "
            "(architecture v1.1 §3.3)."
        )


def build_email_provider(
    edition: Edition,
    *,
    api_key: str | None = None,
    use_fixture: bool = False,
) -> EmailProvider:
    """Construct the email provider for this edition.

    Args:
        edition: The running edition.
        api_key: Live provider credential. Absent in every environment except a
            deliberately configured staging or production deployment.
        use_fixture: Force the fixture adapter regardless of edition, for tests
            and local development.

    Returns:
        An :class:`~smartmatch_providers.base.EmailProvider`.

    Raises:
        ProviderConfigurationError: if a live client is requested under a
            fixture-only edition, or if credentials are absent outside one.
    """
    if use_fixture or edition in _FIXTURE_ONLY_EDITIONS:
        if api_key and edition in _FIXTURE_ONLY_EDITIONS:
            # Credentials must not exist in a classroom project at all. Finding
            # one is a deployment defect worth failing on, not ignoring.
            raise ProviderConfigurationError(
                f"an email credential is present under edition {edition.value!r}, which "
                "must have no provider secrets. Failing closed; check the environment "
                "configuration and secret bindings."
            )
        return FixtureEmailProvider()

    _assert_fixture_only(edition, "email")

    if not api_key:
        raise ProviderConfigurationError(
            f"no email credential configured for edition {edition.value!r}. Live "
            "adapters are skeletons in the Foundation scaffold and cannot initialize "
            "without separately approved configuration."
        )

    raise ProviderConfigurationError(
        "the live email adapter is not implemented in the Foundation scaffold. "
        "Outreach ships in R4, behind gate G4 (consent-origin policy, supervised "
        "recipient policy, and deliverability review approved)."
    )


def build_route_matrix_provider(
    edition: Edition,
    *,
    api_key: str | None = None,
    use_fixture: bool = False,
) -> RouteMatrixProvider:
    """Construct the route-matrix provider for this edition.

    Mirrors :func:`build_email_provider`. The live Routes adapter is deferred to
    R1 and gated on open decision 6 (provider terms and per-run call budget);
    until then the interim is a straight-line approximation carrying a visible
    ``"estimate quality: coarse"`` label, never presented as a real route time.

    Raises:
        ProviderConfigurationError: under the same conditions as
            :func:`build_email_provider`.
    """
    if use_fixture or edition in _FIXTURE_ONLY_EDITIONS:
        if api_key and edition in _FIXTURE_ONLY_EDITIONS:
            raise ProviderConfigurationError(
                f"a route-matrix credential is present under edition {edition.value!r}, "
                "which must have no provider secrets. Failing closed."
            )
        return FixtureRouteMatrixProvider()

    _assert_fixture_only(edition, "route matrix")

    if not api_key:
        raise ProviderConfigurationError(
            f"no route-matrix credential configured for edition {edition.value!r}."
        )

    raise ProviderConfigurationError(
        "the live Routes adapter is not implemented in the Foundation scaffold. "
        "It ships in R1, pending open decision 6 (provider terms and per-run call "
        "budget)."
    )
