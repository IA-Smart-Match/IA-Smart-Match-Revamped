"""Source contract for the Event Host's confirmed-speaker hand-back (TRACK 4).

Customer §6 step 9 hands an Event Host **the confirmed speaker**. It says
nothing about the professionals who said no, and OQ-CBA-042 settles that
silence as the narrow reading: "An Event Host learning that three named
professionals declined them is a fact about those people's availability and
willingness that nobody agreed to share". The tracking surface belongs to the
Speaker Connector by name and to nobody else.

That decision is only worth as much as the code that keeps it, and the failure
mode is not a deliberate feature — it is a helpful one. A count ("3 others
declined"), a progress bar over the batch, a "nobody has accepted yet, 4 asked"
empty state: each of them publishes the same fact by arithmetic instead of by
name. So this file forbids the vocabulary, forbids the batch reads that carry
it, and requires the empty state to say only that no speaker is confirmed.

The second half is ``frontend-broken-buttons.md`` discipline, which the CBA
handoff is unusually exposed to: ``POST .../speaker-handoff`` returns the
speaker it read back out of the committed rows, so there is never a reason for
this page to render a confirmation it composed itself. A repeat call is a
``200`` with an empty ``applied`` — "they are confirmed" and "this request
confirmed them" are separable in the response, and a page that collapsed them
would report a write it did not cause.

Both routes are ``{admin, coordinator}`` server-side. A UI gate is not
authorization, so the page renders its controls and handles the server's ``403``
as the answer it is, rather than hiding the control and implying it does not
exist.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
HANDOFF_PAGE = FRONTEND_SRC / "app" / "pages" / "volunteer" / "VolunteerConfirmedSpeaker.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
SPEAKER_REQUEST_PAGE = FRONTEND_SRC / "app" / "pages" / "volunteer" / "VolunteerSpeakerRequest.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning. See the sibling files.

    Prose *about* declines — this docstring's own subject — is not a decline
    rendered to an Event Host, and a contract that could not tell the two apart
    would forbid explaining itself.
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


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_reads_the_confirmed_speakers_a_host_is_handed() -> None:
    """The read exists, is authenticated, and is unit-scoped in the path."""
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "fetchConfirmedSpeakers")

    assert "/cba/confirmed-speakers" in helper
    assert "encodeURIComponent(unitId)" in helper, (
        "the unit id must be encoded into the path, never concatenated raw"
    )
    assert "authenticated: true" in helper, (
        "the route is admin/coordinator only; the helper must send the bearer token"
    )
    assert 'method: "GET"' in helper, "listing confirmed speakers is a read"


def test_api_lib_reconciles_a_handoff_from_stored_evidence_only() -> None:
    """The write names an invitation. It cannot assert a stage or a timestamp.

    ``SpeakerHandoffRequest`` has no ``stage`` and no ``reached_at`` field, and
    the router calls that absence the design rather than an omission. A client
    type that grew either one would be offering a browser a way to claim a
    speaker confirmed when no stored row says so.
    """
    source = API_LIB.read_text(encoding="utf-8")
    helper = _helper_body(source, "reconcileSpeakerHandoff")

    assert "/speaker-handoff" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "encodeURIComponent(eventId)" in helper
    assert 'method: "POST"' in helper
    assert "authenticated: true" in helper

    payload = source.split("export interface SpeakerHandoffPayload", 1)
    assert len(payload) == 2, "api.ts must type the handoff request body"
    body = payload[1].split("\n}", 1)[0]
    assert "invitation_id" in body
    assert "attendance_id" in body
    for forbidden in ("stage", "reached_at", "confirmed_at", "occurred_at"):
        assert forbidden not in body, (
            f"the handoff payload lets the browser assert {forbidden!r}; every stage and "
            "timestamp is read out of stored rows server-side"
        )


def test_the_confirmed_speaker_type_has_no_member_inquiry_field() -> None:
    """``Capability.MEMBER_INQUIRY_NARRATIVE`` is False under ProductScope.CBA.

    The router honours it structurally: ``ConfirmedSpeakerView`` carries no such
    field, so no client can render the outcome even by accident. The mirror of
    that shape must not reintroduce one.
    """
    source = API_LIB.read_text(encoding="utf-8")
    declared = source.split("export interface ConfirmedSpeaker {", 1)
    assert len(declared) == 2, "api.ts must type the confirmed-speaker row"
    body = declared[1].split("\n}", 1)[0]

    assert "member_inquiry" not in body
    for field in (
        "record_id",
        "professional_id",
        "event_id",
        "full_name",
        "current_stage",
        "confirmed_at",
        "attended_at",
    ):
        assert field in body, f"the confirmed-speaker row must carry {field!r}"


def test_the_handoff_helpers_carry_no_decline_vocabulary() -> None:
    """OQ-CBA-042, at the client boundary.

    The helpers this page uses must not be a route by which an invitation
    response reaches an Event Host's screen — not the value, not a count of it,
    and not a field named for it.
    """
    source = API_LIB.read_text(encoding="utf-8")
    region = "\n".join(
        (
            _helper_body(source, "fetchConfirmedSpeakers"),
            _helper_body(source, "reconcileSpeakerHandoff"),
        )
    )
    for forbidden in ("decline", "response_status", "rejected", "awaiting_response"):
        assert forbidden not in region.lower(), (
            f"the handoff helpers surface invitation responses: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# The page: it shows who is confirmed, and never who said no
# ---------------------------------------------------------------------------

#: Every spelling of "somebody turned this down" that could reach a Host — the
#: values, the fields that hold them, and the plural nouns a summary would use.
DECLINE_VOCABULARY = (
    "decline",
    "declined",
    "response_status",
    "awaiting_response",
    "rejected",
    "turned down",
    "said no",
    "unavailable",
    "no_response",
)

#: The Connector's own tracking surface. Reading any of it here would ship the
#: declines alongside the acceptance, which is exactly what OQ-CBA-042 refuses:
#: "approximating it by widening this one would ship the declines along with the
#: acceptance".
CONNECTOR_ONLY_READS = (
    "fetchSpeakerInvitationBatches",
    "fetchSpeakerInvitationBatch",
    "recordSpeakerInvitationResponse",
    "dispatchSpeakerInvitationBatch",
    "createSpeakerInvitationBatch",
    "SpeakerInvitationOutcome",
    "SpeakerInvitationResponse",
)


def test_the_page_exists_and_reads_the_only_route_that_answers_it() -> None:
    source = HANDOFF_PAGE.read_text(encoding="utf-8")

    assert "fetchConfirmedSpeakers" in source
    assert "professional_id" in source, (
        "a speaker is identified by the professional_id the server reported, never by name"
    )


def test_the_page_never_names_a_decline() -> None:
    """The narrow reading of OQ-CBA-042, enforced on the rendered source."""
    source = _code_only(HANDOFF_PAGE.read_text(encoding="utf-8")).lower()
    for forbidden in DECLINE_VOCABULARY:
        assert forbidden not in source, (
            f"the Host's confirmed-speaker page surfaces a decline: {forbidden!r}"
        )


def test_the_page_reads_none_of_the_connectors_tracking_surface() -> None:
    source = HANDOFF_PAGE.read_text(encoding="utf-8")
    for forbidden in CONNECTOR_ONLY_READS:
        assert forbidden not in source, (
            f"the Host's page reads the Connector's invitation tracking: {forbidden!r}"
        )


def test_the_page_counts_nothing_it_was_not_handed() -> None:
    """A count is a decline published by arithmetic.

    "1 of 4 answered" tells a Host that three people did not, without naming
    one. The page therefore derives no total from an invitation batch and holds
    no denominator at all — the only cardinality it may state is how many
    speakers are confirmed, which the list it was handed already is.
    """
    source = _code_only(HANDOFF_PAGE.read_text(encoding="utf-8")).lower()
    for forbidden in ("invitations_sent", "total_invited", "invitation_count", "others"):
        assert forbidden not in source, f"the page derives an invitation-batch total: {forbidden!r}"


def test_the_empty_state_says_only_that_nobody_is_confirmed_yet() -> None:
    """ "No speaker is confirmed yet" — and nothing about why.

    An empty state that explained itself would explain the one thing this page
    may not say. The wording is pinned so a later "helpful" rewrite has to
    change a test that says why it is worded that way.
    """
    source = HANDOFF_PAGE.read_text(encoding="utf-8")
    assert "No speaker is confirmed for this event yet." in source, (
        "the empty state must state the absence in the server's own terms"
    )


# ---------------------------------------------------------------------------
# The page: no fabricated success, no client-side scoring
# ---------------------------------------------------------------------------


def test_the_page_renders_the_server_response_and_not_the_form() -> None:
    """B17 discipline: a control may claim nothing a 2xx did not report.

    ``POST .../speaker-handoff`` answers with the speaker it read back out of
    the committed rows and with ``applied`` — the stages *this* request wrote.
    Both come from the response.
    """
    source = HANDOFF_PAGE.read_text(encoding="utf-8")

    assert "reconcileSpeakerHandoff" in source
    assert "applied" in source, (
        "a replay writes nothing and says so; the page must render `applied` rather than "
        "reporting a write it did not cause"
    )
    assert "ApiRequestError" in source, "a refusal must be rendered in the server's own words"


FAKE_SUCCESS_LANGUAGE = (
    "Speaker confirmed!",
    "Handoff complete",
    "Successfully confirmed",
    "Speaker booked",
    "Your speaker is on the way",
    "setConfirmed(true)",
    "Confirmation sent",
)


def test_the_page_announces_no_success_of_its_own_invention() -> None:
    source = HANDOFF_PAGE.read_text(encoding="utf-8")
    for forbidden in FAKE_SUCCESS_LANGUAGE:
        assert forbidden not in source, (
            f"the page reports an outcome the server did not: {forbidden!r}"
        )


def test_the_page_shows_no_match_score_and_computes_none() -> None:
    """OQ-CBA-005 and the anti-pattern beside it: no percentage, no scoring here."""
    source = _code_only(HANDOFF_PAGE.read_text(encoding="utf-8"))

    for forbidden in ("%", "match_score", "toFixed", "weight", "* 100"):
        assert forbidden not in source, (
            f"the confirmed-speaker page renders or derives a score: {forbidden!r}"
        )


def test_the_page_uses_no_retired_or_legacy_source() -> None:
    source = HANDOFF_PAGE.read_text(encoding="utf-8")
    for forbidden in ("fetchSpecialists", "/api/data/", "AgenticOutreachPanel", "CrawlerFeed"):
        assert forbidden not in source, f"a CBA path reaches a retired surface: {forbidden!r}"


# ---------------------------------------------------------------------------
# Authorization is the server's, and a refusal is rendered as one
# ---------------------------------------------------------------------------


def test_the_page_treats_a_refusal_as_an_answer_rather_than_hiding_the_control() -> None:
    """A UI gate is not authorization.

    Both routes are ``{admin, coordinator}``. An account the server refuses is
    told so; the control is not removed on the strength of a role the browser
    read for itself, which would be the browser deciding a permission.
    """
    source = HANDOFF_PAGE.read_text(encoding="utf-8")
    assert "403" in source, "the page must name the server's refusal rather than swallow it"


def test_the_page_composes_no_identifier_in_the_browser() -> None:
    """Stakeholder Fix #7 / MM-A01: the unit is the server's grant, nothing else."""
    source = _code_only(HANDOFF_PAGE.read_text(encoding="utf-8"))

    assert "usePortalAccess" in source
    assert "grantedPortal" in source
    assert "useAuthenticatedPrincipal" in source

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID"):
        assert forbidden not in source, (
            f"the page sources its unit id from the browser: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def test_the_route_is_mounted_in_the_volunteer_portal() -> None:
    source = ROUTES.read_text(encoding="utf-8")
    assert "VolunteerConfirmedSpeaker" in source
    assert "confirmed-speaker" in source


def test_the_host_can_reach_it_from_the_request_they_filed() -> None:
    """§6 closes a loop that §12 opened, so the two pages are linked."""
    source = SPEAKER_REQUEST_PAGE.read_text(encoding="utf-8")
    assert "/volunteer-portal/confirmed-speaker" in source
