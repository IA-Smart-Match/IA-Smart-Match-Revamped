"""Source contract for student speaker feedback in the browser (TRACK 5).

Two decisions are load-bearing here, and both are the kind a later refactor
undoes by being helpful rather than by being wrong.

**OQ-CBA-003, part 1 — a Connector reads an aggregate and never a student.**
The server holds that structurally: ``SpeakerFeedbackSummaryResponse`` has no
field a student could be assigned to, the repository read behind it selects one
column and returns ``list[int]``, and there is deliberately no route that lists
individual ratings to a Connector. None of that survives a browser page that
fetches the *student's* list route and renders it on a Connector's screen, or
one that publishes a count the server withheld. So this file pins the direction
of the two reads: ``fetchMySpeakerFeedback`` is a student surface's helper and
must not appear on the Connector page, and the Connector page must render only
the fields the aggregate carries.

It also refuses the arithmetic route to the same leak. The server suppresses
both numbers below ``MIN_RESPONSES_FOR_AGGREGATE`` (3) and sends
``minimum_responses`` so a page can explain the suppression *without knowing the
number*. A page that hard-coded ``3``, or that reconstructed a mean or a count
the server declined to send, would be re-deciding an anonymity threshold in a
bundle nobody versions.

**OQ-CBA-053 — no rating is a scoring input.** "No factor reads this table" is a
backend fact, and the way a frontend breaks it is not by computing a score: it
is by *captioning*. A summary rendered under a "match score" heading, or beside
a "this speaker ranks higher because students liked them" sentence, tells a
Connector something false about how matching works, and a Connector who believes
it will manage the roster accordingly. So the vocabulary is forbidden and the
disclaimer is required.

The third section is ``frontend-broken-buttons.md`` discipline. ``POST
.../feedback`` returns the stored row and a ``changed`` flag that separates "this
is your rating" from "this request changed it", so there is never a reason for
this page to compose a confirmation of its own.

Both student routes are ``student``-scoped server-side and the summary is
``admin``/``coordinator``. A UI gate is not authorization, so each page renders
its control and handles the server's ``403`` as the answer it is.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
STUDENT_PAGE = FRONTEND_SRC / "app" / "pages" / "student" / "StudentSpeakerFeedback.tsx"
CONNECTOR_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorSpeakerFeedback.tsx"
DASHBOARD_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorHome.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    The same reason the sibling contract files do it: prose *about* an
    individual rating — this module's own subject, and the pages' comments —
    is not an individual rating rendered to a Connector, and a check that could
    not tell the two apart would forbid explaining itself.
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
    """The *fields* of one exported interface, with its doc comments stripped.

    Comments go for the same reason they go everywhere else in this file: the
    forbidden names below are field names, and a doc sentence explaining that
    ``response_count`` is "how many ratings the mean was computed from" is prose
    about an aggregate rather than a list of ratings on it. A check that could
    not tell those apart would forbid documenting the type.
    """
    marker = f"export interface {name} {{"
    assert marker in source, f"api.ts is missing {name}"
    return _code_only(source.split(marker, 1)[1].split("\n}", 1)[0])


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_submits_a_rating_without_naming_its_author() -> None:
    """The write names an event and a speaker. It cannot name a student.

    Every route in ``student_speaker_feedback.py`` takes ``student_id`` from
    ``principal.user_id`` and accepts one in no body and no path — that absence
    is what stops MM-A01's caller-selected identity entering. A payload type
    that grew a ``student_id`` would be offering the browser a field the server
    has none to receive, and the next person to read it would reasonably assume
    one end honours it.
    """
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "submitSpeakerFeedback")

    assert "/student/events/" in helper
    assert "/feedback" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "encodeURIComponent(eventId)" in helper
    assert "encodeURIComponent(speakerId)" in helper
    assert 'method: "POST"' in helper
    assert "authenticated: true" in helper

    payload = _interface_body(source, "SpeakerFeedbackSubmission")
    assert "rating" in payload
    assert "comment" in payload
    for forbidden in ("student_id", "student_name", "submitted_at", "status"):
        assert forbidden not in payload, (
            f"the submission payload lets the browser assert {forbidden!r}; the author, the "
            "timestamps and the status are all the server's to write"
        )


def test_api_lib_withdraws_a_rating_through_the_delete_route() -> None:
    """Withdrawal is its own route, not a submission of a sentinel rating.

    There is no zero on this scale, and ``rating: 0`` would be a badly-rated
    speaker rather than a retracted rating — the server rejects it (``ge=1``),
    which is the right answer to a client that tried.
    """
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "withdrawSpeakerFeedback")

    assert 'method: "DELETE"' in helper
    assert "/feedback" in helper
    assert "authenticated: true" in helper
    assert "rating" not in helper, "a withdrawal sends no rating; it is not a zero"


def test_api_lib_reads_only_the_callers_own_ratings_back() -> None:
    """``GET .../speaker-feedback`` is scoped to the caller by the server."""
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchMySpeakerFeedback")

    assert "/student/events/" in helper
    assert "/speaker-feedback" in helper
    assert 'method: "GET"' in helper
    assert "authenticated: true" in helper


def test_the_student_feedback_view_type_carries_no_student_identifier() -> None:
    """No response type in this lane has a field a student could be named in.

    Mirrored from the server, where the same absence is the design:
    ``StudentFeedbackView`` carries no ``student_id`` *even though these are the
    caller's own rows*, precisely so no later copy-paste can put one on the
    Connector's response.
    """
    source = API_LIB.read_text(encoding="utf-8")

    for type_name in (
        "StudentSpeakerFeedback",
        "StudentSpeakerFeedbackResult",
        "StudentSpeakerFeedbackList",
        "SpeakerFeedbackSummary",
    ):
        body = _interface_body(source, type_name)
        for forbidden in ("student_id", "student_name", "student_email", "author"):
            assert forbidden not in body, (
                f"{type_name} carries {forbidden!r}; no shape in this lane may identify the "
                "student behind a rating"
            )


def test_the_aggregate_type_mirrors_the_servers_suppression_fields() -> None:
    """The summary carries the threshold, so no page has to know it.

    ``minimum_responses`` exists exactly so a surface can say why nothing is
    published without hard-coding ``3``. A type that dropped it would push the
    number into the bundle.
    """
    source = API_LIB.read_text(encoding="utf-8")
    body = _interface_body(source, "SpeakerFeedbackSummary")

    for required in (
        "speaker_professional_id",
        "suppressed",
        "response_count",
        "mean_rating",
        "display_text",
        "minimum_responses",
    ):
        assert required in body, f"SpeakerFeedbackSummary is missing {required}"

    for forbidden in ("ratings", "comments", "rows", "individual"):
        assert forbidden not in body, (
            f"SpeakerFeedbackSummary carries {forbidden!r}; the Connector's read is an "
            "aggregate and there is no route that would fill such a field"
        )


def test_the_summary_helper_reads_the_connector_route() -> None:
    """``GET /v1/units/{unit_id}/speakers/{speaker_id}/feedback-summary``."""
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchSpeakerFeedbackSummary")

    assert "/speakers/" in helper
    assert "/feedback-summary" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "encodeURIComponent(speakerId)" in helper
    assert 'method: "GET"' in helper
    assert "authenticated: true" in helper


def test_the_unit_aggregate_type_carries_the_same_suppression_fields_and_no_speaker_id() -> None:
    """``UnitFeedbackSummary`` is the per-speaker model with ``unit_id`` in place
    of ``speaker_professional_id``, and nothing else added.

    Addendum 7 September 2026 (OQ-CBA-003's decision, applied a second time at
    unit scope). No per-speaker breakdown, no rated-speaker count and no list
    of speaker ids belongs on this type: every extra number is a handle a
    reader could difference the pooled one against.
    """
    source = API_LIB.read_text(encoding="utf-8")
    body = _interface_body(source, "UnitFeedbackSummary")

    for required in (
        "unit_id",
        "suppressed",
        "response_count",
        "mean_rating",
        "display_text",
        "minimum_responses",
    ):
        assert required in body, f"UnitFeedbackSummary is missing {required}"

    for forbidden in (
        "speaker_professional_id",
        "speakers",
        "by_speaker",
        "breakdown",
        "student_id",
        "student_name",
    ):
        assert forbidden not in body, (
            f"UnitFeedbackSummary carries {forbidden!r}; every extra field here is a handle a "
            "reader could difference the pooled aggregate against or a way to name a student"
        )


def test_the_unit_summary_helper_reads_the_unit_route() -> None:
    """``GET /v1/units/{unit_id}/speaker-feedback-summary`` — one unit, no speaker id."""
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchUnitSpeakerFeedbackSummary")

    assert "/speaker-feedback-summary" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert 'method: "GET"' in helper
    assert "authenticated: true" in helper
    assert "/speakers/" not in helper, (
        "the unit route takes no speaker id; this is a pooled read, not the per-speaker one"
    )


# ---------------------------------------------------------------------------
# OQ-CBA-003 part 1 — nothing individual reaches a Connector
# ---------------------------------------------------------------------------


def test_the_connector_page_never_reads_a_students_own_feedback_route() -> None:
    """The one read that returns individual rows must not be on this page.

    ``GET .../student/events/{event_id}/speaker-feedback`` returns rows with
    ratings and comments on them. It is scoped to its caller server-side, so a
    Connector calling it would get a ``403`` rather than a leak — but a page
    that tried is a page whose author believed the Connector surface is allowed
    individual ratings, and the next change lands accordingly.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "fetchMySpeakerFeedback",
        "speaker-feedback",
        "submitSpeakerFeedback",
        "withdrawSpeakerFeedback",
    ):
        assert forbidden not in code, (
            f"the Connector page references {forbidden!r}; its only feedback read is the "
            "aggregate (OQ-CBA-003 part 1)"
        )


def test_the_connector_page_renders_no_individual_rating_field() -> None:
    """No per-student row, no comment, no drill-through.

    The free-text comment is the sharpest of these: a sentence in a class of
    thirty re-identifies its author whether or not a column says so, which is
    the router module's own argument for why the list route does not exist.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        ".comment",
        "comment}",
        "student_id",
        "studentName",
        "Individual ratings",
        "Each rating",
        "who rated",
        "See all ratings",
    ):
        assert forbidden not in code, (
            f"the Connector page renders {forbidden!r}; a Connector reads an aggregate and "
            "never one student's rating"
        )


def test_the_connector_page_does_not_reconstruct_a_suppressed_aggregate() -> None:
    """Suppression is the server's answer, and arithmetic is not a way around it.

    Below three responses the server sends ``null`` for both numbers *and*
    withholds the count, because "two students rated this speaker" narrows the
    field considerably on its own. A page that averaged, summed, or counted
    anything itself would be publishing what the server declined to.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("reduce(", "/ ratings", "toFixed", "Math.round", "average"):
        assert forbidden not in code, (
            f"the Connector page computes {forbidden!r}; every number it shows must be one "
            "the server chose to send"
        )


def test_the_connector_page_takes_the_threshold_from_the_server() -> None:
    """``minimum_responses`` is rendered; ``3`` is not written down.

    The threshold is a decided value that can move. A page carrying its own copy
    would keep explaining the old one after it did.
    """
    source = CONNECTOR_PAGE.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "minimum_responses" in code, (
        "the page must explain a suppression using the threshold the server sent"
    )
    assert "display_text" in code, (
        "the server sends the sentence to render when it suppresses; render it rather than "
        "composing a dash or a zero"
    )
    assert not re.search(r"(?<![\w.])3(?![\w.])\s*(?:responses|ratings|students)", code), (
        "the suppression threshold must not be hard-coded in the page"
    )


def test_the_connector_page_shows_a_missing_mean_as_absent_not_zero() -> None:
    """ADR-0011 rule 1. A speaker nobody rated must not read as one rated zero."""
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("?? 0", "|| 0", "?? 0.0", "mean_rating || ", "Number(summary"):
        assert forbidden not in code, (
            f"the Connector page coerces a withheld mean with {forbidden!r}; null is an "
            "absence of evidence, never a score of zero"
        )


# ---------------------------------------------------------------------------
# OQ-CBA-053 — feedback is not a matching input
# ---------------------------------------------------------------------------


def test_no_surface_presents_feedback_as_a_matching_input() -> None:
    """No factor reads this table, and no page may imply one does.

    The failure mode is a caption, not a calculation: a mean rendered under
    "match score", or beside a sentence about ranking, tells a Connector
    something false about the engine that a Connector will then act on.
    """
    forbidden = (
        "match score",
        "match_score",
        "matchscore",
        "factor_scores",
        "registry_version",
        "ranks higher",
        "improves their match",
        "boost",
        "weight",
        "scoring input",
    )

    for page in (CONNECTOR_PAGE, STUDENT_PAGE):
        code = _code_only(page.read_text(encoding="utf-8")).lower()
        for term in forbidden:
            assert term not in code, (
                f"{page.name} presents feedback as {term!r}; OQ-CBA-053 keeps student speaker "
                "feedback out of matching entirely"
            )


def test_the_connector_page_says_feedback_does_not_feed_matching() -> None:
    """Silence is not enough where the reader's default assumption is wrong.

    A Connector looking at a mean beside a roster they matched from will assume
    the two are connected unless told otherwise, so the page says so.
    """
    text = CONNECTOR_PAGE.read_text(encoding="utf-8").lower()
    assert "does not feed matching" in text, (
        "the Connector page must state plainly that these ratings do not feed matching"
    )


def test_no_percentage_is_rendered_for_a_rating() -> None:
    """OQ-CBA-005 keeps prominent percentages off CBA surfaces.

    A 1-to-5 mean rendered as "84%" is worse than merely out of scope: it is
    the same shape as a match percentage on a page about speakers, which is
    exactly the confusion OQ-CBA-053 asks these surfaces not to create.
    """
    for page in (CONNECTOR_PAGE, STUDENT_PAGE):
        code = _code_only(page.read_text(encoding="utf-8"))
        assert "%" not in code, f"{page.name} renders a percentage for a rating"


# ---------------------------------------------------------------------------
# frontend-broken-buttons.md — no success the server did not confirm
# ---------------------------------------------------------------------------


def test_the_student_page_holds_no_local_copy_of_a_rating() -> None:
    """What is stored is the server's answer, re-read after every write.

    B07's defect was a control that reported success it had not observed. The
    submit route returns the stored row, so there is a real answer to render and
    no reason to compose one.
    """
    code = _code_only(STUDENT_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "Feedback submitted!",
        "Thanks for your feedback!",
        "setTimeout",
        "Rating saved successfully",
        "optimistic",
    ):
        assert forbidden not in code, (
            f"{STUDENT_PAGE.name} claims a result with {forbidden!r} rather than rendering the "
            "server's own response"
        )

    assert "changed" in code, (
        "the response separates 'this is your rating' from 'this request changed it'; the page "
        "must render the distinction rather than reporting a write it did not cause"
    )
    assert "ApiRequestError" in code, "a refused write must show the server's own message"


def test_the_student_page_offers_no_control_for_an_event_it_cannot_rate() -> None:
    """A student rates their own attendance, and the server says which.

    Eligibility is four server-side facts — the event exists, the speaker is on
    the roster, this student attended, the window is open — and the page must
    not re-derive any of them. What it must not do is *invent* a target: there
    is no student-visible route listing the speakers at an event, so a picker
    would be a list the browser made up, and a free-text id box would be MM-A01
    in a new spelling.
    """
    code = _code_only(STUDENT_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("fetchSpeakerContacts", "fetchConfirmedSpeakers", "fetchSpecialists"):
        assert forbidden not in code, (
            f"{STUDENT_PAGE.name} calls {forbidden!r}, an admin/coordinator read; a student "
            "surface must not be built on a route the server refuses it"
        )

    assert "uuid" not in code.lower(), (
        "a student must never type a speaker id; the id comes from a server response or the "
        "control is not offered"
    )
    assert "edit_window" in code, (
        "whether a rating may still be changed is the server's `edit_window`, never a date the "
        "browser compares"
    )


def test_the_student_page_handles_a_refusal_rather_than_hiding_the_control() -> None:
    """A UI gate is not authorization, and a hidden control is a lie about scope."""
    code = _code_only(STUDENT_PAGE.read_text(encoding="utf-8"))
    assert "cause.message" in code, (
        "the page must render the server's refusal — including the 403 for an event this "
        "student has no attendance record at — rather than pretending no control exists"
    )


# ---------------------------------------------------------------------------
# Addendum 7 September 2026 — the Connector dashboard's unit-level read
# ---------------------------------------------------------------------------





def test_the_dashboard_reads_the_unit_aggregate_and_computes_nothing() -> None:
    code = _code_only(DASHBOARD_PAGE.read_text(encoding="utf-8"))
    assert "fetchManualEvents" in code
    assert "fetchSpeakerEvents" in code
    assert "fetchSpeakers" in code
    for forbidden in (
        "fetchMySpeakerFeedback",
        "fetchSpeakerFeedbackSummary",
        "reduce(",
        "toFixed",
    ):
        assert forbidden not in code


def test_the_dashboard_renders_the_suppressed_state_as_its_own_thing() -> None:
    code = _code_only(DASHBOARD_PAGE.read_text(encoding="utf-8"))
    assert "No speaker handoffs" in code
    for forbidden in ("?? 0", "|| 0", '?? "—"', "Number("):
        assert forbidden not in code


def test_the_dashboard_distinguishes_published_suppressed_and_unavailable() -> None:
    code = _code_only(DASHBOARD_PAGE.read_text(encoding="utf-8"))
    assert "events.error" in code
    assert "handoffs.error" in code
    assert "speakers.error" in code


def test_no_page_reaches_the_retired_legacy_reads() -> None:
    """No ``/api/data/*`` and no ``fetchSpecialists`` on a CBA surface."""
    for page in (CONNECTOR_PAGE, STUDENT_PAGE):
        code = _code_only(page.read_text(encoding="utf-8"))
        assert "/api/data/" not in code, f"{page.name} reaches a retired legacy read"
        assert "fetchSpecialists" not in code, f"{page.name} calls fetchSpecialists"


# ---------------------------------------------------------------------------
# Both surfaces are reachable
# ---------------------------------------------------------------------------


def test_both_pages_are_mounted() -> None:
    """A page nobody can navigate to is not a delivered surface."""
    routes = ROUTES.read_text(encoding="utf-8")

    assert "StudentSpeakerFeedback" in routes
    assert "CoordinatorSpeakerFeedback" in routes
    assert "speaker-feedback" in routes


# ---------------------------------------------------------------------------
# Addendum 9 September 2026 — the roster read is bounded
#
# The Connector page reads one aggregate per speaker, and for a while it read
# them all at once: ``Promise.all`` over the whole roster, one request per
# contact. That is ~116 simultaneous requests on the pilot unit, and the far
# end is not the browser's to size. Each request holds a connection out of a
# SQLAlchemy pool of 5 base plus 5 overflow for the length of
# ``get_current_principal`` alone, so the roster exhausted the pool, queued for
# the 30s ``pool_timeout``, and failed with ``QueuePool limit of size 5
# overflow 5 reached``. The page did not load slowly — it hung, and refused to
# navigate away.
#
# The fix a reader will reach for first is not available. ``GET
# /v1/units/{unit_id}/speaker-feedback-summary`` looks like the bulk form of
# the per-speaker route and is not one: it returns a single pooled mean and
# count for the whole unit, with no speaker id and no breakdown, and the server
# refuses to add one. The per-speaker route is public to the same reader, so
# any extra number on the pooled response is a handle to difference against —
# a unit at ``n=5`` beside a published speaker at ``n=3`` recovers a mean over
# two students. That residual rule is the reason the breakdown is missing, so
# "just add a bulk route" is a privacy regression rather than a refactor. The
# tests below therefore pin the fan-out as *bounded*, not as eliminated, and
# pin the pooled route as staying the dashboard's alone.
# ---------------------------------------------------------------------------

CONCURRENCY_LIB = FRONTEND_SRC / "lib" / "concurrency.ts"

#: The pool has five base connections; a page may hold at most that many.
MAX_ROSTER_FAN_OUT = 5


def _numeric_const(source: str, name: str) -> int:
    """The value of an exported integer constant in a ``.ts`` module."""
    match = re.search(rf"export const {re.escape(name)}\s*=\s*(\d+)\s*;", source)
    assert match is not None, f"{name} is not an exported integer constant"
    return int(match.group(1))


def test_the_connector_page_does_not_issue_one_request_per_speaker_at_once() -> None:
    """The roster read must be bounded, never a fan-out the roster's length.

    This is the regression. ``Promise.all(roster.contacts.map(...))`` scales
    the number of open sockets with server data nobody in the browser chose,
    and the failure it produces is not a slow page but a hung one: the API's
    connection pool is exhausted, every queued request waits out
    ``pool_timeout``, and the whole roster fails at once.

    So the page must reach its per-speaker reads through a helper that caps
    how many are in flight. ``Promise.all`` is forbidden outright here rather
    than pattern-matched for a roster argument, because the safe uses on this
    page (there are none today) are not worth the check that could tell them
    apart from the unsafe one.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    assert "fetchSpeakerFeedbackSummary" in code, (
        "the Connector page no longer reads the per-speaker aggregate at all; if the read "
        "moved, this contract needs to move with it rather than being deleted"
    )

    assert "Promise.all" not in code, (
        "the Connector page fans its per-speaker reads out with Promise.all: that is one "
        "request per speaker in flight at once (~116 on the pilot unit), which exhausts the "
        "API's 5+5 connection pool and hangs the page with a QueuePool timeout"
    )
    for forbidden in ("Promise.allSettled", "Promise.race"):
        assert forbidden not in code, (
            f"the Connector page fans out with {forbidden!r}; the number of simultaneous "
            "per-speaker reads must be bounded by a limit, not by the roster's length"
        )

    assert "mapWithConcurrency" in code, (
        "the Connector page must read its per-speaker aggregates through mapWithConcurrency, "
        "which bounds how many are in flight"
    )


def test_the_connector_pages_fan_out_bound_is_the_pools_base_size() -> None:
    """The cap is a real number, and it is small enough to matter.

    A bound of 200 would satisfy the test above and reproduce the outage. The
    limit the page passes must resolve to at most the pool's five base
    connections, so the five overflow slots stay available to every other
    caller while a roster loads.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))
    assert "DEFAULT_READ_CONCURRENCY" in code, (
        "the page must pass the shared DEFAULT_READ_CONCURRENCY bound rather than an "
        "inline number nobody will find when the pool is resized"
    )

    limit = _numeric_const(CONCURRENCY_LIB.read_text(encoding="utf-8"), "DEFAULT_READ_CONCURRENCY")
    assert 1 <= limit <= MAX_ROSTER_FAN_OUT, (
        f"DEFAULT_READ_CONCURRENCY is {limit}; it must be between 1 and "
        f"{MAX_ROSTER_FAN_OUT} — the API's connection pool has {MAX_ROSTER_FAN_OUT} base "
        "connections plus 5 overflow, and a single page must not claim the overflow"
    )


def test_the_concurrency_helper_actually_bounds_what_it_starts() -> None:
    """The helper is a queue, not a rename of ``Promise.all``.

    A ``mapWithConcurrency`` that started every worker and only *reported*
    them in order would pass the tests above while reproducing the outage
    exactly. Two structural properties keep it honest: it rejects a
    non-positive limit rather than falling back to unbounded, and it starts at
    most ``limit`` lanes.
    """
    source = CONCURRENCY_LIB.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "export async function mapWithConcurrency" in code
    assert "Math.min(limit, items.length)" in code, (
        "mapWithConcurrency must start at most `limit` lanes; starting one per item is the "
        "unbounded fan-out again under a new name"
    )
    assert "RangeError" in code, (
        "mapWithConcurrency must refuse a non-positive limit rather than silently running unbounded"
    )


def test_the_connector_page_still_reports_a_failed_summary_per_speaker() -> None:
    """Bounding the fan-out must not turn N per-speaker errors into one banner.

    The behavior being preserved: a speaker whose summary the server refused
    shows that refusal on that speaker's own card, and the speakers whose
    summaries did come back still render. A ``mapWithConcurrency`` whose
    worker let a rejection escape would discard the whole roster on one
    ``403``, so the catch must stay *inside* the worker and turn the failure
    into a row.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    # The per-speaker failure is still a value on a row, not a thrown error.
    assert "summary: null," in code, (
        "a failed per-speaker read must still produce a row with a null summary"
    )
    assert "ApiRequestError" in code, (
        "the page must still read the server's own message off ApiRequestError for the "
        "speaker whose summary was refused"
    )
    # ...and the card still renders it. `RosterRow.error` and the card's
    # `error !== null` branch are what put it beside that speaker's name.
    assert "error !== null" in code, (
        "the speaker card no longer branches on a per-speaker error; a refused summary "
        "would render as an indefinite 'Loading…' or vanish into a global banner"
    )
    # The roster-level catch is separate and stays separate: it is the read
    # that failed *before* there were any speakers to attribute a failure to.
    assert "setLoadError(" in code, (
        "the roster-level failure path must remain distinct from the per-speaker one"
    )


def test_the_connector_page_does_not_borrow_the_dashboards_pooled_route() -> None:
    """The pooled unit aggregate must not be pressed into service here.

    ``fetchUnitSpeakerFeedbackSummary`` is one mean over the whole unit. It
    carries no speaker id, so there is nothing on it to attribute to a roster
    row, and a page that called it while rendering per-speaker cards would be
    labelling every speaker with the unit's number. Its absence from the
    pooled response is the residual-differencing rule (see this section's
    header), not a gap to route around.
    """
    code = _code_only(CONNECTOR_PAGE.read_text(encoding="utf-8"))

    assert "fetchUnitSpeakerFeedbackSummary" not in code, (
        "the Connector roster page calls the pooled unit route; that response has no "
        "speaker id and cannot be mapped onto a roster row"
    )


def test_the_pooled_route_still_carries_no_per_speaker_breakdown() -> None:
    """The reason the roster cannot be one request, pinned where it is decided.

    If a later change adds ``speakers``, ``by_speaker`` or a rated-speaker
    count to ``UnitFeedbackSummary``, the roster page above *should* be
    rewritten to one call — but that change re-opens the differencing leak the
    per-speaker threshold exists to close, so it must be an explicit decision
    rather than a convenience someone adds to fix a slow page. This test is
    where that conversation gets forced.
    """
    body = _interface_body(API_LIB.read_text(encoding="utf-8"), "UnitFeedbackSummary")

    for forbidden in ("speakers", "by_speaker", "speaker_count", "rated_speakers", "breakdown"):
        assert forbidden not in body, (
            f"UnitFeedbackSummary gained {forbidden!r}. A per-speaker handle on the pooled "
            "response lets a reader difference the pool against an already-published "
            "speaker's count and recover a suppressed group (OQ-CBA-003 part 1)"
        )
