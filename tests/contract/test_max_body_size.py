"""``MaxBodySizeMiddleware`` (``services/api/smartmatch_api/main.py``) rejects an
oversized body *before parsing*, not after.

Before this middleware existed, the 2 MB bound lived only inside
``routers/imports.py::_validate_inline_rows``, which ran after FastAPI's
dependency resolution had already read the entire request body and built the
``ImportRequest`` pydantic model from it — so the bound protected
``job.payload`` and queued work, not the process of reading and parsing an
oversized request in the first place.

Two kinds of test live here, deliberately:

* Direct calls into ``MaxBodySizeMiddleware`` over its own ASGI interface, with
  a hand-built ``receive``/``send`` pair that records exactly what was called.
  This is the precise proof that the finding is fixed: the wrapped downstream
  application (where FastAPI's routing, dependency resolution, and Pydantic
  parsing all live) is never invoked for an oversized body, and for the
  ``Content-Length`` fast path, ``receive()`` is never even called — nothing is
  read off the wire. No database is touched by any test in this file:
  rejection happens ahead of ``get_session``, so ``app.state.session_factory``
  is never needed.
* One end-to-end test against the real, fully-wired application, posting
  bytes that are not valid JSON at all. If the middleware were not actually
  wired into ``main.app`` — or if rejection happened after parsing instead of
  before — this would come back as a 422 (malformed JSON) rather than the 413
  asserted below.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.testclient import TestClient
from smartmatch_api.main import MAX_REQUEST_BODY_BYTES, MaxBodySizeMiddleware
from smartmatch_api.main import app as real_app

Message = dict[str, Any]

_OVER_CAP = MAX_REQUEST_BODY_BYTES + 1

_BASE_SCOPE: dict[str, Any] = {
    "type": "http",
    "method": "POST",
    "path": "/v1/me",
    "headers": [],
}


def _run(coro: Awaitable[None]) -> None:
    asyncio.run(coro)


def _scope_with_content_length(length: int) -> dict[str, Any]:
    return {**_BASE_SCOPE, "headers": [(b"content-length", str(length).encode())]}


class _RecordingDownstream:
    """A stand-in for the FastAPI application the middleware wraps.

    Recording whether — and with what — it was called is the whole point: an
    oversized request must never reach here, because this is where routing,
    dependency resolution, and Pydantic's own body parsing all live.
    """

    def __init__(self) -> None:
        self.called = False
        self.received_messages: list[Message] = []

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        self.called = True
        while True:
            message = await receive()
            self.received_messages.append(message)
            if not message.get("more_body", False):
                break


class _RecordingSend:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        start = next((m for m in self.messages if m["type"] == "http.response.start"), None)
        return start["status"] if start else None

    @property
    def json_body(self) -> Any:
        body = b"".join(
            m["body"] for m in self.messages if m["type"] == "http.response.body" and m["body"]
        )
        return json.loads(body)


# ---------------------------------------------------------------------------
# The declared-size fast path: refused without reading a byte
# ---------------------------------------------------------------------------


def test_a_declared_oversized_content_length_is_rejected_without_calling_receive():
    """The clearest form of "before parsing": the body is never even read.

    ``receive()`` raising if it is ever called is not a convenience — it is
    the assertion. A middleware that buffered first and checked
    ``Content-Length`` second would still (incorrectly) pass this file's other
    tests but would fail this one immediately.
    """

    async def _never_call_receive() -> Message:
        raise AssertionError(
            "an honestly declared oversized Content-Length must be refused "
            "without reading any of the body"
        )

    downstream = _RecordingDownstream()
    send = _RecordingSend()
    middleware = MaxBodySizeMiddleware(downstream, max_bytes=MAX_REQUEST_BODY_BYTES)

    _run(middleware(_scope_with_content_length(_OVER_CAP), _never_call_receive, send))

    assert not downstream.called
    assert send.status == 413
    assert send.json_body["error"]["code"] == "request_body_too_large"


def test_a_declared_content_length_at_the_cap_is_not_rejected_by_the_fast_path():
    """The bound is inclusive: exactly ``max_bytes`` must not trip the fast path.

    A trivial downstream and a single empty chunk are enough here — this test
    is only about the ``Content-Length`` check itself, not about buffering or
    replay, which the tests below cover.
    """
    downstream = _RecordingDownstream()
    send = _RecordingSend()
    middleware = MaxBodySizeMiddleware(downstream, max_bytes=MAX_REQUEST_BODY_BYTES)

    calls = 0

    async def _receive() -> Message:
        nonlocal calls
        calls += 1
        return {"type": "http.request", "body": b"", "more_body": False}

    _run(middleware(_scope_with_content_length(MAX_REQUEST_BODY_BYTES), _receive, send))

    assert downstream.called
    assert calls == 1


# ---------------------------------------------------------------------------
# No Content-Length (or a dishonest one): bounded by the running total instead
# ---------------------------------------------------------------------------


def test_a_streamed_body_is_rejected_the_moment_the_running_total_crosses_the_cap():
    """A client with no ``Content-Length`` — or a false one — is still bounded.

    Three chunks are queued; the second alone pushes the running total over
    the cap. Only two ``receive()`` calls should happen, and the downstream
    application must never be invoked: the middleware stops reading, and stops
    handing anything to the code that would parse it, the moment it knows the
    request cannot be accepted.
    """
    chunk = b"a" * (MAX_REQUEST_BODY_BYTES // 2 + 1)
    queued: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": True},
        {"type": "http.request", "body": chunk, "more_body": True},
        {"type": "http.request", "body": b"", "more_body": False},
    ]
    calls = 0

    async def _receive() -> Message:
        nonlocal calls
        message = queued[calls]
        calls += 1
        return message

    downstream = _RecordingDownstream()
    send = _RecordingSend()
    middleware = MaxBodySizeMiddleware(downstream, max_bytes=MAX_REQUEST_BODY_BYTES)

    _run(middleware(dict(_BASE_SCOPE), _receive, send))

    assert calls == 2, "must stop reading the instant the running total crosses the cap"
    assert not downstream.called
    assert send.status == 413
    assert send.json_body["error"]["code"] == "request_body_too_large"


def test_a_streamed_body_under_the_cap_is_replayed_to_the_downstream_app_unmodified():
    """A body that fits is read once and handed on exactly as received.

    This is the other half of "before parsing, not instead of it": the
    middleware must not silently drop or reorder anything for a legitimate
    request. ``captured == queued`` is what proves the replay is verbatim,
    not merely present.
    """
    queued: list[Message] = [
        {"type": "http.request", "body": b'{"a":', "more_body": True},
        {"type": "http.request", "body": b"1}", "more_body": False},
    ]
    calls = 0

    async def _receive() -> Message:
        nonlocal calls
        message = queued[calls]
        calls += 1
        return message

    downstream = _RecordingDownstream()
    send = _RecordingSend()
    middleware = MaxBodySizeMiddleware(downstream, max_bytes=MAX_REQUEST_BODY_BYTES)

    _run(middleware(dict(_BASE_SCOPE), _receive, send))

    assert downstream.called
    assert downstream.received_messages == queued


# ---------------------------------------------------------------------------
# End-to-end: the real, fully-wired application
# ---------------------------------------------------------------------------


def test_the_real_application_rejects_an_oversized_non_json_body_as_413_not_422():
    """Proof the middleware is actually wired into ``main.app``, not just correct in isolation.

    The body sent is not valid JSON at all. If this middleware were missing,
    or ran after parsing rather than before, the request would reach
    FastAPI's own body parsing and come back as a 422 ``invalid_request`` for
    malformed JSON — never a 413. Posted to ``/v1/me`` rather than the imports
    route the 2 MB bound was originally written for, which doubles as proof
    the bound is not accidentally scoped to one path (an ASGI middleware runs
    ahead of routing and cannot be route-specific without reimplementing the
    router). No database is touched: rejection happens before ``get_session``
    would ever run.
    """
    garbage = b"\xff" * _OVER_CAP

    response = TestClient(real_app).post(
        "/v1/me",
        content=garbage,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "request_body_too_large"
    assert "error" in body and "message" in body["error"]
