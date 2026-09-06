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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

from fastapi import APIRouter, FastAPI, status
from fastapi.responses import HTMLResponse
from smartmatch_domain.product_scope import Capability
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import build_token_verifier
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smartmatch_api.config import get_settings
from smartmatch_api.errors import EXCEPTION_HANDLERS, ErrorEnvelope, error_response
from smartmatch_api.routers import (
    auth,
    calendar,
    cba_contacts,
    engagement,
    events,
    imports,
    jobs,
    match_runs,
    matching_weights,
    me,
    metrics,
    outreach,
    outreach_contacts,
    pipeline,
    portals,
    redrive,
    review,
    rewards,
    speaker_requests,
    student_events,
)

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
    """
    settings = get_settings()

    app.state.settings = settings
    # The product-scope decisions this process booted with, resolved once so a
    # handler or a diagnostic reads the same answers composition used above
    # rather than re-deriving them from `product_scope` and drifting.
    app.state.product_scope = settings.product_scope
    app.state.enabled_capabilities = settings.enabled_capabilities()
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.token_verifier = build_token_verifier(
        settings.edition,
        use_fixture=settings.use_fixture_providers,
        fixture_principals=settings.dev_principals,
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

# Infrastructure routers: the durable command/job substrate every capability
# rides on, and the operator paths that keep it honest. They are not a product
# capability of their own — there is no version of this product that offers
# match runs but not the job lifecycle that carries them — so they are mounted
# unconditionally rather than classified below.
app.include_router(jobs.router)
app.include_router(redrive.router)
app.include_router(engagement.router)
app.include_router(review.router)

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
)

for _capability_router, _required_capability in CAPABILITY_SCOPED_ROUTERS:
    if get_settings().capability_enabled(_required_capability):
        app.include_router(_capability_router)


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


@app.get(
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
