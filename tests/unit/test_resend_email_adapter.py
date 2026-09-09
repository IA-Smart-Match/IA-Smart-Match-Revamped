"""The retired email provider is unreachable from shipped composition."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_runtime_composition_imports_the_email_provider() -> None:
    api = (ROOT / "services/api/smartmatch_api/main.py").read_text(encoding="utf-8")
    worker = (ROOT / "services/worker/smartmatch_worker/main.py").read_text(encoding="utf-8")
    assert "build_email_provider" not in api
    assert "build_email_provider" not in worker
