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
from typing import Any

from fastapi import FastAPI, status
from fastapi.responses import HTMLResponse
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import build_token_verifier

from smartmatch_api.config import get_settings
from smartmatch_api.errors import EXCEPTION_HANDLERS, ErrorEnvelope
from smartmatch_api.routers import imports, jobs


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
        429: {"model": ErrorEnvelope},
    },
)

for exception_type, handler in EXCEPTION_HANDLERS.items():
    app.add_exception_handler(exception_type, handler)

app.include_router(jobs.router)
app.include_router(imports.router)


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
