"""Fixtures for the compose-appliance click-through (``pytest -m e2e``).

These tests talk to a *running* ``docker compose`` appliance over HTTP. They
build nothing, start nothing and tear nothing down: CI owns ``up``/``down -v``
so that logs survive a failure, exactly as ``scripts/compose_smoke.sh``
already does, and a developer running them by hand wants the stack still
standing afterwards to look at.

Two rules this package holds itself to, both paid for already:

* **No unbounded wait.** ``docker compose up -d`` returns when containers have
  STARTED, not when a one-shot has FINISHED. Every wait here is a bounded poll
  of the actual condition that reports what it saw on each attempt, and ends in
  a hard failure rather than a longer sleep.
* **A step that cannot run is skipped by name, never asserted green.**
  ``pytest.skip`` carrying the reason or the missing decision is the only way a
  step may not run, and ``-ra`` in the Makefile target prints every one of them
  in the summary so a skip can never be mistaken for a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

# --- Local-only identities, matching docker-compose.yml exactly ---------------
# The compose file's own x-compose-dev-identity anchors, the same literals
# scripts/compose_smoke.sh reads. They authenticate nothing outside that
# network and are not secrets; see docker-compose.yml's header note.
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8080")
API_BEARER = os.environ.get("API_BEARER", "compose-api")
UNIT_PATH = os.environ.get("UNIT_PATH", "pilot")
DB_URL = "postgresql://smartmatch:smartmatch@localhost:5432/smartmatch"

#: Bounded poll budgets, in attempts. Mirrors compose_smoke.sh's shape.
READY_ATTEMPTS = int(os.environ.get("READY_ATTEMPTS", "60"))  # x2s
POLL_ATTEMPTS = int(os.environ.get("METRIC_ATTEMPTS", "30"))  # x1s

#: The ratified G1 presentation rule, restated here so a test that depends on
#: it fails loudly if the API stops honouring it rather than silently adapting.
SCORE_LABEL = "heuristic score"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StackUnavailable(Exception):
    """The compose appliance is not answering. Not a test failure — a skip."""


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    """Run one ``docker compose`` command from the repository root."""
    return subprocess.run(
        ["docker", "compose", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
    )


def psql_scalar(sql: str) -> str:
    """Read one scalar from the ``db`` container.

    Via ``docker compose exec`` rather than a host-published port, for the
    reason ``compose_smoke.sh`` gives: ``db`` publishes none that a native
    PostgreSQL on 5432 has not already claimed.

    This helper exists because there is **no list route for review items** —
    the API exposes only ``POST /v1/review-items/{id}/decision`` — so the id a
    coordinator would act on cannot be recovered through the API at all. That
    gap is recorded rather than papered over; see the module docstring of
    ``test_pilot_clickthrough.py``.
    """
    result = _compose("exec", "-T", "db", "psql", DB_URL, "-tAc", sql)
    if result.returncode != 0:
        raise StackUnavailable(f"psql failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def compose_service_state(service: str) -> str:
    """The service's state, or the literal ``absent``.

    ``-a`` because a finished one-shot is missing from a bare ``compose ps``,
    and "absent" is a state that must be nameable rather than read as an
    empty string.
    """
    result = _compose("ps", "-a", "--format", "{{.State}}", service)
    state = result.stdout.strip()
    return state or "absent"


def poll_until(
    describe: str,
    condition: Callable[[], bool],
    *,
    attempts: int,
    interval: float,
) -> bool:
    """Bounded poll of an actual condition. Returns whether it ever held.

    Never sleeps in place of a check, and never loops forever: the budget is
    an argument, and the caller decides what a miss means.
    """
    for attempt in range(1, attempts + 1):
        if condition():
            print(f"  {describe}: held on attempt {attempt}")
            return True
        print(f"  {describe}: not yet on attempt {attempt}/{attempts}")
        if attempt < attempts:
            time.sleep(interval)
    return False


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    """An HTTP client for the appliance, authenticated by the fixture bearer.

    There is no real sign-in in this repository: the compose dev bearer token
    is the only path to an authenticated principal, which is why it is the one
    used here. It resolves to a principal the SERVER names; nothing in this
    package ever tells the API who it is or what role it holds.
    """
    with httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {API_BEARER}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def stack_ready(api: httpx.Client) -> None:
    """Skip the whole suite unless a healthy appliance is actually up.

    A skip, not a failure: these tests describe the compose appliance, and a
    developer running ``pytest tests/`` without one standing has not broken
    anything. CI runs them behind ``docker compose up``, where an unhealthy
    stack fails the ``up`` step long before this is reached.
    """

    def healthy() -> bool:
        try:
            return api.get("/api/health").status_code == 200
        except httpx.HTTPError:
            return False

    if not poll_until("api health", healthy, attempts=READY_ATTEMPTS, interval=2.0):
        pytest.skip(
            f"no compose appliance answering at {API_BASE}/api/health after "
            f"{READY_ATTEMPTS} attempts; run 'docker compose up --build -d' first "
            "(see INSTALL.md §4)",
            allow_module_level=True,
        )

    # The one-shot. `up -d` returns when containers START, not when a one-shot
    # FINISHES — reading the seeded queue before this has exited reads a queue
    # that is not there yet, which passes on a slow terminal and fails on a
    # fast CI runner. Bounded poll of the real condition, never a sleep.
    if not poll_until(
        "seed-review one-shot exited",
        lambda: compose_service_state("seed-review") == "exited",
        attempts=READY_ATTEMPTS,
        interval=2.0,
    ):
        pytest.skip(
            "the seed-review one-shot is "
            f"'{compose_service_state('seed-review')}' and never finished; "
            "'docker compose logs seed-review' shows what it is waiting on",
            allow_module_level=True,
        )


@dataclass
class ClickThrough:
    """State carried between the ordered steps of the one click-through.

    A dataclass rather than a pile of module globals, so a step that did not
    run leaves an obvious ``None`` for the next one to skip on instead of a
    stale value from a previous session.
    """

    unit_id: str | None = None
    role: str | None = None
    email: str | None = None
    accepted_item_id: str | None = None
    rejected_item_id: str | None = None
    baseline_pending: int | None = None
    match_run_id: str | None = None
    notes: list[str] = field(default_factory=list)


@pytest.fixture(scope="session")
def flow() -> ClickThrough:
    return ClickThrough()


def json_body(response: httpx.Response) -> dict[str, Any]:
    """Parse a response body, failing with the status and text when it is not JSON."""
    try:
        parsed = response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code} with a non-JSON body: {response.text[:500]}"
        ) from exc
    assert isinstance(parsed, dict), f"expected a JSON object, got {type(parsed).__name__}"
    return parsed
