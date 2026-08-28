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

from collections.abc import Mapping

from smartmatch_providers.base import (
    Edition,
    EmailProvider,
    ProviderConfigurationError,
    RouteMatrixProvider,
)
from smartmatch_providers.fixtures import FixtureEmailProvider, FixtureRouteMatrixProvider
from smartmatch_providers.identity import FixtureTokenVerifier, TokenVerifier
from smartmatch_providers.tasks import FixtureTaskQueue, TaskQueue

__all__ = [
    "build_email_provider",
    "build_route_matrix_provider",
    "build_task_queue",
    "build_token_verifier",
]

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


def build_task_queue(
    edition: Edition,
    *,
    queue_path: str | None = None,
    use_fixture: bool = False,
) -> TaskQueue:
    """Construct the task queue for this edition.

    Mirrors :func:`build_email_provider`. Cloud Tasks is not a "paid provider"
    in the outreach sense, but it is still an external dependency that reaches
    outside the project, so the classroom edition gets the fixture for the same
    reason it gets fixture mail: a classroom deployment must not be able to
    address a production queue (v1.1 §3.3).

    Args:
        queue_path: Fully-qualified Cloud Tasks queue path. Absent in every
            environment except a deliberately configured deployment.
        use_fixture: Force the in-memory queue, for tests and local development.

    Raises:
        ProviderConfigurationError: if a live queue is requested under a
            fixture-only edition, or if the live client is requested at all —
            it is not implemented in the Foundation scaffold.
    """
    if use_fixture or edition in _FIXTURE_ONLY_EDITIONS:
        if queue_path and edition in _FIXTURE_ONLY_EDITIONS:
            raise ProviderConfigurationError(
                f"a Cloud Tasks queue path is configured under edition "
                f"{edition.value!r}, which must not address any production queue. "
                "Failing closed."
            )
        return FixtureTaskQueue()

    _assert_fixture_only(edition, "task queue")

    if not queue_path:
        raise ProviderConfigurationError(
            f"no Cloud Tasks queue configured for edition {edition.value!r}."
        )

    raise ProviderConfigurationError(
        "the live Cloud Tasks adapter is not implemented in the Foundation "
        "scaffold. It requires a deployed worker URL and service identity to "
        "target, neither of which exists yet."
    )


def build_token_verifier(
    edition: Edition,
    *,
    project_id: str | None = None,
    use_fixture: bool = False,
    fixture_principals: Mapping[str, str] | None = None,
) -> TokenVerifier:
    """Construct the identity token verifier for this edition.

    The live Google Identity Platform verifier is not implemented in the
    Foundation scaffold. Implementing it means fetching and caching Google's
    JWKS, validating signature, issuer, audience, and expiry, and handling key
    rotation — none of which can be exercised meaningfully before a real project
    and audience exist.

    The fixture is not a weaker version of that. It accepts only tokens
    explicitly registered with it, so it cannot be mistaken for "authentication
    that happens to be permissive".

    Raises:
        ProviderConfigurationError: if a live verifier is requested under a
            fixture-only edition, or requested at all — it does not exist yet.
    """
    principals = fixture_principals or {}
    if principals and (edition is not Edition.DEV or not use_fixture):
        raise ProviderConfigurationError(
            "fixture principals may only be registered for edition='dev' with "
            "use_fixture=true; local pilot tokens must never reach a deployed edition."
        )

    if use_fixture or edition in _FIXTURE_ONLY_EDITIONS:
        verifier = FixtureTokenVerifier()
        for token, subject in principals.items():
            verifier.register(token, subject)
        return verifier

    _assert_fixture_only(edition, "identity")

    if not project_id:
        raise ProviderConfigurationError(
            f"no identity project configured for edition {edition.value!r}."
        )

    raise ProviderConfigurationError(
        "the live Google Identity Platform verifier is not implemented in the "
        "Foundation scaffold. It is Foundation item A1 and requires a real "
        "project and audience to validate against."
    )
