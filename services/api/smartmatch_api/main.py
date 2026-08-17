"""SmartMatch API application.

Foundation scaffold. The routes here are deliberately minimal: health, and the
unsubscribe pair that demonstrates the corrected GET/POST semantics. Feature
routes arrive with their release, behind their gates.

What is **not** present, and why:

* ``POST /auth/mock-login`` — archived. Caller-selected identity is the single
  most dangerous pattern in the legacy baseline
  (``bdce024:src/api/routers/portals.py:435``).
* Match-run, discovery, import, and send commands — these are R1–R4 and require
  the outbox, dispatcher, and their release gates.
* Any handler that calls a provider inline — prohibited by v1.1 §1.6.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, status
from fastapi.responses import HTMLResponse

from smartmatch_api.config import get_settings
from smartmatch_api.errors import EXCEPTION_HANDLERS, ErrorEnvelope

app = FastAPI(
    title="SmartMatch API",
    version="0.1.0",
    description=(
        "IA West SmartMatch platform API — Foundation scaffold. "
        "OpenAPI is the source of truth; the TypeScript client is generated from "
        "it and never hand-maintained."
    ),
    responses={
        400: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
    },
)

for exception_type, handler in EXCEPTION_HANDLERS.items():
    app.add_exception_handler(exception_type, handler)


@app.get(
    "/api/health",
    tags=["operations"],
    summary="Liveness probe",
)
def health() -> dict[str, Any]:
    """Report that the process is serving requests.

    Deliberately exposes no dependency or topology detail — not the database
    host, not the queue, not which providers are configured (v1.1 §1.11).
    Readiness, which does check dependencies, is a separate private endpoint and
    is not part of the public surface.
    """
    settings = get_settings()
    return {"status": "ok", "release": settings.release}


@app.get(
    "/u/{token}",
    tags=["outreach"],
    response_class=HTMLResponse,
    summary="Unsubscribe confirmation page",
)
def unsubscribe_page(token: str) -> HTMLResponse:
    """Render the unsubscribe confirmation page. **Never changes state.**

    Fixes the v1.0 mutating-GET unsubscribe (v1.1 §1.10). A GET here is reached
    by link scanners, mail-client prefetchers, and security proxies; if it
    mutated, those would silently unsubscribe recipients who never clicked.

    The actual unsubscribe is the signed POST below, or the RFC 8058 one-click
    POST that mail providers issue directly.
    """
    # Rendered from a template in R4; the scaffold returns the shape only, and
    # deliberately does not echo the token back into the HTML.
    return HTMLResponse(
        "<!doctype html><title>Unsubscribe</title>"
        "<h1>Confirm unsubscribe</h1>"
        "<p>Confirm below to stop receiving these messages.</p>",
        status_code=status.HTTP_200_OK,
    )
