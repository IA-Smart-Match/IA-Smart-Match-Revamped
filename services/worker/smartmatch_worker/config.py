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

## The local development path, and why it is not an exception either

Four more settings — ``dev_task_bearer_token``, ``dev_scheduler_bearer_token``,
``local_task_queue_enabled``, and ``local_task_target_url`` — let
``docker compose up`` exercise both worker HTTP boundaries without a real
Google Cloud project. This is **a developer appliance that emulates Cloud
Tasks and Cloud Scheduler locally, never their implementation**: Cloud
Scheduler's OIDC-authenticated trigger and Cloud Tasks' own delivery
guarantees remain open F5/S-001 deployment work, and nothing validated here
closes that finding. See :mod:`smartmatch_worker.local_tasks` and
:mod:`smartmatch_worker.local_scheduler` for what actually runs when these are
turned on, and :class:`~smartmatch_worker.identity.LocalBearerTaskVerifier`
for what accepts the tokens.

The same asymmetry governs them, sharpened rather than relaxed: every one of
these settings degrades towards *more* refusal, never towards *less*, and the
model validator below enforces every rule that follows by failing the whole
application's boot — not by falling back to something weaker — the moment a
deployment asks for a shape that cannot be honest:

* **Either bearer token, under any edition but ``dev``, fails startup.** Not
  "is ignored". A token that skips the OIDC check is a control this platform
  cannot let a real deployment inherit by copy-pasting a compose file's
  environment block; refusing to boot is the only way "someone forgot to
  strip this" cannot become "someone shipped this".
* **The two tokens must be nonblank and must differ.** One token accepted on
  both endpoints would let a caller holding only task credentials drive
  dispatch, and vice versa — exactly the cross-use ``task_audience`` and
  ``scheduler_audience`` being separate settings exists to refuse in
  production. A blank token is worse than none:
  :class:`~smartmatch_worker.identity.LocalBearerTaskVerifier` compares with
  :func:`hmac.compare_digest`, and an empty stored credential is trivially
  presentable by an unauthenticated caller who simply sends
  ``Authorization: Bearer`` with nothing after it.
* **Enabling the local queue without a task token or a target URL fails
  startup.** The delivery pump has no credential to present to
  ``/tasks/execute`` and nowhere to send it; a deployment that turned the
  queue on and left either blank gets a boot failure naming which one, not a
  pump that silently never delivers anything.
* **A target URL supplied while the queue is disabled fails startup too**,
  as contradictory configuration rather than a harmless unused value — a
  deployment that sets a delivery target and forgets to flip the flag most
  likely believes local dispatch is running when it is not, and that belief
  is the thing worth failing loudly over.
* **The target must be exactly** ``http://127.0.0.1/tasks/execute`` **or**
  ``http://[::1]/tasks/execute`` **(any port), with no userinfo, query, or
  fragment** — see :func:`validate_local_task_target_url`. Not a setting a
  caller, a payload, or a tenant can steer: it is validated once, at boot,
  against a fixed shape, and the queue itself never re-reads it from
  anything but its own construction argument.

Poll and schedule intervals for the local pump and the scheduler sidecar are
**not** settings here, on purpose, matching ``dispatch_batch_size``'s siblings
above in spirit but not in kind: those tune a real deployment's throughput and
carry a working default *because* getting them wrong only costs latency. A
poll interval for a component that exists to prove a security boundary works
is different — an environment-tunable interval is one more thing a compose
file could get wrong in a way that looks like the boundary working when it is
not. They are argued code constants in :mod:`smartmatch_worker.local_tasks`
and :mod:`smartmatch_worker.local_scheduler` instead.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Final
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from smartmatch_persistence.jobs import DEFAULT_JOB_LEASE
from smartmatch_persistence.spend import SpendCeilings

__all__ = ["WorkerSettings", "get_settings", "validate_local_task_target_url"]

#: The only path a local delivery may target — this worker's own task
#: endpoint. Fixed here, never accepted from the environment: a setting that
#: could name any path would let a compose file quietly repoint local
#: dispatch at something other than the boundary it is meant to exercise.
_LOCAL_TASK_TARGET_PATH: Final[str] = "/tasks/execute"

#: Loopback address **literals** only — not ``localhost``, which is a name
#: whose resolution depends on this container's ``/etc/hosts`` or resolver
#: rather than on anything this validator can see. A literal cannot be
#: repointed by changing what a name resolves to; a name can.
_LOCAL_TASK_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1"})


def validate_local_task_target_url(url: str) -> None:
    """Raise unless ``url`` is exactly the shape a local delivery may target.

    Shared between :class:`WorkerSettings`, which calls this at boot so a bad
    value fails startup rather than surfacing as a mysterious connection
    failure later, and :mod:`smartmatch_worker.local_tasks`, which calls it
    again at construction — the same "assert the invariant again at the next
    boundary" discipline :mod:`smartmatch_worker.identity` uses throughout,
    rather than trusting that nothing between the two call sites could change
    the value.

    Args:
        url: The candidate ``SMARTMATCH_LOCAL_TASK_TARGET_URL``.

    Raises:
        ValueError: if the scheme is not plain ``http``, the host is not
            ``127.0.0.1`` or ``::1``, the path is not exactly
            :data:`_LOCAL_TASK_TARGET_PATH`, or the URL carries userinfo, a
            query string, or a fragment.
    """
    parsed = urlsplit(url)
    if parsed.scheme != "http":
        raise ValueError(
            "SMARTMATCH_LOCAL_TASK_TARGET_URL must use plain http (never https, "
            f"which would need a certificate nothing here manages), not {parsed.scheme!r}"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("SMARTMATCH_LOCAL_TASK_TARGET_URL must not carry userinfo")
    if parsed.hostname not in _LOCAL_TASK_LOOPBACK_HOSTS:
        raise ValueError(
            "SMARTMATCH_LOCAL_TASK_TARGET_URL must address 127.0.0.1 or ::1 "
            f"(a literal, never a resolvable name), not {parsed.hostname!r}"
        )
    if parsed.path != _LOCAL_TASK_TARGET_PATH:
        raise ValueError(
            f"SMARTMATCH_LOCAL_TASK_TARGET_URL path must be exactly "
            f"{_LOCAL_TASK_TARGET_PATH!r}, not {parsed.path!r}"
        )
    if parsed.query:
        raise ValueError("SMARTMATCH_LOCAL_TASK_TARGET_URL must not carry a query string")
    if parsed.fragment:
        raise ValueError("SMARTMATCH_LOCAL_TASK_TARGET_URL must not carry a fragment")

    # The port, last, and checked here rather than left to the delivery site
    # for the reason this whole function exists: a bad value must fail the
    # boot, not the delivery.
    #
    # ``urlsplit`` does not validate the port. It parses it lazily, and
    # ``parsed.port`` raises ``ValueError`` only when something actually
    # reads the attribute. Every check above reads ``scheme``, ``username``,
    # ``hostname``, ``path``, ``query`` and ``fragment``, and none of them
    # touches ``port`` — so ``http://127.0.0.1:65536/tasks/execute``, or one
    # with a non-numeric port, used to pass this function intact and then
    # raise inside ``LocalTaskDeliveryPump._post`` on every single poll: a
    # permanent delivery failure surfacing as a recurring exception rather
    # than as the configuration error it is.
    #
    # Reading the attribute inside ``try`` *is* the check. The parse is the
    # validation, so there is no second rule here that could drift out of
    # step with what the delivery site will later accept.
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"SMARTMATCH_LOCAL_TASK_TARGET_URL has an unusable port: {exc}") from exc

    # ``None`` means the URL named no port, which is legal and means the
    # scheme default. An explicitly written ``:0`` is not: it parses cleanly
    # and then ``parsed.port or 80`` at the delivery site reads it as 80, so
    # a credentialed POST would go to a port nobody wrote.
    if port == 0:
        raise ValueError(
            "SMARTMATCH_LOCAL_TASK_TARGET_URL must not name port 0; omit the port to use "
            "the default rather than writing one that silently resolves to a different port"
        )


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

    #: A bearer token this deployment accepts on ``/tasks/execute`` in place of
    #: a verified Cloud Tasks OIDC identity. **No default, and refused outside
    #: ``edition=dev``** — see the module docstring's "local development path"
    #: section and :class:`~smartmatch_worker.identity.LocalBearerTaskVerifier`.
    #: This is a ``docker compose`` convenience, never a second production
    #: control: when it is unset, nothing here changes and
    #: :func:`~smartmatch_worker.identity.build_task_verifier` runs exactly as
    #: it always has.
    dev_task_bearer_token: SecretStr | None = Field(
        default=None,
        description="Dev-only bearer token accepted on /tasks/execute in place of OIDC",
    )

    #: A bearer token accepted on ``/operations/dispatch`` in place of a
    #: verified Cloud Scheduler OIDC identity. Kept as its own setting rather
    #: than reusing ``dev_task_bearer_token``, for the same reason
    #: ``scheduler_audience`` is its own OIDC setting above: one token would
    #: let whichever caller holds it reach both endpoints, which is precisely
    #: the cross-use the real audiences — and this setting's own validator —
    #: exist to refuse.
    dev_scheduler_bearer_token: SecretStr | None = Field(
        default=None,
        description="Dev-only bearer token accepted on /operations/dispatch in place of OIDC",
    )

    #: Whether this process composes
    #: :class:`~smartmatch_worker.local_tasks.LocalPostgresHttpTaskQueue` and
    #: its delivery pump at startup. **Off by default**, for the same reason
    #: nothing in this module defaults towards access: with this unset,
    #: ``app.state.task_queue`` stays ``None`` and ``/operations/dispatch``
    #: keeps answering ``501`` exactly as it does today — see ``main``'s
    #: module docstring for why that refusal, and never ``FixtureTaskQueue``,
    #: is the only honest default for an unconfigured task queue.
    local_task_queue_enabled: bool = Field(
        default=False,
        description="Compose the local Postgres/HTTP loopback task queue at startup",
    )

    #: Where the local delivery pump ``POST``s a claimed task. **No default**;
    #: enabling the queue without it fails startup rather than guessing a
    #: target. Must satisfy :func:`validate_local_task_target_url`.
    local_task_target_url: str | None = Field(
        default=None,
        description="Loopback http://…/tasks/execute the local delivery pump delivers to",
    )

    @model_validator(mode="after")
    def _validate_local_dev_mode(self) -> WorkerSettings:
        """Enforce every rule the local development path must satisfy at boot.

        Raising here — inside a ``pydantic`` validator — means a deployment
        with an inconsistent local-mode configuration never produces a running
        process at all: not one that starts and silently misbehaves, and not
        one an operator has to notice is wrong from its behavior rather than
        from its refusal to boot. See the module docstring's "local
        development path" section for why each rule below exists; this method
        is only the enforcement, not the argument.
        """
        task_token = self.dev_task_bearer_token
        scheduler_token = self.dev_scheduler_bearer_token

        if (task_token is not None or scheduler_token is not None) and self.edition != "dev":
            raise ValueError(
                "SMARTMATCH_DEV_TASK_BEARER_TOKEN and SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN "
                f"are refused outside edition=dev (this deployment is {self.edition!r}); a "
                "bearer token that bypasses the OIDC check must never reach a real edition"
            )

        if task_token is not None and not task_token.get_secret_value().strip():
            raise ValueError("SMARTMATCH_DEV_TASK_BEARER_TOKEN must not be blank")
        if scheduler_token is not None and not scheduler_token.get_secret_value().strip():
            raise ValueError("SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN must not be blank")
        if (
            task_token is not None
            and scheduler_token is not None
            and task_token.get_secret_value() == scheduler_token.get_secret_value()
        ):
            raise ValueError(
                "SMARTMATCH_DEV_TASK_BEARER_TOKEN and SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN "
                "must differ; one token accepted on both endpoints would let a caller "
                "holding only task credentials drive dispatch, and vice versa"
            )

        if self.local_task_queue_enabled:
            if task_token is None:
                raise ValueError(
                    "SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED requires "
                    "SMARTMATCH_DEV_TASK_BEARER_TOKEN; the local delivery pump has no "
                    "credential to present to /tasks/execute without one"
                )
            if not self.local_task_target_url:
                raise ValueError(
                    "SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED requires "
                    "SMARTMATCH_LOCAL_TASK_TARGET_URL; the delivery pump has nowhere to "
                    "deliver a claimed task"
                )
            validate_local_task_target_url(self.local_task_target_url)
        elif self.local_task_target_url:
            raise ValueError(
                "SMARTMATCH_LOCAL_TASK_TARGET_URL is set but "
                "SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED is not; a delivery target with "
                "nothing enabled to deliver to it is contradictory configuration, not "
                "a harmlessly unused value"
            )

        return self

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

    # --- Outreach (R4, gate G4) --------------------------------------------
    #
    # Four settings, and what matters about them is which way each one fails
    # when it is unset. The rule throughout is that omission produces the
    # fixture path, never a live one: a deployment acquires the ability to email
    # a real person by naming every part of what that involves, and never by
    # leaving something out.

    #: The institutional From address. **No default that could reach a
    #: mailbox**: ``example.invalid`` is RFC 2606 reserved and cannot resolve,
    #: so a deployment that forgets to set this fails to deliver rather than
    #: sending as somebody nobody chose. Choosing the real one is an
    #: institutional identity claim — see OQ-001.
    outreach_from_address: str = Field(
        default="noreply@example.invalid",
        description="From address for outreach; the default is deliberately undeliverable",
    )

    #: Origin the unsubscribe URLs in every message are built against. The local
    #: default matches the compose appliance; a deployment that leaves it wrong
    #: sends links that 404, which is visible, rather than links that silently
    #: unsubscribe nothing.
    outreach_public_base_url: str = Field(
        default="http://localhost:8080",
        description="Public origin for List-Unsubscribe URLs",
    )

    #: HMAC key for unsubscribe tokens. ``None`` is permitted only because the
    #: fixture path falls back to a named, obviously-synthetic constant;
    #: ``build_outreach_send_handler`` refuses that fallback in live mode and
    #: fails at boot rather than minting forgeable links. See OQ-005.
    outreach_unsubscribe_secret: SecretStr | None = Field(
        default=None,
        description="HMAC key for unsubscribe tokens; required for live sends",
    )

    #: Live email credential. **Absent everywhere in this repository.** Its
    #: presence is what makes ``build_email_provider`` attempt a live client,
    #: which today is still a named refusal — the live adapter is OQ-002.
    email_api_key: SecretStr | None = Field(
        default=None,
        description="Live email provider credential; absent in every current environment",
    )

    @property
    def outreach_live_mode(self) -> bool:
        """Whether this deployment could reach a real mailbox.

        True only when a credential is present *and* the edition is one that may
        hold one. Written as a conjunction rather than as "not classroom" so
        that a new fixture-only edition added later is live by nobody's
        oversight: the credential is the positive signal, and there is no
        environment in which its absence means anything but fixture mode.
        """
        return self.email_api_key is not None and self.edition not in {"classroom", "dev"}

    #: Included in the health response so a deployment can be identified without
    #: exposing topology.
    release: str = Field(default="dev", description="Release identifier")

    @property
    def allowed_service_accounts(self) -> frozenset[str]:
        """The allowlist, parsed. Empty when unset, which means "refuse everyone"."""
        return frozenset(
            entry.strip() for entry in self.task_service_accounts.split(",") if entry.strip()
        )

    #: Which edition is running. Consulted only when building providers, and
    #: recorded in a provider refusal so an operator can see which deployment
    #: asked. ``dev`` by default because the safe outcome must be what a
    #: deployment gets by writing nothing.
    edition: str = Field(
        default="dev",
        description="Platform edition: dev, staging, classroom, or production",
    )

    #: Per-job spend ceiling, as a decimal string (ADR-0015 A1). **No default,
    #: and the absence is the control.** A worker only routes
    #: ``extraction.paid_pages`` when all three ceilings are set, so a
    #: deployment acquires the ability to spend money by naming the numbers it
    #: is accountable for — never by omission. A1 is explicit that until A3 is
    #: confirmed against the actual provider, every ceiling computed from it is
    #: provisional, so no figure here can be shipped as a default.
    #:
    #: Strings rather than ``Decimal``: an environment variable is a string,
    #: and parsing it here keeps the float that ``Decimal(0.1)`` would smuggle
    #: in out of a money path entirely.
    spend_ceiling_job: str | None = Field(
        default=None,
        description="Per-job spend ceiling, e.g. '2.00'. Required to enable paid extraction.",
    )

    #: Per-tenant-per-day spend ceiling, as a decimal string (G3 §4).
    spend_ceiling_tenant_day: str | None = Field(
        default=None,
        description="Per-tenant-per-day spend ceiling, e.g. '25.00'.",
    )

    #: Per-tenant-per-month spend ceiling, as a decimal string (G3 §4).
    spend_ceiling_tenant_month: str | None = Field(
        default=None,
        description="Per-tenant-per-month spend ceiling, e.g. '250.00'.",
    )

    @property
    def spend_ceilings(self) -> SpendCeilings | None:
        """The three ceilings, or ``None`` when the deployment has not set all three.

        All-or-nothing on purpose. A partially configured set would leave one
        ceiling defaulted by this module rather than chosen by whoever answers
        for the spend, which is the one thing ADR-0015 A1 says must not happen.
        Returning ``None`` is what keeps the paid command unrouted, so an
        incomplete configuration produces a worker that cannot spend rather
        than one that spends against a number nobody picked.

        Raises:
            ValueError: when a ceiling is set but is not a usable decimal, so a
                typo fails the boot loudly instead of resolving to a silent
                zero. ``SpendCeilings`` itself refuses a negative.
        """
        raw = (
            self.spend_ceiling_job,
            self.spend_ceiling_tenant_day,
            self.spend_ceiling_tenant_month,
        )
        if any(value is None for value in raw):
            return None

        parsed: list[Decimal] = []
        for name, value in zip(
            ("spend_ceiling_job", "spend_ceiling_tenant_day", "spend_ceiling_tenant_month"),
            raw,
            strict=True,
        ):
            try:
                parsed.append(Decimal(str(value)))
            except InvalidOperation as exc:
                raise ValueError(f"{name} is not a valid decimal: {value!r}") from exc

        return SpendCeilings(job=parsed[0], tenant_day=parsed[1], tenant_month=parsed[2])

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
