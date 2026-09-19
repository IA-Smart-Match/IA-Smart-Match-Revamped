"""Nothing in the CBA process can see ``EXERCISE_REGISTRY``.

ADR-0025's whole isolation claim, reduced to the one thing that can be
checked mechanically: the exercise rulebook is bound to its version **only**
when :mod:`smartmatch_domain.exercise.registry` is imported, and the CBA
composition never imports it.

The check runs in a fresh interpreter each time, because
``_REGISTRIES_BY_VERSION`` is process-global: in this test session the
exercise registry is already registered by the other exercise tests, so an
in-process assertion would prove nothing at all.

Follow-up recorded on PR #173 and relevant here: the match-runs router and the
worker wrap only the bare gate calls in ``except (RegistryNotApprovedError,
RegistryNotReadyError)``, not the ranking and explanation calls that would
raise :class:`UnknownRegistryVersionError`. That handler widening is still not
needed, and this file is why — a CBA process cannot resolve ``exercise-0.1.0``
because it cannot produce a score that names it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

EXERCISE_PIN = "exercise-0.1.0"


def _run(script: str) -> str:
    """Run a snippet in a fresh interpreter and return its stdout.

    The parent's ``sys.path`` is handed over so the child imports *this*
    working tree's domain package rather than whatever is installed.
    """
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path)}
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_importing_scoring_alone_does_not_register_the_exercise_version() -> None:
    output = _run(
        f"""
        import smartmatch_domain.scoring  # noqa: F401
        from smartmatch_domain.factor_registry import (
            UnknownRegistryVersionError,
            registry_for_version,
        )
        try:
            registry_for_version({EXERCISE_PIN!r})
        except UnknownRegistryVersionError:
            print("unregistered")
        else:
            print("REGISTERED")
        """
    )
    assert output == "unregistered"


def test_importing_explanation_alone_does_not_register_it_either() -> None:
    output = _run(
        f"""
        import smartmatch_domain.explanation  # noqa: F401
        from smartmatch_domain.factor_registry import (
            UnknownRegistryVersionError,
            registry_for_version,
        )
        try:
            registry_for_version({EXERCISE_PIN!r})
        except UnknownRegistryVersionError:
            print("unregistered")
        else:
            print("REGISTERED")
        """
    )
    assert output == "unregistered"


def test_the_simulated_results_rule_does_not_register_it_either() -> None:
    """The one exercise module a non-matching path might import on its own."""
    output = _run(
        f"""
        import smartmatch_domain.exercise.simulation  # noqa: F401
        from smartmatch_domain.factor_registry import (
            UnknownRegistryVersionError,
            registry_for_version,
        )
        try:
            registry_for_version({EXERCISE_PIN!r})
        except UnknownRegistryVersionError:
            print("unregistered")
        else:
            print("REGISTERED")
        """
    )
    assert output == "unregistered"


def test_importing_the_exercise_matching_module_registers_it() -> None:
    output = _run(
        f"""
        import smartmatch_domain.exercise.matching  # noqa: F401
        from smartmatch_domain.factor_registry import registry_for_version

        print(registry_for_version({EXERCISE_PIN!r}).version)
        """
    )
    assert output == EXERCISE_PIN


def test_the_cba_pins_still_resolve_with_the_exercise_registered() -> None:
    output = _run(
        """
        import smartmatch_domain.exercise.matching  # noqa: F401
        from smartmatch_domain.factor_registry import (
            CBA_REGISTRY,
            REGISTRY_VERSION,
            SUPERSEDED_REGISTRY_VERSION,
            registry_for_version,
        )

        assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY
        assert registry_for_version(SUPERSEDED_REGISTRY_VERSION) is CBA_REGISTRY
        print("ok")
        """
    )
    assert output == "ok"
