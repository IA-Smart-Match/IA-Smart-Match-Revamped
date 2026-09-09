"""What the rewards surface *says* under CBA, and what it must keep *doing*.

Customer §4 keeps rewards and points ("Rewards / points — **Keep**") and §25
files "Rewards/points refinements" under **P2**. So this file is deliberately
two halves that pull against each other, and both have to hold:

* **Preservation.** The four rewards routes stay mounted and the student page
  keeps its catalog, its server balance, and its redemption control. A P2
  wording pass that quietly removed a working capability would be the failure
  this file exists to make loud.
* **Wording.** The copy a student reads names the CBA role
  (``docs/product/cba-role-presentation.md``), carries no retired §4 term, and
  claims no funding fact the server did not check.

What this file deliberately does **not** re-assert: that ``rewards_ledger`` is
enabled, that the page reads ``useRewards``, and that rewards are not gated by
the removed dues capability. ``tests/unit/test_cba_surface_composition.py``
owns those, and a second copy of an assertion is a second thing to update when
the real one changes.

Why the assertions are over *source text* rather than a rendered page: the
frontend's own runner (``apps/web/legacy-frontend/tests``) renders components,
and duplicating that here would be a second, weaker DOM test. What Python can
own without a browser is the invariant that survives a refactor — that this
page reads its role label from the one map, and that no deleted client-side
points formula came back. Both are properties of the file, so the file is what
is read.

Sources: ``docs/product/cba-smart-match-customer-requirements.md`` §§4, 21, 25;
``docs/product/cba-role-presentation.md``;
``docs/decisions/d6-rewards-budget-decision-record.md`` §3.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"
STUDENT_REWARDS_PATH = FRONTEND_SRC / "app" / "pages" / "student" / "StudentRewards.tsx"
ROLE_LABELS_PATH = FRONTEND_SRC / "lib" / "roleLabels.ts"

if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import bookkeeping
    sys.path.insert(0, str(REPO_ROOT))

from tools.scan_cba_terminology import RULES, strip_ts_comments  # noqa: E402


@pytest.fixture(scope="module")
def page_source() -> str:
    """The student rewards page, as written."""
    return STUDENT_REWARDS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page_copy(page_source: str) -> str:
    """The page with engineering prose blanked out.

    A comment recording *why* the deleted browser-side formula was deleted has
    to be allowed to name it. Only what a reader could see is asserted on.
    """
    return strip_ts_comments(page_source)


# ---------------------------------------------------------------------------
# Preservation — the capability is not what a wording pass may spend
# ---------------------------------------------------------------------------


def test_the_rewards_routes_are_still_mounted():
    """A blanket route disable is the anti-pattern this card names first."""
    pytest.importorskip("fastapi")
    from smartmatch_api.main import app

    # Read through the generated schema rather than ``app.routes``: this
    # FastAPI version wraps an included router in one opaque entry, so walking
    # the route list would silently see none of these three.
    paths = set(app.openapi()["paths"])
    assert "/v1/units/{unit_id}/rewards" in paths
    assert "/v1/units/{unit_id}/redemptions" in paths
    assert "/v1/units/{unit_id}/redemptions/{redemption_id}/decision" in paths


def test_the_page_still_renders_the_server_catalog_and_balance(page_source: str):
    """Server values, listed and folded — not a constant and not a formula."""
    assert "catalog.items.map" in page_source
    assert "catalog.balance" in page_source


def test_the_page_still_offers_a_redemption_request(page_source: str):
    """The control stays reachable: this card gates nothing that works."""
    assert "requestItem(" in page_source
    assert "Request redemption" in page_source


@pytest.mark.parametrize(
    "formula",
    [
        "studentPoints",
        "STUDENT_REWARD_CATALOG",
        "getStudentTotalPoints",
        "attendance_streak",
        "events_attended",
    ],
)
def test_no_deleted_client_side_points_formula_came_back(page_copy: str, formula: str):
    """ADR-0013: a balance with no history behind it cannot say why it is that.

    The progress bar's percentage is not caught by this and should not be: it
    is a width computed from ``points_still_needed``, a number the server sent,
    not a balance the browser derived. Comments are stripped first: the header
    naming the formulas it deleted is the record of the deletion, not a
    reintroduction of it.
    """
    assert formula not in page_copy


# ---------------------------------------------------------------------------
# Wording — CBA vocabulary, and no claim the server did not check
# ---------------------------------------------------------------------------


def test_the_page_carries_no_retired_terminology(page_copy: str):
    """The §4 sweep, applied to this page by the shipped scanner's own rules."""
    offenders = [
        (rule.code, line.strip())
        for rule in RULES
        for line in page_copy.splitlines()
        if rule.regex.search(line)
    ]
    assert offenders == []


def test_visible_copy_names_no_stored_role_string(page_copy: str):
    """``coordinator`` is a row in the database, not a person's name.

    ``docs/product/cba-role-presentation.md`` maps the stored ``coordinator``
    role to the visible label **Speaker Connector**. A student reading a
    redemption ticket should be told who reviews it in the vocabulary the rest
    of the CBA product uses.

    The one permitted occurrence is the *key* the label is looked up by —
    ``ROLE_PRESENTATION.coordinator`` — because the stored role string is
    exactly what that map is keyed on. Blanking it before the search is the
    difference between "no stored role in the copy" and "no stored role
    anywhere", and only the first is true or desirable.
    """
    without_lookup = re.sub(r"ROLE_PRESENTATION\.coordinator", "", page_copy)
    assert re.search(r"coordinator", without_lookup, re.IGNORECASE) is None


def test_the_page_reads_its_role_label_from_the_shared_map(page_source: str):
    """One map, read in two places — never a fourth spelling of a persona."""
    assert "roleLabels" in page_source
    assert "ROLE_PRESENTATION" in page_source


def test_the_shared_map_still_calls_the_stored_coordinator_role_speaker_connector():
    """Guards the assumption the assertion above rests on."""
    source = ROLE_LABELS_PATH.read_text(encoding="utf-8")
    assert (
        re.search(r"coordinator:\s*\{[^}]*roleLabel:\s*\"Speaker Connector\"", source) is not None
    )


def test_the_page_claims_no_confirmed_institutional_funding(page_copy: str):
    """D6 §3: the $5,000 ceiling is a placeholder, explicitly *not* ratified.

    What the server checks per row is ``funded IS TRUE`` and a named
    ``budget_owner_id``. "Confirmed funding" reads as an institutional promise
    that record does not make; the row-level fact does, so the copy states the
    row-level fact.
    """
    assert "confirmed funding" not in page_copy.lower()
    assert "named budget owner" in page_copy
