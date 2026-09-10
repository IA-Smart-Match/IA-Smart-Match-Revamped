"""Unit-scoped portal hooks read the unit the *server* granted.

The defect this file exists to stop, observed on the deployed classroom VM:
``/coordinator-portal/outreach`` told a signed-in Speaker Connector that drafts,
speaker invitations and sends were unavailable while ``outreach_draft`` held 4
rows, ``cba_invitation_batch`` 3 and ``cba_invitation`` 9. Nothing was missing.
The retired outreach and invitation hooks once resolved their
unit with ``getConfiguredUnitId()`` — the build-time ``VITE_SMARTMATCH_UNIT_ID``,
which that deployment's bundle is built without — and short-circuited to an
"unavailable" state before issuing a single request.

The rule they now follow is the one ``CoordinatorEvents.tsx`` states in its own
docstring and ``CoordinatorMeetings.tsx`` and ``CoordinatorInvitations.tsx``
already followed: the unit is ``PortalDescriptor.default_unit_id`` off
``GET /v1/me/portals``, and never a build variable. Stakeholder Fix #7 / MM-A01
— the browser asserts no tenant, user, role **or unit**.

Two halves, and both have to hold, because either alone regresses quietly:

* **The source.** No hook here looks the build variable up, and each takes the
  granted unit as an argument that its caller resolves from the grant. This is
  the half that decides whether a request is issued at all.
* **The copy.** No user-facing string names a ``VITE_*`` variable. That is not a
  cosmetic rule. A coordinator cannot set a build variable and cannot rebuild the
  bundle, so such a message describes no state they can act on — and it was
  *false* besides, since the actual cause was an unattached grant. The three
  states stay distinct: ``"idle"`` (no unit granted), ``"unavailable"`` (no
  credential, or a read that failed) and ``"ready"`` with an empty list (the
  server answered, and its answer was none). ADR-0011's rule that an unknown is
  never a zero has the corollary that "we did not ask" is never "there is none".

Assertions are over source text for ``tests/unit/test_cba_rewards_copy.py``'s
reason: the frontend has its own DOM runner, and what Python can own without a
browser is the invariant that survives a refactor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

HOOKS = FRONTEND_SRC / "app" / "hooks"
REWARDS_HOOK = HOOKS / "useRewards.ts"

STUDENT_REWARDS = FRONTEND_SRC / "app" / "pages" / "student" / "StudentRewards.tsx"

#: Hook, and the exact parameter its callers must hand the granted unit through.
UNIT_SCOPED_HOOKS = (
    (REWARDS_HOOK, "useRewards(unitId: string | null)"),
)

#: Every call site of the three, and the portal each resolves its grant for.
UNIT_SCOPED_CALLERS = (
    (STUDENT_REWARDS, "student"),
)


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    The docstrings in these files *do* name ``VITE_SMARTMATCH_UNIT_ID`` — they
    explain at length why the hook stopped reading it, which is exactly the
    prose a later reader needs. Scanning raw text would forbid the explanation
    along with the behaviour, so the comments come out first and only code is
    read. Copy assertions run over the string literals, which survive this.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


@pytest.mark.parametrize(("path", "signature"), UNIT_SCOPED_HOOKS, ids=lambda value: str(value))
def test_the_hook_takes_the_granted_unit_and_looks_up_no_build_variable(
    path: Path, signature: str
) -> None:
    """The unit arrives as an argument; it is never read out of the bundle.

    Both assertions are needed. Dropping ``getConfiguredUnitId`` without taking
    a parameter would leave the hook with no unit at all, and taking a parameter
    while still consulting the variable would leave two answers to which unit a
    screen is about — which on a multi-unit pilot renders one unit's rows under
    another unit's name.
    """
    code = _code_only(path.read_text(encoding="utf-8"))

    assert signature in code, (
        f"{path.name} must take the server-granted unit as an argument: expected {signature!r}"
    )

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID"):
        assert forbidden not in code, (
            f"{path.name} resolves its unit from the browser build again: {forbidden!r}. "
            "The unit is PortalDescriptor.default_unit_id, from GET /v1/me/portals."
        )


@pytest.mark.parametrize(("path", "portal"), UNIT_SCOPED_CALLERS, ids=lambda value: str(value))
def test_the_caller_resolves_the_unit_from_the_server_granted_portal(
    path: Path, portal: str
) -> None:
    """Every call site derives the unit the way the rest of the portal does.

    ``grantedPortal(portalAccess, "<portal>")?.default_unit_id ?? null`` — the
    literal shape ``CoordinatorEvents.tsx``, ``CoordinatorMeetings.tsx`` and
    ``CoordinatorInvitations.tsx`` use. Asserted here rather than left implicit
    because the hooks now accept *any* ``string | null``, so the guard against a
    browser-composed unit moved to the caller along with the responsibility.
    """
    code = _code_only(path.read_text(encoding="utf-8"))

    assert "usePortalAccess" in code
    assert f'grantedPortal(portalAccess, "{portal}")' in code, (
        f"{path.name} must resolve the {portal} grant the way the other portal pages do"
    )
    assert "grant?.default_unit_id ?? null" in code, (
        f"{path.name} must take the unit off the grant, not compose one"
    )

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID"):
        assert forbidden not in code, (
            f"{path.name} sources its unit id from the browser build: {forbidden!r}"
        )


@pytest.mark.parametrize(
    "path",
    [path for path, _ in UNIT_SCOPED_HOOKS] + [path for path, _ in UNIT_SCOPED_CALLERS],
    ids=lambda value: str(value),
)
def test_no_user_facing_string_names_a_build_variable(path: Path) -> None:
    """The copy describes a state the reader is in, not one the builder is in.

    ``"Outreach requires VITE_SMARTMATCH_UNIT_ID and a bearer token"`` was
    rendered to signed-in coordinators on the pilot. It named a build-time
    instruction on a user-facing surface — nothing a coordinator can act on —
    and it was not even the true cause. This scans string literals only, so the
    docstrings may go on explaining the variable by name.
    """
    source = path.read_text(encoding="utf-8")
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', _code_only(source))

    offenders = [text for text in literals if "VITE_" in text]
    assert not offenders, (
        f"{path.name} renders a build-time instruction to a user: {offenders!r}. "
        "Say which state the reader is actually in."
    )


@pytest.mark.parametrize(
    ("path", "constant"),
    (
        (REWARDS_HOOK, "REWARDS_NO_UNIT_REASON"),
    ),
    ids=lambda value: str(value),
)
def test_no_unit_is_its_own_state_and_carries_no_load_error(path: Path, constant: str) -> None:
    """``unitId === null`` is ``"idle"`` with no error, and says so in its own words.

    Three facts are guarded, and each is one the earlier code got wrong:

    * a *named* reason for "the grant carries no unit", separate from the
      credential failure, so the two are not one sentence again;
    * ``setStatus("idle")`` rather than ``setStatus("unavailable")`` — nothing
      was asked for, so nothing failed;
    * ``setLoadError(null)`` on that branch — an error string here would be the
      hook claiming a failure that did not happen, and the consumer would render
      it beside the honest states as though it were one.
    """
    source = path.read_text(encoding="utf-8")
    code = _code_only(source)

    assert f"export const {constant} =" in source, (
        f"{path.name} must name the no-unit state separately from the credential failure"
    )
    assert 'setStatus("idle")' in code, (
        f"{path.name} must treat a missing unit as idle, not as a failed read"
    )
    assert "setLoadError(null)" in code, (
        f"{path.name} must report no error for a state in which nothing was attempted"
    )


@pytest.mark.parametrize(
    ("path", "constant"),
    (
        (STUDENT_REWARDS, "REWARDS_NO_UNIT_REASON"),
    ),
    ids=lambda value: str(value),
)
def test_the_page_renders_the_no_unit_reason_rather_than_an_empty_listing(
    path: Path, constant: str
) -> None:
    """A hook that says "no unit" is not allowed to reach the reader as "none".

    The constant existing is half a fix; a page that swallowed the ``"idle"``
    state would show an empty shelf, which is a claim about a unit there is no
    unit to make.
    """
    code = _code_only(path.read_text(encoding="utf-8"))

    assert constant in code, f"{path.name} must render {constant} for the no-unit state"
