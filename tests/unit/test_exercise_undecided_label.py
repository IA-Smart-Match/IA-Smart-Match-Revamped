"""The Undecided half's words arrive from the server as a ``factor_labels`` entry.

OQ-CE-14 / D2: the reason line names an undecided goal's half as "undecided
goal suits a broad event". The web used to keep its own copy of that phrase to
print under the reason; a copy can drift from the server's wording. The list
response now carries it under the ``undecided_goal_half`` key — the same name
as the entry flag that says when to use it — and the four factor labels are
unchanged beside it.
"""

from __future__ import annotations

from smartmatch_api.routers.exercise_matching_models import (
    RankedListView,
    rankable_set,
    ranked_list_view,
)
from smartmatch_domain.exercise.registry import EXERCISE_FACTOR_LABELS

from tests.unit.test_exercise_undecided_goal_flag import (
    _GOAL_ONLY,
    _UNDECIDED_CARDS,
    _event,
    _events,
    _ranked,
    _rows,
)

_KEY = "undecided_goal_half"


def _view() -> RankedListView:
    return ranked_list_view(
        _ranked("E11", _GOAL_ONLY),
        rankable_set(_rows(), _events()),
        event=_event("E11"),
        weights=_GOAL_ONLY,
        setting_name=None,
    )


def test_the_list_response_labels_the_undecided_half() -> None:
    assert _view().factor_labels[_KEY] == "undecided goal suits a broad event"


def test_the_label_is_the_phrase_the_reason_line_uses() -> None:
    view = _view()
    label = view.factor_labels[_KEY]
    undecided = [e for e in view.entries if e.profile_no in _UNDECIDED_CARDS]
    assert undecided
    assert all(label.lower() in entry.reason.lower() for entry in undecided)


def test_the_four_factor_labels_are_unchanged_beside_it() -> None:
    labels = _view().factor_labels
    assert {k: v for k, v in labels.items() if k != _KEY} == dict(EXERCISE_FACTOR_LABELS)


def test_the_label_is_not_a_weight() -> None:
    assert _KEY not in _view().weights
