"""SmartMatch API application.

The routes here are those whose contracts and gates are settled. Feature routes
arrive with their release, behind their gates — a route that exists before its
gate closes is a route someone will call.

What is **not** present, and why:

* ``POST /auth/mock-login`` — archived (MM-A01), and **not** what
  ``routers/auth.py`` restores. Caller-selected identity was the single most
  dangerous pattern in the legacy baseline
  (``bdce024:src/api/routers/portals.py:435``): that route let a caller *choose*
  who they were. ``POST /v1/auth/login`` requires a secret only the account
  holder has, and the local account, tenant, and roles are still read
  server-side from ``user_account`` and ``membership`` — never from the request.
  It is a pilot-scoped stand-in for institutional sign-in, authorized by the
  owner on 2026-09-04 and recorded in
  ``docs/decisions/pilot-login-decision-2026-09-04.md``; it is not A1b, does not
  unblock it, and leaves the JWKS verifier unwired.
* ``GET /v1/me/portals`` — the authenticated account-to-portal mapping the
  portal shells were blocked on, derived from the caller's own memberships and
  taking no parameter at all. Deliberately not ``/api/portals/{id}``: a portal
  follows from who you are, not from an id you send.
* Match-run, discovery, and send commands — each waits on its gate: G1 for the
  factor registry, G3 for agent controls, G4 for consent-origin policy. The
  submission machinery they will use is built and exercised by ``/imports``.
* Any handler that calls a provider inline — prohibited by v1.1 §1.6. The
  request path records intent; the dispatcher moves it; the worker performs it.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse
from smartmatch_domain.product_scope import Capability
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import build_token_verifier
from starlette.datastructures import Headers
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smartmatch_api.config import (
    Settings,
    check_speaker_portal_startup,
    get_settings,
    require_exercise_workspace_secret,
)
from smartmatch_api.dependencies import DbSession
from smartmatch_api.errors import EXCEPTION_HANDLERS, ErrorEnvelope, error_response
from smartmatch_api.routers import (
    attendance,
    auth,
    calendar,
    cba_contact_channels,
    cba_contacts,
    cba_handoff,
    cba_invitations,
    engagement,
    events,
    exercise_instructor,
    exercise_instructor_refresh,
    exercise_instructor_session,
    exercise_matching,
    exercise_public,
    exercise_results,
    exercise_workspace,
    host_organizations,
    imports,
    jobs,
    manual_events,
    match_runs,
    matching_weights,
    me,
    me_contact_channels,
    meetings,
    metrics,
    outreach,
    outreach_contacts,
    pipeline,
    portals,
    redrive,
    review,
    rewards,
    speaker_availability,
    speaker_pipeline,
    speaker_portal,
    speaker_requests,
    speaker_self,
    student_events,
    student_speaker_feedback,
)
from smartmatch_api.token_pages import install_access_log_redaction

#: Most bytes any request body may occupy, enforced ahead of the FastAPI
#: application entirely. Shares its value with
#: :data:`smartmatch_api.routers.imports.MAX_INLINE_ROWS_BYTES` rather than
#: restating it: the two are the same bound, not two bounds that happen to
#: agree today.
#:
#: This used to be checked only inside ``routers/imports.py``, after Pydantic
#: had already read and parsed the entire body to build ``ImportRequest`` —
#: which meant a request with an enormous raw body had already paid that cost
#: before the router got a chance to refuse it. :class:`MaxBodySizeMiddleware`
#: below is what "ahead of parsing" actually requires: an ASGI layer that runs
#: before routing, before dependency resolution, before anything reads the
#: body into a pydantic model.
MAX_REQUEST_BODY_BYTES: Final[int] = imports.MAX_INLINE_ROWS_BYTES


def _declared_content_length(scope: Scope) -> int | None:
    """The request's own ``Content-Length``, or ``None`` if absent or unparseable.

    An unparseable value is left for Starlette's own request handling to
    reject downstream; this only short-circuits the case that matters here — a
    client that honestly declares a body larger than the bound, which can be
    refused without reading a single byte of it.
    """
    value = Headers(scope=scope).get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class MaxBodySizeMiddleware:
    """Reject a request body over ``max_bytes`` before anything downstream parses it.

    Two checks, in order:

    1. ``Content-Length``, when the client sends one. An honest, oversized
       declaration is refused without reading any of the body.
    2. The running total of bytes actually received. A client that lies about
       ``Content-Length``, or sends chunked with none at all, is still bounded:
       the body is buffered chunk by chunk, and the moment the total crosses
       ``max_bytes`` the request is rejected and the wrapped application is
       never invoked — it never sees an oversized body, parsed or otherwise.

    A body that fits is buffered in full and replayed to the wrapped
    application exactly as received; nothing about a well-formed request
    changes, and it is read from the network at most once either way.

    Applied ahead of every route rather than only the one that motivated it
    (``POST /v1/units/{unit_id}/imports``): an ASGI middleware runs before
    routing, so it cannot know which handler a request will reach without
    reimplementing the router's own path matching. Every other route in this
    application accepts a body far smaller than :data:`MAX_REQUEST_BODY_BYTES`
    (``routers/redrive.py``'s ``RedriveRequest`` has no field remotely this
    large), so one bound shared by the whole app costs those routes nothing.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self._max_bytes:
            await self._reject(scope, receive, send)
            return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                buffered.append(message)
                break
            total += len(message.get("body", b""))
            if total > self._max_bytes:
                await self._reject(scope, receive, send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def _replay() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self._app(scope, _replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = error_response(
            status.HTTP_413_CONTENT_TOO_LARGE,
            code="request_body_too_large",
            message=f"Request body must be at most {self._max_bytes} bytes.",
        )
        await response(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build shared resources once per process.

    The session factory and token verifier are constructed here rather than per
    request: a connection pool created per request is not a pool, and a verifier
    rebuilt per request would discard the key cache a real JWKS verifier needs.

    Settings are read (and validated) at startup, so a misconfigured
    deployment — a classroom edition carrying provider credentials, say — fails
    to boot rather than failing later under load.

    ## The token verifier is built only where there is a login

    ADR-0025 D1 makes ``get_current_principal`` *unreachable* in the
    class-exercise scope by not mounting any router that resolves one. Building
    the verifier anyway would leave the other half of that machinery sitting on
    ``app.state`` in a process with nothing to verify — one line in a future
    handler away from being the bypass D9 rejected. A product with no login has
    no token, so it builds nothing to check one with, and
    ``app.state.token_verifier`` is set to ``None`` rather than left unset, so a
    reader of the state sees a decision rather than an omission.

    ``AUTHENTICATED_LOGIN`` is the condition rather than a comparison against
    ``ProductScope.CLASS_EXERCISE``: it is the same capability
    ``routers_for`` drops the principal-bearing infrastructure routers on, so
    the verifier exists in exactly the processes that mount something able to
    use it, and a later scope with a login gets it without editing this line.

    The session factory is built in every scope. The exercise has its own
    ``exercise_`` tables and will need it; what it must not have is a principal.
    Nothing here issues a query in any scope.
    """
    settings = get_settings()

    app.state.settings = settings
    # The product-scope decisions this process booted with, resolved once so a
    # handler or a diagnostic reads the same answers composition used above
    # rather than re-deriving them from `product_scope` and drifting.
    app.state.product_scope = settings.product_scope
    app.state.enabled_capabilities = settings.enabled_capabilities()
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.token_verifier = (
        build_token_verifier(
            settings.edition,
            use_fixture=settings.use_fixture_providers,
            fixture_principals=settings.dev_principals,
        )
        if settings.capability_enabled(Capability.AUTHENTICATED_LOGIN)
        else None
    )

    yield

    app.state.session_factory.kw["bind"].dispose()


app = FastAPI(
    title="SmartMatch API",
    version="0.1.0",
    description=(
        "IA West SmartMatch platform API — Foundation scaffold. "
        "OpenAPI is the source of truth; the TypeScript client is generated from "
        "it and never hand-maintained."
    ),
    lifespan=lifespan,
    responses={
        400: {"model": ErrorEnvelope},
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        # Declared explicitly, which also *replaces* FastAPI's automatic 422.
        # Left to itself it documents ``HTTPValidationError`` — the second error
        # shape — on every route that takes a parameter, so the contract would
        # advertise a body the API no longer returns.
        422: {"model": ErrorEnvelope},
        # Answered by MaxBodySizeMiddleware, ahead of every route — not by any
        # handler — so it is declared here rather than per-route.
        413: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
    },
)

for exception_type, handler in EXCEPTION_HANDLERS.items():
    app.add_exception_handler(exception_type, handler)

# The outermost ASGI layer: it must see every request before FastAPI's own
# routing and dependency resolution do, which is what "ahead of parsing" means
# for an oversized body. See MaxBodySizeMiddleware's docstring.
app.add_middleware(MaxBodySizeMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)

#: Infrastructure routers: the durable command/job substrate every capability
#: rides on, and the operator paths that keep it honest. They are not a product
#: capability of their own — there is no version of this product that offers
#: match runs but not the job lifecycle that carries them — so they are not
#: classified in the capability table below.
#:
#: They are, however, every one of them *principal-bearing*: each route here
#: resolves a principal and authorizes against a tenant. So they ride
#: `AUTHENTICATED_LOGIN` — not as a product decision about the job substrate,
#: but as the plain statement that a product with no login has nobody to serve
#: them to. ADR-0025 D1 requires the authenticated CBA routers to be *absent*
#: from the route table in the class-exercise scope, so that
#: `get_current_principal` is unreachable rather than bypassed (D9 rejected the
#: per-route bypass). Leaving these five mounted unconditionally would have made
#: that statement false for five routers while the table made it true for the
#: rest.
#:
#: Under both scopes that have a login — `cba` and `ia_west_legacy` — this
#: mounts exactly what mounting them unconditionally did, so the served contract
#: is unchanged.
#:
#: `review.unit_router` is the unit-scoped half of the same resource:
#: `GET /v1/units/{unit_id}/review-items`, the queue behind the
#: `pending_review_items` badge `routers/metrics.py` already published. Listed
#: separately rather than folded into `review.router` because the two prefixes
#: genuinely differ — `/v1/units` against `/v1/review-items` — and a FastAPI
#: prefix cannot be escaped per-route. It stays beside the decision route it is
#: the read half of: a route that lists what another route decides should not be
#: able to disappear separately from it.
PRINCIPAL_BEARING_INFRASTRUCTURE_ROUTERS: Final[tuple[APIRouter, ...]] = (
    jobs.router,
    redrive.router,
    engagement.router,
    review.router,
    review.unit_router,
)

#: Every router that answers to a named product capability, paired with the
#: capability it serves.
#:
#: This is the API half of the single CBA scope policy in
#: ``smartmatch_domain.product_scope``; the frontend half is
#: ``apps/web/legacy-frontend/src/lib/productScope.ts``. Composition asks the
#: policy rather than restating it, so "which product is this" is answered in
#: one place and read in two.
#:
#: Under the default CBA scope every capability listed here is enabled, so the
#: mounted route set — and therefore the committed OpenAPI contract — is exactly
#: what it was before this table existed. The capabilities CBA *does* gate
#: (external acquisition, cold unknown-contact outreach, chapter dues, the
#: ``member_inquiry`` narrative) own no router at all: they were never mounted,
#: and this is the declaration that says so on purpose rather than by accident.
#:
#: Mounting is decided once, at import, from the settings the process booted
#: with. A route set that changed per request would be a different application
#: on every call, and the generated contract could not describe either one.
CAPABILITY_SCOPED_ROUTERS: Final[tuple[tuple[APIRouter, Capability], ...]] = (
    (imports.router, Capability.OPERATOR_RECORD_IMPORT),
    (me.router, Capability.AUTHENTICATED_LOGIN),
    (metrics.router, Capability.DISCOVERY_METRICS),
    # The same register, presented as a funnel. `DISCOVERY_METRICS` and not a
    # capability of its own: this router measures nothing `metrics.router` does
    # not already measure, through the same owning queries and the same
    # authorization, so a deployment that offered one and withheld the other
    # would be offering and withholding the identical numbers.
    (speaker_pipeline.router, Capability.DISCOVERY_METRICS),
    (events.router, Capability.EVENT_READS),
    # The .ics download, classified with `events` because that is what it is:
    # the same event, in a second representation, behind the same roles
    # (`routers/calendar.py` restates `routers/events.py::_EVENT_ROLES`) and
    # under the same `/v1/units` prefix. It is not infrastructure — it is a
    # user-facing read, and a product that did not offer event reads has no
    # coherent reason to hand out an .ics of an event it does not show.
    #
    # Reading it next to `events` here is also how a later change to one is
    # noticed as a change to the pair.
    #
    # G5 (Calendar API) stays deferred and this does not reopen it: the route
    # makes no network call, holds no credential, and writes into nobody's
    # calendar. See `docs/plans/open-questions/calendar-deferred.md`.
    (calendar.router, Capability.EVENT_READS),
    # The student's two reads of the same catalog (customer §15, card
    # `CBA-STUDENT-EVENTS`). `EVENT_READS` again, and for the reason `calendar`
    # is: this is the same event in a third presentation, behind a different
    # role, and a product that offers no event reads has nothing for a student
    # to browse. Its own capability would have implied a deployment could offer
    # the coordinator catalog and withhold the student one, which is not a
    # decision any committed artifact makes — customer §22 keeps event reads and
    # §15 says students are among the readers.
    #
    # Since `CBA-STUDENT-REGISTRATION` this router also carries the two
    # registration *writes*, and they ride `EVENT_READS` rather than taking a
    # capability of their own. That is the opposite of the decision
    # `SPEAKER_REQUEST_INTAKE` below makes about a write, so it has to be argued
    # rather than assumed.
    #
    # That capability exists because a product showing a coordinator the event
    # catalog without accepting Speaker Requests is coherent, and so is the
    # reverse: two genuinely separable products. A student catalog without
    # registration is not that shape. It is the state this page was in for
    # exactly one card, and `docs/plans/frontend-broken-buttons.md` B06 names it
    # a defect rather than a smaller product — a Register button with nothing
    # behind it, or a browse list relabelled to conceal that there was nothing.
    # A separate capability would make that degraded state a *supported*
    # configuration, which is the thing nobody wants to be able to ship again.
    #
    # What has not changed is that this is not an *attendance* surface.
    # Registration writes `event_registration`; `attendance_record` is attendance
    # and ADR-0013 makes it the only input to points, so nothing on this router
    # writes it. See `routers/student_events.py` and migration `0026`.
    (student_events.router, Capability.EVENT_READS),
    # The Speaker Request intake and its queue (customer §§12-13). Its own
    # capability rather than a share of `events`, and the distinction is the
    # direction of the arrow: `events` and `calendar` hand a coordinator what
    # the system already holds, and this one is how something new gets into it.
    # A product could offer either without the other, so gating them together
    # would make one decision look like two.
    #
    # It is not `OPERATOR_RECORD_IMPORT` either, which is an operator loading
    # records the institution already holds through the quarantine/review path.
    # A host filing a request is a person stating a new intention, and it has no
    # review queue in front of it — see `routers/speaker_requests.py`.
    (speaker_requests.router, Capability.SPEAKER_REQUEST_INTAKE),
    # The Event Host's own organization and the Connector's directory of them
    # (migration 0036). `SPEAKER_REQUEST_INTAKE` rather than a capability of
    # its own, and the argument is the one the student-registration line above
    # makes rather than the one the line it sits under makes.
    #
    # That capability's own docstring says what it covers: "An Event Host
    # filing a Speaker Request, and a Speaker Connector reading the queue of
    # them." An organization is the "on behalf of" half of exactly that
    # filing, and a deployment with intake off has no page these routes could
    # be opened from -- the host portal is the request form and the record of
    # what was requested. A separate flag would make "hosts may file requests
    # but may not say who they are" a supported configuration, which is a
    # degraded state rather than a smaller product.
    #
    # Not `SPEAKER_CONTACT_MANAGEMENT`: that is the Connector's roster of
    # *professionals* they might send to. This is the other side of the table
    # entirely -- who is asking, not who might answer -- and no route here
    # reads or writes a contact_channel, an address, or a consent.
    (host_organizations.router, Capability.SPEAKER_REQUEST_INTAKE),
    # The other side of the same match: a Speaker Connector's roster of
    # professional contacts (customer §13, and §§7-8 for the correction). Its
    # own capability rather than a share of the line above it, because the two
    # are opposite ends of one arrow and a product could offer either alone —
    # requests with no roster is a Connector answering from outside the system,
    # and a roster with no requests is a directory. The authorization rows
    # already say they are two decisions: §12 admits the Event Host to filing a
    # request, §13 admits only the Connector to the roster.
    #
    # Not `CONSENTED_OUTREACH`, and the distinction is the one this card turns
    # on: a contact *record* is not a contact *channel*. These routes write no
    # `contact_channel` row, create no consent, and make nobody writable-to —
    # an address typed on the create form is discarded and reported as withheld
    # (OQ-CBA-011). A deployment could enable this with outreach off and the
    # roster would work exactly as well.
    #
    # Not `EXTERNAL_SPEAKER_ACQUISITION` either: every record is typed by a
    # person about somebody the institution already knows, which is the manual,
    # inside-the-system growth customer §20 permits. No network call, no scrape,
    # no external lookup.
    (cba_contacts.router, Capability.SPEAKER_CONTACT_MANAGEMENT),
    # A roster contact's stated availability (B26 T3): read and corrected by the
    # Connector from the same roster, so the same flag. Roster data that sends
    # nothing, so not `CONSENTED_OUTREACH` -- the argument
    # `student_speaker_feedback.connector_router` makes below.
    (speaker_availability.router, Capability.SPEAKER_CONTACT_MANAGEMENT),
    (match_runs.router, Capability.MATCH_RUNS),
    # The weights a match run is scored under (customer §5, §13's "manage
    # matching weights"). `MATCH_RUNS` rather than a capability of its own, and
    # that is the whole argument: configuring the weighting of a matching engine
    # a deployment does not offer is not a smaller product, it is a settings
    # screen for nothing. The two are enabled together or neither is.
    #
    # Not `OPERATOR_RECORD_IMPORT` and not an admin capability: this is a
    # Connector adjusting how their own unit's shortlist is composed, scoped to
    # that unit, and it authorizes exactly as the match-run routes do.
    (matching_weights.router, Capability.MATCH_RUNS),
    (rewards.router, Capability.REWARDS_LEDGER),
    # The S12 funnel's coordinator-driven write path. Classified with `metrics`,
    # which reads the same table: `routers/pipeline.py` is what makes the last
    # three funnel metrics reachable at all, and a reader wondering where a
    # non-zero `pipeline_confirmed` could come from should find the two next to
    # each other.
    (pipeline.router, Capability.DISCOVERY_METRICS),
    # The attendance writer, classified with the funnel it unblocks. Until
    # OQ-102 was closed on 7 September 2026 nothing under `/v1` wrote an
    # `attendance_record`, so the funnel's Attended stage — which *cites* one
    # and never creates it — was unreachable through the API in both the S12
    # and the CBA walks. That is the argument for putting it here rather than
    # under `EVENT_READS` (student feedback eligibility reads the same row) or
    # `REWARDS_LEDGER` (points derive from it): both of those consume the
    # evidence, and this is the capability that could not complete without it.
    # One capability, not three, and `routers/attendance.py` says which.
    (attendance.router, Capability.DISCOVERY_METRICS),
    (auth.router, Capability.AUTHENTICATED_LOGIN),
    (portals.router, Capability.AUTHENTICATED_LOGIN),
    # Two routers from one module: the unit-scoped operations, and the one
    # unauthenticated operation. See `routers/outreach.py` — "this route takes
    # no principal" is worth being visible in a declaration rather than
    # discoverable by reading a handler.
    #
    # Both are CONSENTED outreach, which the CBA scope preserves. The gated
    # capability is cold contact of someone who never agreed to be contacted —
    # a different trust model that shares only a word, and that these routes do
    # not implement.
    (outreach.router, Capability.CONSENTED_OUTREACH),
    (outreach.public_router, Capability.CONSENTED_OUTREACH),
    # The contact-channel surface lives in its own module but authorizes
    # through `outreach._authorize_outreach` — one question about a unit's
    # outreach with one answer. See `routers/outreach_contacts.py`. It is
    # classified with the two above because it is the same trust model: these
    # routes record and move *consent*, which is exactly what CONSENTED_OUTREACH
    # names. A product without consented outreach has no contact channels to
    # administer.
    (outreach_contacts.router, Capability.CONSENTED_OUTREACH),
    # The §13 roster's channels — the one place a Speaker Connector's contact
    # *record* can acquire a contact *channel*. `CONSENTED_OUTREACH` rather than
    # `SPEAKER_CONTACT_MANAGEMENT`, and the split is the same one the
    # `cba_contacts` note above draws, applied honestly in the other direction:
    # a deployment that offers the roster with outreach switched off should get
    # the roster and no way to make anybody writable-to, which is precisely what
    # gating these three here produces. Classifying them with the roster would
    # have handed a consent surface to every deployment that wanted a directory.
    #
    # They still authorize through `cba_contacts._authorize_speaker_contacts`,
    # so the capability flag and the role gate answer two different questions:
    # whether this product includes consent management at all, and whether this
    # caller may exercise it on this unit.
    (cba_contact_channels.router, Capability.CONSENTED_OUTREACH),
    # Speaker invitations (customer §6 steps 7-8, §13, §14). `CONSENTED_OUTREACH`
    # and not `SPEAKER_CONTACT_MANAGEMENT`, for the reason the note directly
    # above gives and more plainly still: these routes put messages in inboxes.
    # Every one of them is composed from the closed template registry, addressed
    # to an `active_candidate` channel, and delivered by the one `outreach.send`
    # handler — so a deployment with consented outreach switched off must not
    # have them, and a deployment that has them has already accepted the
    # capability that governs sending.
    #
    # Both routers ride the same flag, and the second is the unauthenticated one
    # — the Speaker's own accept/decline. It is listed here rather than mounted
    # unconditionally because an invitation nobody can be sent has nothing to
    # answer: gating the answer with the send is what keeps the pair coherent.
    (cba_invitations.router, Capability.CONSENTED_OUTREACH),
    (cba_invitations.public_router, Capability.CONSENTED_OUTREACH),
    # The speaker handoff (customer §6 step 8, §23). Rides `CONSENTED_OUTREACH`
    # rather than `DISCOVERY_METRICS` even though it writes funnel stages,
    # because the fact it writes them *from* is an invitation's stored answer: a
    # deployment without consented outreach has no `cba_invitation` rows, so
    # this surface would have nothing to reconcile and would only be able to
    # report 404. Gating the handoff with the invitation is what keeps the pair
    # coherent, the same argument the Speaker's own accept/decline route above
    # is mounted on.
    (cba_handoff.router, Capability.CONSENTED_OUTREACH),
    # Student speaker feedback (customer §§15-16, OQ-CBA-003 decided 6 September
    # 2026). The card's two halves ride two different flags on purpose.
    #
    # The student's own routes are `EVENT_READS`, the flag `student_events.router`
    # already carries: this surface is reached from an event the student attended,
    # it is scoped to one event throughout, and a deployment with the student
    # event journey switched off has no page these routes could be opened from.
    # It is not `REWARDS_LEDGER` or anything else student-shaped -- nothing here
    # touches points, and ADR-0013 keeps attendance the only input to those.
    (student_speaker_feedback.router, Capability.EVENT_READS),
    # The Connector's aggregate is `SPEAKER_CONTACT_MANAGEMENT` instead. It is a
    # fact about a §13 roster contact, reached from that contact, and it answers
    # `404` for an id the roster does not hold -- so a deployment that has turned
    # the roster off must not be answering questions about who is on it. Putting
    # both halves on one flag would make one of those two statements false, and
    # the half it would falsify is the privacy-bearing one.
    #
    # Deliberately not `CONSENTED_OUTREACH`: this route puts nothing in an inbox
    # and sends nobody anything. It reads numbers students volunteered.
    (student_speaker_feedback.connector_router, Capability.SPEAKER_CONTACT_MANAGEMENT),
    # The internal CBA meeting record (migration 0034). One flag, and the
    # router's own docstring carries the argument for this one rather than the
    # two it was weighed against.
    #
    # `SPEAKER_CONTACT_MANAGEMENT` because this is the same persona doing the
    # same kind of by-hand record-keeping the roster routes above are: a
    # Connector maintaining their unit's own records, with no network call and
    # nothing sent. A deployment with that surface off has no page these routes
    # could be opened from.
    #
    # Deliberately not `CONSENTED_OUTREACH`: that flag gates putting something in
    # somebody's inbox, and these routes send nothing and read no address --
    # mounting them there would make an outreach switch govern a table that
    # cannot reach anybody. Deliberately not `EVENT_READS` either: a meeting is
    # not an `event` row, is in no catalog, no match run and no student agenda,
    # and attaching it to that flag would place it inside a funnel it stands
    # outside of.
    (meetings.router, Capability.SPEAKER_CONTACT_MANAGEMENT),
    # Manually filed events (migration 0035) and their per-event feedback QR.
    # Classified with `events`/`calendar` above: a manual event is a row in
    # the same `event` table those routes read, gated behind the same flag
    # a deployment already uses to decide whether it shows events at all.
    (manual_events.router, Capability.EVENT_READS),
    (manual_events.public_router, Capability.EVENT_READS),
    # The class exercise (ADR-0025 D1). Listed here, beside
    # `outreach.public_router` and `cba_invitations.public_router`, because it is
    # the same kind of declaration those two are: a router that takes no
    # principal, said out loud in the table rather than discovered by reading a
    # handler.
    #
    # It differs from them in one way that matters, and the difference is the
    # ADR's whole point. Those two are unauthenticated routes inside a product
    # that has a login; this one belongs to a product that has none. Under
    # `CLASS_EXERCISE` the capability table turns every other row here off and
    # `routers_for` drops the principal-bearing infrastructure with them, so
    # `get_current_principal` is not reachable in that process at all — which is
    # what D9 rejected the per-route bypass in favour of. Under `cba` and
    # `ia_west_legacy` this row is off, so the CBA contract is unchanged and the
    # exercise route answers 404 there.
    #
    # The matching, results, and ingest routers join this row the same way,
    # each with the migration that gives them something to answer from.
    (exercise_public.router, Capability.CLASS_EXERCISE),
    # CE-WORKSPACE: the team workspaces design spec §15 and the requirements'
    # "Getting in" row describe. Same capability, same no-principal declaration,
    # and the first exercise router that reads and writes a table — through
    # `exercise_dependencies`, which is the one sanctioned door (ADR-0025 D2).
    #
    # Its `POST` routes are cookie-authenticated with no login behind them, so
    # they carry a CSRF requirement the CBA bearer routes do not need; that is
    # stated on `exercise_dependencies.EXERCISE_REQUEST_HEADER` rather than
    # here, because it is a property of the dependency both routes take.
    (exercise_workspace.router, Capability.CLASS_EXERCISE),
    # CE-INSTRUCTOR: the instructor page design spec §14 and §1 name. Two
    # routers from two modules, and the split is the security property rather
    # than a layout choice.
    #
    # `exercise_instructor_session.router` carries the two routes that must
    # answer *before* there is a session — present the passcode, clear the
    # cookie — and is therefore the one instructor router with no session
    # dependency on it. `exercise_instructor.router` carries every other
    # instructor route and takes `require_instructor_session` as a
    # **router-level** dependency, so a route added to it is gated by existing
    # rather than by somebody remembering to gate it. A gate written as a
    # handler parameter comes off when a signature is edited, and an open
    # instructor route looks exactly like a working one. They were one module
    # until SPLIT-INSTRUCTOR-SESSION; each file's docstring says why.
    #
    # Same capability and the same no-principal declaration as the two rows
    # above: the passcode is a door, not an identity. It resolves no
    # `user_account`, mints no principal, and reaches no CBA table (ADR-0025
    # D1/D2) — `routers/auth.py` is not imported and is not mounted in this
    # scope at all.
    (exercise_instructor_session.router, Capability.CLASS_EXERCISE),
    (exercise_instructor.router, Capability.CLASS_EXERCISE),
    # CE-MATCHING-API: the matching screen design spec §4-§8 describes — the
    # event picker, the ranked list with its "who is on the list" table, the
    # saved settings, the side-by-side compare and the CSV download.
    #
    # Same capability and the same no-principal declaration as the rows above.
    # Its prefix is `/v1/exercise/workspaces/current`, which is the deviation
    # from design spec §6's `/v1/exercise/workspaces/{token}/...` worth seeing
    # here rather than only in the module: every route is addressed by the
    # workspace cookie, so no team number, dataset id or workspace id is
    # accepted from a client on any of them, and a team can only ever act on
    # its own rows.
    (exercise_matching.router, Capability.CLASS_EXERCISE),
    # CE-RESULTS-API: design spec §9-§13 — the results lock and the one-run
    # rule, the three comparison panels, the asking choice and the one refresh.
    #
    # Same capability and the same no-principal declaration as the rows above,
    # and the same addressing as `exercise_matching.router`: the prefix is
    # `/v1/exercise/workspaces/current`, so no team number, dataset id or
    # workspace id is accepted from a client on any of its routes.
    #
    # It is the first router that composes design spec §11's simulated-results
    # rule, which is the one reader of the withheld column (ADR-0025 D6). What
    # the rule returns is profile numbers; nothing it reads reaches a response.
    (exercise_results.router, Capability.CLASS_EXERCISE),
    # CE-RESULTS-API, instructor half: `POST /v1/exercise/instructor/refresh-all`
    # replaces the refusing stub PR #184 shipped at that path. A third exercise
    # router rather than a ninth section of `exercise_instructor.py`, which is
    # already past the repository's 800-line ceiling — and it takes the same
    # router-level `require_instructor_session` dependency, so the gate is
    # structural here exactly as it is there.
    (exercise_instructor_refresh.router, Capability.CLASS_EXERCISE),
    # B26 T6b-1: Speaker accounts. `SPEAKER_PORTAL` is off in every scope until
    # its turn-on rule clears, so none of these three mounts today. `router` is
    # the Connector's invite/revoke/access ({admin, coordinator}); the other two
    # take no principal — the activation token is their whole authorization,
    # and each is declared in `UNAUTHENTICATED_ROUTES`.
    (speaker_portal.router, Capability.SPEAKER_PORTAL),
    (speaker_portal.public_router, Capability.SPEAKER_PORTAL),
    (speaker_portal.pages_router, Capability.SPEAKER_PORTAL),
    # B26 T6b-2: the Speaker's own reads and writes under `/v1/me`
    # ({speaker}), off with the rest of the portal.
    (speaker_self.router, Capability.SPEAKER_PORTAL),
    # B26 T6b-3: the Speaker's own channel opt-in / opt-out ({speaker}).
    (me_contact_channels.router, Capability.SPEAKER_PORTAL),
)


def routers_for(settings: Settings) -> tuple[APIRouter, ...]:
    """Every router a process configured by ``settings`` mounts, in mount order.

    The composition rule as a function, so "which routes does this product
    serve" can be answered — by a test, or by a reader — without booting a
    second interpreter to observe the answer. The application below is built
    from it, so there is one rule rather than a rule and a description of it.

    Mounting is decided once, at import, from the settings the process booted
    with. This function is pure and takes its settings as an argument; it is
    *not* a per-request hook, and calling it with other settings does not change
    the running application.
    """
    infrastructure = (
        PRINCIPAL_BEARING_INFRASTRUCTURE_ROUTERS
        if settings.capability_enabled(Capability.AUTHENTICATED_LOGIN)
        else ()
    )
    return infrastructure + tuple(
        router
        for router, capability in CAPABILITY_SCOPED_ROUTERS
        if settings.capability_enabled(capability)
    )


# The class exercise's workspace cookie is derived from a deployment secret
# (design spec §15; OQ-CE-08, closed 2026-09-25). A process that serves the exercise
# without one would either derive every token from an empty key — making a
# workspace id a workspace token — or fall back to per-entry random tokens,
# which silently logs a team's first laptop out when its second one enters the
# same number. Neither is a thing to discover in a classroom, so the process
# refuses to start instead.
#
# Checked here, at import, rather than in `Settings`: several tests construct
# `Settings(product_scope=class_exercise)` to ask which routes that scope
# mounts, and a construction-time raise would make that question unanswerable
# without a secret in the environment. This is the boundary where the answer
# actually matters — the application either exists or it does not.
if get_settings().capability_enabled(Capability.CLASS_EXERCISE):
    require_exercise_workspace_secret(get_settings())

# B26 T6b-1 (§4.2, R10): refuse to boot with the capability on and no usable
# token secret; with it off the secret is never read and this is `None`.
app.state.speaker_portal_token_secret = check_speaker_portal_startup(get_settings())

# B26 T6b-1 (R4): token-bearing paths (`/s`, `/i`, `/u`, `/q`) are redacted in
# uvicorn's access log rather than the log being disabled. Idempotent.
install_access_log_redaction()


for _mounted_router in routers_for(get_settings()):
    app.include_router(_mounted_router)


@app.get("/api/health", tags=["operations"], summary="Liveness probe")
def health() -> dict[str, Any]:
    """Report that the process is serving requests.

    Exposes no dependency or topology detail — not the database host, not the
    queue, not which providers are configured (v1.1 §1.11). Readiness, which
    does check dependencies, is a separate private endpoint and is deliberately
    not part of the public surface.
    """
    settings = get_settings()
    return {"status": "ok", "release": settings.release}


#: The two token-addressed HTML pages a CBA email links to, as a router rather
#: than two bare ``@app.get`` declarations, so that the capability that owns
#: them can decide whether they are mounted at all.
#:
#: They are outreach pages: ``/u/{token}`` is the read half of the unsubscribe
#: pair whose write half is ``POST /v1/unsubscribe``, and ``/i/{token}`` is the
#: page the link in a speaker invitation actually carries. Both are addressed by
#: a token minted by the CBA outreach and invitation machinery, and neither can
#: be reached by anyone who was not sent one. Declared on the application rather
#: than inside ``routers/outreach.py`` and ``routers/cba_invitations.py`` only
#: because they sit at the root of the path space, which is a URL fact, not a
#: product one.
#:
#: Left on the application unconditionally they were served in *every* scope,
#: including ``CLASS_EXERCISE`` — a no-login product over made-up rows, which has
#: no unsubscribe list and sends no invitation. Two CBA outreach pages answering
#: 200 in that process is exactly the surface ADR-0025 D1 keeps out of it. The
#: gate is :attr:`Capability.CONSENTED_OUTREACH`, which is the same capability
#: ``outreach.public_router`` and ``cba_invitations.public_router`` are declared
#: under above — the capability that owns the machinery that mints these tokens —
#: rather than a comparison against ``ProductScope.CLASS_EXERCISE``. A later
#: scope that has outreach gets these pages without editing this line, and a
#: later scope that does not, does not.
#:
#: Under ``cba`` and ``ia_west_legacy`` ``CONSENTED_OUTREACH`` is on, so the
#: served contract is unchanged: same paths, same handlers, same documented
#: responses, and the same place in the OpenAPI document — which is why the
#: router is included *below* ``/api/health`` rather than joining
#: ``CAPABILITY_SCOPED_ROUTERS``, where it would have moved ahead of it.
#:
#: A bare assignment, not an annotated one, for ``exercise_public.router``'s
#: reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads
#: router prefixes out of the AST and matches ``name = APIRouter(...)``.
token_pages_router = APIRouter()


@token_pages_router.get(
    "/u/{token}",
    tags=["outreach"],
    summary="Unsubscribe confirmation page",
    # Media types are declared per response rather than through
    # ``response_class=HTMLResponse``. A route-wide response class sets the
    # media type for *every* response the route publishes, including the error
    # responses inherited from the application-level ``responses`` above — so
    # this route, and only this route, documented its 4xx bodies as
    # ``text/html`` while the exception handlers return ``application/json``.
    # A generated client would take the contract at its word and try to parse
    # an error envelope as HTML.
    #
    # The handler still returns an ``HTMLResponse``; only the documented
    # contract changes. Declaring 200 as HTML here keeps that accurate.
    responses={
        200: {"content": {"text/html": {}}, "description": "Confirmation page"},
        **{
            code: {"model": ErrorEnvelope, "content": {"application/json": {}}}
            for code in (400, 401, 403, 404, 409, 422, 429)
        },
    },
)
def unsubscribe_page(token: str) -> HTMLResponse:
    """Render the unsubscribe confirmation page. **Never changes state.**

    Fixes the v1.0 mutating-GET unsubscribe (v1.1 §1.10). A GET here is reached
    by link scanners, mail-client prefetchers, and security proxies; if it
    mutated, those would silently unsubscribe recipients who never clicked.

    The actual unsubscribe is the signed POST, or the RFC 8058 one-click POST
    that mail providers issue directly. Both arrive with R4.
    """
    # Rendered from a template in R4. The token is deliberately not echoed into
    # the HTML — reflecting it invites both leakage and injection.
    return HTMLResponse(
        "<!doctype html><title>Unsubscribe</title>"
        "<h1>Confirm unsubscribe</h1>"
        "<p>Confirm below to stop receiving these messages.</p>",
        status_code=status.HTTP_200_OK,
    )


#: Headers every ``/i/{token}`` response carries, on both methods (B26 T6a).
#:
#: ``no-store`` keeps a page reached through a secret link out of shared and
#: browser caches; ``no-referrer`` keeps the token-bearing URL out of the
#: ``Referer`` of anything the page leads to; ``noindex`` keeps a crawler that
#: somehow holds the link from indexing it. The CSP allows nothing to load and
#: the form to post only back to this origin, and forbids framing.
_TOKEN_PAGE_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Robots-Tag", "noindex"),
    ("X-Content-Type-Options", "nosniff"),
    (
        "Content-Security-Policy",
        "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    ),
)

#: The largest ``POST /i/{token}`` body read. The form sends one short field,
#: ``response=decline`` at most; 1 KiB is ample and bounds the parse.
_TOKEN_FORM_MAX_BYTES: Final[int] = 1024

#: The only body media type the form route accepts — what a browser sends for a
#: ``<form method="post">`` with no ``enctype``.
_FORM_MEDIA_TYPE: Final[str] = "application/x-www-form-urlencoded"

#: ``parse_qs`` raises past this many fields. One is expected; the slack covers
#: a browser or extension adding a stray field without letting a body of
#: hundreds of ``&``-separated pairs be expanded.
_TOKEN_FORM_MAX_FIELDS: Final[int] = 4


def _token_page(title: str, heading: str, body_html: str, *, status_code: int) -> HTMLResponse:
    """A complete, self-contained token page. Nothing in it depends on the token."""
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title></head><body><main>"
        f"<h1>{heading}</h1>{body_html}</main></body></html>",
        status_code=status_code,
        headers=dict(_TOKEN_PAGE_HEADERS),
    )


@token_pages_router.get(
    "/i/{token}",
    tags=["speaker-invitations"],
    summary="Speaker invitation response page",
    # Declared per response for `unsubscribe_page`'s reason: a route-wide
    # response class would document this route's inherited 4xx bodies as HTML
    # while the exception handlers return JSON.
    responses={
        200: {"content": {"text/html": {}}, "description": "Response page"},
        **{
            code: {"model": ErrorEnvelope, "content": {"application/json": {}}}
            for code in (400, 401, 403, 404, 409, 422, 429)
        },
    },
)
def invitation_response_page(token: str) -> HTMLResponse:
    """Render the accept-or-decline page. **Never changes state.**

    The link an invitation actually carries, and a GET for the reason
    :func:`unsubscribe_page` is one: a link in an email is fetched by scanners,
    prefetchers and security proxies, so a GET that recorded an answer would
    have Speakers accepting engagements they never read about. The answer is
    ``POST /i/{token}`` (:func:`answer_invitation_by_form`): the page's own form,
    posted back to this same URL. It cannot be ``POST
    /v1/speaker-invitations/respond``, which takes JSON a no-JS form cannot send
    and would need the token written into the page.

    The token is deliberately not echoed into the HTML — reflecting it invites
    both leakage and injection — and the page says nothing about whether the
    token is real, for the same anti-oracle reason the POST answers identically
    to every token. The bytes are the same for every token, and nothing here
    reads the database.
    """
    return _token_page(
        "Speaker invitation",
        "Respond to this invitation",
        '<p id="i-help">Choose Accept or Decline. Neither choice changes whether '
        "you receive other messages. Your first answer is final. To change it, "
        "contact the person who invited you.</p>"
        # No `action`: the browser posts to the document's own URL, so the token
        # travels in the path the Speaker already holds and is never written
        # into the HTML. (An empty `action=""` is invalid HTML.)
        '<form method="post" aria-describedby="i-help">'
        '<button type="submit" name="response" value="accept">Accept invitation</button> '
        '<button type="submit" name="response" value="decline">Decline invitation</button>'
        "</form>",
        status_code=status.HTTP_200_OK,
    )


class FormOutcome(enum.Enum):
    """What the ``POST /i/{token}`` body says, decided from the body alone."""

    TOO_LARGE = "too_large"
    INVALID = "invalid"
    ACCEPT = "accept"
    DECLINE = "decline"


async def _read_answer_form(request: Request) -> FormOutcome:
    """Read and classify the form body. **Never raises.**

    Async because reading a body is; everything that touches the database stays
    in the sync route, which FastAPI runs in its threadpool. Hand-parsed with
    :func:`urllib.parse.parse_qs` because ``python-multipart`` is not a runtime
    dependency and FastAPI's ``Form()`` needs it (T6a plan §6 C2).

    Every decision here depends on the request body and headers only, never on
    the token, so none of them can say whether a token is real.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _TOKEN_FORM_MAX_BYTES:
        return FormOutcome.TOO_LARGE
    try:
        # Already buffered by MaxBodySizeMiddleware, so a chunked body with no
        # Content-Length is bounded by the global cap before it gets here.
        body = await request.body()
    except ClientDisconnect:
        return FormOutcome.INVALID
    if len(body) > _TOKEN_FORM_MAX_BYTES:
        return FormOutcome.TOO_LARGE

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != _FORM_MEDIA_TYPE:
        return FormOutcome.INVALID
    try:
        fields = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=_TOKEN_FORM_MAX_FIELDS,
        )
    except (UnicodeDecodeError, ValueError):
        return FormOutcome.INVALID

    answers = fields.get("response", [])
    if len(answers) != 1:
        return FormOutcome.INVALID
    return {"accept": FormOutcome.ACCEPT, "decline": FormOutcome.DECLINE}.get(
        answers[0], FormOutcome.INVALID
    )


_FORM_RESPONSE_BODY_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "required": ["response"],
    "properties": {"response": {"type": "string", "enum": ["accept", "decline"]}},
}


@token_pages_router.post(
    "/i/{token}",
    tags=["speaker-invitations"],
    summary="Accept or decline an invitation from its page's form",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {_FORM_MEDIA_TYPE: {"schema": _FORM_RESPONSE_BODY_SCHEMA}},
        }
    },
    # Per response, for `unsubscribe_page`'s reason. The three codes this
    # handler renders itself are HTML; the inherited ones stay the JSON envelope.
    responses={
        200: {
            "content": {"text/html": {}},
            "description": "Answer received. Identical for every token and every outcome.",
        },
        400: {"content": {"text/html": {}}, "description": "No valid accept or decline"},
        413: {"content": {"text/html": {}}, "description": "Body over 1 KiB"},
        **{
            code: {"model": ErrorEnvelope, "content": {"application/json": {}}}
            for code in (401, 403, 404, 409, 422, 429)
        },
    },
)
def answer_invitation_by_form(
    token: str,
    session: DbSession,
    outcome: Annotated[FormOutcome, Depends(_read_answer_form)],
) -> HTMLResponse:
    """Record the Speaker's answer from the ``GET /i/{token}`` page's form.

    **Unauthenticated by design**, for ``speaker_respond``'s reason, and it runs
    the same code (``cba_invitations.answer_by_token``): the first answer
    stands, a different second answer writes nothing, and an undispatched
    invitation cannot be answered.

    The 200 page is byte-identical for every token and every outcome — recorded,
    repeated, refused, invented, undispatched, too short or too long — so the
    route is not an oracle for whether somebody was invited. There is no
    redirect: a redirect target would need the token or a second page, and a
    refresh that re-POSTs is a no-op. A 400 or 413 is decided from the body
    alone, before the token is looked at.

    Two residuals are documented rather than fixed (T6a plan §5):

    * **Timing.** A token of plausible length costs a database lookup and, for a
      real one, a write; a too-short or too-long one skips both. The bytes are
      identical; the latency is not — the same exposure as the JSON route.
    * **Write failure.** A database error on a real token propagates to the
      application's exception handler as a 500 envelope, which an invented token
      cannot provoke. Errors are not swallowed to hide that.

    No rate limit, for the reason given above ``speaker_respond``:
    ``charge_quota`` keys by tenant and user, and this route has no principal.
    The edge rate limit is an ops follow-up.
    """
    if outcome is FormOutcome.TOO_LARGE:
        return _token_page(
            "Speaker invitation",
            "Request too large",
            "<p>That request was too large. Go back and choose Accept or Decline.</p>",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if outcome is FormOutcome.INVALID:
        return _token_page(
            "Speaker invitation",
            "Respond to this invitation",
            "<p>Choose Accept or Decline. Go back and use one of the two buttons.</p>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if (
        cba_invitations.RESPONSE_TOKEN_MIN_LENGTH
        <= len(token)
        <= cba_invitations.RESPONSE_TOKEN_MAX_LENGTH
    ):
        verb: Literal["accept", "decline"] = (
            "accept" if outcome is FormOutcome.ACCEPT else "decline"
        )
        cba_invitations.answer_by_token(session, token, verb)

    return _token_page(
        "Speaker invitation",
        "Thank you",
        "<p>Thank you. We have your answer.</p>",
        status_code=status.HTTP_200_OK,
    )


#: The routers declared on the application module itself rather than in
#: ``routers/``, each with the capability that decides whether it is mounted.
#: One entry today; a second would be listed here rather than gated inline, for
#: the reason ``CAPABILITY_SCOPED_ROUTERS`` is a table.
APP_LEVEL_ROUTERS: Final[tuple[tuple[APIRouter, Capability], ...]] = (
    (token_pages_router, Capability.CONSENTED_OUTREACH),
)


def app_level_routers_for(settings: Settings) -> tuple[APIRouter, ...]:
    """The application-module routers a process configured by ``settings`` mounts.

    The companion to :func:`routers_for`, and separate from it because the two
    are included at different points in the application's route order and that
    order is the order of the exported OpenAPI document.

    ``GET /api/health`` is deliberately not here. It is declared with
    ``@app.get`` and is ungated in every scope — a liveness probe that a product
    decision could remove is a liveness probe a monitor cannot rely on — so it,
    and only it, is the route no composition rule accounts for.
    """
    return tuple(
        router
        for router, capability in APP_LEVEL_ROUTERS
        if settings.capability_enabled(capability)
    )


for _app_level_router in app_level_routers_for(get_settings()):
    app.include_router(_app_level_router)
