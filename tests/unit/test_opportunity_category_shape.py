"""P8 opportunities — category-shape fixtures only (design §9, §16; V5).

Status: **RECORDED — GATE INCOMPLETE** (design §3.3 P8 row). Only committed
category-shape fixtures are authorized at this slice. This module adds no
production code: it validates fixtures purely structurally, with no import of
(and no addition of) any parser, enum, `Literal[...]` union, or validator that
gates on the specific category value.

The recorded opportunity set — hackathon, datathon, competition, guest
lecturer event, school event — is an **inclusive set of examples, not a
closed vocabulary**, unless a later product-owner artifact explicitly says it
is exhaustive (design §9). "Out-of-list" does not mean invalid or unknown:
`tests/fixtures/opportunities/out_of_list_raw_example.json` proves a raw
example outside the five recorded names is still a valid, recognized
opportunity-category shape.

Recorded direction, not implemented here: the design's later session
direction intends out-of-list raw examples to go to the IA West Coordinator
for review (design §9). That routing is unimplemented and gate-blocked behind
T-28 identity/tenant/unit authorization and P6 persistence — this module
encodes no routing behavior, no queue, no assignee, and no approve/reject
action. No metric is registered here either; that additionally waits for an
explicit canonical opportunity definition, P6 owning persistence, and the
completed P1 authorization rule (design §9). No score floor is assumed — P8
does not inherit P5.
"""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "opportunities"

#: The five names the design records in §9 -- an inclusive example set, not a
#: closed vocabulary. Defined here only so *this test module* can check the
#: `in-list` fixtures against it; nothing in this file (or production code)
#: uses this set to reject an unlisted category.
RECORDED_EXAMPLES = frozenset(
    {
        "hackathon",
        "datathon",
        "competition",
        "guest lecturer event",
        "school event",
    }
)

#: Keys whose presence would mean a fixture had crossed the hard boundary in
#: the task brief: no authenticated assignee, no durable-queue reference, no
#: executable decision field. Checked against every fixture, in-list and
#: out-of-list alike.
FORBIDDEN_KEYS = frozenset(
    {
        "assignee",
        "assigned_to",
        "assigned_user",
        "reviewer",
        "reviewer_id",
        "queue",
        "queue_id",
        "review_queue",
        "decision",
        "approved",
        "approval",
        "rejected",
        "rejection",
        "status",
    }
)

#: Substrings that would indicate an executable decision, a durable queue, or
#: routing/assignment behavior leaking into fixture data, even under a key
#: name not listed above. Checked against the raw fixture text.
FORBIDDEN_TEXT_SUBSTRINGS = (
    "assignee",
    "assigned_to",
    "reviewer_id",
    "queue_id",
    "approve",
    "reject",
    "west_coordinator_id",
)

IN_LIST_FIXTURES = {
    "hackathon": "in_list_hackathon.json",
    "datathon": "in_list_datathon.json",
    "competition": "in_list_competition.json",
    "guest lecturer event": "in_list_guest_lecturer_event.json",
    "school event": "in_list_school_event.json",
}

OUT_OF_LIST_FIXTURE = "out_of_list_raw_example.json"

REQUIRED_KEYS = frozenset({"opportunity_category_shape", "category", "raw_label", "source"})


def _load(name: str) -> dict[str, Any]:
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


def _load_raw_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _is_valid_opportunity_category_shape(fixture: dict[str, Any]) -> bool:
    """Structural shape check only.

    Deliberately does **not** check `fixture["category"]` against the
    recorded-examples set or any other membership set -- that would be
    exactly the closed-vocabulary gate the design prohibits absent a
    product-owner artifact declaring the five examples exhaustive (design
    §9). A category outside the recorded five is just as valid a shape as
    one inside it.
    """
    if not REQUIRED_KEYS.issubset(fixture.keys()):
        return False
    category = fixture.get("category")
    if not isinstance(category, str) or category == "":
        return False
    raw_label = fixture.get("raw_label")
    return isinstance(raw_label, str) and raw_label != ""


class TestInListCategoryShape:
    """Each of the five recorded examples parses/validates to the expected shape."""

    def test_all_five_recorded_examples_have_an_in_list_fixture(self) -> None:
        assert set(IN_LIST_FIXTURES.keys()) == RECORDED_EXAMPLES

    def test_each_in_list_fixture_is_labeled_in_list_verbatim(self) -> None:
        for filename in IN_LIST_FIXTURES.values():
            fixture = _load(filename)
            assert fixture["opportunity_category_shape"] == "in-list"

    def test_each_in_list_fixture_category_matches_its_recorded_example(self) -> None:
        for expected_category, filename in IN_LIST_FIXTURES.items():
            fixture = _load(filename)
            assert fixture["category"] == expected_category

    def test_each_in_list_fixture_is_a_valid_opportunity_category_shape(self) -> None:
        for filename in IN_LIST_FIXTURES.values():
            fixture = _load(filename)
            assert _is_valid_opportunity_category_shape(fixture) is True

    def test_each_in_list_category_is_a_member_of_the_recorded_set(self) -> None:
        for filename in IN_LIST_FIXTURES.values():
            fixture = _load(filename)
            assert fixture["category"] in RECORDED_EXAMPLES


class TestOutOfListRawExampleShape:
    """An out-of-list raw example is a valid shape, not an invalid/unknown one."""

    def test_out_of_list_fixture_is_labeled_verbatim(self) -> None:
        fixture = _load(OUT_OF_LIST_FIXTURE)
        assert fixture["opportunity_category_shape"] == "out-of-list raw example"

    def test_out_of_list_category_is_not_one_of_the_recorded_examples(self) -> None:
        fixture = _load(OUT_OF_LIST_FIXTURE)
        assert fixture["category"] not in RECORDED_EXAMPLES

    def test_out_of_list_fixture_is_a_valid_opportunity_category_shape(self) -> None:
        """Out-of-list does not mean invalid or unknown (design §9)."""
        fixture = _load(OUT_OF_LIST_FIXTURE)
        assert _is_valid_opportunity_category_shape(fixture) is True

    def test_out_of_list_fixture_carries_no_rejection_or_unknown_marker(self) -> None:
        fixture = _load(OUT_OF_LIST_FIXTURE)
        for suspect_key in ("valid", "rejected", "unknown", "invalid", "error"):
            assert suspect_key not in fixture


class TestVocabularyIsOpenNotClosed:
    """Guards against the five recorded examples silently becoming a closed set.

    `_is_valid_opportunity_category_shape` above is the only "acceptance"
    check this module defines, and it is purely structural. This test proves
    that property with fresh, unlisted category values -- including a random
    one that cannot coincidentally match anything -- rather than only the one
    committed out-of-list fixture. If a future change makes the shape
    validator (or any production equivalent this test starts exercising)
    reject a category because it is absent from `RECORDED_EXAMPLES`, a
    `Literal[...]`, or an enum, this test fails.
    """

    def test_arbitrary_unlisted_categories_are_still_valid_shapes(self) -> None:
        random_category = "".join(random.choices(string.ascii_lowercase, k=16))
        arbitrary_categories = (
            "career fair",
            "networking mixer",
            "alumni panel",
            random_category,
        )
        for category in arbitrary_categories:
            assert category not in RECORDED_EXAMPLES
            synthetic_fixture = {
                "opportunity_category_shape": "out-of-list raw example",
                "category": category,
                "raw_label": f"Synthetic (test-generated, not committed): {category}",
                "source": "test-generated -- not a committed fixture",
            }
            assert _is_valid_opportunity_category_shape(synthetic_fixture) is True

    def test_recorded_examples_constant_is_not_referenced_by_the_shape_validator(self) -> None:
        """A closed-vocabulary regression would almost always start here: the
        shape validator reaching into `RECORDED_EXAMPLES` (or an equivalent
        enum/Literal) to gate acceptance. Inspect its source for that.
        """
        import inspect

        source = inspect.getsource(_is_valid_opportunity_category_shape)
        assert "RECORDED_EXAMPLES" not in source
        assert "Literal" not in source
        assert "Enum" not in source


class TestNoExecutableAssignmentOrDecision:
    """Hard boundary: no authenticated assignee, durable queue, or executable
    decision field in any P8 fixture at this slice (task brief; design §9).
    """

    def _all_fixture_filenames(self) -> tuple[str, ...]:
        return (*IN_LIST_FIXTURES.values(), OUT_OF_LIST_FIXTURE)

    def test_no_fixture_has_a_forbidden_key(self) -> None:
        for filename in self._all_fixture_filenames():
            fixture = _load(filename)
            present = FORBIDDEN_KEYS.intersection(fixture.keys())
            assert not present, f"{filename} carries forbidden key(s): {sorted(present)}"

    def test_no_fixture_text_carries_assignment_queue_or_decision_language(self) -> None:
        for filename in self._all_fixture_filenames():
            raw_lower = _load_raw_text(filename).lower()
            for substring in FORBIDDEN_TEXT_SUBSTRINGS:
                assert substring not in raw_lower, (
                    f"{filename} contains forbidden substring {substring!r}"
                )

    def test_all_fixtures_are_exactly_the_authorized_required_keys(self) -> None:
        """Category-shape only: no field beyond the four required keys."""
        for filename in self._all_fixture_filenames():
            fixture = _load(filename)
            assert set(fixture.keys()) == REQUIRED_KEYS
