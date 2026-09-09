from smartmatch_domain.speaker_matching import suggest_speakers
from smartmatch_persistence import schema


def test_matching_is_deterministic_and_does_not_pad_results():
    profiles = [
        {
            "speaker_id": "b",
            "name": "Beta",
            "expertise_topics": ["AI"],
            "home_region": "West",
            "service_regions": [],
        },
        {
            "speaker_id": "a",
            "name": "Alpha",
            "expertise_topics": ["AI"],
            "home_region": "West",
            "service_regions": [],
        },
        {
            "speaker_id": "c",
            "name": "No evidence",
            "expertise_topics": ["Finance"],
            "home_region": "East",
            "service_regions": [],
        },
    ]
    result = suggest_speakers(["AI"], "West", profiles)
    assert [item.speaker_id for item in result] == ["a", "b"]
    assert all(item.explanations for item in result)


def test_matching_caps_results_at_three():
    profiles = [
        {
            "speaker_id": str(i),
            "name": str(i),
            "expertise_topics": ["Data"],
            "home_region": None,
            "service_regions": [],
        }
        for i in range(5)
    ]
    assert len(suggest_speakers(["Data"], None, profiles)) == 3


def test_match_results_snapshot_the_displayed_profile() -> None:
    assert {
        "speaker_name",
        "speaker_title",
        "speaker_company",
        "speaker_board_role",
        "expertise_topics",
        "home_region",
        "service_regions",
    } <= set(schema.speaker_match_result.c.keys())
