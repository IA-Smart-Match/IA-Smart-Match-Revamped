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
from typing import Final

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from smartmatch_domain.exercise.workspace_token import MINIMUM_WORKSPACE_SECRET_LENGTH
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

    #: ADR-0017's offline, in-process embedding model for customer §9's Topic
    #: comparison. A deployment-level opt-in, not a user preference: nothing on
    #: a request or a principal can flip this, because a stored score's
    #: ``cba_semantic_topic.basis`` records which engine produced it and two
    #: shortlists in the same unit must have been produced by the same one, or
    #: the record must at least be honest about which was which per run — that
    #: is only true if the choice is a deployment fact, not something that can
    #: change between two runs a coordinator submits back to back.
    #:
    #: Off by default so an unconfigured deployment keeps exactly today's
    #: behaviour: ``FixtureSemanticTopicProvider``, the same golden pins, the
    #: same CI. Turning this on does not add a vendor, a credential, or a
    #: network call — ``LocalEmbeddingSemanticTopicProvider`` is a vendored,
    #: offline model (ADR-0017) — so nothing else in the isolation gate's
    #: "no live providers" property is at stake here.
    cba_topic_local_embedding_enabled: bool = False

    #: Local-pilot bearer tokens mapped to their stable external subjects.
    #:
    #: This is intentionally not an account-authentication system: it has no
    #: password, expiry, or revocation. It exists only to make a local fixture
    #: verifier accept a finite, explicitly configured set of test principals.
    #: It must never be present outside development.
    dev_principals: dict[str, str] = Field(default_factory=dict)

    email_api_key: str | None = None
    routes_api_key: str | None = None

    #: Origin the *speaker-response* links in an invitation are built against,
    #: and the same environment variable the worker reads for its unsubscribe
    #: links (``SMARTMATCH_OUTREACH_PUBLIC_BASE_URL``). One name deliberately:
    #: the two links appear in the same message, and a deployment that
    #: configured one and not the other would send a mail whose links point at
    #: different hosts.
    #:
    #: It is read here rather than taken from a request body because a caller
    #: supplying it would be a caller putting an arbitrary link into an
    #: institutional email over an already-consented address — a phishing
    #: primitive rather than a parameter. The local default matches the compose
    #: appliance; a deployment that leaves it wrong sends links that 404, which
    #: is visible, rather than links that silently record nothing.
    #:
    #: No credential and no live-service default, so this does not widen what an
    #: unconfigured deployment can reach: it changes the text of a message the
    #: fixture provider prints and nothing else.
    outreach_public_base_url: str = Field(
        default="http://localhost:8080",
        description="Public origin for invitation response URLs",
    )

    #: The HMAC key the class exercise derives its workspace cookie tokens from
    #: (design spec §15; OQ-CE-08, closed 2026-09-25). Read from
    #: ``SMARTMATCH_EXERCISE_WORKSPACE_SECRET``.
    #:
    #: ``None`` by default and required *only* in
    #: ``ProductScope.CLASS_EXERCISE``. A CBA or legacy deployment has no
    #: exercise routes, derives no workspace token, and must not be made to
    #: carry a secret it has no use for — a required variable nobody needs is a
    #: variable that gets set to ``"changeme"`` in every environment that does
    #: need it.
    #:
    #: Checked by :func:`require_exercise_workspace_secret`, which
    #: ``smartmatch_api.main`` calls at import when the exercise capability is
    #: enabled, so a process in that scope with no secret does not boot. It is
    #: deliberately *not* a ``model_validator`` rule: ``Settings`` is
    #: constructed with ``product_scope=class_exercise`` by several tests that
    #: are asking which routes that scope mounts, and a construction-time raise
    #: would make "which routes" unanswerable without a secret in the
    #: environment.
    #:
    #: Never logged and never returned by any route. It is not a credential for
    #: a person — the exercise has no login — but it is what stops a workspace
    #: id from being a workspace token, which is the whole of the cookie's
    #: strength.
    exercise_workspace_secret: SecretStr | None = None

    #: The class exercise's instructor passcode (design spec §14). Read from
    #: ``SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE``.
    #:
    #: OQ-CE-07 (closed 2026-09-25): one environment variable, set per
    #: deployment, shared out of band, and rotated by changing the value.
    #:
    #: ``None`` — the default — means **the instructor page cannot be entered**.
    #: It is deliberately not part of the boot guard that
    #: :func:`require_exercise_workspace_secret` implements: the exercise's
    #: team-facing routes are the product and they work without an instructor
    #: page, so a missing passcode must not take a classroom down. What it must
    #: never do is open the door, which is why the login refuses every attempt
    #: rather than skipping the check — see
    #: ``exercise_dependencies.get_instructor_passcode``.
    #:
    #: A :class:`~pydantic.SecretStr`, so ``repr(settings)`` and
    #: ``settings.model_dump()`` — the two shapes that reach a debugger and a
    #: crash report without anybody deciding they should — print a mask. Never
    #: logged and never returned by any route.
    exercise_instructor_passcode: SecretStr | None = None

    #: The Speaker portal activation-token secret (B26 T6b-1 plan §4.1). Read
    #: from ``SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET``; the worker must hold the
    #: same value. Read only when ``Capability.SPEAKER_PORTAL`` is on, and then
    #: required (:func:`check_speaker_portal_startup`). No synthetic fallback:
    #: a forgeable activation link lets someone else take over the account.
    speaker_portal_token_secret: SecretStr | None = None

    #: Whether the class exercise's workspace cookie carries ``Secure``.
    #: Read from ``SMARTMATCH_EXERCISE_COOKIE_SECURE``.
    #:
    #: ``None`` — the default — means "follow the edition": off in ``dev``, on
    #: everywhere else. That rule is a *guess* and is documented as one, because
    #: ``edition`` does not answer "is this served over TLS". The pilot VM is
    #: reached over HTTPS while its compose file pins
    #: ``SMARTMATCH_EDITION=dev``, which is precisely the deployment where the
    #: guess is wrong and the classroom's cookie would go over the wire without
    #: ``Secure``.
    #:
    #: So the deployment can say. ``true`` on any TLS host — set it on the VM —
    #: and ``false`` only where the site is genuinely served over ``http``,
    #: since a ``Secure`` cookie is simply not stored over plain HTTP and
    #: pinning it on would break local development rather than protect it.
    exercise_cookie_secure: bool | None = None

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


def require_exercise_workspace_secret(settings: Settings) -> str:
    """The exercise's workspace secret, or refuse to let the process run.

    Called once, at application import, when ``Capability.CLASS_EXERCISE`` is
    enabled. A class-exercise deployment that boots without this secret has two
    possible behaviours and both are worse than not booting: derive tokens from
    an empty key, in which case a workspace id *is* a workspace token, or fall
    back to random per-entry tokens, in which case the second laptop on a team
    silently knocks the first off its own saved runs (OQ-CE-08). Failing at
    startup is the only honest third option.

    Args:
        settings: The process's settings.

    Returns:
        The secret, unwrapped, for the scope that needs it. It is stored as a
        :class:`~pydantic.SecretStr` so that ``repr(settings)`` and
        ``settings.model_dump()`` — the two shapes that reach a debugger, a
        crash report and a log line without anybody deciding they should —
        print ``**********`` instead of the HMAC key. Unwrapping happens here,
        at the one call that needs the bytes.

    Raises:
        ValueError: if the scope needs a secret and none is configured, or the
            configured one is shorter than
            :data:`~smartmatch_domain.exercise.workspace_token.MINIMUM_WORKSPACE_SECRET_LENGTH`.
            The message names the variable and the length and quotes no part of
            the value.
    """
    stored = settings.exercise_workspace_secret
    secret = stored.get_secret_value() if stored is not None else None
    if secret is None or not secret.strip():
        raise ValueError(
            "SMARTMATCH_EXERCISE_WORKSPACE_SECRET is required when "
            "SMARTMATCH_PRODUCT_SCOPE=class_exercise; it is the key the team "
            "workspace cookie is derived from. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(32))'`."
        )
    if len(secret) < MINIMUM_WORKSPACE_SECRET_LENGTH:
        raise ValueError(
            "SMARTMATCH_EXERCISE_WORKSPACE_SECRET must be at least "
            f"{MINIMUM_WORKSPACE_SECRET_LENGTH} characters; the configured "
            "value is shorter. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(32))'`."
        )
    return secret


#: The shortest Speaker portal token secret a process will boot with.
MINIMUM_SPEAKER_PORTAL_SECRET_LENGTH: Final[int] = 32


def check_speaker_portal_startup(settings: Settings) -> str | None:
    """The Speaker portal token secret when the capability is on; ``None`` when off.

    Off: returns ``None`` without reading the secret. On: returns the unwrapped
    secret, or raises when it is missing, blank or shorter than
    :data:`MINIMUM_SPEAKER_PORTAL_SECRET_LENGTH` (plan §4.2, R10).

    Raises:
        ValueError: naming the variable and the minimum length, quoting no
            part of the value.
    """
    if not settings.capability_enabled(Capability.SPEAKER_PORTAL):
        return None
    stored = settings.speaker_portal_token_secret
    secret = stored.get_secret_value() if stored is not None else None
    if secret is None or not secret.strip() or len(secret) < MINIMUM_SPEAKER_PORTAL_SECRET_LENGTH:
        raise ValueError(
            "SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET is required, at least "
            f"{MINIMUM_SPEAKER_PORTAL_SECRET_LENGTH} characters, when the speaker_portal "
            "capability is on; the api and the worker must hold the same value. Generate "
            "one with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
        )
    return secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, validated once at first use."""
    return Settings()
