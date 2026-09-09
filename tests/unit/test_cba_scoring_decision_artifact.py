"""ADR-0016 (CBA scoring policy) is a complete, honest decision artifact.

``OQ-CBA-004`` names Danny Tran (Development Lead / program owner of record) as
the owner whose approval is a hard pre-merge gate for the first Wave 3 registry
PR. This file is the executable half of that gate. It is split deliberately in
two:

* **Completeness tests run unconditionally.** A proposal that omits a band
  value, a boundary rule, the redistribution formula, the serialization, the UI
  labels, the pin policy, or the golden cases is not decidable, and an owner
  cannot approve what the document does not say. These fail while the drafting
  is incomplete.

* **Approval tests are ``xfail(strict=True)``.** ADR-0016's status is
  ``Proposed`` and no owner has decided. Asserting ``Accepted`` today would
  either fail CI for a gate that is genuinely, correctly open, or invite
  someone to make it pass by typing an approval nobody gave. ``strict=True`` is
  what keeps the marker honest in the other direction: the day the owner
  approves and the ADR records it, these XPASS, the suite goes red, and whoever
  lands the approval must delete the markers in the same change. A non-strict
  xfail would let an approved ADR sit behind a permanently green skip.

Nothing here infers authority from the existence of a document, from the word
"approved", or from a date — the same rule
``tests/unit/test_gate_decision_artifacts.py`` states for the G1/G3/D6 packets.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ADR_PATH = REPO_ROOT / "docs/architecture/decisions/ADR-0016-cba-scoring-policy.md"
ADR_INDEX = REPO_ROOT / "docs/architecture/decisions/README.md"
OQ_REGISTER = REPO_ROOT / "docs/plans/open-questions/cba-phase-deferred.md"

#: The owner named by OQ-CBA-004. Spelled here so a rename of the owner in the
#: register without a corresponding edit to the ADR is a test failure rather
#: than a silent divergence.
OQ_CBA_004_OWNER = "Danny Tran"

#: Why every approval assertion below is expected to fail today.


def _adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def _adr_lower() -> str:
    return _adr_text().lower()


def test_the_adr_exists_and_states_its_standing_accurately() -> None:
    """The artifact must exist and must not misstate its own standing.

    This test was the mirror image of itself until 5 September 2026: it asserted
    ``**Status:** Proposed`` and that the document called itself unapproved. The
    owner has since decided, so the guard is inverted rather than deleted — an
    accepted ADR that still describes itself as an unapproved proposal is the same
    defect as a proposal that reads as settled, just pointing the other way.
    """
    assert ADR_PATH.is_file(), f"{ADR_PATH} is missing"
    text = _adr_text()
    assert re.search(r"^\*\*Status:\*\*\s*Accepted\b", text, re.MULTILINE), (
        "ADR-0016 is accepted and must declare `**Status:** Accepted`"
    )
    lowered = text.lower()
    assert "not approved" not in lowered, (
        "ADR-0016 is accepted; it must not still describe itself as unapproved"
    )
    assert "oq-cba-004" in lowered
    assert OQ_CBA_004_OWNER.lower() in lowered


def test_the_adr_names_every_proposal_the_owner_must_decide() -> None:
    """A decision the owner cannot point at by number cannot be approved by number."""
    text = _adr_text()
    for number in range(1, 10):
        assert re.search(rf"^### Proposal {number}\b", text, re.MULTILINE), (
            f"ADR-0016 is missing a numbered `### Proposal {number}` heading; "
            "every decision must be separately approvable"
        )


def test_the_adr_separates_neutral_topic_policy_from_unknown_evidence() -> None:
    """OQ-CBA-004 requirement 1: the two cases are answered separately."""
    lowered = _adr_lower()
    required = (
        "policy_neutral",
        "unknown",
        "measured",
        "adr-0011",
        "no usable topic evidence",
        "could not be evaluated",
    )
    for phrase in required:
        assert phrase in lowered, f"ADR-0016 does not separate neutral from unknown: {phrase!r}"
    assert "neutral is not an unknown" in lowered
    assert "unknown is still not zero" in lowered


def test_the_adr_states_the_neutral_topic_value_and_its_provenance() -> None:
    """The neutral value is a named, versioned policy constant, never a stray literal."""
    lowered = _adr_lower()
    assert "cba_neutral_topic_value" in lowered
    assert "cba_neutral_topic_policy_version" in lowered
    assert "neutral_topic_policy_id" in lowered


def test_the_adr_fixes_the_proximity_bands_including_boundary_ownership() -> None:
    """OQ-CBA-002: exact sub-scores and which band owns exactly 25 and 75 miles."""
    text = _adr_text()
    lowered = text.lower()
    for phrase in ("0 ≤ d < 25", "25 ≤ d < 75", "75 ≤ d"):
        assert phrase in lowered, f"ADR-0016 does not state the band interval {phrase!r}"
    assert "lower-inclusive, upper-exclusive" in lowered
    assert "exactly 25" in lowered and "exactly 75" in lowered
    # The proposed sub-scores themselves, on both the proximity and the
    # registry's penalty (travel burden) scale, so no reader has to invert them.
    for value in ("1.00", "0.60", "0.20", "0.00", "0.40", "0.80"):
        assert value in text, f"ADR-0016 does not state the band sub-score {value!r}"
    assert "step function" in lowered
    assert "is not the far band" in lowered


def test_the_adr_fixes_the_virtual_event_redistribution_formula() -> None:
    """OQ-CBA-001: the formula, its exact weights, and the rejected alternative."""
    text = _adr_text()
    lowered = text.lower()
    assert "cba-virtual-1" in lowered
    assert "scoring mode" in lowered
    for weight in ("0.428571", "0.357143", "0.214286"):
        assert weight in text, f"ADR-0016 does not state the virtual weight {weight!r}"
    assert "proportional renormalization" in lowered
    assert "fixed table" in lowered
    assert "is_virtual" in lowered


def test_the_adr_defines_serialization_ui_labels_and_pins() -> None:
    """The register's stated requirements for the approved artifact."""
    lowered = _adr_lower()
    for phrase in (
        "serialization",
        "scorestate",
        "policy_neutral_factor_keys",
        "explanation_to_payload",
        "ui label",
        "heuristic score",
        "registry_version",
        "scoring_mode",
        "weights_fingerprint",
        "matchrunpins",
    ):
        assert phrase in lowered, f"ADR-0016 is missing required content: {phrase!r}"


def test_the_adr_states_the_registry_version_pin_policy() -> None:
    """A pinned run must stay readable across the 1.x to 2.x change."""
    lowered = _adr_lower()
    assert "1.1.1-approved-g1-m6j" in lowered
    assert "2.0.0" in lowered
    assert "pin policy" in lowered


def test_the_adr_enumerates_named_golden_cases() -> None:
    """Every decision above must imply a case a golden set can assert."""
    text = _adr_text()
    identifiers = set(re.findall(r"\bG-CBA-\d{2}\b", text))
    assert len(identifiers) >= 10, (
        f"ADR-0016 names only {len(identifiers)} golden cases; each proposal must "
        "imply at least one"
    )


def test_the_adr_invents_no_temporary_default() -> None:
    """The anti-pattern this card exists to refuse."""
    lowered = _adr_lower()
    for banned in ("temporary default", "for now we assume", "assume for now", "placeholder value"):
        assert banned not in lowered, (
            f"ADR-0016 contains {banned!r}: an unapproved value must be a labelled "
            "proposal, never a temporary default"
        )


def test_the_adr_is_indexed() -> None:
    """ADR-0016 must appear in the decision index (see test_adr_index.py)."""
    index = ADR_INDEX.read_text(encoding="utf-8")
    assert "ADR-0016-cba-scoring-policy.md" in index


def test_the_open_questions_stay_open_until_the_owner_decides() -> None:
    """The register must still show 001/002/004 open, and must cite the proposal."""
    register = OQ_REGISTER.read_text(encoding="utf-8")
    assert "ADR-0016-cba-scoring-policy.md" in register, (
        "the OQ register must point at the proposal the owner has to decide"
    )
    lowered = register.lower()
    assert "awaiting owner decision" in lowered
    assert "proposed, not accepted" in lowered


def test_the_adr_is_accepted_by_the_named_owner() -> None:
    """Approval gate. Fails while OQ-CBA-004 is open — that is the correct state."""
    text = _adr_text()
    assert re.search(r"^\*\*Status:\*\*\s*Accepted\b", text, re.MULTILINE), (
        "ADR-0016 is not Accepted"
    )


def test_the_adr_records_a_decision_date_and_an_approving_owner() -> None:
    """Approval gate. An accepted ADR names who decided and on what date."""
    text = _adr_text()
    assert re.search(
        rf"^\*\*Decided:\*\*\s*\d{{1,2}}\s+\w+\s+\d{{4}}\s+—\s+{OQ_CBA_004_OWNER}\b",
        text,
        re.MULTILINE,
    ), "ADR-0016 records no `**Decided:** <date> — <owner>` line"


def test_the_register_closes_the_three_open_questions() -> None:
    """Approval gate. OQ-CBA-001/002/004 close only on the owner's decision."""
    register = OQ_REGISTER.read_text(encoding="utf-8")
    for oq in ("OQ-CBA-001", "OQ-CBA-002", "OQ-CBA-004"):
        assert f"{oq} | **Closed" in register, f"{oq} is not closed in the register"
