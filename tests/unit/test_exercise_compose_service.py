"""The `api-exercise` compose service is the repo-side half of standing the
class exercise up on the pilot VM (docs/operations/exercise-hosting.md §9,
steps 7-10 and 18). This file pins the properties an operator and CI both
depend on:

* the service exists and runs the exercise product scope;
* it binds loopback only, on a port the `api` service does not already use;
* it lives in its own compose file (`docker-compose.exercise.yml`), loaded
  only when an operator names it, and is additionally gated behind the
  `exercise` compose profile — so a plain `docker compose up` against
  `docker-compose.yml` (local dev, `scripts/compose_smoke.sh`, the CI
  `compose-smoke` / `pilot-e2e` jobs) never sees this service at all and
  needs none of its secrets. It was tried first as a plain profile-gated
  service inside `docker-compose.yml` and broke both of those CI jobs:
  Docker Compose interpolates `${VAR:?message}` for every service in a
  loaded file at PARSE time, before profiles decide what actually starts, so
  a required variable with no default fails `docker compose config` — and so
  `up`/`ps`/`logs`/`down` — for the WHOLE stack the moment the declaring file
  is loaded, profile or no profile. A separate file that nobody names by
  default is what keeps that interpolation from ever running against the
  default stack;
* `docker-compose.yml` and `docker-compose.vm.yml` are untouched by this
  service — verified here by content, not merely absence of the service
  name, because that is the property the interpolation bug above depends on;
* every secret it reads is REQUIRED interpolation (`${VAR:?...}`) with no
  default — a missing secret must stop compose from starting the container,
  not boot it into an insecure or half-configured state;
* its database URL is a variable of its own, never the `api` service's
  SMARTMATCH_DATABASE_URL — ADR-0025 D2 forbids handing the exercise process
  CBA credentials.

Parsed with PyYAML rather than read as text (unlike
test_compose_dev_principals.py, which has a YAML-anchor reason to avoid a
parser): none of what is asserted here touches an anchor, and a real parse is
what `docker compose config` itself does, so this is the closest a CI runner
without a Docker daemon can get to that command.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
VM_COMPOSE_FILE = REPO_ROOT / "docker-compose.vm.yml"
EXERCISE_COMPOSE_FILE = REPO_ROOT / "docker-compose.exercise.yml"

SERVICE_NAME = "api-exercise"
REQUIRED_ENV_VARS = {
    "SMARTMATCH_EXERCISE_WORKSPACE_SECRET",
    "SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE",
    "SMARTMATCH_DATABASE_URL",
}

# `${VAR:?message}` — bash/compose "required, error if unset or empty" form.
# Deliberately does NOT match `${VAR:-default}` or `${VAR}` alone.
_REQUIRED_INTERPOLATION = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+):\?.+\}$")


@pytest.fixture(scope="module")
def compose_document() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vm_compose_document() -> dict:
    return yaml.safe_load(VM_COMPOSE_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def exercise_compose_document() -> dict:
    return yaml.safe_load(EXERCISE_COMPOSE_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service(exercise_compose_document: dict) -> dict:
    services = exercise_compose_document["services"]
    assert SERVICE_NAME in services, (
        f"{SERVICE_NAME} is not defined in docker-compose.exercise.yml — the "
        "compose change docs/operations/exercise-hosting.md §9 steps 7-10 "
        "depend on is missing"
    )
    return services[SERVICE_NAME]


def test_base_compose_file_does_not_declare_the_service(
    compose_document: dict,
) -> None:
    # The whole point of the separate file: docker-compose.yml must never
    # gain api-exercise, or its required-interpolation env vars break
    # `docker compose up` for the default stack again (see module docstring).
    assert SERVICE_NAME not in compose_document["services"]


def test_vm_override_does_not_declare_the_service(
    vm_compose_document: dict,
) -> None:
    # Same reason: an api-exercise fragment in docker-compose.vm.yml with no
    # build/image of its own would break the ordinary CBA
    # `-f docker-compose.yml -f docker-compose.vm.yml` VM deploy whenever
    # docker-compose.exercise.yml is not also named.
    assert SERVICE_NAME not in vm_compose_document.get("services", {})


def test_service_exists(service: dict) -> None:
    assert service["build"]["dockerfile"] == "Dockerfile.api"


def test_scope_env_is_class_exercise(service: dict) -> None:
    env = service["environment"]
    assert env["SMARTMATCH_PRODUCT_SCOPE"] == "class_exercise"


def test_binds_loopback_only(service: dict) -> None:
    ports = service["ports"]
    assert ports, "api-exercise must publish a port to be reachable at all"
    for binding in ports:
        assert binding.startswith("127.0.0.1:"), (
            f"api-exercise port binding {binding!r} is not loopback-only"
        )


def test_does_not_reuse_api_service_port(
    compose_document: dict, exercise_compose_document: dict
) -> None:
    def published_host_ports(document: dict, service_name: str) -> set[str]:
        ports = document["services"][service_name].get("ports", [])
        return {binding.split(":")[1] for binding in ports}

    api_ports = published_host_ports(compose_document, "api")
    exercise_ports = published_host_ports(exercise_compose_document, SERVICE_NAME)
    assert not (api_ports & exercise_ports), (
        f"api-exercise republishes api's host port(s) {api_ports & exercise_ports} "
        "— it must bind its own free port"
    )


def test_is_gated_behind_a_dedicated_profile(service: dict) -> None:
    profiles = service.get("profiles")
    assert profiles, "api-exercise must declare compose profiles"
    assert "default" not in profiles
    # It must not share the `dataset` profile either — that profile is a
    # one-shot data generator, unrelated to a long-running API process.
    assert set(profiles) == {"exercise"}


def test_every_required_secret_uses_required_interpolation_with_no_default(
    service: dict,
) -> None:
    env = service["environment"]
    missing = REQUIRED_ENV_VARS - env.keys()
    assert not missing, f"api-exercise is missing required env vars: {missing}"

    for var_name in REQUIRED_ENV_VARS:
        raw_value = env[var_name]
        match = _REQUIRED_INTERPOLATION.match(raw_value)
        assert match, (
            f"{var_name}={raw_value!r} on api-exercise must use required "
            "interpolation (${VAR:?message}) with no fallback default — a "
            "missing secret must stop the container from starting"
        )


def test_database_url_is_the_dedicated_exercise_variable(service: dict) -> None:
    raw_value = service["environment"]["SMARTMATCH_DATABASE_URL"]
    match = _REQUIRED_INTERPOLATION.match(raw_value)
    assert match is not None
    source_var = match.group("name")
    assert source_var == "SMARTMATCH_EXERCISE_DATABASE_URL", (
        "api-exercise's SMARTMATCH_DATABASE_URL must be sourced from "
        "SMARTMATCH_EXERCISE_DATABASE_URL, a variable of its own — never "
        "from the same host variable the CBA `api` service reads, per "
        "ADR-0025 D2"
    )


def test_api_service_database_url_is_unchanged(compose_document: dict) -> None:
    # The CBA api service must keep its literal, owner-role connection
    # string byte-for-byte — this track must not touch it.
    api_env = compose_document["services"]["api"]["environment"]
    assert api_env["SMARTMATCH_DATABASE_URL"] == (
        "postgresql+psycopg://smartmatch:smartmatch@db:5432/smartmatch"
    )


def test_no_default_stack_service_name_collides(
    exercise_compose_document: dict,
) -> None:
    # A plain `docker compose config --services` call resolves every service
    # whether or not its profile is active, so this checks the declared
    # profile instead — the property CI actually relies on is that `up`
    # without --profile exercise never starts this container, and (per
    # test_base_compose_file_does_not_declare_the_service) that it is not
    # even considered unless docker-compose.exercise.yml is named.
    services = exercise_compose_document["services"]
    assert services[SERVICE_NAME].get("profiles") == ["exercise"]


def test_adds_restart_policy(service: dict) -> None:
    # Matches every long-running service in docker-compose.vm.yml. Declared
    # directly on the service in docker-compose.exercise.yml rather than as a
    # docker-compose.vm.yml override — see the module docstring and that
    # file's own header for why an override here would break the ordinary
    # CBA-only VM deploy command.
    assert service.get("restart") == "unless-stopped"


def test_pins_cookie_secure_true(service: dict) -> None:
    # Owner decision, 2026-09-21: true on the HTTPS VM
    # (exercise-hosting.md §2). Hard-set rather than interpolated, for the
    # same reason as the restart policy above.
    assert service["environment"]["SMARTMATCH_EXERCISE_COOKIE_SECURE"] == "true"
