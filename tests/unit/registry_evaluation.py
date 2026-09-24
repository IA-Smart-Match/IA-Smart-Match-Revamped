"""Evaluate registry 3.0.0 in a test without making it approved or current.

Not collected (no ``test_`` prefix). T8c plan §9 item 2.

Registry 3.0.0 ships ``proposed``: the real approval gate refuses it, and must go
on refusing it everywhere outside a test that asks for it by name. This helper
lets one test evaluate it:

* It wraps the ``assert_registry_approved`` **name** only in the modules the
  caller lists, and only if each is already in ``sys.modules``. It never imports
  a module: a golden or domain test names ``smartmatch_domain.scoring`` and
  ``smartmatch_domain.explanation`` and so never pulls in the API or the worker.
* A listed module missing from ``sys.modules`` raises ``LookupError``: a silent
  no-op would leave a gate unpatched and the test would prove nothing.
* The wrapper lets exactly one registry through: ``registry is CBA_REGISTRY_3``.
  Every other call, including every zero-argument call, goes to the real gate.

``monkeypatch`` undoes every wrap when the test ends. The registry's status,
``CURRENT_CBA_REGISTRY`` and ``REGISTRY_VERSION`` are never touched.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from smartmatch_domain.factor_registry import CBA_REGISTRY_3

__all__ = ["DOMAIN_MODULES", "evaluate_registry_3"]

#: The domain modules whose gate a golden or domain unit test evaluates.
DOMAIN_MODULES: tuple[str, ...] = ("smartmatch_domain.scoring", "smartmatch_domain.explanation")


def _passing_only_registry_3(real: Callable[..., None]) -> Callable[..., None]:
    def gate(**kwargs: Any) -> None:
        if kwargs.get("registry") is CBA_REGISTRY_3:
            return
        real(**kwargs)

    return gate


def evaluate_registry_3(
    monkeypatch: pytest.MonkeyPatch, *, modules: Sequence[str] = DOMAIN_MODULES
) -> None:
    """Let ``CBA_REGISTRY_3`` through the approval gate of the named modules.

    Raises:
        LookupError: when a named module has not been imported yet.
        AttributeError: when a named module has no ``assert_registry_approved``.
    """
    for name in modules:
        module = sys.modules.get(name)
        if module is None:
            raise LookupError(
                f"{name} is not imported; evaluate_registry_3 patches only modules already "
                "loaded, so an unimported one would keep the real gate silently"
            )
        real = module.assert_registry_approved
        monkeypatch.setattr(module, "assert_registry_approved", _passing_only_registry_3(real))
