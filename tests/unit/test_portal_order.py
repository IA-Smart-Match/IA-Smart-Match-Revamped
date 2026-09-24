"""R-J (B26 T6b-5): the Event Host Portal is listed before the Speaker Portal.

One login may hold both roles after an existing-login activation.
``default_portal`` is the first listed portal, so this order is what keeps a
Host who is also a Speaker landing where they always did.
"""

from __future__ import annotations

from smartmatch_api.routers import portals


def test_volunteer_precedes_speaker() -> None:
    order = portals._PORTAL_ORDER
    assert order.index("volunteer") < order.index("speaker")


def test_the_module_asserts_the_order_at_import() -> None:
    """The guard lives in the module, so a reordering fails at import, not in review."""
    source = portals.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert '_PORTAL_ORDER.index("volunteer") < _PORTAL_ORDER.index("speaker")' in text
