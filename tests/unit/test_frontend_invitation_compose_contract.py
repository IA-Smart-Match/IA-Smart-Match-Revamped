"""Source contract for the Connector's invitation-compose surface (TRACK 3).

``CoordinatorOutreach.tsx`` says, in its own words, why it has no compose form:

    composing a batch needs the roster ids a Connector picked off a shortlist,
    which is the match-run screen's output rather than something to retype.

TRACK 2 built that screen, so the shortlist now exists as a server row. This
file guards the page that finally composes from it, and it guards it against
the four ways an invitation UI goes wrong.

**It may not ask anybody to type an id.** A form with a UUID field is a control
that only works for someone who has already queried the database, which is not
a Connector — the same objection ``CoordinatorOutreach.tsx`` raises against a
``contact_channel_id`` box, applied to ``professional_id``. Every recipient on
this page arrives from ``GET /v1/units/{unit_id}/match-runs/{match_run_id}``,
whose ``shortlist`` carries the ``subject_id``s the server itself chose.

**It may not compose for somebody who has not consented.** The batch route
checks consent, the dispatch checks it again, and the worker checks it a third
time — but a Connector who learns from a job log that three of their twelve
names could not be written to has been told too late. So the page reads each
shortlisted person's channels, renders the server's own ``send_eligible``,
``suppressed``, ``contact_state`` and ``consent_source``, and makes an
unconsented recipient non-selectable *with the reason visible*. That gating is
a courtesy and a disclosure; it is never authorization, which stays server-side
and deny-by-default on every one of these routes.

**It may not say anything was sent.** ``POST .../batches`` composes rows and
submits nothing at all. The strongest true word for a composed batch is
"queued" — B17's lesson, applied one step earlier than the outreach Send button
had to learn it.

**It may not become a second dispatch screen.** Dispatch and tracking live in
``CoordinatorOutreach.tsx``. A second control that submits ``outreach.send`` is
a second place the delivery-time consent recheck has to be reasoned about.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
COMPOSE_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorInvitations.tsx"
OUTREACH_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorOutreach.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    The same call ``test_frontend_no_fake_success_contract.py`` and
    ``test_frontend_match_run_contract.py`` make, for the same reason: these
    files explain the rules they obey, and a raw scan would fail on a file's own
    account of why it passes — which trains the next person to delete the
    explanation rather than keep the guard.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_exposes_the_compose_and_consent_reads() -> None:
    """Compose, and the read that lets a Connector see who cannot be written to.

    ``createSpeakerInvitationBatch`` has existed since the invitations card and
    was called by nothing. ``fetchSpeakerContactChannels`` is what makes "why
    can I not invite this person" answerable *before* composing rather than only
    afterwards, out of the batch's skip reasons.
    """
    source = API_LIB.read_text(encoding="utf-8")

    assert "export async function createSpeakerInvitationBatch" in source
    assert "export async function fetchSpeakerContactChannels" in source
    # The shortlist this page composes from is a server row, read back.
    assert "export async function fetchMatchRun" in source


def test_create_batch_sends_exactly_the_contract_body() -> None:
    """The five fields ``BatchCreateRequest`` declares, and the omissions.

    ``contracts/openapi/smartmatch.json`` is explicit that a caller supplies no
    template, no body, no recipient address and no response link. The template
    is the server's closed registry; the address is resolved from the
    recipient's own stored channels; and a browser-supplied link would put an
    arbitrary URL into an institutional email over an already-consented
    address, which is a phishing primitive rather than a parameter.
    """
    source = API_LIB.read_text(encoding="utf-8")

    for field in (
        "professional_ids",
        "event_name",
        "event_date",
        "coordinator_name",
        "match_run_id",
    ):
        assert field in source, f"createSpeakerInvitationBatch drops {field!r}"
    # The create documents `Idempotency-Key` as required and unique per unit.
    assert "Idempotency-Key" in source

    call = source.split("export async function createSpeakerInvitationBatch", 1)
    assert len(call) == 2
    body = call[1].split("\n}", 1)[0]
    for forbidden in (
        "template_id",
        "recipient_address",
        "response_link",
        "tenant",
        "actor",
    ):
        assert forbidden not in body, (
            f"createSpeakerInvitationBatch gained a field the server owns: {forbidden!r}"
        )


def test_the_channel_type_carries_the_servers_own_consent_answer() -> None:
    """``send_eligible`` is read, never re-derived.

    The server computes it at read time from state, source and suppression
    together. A browser that recomputed "consented" from any subset of those
    would be a second answer to "may we write to this person", and the
    disagreement between two such answers always resolves toward sending.
    """
    source = API_LIB.read_text(encoding="utf-8")
    declaration = source.split("export interface SpeakerContactChannel", 1)
    assert len(declaration) == 2, "api.ts must type the channel row rather than returning unknown"
    body = declaration[1].split("\n}", 1)[0]

    for field in (
        "contact_channel_id",
        "channel_kind",
        "address",
        "contact_state",
        "suppressed",
        "send_eligible",
        "consent_source",
    ):
        assert field in body, f"the channel type drops {field!r}"


# ---------------------------------------------------------------------------
# The page: recipients come from the run, never from a keyboard
# ---------------------------------------------------------------------------


def test_compose_page_reads_its_recipients_from_the_match_run() -> None:
    """The shortlist is a server row, and this page opens it by id from the URL."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")

    assert "fetchMatchRun" in source
    assert "shortlist" in source
    assert "subject_id" in source, "the recipient ids must come from the run's own shortlist"


HAND_ENTERED_ID_FORBIDDEN = (
    "uuid",
    "UUID",
    "Paste",
    "paste",
    'placeholder="professional',
    'placeholder="subject',
    'placeholder="Speaker id',
)


def test_compose_page_never_asks_anybody_to_type_an_identifier() -> None:
    """No id field, and no copy that invites one.

    A UUID box is a control that only works for someone who has already queried
    the database. Every identifier on this page is one the server handed over:
    the unit from ``GET /v1/me/portals``, the run from the shortlist link, and
    each ``subject_id`` from the run itself.
    """
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))
    for pattern in HAND_ENTERED_ID_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorInvitations asks for a hand-entered identifier: {pattern!r}"
        )

    # The only free text the Connector supplies is the message's own copy.
    typed_inputs = re.findall(r'<input[^>]*type="text"[^>]*>', source, flags=re.DOTALL)
    for element in typed_inputs:
        assert "professional" not in element and "subject" not in element, (
            f"CoordinatorInvitations has a text input for an identifier: {element!r}"
        )


# ---------------------------------------------------------------------------
# The page: consent is surfaced, and it gates selection
# ---------------------------------------------------------------------------


def test_compose_page_reads_and_renders_the_consent_state() -> None:
    """Told at the moment they act, not out of a job log afterwards."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")

    assert "fetchSpeakerContactChannels" in source
    for field in ("send_eligible", "suppressed", "contact_state", "consent_source"):
        assert field in source, f"the compose page hides the server's {field!r}"


def test_compose_page_makes_an_unconsented_recipient_non_selectable() -> None:
    """Disabled, and disabled *with the reason beside it*.

    A greyed-out row with no explanation tells a Connector that something is
    wrong and nothing about what to do, which is the state the batch route's
    skip reasons exist to avoid reproducing.
    """
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))

    assert "disabled=" in source, "an unconsented recipient must not be selectable"
    assert 'type="checkbox"' in source
    assert "no_contact_channel" in source or "holds no address" in source, (
        "the compose page must name why a recipient cannot be invited"
    )


def test_compose_page_defers_to_the_server_for_authorization() -> None:
    """The rule the non-negotiables state, kept where it can be broken."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")
    assert "server" in source


# ---------------------------------------------------------------------------
# The page: a composed batch is queued, and nothing here sends it
# ---------------------------------------------------------------------------


FAKE_SUCCESS_FORBIDDEN = (
    "Invitations sent",
    "Invitation sent",
    "Message sent",
    "Sent!",
    "successfully",
    "Success!",
    "console.log",
    "setTimeout",
)


def test_compose_page_never_claims_an_invitation_was_sent() -> None:
    """``POST .../batches`` composes rows and submits nothing at all."""
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))
    for pattern in FAKE_SUCCESS_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorInvitations reintroduced a fabricated success: {pattern!r}"
        )


def test_compose_page_reports_the_queued_state_it_actually_has() -> None:
    """The positive half. Forbidding "sent" is not a contract on its own."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")

    assert "Queued" in source
    assert "invited_count" in source
    assert "skipped_count" in source
    assert "skip_reason" in source, "every name submitted comes back invited or skipped"


def test_dispatch_and_tracking_stay_on_the_outreach_page() -> None:
    """One dispatch control in the product, and it is not on this page."""
    compose = COMPOSE_PAGE.read_text(encoding="utf-8")
    outreach = OUTREACH_PAGE.read_text(encoding="utf-8")

    assert "dispatchSpeakerInvitationBatch" not in compose
    assert "dispatchBatch" not in compose
    assert "recordSpeakerInvitationResponse" not in compose

    assert "dispatchBatch" in outreach, "dispatch must remain on CoordinatorOutreach"
    assert "useSpeakerInvitations" in outreach


# ---------------------------------------------------------------------------
# The page: no score, no scoring, no weights
# ---------------------------------------------------------------------------


PERCENTAGE_FORBIDDEN = (
    "* 100",
    "*100",
    "%",
    "percent",
    "Percent",
    "Match Score",
    "match_score",
    "heuristic_score",
    "fit score",
    "Fit Score",
)


def test_compose_page_displays_no_percentage_anywhere() -> None:
    """OQ-CBA-005, held at the third surface that could break it."""
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))
    for pattern in PERCENTAGE_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorInvitations renders a match percentage: {pattern!r}"
        )


CLIENT_SCORING_FORBIDDEN = (
    ".sort(",
    ".reduce(",
    "Math.max",
    "Math.min",
    "Math.round",
    "weights",
    ".weight",
    "toFixed",
)


def test_compose_page_computes_nothing_the_server_ranked() -> None:
    """The server ranked this shortlist; the page composes to it in run order."""
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))
    for pattern in CLIENT_SCORING_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorInvitations re-orders or re-scores the shortlist: {pattern!r}"
        )


def test_compose_page_carries_no_numeric_weight_literal() -> None:
    """No decimal literal at all — blunter than "no weights", and firmer."""
    source = _code_only(COMPOSE_PAGE.read_text(encoding="utf-8"))
    offenders = re.findall(r"(?<![\w.\-])\d+\.\d+(?![\w])", source)
    assert offenders == [], (
        f"CoordinatorInvitations carries literals that could be factor weights: {offenders}"
    )


def test_compose_page_surfaces_the_registry_version_from_the_run() -> None:
    """Provenance travels with the shortlist somebody is about to act on."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")
    assert "registry_version" in source


CBA_FORBIDDEN_SURFACES = (
    "fetchSpecialists",
    "/api/data/",
    "AgenticOutreachPanel",
    "rankSpeakers",
    "scoreSpeaker",
    "fetchPipeline",
)


def test_compose_page_touches_none_of_the_retired_surfaces() -> None:
    """Non-negotiable: no ``fetchSpecialists``, no ``/api/data/*``, no agentic panel."""
    source = COMPOSE_PAGE.read_text(encoding="utf-8")
    for pattern in CBA_FORBIDDEN_SURFACES:
        assert pattern not in source, (
            f"CoordinatorInvitations reaches a retired legacy surface: {pattern!r}"
        )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_the_compose_page_is_mounted_in_the_coordinator_portal() -> None:
    """A UI route is a claim about what exists, never an authorization decision."""
    source = ROUTES.read_text(encoding="utf-8")
    assert "CoordinatorInvitations" in source
    assert '"invitations"' in source or "'invitations'" in source
