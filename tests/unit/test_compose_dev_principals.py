"""The compose dev-principal map and the rows it resolves to are one fixture.

``docker-compose.yml`` holds ``SMARTMATCH_DEV_PRINCIPALS`` — bearer token to
external subject — and ``tools/seed_pilot_principals.py`` holds the accounts and
memberships those subjects name. Neither half can see the other at runtime, and
a drift between them fails in exactly the wrong way: a token in the map with no
seeded subject authenticates as nobody and answers ``401``, which a stakeholder
discovers by clicking, and a seeded subject with no token is an account nothing
can reach. Both are asserted here instead.

Read as text rather than through a YAML parser, deliberately. What has to be
true is that the *literal in the file* is the literal the API receives, and a
parser that resolved anchors would happily agree with itself about a value the
file no longer contains. ``docker compose config`` is the runtime check and
``scripts/compose_smoke.sh`` already runs it; this is the static one.

This file asserts nothing about permission, and could not: a token yields a
bare subject, and ``PrincipalRepository.load_by_subject`` reads tenant,
membership and grants from rows the compose file cannot write. What it does
assert is that the four principals are four *different* roles — the point of
the set is one principal per portal, and two entries sharing a role would leave
a portal unenterable while looking complete.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

# `tools/` on the path, not the repository root: seed_pilot_principals.py is
# run by compose with PYTHONPATH=/home/smartmatch, where its sibling import of
# `seed_pilot` resolves as a bare module. Importing it as `tools.…` instead
# would exercise a module shape the container never runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_principals import (  # noqa: E402
    COMPOSE_DEV_PRINCIPALS,
    SEEDED_BY_THIS_TOOL,
    DevPrincipal,
)
from smartmatch_api.routers.portals import _PORTAL_FOR_ROLE  # noqa: E402

#: The one line in ``docker-compose.yml`` that carries the whole map. Anchored
#: to the key so a JSON object appearing anywhere else in the file cannot stand
#: in for it.
_MAP_PATTERN = re.compile(
    r"^\s*api_dev_principals_json:\s*&compose_api_dev_principals_json\s*'(?P<json>\{.*\})'\s*$",
    re.MULTILINE,
)

#: The length at which ``tools/scan_forbidden.py``'s ``hard-coded-credential``
#: rule starts treating a quoted literal as credential-shaped. Every dev token
#: stays under it — not to evade the rule, but because a local-only identifier
#: that needs sixteen characters of entropy has stopped being one.
_CREDENTIAL_SHAPE_THRESHOLD = 16


def _compose_dev_principals() -> dict[str, str]:
    """The ``SMARTMATCH_DEV_PRINCIPALS`` map exactly as the file states it."""
    source = COMPOSE_FILE.read_text(encoding="utf-8")
    match = _MAP_PATTERN.search(source)
    assert match is not None, (
        "docker-compose.yml no longer carries an `api_dev_principals_json` "
        "anchor holding a single-quoted JSON object. That anchor is what the "
        "`api` service aliases into SMARTMATCH_DEV_PRINCIPALS; if it moved, "
        "this test has to move with it rather than be deleted"
    )
    parsed = json.loads(match.group("json"))
    assert isinstance(parsed, dict)
    return parsed


def test_every_compose_token_resolves_to_a_seeded_subject() -> None:
    """The two halves of the fixture are the same fixture."""
    expected = {principal.token: principal.subject for principal in COMPOSE_DEV_PRINCIPALS}

    assert _compose_dev_principals() == expected, (
        "docker-compose.yml's SMARTMATCH_DEV_PRINCIPALS and "
        "tools/seed_pilot_principals.py's COMPOSE_DEV_PRINCIPALS disagree. A "
        "token here with no subject there is a 401 a stakeholder finds by "
        "clicking; a subject there with no token here is an account nothing "
        "can reach"
    )


def test_the_four_principals_open_the_four_portals() -> None:
    """One principal per portal, and no portal claimed twice.

    ``_PORTAL_FOR_ROLE`` is the routing table ``GET /v1/me/portals`` answers
    from, so comparing against it is comparing against what the API will
    actually report rather than against a list restated here.
    """
    roles = [principal.role for principal in COMPOSE_DEV_PRINCIPALS]
    assert len(set(roles)) == len(roles), (
        f"two compose principals share a role ({sorted(roles)}); the set exists "
        "to open every portal, and a duplicate leaves one unenterable while "
        "looking complete"
    )
    assert set(roles) == set(_PORTAL_FOR_ROLE), (
        f"the compose principals cover the roles {sorted(set(roles))}, and "
        f"routers/portals.py maps {sorted(_PORTAL_FOR_ROLE)}. A role the "
        "product has a portal for and the pilot has no principal for cannot be "
        "clicked through at all"
    )
    for principal in COMPOSE_DEV_PRINCIPALS:
        portal, _home_path = _PORTAL_FOR_ROLE[principal.role]
        assert principal.portal == portal, (
            f"{principal.subject!r} records portal={principal.portal!r} but its "
            f"role opens {portal!r}; the field is documentation for an operator "
            "and a wrong one is worse than none"
        )


def test_the_coordinator_is_seeded_by_the_other_one_shot() -> None:
    """``seed`` owns the coordinator; ``seed-principals`` owns the rest.

    Two services writing the same row would work — ``seed_pilot`` is idempotent
    for identical data — right up until they disagreed about an email, at which
    point the second would fail on the first's row.
    """
    seeded_roles = {principal.role for principal in SEEDED_BY_THIS_TOOL}
    assert seeded_roles == {"student", "volunteer", "admin"}

    source = COMPOSE_FILE.read_text(encoding="utf-8")
    coordinator = next(p for p in COMPOSE_DEV_PRINCIPALS if p.role == "coordinator")
    assert f'"{coordinator.subject}"' in source, (
        f"the `seed` service no longer names {coordinator.subject!r}; the "
        "coordinator half of the map has lost the one-shot that creates it"
    )
    assert coordinator.email in source


@pytest.mark.parametrize("principal", COMPOSE_DEV_PRINCIPALS, ids=lambda p: p.role)
def test_no_pilot_identity_could_be_mistaken_for_a_real_one(principal: DevPrincipal) -> None:
    """Synthetic on its face: ``.invalid`` addresses and short, plain tokens.

    ``.invalid`` is reserved by RFC 2606 and resolves nowhere, so no message
    this pilot composes can reach a person. The token check is the compose
    header note's rule, held as a test rather than as a habit.
    """
    assert principal.email.endswith("@example.invalid"), (
        f"{principal.email!r} is not an @example.invalid address; a synthetic "
        "pilot must hold no address that could reach anybody"
    )
    assert len(principal.token) < _CREDENTIAL_SHAPE_THRESHOLD, (
        f"the dev token {principal.token!r} is {len(principal.token)} "
        f"characters. Past {_CREDENTIAL_SHAPE_THRESHOLD} it reads as an "
        "entropy-bearing credential to tools/scan_forbidden.py and to a person; "
        "a value that needs to be that long is not local-only test data any more"
    )
    assert re.fullmatch(r"[a-z][a-z0-9-]*", principal.token), (
        f"the dev token {principal.token!r} is not a plain lowercase "
        "identifier. Nothing here may carry the shape of a real credential"
    )
    assert principal.subject.startswith("compose-pilot-")
