"""Source contract for the incoming Speaker Request queue (TRACK 2).

``GET /v1/units/{unit_id}/speaker-requests`` is what an Event Host's §12 intake
becomes on a Speaker Connector's screen: the queue of what people actually
asked for. Two properties of that route decide what a client may render, and
both are easy to lose in a refactor, so both are pinned here.

**Only requests appear, and only because the server said so.** The route
restricts to ``origin = 'coordinator_entry'`` in the repository. A client that
merged this list with anything else — an extracted event, a legacy CSV row —
would be answering "what hosts asked for" with something a crawler produced.
So the page has exactly one source for the queue.

**``truncated`` is an answer, not a hint.** The server reads one row past its
cap so a full page never reads as a complete queue. A page that dropped the
flag would show a Connector a partial queue as if it were the whole thing.

The roster half is held to customer §19. ``SpeakerContactResponse`` carries
``match_eligible`` and a stable ``match_ineligibility_reason`` token precisely
so a screen can tell "the classifier proposed Finance and nobody has checked"
from "we have no idea where this person works" — two states that call for
different actions and would otherwise be one greyed-out row. The page must
render the reason, not just the greying.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
MATCH_RUN_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorMatchRuns.tsx"
HOST_PAGE = FRONTEND_SRC / "app" / "pages" / "volunteer" / "VolunteerMyRequests.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning. See the sibling file."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


# ---------------------------------------------------------------------------
# The client helper
# ---------------------------------------------------------------------------


def test_api_lib_reads_the_speaker_request_queue() -> None:
    """The read exists, is authenticated, and is unit-scoped in the path."""
    source = API_LIB.read_text(encoding="utf-8")

    assert "export async function fetchSpeakerRequests" in source
    assert "/speaker-requests" in source

    helper = source.split("export async function fetchSpeakerRequests", 1)[1].split("\n}", 1)[0]
    assert "encodeURIComponent(unitId)" in helper, (
        "the unit id must be encoded into the path, never concatenated raw"
    )
    assert "authenticated: true" in helper, (
        "the queue is admin/coordinator only; the helper must send the bearer token"
    )
    assert 'method: "POST"' not in helper, "listing the queue is a read"


def test_api_lib_reads_the_hosts_own_filed_requests() -> None:
    """``GET /v1/units/{unit_id}/host/speaker-requests`` — OQ-CBA-014.

    A different route from the queue above, not a filtered call to it: the
    host-scoped read takes no filter beyond the unit, because the only
    predicate the server applies is the verified principal.
    """
    source = API_LIB.read_text(encoding="utf-8")

    assert "export async function fetchMySpeakerRequests" in source
    assert "/host/speaker-requests" in source

    helper = source.split("export async function fetchMySpeakerRequests", 1)[1].split("\n}", 1)[0]
    assert "encodeURIComponent(unitId)" in helper, (
        "the unit id must be encoded into the path, never concatenated raw"
    )
    assert "authenticated: true" in helper
    assert 'method: "POST"' not in helper, "listing your own requests is a read"
    assert "speakerId" not in helper and "host_id" not in helper, (
        "the only predicate is the verified principal; no other identity travels in this call"
    )


def test_the_queue_response_type_keeps_the_truncation_answer() -> None:
    """``truncated`` travels with the rows, because a capped page is not a queue."""
    source = API_LIB.read_text(encoding="utf-8")

    listing = source.split("export interface SpeakerRequestList", 1)
    assert len(listing) == 2, "api.ts must type the queue response rather than returning unknown"
    body = listing[1].split("\n}", 1)[0]

    assert "requests" in body
    assert "truncated" in body
    assert "unit_id" in body


def test_the_contact_type_carries_the_match_eligibility_the_server_computes() -> None:
    """§19's review step is a server answer, and the client must be able to read it.

    Without these two fields a roster picker has to *infer* eligibility from a
    missing classification code — which is a second, unreviewed copy of a rule
    the server already applies, and which cannot distinguish an unreviewed
    proposal from an absent one.
    """
    source = API_LIB.read_text(encoding="utf-8")

    contact = source.split("export interface SpeakerContact {", 1)
    assert len(contact) == 2, "api.ts must still declare the SpeakerContact type"
    body = contact[1].split("\n}", 1)[0]

    assert "match_eligible" in body
    assert "match_ineligibility_reason" in body


# ---------------------------------------------------------------------------
# The page: the queue
# ---------------------------------------------------------------------------


def test_the_page_reads_the_queue_from_the_only_route_that_answers_it() -> None:
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")

    assert "fetchSpeakerRequests" in source
    assert "request_id" in source, "a queued request must be selected by the server's own id"


QUEUE_FORBIDDEN_SOURCES = (
    "fetchEvents",
    "fetchCalendarEvents",
    "fetchCoordinatorEvents",
    "fetchCrawlerResults",
    "CppEvent",
)


def test_the_page_merges_nothing_into_the_queue() -> None:
    """One source. An extracted or legacy row is not a thing a host asked for."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")
    for pattern in QUEUE_FORBIDDEN_SOURCES:
        assert pattern not in source, (
            f"CoordinatorMatchRuns blends a non-request source into the queue: {pattern!r}"
        )


def test_the_page_renders_the_truncation_flag() -> None:
    """A capped queue must say it is capped."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")
    assert "truncated" in source


# ---------------------------------------------------------------------------
# The page: the roster picker
# ---------------------------------------------------------------------------


def test_the_roster_picker_comes_from_the_unit_contact_roster() -> None:
    """``fetchSpeakerContacts``, and nothing that resembles the retired specialist list."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")

    assert "fetchSpeakerContacts" in source
    assert "professional_id" in source, (
        "candidates are named by the professional_id the roster reported, never by name"
    )


def test_the_roster_picker_surfaces_why_a_contact_is_not_selectable() -> None:
    """A greyed-out row that says nothing is a worse answer than no row at all."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")

    assert "match_eligible" in source
    assert "match_ineligibility_reason" in source
    assert "disabled" in source, "an ineligible contact must not be selectable"


def test_the_roster_picker_decides_no_eligibility_of_its_own() -> None:
    """Eligibility is read, never recomputed.

    Re-deriving it from ``primary_industry_code == null`` would be a second
    copy of customer §19's review rule living in a bundle nobody versions, and
    it would call an unreviewed classifier proposal "classified".
    """
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))

    for forbidden in (
        "primary_industry_code === null",
        "primary_role_code === null",
        "primary_industry_code == null",
        "primary_role_code == null",
    ):
        assert forbidden not in source, (
            f"CoordinatorMatchRuns recomputes match eligibility client-side: {forbidden!r}"
        )


def test_the_page_never_invents_a_reason_the_server_did_not_send() -> None:
    """An unrecognised token is rendered as itself, not swallowed.

    The reason vocabulary grows server-side. A client that mapped unknown
    tokens onto a friendly catch-all would report the wrong cause the first
    time the server added one — so the raw token is the fallback.
    """
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")
    assert "MATCH_INELIGIBILITY_EXPLANATIONS" in source, (
        "the page must hold its reason wording in one named table with a raw-token fallback"
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_the_page_composes_no_identifier_in_the_browser() -> None:
    """The unit is the server's grant, not an env var and not a query string.

    Stakeholder Fix #7 / MM-A01: the browser asserts no tenant, no user, no
    role and no unit. ``GET /v1/me/portals`` says which unit this account was
    granted, and that is the only unit this page reads or writes.
    """
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))

    assert "usePortalAccess" in source
    assert "grantedPortal" in source
    assert "useAuthenticatedPrincipal" in source

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID", "unit_id="):
        assert forbidden not in source, (
            f"CoordinatorMatchRuns sources its unit id from the browser: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# The Event Host's own read (OQ-CBA-014, closed 7 September 2026)
# ---------------------------------------------------------------------------


def test_the_host_page_reads_only_the_host_route() -> None:
    """``VolunteerMyRequests.tsx`` calls the host-scoped read and never the queue.

    The queue holds every host's filings for the unit and is
    ``admin``/``coordinator`` only server-side. A page built for an Event
    Host that imported it would be a client reaching for a route the server
    refuses that account, and the next edit could easily "fix" the refusal
    by widening a role set that OQ-CBA-014 deliberately narrowed.
    """
    source = HOST_PAGE.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "fetchMySpeakerRequests" in code
    assert "fetchSpeakerRequests" not in code.replace("fetchMySpeakerRequests", ""), (
        "VolunteerMyRequests imports the Connector's queue helper; it must call only the "
        "host-scoped route"
    )


def test_the_host_page_renders_a_list_an_empty_state_and_an_error_state() -> None:
    """Three renderable outcomes, and none of them is silence.

    A list of what was filed, a stated empty state that explains the
    pre-migration gap rather than implying nothing was ever filed, and a
    rendered server refusal — the same three-state discipline every other
    read page in this portal follows.

    Since TRACK T1 the list is drawn a page at a time, so the rows are mapped
    from the pager's slice. The claim held here is the one that mattered all
    along and is unchanged: the whole array the host-scoped read returned is
    what reaches the list, and every row on the current page is rendered from
    it. The pager is a window over that array, not a filter on it.
    """
    source = HOST_PAGE.read_text(encoding="utf-8")
    code = _code_only(source)

    assert "items={requests}" in code, (
        "the whole result of the host-scoped read must reach the list, unfiltered"
    )
    assert "visibleRequests.map" in code, "a non-empty result must render each request on the page"
    assert "request.request_id" in code or "request_id" in code, (
        "each rendered request must be keyed by the server's own id"
    )
    assert "requests.length === 0" in code, "an empty result must be its own branch"
    assert "loadError" in code, "a refused or failed read must be its own branch"
    assert "ApiRequestError" in code, "a 403 must render as the server's own refusal"


def test_the_host_page_names_the_pre_migration_gap_honestly() -> None:
    """A pre-``0033`` request the host filed is invisible to them, and the empty
    state must say so rather than implying nothing was ever filed.
    """
    text = HOST_PAGE.read_text(encoding="utf-8")
    assert "7 September 2026" in text, (
        "the empty state must name the date before which a filed request has no recorded filer"
    )


def test_the_host_page_composes_no_identifier_in_the_browser() -> None:
    """The unit is the server's grant, not an env var and not a query string.

    Stakeholder Fix #7 / MM-A01, mirrored from the Connector's own queue page:
    the browser asserts no tenant, no user, no role and no unit. ``GET
    /v1/me/portals`` says which unit this account was granted, and that is
    the only unit this page reads.
    """
    source = _code_only(HOST_PAGE.read_text(encoding="utf-8"))

    assert "usePortalAccess" in source
    assert "grantedPortal" in source
    assert "useAuthenticatedPrincipal" in source

    for forbidden in ("getConfiguredUnitId", "VITE_SMARTMATCH_UNIT_ID", "unit_id=", "?host_id"):
        assert forbidden not in source, (
            f"VolunteerMyRequests sources an identifier from the browser: {forbidden!r}"
        )
