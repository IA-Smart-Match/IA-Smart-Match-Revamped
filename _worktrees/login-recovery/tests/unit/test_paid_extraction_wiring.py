"""The composition root's paid-extraction wiring (ADR-0015 A1).

`tests/unit/test_paid_extraction_handler.py` covers the handler and
`with_paid_extraction` themselves. What is covered here is the one thing
neither of those can see: whether a booting worker actually ends up routing
`extraction.paid_pages`, and under exactly which configuration.

The rule these tests pin is that a worker acquires the ability to spend money
only when a deployment has named all three ceilings it is accountable for.
ADR-0015 A1 leaves the A3 price unverified, so every ceiling derived from it is
provisional and none can ship as a default; the absence of configuration is
therefore the control, not an oversight. `default_registry` itself stays
unchanged -- it takes no collaborators, and `handlers` importing
`paid_extraction` to reach the command type would make a cycle out of a
one-way dependency -- so the composition happens in `create_app`'s lifespan,
where the session factory exists.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.handlers import CommandRegistry, default_registry
from smartmatch_worker.main import create_app
from smartmatch_worker.paid_extraction import PAID_EXTRACTION_COMMAND_TYPE

#: A DSN that is never connected to. `create_app`'s lifespan builds a session
#: factory from it, which does not open a connection, and no test here executes
#: a command.
_UNUSED_DSN = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

_ALL_THREE = {
    "spend_ceiling_job": "2.00",
    "spend_ceiling_tenant_day": "25.00",
    "spend_ceiling_tenant_month": "250.00",
}


def _settings(**overrides: str) -> WorkerSettings:
    """Build settings from explicit values only, never the ambient environment."""
    return WorkerSettings(database_url=_UNUSED_DSN, **overrides)


def _routed_command_types(settings: WorkerSettings) -> frozenset[str]:
    """Boot an app through its real lifespan and report what it ended up routing."""
    app = create_app(settings=settings)
    with TestClient(app):
        return frozenset(app.state.registry.command_types)


class TestCeilingConfiguration:
    """`WorkerSettings.spend_ceilings` is all-or-nothing, and parses strictly."""

    def test_no_ceilings_configured_yields_none(self):
        assert _settings().spend_ceilings is None

    def test_all_three_ceilings_yield_the_decimals_as_written(self):
        ceilings = _settings(**_ALL_THREE).spend_ceilings

        assert ceilings is not None
        # Decimal, not float: the exact figures a deployment typed.
        assert ceilings.job == Decimal("2.00")
        assert ceilings.tenant_day == Decimal("25.00")
        assert ceilings.tenant_month == Decimal("250.00")

    @pytest.mark.parametrize("omitted", sorted(_ALL_THREE))
    def test_a_partial_set_yields_none_rather_than_defaulting_the_rest(self, omitted: str):
        """Two of three is not "nearly configured" -- it is unconfigured.

        Filling the gap here would mean one ceiling chosen by this module
        rather than by whoever answers for the spend, which is the single thing
        A1 says must not happen.
        """
        partial = {name: value for name, value in _ALL_THREE.items() if name != omitted}

        assert _settings(**partial).spend_ceilings is None

    def test_an_unparseable_ceiling_fails_loudly_rather_than_resolving_to_zero(self):
        settings = _settings(**{**_ALL_THREE, "spend_ceiling_job": "two dollars"})

        with pytest.raises(ValueError, match="spend_ceiling_job is not a valid decimal"):
            _ = settings.spend_ceilings

    def test_a_negative_ceiling_is_refused_by_spend_ceilings_itself(self):
        settings = _settings(**{**_ALL_THREE, "spend_ceiling_job": "-1.00"})

        with pytest.raises(ValueError, match="must be non-negative"):
            _ = settings.spend_ceilings


class TestRegistryComposition:
    """What a booted worker routes, as a function of its ceiling configuration."""

    def test_default_registry_still_does_not_route_the_paid_command(self):
        """The wiring is composed at boot; `default_registry` is left as it was."""
        assert PAID_EXTRACTION_COMMAND_TYPE not in default_registry().command_types

    def test_a_worker_without_ceilings_cannot_spend(self):
        routed = _routed_command_types(_settings())

        assert PAID_EXTRACTION_COMMAND_TYPE not in routed
        # The rest of the shipped registry is untouched by the absence.
        assert {"test.noop", "import.create"} <= routed

    def test_a_worker_with_all_three_ceilings_routes_the_paid_command(self):
        routed = _routed_command_types(_settings(**_ALL_THREE))

        assert PAID_EXTRACTION_COMMAND_TYPE in routed
        # Composed onto the shipped registry, not in place of it.
        assert {"test.noop", "import.create"} <= routed

    def test_a_worker_with_a_partial_set_cannot_spend(self):
        routed = _routed_command_types(_settings(spend_ceiling_job="2.00"))

        assert PAID_EXTRACTION_COMMAND_TYPE not in routed

    def test_an_injected_registry_is_never_composed_onto(self):
        """A caller that passes a registry gets exactly that registry.

        Composing onto an injected one would hand a test, or an embedder, a
        money-spending handler it did not ask for -- even though this
        deployment's ceilings are fully configured.
        """
        injected = CommandRegistry(handlers={})
        app = create_app(settings=_settings(**_ALL_THREE), registry=injected)

        with TestClient(app):
            assert app.state.registry is injected
            assert PAID_EXTRACTION_COMMAND_TYPE not in app.state.registry.command_types
