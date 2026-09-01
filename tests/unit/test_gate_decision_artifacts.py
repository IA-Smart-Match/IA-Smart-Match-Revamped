"""Gate decision artifact completeness — prep packets only, not approval.

These tests protect workshop packet structure so missing decision fields are
caught in CI. They do not infer institutional authority from document existence
or from the words "approved" / "signed" alone.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

G1_PACKET = REPO_ROOT / "docs/plans/workshops/g1-factor-registry-workshop-packet.md"
G3_THREAT_MODEL = REPO_ROOT / "docs/security/crawler-threat-model-draft.md"
D6_WORKSHEET = REPO_ROOT / "docs/pilot-data/rewards-catalog-worksheet.md"


def test_g1_packet_remains_unapproved_prep() -> None:
    """G1 workshop packet must not be mistaken for D1/G1 ratification."""
    text = G1_PACKET.read_text(encoding="utf-8").lower()
    assert "preparation only" in text
    assert "does not approve" in text


def test_g1_packet_names_required_decision_fields() -> None:
    """G1 packet must enumerate every field the program owner must decide."""
    text = G1_PACKET.read_text(encoding="utf-8")
    lowered = text.lower()
    required_phrases = (
        "historical_conversion",
        "student_interest",
        "measured zero",
        "unknown",
        "weight governance",
        "program owner",
        "golden case",
        "surviving factor keys and final weights",
        "q6",
    )
    for phrase in required_phrases:
        assert phrase in lowered, f"G1 packet missing required field heading: {phrase!r}"


def test_g3_threat_model_remains_unsigned_draft() -> None:
    """G3 threat model must stay explicitly unsigned until R3 reviewer sign-off."""
    text = G3_THREAT_MODEL.read_text(encoding="utf-8").lower()
    assert "draft" in text
    assert "not signed" in text


def test_g3_threat_model_names_required_controls_and_signoff() -> None:
    """G3 draft must enumerate every control and reviewer-sign-off field."""
    text = G3_THREAT_MODEL.read_text(encoding="utf-8")
    lowered = text.lower()
    required_phrases = (
        "agent evaluation set",
        "pass/fail",
        "allowed tools",
        "domains",
        "extraction budget",
        "max pages",
        "depth",
        "bytes",
        "wall time",
        "rate and cost ceilings",
        "escalation",
        "vocabulary growth owner",
        "security reviewer sign-off",
    )
    for phrase in required_phrases:
        assert phrase in lowered, f"G3 threat model missing required field: {phrase!r}"


def test_d6_worksheet_retains_do_not_seed_warning() -> None:
    """D6 worksheet must warn engineering not to seed placeholder catalog rows."""
    text = D6_WORKSHEET.read_text(encoding="utf-8").lower()
    assert "do not seed" in text
    assert "human completion required" in text


def test_d6_worksheet_names_required_catalog_and_calibration_fields() -> None:
    """D6/D7 worksheet must name owner, funding, fulfilment, point cost, and N."""
    text = D6_WORKSHEET.read_text(encoding="utf-8")
    lowered = text.lower()
    required_phrases = (
        "budget_owner_id",
        "funded",
        "fulfilment",
        "points_cost",
        "calibration n",
        "points per verified attendance",
    )
    for phrase in required_phrases:
        assert phrase in lowered, f"D6 worksheet missing required field: {phrase!r}"
