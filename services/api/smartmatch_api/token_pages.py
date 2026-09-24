"""Shared, token-free helpers for the no-JS token pages (``/s/{token}``, ``/i/{token}``).

B26 T6b-1 plan §3.5 (R9) and §4.5 (R4). No ``APIRouter`` lives here: the routes
stay in their routers, and this module holds only what two of them would
otherwise copy.

* :data:`TOKEN_PAGE_HEADERS` and :func:`token_page` — T6a's token-page headers
  and markup, byte-identical to its ``_token_page``.
* :func:`read_urlencoded_form` — reads a small ``<form method="post">`` body
  with the standard library (``python-multipart`` is not a runtime
  dependency). It **never raises**: every outcome is a :class:`FormRead`.
* :class:`TokenPathRedactingFilter` and :func:`install_access_log_redaction` —
  rewrite ``/s/``, ``/i/``, ``/u/`` and ``/q/`` path tokens in uvicorn's access
  log to ``<redacted>`` and keep the line.

Composition with T6a (#213): while #213 is unmerged, ``main.py``'s ``/i/`` code
keeps its private copies; T6a's rebase deletes them and imports from here.
"""

from __future__ import annotations

import enum
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import parse_qs

from fastapi.responses import HTMLResponse
from starlette.requests import ClientDisconnect, Request

__all__ = [
    "FORM_MEDIA_TYPE",
    "TOKEN_PAGE_HEADERS",
    "FormRead",
    "FormReadOutcome",
    "TokenPathRedactingFilter",
    "install_access_log_redaction",
    "read_urlencoded_form",
    "token_page",
]

#: Headers every token page carries, on both methods. ``no-store`` keeps a page
#: reached through a secret link out of caches; ``no-referrer`` keeps the
#: token-bearing URL out of any ``Referer``; ``noindex`` keeps crawlers away.
#: The CSP loads nothing, posts only back to this origin, and forbids framing.
TOKEN_PAGE_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Robots-Tag", "noindex"),
    ("X-Content-Type-Options", "nosniff"),
    (
        "Content-Security-Policy",
        "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    ),
)

#: What a browser sends for a ``<form method="post">`` with no ``enctype``.
FORM_MEDIA_TYPE: Final[str] = "application/x-www-form-urlencoded"


def token_page(title: str, heading: str, body_html: str, *, status_code: int) -> HTMLResponse:
    """A complete, self-contained token page. Nothing in it depends on the token."""
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title></head><body><main>"
        f"<h1>{heading}</h1>{body_html}</main></body></html>",
        status_code=status_code,
        headers=dict(TOKEN_PAGE_HEADERS),
    )


class FormReadOutcome(enum.Enum):
    """How reading a form body went, decided from the body and headers alone."""

    OK = "ok"
    TOO_LARGE = "too_large"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class FormRead:
    """The result of :func:`read_urlencoded_form`. ``fields`` is empty unless ``OK``."""

    outcome: FormReadOutcome
    fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


async def read_urlencoded_form(request: Request, *, max_bytes: int, max_fields: int) -> FormRead:
    """Read a small urlencoded form body. **Never raises.**

    Covers: a declared ``Content-Length`` over the cap, a buffered body over
    the cap, a client disconnect, a wrong media type, bad UTF-8, and more than
    ``max_fields`` fields. None of these depends on the path token, so none can
    say whether a token is real.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        return FormRead(FormReadOutcome.TOO_LARGE)
    try:
        body = await request.body()
    except ClientDisconnect:
        return FormRead(FormReadOutcome.INVALID)
    if len(body) > max_bytes:
        return FormRead(FormReadOutcome.TOO_LARGE)

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != FORM_MEDIA_TYPE:
        return FormRead(FormReadOutcome.INVALID)
    try:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=max_fields)
    except (UnicodeDecodeError, ValueError):
        return FormRead(FormReadOutcome.INVALID)
    return FormRead(FormReadOutcome.OK, {name: tuple(values) for name, values in parsed.items()})


#: The token-bearing path prefixes: ``/s`` (Speaker activation), ``/i``
#: (invitation answer), ``/u`` (unsubscribe), ``/q`` (feedback QR).
_TOKEN_PATH: Final[re.Pattern[str]] = re.compile(r"^/(s|i|u|q)/[^/?#]+")


class TokenPathRedactingFilter(logging.Filter):
    """Rewrite a token path in a uvicorn access-log record; always keep the line.

    uvicorn logs ``'%s - "%s %s HTTP/%s" %d'`` with the path at ``args[2]``.
    A record of any other shape passes through untouched.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            redacted = _TOKEN_PATH.sub(r"/\1/<redacted>", args[2])
            if redacted != args[2]:
                record.args = (*args[:2], redacted, *args[3:])
        return True


def install_access_log_redaction() -> None:
    """Attach one :class:`TokenPathRedactingFilter` to ``uvicorn.access``. Idempotent.

    uvicorn configures logging before it imports the app, so a filter added at
    app import survives, including under ``--reload``.
    """
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, TokenPathRedactingFilter) for existing in logger.filters):
        logger.addFilter(TokenPathRedactingFilter())
