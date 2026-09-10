"""A pilot dataset rebuild must leave every portal principal reachable.

``scripts/reset_pilot_dataset.sh`` drops the database and rebuilds it, and then
starts an API of its own with a ``SMARTMATCH_DEV_PRINCIPALS`` map it composes
in-line. Two halves have to hold for a portal to open afterwards:

* the **token** has to be in that map — ``Settings`` reads the environment once
  at process start, so a token missing from it authenticates as nobody and
  answers ``401``;
* the **subject** the token resolves to has to have been seeded, because
  ``PrincipalRepository.load_by_subject`` reads tenant, membership and grants
  from rows the map cannot write.

``tools/seed_pilot_principals.COMPOSE_DEV_PRINCIPALS`` is the whole set — one
principal per portal — and ``tests/unit/test_compose_dev_principals.py``
already pins ``docker-compose.yml`` to it. This file pins the *rebuild script*
to the same table, which is the half that was missing: the script composed its
map from its own coordinator token plus the feedback cohort only, so the three
principals its own ``make seed-pilot-principals`` step had just seeded —
student, Event Host and admin — had no token that reached them.

The map is not restated here. The script's own embedded snippet is extracted
and **executed**, exactly as the script runs it and with the ``PYTHONPATH`` the
script gives it, so a snippet that no longer imports what it needs fails here
rather than at rebuild time.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = REPO_ROOT / "scripts" / "reset_pilot_dataset.sh"

sys.path.insert(0, str(REPO_ROOT / "tools"))

from pilot_dataset_plan import feedback_dev_principals  # noqa: E402
from seed_pilot_principals import (  # noqa: E402
    COMPOSE_DEV_PRINCIPALS,
    SEEDED_BY_THIS_TOOL,
)

#: The step-0b command, captured whole: the ``PYTHONPATH`` it runs under and the
#: heredoc body it feeds to the interpreter. Anchored to ``DEV_PRINCIPALS=`` so
#: no other python heredoc in the script can stand in for it.
_STEP_0B = re.compile(
    r'^DEV_PRINCIPALS="\$\(\s*\n'
    r'\s*PYTHONPATH="(?P<pythonpath>[^"]*)"[^\n]*<<\'PYEOF\'\n'
    r"(?P<body>.*?)\nPYEOF\n",
    re.MULTILINE | re.DOTALL,
)

_DOMAIN_PATH = re.compile(r'^DOMAIN_PATH="(?P<value>[^"]*)"\s*$', re.MULTILINE)

#: The script's own defaults for the operator-configurable coordinator, which
#: step 0b passes to the snippet as ``argv[1:]``.
_DEFAULT = r'^{name}="\$\{{{name}:-(?P<value>[^}}]*)\}}"\s*$'


def _script_source() -> str:
    return RESET_SCRIPT.read_text(encoding="utf-8")


def _script_default(name: str) -> str:
    match = re.search(_DEFAULT.format(name=name), _script_source(), re.MULTILINE)
    assert match is not None, f"scripts/reset_pilot_dataset.sh no longer defaults {name}"
    return match.group("value")


def _rebuild_dev_principals() -> dict[str, str]:
    """Run the script's own step-0b snippet and return the map it prints."""
    source = _script_source()
    step = _STEP_0B.search(source)
    assert step is not None, (
        "scripts/reset_pilot_dataset.sh no longer computes DEV_PRINCIPALS from a "
        "`PYEOF` heredoc. That snippet is the whole dev-principal map the "
        "rebuilt appliance boots with; if it moved, this test has to move with "
        "it rather than be deleted"
    )
    domain_path = _DOMAIN_PATH.search(source)
    assert domain_path is not None, "scripts/reset_pilot_dataset.sh no longer sets DOMAIN_PATH"

    pythonpath = step.group("pythonpath").replace("$DOMAIN_PATH", domain_path.group("value"))
    assert "$" not in pythonpath, (
        f"step 0b's PYTHONPATH {pythonpath!r} interpolates something this test "
        "cannot expand; expand it here rather than guessing"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ":".join(
        str(REPO_ROOT / part) for part in pythonpath.split(":") if part
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-",
            _script_default("COORDINATOR_TOKEN"),
            _script_default("COORDINATOR_SUBJECT"),
        ],
        input=step.group("body"),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=environment,
    )
    assert completed.returncode == 0, (
        f"the rebuild script's dev-principal snippet failed to run:\n{completed.stderr}"
    )
    parsed = json.loads(completed.stdout)
    assert isinstance(parsed, dict)
    return parsed


def test_a_rebuild_preserves_every_portal_principal() -> None:
    """Every compose token still reaches its subject after a rebuild.

    This is the whole point of the file. The rebuild script seeds the student,
    Event Host and admin rows itself, one step after composing this map; a map
    that omits their tokens leaves three of the four portals answering ``401``
    to a stakeholder who was told the appliance was rebuilt.
    """
    rebuilt = _rebuild_dev_principals()
    missing = {
        principal.token: principal.subject
        for principal in COMPOSE_DEV_PRINCIPALS
        if rebuilt.get(principal.token) != principal.subject
    }
    assert not missing, (
        f"a rebuild would boot the API without {sorted(missing)}. Every entry "
        "in tools/seed_pilot_principals.COMPOSE_DEV_PRINCIPALS is one portal's "
        "only way in, and a token absent from SMARTMATCH_DEV_PRINCIPALS "
        "authenticates as nobody: the portal answers 401 and the rebuild looks "
        "like it worked"
    )


def test_a_rebuild_keeps_the_operator_coordinator_and_the_feedback_cohort() -> None:
    """Merging, never replacing: the tokens the rebuild already needed survive.

    The generator authenticates as the operator-configurable coordinator, and
    every feedback student writes its own rating, so widening the map must not
    have narrowed it.
    """
    rebuilt = _rebuild_dev_principals()
    assert rebuilt[_script_default("COORDINATOR_TOKEN")] == _script_default("COORDINATOR_SUBJECT")
    for token, subject in feedback_dev_principals().items():
        assert rebuilt[token] == subject, (
            f"the feedback student token {token!r} is no longer in the rebuild "
            "map; the generator's Phase B ratings would all 401"
        )


def test_no_token_in_the_rebuild_map_resolves_to_an_unseeded_subject() -> None:
    """The other half of the fixture: a subject in the map is a subject seeded.

    A token whose subject nothing creates is the same ``401`` from the other
    direction, and is how the coordinator half of the compose map was left
    unreachable: ``make seed-pilot-principals`` deliberately does not seed a
    coordinator, so the script has to.
    """
    source = _script_source()
    seeded_by_the_tool = {principal.subject for principal in SEEDED_BY_THIS_TOOL}
    feedback_subjects = set(feedback_dev_principals().values())

    for token, subject in _rebuild_dev_principals().items():
        if subject in seeded_by_the_tool or subject in feedback_subjects:
            continue
        assert subject in source, (
            f"the rebuild map resolves {token!r} to {subject!r}, and nothing in "
            "the script seeds that subject: not `make seed-pilot-principals` "
            "(which never seeds a coordinator) and not a `make seed-pilot` call "
            "naming it. That token authenticates as nobody"
        )


@pytest.mark.parametrize("principal", COMPOSE_DEV_PRINCIPALS, ids=lambda principal: principal.role)
def test_the_rebuild_seeds_a_row_for_every_portal_principal(principal) -> None:
    """A token is only half of a login; the row it resolves to is the other."""
    source = _script_source()
    if principal in SEEDED_BY_THIS_TOOL:
        assert "seed-pilot-principals" in source, (
            "the rebuild script no longer runs `make seed-pilot-principals`, "
            f"which is what creates the {principal.role} row"
        )
        return
    assert principal.subject in source, (
        f"{principal.subject!r} is in the compose principal table but the "
        "rebuild script never names it. `make seed-pilot-principals` refuses "
        "to seed a coordinator on purpose, so a rebuild that does not seed this "
        "one leaves its token resolving to no row at all"
    )
