"""SmartMatch API application.

The routes here are those whose contracts and gates are settled. Feature routes
arrive with their release, behind their gates — a route that exists before its
gate closes is a route someone will call.

What is **not** present, and why:

* ``POST /auth/mock-login`` — archived (MM-A01). Caller-selected identity was the
  single most dangerous pattern in the legacy baseline
  (``bdce024:src/api/routers/portals.py:435``). Identity now comes from a
  verified token, and the local account, tenant, and roles are read server-side.
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

from fastapi import FastAPI, status
from fastapi.responses import HTMLResponse
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import build_token_verifier
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smartmatch_api.config import get_settings
from smartmatch_api.errors import EXCEPTION_HANDLERS, ErrorEnvelope, error_response
from smartmatch_api.routers import engagement, events, imports, jobs, me, metrics, redrive, review

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

app.include_router(jobs.router)
app.include_router(imports.router)
app.include_router(redrive.router)
app.include_router(me.router)
app.include_router(metrics.router)
app.include_router(events.router)
app.include_router(engagement.router)
app.include_router(review.router)


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
