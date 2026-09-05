"""Terminology contract for CBA-visible copy (customer §4, §25 P0).

The customer replaced an institutional vocabulary, not a colour scheme. §4 is a
table of old-term/new-term pairs, and §25 lists seven of those renames as P0.
This module holds the executable half of that decision in three layers:

1. **Self-tests for the scanner** (``tools/scan_cba_terminology.py``). A gate
   nobody has verified is worse than no gate, so the rules are fed known-bad
   copy and asserted to fire, and known-good copy and asserted to stay quiet.
2. **A repository sweep**, asserting the scanner finds nothing in the surfaces
   it is scoped to.
3. **Positive assertions**: the four names the customer asked for by name
   (*CBA*, *Student Portal*, *Connector Dashboard*, *Speaker Request*) appear
   on the surfaces that carry them, and *Speaker* is preserved.

**What this contract deliberately does not touch**, because a scanner that
sweeps every occurrence of a word is a blind global replace wearing a test's
clothing:

* The backend authorization ``membership`` record and its API fields
  (``memberships``, ``MembershipResponse``, ``org_unit_path``). The capability
  policy is explicit that ``chapter_membership_dues`` is a *product concept*
  and "never the backend ``membership`` record"
  (``docs/product/cba-capability-policy.md``). Renaming an authorization table
  is authorized by nothing.
* The ``ia_west_legacy`` product scope and the ``ia_west_chapter`` outreach
  voice. Both are wire values in a server contract; the first exists *because*
  CBA is the other product.
* The Member-Inquiry / membership-interest narrative. CBA does not rename this
  concept — the policy switches it **off**
  (``member_inquiry_narrative``/``chapter_membership_dues``), and the removal
  belongs to ``CBA-SCOPE-COMPOSITION``. Renaming a gated concept would disguise
  a removal as a rename, which is worse than leaving the old word visible.
* Historical documents, decision records, and the legacy-baseline citations
  that name ``Nebiux-Team-IA-West-SmartMatch@bdce024``. History is not copy.
* Stored role strings and role labels (``volunteer``, ``coordinator``), which
  ``CBA-ROLE-PRESENTATION`` owns.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

_spec = importlib.util.spec_from_file_location(
    "scan_cba_terminology", REPO_ROOT / "tools" / "scan_cba_terminology.py"
)
assert _spec and _spec.loader
scan_cba_terminology = importlib.util.module_from_spec(_spec)
sys.modules["scan_cba_terminology"] = scan_cba_terminology
_spec.loader.exec_module(scan_cba_terminology)

RULES = {rule.code: rule for rule in scan_cba_terminology.RULES}


def _fires(code: str, source: str) -> bool:
    return bool(RULES[code].regex.search(source))


def _read(relative: str) -> str:
    return (WEB_SRC / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Layer 1: the scanner catches the terms §4 retires
# ---------------------------------------------------------------------------


def test_catches_the_institutional_name() -> None:
    assert _fires("ia-west", '<p className="text-xs">IA West Chapter</p>')
    assert _fires("ia-west", "IA-West Smart Match")
    assert _fires("insights-association", 'subject: "Welcome to Insights Association"')


def test_catches_chapter_as_an_institution() -> None:
    assert _fires("chapter", "Live campus engagements and chapter events")
    assert _fires("chapter-admin", "<span>Chapter Admin Dashboard</span>")


def test_catches_membership_and_dues_as_a_product_concept() -> None:
    assert _fires("membership-dues", "Membership dues are payable each term")
    assert _fires("membership-dues", "Chapter membership renewal")


def test_catches_the_retired_portal_and_opportunity_names() -> None:
    assert _fires("member-portal", "<span>Member Portal</span>")
    assert _fires("volunteer-opportunity", "Browse volunteer opportunities")


# ---------------------------------------------------------------------------
# Layer 1b: the scanner stays quiet on the things §4 keeps
# ---------------------------------------------------------------------------


def test_does_not_fire_on_the_backend_authorization_membership_record() -> None:
    """``membership`` the authorization row is untouched by a terminology sweep."""
    source = (
        "export function activeMemberships(me: MeResponse): MembershipResponse[] {\n"
        "  return me.memberships.filter((membership) => membership.is_active);\n"
        "}"
    )
    for rule in scan_cba_terminology.RULES:
        assert not rule.regex.search(source), (
            f"rule {rule.code!r} matches the authorization membership record; "
            "the capability policy forbids renaming it."
        )


def test_does_not_fire_on_wire_values_that_name_the_legacy_product() -> None:
    source = (
        'export type OutreachEmailVoice = "school_coordinator" | "ia_west_chapter";\n'
        "  chapter_membership_dues: false,\n"
        '  ia_west_legacy: "ia_west_legacy",\n'
    )
    for rule in scan_cba_terminology.RULES:
        assert not rule.regex.search(source), (
            f"rule {rule.code!r} matches a server-contract wire value; renaming "
            "an API field is out of scope for a copy sweep."
        )


def test_does_not_fire_on_the_preserved_speaker_vocabulary() -> None:
    source = "CBA Speaker Network - Speaker Request - Speaker Connector - Student Portal"
    for rule in scan_cba_terminology.RULES:
        assert not rule.regex.search(source), f"rule {rule.code!r} matches approved CBA copy"


def test_every_allowlist_entry_carries_a_reason() -> None:
    """An unexplained exclusion defeats the gate it is carved out of."""
    assert scan_cba_terminology.ALLOWLIST, "the scanner claims no exclusions at all"
    for entry in scan_cba_terminology.ALLOWLIST:
        assert entry.reason.strip(), f"allowlist entry {entry.path!r} has no reason"
        assert entry.code in RULES or entry.code == "*", (
            f"allowlist entry {entry.path!r} cites unknown rule {entry.code!r}"
        )


def test_the_scanner_declares_the_surfaces_it_is_scoped_to() -> None:
    """Scope is stated, not inferred: this is a CBA-visible copy gate, not a
    repository-wide word filter.
    """
    roots = [str(root) for root in scan_cba_terminology.SCANNED_ROOTS]
    assert "apps/web/legacy-frontend/src" in roots
    for path in scan_cba_terminology.SCANNED_FILES:
        assert (REPO_ROOT / path).is_file(), f"scanned file {path} does not exist"


# ---------------------------------------------------------------------------
# Layer 2: the repository is clean under that scope
# ---------------------------------------------------------------------------


def test_cba_visible_copy_carries_no_retired_terminology() -> None:
    findings = scan_cba_terminology.scan(REPO_ROOT)
    rendered = "\n".join(f"{f.path}:{f.line}: [{f.code}] {f.text.strip()}" for f in findings)
    assert not findings, f"retired IA-West terminology in CBA-visible copy:\n{rendered}"


# ---------------------------------------------------------------------------
# Layer 3: the replacement names are actually present
# ---------------------------------------------------------------------------


def test_the_admin_shell_names_cba() -> None:
    assert "CBA" in _read("app/components/Layout.tsx")


def test_the_student_portal_keeps_its_customer_approved_name() -> None:
    assert "Student Portal" in _read("app/components/StudentLayout.tsx")


def test_the_connector_dashboard_is_named() -> None:
    source = _read("app/components/CoordinatorPortalLayout.tsx")
    assert "Connector Dashboard" in source, (
        "customer §4: Chapter Admin Dashboard is renamed Connector Dashboard"
    )


def test_speaker_requests_replace_volunteer_opportunities_in_visible_copy() -> None:
    page = _read("app/pages/Opportunities.tsx")
    nav = _read("app/components/Layout.tsx")
    assert "Speaker Requests" in page
    assert "Speaker Requests" in nav
    # The registered metric name is a fact about the server, not a label, so it
    # is still shown verbatim next to the renamed heading.
    assert "OPPORTUNITIES_METRIC_NAME" in page


def test_speaker_survives_the_sweep() -> None:
    """§4 maps Speaker to Speaker. The sweep must not have eaten it."""
    for relative in ("components/QRCodeCard.tsx", "app/pages/Outreach.tsx"):
        assert re.search(r"\bSpeakers?\b", _read(relative), re.IGNORECASE), (
            f"{relative} lost its Speaker vocabulary"
        )
