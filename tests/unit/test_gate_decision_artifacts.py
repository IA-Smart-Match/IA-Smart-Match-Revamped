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
CBA_SCORING_ADR = REPO_ROOT / "docs/architecture/decisions/ADR-0016-cba-scoring-policy.md"

#: OQ-CBA-004's named owner, and the reason every approval assertion about
#: ADR-0016 is expected to fail. Duplicated deliberately from
#: ``tests/unit/test_cba_scoring_decision_artifact.py``: that file is the
#: artifact's own completeness suite, this one is the register of *gates*, and a
#: gate whose reason string lived in another module would be a gate whose
#: justification a reader has to go and find.
OQ_CBA_004_OWNER = "Danny Tran"


def test_g1_packet_remains_unapproved_prep() -> None:
    """G1 workshop packet must not be mistaken for D1/G1 ratification."""
    text = G1_PACKET.read_text(encoding="utf-8").lower()
    assert "ready to schedule" in text
    assert "remain blocked" in text


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


def test_g3_threat_model_is_signed_requirements() -> None:
    """R3 threat model design requirements signed 2026-09-03 (Danny Tran)."""
    text = G3_THREAT_MODEL.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "signed 2026-09-03" in lowered
    assert "danny tran" in lowered
    assert "r3-signing-decisions-2026-09-03" in text


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


def test_cba_scoring_adr_reads_as_the_approval_it_now_is() -> None:
    """ADR-0016 must read as ratified now that OQ-CBA-004 is closed.

    Until 5 September 2026 this asserted the opposite, and the reasoning still
    holds in mirror: the danger is a decision document whose voice and whose
    header disagree. Then, the risk was a proposal that read as settled. Now it
    is an accepted policy still carrying "must not be implemented", which would
    stop engineering from applying values the owner has approved and leave the
    downstream reader unable to tell what is in force.
    """
    text = CBA_SCORING_ADR.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "**status:** accepted" in lowered
    assert "must not be implemented" not in lowered, (
        "ADR-0016 is accepted; the do-not-implement banner must be gone"
    )
    assert "not approved" not in lowered
    assert "oq-cba-004" in lowered
    assert OQ_CBA_004_OWNER.lower() in lowered


def test_cba_scoring_adr_names_every_field_the_owner_must_decide() -> None:
    """ADR-0016 must enumerate every field the OQ-CBA-004 owner has to rule on."""
    lowered = CBA_SCORING_ADR.read_text(encoding="utf-8").lower()
    required_phrases = (
        "neutral topic",
        "policy_neutral",
        "unknown",
        "cba_neutral_topic_value",
        "proximity band",
        "boundary ownership",
        "lower-inclusive, upper-exclusive",
        "virtual",
        "cba-virtual-1",
        "proportional renormalization",
        "serialization",
        "ui label",
        "registry_version",
        "pin policy",
        "golden case",
        "program owner of record",
    )
    for phrase in required_phrases:
        assert phrase in lowered, f"ADR-0016 missing required decision field: {phrase!r}"


def test_cba_scoring_adr_is_accepted_with_an_owner_and_a_date() -> None:
    """The gate itself. Fails while the owner has not decided — correctly.

    ``strict=True`` so this cannot stay quietly red after the decision lands:
    the moment the status flips and the ``**Decided:**`` line names the owner
    and a date, the test XPASSes and the suite fails until the marker is
    removed. That is the point — the marker records an *open* gate, and an
    open-gate marker outliving its gate is exactly the stale artifact this file
    exists to prevent.
    """
    text = CBA_SCORING_ADR.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "**status:** accepted" in lowered, "ADR-0016 status is not Accepted"
    assert "**decided:**" in lowered, "ADR-0016 records no decision date"
    assert OQ_CBA_004_OWNER.lower() in lowered.split("**decided:**", 1)[1][:200], (
        "ADR-0016's decision line does not name the approving owner"
    )
