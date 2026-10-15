"""Contract-suite fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _pin_2_0_0_current(monkeypatch):
    """Pre-staged 3.0.0 flip (#297): keep this suite on 2.0.0 until IA West review lands.

    Tests that need 3.0.0 current set it themselves (``_make_3_0_0_current``).
    """
    from smartmatch_domain import factor_registry

    monkeypatch.setattr(factor_registry, "CURRENT_CBA_REGISTRY", factor_registry.CBA_REGISTRY)
