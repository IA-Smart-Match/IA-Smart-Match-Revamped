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

    Not ``Dashboard.tsx``: that is the ``admin`` portal's own home screen
    (``_PORTAL_FOR_ROLE`` maps the stored ``admin`` role to
    ``home_path: "/dashboard"``), and a pilot Connector holding only a
    ``coordinator`` membership never reaches it. The unit here comes from
    ``GET /v1/me/portals``, which is the only source of a unit id this account
    is entitled to.

    This paragraph used to add "and it scopes itself by the
    ``VITE_SMARTMATCH_UNIT_ID`` build variable". That was true when it was
    written and is no longer: ``useUnitMetrics`` now takes the granted unit as
    an argument, exactly as the three hooks in PR #139 do, and every one of its
    call sites resolves ``grantedPortal(portalAccess, "admin")`` — see
    ``test_frontend_unit_metrics_granted_unit.py``. Which surface a Connector
    reaches is why this test targets the Connector's own landing page, and that
    reason stands on the portal grant alone.
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
    ):
        assert forbidden not in code, (
            f"the statistics surface applies {forbidden!r} to a server-owned string; a "
            "registered definition is rendered exactly as the register wrote it"
        )

    # `\b` on both sides, and the reason is a real collision rather than
    # fastidiousness: the event listing carries a server field named
    # ``truncated``, which a substring check would flag while the CSS class
    # ``truncate`` — the one that actually clips text — went on being the thing
    # this test meant. A rule that cannot tell the server's word from the
    # browser's would have to be deleted the first time it fired wrongly.
    assert re.search(r"\btruncate\b", code) is None, (
        "the statistics surface clips text with the `truncate` class; a registered "
        "definition is rendered exactly as the register wrote it"
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

    Addendum 7 September 2026 closed the unit-feedback gap this test first
    pinned: the surface *reads* the unit aggregate through its own route rather
    than merely naming the absence of one.

    Addendum 10 September 2026 closed the second. This test used to require the
    string ``GET /v1/review-items`` on the page, because the review queue was
    undrawable — size measurable as a registered metric, items unlistable. That
    is no longer true. ``GET /v1/units/{unit_id}/review-items``
    (``routers/review.py``) exists, ``CoordinatorReviewQueue`` renders it, and
    the home page now counts its pending items and links to them. Continuing to
    require the old sentence would require the page to keep telling a Connector
    that a working page does not exist — the fabricated-equivalence defect
    pointed the other way.

    So the assertion is inverted rather than dropped: the page must NOT claim
    the list route is missing, and must read it. The invariant this test exists
    for is unchanged — a gap is named and never filled in by the browser — and
    the one genuinely open gap on this surface is asserted below, in the match
    runs row.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))
    text = STATS_PAGE.read_text(encoding="utf-8")

    assert "GET /v1/review-items</code>" not in text, (
        "the surface still claims the review-item list route is missing; it exists and "
        "CoordinatorReviewQueue renders it"
    )
    assert "fetchReviewItems" in code, (
        "the surface must read the review queue it links to, so the count and the page "
        "cannot disagree"
    )
    assert "/coordinator-portal/review-queue" in code, (
        "the pending-review count must link through to the queue it counts"
    )

    # The one gap that is still real on this surface: match runs are fetched
    # one at a time by id and nothing enumerates them, so the action queue row
    # carries no number and says why.
    assert "has no route that lists them" in text, (
        "the match-runs row must say why it carries no count rather than showing a zero"
    )

    assert "fetchUnitSpeakerFeedbackSummary" in code, (
        "the surface must read the unit feedback aggregate rather than merely naming its absence"
    )
    assert "GET /v1/units/{unit_id}/speaker-feedback-summary" in text, (
        "the surface must name the route the unit aggregate comes from"
    )


def test_the_statistics_surface_summarises_events_without_counting_them() -> None:
    """The hosted-events panel reads ``/v1`` and computes nothing.

    ``GET /v1/units/{unit_id}/events`` has existed since the discovery slice
    and no portal page was calling it, so this surface rendered an "unavailable"
    panel over a route that worked — a true statement about the legacy backend
    and a false one about this deployment.

    What it may render is what the *response* says about its own completeness:
    the two withheld counts, which the route counts from the same rows the
    listing is partitioned out of. What it may not render is ``events.length``.
    That is a figure this browser computed, and it would sit among figures whose
    whole claim is that one server query owns each of them — the register above
    is where a count belongs, and it has no metric for this one.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert "fetchUnitEvents" in code, (
        "the hosted-events panel must read the unit's event listing through its own helper"
    )
    for field in ("withheld_unresolved_date", "withheld_quarantined_tags"):
        assert field in code, (
            f"the panel must render {field!r}; without the withheld counts, 'this unit has no "
            "events' and 'this unit has seven the pipeline could not finish' are one silence"
        )

    for forbidden in ("events.length", "listing.events.length"):
        assert forbidden not in code, (
            f"the statistics surface counts events with {forbidden!r}; every figure it shows "
            "must be one a server query owns"
        )


def test_the_outreach_panel_says_drafts_and_sends_and_never_threads() -> None:
    """OQ-008, held as a naming rule on the surface that reads the routes.

    ``/v1`` outreach stores an ``outreach_draft`` — a composed message — and an
    ``outreach_send`` — one attempt to deliver it. It has no inbound leg, so a
    thread is not a dataset this deployment withholds; it is a shape the data
    does not have. Rendering these rows under the legacy word would be the
    fabricated equivalence the unavailable panels exist to prevent, and a reader
    shown "threads" would go looking for replies that do not exist.

    The rule is enforced on rendered copy rather than on prose, because the
    page's own docstring has to be free to explain *why* it does not say
    threads. A guard that failed on a file's explanation of why it passes trains
    the next person to delete the explanation.
    """
    code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))

    assert "fetchOutreachDrafts" in code and "fetchOutreachSends" in code, (
        "the panel must read both outreach routes rather than one of them"
    )
    assert re.search(r"\bthreads?\b", code, flags=re.IGNORECASE) is None, (
        "the outreach panel calls something a thread; /v1 outreach returns drafts and sends, "
        "and this API has no inbound leg for a thread to be made of"
    )
    # `\s*` because a heading long enough to be prettier-wrapped sits on its own
    # line between its tags, and a check that only matched `>Drafts<` would pass
    # or fail on formatting rather than on what the heading says.
    for heading in ("Drafts", "Sends"):
        assert re.search(rf">\s*{heading}\s*<", code) is not None, (
            f"the panel has no {heading!r} heading; its own headings must name what the routes "
            "return"
        )

    for forbidden in (
        "drafts.length",
        "sends.length",
        "drafts.data.length +",
        "sends.data.length +",
    ):
        assert forbidden not in code, (
            f"the outreach panel computes {forbidden!r}; neither response carries a total, so "
            "a count here would be a number of one page presented as a number of attempts"
        )


def test_the_surface_claims_no_absence_for_a_dataset_it_now_reads() -> None:
    """An unavailable panel is a claim, and it must come down when it stops being true.

    ``PortalDatasetUnavailable`` says a dataset is not carried by this
    deployment. Left standing beside a working ``/v1`` read it is the same
    fabricated-equivalence defect it was written to prevent, pointed the other
    way: the reader is told a capability is absent while the page holds its
    answer.

    Addendum 10 September 2026: Meeting bookings used to be the one coordinator
    dataset with no ``/v1`` route, so this test required its panel to stay.
    ``GET``/``POST /v1/units/{unit_id}/meetings`` (migration ``0034``) are live
    and ``CoordinatorMeetings`` has been reading and writing them, so the panel
    was claiming an absence over a working route — exactly what this test
    forbids for the other three. It joins them rather than keeping an
    exemption, and the surface now renders no unavailable panel at all.
    """
    text = STATS_PAGE.read_text(encoding="utf-8")
    code = _code_only(text)

    for retired in (
        "Your coordinator profile",
        "Hosted events and staffing",
        "Outreach threads",
        "Meeting bookings",
    ):
        assert f'dataset="{retired}"' not in code, (
            f"the surface still renders an unavailable panel for {retired!r}, which it now "
            "reads from /v1"
        )

    assert "PortalDatasetUnavailable" not in code, (
        "every dataset this surface once called absent is now served by /v1; an unavailable "
        "panel left standing beside a working read is the same fabricated-equivalence defect "
        "pointed the other way"
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
