"""``smartmatch_api.token_pages``: shared, token-free helpers for ``/s``, ``/i`` (B26 T6b-1).

R4 (access-log redaction) and R9 (one form reader, never raises).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

import pytest
from smartmatch_api.token_pages import (
    FORM_MEDIA_TYPE,
    TOKEN_PAGE_HEADERS,
    FormReadOutcome,
    TokenPathRedactingFilter,
    install_access_log_redaction,
    read_urlencoded_form,
    token_page,
)
from starlette.requests import Request


def _request(
    body: bytes,
    *,
    content_type: str | None = FORM_MEDIA_TYPE,
    content_length: str | None = "auto",
    disconnect: bool = False,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    if content_length == "auto":
        headers.append((b"content-length", str(len(body)).encode()))
    elif content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    scope = {"type": "http", "method": "POST", "path": "/s/x", "headers": headers}
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if disconnect:
            return {"type": "http.disconnect"}
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _read(request: Request, *, max_bytes: int = 64, max_fields: int = 4):
    return asyncio.run(read_urlencoded_form(request, max_bytes=max_bytes, max_fields=max_fields))


def test_read_form_reads_fields() -> None:
    read = _read(_request(b"a=1&b=&a=2"))
    assert read.outcome is FormReadOutcome.OK
    assert read.fields == {"a": ("1", "2"), "b": ("",)}


def test_read_form_refuses_declared_and_actual_oversize() -> None:
    assert _read(_request(b"a=1", content_length="999")).outcome is FormReadOutcome.TOO_LARGE
    big = b"a=" + b"x" * 100
    assert _read(_request(big, content_length=None)).outcome is FormReadOutcome.TOO_LARGE
    assert _read(_request(big)).outcome is FormReadOutcome.TOO_LARGE


@pytest.mark.parametrize(
    "request_factory",
    [
        lambda: _request(b"a=1", content_type="application/json"),
        lambda: _request(b"a=1", content_type=None),
        lambda: _request(b"a=\xff\xfe"),
        lambda: _request(b"a=1&b=2&c=3&d=4&e=5"),
    ],
    ids=["json", "no-type", "bad-utf8", "too-many-fields"],
)
def test_read_form_refuses_wrong_media_type_bad_utf8_and_too_many_fields(request_factory) -> None:
    assert _read(request_factory()).outcome is FormReadOutcome.INVALID


@pytest.mark.parametrize("case", ["disconnect"])
def test_read_form_never_raises(case: str) -> None:
    read = _read(_request(b"", disconnect=True))
    assert read.outcome is FormReadOutcome.INVALID
    assert read.fields == {}


def test_token_page_is_byte_stable_and_carries_the_headers() -> None:
    first = token_page("T", "H", "<p>b</p>", status_code=200)
    second = token_page("T", "H", "<p>b</p>", status_code=200)
    assert first.body == second.body
    assert first.status_code == 200
    headers = dict(TOKEN_PAGE_HEADERS)
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Robots-Tag"] == "noindex"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'self'" in headers["Content-Security-Policy"]
    for name, value in TOKEN_PAGE_HEADERS:
        assert first.headers[name] == value
    assert first.body.startswith(b"<!doctype html>")


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", 200),
        None,
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/s/x", "/s/<redacted>"),
        ("/i/x?y", "/i/<redacted>?y"),
        ("/u/x", "/u/<redacted>"),
        ("/q/x", "/q/<redacted>"),
    ],
)
def test_access_log_filter_redacts_s_i_u_q_tokens(path: str, expected: str) -> None:
    record = _access_record(path)
    assert TokenPathRedactingFilter().filter(record) is True
    assert record.args[2] == expected  # type: ignore[index]
    assert "x" not in record.getMessage().split(" ")[3].replace("<redacted>", "")


@pytest.mark.parametrize("path", ["/speaker-portal", "/settings", "/v1/units/abc/metrics", "/s"])
def test_access_log_filter_leaves_other_paths(path: str) -> None:
    record = _access_record(path)
    assert TokenPathRedactingFilter().filter(record) is True
    assert record.args[2] == path  # type: ignore[index]


def _redacting_filters(filters: Iterable[logging.Filter]) -> list[logging.Filter]:
    return [f for f in filters if isinstance(f, TokenPathRedactingFilter)]


def test_install_is_idempotent_and_attached_after_importing_main() -> None:
    import smartmatch_api.main  # noqa: F401

    logger = logging.getLogger("uvicorn.access")
    assert len(_redacting_filters(logger.filters)) == 1
    install_access_log_redaction()
    install_access_log_redaction()
    assert len(_redacting_filters(logger.filters)) == 1
