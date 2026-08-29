"""Source contract for the ADR-0011 zero-coercion cleanup (plan P3, card Z4).

Narrow, source-text checks in the style of test_frontend_auth_contract.py.
This is not a substitute for Vitest — it only asserts that the specific
fields the Z1 inventory (docs/plans/adr0011-frontend-coercion-inventory.md)
classified as violations were actually converted to the nullable seam
(`parseNumberOrNull` / `number | null`), and that the pre-fix fabricated
fallback in Volunteers.tsx is gone.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_TS = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "api.ts"
)
VOLUNTEERS_TSX = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Volunteers.tsx"
)

# Z1 violations V1-V5: interface fields that must be `number | null`, not a
# bare `number` with a `?? 0` / `|| 0` fallback in their normalizer.
NULLABLE_TYPE_DECLARATIONS = (
    "volunteer_fatigue: number | null;",  # CalendarAssignmentSummary (V1)
    "recent_assignment_count: number | null;",  # CalendarAssignmentSummary (V2)
    "scan_count: number | null;",  # QrCodeAsset (V3)
    "conversion_count: number | null;",  # QrCodeAsset (V3)
    "conversion_rate: number | null;",  # QrCodeAsset (V3)
    "total_generated: number | null;",  # QrStatsSummary (V4)
    "total_scans: number | null;",  # QrStatsSummary (V4)
    "total_conversions: number | null;",  # QrStatsSummary (V4)
    "total_feedback: number | null;",  # FeedbackStatsSummary (V5)
    "accepted: number | null;",  # FeedbackStatsSummary (V5)
    "declined: number | null;",  # FeedbackStatsSummary (V5)
    "acceptance_rate: number | null;",  # FeedbackStatsSummary (V5)
    "attended_count: number | null;",  # FeedbackStatsSummary (V5)
    "membership_interest_count: number | null;",  # FeedbackStatsSummary (V5)
    "membership_interest_rate: number | null;",  # FeedbackStatsSummary (V5)
    "average_match_score_accepted: number | null;",  # FeedbackStatsSummary (V5)
    "average_match_score_declined: number | null;",  # FeedbackStatsSummary (V5)
    "pain_score: number | null;",  # FeedbackStatsSummary (V5)
)

# Exact pre-fix snippets that fabricated a zero for these violating fields.
# None of these should exist in api.ts any more.
#
# Note: `total_feedback` / `acceptance_rate` / `pain_score` are deliberately
# NOT listed here even though they were also zero-coerced pre-fix, because
# the identical literal pattern legitimately still exists today in
# normalizeFeedbackWeightSnapshot's FeedbackWeightSnapshot fields (Z1
# inventory: "measured-zero-ok" nested per-submission snapshot, out of this
# card's named scope) — a literal-substring check can't tell the two apart.
# NULLABLE_TYPE_DECLARATIONS above already proves the FeedbackStatsSummary
# copies of these fields were fixed.
FORBIDDEN_ZERO_COERCIONS = (
    "record.recent_assignment_count ?? record.recentAssignments ?? record.assignment_count ?? 0, 0",
    "parseNumber(record.attended_count ?? 0, 0)",
    "parseNumber(record.average_match_score_accepted ?? 0, 0)",
    "parseNumber(record.average_match_score_declined ?? 0, 0)",
    # The old all-zero placeholder objects (the exact ADR-0011 anti-pattern
    # this card exists to remove).
    "total_generated: 0,\n    total_scans: 0,\n    total_conversions: 0,\n    conversion_rate: 0,",
    "total_feedback: 0,\n    accepted: 0,\n    declined: 0,\n    acceptance_rate: 0,",
)


def test_api_ts_declares_violating_fields_as_nullable() -> None:
    source = API_TS.read_text(encoding="utf-8")
    for declaration in NULLABLE_TYPE_DECLARATIONS:
        assert declaration in source, (
            f"api.ts no longer declares {declaration!r} — did a Z1 violation "
            "field regress to a bare `number` with a zero fallback?"
        )


def test_api_ts_has_no_forbidden_zero_coercions_on_violation_fields() -> None:
    source = API_TS.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_ZERO_COERCIONS:
        assert forbidden not in source, (
            f"api.ts still contains a zero-coercion for a Z1 violation field: {forbidden!r}"
        )


def test_api_ts_defines_parse_number_or_null_seam() -> None:
    source = API_TS.read_text(encoding="utf-8")
    assert "function parseNumberOrNull(value: unknown): number | null" in source
    # parseNumber must still exist: layout-ok / measured-zero-ok call sites
    # (documented in the Z1 inventory) legitimately keep using it.
    assert "function parseNumber(value: unknown, fallback = 0): number" in source


def test_api_ts_defines_normalize_fatigue_or_null_seam() -> None:
    source = API_TS.read_text(encoding="utf-8")
    assert "function normalizeFatigueOrNull(value: unknown): number | null" in source


def test_empty_summary_placeholders_are_not_fabricated_zero_objects() -> None:
    source = API_TS.read_text(encoding="utf-8")
    assert "export function emptyQrStatsSummary(): QrStatsSummary" in source
    assert "export function emptyFeedbackStatsSummary(): FeedbackStatsSummary" in source
    # The placeholder returned before the first fetch resolves (or after a
    # failed fetch) must use null, not 0, for every numeric field.
    for forbidden in FORBIDDEN_ZERO_COERCIONS[-2:]:
        assert forbidden not in source


def test_volunteers_page_no_longer_fabricates_a_fatigue_estimate() -> None:
    """V6/V7: Volunteers.tsx used to synthesize a fatigue number from
    unrelated pipeline-stage weighting whenever a volunteer had no calendar
    assignment overlays, and presented it as if it were measured. That
    formula must be gone; fatigue must come only from real backend evidence
    (or be null)."""
    source = VOLUNTEERS_TSX.read_text(encoding="utf-8")
    assert "fallbackFatigue" not in source
    assert "12 + weightedLoad" not in source
    assert "volunteerFatigue = backendFatigue ?? fallbackFatigue" not in source
