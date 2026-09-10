"""Every demo principal's portal must have data on its primary surfaces.

The counterpart to ``tests/unit/test_compose_dev_principals.py``. That file
asserts the four compose bearer tokens resolve to four seeded accounts with four
distinct roles — that a stakeholder can *enter* every portal. This file asserts
the second half, which is a different failure and was found the hard way: a
portal that opens onto an empty screen.

Why "empty" here is never an ADR-0011 unknown
---------------------------------------------
Nothing in this file asserts on a score, a balance, or any measurement. It
asserts that a *table* a portal reads from is one ``tools/verify_pilot_dataset.py``
counts, and that a table scoped to a *person* names which demo subject's rows
must be there. A speaker whose topic relevance is unknown stays unknown; what is
refused is a surface with no rows at all behind it.

The ownership trap this exists to catch
---------------------------------------
Three surfaces are scoped by ``principal.user_id`` rather than by unit, and the
dataset generator writes their rows under ``synthetic-student:*`` accounts and
under the *coordinator* token. The rows exist and the counts look healthy, and
the demo student still sees nothing, because none of those rows belong to the
account ``compose-student`` resolves to. A row count alone cannot see that, so
:data:`~verify_pilot_dataset.DEMO_PORTAL_SURFACES` records the owner beside the
table and this file holds the two together.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root, for the reason
# `test_compose_dev_principals.py` gives about its own import: these modules are
# run by compose as bare siblings and importing them as `tools.…` would exercise
# a module shape nothing runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS  # noqa: E402
from verify_pilot_dataset import (  # noqa: E402
    COUNTED_TABLES,
    DEMO_PORTAL_SURFACES,
    PortalSurface,
)

#: The tables behind each portal's primary surfaces, by the compose token that
#: opens that portal.
#:
#: "Primary" means the screen the portal lands on and the screen it exists for —
#: not every table a route touches. The student portal is its agenda and its
#: rewards; the Event Host portal is the one read route it has
#: (``GET /v1/units/{unit_id}/host/speaker-requests``, OQ-CBA-014); the
#: coordinator portal is the Speaker Request queue and the match runs it drives;
#: the administration portal is the meetings page (#130) and the rewards catalog
#: whose budget it owns.
#:
#: Restated here rather than imported so this file is a second statement of the
#: requirement and not a tautology over the first.
_REQUIRED_SURFACE_TABLES: dict[str, frozenset[str]] = {
    "compose-api": frozenset(
        {"event", "speaker_request_classification", "match_run", "cba_meeting"}
    ),
    "compose-student": frozenset(
        {"attendance_record", "event_registration", "point_ledger_entry", "redemption"}
    ),
    "compose-host": frozenset({"event"}),
    "compose-admin": frozenset({"cba_meeting", "reward_item"}),
}


def test_every_demo_portal_primary_surface_table_is_counted() -> None:
    """A table no verification counts is a screen nobody notices is empty."""
    counted = {entry.table.name for entry in COUNTED_TABLES}
    uncounted = {
        token: sorted(tables - counted)
        for token, tables in _REQUIRED_SURFACE_TABLES.items()
        if tables - counted
    }
    assert not uncounted, (
        "verify_pilot_dataset.COUNTED_TABLES does not count every table a demo "
        f"portal's primary surface reads from: {uncounted}. A portal whose table is "
        "not counted opens onto an empty screen and no gate says so."
    )


def test_every_compose_principal_has_declared_portal_surfaces() -> None:
    """Four tokens, four portals, four non-empty surface sets."""
    declared = {surface.token for surface in DEMO_PORTAL_SURFACES}
    expected = {principal.token for principal in COMPOSE_DEV_PRINCIPALS}
    assert declared == expected, (
        "DEMO_PORTAL_SURFACES and COMPOSE_DEV_PRINCIPALS disagree about which "
        f"principals exist: declared={sorted(declared)} expected={sorted(expected)}"
    )


@pytest.mark.parametrize("principal", COMPOSE_DEV_PRINCIPALS, ids=lambda p: p.token)
def test_each_portal_declares_the_surfaces_it_lands_on(principal: Any) -> None:
    """Each portal's declared surfaces cover the tables that portal exists for."""
    token = principal.token
    declared = {surface.table.name for surface in DEMO_PORTAL_SURFACES if surface.token == token}
    required = _REQUIRED_SURFACE_TABLES[token]
    assert required <= declared, (
        f"the {principal.portal!r} portal ({token}) declares surfaces "
        f"{sorted(declared)}, which does not cover {sorted(required - declared)}"
    )


def test_a_person_scoped_surface_names_whose_rows_must_be_there() -> None:
    """The ownership half: a subject-scoped surface must name its demo subject.

    This is the assertion the row counts could not make. ``point_ledger_entry``
    holding 187 rows is not the student portal being full; it is 187 rows under
    ``synthetic-student:*`` accounts that no demo login resolves to.
    """
    subjects = {principal.subject for principal in COMPOSE_DEV_PRINCIPALS}
    for surface in DEMO_PORTAL_SURFACES:
        if surface.subject_column is None:
            continue
        assert surface.subject in subjects, (
            f"surface {surface.table.name!r} for {surface.token} is scoped by "
            f"{surface.subject_column!r} but names subject {surface.subject!r}, which is "
            "not a subject any compose demo login resolves to — the rows would be "
            "invisible to the person the portal is for"
        )


def test_every_declared_surface_is_a_counted_table() -> None:
    """No surface may name a table the counter does not read."""
    counted = {entry.table.name for entry in COUNTED_TABLES}
    stray = sorted({surface.table.name for surface in DEMO_PORTAL_SURFACES} - counted)
    assert not stray, f"declared portal surfaces name uncounted tables: {stray}"


def test_portal_surface_is_immutable() -> None:
    """The declaration is data, not state a caller may edit."""
    surface = DEMO_PORTAL_SURFACES[0]
    assert isinstance(surface, PortalSurface)
    with pytest.raises((AttributeError, TypeError)):
        surface.token = "compose-api"  # type: ignore[misc]
