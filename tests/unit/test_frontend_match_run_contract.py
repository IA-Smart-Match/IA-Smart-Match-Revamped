"""Event Host Smart Match client contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src"
API = (ROOT / "lib/api.ts").read_text(encoding="utf-8")
EVENTS = (ROOT / "app/pages/coordinator/CoordinatorEvents.tsx").read_text(encoding="utf-8")


def test_event_host_runs_and_submits_the_new_match_workflow() -> None:
    assert "runSpeakerMatch" in API and "submitSpeakerShortlist" in API
    assert "runSpeakerMatch" in EVENTS and "submitSpeakerShortlist" in EVENTS
    assert '"Idempotency-Key"' in API


def test_suggestions_do_not_expose_scores() -> None:
    suggestion = API.split("export interface MatchSuggestion", 1)[1].split("}", 1)[0]
    assert "score" not in suggestion.casefold()
    assert "percentage" not in suggestion.casefold()
