"""Deterministic matching for published, available speaker profiles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


def _terms(values: Iterable[str]) -> frozenset[str]:
    return frozenset(value.strip().casefold() for value in values if value.strip())


@dataclass(frozen=True, slots=True)
class SpeakerSuggestion:
    speaker_id: Any
    topic_score: float
    proximity_score: float
    total_score: float
    explanations: tuple[str, ...]


def suggest_speakers(
    event_topics: Iterable[str], event_region: str | None, profiles: Iterable[Mapping[str, Any]]
) -> list[SpeakerSuggestion]:
    """Return up to three evidence-backed suggestions with stable ordering."""
    topics = _terms(event_topics)
    region = event_region.strip().casefold() if event_region and event_region.strip() else None
    suggestions: list[tuple[str, SpeakerSuggestion]] = []
    for profile in profiles:
        expertise = _terms(profile.get("expertise_topics") or ())
        overlap = topics & expertise
        topic_score = len(overlap) / len(topics) if topics else 0.0
        regions = _terms(
            (profile.get("home_region") or "", *(profile.get("service_regions") or ()))
        )
        proximity = 1.0 if region and region in regions else 0.0
        if topic_score == 0 and proximity == 0:
            continue
        explanations: list[str] = []
        if overlap:
            explanations.append("Relevant experience: " + ", ".join(sorted(overlap)))
        if proximity:
            explanations.append("Serves the event region")
        suggestions.append(
            (
                str(profile.get("name", "")).casefold(),
                SpeakerSuggestion(
                    profile["speaker_id"],
                    topic_score,
                    proximity,
                    topic_score * 0.7 + proximity * 0.3,
                    tuple(explanations),
                ),
            )
        )
    suggestions.sort(key=lambda item: (-item[1].total_score, item[0], str(item[1].speaker_id)))
    return [item[1] for item in suggestions[:3]]
