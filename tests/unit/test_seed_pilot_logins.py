"""Unit coverage for the pilot-login seed's role assignment.

What is worth pinning here is not that the tool writes rows — ``seed_pilot``
owns that and ``tests/unit/test_seed_pilot.py`` covers it — but *which* roles
each login is given, because that is the whole content of the decision this
file encodes: ``coordinator`` and ``admin`` are one persona landing in one
shell, so both connector logins hold both memberships and are the same thing
to the product.

The rest is the behaviour that must survive that change: the tool still
refuses a half-configured pair, still refuses a short password, still invents
nothing for an unconfigured role, and still never carries a password into
anything it prints.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from smartmatch_domain.pilot_credentials import MINIMUM_PASSWORD_LENGTH

# `tools/` rather than the repository root, and for the reason
# `test_compose_dev_principals.py` gives: these operator scripts import each
# other by bare module name (`seed_pilot_logins` does `from seed_pilot import
# ...`), because they run as scripts and not as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import seed_pilot_logins

#: Long enough to pass the minimum-length check and obviously synthetic. Not a
#: credential: nothing reads it but the fake below.
_USABLE_SECRET = "not-a-real-password-000"

_SEED_KWARGS = {
    "tenant_slug": "pilot",
    "tenant_name": "Synthetic Pilot",
    "unit_path": "pilot",
    "unit_type": "program",
    "unit_name": "Synthetic Pilot Unit",
}


def _environ_for(*roles: str) -> dict[str, str]:
    """Configure exactly the named roles, and nothing else."""
    environ: dict[str, str] = {}
    for entry in seed_pilot_logins.ROLE_CREDENTIALS:
        if entry.role in roles:
            environ[entry.email_var] = f"{entry.role}@test.invalid"
            environ[entry.password_var] = _USABLE_SECRET
    return environ


class _Recorder:
    """Stands in for `seed_pilot` and the credential repository together."""

    def __init__(self) -> None:
        self.seeded: list[dict[str, object]] = []
        self.credentials: list[uuid.UUID] = []

    def seed_pilot(self, _connection: object, **kwargs: object) -> None:
        self.seeded.append(kwargs)

    def upsert(self, _connection: object, **kwargs: object) -> None:
        self.credentials.append(kwargs["user_id"])  # type: ignore[arg-type]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Patch out every database call, leaving only the role decision."""
    rec = _Recorder()
    account_id = uuid.uuid4()
    monkeypatch.setattr(seed_pilot_logins, "seed_pilot", rec.seed_pilot)
    monkeypatch.setattr(seed_pilot_logins, "_account_id", lambda _c, *, subject: account_id)
    monkeypatch.setattr(
        seed_pilot_logins,
        "PilotCredentialRepository",
        lambda: SimpleNamespace(upsert=rec.upsert),
    )
    monkeypatch.setattr(
        seed_pilot_logins.sa,
        "select",
        lambda *_a, **_k: SimpleNamespace(where=lambda *_w: object()),
    )
    return rec


class _Connection:
    """Answers the one `SELECT tenant.id` the tool makes per configured role."""

    def __init__(self) -> None:
        self.tenant_id = uuid.uuid4()

    def execute(self, _statement: object, _params: object | None = None) -> object:
        return SimpleNamespace(scalar_one=lambda: self.tenant_id)


# ---------------------------------------------------------------------------
# The decision: one persona, two roles, two credentials
# ---------------------------------------------------------------------------


def test_both_connector_logins_carry_both_memberships() -> None:
    """The deliverable. Either address signs in to the same connector shell.

    They stay two accounts because login is keyed on ``user_account.email``
    and an account holds one ``pilot_credential`` — merging them would retire
    an address the owner already has, which is the owner's decision. What is
    merged is the *persona*: identical role sets, identical portal.
    """
    by_subject = {entry.subject: entry for entry in seed_pilot_logins.ROLE_CREDENTIALS}

    coordinator = by_subject["pilot-login-coordinator"]
    admin = by_subject["pilot-login-admin"]

    assert set(coordinator.roles) == {"coordinator", "admin"}
    assert set(admin.roles) == {"coordinator", "admin"}
    # Same persona, and the stored primary role still distinguishes the rows an
    # operator reads in the report this tool prints.
    assert coordinator.role == "coordinator"
    assert admin.role == "admin"


def test_the_single_role_logins_gained_nothing() -> None:
    """The merge is the connector persona's alone.

    A student who quietly became a coordinator would be this change buying its
    deliverable by widening something, which is the failure mode the whole
    pilot-principal design exists to avoid.
    """
    for entry in seed_pilot_logins.ROLE_CREDENTIALS:
        if entry.role in {"student", "volunteer"}:
            assert entry.roles == (entry.role,), (
                f"the {entry.role} login now holds {entry.roles}; only the "
                "connector persona holds more than one role"
            )


def test_every_seeded_role_is_one_the_portal_map_knows() -> None:
    """A role with no portal would seed a login that opens nothing."""
    from smartmatch_api.routers.portals import _PORTAL_FOR_ROLE

    for entry in seed_pilot_logins.ROLE_CREDENTIALS:
        for role in entry.roles:
            assert role in _PORTAL_FOR_ROLE, f"{entry.subject} holds unmapped role {role!r}"


def test_the_connector_logins_are_handed_to_seed_pilot_as_one_membership_set(
    recorder: _Recorder,
) -> None:
    """Both roles go through one `seed_pilot` call, not two.

    Two calls would hit ``_ensure_membership_set`` twice with one role each,
    and the second would see the first's row as a membership it did not ask
    for — a conflict, on a fresh database, every time.
    """
    outcomes = seed_pilot_logins.seed_role_logins(
        _Connection(),  # type: ignore[arg-type]
        environ=_environ_for("coordinator"),
        **_SEED_KWARGS,
    )

    assert [outcome.created for outcome in outcomes if outcome.role == "coordinator"] == [True]
    assert len(recorder.seeded) == 1
    call = recorder.seeded[0]
    assert call["role"] == "coordinator"
    assert call["additional_roles"] == ("admin",)


def test_a_single_role_login_passes_no_additional_roles(recorder: _Recorder) -> None:
    seed_pilot_logins.seed_role_logins(
        _Connection(),  # type: ignore[arg-type]
        environ=_environ_for("student"),
        **_SEED_KWARGS,
    )

    assert recorder.seeded[0]["role"] == "student"
    assert recorder.seeded[0]["additional_roles"] == ()


# ---------------------------------------------------------------------------
# What the merge must not have loosened
# ---------------------------------------------------------------------------


def test_an_unconfigured_role_creates_nothing_and_says_so(recorder: _Recorder) -> None:
    outcomes = seed_pilot_logins.seed_role_logins(
        _Connection(),  # type: ignore[arg-type]
        environ=_environ_for("student"),
        **_SEED_KWARGS,
    )

    skipped = [outcome for outcome in outcomes if not outcome.created]
    assert {outcome.role for outcome in skipped} == {"coordinator", "admin", "volunteer"}
    for outcome in skipped:
        assert "not created" in outcome.reason
        # The variable names are named, so an operator can act on the report.
        assert "SMARTMATCH_PILOT_" in outcome.reason
    assert len(recorder.seeded) == 1


def test_a_half_configured_role_is_an_error_not_a_skip(recorder: _Recorder) -> None:
    entry = next(e for e in seed_pilot_logins.ROLE_CREDENTIALS if e.role == "admin")

    with pytest.raises(seed_pilot_logins.SeedCredentialError, match="Set both or neither"):
        seed_pilot_logins.seed_role_logins(
            _Connection(),  # type: ignore[arg-type]
            environ={entry.email_var: "admin@test.invalid"},
            **_SEED_KWARGS,
        )

    assert recorder.seeded == []


def test_a_short_password_is_refused_rather_than_lengthened(recorder: _Recorder) -> None:
    entry = next(e for e in seed_pilot_logins.ROLE_CREDENTIALS if e.role == "admin")
    too_short = "x" * (MINIMUM_PASSWORD_LENGTH - 1)

    with pytest.raises(seed_pilot_logins.SeedCredentialError, match="shorter than"):
        seed_pilot_logins.seed_role_logins(
            _Connection(),  # type: ignore[arg-type]
            environ={entry.email_var: "admin@test.invalid", entry.password_var: too_short},
            **_SEED_KWARGS,
        )

    assert recorder.seeded == []


def test_no_outcome_the_tool_prints_carries_a_password(recorder: _Recorder) -> None:
    """The report names roles, emails and variable names — never a secret."""
    outcomes = seed_pilot_logins.seed_role_logins(
        _Connection(),  # type: ignore[arg-type]
        environ=_environ_for("coordinator", "admin", "student", "volunteer"),
        **_SEED_KWARGS,
    )

    assert [outcome.created for outcome in outcomes] == [True, True, True, True]
    for outcome in outcomes:
        assert _USABLE_SECRET not in outcome.reason
    assert len(recorder.credentials) == 4
