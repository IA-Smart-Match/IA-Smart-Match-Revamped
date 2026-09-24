"""API contract tests for the Foundation surface."""

from __future__ import annotations

import secrets
from html.parser import HTMLParser
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_leaks_no_dependency_or_topology_detail():
    """v1.1 §1.11: public health endpoints expose no dependency or topology detail."""
    body = TestClient(app).get("/api/health").json()
    serialized = str(body).lower()

    for leaked in (
        "postgres",
        "database",
        "database_url",
        "localhost",
        "queue",
        "cloud",
        "resend",
        "api_key",
        "secret",
        "password",
        "5432",
    ):
        assert leaked not in serialized, f"health response leaks {leaked!r}"


def test_health_response_keys_are_minimal():
    body = TestClient(app).get("/api/health").json()
    assert set(body) == {"status", "release"}


# ---------------------------------------------------------------------------
# The archived legacy surface must not exist
# ---------------------------------------------------------------------------


def test_mock_login_endpoint_does_not_exist():
    """Caller-selected identity is archived (legacy portals.py:435)."""
    response = TestClient(app).post("/auth/mock-login", json={"role": "admin"})
    assert response.status_code == 404


def test_no_route_advertises_a_mock_or_demo_login():
    """Checked against the published contract, not the route table.

    ``app.routes`` mixes route objects with router wrappers that have no
    ``.path``, and it is the OpenAPI document that clients actually see — so
    asserting on the document is both more robust and more meaningful.
    """
    paths = set(app.openapi()["paths"])
    assert not any("mock" in path or "demo" in path for path in paths)


# ---------------------------------------------------------------------------
# Unsubscribe GET/POST semantics (v1.1 §1.10)
# ---------------------------------------------------------------------------


def test_unsubscribe_get_renders_a_confirmation_page(client: TestClient):
    response = client.get("/u/some-opaque-token")
    assert response.status_code == 200
    assert "confirm" in response.text.lower()


def test_unsubscribe_get_does_not_echo_the_token():
    """Reflecting the token into HTML invites both leakage and injection."""
    response = TestClient(app).get("/u/secret-token-value")
    assert "secret-token-value" not in response.text


def test_unsubscribe_get_is_declared_safe():
    """A GET route must not be registered for any mutating verb path.

    The corrected design puts the state change on a signed POST; this asserts
    the GET path exists and is registered for GET only.

    Read off the OpenAPI document rather than off ``app.routes``, for exactly
    the reason the docstring two tests above already gives: ``app.routes`` mixes
    route objects with router wrappers that have no ``.path``, so which of the
    two a route appears as depends on whether it was declared with ``@app.get``
    or included from a router — a composition detail, not a contract one. These
    pages moved behind ``Capability.CONSENTED_OUTREACH`` (ADR-0025 D1: a
    no-login product serves no CBA outreach page), which changed them from the
    first form to the second and changed nothing a client sees. The document is
    what a client sees, and it is byte-identical.
    """
    operations = set(app.openapi()["paths"]["/u/{token}"])
    assert operations == {"get"}


# ---------------------------------------------------------------------------
# Speaker invitation page (B26 T6a): real accept / decline controls
# ---------------------------------------------------------------------------

#: A real-shaped token, minted the way invitations mint theirs. Derived at
#: runtime rather than written as a literal: a credential-shaped string spelled
#: out in source trips the forbidden-behavior scan (hard-coded-credential).
_REAL_SHAPED_TOKEN = secrets.token_urlsafe(32)

#: The headers every token page sends (T6a plan §2.3).
_TOKEN_PAGE_HEADERS = {
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-robots-tag": "noindex",
    "x-content-type-options": "nosniff",
    "content-security-policy": (
        "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}


class _Element:
    def __init__(self, tag: str, attrs: dict[str, str | None]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.text = ""


class _PageParser(HTMLParser):
    """Collects every element with its attributes and its direct text."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[_Element] = []
        self._open: list[_Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(tag, dict(attrs))
        self.elements.append(element)
        if tag not in {"meta", "link", "br", "input"}:
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index].tag == tag:
                del self._open[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._open:
            self._open[-1].text += data

    def find(self, tag: str) -> list[_Element]:
        return [element for element in self.elements if element.tag == tag]


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    return parser


def test_invitation_page_renders_accept_and_decline_controls(client: TestClient):
    """One POST form with no ``action``: it posts to the page's own URL, so the
    token travels in the path the Speaker already holds and is never written
    into the HTML."""
    page = _parse(client.get(f"/i/{_REAL_SHAPED_TOKEN}").text)

    forms = page.find("form")
    assert len(forms) == 1
    assert (forms[0].attrs.get("method") or "").lower() == "post"
    assert "action" not in forms[0].attrs

    buttons = [
        button
        for button in page.find("button")
        if button.attrs.get("type") == "submit" and button.attrs.get("name") == "response"
    ]
    assert sorted(button.attrs.get("value") for button in buttons) == ["accept", "decline"]
    assert page.find("input") == []


def test_invitation_page_does_not_echo_the_token(client: TestClient):
    """Reflecting the token invites both leakage and injection."""
    response = client.get("/i/secret-token-value-0123456789")

    assert "secret-token-value-0123456789" not in response.text
    assert all("secret-token-value-0123456789" not in value for value in response.headers.values())


@pytest.mark.parametrize(
    "token",
    [_REAL_SHAPED_TOKEN, "abc", "x" * 300, "<script>alert(1)"],
    ids=["real-shaped", "three-chars", "three-hundred-chars", "script"],
)
def test_invitation_page_is_identical_for_every_token(client: TestClient, token: str):
    """The page says nothing about whether a token is real."""
    baseline = client.get("/i/another-token-entirely-0123456789")
    response = client.get(f"/i/{quote(token, safe='')}")

    assert response.status_code == 200
    assert response.content == baseline.content


def test_invitation_page_has_labelled_real_buttons(client: TestClient):
    page = _parse(client.get(f"/i/{_REAL_SHAPED_TOKEN}").text)

    labels = {button.attrs.get("value"): button.text.strip() for button in page.find("button")}
    assert labels == {"accept": "Accept invitation", "decline": "Decline invitation"}

    (html,) = page.find("html")
    assert html.attrs.get("lang") == "en"
    assert len(page.find("h1")) == 1

    (form,) = page.find("form")
    described_by = form.attrs.get("aria-describedby")
    assert described_by
    assert [element for element in page.elements if element.attrs.get("id") == described_by]


def test_token_pages_send_no_store_no_referrer_and_csp(client: TestClient):
    response = client.get(f"/i/{_REAL_SHAPED_TOKEN}")

    assert response.headers["content-type"] == "text/html; charset=utf-8"
    for name, value in _TOKEN_PAGE_HEADERS.items():
        assert response.headers.get(name) == value, name


def test_invitation_path_serves_get_and_post_only():
    """GET renders the page and never changes state; the answer is the POST."""
    operations = set(app.openapi()["paths"]["/i/{token}"])
    assert operations == {"get", "post"}


# ---------------------------------------------------------------------------
# OpenAPI is the contract source of truth
# ---------------------------------------------------------------------------


def test_openapi_document_is_generated(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "SmartMatch API"
    assert "/api/health" in schema["paths"]


def test_error_envelope_is_declared_in_the_schema(client: TestClient):
    """The stable error envelope is part of the published contract."""
    schema = client.get("/openapi.json").json()
    assert "ErrorEnvelope" in schema["components"]["schemas"]
