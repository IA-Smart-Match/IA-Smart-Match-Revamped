"""The exercise seed's start-up guard and its failure handling (CE-SEED).

The seed itself writes to PostgreSQL and is proven in
``tests/integration/test_exercise_seed.py``. What is proven here needs no
database, and is the half that protects the pilot VM:

* the auto-seed is **off** unless ``SMARTMATCH_EXERCISE_SEED_ON_START`` is set;
* when it is set, it still refuses under every production signal, including the
  pilot VM's own combination, where ``SMARTMATCH_EDITION=dev`` is pinned and so
  an edition check alone would have let it through;
* a failure is one log line, never an exception that stops the API, and never
  the text of the exception — driver text can carry row values (ADR-0025 D6).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from smartmatch_api import exercise_seed
from smartmatch_api.config import Settings
from smartmatch_api.exercise_seed import (
    DEFAULT_SEED_FILE,
    SeedOutcome,
    auto_seed_refusal,
    seed_on_start,
)
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS

from tests.unit.exercise_workbooks import ANN_FULL_FILE

_LOCAL_URL = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"


def _settings(**overrides: object) -> Settings:
    """A host-run developer API with the flag on: the one place the seed may run.

    Every field the guard reads is passed explicitly, so a ``SMARTMATCH_*``
    variable in the shell running the tests cannot change the answer.
    """
    values: dict[str, object] = {
        "edition": "dev",
        "product_scope": "class_exercise",
        "exercise_seed_on_start": True,
        "exercise_cookie_secure": None,
        "release": "dev",
        "database_url": _LOCAL_URL,
        "use_fixture_providers": True,
        "email_api_key": None,
        "routes_api_key": None,
        "dev_principals": {},
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class _NeverCalled:
    """A session factory the test fails on if anything opens a session."""

    def __call__(self) -> object:
        raise AssertionError("the seed opened a database session it should not have")


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_the_flag_is_off_by_default() -> None:
    assert Settings.model_fields["exercise_seed_on_start"].default is False


def test_the_default_seed_file_is_anns_fixture() -> None:
    assert DEFAULT_SEED_FILE == ANN_FULL_FILE
    assert DEFAULT_SEED_FILE.is_file()


@pytest.mark.parametrize(
    "database_url",
    [
        _LOCAL_URL,
        "postgresql+psycopg://smartmatch:smartmatch@127.0.0.1:5432/smartmatch",
        "postgresql+psycopg://smartmatch:smartmatch@[::1]:5432/smartmatch",
        "postgresql+psycopg://smartmatch@/smartmatch",
    ],
)
def test_a_host_run_developer_api_may_seed(database_url: str) -> None:
    assert auto_seed_refusal(_settings(database_url=database_url)) is None


@pytest.mark.parametrize(
    ("overrides", "names"),
    [
        ({"exercise_cookie_secure": True}, "SMARTMATCH_EXERCISE_COOKIE_SECURE"),
        ({"edition": "staging"}, "SMARTMATCH_EDITION"),
        ({"edition": "production"}, "SMARTMATCH_EDITION"),
        ({"release": "vm-unknown"}, "SMARTMATCH_RELEASE"),
        ({"release": "compose-dev"}, "SMARTMATCH_RELEASE"),
        ({"release": "3f2a9c1"}, "SMARTMATCH_RELEASE"),
        ({"use_fixture_providers": False}, "SMARTMATCH_USE_FIXTURE_PROVIDERS"),
        ({"email_api_key": "k"}, "provider credential"),
        ({"routes_api_key": "k"}, "provider credential"),
        (
            {"database_url": "postgresql+psycopg://smartmatch:smartmatch@db:5432/smartmatch"},
            "SMARTMATCH_DATABASE_URL",
        ),
        (
            {"database_url": "postgresql+psycopg://u:p@10.0.0.5:5432/smartmatch"},
            "SMARTMATCH_DATABASE_URL",
        ),
        ({"product_scope": "cba"}, "SMARTMATCH_PRODUCT_SCOPE"),
    ],
)
def test_every_production_signal_refuses(overrides: dict[str, object], names: str) -> None:
    refusal = auto_seed_refusal(_settings(**overrides))

    assert refusal is not None
    assert names in refusal


def test_the_pilot_vms_own_environment_is_refused() -> None:
    """``docker-compose.exercise.yml`` as it runs on the VM, with the flag on anyway.

    ``SMARTMATCH_EDITION=dev`` passes the edition check — which is why the
    edition cannot be the guard — and three other signals refuse it.
    """
    vm = _settings(
        exercise_cookie_secure=True,
        release="vm-unknown",
        database_url="postgresql+psycopg://exercise_role:pw@db:5432/smartmatch",
    )

    refusal = auto_seed_refusal(vm)

    assert refusal is not None
    assert "SMARTMATCH_EXERCISE_COOKIE_SECURE" in refusal


def test_a_refusal_never_names_a_password() -> None:
    refusal = auto_seed_refusal(
        _settings(database_url="postgresql+psycopg://role:hunter2-secret@db:5432/smartmatch")
    )

    assert refusal is not None
    assert "hunter2-secret" not in refusal


# ---------------------------------------------------------------------------
# On start
# ---------------------------------------------------------------------------


def test_off_opens_no_session_and_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=exercise_seed.__name__)

    seed_on_start(_settings(exercise_seed_on_start=False), _NeverCalled())  # type: ignore[arg-type]

    assert [r for r in caplog.records if r.name == exercise_seed.__name__] == []


def test_refused_opens_no_session_and_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=exercise_seed.__name__)

    seed_on_start(_settings(exercise_cookie_secure=True), _NeverCalled())  # type: ignore[arg-type]

    lines = [r for r in caplog.records if r.name == exercise_seed.__name__]
    assert len(lines) == 1
    assert lines[0].levelno == logging.WARNING
    assert "refused" in lines[0].getMessage()


def test_a_failure_is_one_line_without_the_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=exercise_seed.__name__)

    def exploding_factory() -> object:
        raise RuntimeError("secret-interest-042 leaked through a driver message")

    seed_on_start(_settings(), exploding_factory)  # type: ignore[arg-type]

    lines = [r for r in caplog.records if r.name == exercise_seed.__name__]
    assert len(lines) == 1
    assert lines[0].levelno == logging.WARNING
    assert "RuntimeError" in lines[0].getMessage()
    assert "secret-interest-042" not in caplog.text
    assert lines[0].exc_info is None


def test_a_missing_seed_file_is_one_line(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.DEBUG, logger=exercise_seed.__name__)

    seed_on_start(_settings(), _NeverCalled(), seed_file=tmp_path / "absent.xlsx")  # type: ignore[arg-type]

    lines = [r for r in caplog.records if r.name == exercise_seed.__name__]
    assert len(lines) == 1
    assert "FileNotFoundError" in lines[0].getMessage()


# ---------------------------------------------------------------------------
# What a line may say
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seeded", [True, False])
def test_a_line_is_counts_and_a_label_only(seeded: bool) -> None:
    line = SeedOutcome(
        seeded=seeded, label="Ann's student body (seeded)", profile_count=300, event_count=12
    ).line()

    assert "\n" not in line
    for field in EXERCISE_WITHHELD_FIELDS:
        assert field not in line
    if seeded:
        assert "300 profiles" in line
        assert "12 events" in line
    else:
        assert "nothing seeded" in line
