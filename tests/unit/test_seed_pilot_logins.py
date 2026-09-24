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

import pytest
from smartmatch_domain.pilot_credentials import MINIMUM_PASSWORD_LENGTH, StoredPassword
from smartmatch_persistence.login_accounts import (
    AddressHolders,
    AddressState,
    LoginHolder,
    NewLogin,
    RoleGrant,
)

# `tools/` rather than the repository root, and for the reason
# `test_compose_dev_principals.py` gives: these operator scripts import each
# other by bare module name (`seed_pilot_logins` does `from seed_pilot import
# ...`), because they run as scripts and not as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import seed_pilot_logins

#: Long enough to pass ``MINIMUM_PASSWORD_LENGTH`` (12) and obviously
#: synthetic — and deliberately under sixteen characters, the length at which
#: ``tools/scan_forbidden.py``'s ``hard-coded-credential`` rule starts reading
#: a ``secret``/``password`` literal as entropy-bearing (the convention
#: ``test_compose_dev_principals.py`` documents). Not a credential: nothing
#: reads it but the fake below.
_USABLE_SECRET = "fake-pass-00000"

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
    """Stands in for the identity helpers and ``login_accounts`` together.

    Every call is appended to :attr:`events` in order, with the connection it
    was handed, so a test can read both *what* the seed did and that it did it
    in one transaction and in the lock order (address lock, then the row
    locks, then writes).
    """

    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []
        self.connections: set[int] = set()
        self.accounts: dict[str, uuid.UUID] = {}
        self.holders: dict[str, AddressHolders] = {}
        self.tenant_id = uuid.uuid4()

    def _saw(self, connection: object, *event: object) -> None:
        self.connections.add(id(connection))
        self.events.append(event)

    def tenant(self, connection: object, *, slug: str, display_name: str) -> uuid.UUID:
        self._saw(connection, "tenant", slug)
        return self.tenant_id

    def unit(self, connection: object, **kwargs: object) -> None:
        self._saw(connection, "unit", kwargs["path"])

    def account(self, connection: object, *, tenant_id: uuid.UUID, subject: str, email: str):
        self._saw(connection, "account", subject)
        return self.accounts.setdefault(subject, uuid.uuid4())

    def verify(self, connection: object, *, account_id: uuid.UUID, roles, **_: object):
        self._saw(connection, "verify", account_id, tuple(roles))
        return frozenset()

    def lock_address(self, connection: object, *, address: str) -> None:
        self._saw(connection, "lock", address)

    def holders_for_address(self, connection: object, *, address: str, lock: bool, **_: object):
        self._saw(connection, "holders", address, lock)
        return self.holders.get(address, AddressHolders(AddressState.NONE, None))

    def find_or_add_role(
        self,
        connection: object,
        *,
        email: str,
        role: str,
        create: NewLogin | None = None,
        **_: object,
    ) -> RoleGrant:
        self._saw(connection, "role", email, role, None if create is None else create.user_id)
        return RoleGrant(
            user_id=create.user_id if create else uuid.uuid4(),
            external_subject="recorded",
            login_created=create is not None,
            role_added=True,
        )

    def rotate(self, connection: object, *, user_id: uuid.UUID, **_: object) -> None:
        self._saw(connection, "rotate", user_id)

    def of(self, kind: str) -> list[tuple[object, ...]]:
        return [event for event in self.events if event[0] == kind]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Patch out every database call, leaving only the tool's decisions."""
    rec = _Recorder()
    monkeypatch.setattr(seed_pilot_logins, "_existing_or_insert_tenant", rec.tenant)
    monkeypatch.setattr(seed_pilot_logins, "_existing_or_insert_unit", rec.unit)
    monkeypatch.setattr(seed_pilot_logins, "_existing_or_insert_account", rec.account)
    monkeypatch.setattr(seed_pilot_logins, "verify_membership_set", rec.verify)
    accounts = seed_pilot_logins.login_accounts
    monkeypatch.setattr(accounts, "lock_address", rec.lock_address)
    monkeypatch.setattr(accounts, "holders_for_address", rec.holders_for_address)
    monkeypatch.setattr(accounts, "find_or_add_role", rec.find_or_add_role)
    monkeypatch.setattr(accounts, "rotate_own_password", rec.rotate)
    return rec


def _holder(subject: str) -> AddressHolders:
    return AddressHolders(
        AddressState.ONE_IN_TENANT,
        LoginHolder(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            external_subject=subject,
            suspended=False,
            password=StoredPassword(algorithm="recorded", iterations=1, salt=b"", digest=b""),
        ),
    )


def _entry(role: str) -> seed_pilot_logins.RoleCredential:
    return next(e for e in seed_pilot_logins.ROLE_CREDENTIALS if e.role == role)


_CONNECTION = object()


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


def test_the_connector_logins_are_verified_as_one_membership_set(
    recorder: _Recorder,
) -> None:
    """Both roles are checked as one set, not one at a time.

    Two checks with one role each would each see the other's row as a
    membership they did not ask for — a conflict, on a re-run, every time.
    """
    outcomes = seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("coordinator"),
        **_SEED_KWARGS,
    )

    assert [outcome.created for outcome in outcomes if outcome.role == "coordinator"] == [True]
    [verify] = recorder.of("verify")
    assert verify[2] == ("coordinator", "admin")


def test_a_single_role_login_passes_no_additional_roles(recorder: _Recorder) -> None:
    seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("student"),
        **_SEED_KWARGS,
    )

    assert recorder.of("verify")[0][2] == ("student",)
    assert [event[2] for event in recorder.of("role")] == ["student"]


# ---------------------------------------------------------------------------
# What the merge must not have loosened
# ---------------------------------------------------------------------------


def test_an_unconfigured_role_creates_nothing_and_says_so(recorder: _Recorder) -> None:
    outcomes = seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("student"),
        **_SEED_KWARGS,
    )

    skipped = [outcome for outcome in outcomes if not outcome.created]
    assert {outcome.role for outcome in skipped} == {"coordinator", "admin", "volunteer"}
    for outcome in skipped:
        assert "not created" in outcome.reason
        # The variable names are named, so an operator can act on the report.
        assert "SMARTMATCH_PILOT_" in outcome.reason
    assert len(recorder.of("verify")) == 1


def test_a_half_configured_role_is_an_error_not_a_skip(recorder: _Recorder) -> None:
    entry = next(e for e in seed_pilot_logins.ROLE_CREDENTIALS if e.role == "admin")

    with pytest.raises(seed_pilot_logins.SeedCredentialError, match="Set both or neither"):
        seed_pilot_logins.seed_role_logins(
            _CONNECTION,  # type: ignore[arg-type]
            environ={entry.email_var: "admin@test.invalid"},
            **_SEED_KWARGS,
        )

    assert recorder.events == []


def test_a_short_password_is_refused_rather_than_lengthened(recorder: _Recorder) -> None:
    entry = next(e for e in seed_pilot_logins.ROLE_CREDENTIALS if e.role == "admin")
    too_short = "x" * (MINIMUM_PASSWORD_LENGTH - 1)

    with pytest.raises(seed_pilot_logins.SeedCredentialError, match="shorter than"):
        seed_pilot_logins.seed_role_logins(
            _CONNECTION,  # type: ignore[arg-type]
            environ={entry.email_var: "admin@test.invalid", entry.password_var: too_short},
            **_SEED_KWARGS,
        )

    assert recorder.events == []


def test_no_outcome_the_tool_prints_carries_a_password(recorder: _Recorder) -> None:
    """The report names roles, emails and variable names — never a secret."""
    outcomes = seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("coordinator", "admin", "student", "volunteer"),
        **_SEED_KWARGS,
    )

    assert [outcome.created for outcome in outcomes] == [True, True, True, True]
    for outcome in outcomes:
        assert _USABLE_SECRET not in outcome.reason
    assert len([event for event in recorder.of("role") if event[3] is not None]) == 4


# ---------------------------------------------------------------------------
# B26 T6b-5: the seed on find_or_add_role (plan §3.4)
# ---------------------------------------------------------------------------


def test_a_free_address_creates_the_login_through_find_or_add_role(recorder: _Recorder) -> None:
    entry = _entry("student")
    email = f"{entry.role}@test.invalid"
    seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("student"),
        **_SEED_KWARGS,
    )

    account_id = recorder.accounts[entry.subject]
    assert recorder.events == [
        ("tenant", "pilot"),
        ("unit", "pilot"),
        ("lock", email),
        ("holders", email, True),
        ("account", entry.subject),
        ("verify", account_id, ("student",)),
        ("role", email, "student", account_id),
    ]


def test_the_seeds_own_login_gets_its_roles_and_a_rotated_password(recorder: _Recorder) -> None:
    entry = _entry("coordinator")
    email = f"{entry.role}@test.invalid"
    recorder.holders[email] = _holder(entry.subject)

    [outcome] = [
        o
        for o in seed_pilot_logins.seed_role_logins(
            _CONNECTION,  # type: ignore[arg-type]
            environ=_environ_for("coordinator"),
            **_SEED_KWARGS,
        )
        if o.role == "coordinator"
    ]

    account_id = recorder.accounts[entry.subject]
    assert recorder.of("role") == [
        ("role", email, "coordinator", None),
        ("role", email, "admin", None),
    ]
    assert recorder.of("rotate") == [("rotate", account_id)]
    assert recorder.events.index(("rotate", account_id)) > recorder.events.index(
        ("holders", email, True)
    )
    assert outcome.created and not outcome.foreign_login
    assert "password rotated" in outcome.reason


def test_a_foreign_login_gets_the_roles_and_keeps_its_password(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q4: the address already signs in as a login the seed did not create."""
    entry = _entry("volunteer")
    email = f"{entry.role}@test.invalid"
    recorder.holders[email] = _holder("activated-speaker-login")

    outcomes = seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("volunteer"),
        **_SEED_KWARGS,
    )

    [outcome] = [o for o in outcomes if o.role == "volunteer"]
    assert recorder.of("role") == [("role", email, "volunteer", None)]
    assert recorder.of("rotate") == []
    assert recorder.of("account") == [] and recorder.of("verify") == []
    assert outcome.created and outcome.foreign_login
    assert entry.password_var in outcome.reason and "was not applied" in outcome.reason
    assert _USABLE_SECRET not in outcome.reason

    # main() reports it on stderr, never stdout, and never the password.
    monkeypatch.setattr(seed_pilot_logins, "require_development_fixture_settings", lambda s: s)
    monkeypatch.setattr(seed_pilot_logins, "Settings", lambda: _FakeSettings())
    monkeypatch.setattr(seed_pilot_logins, "create_db_engine", lambda url: _FakeEngine())
    monkeypatch.setattr(seed_pilot_logins, "acquire_seed_lock", lambda connection: None)
    monkeypatch.setattr(seed_pilot_logins, "seed_role_logins", lambda c, **k: [outcome])
    assert seed_pilot_logins.main([]) == 0
    printed = capsys.readouterr()
    assert entry.password_var in printed.err and entry.password_var not in printed.out
    assert _USABLE_SECRET not in printed.err + printed.out


@pytest.mark.parametrize("state", [AddressState.AMBIGUOUS, AddressState.OTHER_TENANT])
def test_ambiguous_or_other_tenant_address_is_a_conflict_error(
    recorder: _Recorder, state: AddressState
) -> None:
    entry = _entry("admin")
    recorder.holders[f"{entry.role}@test.invalid"] = AddressHolders(state, None)

    with pytest.raises(seed_pilot_logins.SeedConflictError) as raised:
        seed_pilot_logins.seed_role_logins(
            _CONNECTION,  # type: ignore[arg-type]
            environ=_environ_for("admin"),
            **_SEED_KWARGS,
        )

    message = str(raised.value)
    assert entry.role in message and entry.email_var in message
    assert "@" not in message and str(recorder.tenant_id) not in message
    assert recorder.of("role") == [] and recorder.of("rotate") == []


def test_the_connector_login_adds_coordinator_and_admin_in_one_transaction(
    recorder: _Recorder,
) -> None:
    entry = _entry("admin")
    email = f"{entry.role}@test.invalid"
    seed_pilot_logins.seed_role_logins(
        _CONNECTION,  # type: ignore[arg-type]
        environ=_environ_for("admin"),
        **_SEED_KWARGS,
    )

    account_id = recorder.accounts[entry.subject]
    assert recorder.of("role") == [
        ("role", email, "admin", account_id),
        ("role", email, "coordinator", None),
    ]
    assert recorder.connections == {id(_CONNECTION)}


class _FakeSettings:
    database_url = "postgresql+psycopg://fake.invalid/pilot"


class _FakeEngine:
    def begin(self):
        from contextlib import nullcontext

        return nullcontext(_CONNECTION)

    def dispose(self) -> None:
        return None
