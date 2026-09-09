"""Email delivery code is not wired into the application."""

from pathlib import Path

from smartmatch_api.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_api_exposes_no_email_outreach_route() -> None:
    paths = set(app.openapi()["paths"])
    assert not any("outreach" in path or "speaker-invitations" in path for path in paths)


def test_worker_does_not_register_the_email_handler() -> None:
    source = (ROOT / "services/worker/smartmatch_worker/main.py").read_text(encoding="utf-8")
    assert "build_outreach_send_handler" not in source
    assert "build_email_provider" not in source
    assert "with_outreach_send(" not in source
