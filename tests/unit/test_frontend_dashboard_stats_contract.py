"""Source contract for the Connector's pilot statistics (TRACK 14).

A dashboard is where derived numbers get invented. Every other surface in this
frontend fetches one resource and renders it; a statistics panel is the one
place a developer is *invited* to add together things the server sent
separately, and the result looks exactly as authoritative as a measured figure.
This file refuses that in the only way a source-level check can: by naming the
arithmetic and forbidding it on the page that carries the counts.

Three decisions are load-bearing.

**ADR-0011 — a number has one owning query, and unknown is never zero.** Each
figure on the Connector's statistics surface comes from
``GET /v1/units/{unit_id}/metrics?surface=cba`` or from
``GET /v1/units/{unit_id}/engagement/attendance-summary``, both of which count
server-side and both of which distinguish "we measured none" from "there is no
evidence source". ``MetricSummary.value`` is ``null`` with an
``unknown_reason`` beside it precisely so that no client has to reconstruct the
distinction, and a ``?? 0`` in the browser destroys it silently.

**OQ-CBA-003 part 1 — a Connector reads an aggregate and never a student.**
There is no unit-level feedback statistic in this API: the only feedback read a
Connector has is the per-speaker aggregate, and the statistics surface points at
the page that renders it rather than growing a second, hand-rolled copy. What it
must never do is publish a number the server withheld, name a student, or write
down the suppression threshold — that value is a decided one that travels in
``minimum_responses`` and can move.

**OQ-CBA-005 / OQ-CBA-053 — no percentage, and feedback is not a matching
input.** A statistics panel is where a "match rate" grows. There is no
percentage on any match-derived figure, and the surface says out loud that
student feedback does not feed matching, because a rating rendered near a
funnel count reads as an input to it unless a reader is told otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
STATS_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorHome.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    Prose *about* an individual rating is not an individual rating, and a check
    that could not tell the two apart would forbid the page from explaining why
    it does not render one.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _helper_body(source: str, name: str) -> str:
    """The source of one exported helper, from its signature to its closing brace."""
    marker = f"export async function {name}"
    assert marker in source, f"api.ts is missing {name}"
    return source.split(marker, 1)[1].split("\n}", 1)[0]


def _interface_body(source: str, name: str) -> str:
    """The fields of one exported interface, with its doc comments stripped."""
    marker = f"export interface {name} {{"
    assert marker in source, f"api.ts is missing {name}"
    return _code_only(source.split(marker, 1)[1].split("\n}", 1)[0])


# ---------------------------------------------------------------------------
# The client helpers — each statistic has exactly one owning read
# ---------------------------------------------------------------------------


def test_api_lib_reads_the_cba_view_of_the_metric_register() -> None:
    """The counts come from the register, asked for as the CBA product sees it.

    ``surface=cba`` is a real query parameter on ``GET /v1/units/{id}/metrics``
    and the server decides what it means: ``pipeline_member_inquiry`` omitted
    (``Capability.MEMBER_INQUIRY_NARRATIVE`` is off under ``ProductScope.CBA``)
    and the four funnel metrics relabelled for a surface whose subject is a
    speaker. A page that asked for the default view and filtered the payload in
    the browser would be keeping a second copy of that exclusion list, which is
    the copy that goes stale.
    """
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchCbaUnitMetrics")

    assert "/metrics" in helper
    assert "surface=cba" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "authenticated: true" in helper


def test_api_lib_reads_attendance_evidence_as_the_server_counted_it() -> None:
    """Attendance is counted server-side, ``total`` included.

    ``AttendanceSummaryResponse`` documents ``total`` as "the sum of
    ``by_method``, folded server-side from the same counts this response
    carries — never a stored counter and never arithmetic left to a client".
    The client type must therefore carry the folded total as a field, so no
    caller is tempted to add the three method counts up itself.
    """
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchAttendanceSummary")

    assert "/engagement/attendance-summary" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "authenticated: true" in helper

    fields = _interface_body(source, "AttendanceSummary")
    for field in (
        "unit_id",
        "total",
        "by_method",
        "distinct_subjects",
        "distinct_events",
        "first_recorded_at",
        "last_recorded_at",
    ):
        assert field in fields, f"AttendanceSummary is missing {field!r}"

    for forbidden in ("subject_ids", "attendees", "roster", "[]"):
        assert forbidden not in fields, (
            f"AttendanceSummary carries {forbidden!r}; this response is counts only and "
            "returns no list of the accounts behind them while D8 is open"
        )


# ---------------------------------------------------------------------------
# The statistics surface — every number is one the server chose to send
# ---------------------------------------------------------------------------


def test_the_statistics_surface_reads_both_owning_queries() -> None:
    """The Connector's own landing surface carries the statistics.

    Not ``Dashboard.tsx``: that is the IA admin surface, it scopes itself by the
    ``VITE_SMARTMATCH_UNIT_ID`` build variable rather than by the unit the
    server granted this account, and a pilot Connector never reaches it. The
    unit here comes from ``GET /v1/me/portals``, which is the only source of a
    unit id this account is entitled to.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert "fetchCbaUnitMetrics" in code
    assert "fetchAttendanceSummary" in code
    assert "default_unit_id" in code, (
        "the unit must come from the server's portal grant, never from a build variable"
    )


def test_the_statistics_surface_computes_nothing() -> None:
    """No total, no mean, no rounding, no percentage of anything.

    Every figure has one owning server query (ADR-0011 rule 3). A browser that
    folded two responses together would be publishing an eighth metric that no
    query owns and that nothing can drill into.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "reduce(",
        "toFixed",
        "Math.round",
        "Math.max",
        "Math.min",
        "average",
        " += ",
        ".length +",
    ):
        assert forbidden not in code, (
            f"the statistics surface computes {forbidden!r}; every number it shows must be "
            "one the server chose to send"
        )


def test_the_statistics_surface_never_coerces_an_unknown_to_zero() -> None:
    """ADR-0011 rule 1: a null is not a zero.

    ``MetricSummary.value`` is ``null`` exactly when no evidence source exists,
    and ``unknown_reason`` says why. ``?? 0`` turns "we cannot answer" into "the
    answer is none", which is the one substitution this whole register exists to
    prevent — and it reads as deliberate to everyone downstream.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("?? 0", "|| 0", "Number("):
        assert forbidden not in code, (
            f"the statistics surface contains {forbidden!r}; an unmeasured metric renders as "
            "unknown with the server's reason, never as zero"
        )

    assert "unknown_reason" in code, (
        "a metric with no value must render the server's reason rather than a bare dash"
    )


def test_the_statistics_surface_renders_no_percentage() -> None:
    """OQ-CBA-005 keeps percentages off CBA surfaces.

    A funnel of counts is where a "conversion rate" appears, and a percentage
    beside a speaker count is the same shape as the match percentage OQ-CBA-005
    forbids — with the added problem that computing one would need division the
    surface is not allowed to do.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))
    assert "%" not in code, "the statistics surface renders a percentage"


def test_the_statistics_surface_shows_no_individual_student_rating() -> None:
    """OQ-CBA-003 part 1, held as an absence of reads rather than as a filter.

    The per-speaker aggregate belongs to the feedback page. This surface links
    to it and fetches no feedback of its own, so there is no response here for a
    later edit to render a field out of.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "fetchMySpeakerFeedback",
        "fetchSpeakerFeedbackSummary",
        "mean_rating",
        "response_count",
        "student_id",
        "studentName",
        "who rated",
        "See all ratings",
    ):
        assert forbidden not in code, (
            f"the statistics surface references {forbidden!r}; a Connector reads an aggregate "
            "on the feedback page and never a student's rating anywhere"
        )


def test_the_statistics_surface_writes_down_no_suppression_threshold() -> None:
    """``minimum_responses`` is the server's to send; ``3`` is not written here.

    The threshold is a decided value that can move, and a surface carrying its
    own copy keeps explaining the old one after it does.
    """
    text = STATS_PAGE.read_text(encoding="utf-8")

    for pattern in (
        r"at least\s+3\b",
        r"fewer than\s+3\b",
        r"minimum_responses\s*[:=]\s*3\b",
        r"three students",
    ):
        assert re.search(pattern, text, flags=re.IGNORECASE) is None, (
            f"the statistics surface hard-codes the suppression threshold ({pattern!r}); "
            "it travels in `minimum_responses` on the response that needs it"
        )


def test_the_statistics_surface_says_feedback_does_not_feed_matching() -> None:
    """OQ-CBA-053, said out loud beside the funnel counts.

    Silence is not enough where the reader's default assumption is wrong. A
    pointer to student ratings placed near "speakers matched" reads as an input
    to that number unless the page says otherwise.
    """
    text = STATS_PAGE.read_text(encoding="utf-8").lower()
    assert "does not feed matching" in text


def test_the_statistics_surface_names_the_statistics_the_api_cannot_answer() -> None:
    """A gap is reported, never filled in by the browser.

    Two are real and both are stated. There is no route that lists review items,
    so the queue itself stays undrawable even though its *size* is a registered
    metric; and there is no unit-level feedback aggregate, only the per-speaker
    one. An empty list in either place would be a claim about the data when the
    truth is a claim about the API.
    """
    text = STATS_PAGE.read_text(encoding="utf-8")

    assert "GET /v1/review-items" in text, (
        "the surface must name the missing list route rather than drawing an empty queue"
    )
    assert "feedback-summary" in text, (
        "the surface must say that feedback is answerable per speaker only, and point at it"
    )


def test_the_statistics_surface_renders_the_servers_refusal() -> None:
    """A UI gate is display only; a 403 is an answer to render.

    The metrics aggregate read is authorized per request against the loaded
    unit. Hiding the panel on a refusal would tell a Connector the capability
    does not exist, which is a different and false statement.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert "ApiRequestError" in code
    assert "cause.message" in code or "error.message" in code, (
        "the server's own refusal text must be what a reader sees"
    )


def test_the_statistics_surface_touches_no_archived_backend() -> None:
    """None of the surfaces `frontend-broken-buttons.md` says not to port."""
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("fetchSpecialists", "/api/data", "AgenticOutreachPanel", "fetchPipeline("):
        assert forbidden not in code, (
            f"the statistics surface reaches for {forbidden!r}, which has no counterpart in "
            "this repository's API"
        )
