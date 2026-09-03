"""The opt-in local development path, and the refusals that fence it in.

``docker compose up`` needs a worker that a scheduler sidecar can actually
reach, and there is no OIDC issuer on a developer's laptop to mint the
credential :class:`~smartmatch_worker.identity.OidcTaskVerifier` wants. So the
worker grew a second, explicitly opt-in credential path:
:class:`~smartmatch_worker.identity.LocalBearerTaskVerifier`, composed only
when :class:`~smartmatch_worker.config.WorkerSettings` says so.

**Adding a bearer token to a service whose entire posture is "refuse when
unconfigured" is the single most dangerous change on this surface**, and it is
the reason this file exists. Security finding S-001 was resolved by
``build_task_verifier`` returning a verifier that refuses every request when
nothing is configured, and the shipped default must be exactly as closed after
this path exists as it was before it. Cloud Tasks' and Cloud Scheduler's real
OIDC identities remain open F5/S-001 deployment work; nothing here implements
either, and nothing here may make either easier to skip.

The fence is not in the verifier — that class compares one string and says so
in its own docstring. The fence is in ``WorkerSettings``, at boot, and it is
made of refusals:

* the tokens are refused outside ``edition="dev"``, so the mechanism cannot be
  carried into a real deployment by an environment variable;
* a blank token is refused, so "configured" cannot degrade into "accepts an
  empty credential";
* the task and scheduler tokens are refused when equal, so a caller holding
  one cannot exercise the other's endpoint — the local restatement of the
  separate-audiences rule the OIDC path keeps;
* the local queue is refused without both a token and a validated loopback
  target, so a half-configured deployment never boots;
* a target that is not plain ``http`` to a loopback literal at exactly
  ``/tasks/execute`` is refused, so a credentialed ``POST`` cannot be aimed
  anywhere but this machine.

Each of those is a boot-time ``ValueError``, deliberately, rather than a
setting that is ignored or defaulted: a process that does not start is a
failure an operator sees, and a process that quietly ignored a token is one
they do not.

Every case below constructs ``WorkerSettings`` directly with keyword
arguments rather than through the environment, so these assertions are about
the model's own rules and cannot be perturbed by the machine the suite runs
on — the same discipline ``create_app``'s injectable collaborators exist to
serve.
"""

from __future__ import annotations

import re

import pytest
from pydantic import SecretStr, ValidationError
from smartmatch_worker.config import WorkerSettings, validate_local_task_target_url
from smartmatch_worker.identity import (
    LocalBearerTaskVerifier,
    TaskIdentityError,
    UnconfiguredTaskVerifier,
    build_task_verifier,
)

#: A valid loopback target, used wherever a test needs the URL to be the part
#: that is *not* under examination.
GOOD_TARGET = "http://127.0.0.1:8080/tasks/execute"


def _settings(**overrides: object) -> WorkerSettings:
    """Build settings with the local path on and every rule satisfied.

    ``_env_file=None`` matters: ``WorkerSettings`` declares ``env_file=".env"``,
    and a developer's own ``.env`` sitting in the checkout would otherwise
    supply values these tests did not choose — which is the one way a test
    about refusals could pass for a reason that has nothing to do with the
    rule under test.
    """
    base: dict[str, object] = {
        "edition": "dev",
        "dev_task_bearer_token": SecretStr("compose-task"),
        "dev_scheduler_bearer_token": SecretStr("compose-sched"),
        "local_task_queue_enabled": True,
        "local_task_target_url": GOOD_TARGET,
        "_env_file": None,
    }
    base.update(overrides)
    return WorkerSettings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The shipped default is unchanged — this is the S-001 property
# ---------------------------------------------------------------------------


def test_nothing_configured_still_refuses_everything() -> None:
    """The default posture after this feature must equal the default before it.

    Not a formality. The whole risk of adding a bearer path is that it becomes
    reachable without anyone opting in, and the observable form of "nobody
    opted in" is this: no token, no queue, no target, and a verifier that is
    the unconfigured one rather than a permissive one.
    """
    settings = WorkerSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.dev_task_bearer_token is None
    assert settings.dev_scheduler_bearer_token is None
    assert settings.local_task_queue_enabled is False
    assert settings.local_task_target_url is None

    verifier = build_task_verifier(
        expected_audience=settings.task_audience,
        allowed_service_accounts=settings.allowed_service_accounts,
    )
    assert isinstance(verifier, UnconfiguredTaskVerifier)


def test_build_task_verifier_never_returns_the_local_verifier() -> None:
    """The OIDC builder has not learned about the local path, and must not.

    ``build_task_verifier`` is what an unconfigured deployment reaches. If it
    could ever hand back a :class:`LocalBearerTaskVerifier`, the opt-in would
    stop being an opt-in. Composition of the local verifier belongs in
    ``main``'s lifespan, gated on the setting, and nowhere else.
    """
    verifier = build_task_verifier(
        expected_audience="https://worker.invalid",
        allowed_service_accounts=frozenset({"dispatcher@example.invalid"}),
    )
    assert not isinstance(verifier, LocalBearerTaskVerifier)


# ---------------------------------------------------------------------------
# edition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edition", ["staging", "classroom", "production"])
def test_a_dev_token_is_refused_outside_the_dev_edition(edition: str) -> None:
    """Refused at boot, not ignored at runtime.

    An ignored setting is indistinguishable, from outside, from one that was
    honored — so a deployment that shipped a token into staging would look
    exactly like one that did not. Failing to start is the only outcome that
    tells someone.
    """
    with pytest.raises(ValidationError, match="refused outside edition=dev"):
        _settings(edition=edition, local_task_queue_enabled=False, local_task_target_url=None)


@pytest.mark.parametrize(
    "field",
    ["dev_task_bearer_token", "dev_scheduler_bearer_token"],
)
def test_either_token_alone_is_enough_to_trigger_the_edition_refusal(field: str) -> None:
    """Both tokens are fenced, not just the one a reader thinks of first.

    Parametrized because the rule is a disjunction over two fields, and a test
    of one branch says nothing about the other — the scheduler token is the
    easier one to forget, since it is the one that does not reach
    ``/tasks/execute``.
    """
    overrides: dict[str, object] = {
        "edition": "production",
        "dev_task_bearer_token": None,
        "dev_scheduler_bearer_token": None,
        "local_task_queue_enabled": False,
        "local_task_target_url": None,
        field: SecretStr("compose-any"),
    }
    with pytest.raises(ValidationError, match="refused outside edition=dev"):
        _settings(**overrides)


# ---------------------------------------------------------------------------
# Token shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_task_token_is_refused(blank: str) -> None:
    """Whitespace is not a credential.

    ``None`` means "this path is off" and is a legal, safe value. A blank
    string is different: it says the path is on and then supplies nothing to
    check, which would make the endpoint reachable by any caller sending an
    empty bearer credential.
    """
    with pytest.raises(ValidationError, match="must not be blank"):
        _settings(dev_task_bearer_token=SecretStr(blank))


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_scheduler_token_is_refused(blank: str) -> None:
    """The same rule on the scheduler credential, asserted separately."""
    with pytest.raises(ValidationError, match="must not be blank"):
        _settings(dev_scheduler_bearer_token=SecretStr(blank))


def test_the_two_tokens_must_differ() -> None:
    """One shared token would collapse two deliberately separate callers into one.

    The OIDC path keeps Cloud Tasks and Cloud Scheduler apart with separate
    audiences and separate allowlists, and ``config``'s own docstring says why:
    granting the queue permission to deliver a task must not also grant it
    permission to drive dispatch. Equal local tokens would undo exactly that,
    locally, which is where the developer's mental model of the system is
    formed.
    """
    same = SecretStr("compose-same")
    with pytest.raises(ValidationError, match="must differ"):
        _settings(dev_task_bearer_token=same, dev_scheduler_bearer_token=same)


# ---------------------------------------------------------------------------
# Partial local-queue configuration
# ---------------------------------------------------------------------------


def test_the_queue_cannot_be_enabled_without_a_task_token() -> None:
    """The pump needs a credential to present; there is no anonymous delivery."""
    with pytest.raises(ValidationError, match=r"requires\s+SMARTMATCH_DEV_TASK_BEARER_TOKEN"):
        _settings(dev_task_bearer_token=None)


def test_the_queue_cannot_be_enabled_without_a_target() -> None:
    """A pump with nowhere to deliver is refused rather than defaulted.

    Guessing a target would be this module choosing where a credentialed
    ``POST`` goes, which is the one decision it must never make on an
    operator's behalf.
    """
    with pytest.raises(ValidationError, match=r"requires\s+SMARTMATCH_LOCAL_TASK_TARGET_URL"):
        _settings(local_task_target_url=None)


def test_a_target_without_the_queue_enabled_is_contradictory_and_refused() -> None:
    """The inverse half, which a "required field" check alone would not catch.

    A target set while the queue is off is not a harmlessly unused value: it
    is a configuration whose author plainly believed delivery was on. Booting
    anyway would leave them with a worker that silently never delivers.
    """
    with pytest.raises(ValidationError, match="contradictory configuration"):
        _settings(local_task_queue_enabled=False)


def test_the_fully_configured_local_path_is_accepted() -> None:
    """The permitted shape, which is what catches an over-tight validator.

    A rule set that refused everything would pass every refusal test above and
    still be broken. This is the case that says the feature can actually be
    turned on.
    """
    settings = _settings()

    assert settings.local_task_queue_enabled is True
    assert settings.local_task_target_url == GOOD_TARGET
    assert settings.dev_task_bearer_token is not None
    assert settings.dev_scheduler_bearer_token is not None


# ---------------------------------------------------------------------------
# The delivery target
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://127.0.0.1:8080/tasks/execute", "plain http"),
        ("http://worker:8080/tasks/execute", "127.0.0.1 or ::1"),
        ("http://169.254.169.254/tasks/execute", "127.0.0.1 or ::1"),
        ("http://localhost:8080/tasks/execute", "127.0.0.1 or ::1"),
        ("http://127.0.0.1:8080/tasks/execute/../admin", "path must be exactly"),
        ("http://127.0.0.1:8080/", "path must be exactly"),
        ("http://user:pw@127.0.0.1:8080/tasks/execute", "userinfo"),
        ("http://127.0.0.1:8080/tasks/execute?to=elsewhere", "query string"),
        ("http://127.0.0.1:8080/tasks/execute#frag", "fragment"),
        # A port outside the valid range, and a non-numeric one. `urlsplit`
        # parses the port lazily, so neither is refused by any check that
        # only reads `hostname` and `path` — both used to pass boot
        # validation and then raise inside the delivery pump on every poll,
        # turning a configuration error into a permanent, recurring runtime
        # failure. See `validate_local_task_target_url`.
        ("http://127.0.0.1:65536/tasks/execute", "unusable port"),
        ("http://127.0.0.1:notaport/tasks/execute", "unusable port"),
        # Port 0 parses cleanly and is then read as 80 by `parsed.port or 80`
        # at the delivery site, which would send a credentialed POST to a
        # port nobody wrote.
        ("http://127.0.0.1:0/tasks/execute", "must not name port 0"),
    ],
)
def test_a_target_that_is_not_exactly_loopback_tasks_execute_is_refused(
    url: str, reason: str
) -> None:
    """Every clause of the target rule, each with its own case.

    The rule is six conditions and a test of one says nothing about the other
    five. Two entries deserve naming individually:

    ``http://localhost:8080/...`` is refused even though it usually resolves
    to loopback. "Usually" is the problem — ``localhost`` is a *name*, and
    what a name resolves to is decided by a resolver this process does not
    control, so a literal is the only form that means the same thing on every
    machine.

    ``http://169.254.169.254/...`` is the cloud metadata address, and it is
    here as the concrete thing a host allowlist exists to keep a credentialed
    ``POST`` away from.
    """
    with pytest.raises(ValueError, match=reason):
        validate_local_task_target_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/tasks/execute",
        "http://127.0.0.1/tasks/execute",
        "http://[::1]:8080/tasks/execute",
    ],
)
def test_the_permitted_targets_are_accepted(url: str) -> None:
    """Both loopback literals, with and without an explicit port."""
    validate_local_task_target_url(url)


def test_the_settings_validator_applies_the_target_rule_too() -> None:
    """The rule is enforced at boot, not only where ``local_tasks`` re-checks it.

    ``validate_local_task_target_url`` being correct is worth nothing if
    ``WorkerSettings`` never calls it — the failure would then surface as a
    connection error at delivery time, long after the operator stopped
    looking at the boot log.
    """
    with pytest.raises(ValidationError, match=re.escape("127.0.0.1 or ::1")):
        _settings(local_task_target_url="http://example.invalid/tasks/execute")


# ---------------------------------------------------------------------------
# LocalBearerTaskVerifier
# ---------------------------------------------------------------------------


def test_the_matching_token_is_accepted() -> None:
    """The permitted case, which is what catches a verifier that refuses everything."""
    verifier = LocalBearerTaskVerifier(token="compose-task", label="task")

    identity = verifier.verify("Bearer compose-task")

    assert identity is not None


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Bearer ",
        "Bearer wrong",
        "Bearer compose-task-",
        "Bearer COMPOSE-TASK",
        "compose-task",
        "Basic compose-task",
    ],
)
def test_every_other_credential_is_refused(authorization: str | None) -> None:
    """Absent, malformed, mis-scheme, near-miss, and wrong-case, all refused.

    ``"Bearer compose-task-"`` and ``"Bearer COMPOSE-TASK"`` are the ones
    worth having: a comparison that truncated, or that folded case, would
    accept both while passing a test that only tried an obviously wrong
    string.
    """
    verifier = LocalBearerTaskVerifier(token="compose-task", label="task")

    with pytest.raises(TaskIdentityError):
        verifier.verify(authorization)


def test_a_refusal_never_discloses_the_token() -> None:
    """The failure message names which credential failed and nothing else.

    An exception that echoed either the expected or the presented value would
    put a credential into whatever log or response body caught it — and the
    presented value is attacker-chosen, which makes echoing it a reflection
    bug on top of a disclosure one.
    """
    verifier = LocalBearerTaskVerifier(token="compose-task", label="scheduler")

    with pytest.raises(TaskIdentityError) as caught:
        verifier.verify("Bearer guessed-value")

    message = str(caught.value)
    assert "compose-task" not in message
    assert "guessed-value" not in message
    assert "scheduler" in message


def test_neither_token_opens_the_other_endpoint() -> None:
    """Cross-use is refused, which is the point of the two tokens differing.

    ``config`` refuses equal tokens at boot; this is the other half of that
    argument, at the verifier: given two different tokens, each verifier
    accepts only its own. Together they mean a caller holding the task
    credential genuinely cannot drive dispatch.
    """
    task_verifier = LocalBearerTaskVerifier(token="compose-task", label="task")
    scheduler_verifier = LocalBearerTaskVerifier(token="compose-sched", label="scheduler")

    assert task_verifier.verify("Bearer compose-task") is not None
    assert scheduler_verifier.verify("Bearer compose-sched") is not None

    with pytest.raises(TaskIdentityError):
        task_verifier.verify("Bearer compose-sched")
    with pytest.raises(TaskIdentityError):
        scheduler_verifier.verify("Bearer compose-task")
