"""OpenAPI contract for the Speaker's own routes (B26 T6b-2 plan §5, §7.5).

``SPEAKER_PORTAL`` is off in every scope, so the committed document carries none
of these paths. The schema is proven on an application built with the
capability on (the ``test_exercise_instructor_router.py`` pattern).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.main import routers_for
from smartmatch_domain.product_scope import Capability

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"

OPERATIONS = {
    ("/v1/me/availability", "get"),
    ("/v1/me/availability", "patch"),
    ("/v1/me/invitations", "get"),
    ("/v1/me/invitations/{invitation_id}/response", "post"),
    ("/v1/me/engagements", "get"),
}
PATHS = {path for path, _ in OPERATIONS}


class _PortalOn(Settings):
    def capability_enabled(self, capability: Capability) -> bool:  # type: ignore[override]
        return capability is Capability.SPEAKER_PORTAL or super().capability_enabled(capability)


@cache
def _document() -> dict[str, Any]:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(_PortalOn()):
        app.include_router(router)
    return app.openapi()


def _schema(name: str) -> dict[str, Any]:
    return _document()["components"]["schemas"][name]


def _resolve(ref_holder: dict[str, Any]) -> dict[str, Any]:
    return _schema(ref_holder["$ref"].rsplit("/", 1)[-1])


def test_the_five_operations_are_published_when_on() -> None:
    paths = _document()["paths"]
    for path, method in OPERATIONS:
        assert method in paths.get(path, {}), (path, method)
        responses = paths[path][method]["responses"]
        for code in ("403", "404", "429"):
            assert code in responses, (path, method, code)
    assert "409" in paths["/v1/me/availability"]["patch"]["responses"]
    assert "409" in paths["/v1/me/invitations/{invitation_id}/response"]["post"]["responses"]


def test_no_parameter_names_a_subject() -> None:
    names = set()
    for path, method in OPERATIONS:
        for parameter in _document()["paths"][path][method].get("parameters", []):
            # Only the bearer header is skipped: it is authentication, not a
            # subject. Any other header or cookie stays in the checked set.
            if parameter["name"].lower() == "authorization":
                continue
            names.add(parameter["name"])
    assert names == {"invitation_id", "when"}


def test_request_bodies_forbid_additional_properties() -> None:
    paths = _document()["paths"]
    for path, method in (
        ("/v1/me/availability", "patch"),
        ("/v1/me/invitations/{invitation_id}/response", "post"),
    ):
        schema = paths[path][method]["requestBody"]["content"]["application/json"]["schema"]
        body = _resolve(schema)
        assert body["additionalProperties"] is False, path
        assert not {"professional_id", "user_id", "unit_id"} & set(body["properties"])


def test_invitation_and_engagement_items_have_exact_property_sets() -> None:
    assert set(_schema("MyInvitation")["properties"]) == {
        "invitation_id",
        "event",
        "dispatched_at",
        "status",
        "response",
        "answerable",
    }
    assert set(_schema("MyInvitationEvent")["properties"]) == {
        "title",
        "date_text",
        "local_date",
        "time_zone",
    }
    assert set(_schema("MyInvitationResponse")["properties"]) == {"recorded_at", "recorded_by"}
    assert set(_schema("MyEngagement")["properties"]) == {
        "engagement_id",
        "event",
        "state",
        "confirmed_at",
        "attended_at",
        "cancelled_at",
    }
    assert set(_schema("MyEngagementEvent")["properties"]) == {
        "title",
        "local_date",
        "time_zone",
        "time_precision",
        "starts_at",
        "ends_at",
    }


def test_when_is_an_enum_of_upcoming_and_past() -> None:
    parameters = _document()["paths"]["/v1/me/engagements"]["get"]["parameters"]
    (when,) = [p for p in parameters if p["name"] == "when"]
    schema = when["schema"]
    if "$ref" in schema:
        schema = _resolve(schema)
    assert set(schema["enum"]) == {"upcoming", "past"}
    assert schema.get("default") == "upcoming" or when["schema"].get("default") == "upcoming"


def test_committed_contract_has_none_of_the_four_paths() -> None:
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert not set(committed["paths"]) & PATHS
