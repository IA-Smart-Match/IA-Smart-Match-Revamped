import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps" / "web" / "legacy-frontend" / "src"
API = (ROOT / "lib" / "api.ts").read_text(encoding="utf-8")
CONNECTOR = (ROOT / "app" / "pages" / "Volunteers.tsx").read_text(encoding="utf-8")
BOARD = (ROOT / "app" / "components" / "SpeakerEventsBoard.tsx").read_text(encoding="utf-8")
OPENAPI = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json").read_text(
        encoding="utf-8"
    )
)


def test_frontend_uses_unit_scoped_speaker_workflow_endpoints():
    for path in (
        "/speakers",
        "/speaker-roster/publish",
        "/match-runs",
        "/shortlist",
        "/speaker-events",
        "/transitions",
        "/notes",
        "/corrections",
        "/close-attendance",
        "/cancel",
    ):
        assert path in API


def test_removed_email_and_batch_features_have_no_active_adapter():
    forbidden = (
        "/api/outreach",
        "generateEmail",
        "generateIcs",
        "initiateWorkflow",
        "agentic-workflow",
        "batch invitation",
    )
    active = API + CONNECTOR + BOARD
    for value in forbidden:
        assert value not in active


def test_shared_board_has_every_display_status():
    for label in (
        "Not Emailed Yet",
        "Awaiting Response",
        "Declined",
        "Ready for Handoff",
        "Handed Off",
        "Awaiting Final Confirmation",
        "Confirmed",
        "Withdrawn",
        "Attended",
        "Did Not Attend",
        "Event Cancelled",
    ):
        assert label in BOARD


def test_event_host_contract_excludes_private_contacts_and_internal_scores():
    schemas = OPENAPI["components"]["schemas"]
    public_fields = schemas["PublicSpeakerResponse"]["properties"]
    suggestion_fields = schemas["MatchSuggestion"]["properties"]
    assert "contact_email" not in public_fields
    assert "contact_phone" not in public_fields
    assert "score" not in suggestion_fields
    assert "percentage" not in suggestion_fields


def test_contract_has_no_email_or_unsubscribe_route():
    paths = "\n".join(OPENAPI["paths"])
    assert "/u/" not in paths
    assert "/email" not in paths
    assert "/outreach" not in paths
