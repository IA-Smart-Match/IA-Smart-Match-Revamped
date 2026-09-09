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

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
STATS_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorHome.tsx"
TOOLTIP_PRIMITIVE = FRONTEND_SRC / "app" / "components" / "ui" / "tooltip.tsx"
WEB_PACKAGE_JSON = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "package.json"


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


def _jsx_element(source: str, tag: str) -> str:
    """Everything between the opening and closing tag of one JSX element.

    Crude on purpose, and sufficient because the element it is asked about is
    written once on this page. It is what lets a check say *where* a string is
    rendered rather than merely that it appears somewhere in the file — the
    difference between "the reason is on the page" and "the reason is on the
    card face and not inside a tooltip".
    """
    opening = f"<{tag}"
    closing = f"</{tag}>"
    assert opening in source, f"the statistics surface renders no <{tag}>"
    assert closing in source, f"<{tag}> is never closed on the statistics surface"
    return source.split(opening, 1)[1].split(closing, 1)[0]


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


# ---------------------------------------------------------------------------
# The metric card — a definition is the register's sentence, shown on demand
# ---------------------------------------------------------------------------


def test_a_metric_definition_opens_from_a_real_focusable_button() -> None:
    """The definition is behind hover *and* focus, from one real control.

    Six registered definitions printed on the card faces ran to the length of a
    paragraph each and pushed the grid past the fold, so the first thing a
    Connector could do with their unit's numbers was scroll away from them. The
    fix is an affordance, and the affordance has to be a ``<button>``: a
    ``<span>`` with a mouse handler is the same control to a mouse and no
    control at all to a keyboard or a screen reader. Radix's ``Tooltip`` opens
    on both from a single trigger, which is why this needs no new component.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert "TooltipTrigger" in code and "TooltipContent" in code, (
        "the definition must be rendered through the tooltip primitive this app already has"
    )

    trigger = _jsx_element(code, "TooltipTrigger")
    assert "<button" in trigger, (
        "the info affordance must be a real <button>; a span with a hover handler does not "
        "exist to a keyboard"
    )
    assert 'type="button"' in trigger, (
        "an unqualified <button> inside a form submits it; the affordance opens a tooltip"
    )
    assert "aria-label" in trigger, (
        "six controls all announcing themselves as 'info' are six identical stops in a "
        "screen reader's list; each one names its metric"
    )


def test_the_card_face_carries_the_name_and_the_value_and_no_definition() -> None:
    """``definition`` is rendered once, and only inside the tooltip.

    A definition left on the face *as well* would defeat the whole change while
    passing a check that only asked whether a tooltip existed.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert code.count("metric.definition") == 1, (
        "the registered definition is rendered exactly once — inside the tooltip"
    )
    assert "metric.definition" in _jsx_element(code, "TooltipContent"), (
        "the definition must render inside the tooltip content, not on the card face"
    )
    assert "metric.display_name" in code and "metric.value" in code, (
        "the card face still carries the metric's name and its value"
    )


def test_the_definition_is_rendered_verbatim() -> None:
    """The register is the author of a registered definition.

    A browser that sliced, clamped or ellipsised one would be publishing a
    second, shorter definition that no server owns, that no other surface
    agrees with, and that nothing can drill into. A definition that is too long
    is a sentence to rewrite in ``metrics.py``, where every reader of the
    register gets the rewrite.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "definition.slice",
        "definition.substring",
        "definition.substr",
        "definition.split",
        "definition.replace",
        "line-clamp",
        "truncate",
    ):
        assert forbidden not in code, (
            f"the statistics surface applies {forbidden!r} to a server-owned string; a "
            "registered definition is rendered exactly as the register wrote it"
        )


def test_an_unmeasured_metric_states_its_reason_on_the_card_face() -> None:
    """ADR-0011: the reason a number is missing is not a footnote.

    A ``definition`` explains a figure that is on the screen and can wait for a
    hover. An ``unknown_reason`` *is* the content of an unmeasured metric —
    there is no number beside it to be read instead — and putting it behind a
    gesture a reader has to guess to make would leave "Not measured" standing
    alone, which is the bare dash this register exists to prevent.
    """
    source = STATS_PAGE.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "metric.unknown_reason" in code
    assert "unknown_reason" not in _jsx_element(code, "TooltipContent"), (
        "the server's reason for an unmeasured metric must render inline, never inside a tooltip"
    )


def test_the_hover_affordance_adds_no_dependency() -> None:
    """The primitive is the one already in this app.

    ``components/ui/tooltip.tsx`` wraps ``@radix-ui/react-tooltip``, which is
    already a declared dependency. A second tooltip library — or a hand-rolled
    one — would be a new supply-chain entry and a second set of focus and
    dismissal behaviours to keep correct, bought for a card header.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))
    manifest = json.loads(WEB_PACKAGE_JSON.read_text(encoding="utf-8"))

    assert "components/ui/tooltip" in code, (
        "the page must import the app's existing tooltip primitive"
    )
    assert "@radix-ui/react-tooltip" in TOOLTIP_PRIMITIVE.read_text(encoding="utf-8")
    assert "@radix-ui/react-tooltip" in manifest["dependencies"], (
        "the tooltip primitive's package must already be declared; this change adds none"
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
    """OQ-CBA-003 part 1, held as an absence of *per-speaker* reads.

    The per-speaker aggregate belongs to the feedback page, and this surface
    must not fetch it — `fetchSpeakerFeedbackSummary` and
    `fetchMySpeakerFeedback` are both a different, narrower or individual
    read than the pooled unit one this page is allowed. `mean_rating` and
    `response_count` are legitimately present now: they are fields on the
    *unit*-level `UnitFeedbackSummary` (the 7 September addendum), not on any
    per-speaker or per-student response, and nothing on this page can name a
    student.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "fetchMySpeakerFeedback",
        "fetchSpeakerFeedbackSummary",
        "speaker_professional_id",
        "student_id",
        "studentName",
        "who rated",
        "See all ratings",
    ):
        assert forbidden not in code, (
            f"the statistics surface references {forbidden!r}; a Connector reads the pooled "
            "unit aggregate here and never a per-speaker or per-student read"
        )

    assert "fetchUnitSpeakerFeedbackSummary" in code, (
        "the statistics surface must read the unit-level aggregate through its own helper"
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
    """A remaining gap is reported, never filled in by the browser.

    Addendum 7 September 2026 closed the unit-feedback gap this test used to
    pin: the surface now *reads* the unit aggregate through its own route
    rather than merely naming the absence of one. The review queue is a
    different, still-open gap — there is no route that lists review items, so
    the queue stays undrawable even though its *size* is a registered metric —
    and an empty list there would be a claim about the data when the truth is
    a claim about the API.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))
    text = STATS_PAGE.read_text(encoding="utf-8")

    assert "GET /v1/review-items" in text, (
        "the surface must name the missing list route rather than drawing an empty queue"
    )
    assert "fetchUnitSpeakerFeedbackSummary" in code, (
        "the surface must read the unit feedback aggregate rather than merely naming its absence"
    )
    assert "GET /v1/units/{unit_id}/speaker-feedback-summary" in text, (
        "the surface must name the route the unit aggregate comes from"
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
