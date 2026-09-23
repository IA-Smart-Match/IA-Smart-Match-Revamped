"""OpenAPI contract for the Connector availability routes (B26 T3).

Asserted against the committed document, which is what a client generator
reads: a full-replace body whose keys are optional in the schema would let a
generated client omit one and silently clear it.
"""

from __future__ import annotations

import json
from pathlib import Path

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"

PATH = "/v1/units/{unit_id}/speaker-contacts/{professional_id}/availability"


def _document() -> dict:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _document()["components"]["schemas"][name]


def _types(prop: dict) -> set[str]:
    return {option.get("type") for option in prop.get("anyOf", [prop])}


def test_both_methods_are_published() -> None:
    operations = _document()["paths"][PATH]
    assert {"get", "patch"} <= set(operations)


def test_patch_takes_the_update_request() -> None:
    body = _document()["paths"][PATH]["patch"]["requestBody"]
    ref = body["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/SpeakerAvailabilityUpdateRequest")


def test_request_requires_every_key_and_forbids_others() -> None:
    request = _schema("SpeakerAvailabilityUpdateRequest")
    assert set(request["required"]) == {
        "expected_version",
        "invitations_paused_until",
        "declared_capacity_hours_per_90_days",
        "unavailable",
    }
    assert request["additionalProperties"] is False
    assert "professional_id" not in request["properties"]


def test_expected_version_is_integer_or_null() -> None:
    prop = _schema("SpeakerAvailabilityUpdateRequest")["properties"]["expected_version"]
    assert _types(prop) == {"integer", "null"}


def test_response_version_and_capacity_are_nullable_numbers() -> None:
    properties = _schema("SpeakerAvailabilityResponse")["properties"]
    assert _types(properties["version"]) == {"integer", "null"}
    capacity = _types(properties["declared_capacity_hours_per_90_days"])
    assert "number" in capacity
    assert "null" in capacity
    assert "updated_by_user_id" not in properties


def test_router_is_not_mounted_when_speaker_contacts_are_off() -> None:
    """Plan-gate addition 5: the class-exercise scope turns the roster off."""
    from smartmatch_api.config import Settings
    from smartmatch_api.main import routers_for
    from smartmatch_api.routers import speaker_availability
    from smartmatch_domain.product_scope import Capability, ProductScope

    settings = Settings(product_scope=ProductScope.CLASS_EXERCISE)
    assert not settings.capability_enabled(Capability.SPEAKER_CONTACT_MANAGEMENT)
    assert speaker_availability.router not in routers_for(settings)
    assert speaker_availability.router in routers_for(Settings(product_scope=ProductScope.CBA))
