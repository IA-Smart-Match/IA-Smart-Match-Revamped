"""The registered-metrics surfaces read the unit the *server* granted.

The sibling of ``test_frontend_granted_unit_contract.py``, for the fourth hook
that had the defect that file exists to stop. ``useOutreach``,
``useSpeakerInvitations`` and ``useRewards`` were fixed in PR #139;
``useUnitMetrics`` was not, and it is the hook behind every registered metric
on the IA admin surfaces — the opportunities count, the five pipeline funnel
tiles, and the dashboard's headline cards.

It resolved its unit with ``getConfiguredUnitId()``, the build-time
``VITE_SMARTMATCH_UNIT_ID``. The deployed pilot VM's bundle is built without
that variable, so the hook short-circuited to ``"unavailable"`` before issuing
a single request, and the reason it handed the reader was:

    "Registered metrics require VITE_SMARTMATCH_UNIT_ID and a bearer token
    (VITE_SMARTMATCH_BEARER_TOKEN or session storage)."

Two things wrong with that sentence, and the second is the worse one. It names
build variables at somebody holding a browser, who cannot set them and cannot
rebuild the bundle. And it was false: the account had a unit, granted by the
server, that nothing on the page had asked for.

## Why a separate file rather than a parameter added to #139's

That file's shape is the three hooks it covers: each holds its own state with
``setStatus``/``setLoadError``, and its assertions are written against those
calls. ``useUnitMetrics`` derives its status from a TanStack ``useQuery``
result and assigns a local, so the same assertions could only be made to cover
it by loosening them — which would weaken the guard on the three hooks that do
pass them today. The invariant is shared; the source shape is not.

## Why these are portal surfaces, which is the part that needed deciding

``Dashboard.tsx``, ``Pipeline.tsx`` and ``Opportunities.tsx`` sit under the
pathless ``Layout`` route rather than one of the three portal shells, so
"leave the build variable, it is a legitimate deployment input for an admin
surface" was a real option rather than a cop-out. It is wrong, and
``services/api/smartmatch_api/routers/portals.py`` is what settles it:
``_PORTAL_FOR_ROLE`` maps the stored ``admin`` role to the portal ``admin``
with ``home_path: "/dashboard"``. ``PortalGate`` renders that ``home_path`` as
a link. ``/dashboard`` is the admin portal's home screen, reachable by an
ordinary signed-in pilot account, and ``PortalKind`` in ``lib/principal.ts``
has carried ``"admin"`` since the mapping existed. So the unit these screens
are about is the unit the server granted the account, exactly as for the other
three portals — and the assertions below pin that resolution rather than
merely forbidding the old one.

Assertions are over source text for ``test_frontend_granted_unit_contract.py``'s
reason: the frontend has its own DOM runner, and what Python can own without a
browser is the invariant that survives a refactor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

METRICS_HOOK = FRONTEND_SRC / "app" / "hooks" / "useUnitMetrics.ts"
FUNNEL_TILES = FRONTEND_SRC / "app" / "components" / "PipelineFunnelTiles.tsx"
DASHBOARD_PAGE = FRONTEND_SRC / "app" / "pages" / "Dashboard.tsx"
PIPELINE_PAGE = FRONTEND_SRC / "app" / "pages" / "Pipeline.tsx"
OPPORTUNITIES_PAGE = FRONTEND_SRC / "app" / "pages" / "Opportunities.tsx"

#: The pages that hold a grant and resolve the unit off it.
GRANT_HOLDING_PAGES = (DASHBOARD_PAGE, PIPELINE_PAGE, OPPORTUNITIES_PAGE)

#: Every file this fix touches, for the copy sweep.
METRICS_SURFACES = (METRICS_HOOK, FUNNEL_TILES, *GRANT_HOLDING_PAGES)


def _code_only(source: str) -> str:
    """Strip line comments and then JSDoc blocks before scanning.

    These files *do* name ``VITE_SMARTMATCH_UNIT_ID`` at length — they explain
    why the hook stopped reading it, which is exactly the prose a later reader
    needs. Scanning raw text would forbid the explanation along with the
    behaviour, so comments come out first and only code is read. String
    literals survive this, which is what the copy assertion needs.

    **Line comments come out first, and the order is load-bearing.**
    ``test_frontend_granted_unit_contract.py`` does it the other way round and
    would silently mis-read ``Dashboard.tsx``: line 384 there is the line
    comment ``// ... the legacy /api/*`` routes, whose ``/*`` opens a block
    comment as far as a regex is concerned, and the next ``*/`` in the file is
    130 lines later — swallowing the whole unit-resolution block this module
    asserts on. Stripping ``//`` lines first removes the false opener before
    anything can pair with it. A false *negative* of that kind is the failure
    mode to design against here: it makes a guard quietly assert nothing.
    """
    without_line_comments = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )
    return re.sub(r"/\*.*?\*/", "", without_line_comments, flags=re.DOTALL)


def test_the_metrics_hook_takes_the_granted_unit_and_looks_up_no_build_variable() -> None:
    """The unit arrives as an argument; it is never read out of the bundle.

    Both halves are asserted, because either alone regresses quietly. Dropping
    ``getConfiguredUnitId`` without taking a parameter would leave the hook
    with no unit at all; taking a parameter while still consulting the variable
    would leave two answers to which unit a screen is about, which on a
    multi-unit pilot renders one unit's metrics under another unit's name.

    The signature is pinned whole, ``reloadToken`` included, because parameter
    *order* is the part a caller can get wrong silently: the hook's only
    argument used to be ``reloadToken``, and a call site left un-migrated would
    hand a number where the unit now goes.
    """
    code = _code_only(METRICS_HOOK.read_text(encoding="utf-8"))

    assert "useUnitMetrics(unitId: string | null, reloadToken = 0)" in code, (
        "useUnitMetrics must take the server-granted unit as its first argument"
    )

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID"):
        assert forbidden not in code, (
            f"useUnitMetrics resolves its unit from the browser build again: {forbidden!r}. "
            "The unit is PortalDescriptor.default_unit_id, from GET /v1/me/portals."
        )


@pytest.mark.parametrize("path", GRANT_HOLDING_PAGES, ids=lambda value: str(value.name))
def test_the_page_resolves_the_unit_from_the_server_granted_admin_portal(path: Path) -> None:
    """Every call site derives the unit the way the rest of the product does.

    ``grantedPortal(portalAccess, "admin")?.default_unit_id ?? null`` — the
    literal shape ``CoordinatorEvents.tsx``, ``CoordinatorOutreach.tsx`` and
    ``StudentRewards.tsx`` use for their own portals. Asserted here rather than
    left implicit because the hook now accepts *any* ``string | null``, so the
    guard against a browser-composed unit moved to the caller along with the
    responsibility.

    The portal is pinned as ``"admin"`` specifically. A page that resolved some
    other portal's grant would type-check and would read a unit — the wrong
    one — which is the failure mode a bare "resolves something from the grant"
    assertion would wave through.
    """
    code = _code_only(path.read_text(encoding="utf-8"))

    assert "usePortalAccess" in code, f"{path.name} must read the portal mapping"
    assert 'grantedPortal(portalAccess, "admin")' in code, (
        f"{path.name} must resolve the admin grant the way the portal pages do; "
        "_PORTAL_FOR_ROLE maps the stored `admin` role to home_path /dashboard"
    )
    assert "grant?.default_unit_id ?? null" in code, (
        f"{path.name} must take the unit off the grant, not compose one"
    )

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID"):
        assert forbidden not in code, (
            f"{path.name} sources its unit id from the browser build: {forbidden!r}"
        )


def test_the_funnel_tiles_require_the_unit_rather_than_defaulting_it() -> None:
    """``PipelineFunnelTiles`` has no grant, so its caller must supply one.

    The component is rendered inside ``Dashboard.tsx`` and ``Pipeline.tsx`` and
    holds no portal grant of its own. ``unitId?: string | null`` would let a
    third caller mount the funnel having answered nothing and get five silently
    unknown tiles — a caller's ignorance rendered as an empty state. The
    required form makes it a compile error instead, while still admitting the
    honest ``null``.

    The negative assertion is the load-bearing one: a later "make it optional
    for convenience" edit is exactly the regression this pins, so the optional
    spelling is forbidden by name rather than merely left unasserted.
    """
    code = _code_only(FUNNEL_TILES.read_text(encoding="utf-8"))

    assert "unitId: string | null;" in code, (
        "PipelineFunnelTiles must declare a required unitId prop"
    )
    assert "unitId?:" not in code, (
        "PipelineFunnelTiles must not default its unit away; a caller with no grant "
        "should fail to compile, not render five unknown tiles"
    )
    assert "useUnitMetrics(unitId, reloadToken)" in code, (
        "PipelineFunnelTiles must hand the prop straight to the hook"
    )

    for path in (DASHBOARD_PAGE, PIPELINE_PAGE):
        caller = _code_only(path.read_text(encoding="utf-8"))
        assert "unitId={unitId}" in caller, (
            f"{path.name} must pass its granted unit down to PipelineFunnelTiles"
        )


@pytest.mark.parametrize("path", METRICS_SURFACES, ids=lambda value: str(value.name))
def test_no_user_facing_string_names_a_build_variable(path: Path) -> None:
    """The copy describes a state the reader is in, not one the builder is in.

    "Registered metrics require VITE_SMARTMATCH_UNIT_ID and a bearer token
    (VITE_SMARTMATCH_BEARER_TOKEN or session storage)" was rendered under every
    metric on the pilot's dashboard. It named a build-time instruction on a
    user-facing surface — nothing a reader can act on — and it was not the true
    cause either. This scans string literals only, so the docstrings may go on
    explaining the variable by name.
    """
    source = path.read_text(encoding="utf-8")
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', _code_only(source))

    offenders = [text for text in literals if "VITE_" in text]
    assert not offenders, (
        f"{path.name} renders a build-time instruction to a user: {offenders!r}. "
        "Say which state the reader is actually in."
    )


def test_no_unit_is_its_own_state_and_carries_no_load_error() -> None:
    """``unitId === null`` is ``"idle"``, and the branch reports no failure.

    Three facts, each one the earlier code got wrong:

    * a *named* reason for "the grant carries no unit", separate from the
      credential failure, so the two are not one sentence again;
    * ``status = "idle"`` rather than ``status = "unavailable"`` — nothing was
      asked for, so nothing failed;
    * no ``loadError`` assignment on that branch. An error string here would be
      the hook claiming a failure that did not happen, and the consumer would
      render it beside the honest states as though it were one.

    The third is asserted over the branch body rather than the whole file,
    since ``loadError`` is legitimately assigned on the two branches beside it.
    """
    source = METRICS_HOOK.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "export const METRICS_NO_UNIT_REASON =" in source, (
        "the no-unit state must be named separately from the credential failure"
    )
    assert "export const METRICS_UNAVAILABLE_REASON =" in source

    branch = re.search(r"if \(unitId === null\) \{(.*?)\n  \} else", code, flags=re.DOTALL)
    assert branch is not None, "useUnitMetrics must branch on `unitId === null` explicitly"
    body = branch.group(1)

    assert 'status = "idle";' in body, (
        "a missing unit is idle, not a failed read: nothing was attempted"
    )
    assert "loadError" not in body, (
        "the no-unit branch must report no error; nothing was attempted, so nothing failed"
    )


def test_the_three_no_data_facts_stay_three_separate_sentences() -> None:
    """Loading, no-unit, and no-credential are never collapsed into one another.

    ``grantedPortal()`` answers ``null`` both while ``GET /v1/me/portals`` is in
    flight and when the answer carried no grant, so a surface that rendered the
    no-unit reason for every ``null`` would tell a reader their membership is
    missing during the second it takes to find out that it is not. ADR-0011's
    rule that an unknown is never a zero has the corollary that "we have not
    asked yet" is never "there is nothing to ask about".

    Pinned on every surface, not just the hook: the hook cannot tell the two
    nulls apart by construction — that is why the distinction is the caller's —
    so the guard has to live where the distinction is drawn.
    """
    hook = METRICS_HOOK.read_text(encoding="utf-8")
    assert "export const METRICS_UNIT_RESOLVING_REASON =" in hook, (
        "the in-flight case needs its own words, or it borrows the no-unit case's"
    )

    for path in (FUNNEL_TILES, *GRANT_HOLDING_PAGES):
        code = _code_only(path.read_text(encoding="utf-8"))
        assert "unitResolving" in code, (
            f"{path.name} must distinguish a mapping still in flight from a grant "
            "that carries no unit"
        )
        assert "METRICS_UNIT_RESOLVING_REASON" in code, (
            f"{path.name} must say the in-flight case in the shared words"
        )
        assert "metricsNoUnitReason" in code, (
            f"{path.name} must render the resolved no-unit reason rather than an empty state"
        )


def test_no_surface_invents_a_unit_id_to_fall_back_on() -> None:
    """ADR-0011 rule 1 applied to the identifier rather than the number.

    A ``?? "some-uuid"`` anywhere in this chain would restore the whole defect
    in a new place: the browser would name a unit the server never granted it,
    every request would be refused, and the refusal would read as an outage.
    ``"unscoped"`` is exempt and is deliberately checked for — it is a cache-key
    placeholder for a query that is ``enabled: false``, never a path segment.
    """
    code = _code_only(METRICS_HOOK.read_text(encoding="utf-8"))

    assert 'unitId ?? "unscoped"' in code, (
        "the disabled-query cache key placeholder is expected to stay `unscoped`"
    )

    fallbacks = re.findall(r'unitId\s*\?\?\s*"([^"]*)"', code)
    assert set(fallbacks) <= {"unscoped"}, (
        f"a unit id is being invented as a fallback: {sorted(set(fallbacks))!r}. "
        "A value with no evidence renders as unknown, never as a guess."
    )
