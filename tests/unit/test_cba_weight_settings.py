"""What a matching-weight setting may be, and what it may never become.

Every assertion here about a "default" compares against
:func:`smartmatch_domain.factor_registry.normalize_weights` rather than against
a number. That is not stylistic caution: a test that asserted
``applied_weights(None)["industry_match"] == 0.30`` would be one more copy of
the registry default — the one nobody thinks of as a copy — and it would keep
passing for a whole release after ADR-0016 revised the weight, reporting that
the override layer works while it quietly served a stale figure.

:func:`test_no_registry_weight_literal_appears_in_the_settings_feature` is the
mechanical half of the same rule, in the shape ``tests/unit/test_factor_registry.py``
uses for the §11 virtual weights: it reads the feature's own source and requires
that none of the registry's numbers has been retyped into it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    CBA_PHYSICAL_MODEL,
    CBA_VIRTUAL_MODEL,
    SCORING_MODELS,
    normalize_weights,
)
from smartmatch_domain.factors.industry_match import INDUSTRY_MATCH_FACTOR_KEY
from smartmatch_domain.factors.proximity import CBA_PROXIMITY_FACTOR_KEY
from smartmatch_domain.factors.role_match import ROLE_MATCH_FACTOR_KEY
from smartmatch_domain.weight_settings import (
    CONFIGURABLE_FACTOR_KEYS,
    InvalidWeightOverrideError,
    MatchWeightSettings,
    applied_weights,
    configurable_factor_keys,
    validate_weight_overrides,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every runtime module this card adds. Read as text by the literal check below,
#: so a default retyped into any of them fails here rather than drifting.
SETTINGS_FEATURE_SOURCES: tuple[Path, ...] = (
    REPO_ROOT / "python/smartmatch_domain/smartmatch_domain/weight_settings.py",
    REPO_ROOT / "python/smartmatch_persistence/smartmatch_persistence/match_weight_settings.py",
    REPO_ROOT / "services/api/smartmatch_api/routers/matching_weights.py",
    REPO_ROOT / "db/migrations/versions/0027_match_weight_setting.py",
)

#: A stand-in account id. Synthetic, and nothing here reaches a database.
AN_AUTHOR = "3f7c1e02-0000-4000-8000-000000000001"

#: A fixed instant, so a failure message never depends on when the suite ran.
A_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The override layer defers to the registry
# ---------------------------------------------------------------------------


def test_a_unit_with_no_settings_scores_on_the_registrys_own_weights() -> None:
    """``None`` is not an empty weighting; it is "ask the registry"."""
    assert dict(applied_weights(None, model=CBA_PHYSICAL_MODEL)) == dict(
        normalize_weights(model=CBA_PHYSICAL_MODEL)
    )


def test_an_empty_override_map_is_the_same_scoring_answer_as_no_settings() -> None:
    """A unit that reset its settings scores exactly as one that never had any.

    Their *histories* differ — one has an author and a timestamp — and the
    repository keeps them distinguishable. What must not differ is the score.
    """
    assert dict(applied_weights({}, model=CBA_PHYSICAL_MODEL)) == dict(
        applied_weights(None, model=CBA_PHYSICAL_MODEL)
    )


def test_a_partial_override_leaves_every_other_factor_on_its_registry_share() -> None:
    """Overriding one factor must not silently restate the other three.

    The un-overridden factors keep the *ratios* the registry declares, which is
    the property that survives a registry revision. Asserting their absolute
    values instead would have pinned today's numbers into this file.
    """
    defaults = normalize_weights(model=CBA_PHYSICAL_MODEL)
    overrides = validate_weight_overrides({INDUSTRY_MATCH_FACTOR_KEY: 10.0})
    applied = applied_weights(overrides, model=CBA_PHYSICAL_MODEL)

    others = [key for key in defaults if key != INDUSTRY_MATCH_FACTOR_KEY]
    for left, right in zip(others, others[1:], strict=False):
        assert applied[left] * defaults[right] == pytest.approx(
            applied[right] * defaults[left]
        ), "un-overridden factors must keep the registry's ratios"


def test_applied_weights_always_sum_to_one() -> None:
    overrides = validate_weight_overrides(
        {INDUSTRY_MATCH_FACTOR_KEY: 7.0, ROLE_MATCH_FACTOR_KEY: 3.0}
    )
    for model in (CBA_PHYSICAL_MODEL, CBA_VIRTUAL_MODEL):
        assert sum(applied_weights(overrides, model=model).values()) == pytest.approx(1.0)


def test_the_scale_of_an_override_pair_does_not_change_their_ratio() -> None:
    """Normalization is what makes an upper bound unnecessary."""
    small = applied_weights(
        validate_weight_overrides({INDUSTRY_MATCH_FACTOR_KEY: 2.0, ROLE_MATCH_FACTOR_KEY: 1.0}),
        model=CBA_PHYSICAL_MODEL,
    )
    large = applied_weights(
        validate_weight_overrides(
            {INDUSTRY_MATCH_FACTOR_KEY: 2_000.0, ROLE_MATCH_FACTOR_KEY: 1_000.0}
        ),
        model=CBA_PHYSICAL_MODEL,
    )
    assert small[INDUSTRY_MATCH_FACTOR_KEY] / small[ROLE_MATCH_FACTOR_KEY] == pytest.approx(
        large[INDUSTRY_MATCH_FACTOR_KEY] / large[ROLE_MATCH_FACTOR_KEY]
    )


def test_a_virtual_run_never_carries_a_proximity_weight_however_it_is_set() -> None:
    """Customer §11's exclusion is structural and a setting cannot undo it."""
    overrides = validate_weight_overrides({CBA_PROXIMITY_FACTOR_KEY: 9.0})
    assert CBA_PROXIMITY_FACTOR_KEY not in applied_weights(overrides, model=CBA_VIRTUAL_MODEL)
    assert CBA_PROXIMITY_FACTOR_KEY in applied_weights(overrides, model=CBA_PHYSICAL_MODEL)


# ---------------------------------------------------------------------------
# Refusal, never repair
# ---------------------------------------------------------------------------


def test_an_unknown_factor_key_is_refused_rather_than_ignored() -> None:
    """``normalize_weights`` ignores it; the settings boundary must not.

    A Connector who types ``industry`` for ``industry_match`` would otherwise
    get a 2xx, no effect, and no explanation.
    """
    with pytest.raises(InvalidWeightOverrideError) as excinfo:
        validate_weight_overrides({"industry": 0.5})
    assert "industry" in str(excinfo.value)
    assert "not a configurable factor" in str(excinfo.value)


@pytest.mark.parametrize(
    "value",
    [-0.1, float("nan"), float("inf"), float("-inf"), "0.4", None, True],
    ids=["negative", "nan", "inf", "-inf", "string", "none", "boolean"],
)
def test_a_value_that_is_not_a_finite_non_negative_number_is_refused(value: object) -> None:
    with pytest.raises(InvalidWeightOverrideError):
        validate_weight_overrides({INDUSTRY_MATCH_FACTOR_KEY: value})


def test_a_weight_set_that_zeroes_out_every_scored_factor_is_refused() -> None:
    """All-zero would normalize to all-zero and score every candidate 0.0."""
    with pytest.raises(InvalidWeightOverrideError) as excinfo:
        validate_weight_overrides(dict.fromkeys(CONFIGURABLE_FACTOR_KEYS, 0.0))
    assert "sum to zero" in str(excinfo.value)


def test_a_set_that_only_breaks_the_virtual_model_is_still_refused() -> None:
    """A setting must be admissible for *every* current model.

    Proximity carries the whole weight and the other three are zeroed: coherent
    for a physical event, and for a virtual one it leaves nothing at all,
    because §11 drops Proximity before normalization.
    """
    proposal: dict[str, float] = dict.fromkeys(CONFIGURABLE_FACTOR_KEYS, 0.0)
    proposal[CBA_PROXIMITY_FACTOR_KEY] = 1.0

    # It really would have been fine for the physical model alone ...
    assert sum(applied_weights(proposal, model=CBA_PHYSICAL_MODEL).values()) == pytest.approx(1.0)

    # ... and it is refused anyway, naming the mode it would have broken.
    with pytest.raises(InvalidWeightOverrideError) as excinfo:
        validate_weight_overrides(proposal)
    assert CBA_VIRTUAL_MODEL.scoring_mode is not None
    assert CBA_VIRTUAL_MODEL.scoring_mode in str(excinfo.value)


def test_an_empty_proposal_is_accepted_as_a_reset() -> None:
    """"Use the approved weights" is not the same request as "score nothing"."""
    assert dict(validate_weight_overrides({})) == {}


def test_every_problem_is_reported_at_once() -> None:
    """A settings form is fixed in one pass, or in as many passes as we report."""
    with pytest.raises(InvalidWeightOverrideError) as excinfo:
        validate_weight_overrides({"nonsense": 1.0, INDUSTRY_MATCH_FACTOR_KEY: -1.0})
    message = str(excinfo.value)
    assert "nonsense" in message
    assert INDUSTRY_MATCH_FACTOR_KEY in message


def test_a_zero_on_one_factor_alone_is_perfectly_valid() -> None:
    """Refusing a zero *total* is not refusing a zero.

    Switching one factor off is a legitimate weighting; the registry supplies
    the rest and the total is still positive.
    """
    overrides = validate_weight_overrides({CBA_PROXIMITY_FACTOR_KEY: 0.0})
    applied = applied_weights(overrides, model=CBA_PHYSICAL_MODEL)
    assert applied[CBA_PROXIMITY_FACTOR_KEY] == 0.0
    assert sum(applied.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The stored value, and its audit fields
# ---------------------------------------------------------------------------


def test_settings_carry_an_author_and_a_version() -> None:
    settings = MatchWeightSettings(
        overrides=validate_weight_overrides({ROLE_MATCH_FACTOR_KEY: 1.0}),
        version=2,
        updated_by_user_id=AN_AUTHOR,
        updated_at=A_MOMENT,
    )
    assert settings.version == 2
    assert sum(settings.weights_for(CBA_PHYSICAL_MODEL).values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("version", "author"),
    [(0, AN_AUTHOR), (-1, AN_AUTHOR), (1, "  ")],
    ids=["version-zero", "version-negative", "blank-author"],
)
def test_settings_that_could_not_have_come_from_a_real_change_are_refused(
    version: int, author: str
) -> None:
    with pytest.raises(ValueError):
        MatchWeightSettings(
            overrides={},
            version=version,
            updated_by_user_id=author,
            updated_at=A_MOMENT,
        )


def test_settings_refuse_a_non_configurable_factor_even_when_built_directly() -> None:
    """The constructor is a second gate, not a repetition of the first.

    A row read back from a database that predates a registry retirement would
    otherwise reach a scoring path carrying a factor no model admits.
    """
    with pytest.raises(ValueError, match="non-configurable"):
        MatchWeightSettings(
            overrides={"topic_relevance": 1.0},
            version=1,
            updated_by_user_id=AN_AUTHOR,
            updated_at=A_MOMENT,
        )


def test_the_configurable_set_is_the_registrys_approved_scoring_set() -> None:
    """Derived, not restated, so a registry change cannot leave a factor
    unconfigurable or a setting inert."""
    assert CONFIGURABLE_FACTOR_KEYS == APPROVED_SCORING_KEYS
    assert configurable_factor_keys() == tuple(sorted(APPROVED_SCORING_KEYS))


# ---------------------------------------------------------------------------
# The rule this whole card exists to keep
# ---------------------------------------------------------------------------


def test_no_registry_weight_literal_appears_in_the_settings_feature() -> None:
    """Registry defaults stay the sole default literals.

    Every normalized weight either current model computes is searched for as a
    decimal literal in this feature's own source. A migration default, a
    Pydantic field default, or a fixture that retyped one of them is caught
    here.

    The search is textual on purpose. A structural check would be tighter and
    would also be satisfied by a value assembled from two halves; the failure
    this guards against is somebody typing a number they read off the ADR.
    """
    forbidden: set[str] = set()
    for model in SCORING_MODELS.values():
        for value in normalize_weights(model=model).values():
            rendered = f"{value:.6f}".rstrip("0")
            if len(rendered) >= 4:
                # A short rendering ("0.3") is an ordinary number a docstring or
                # a scale may legitimately contain; every registry default and
                # every §11 virtual weight renders longer than that.
                forbidden.add(rendered)

    present = [path for path in SETTINGS_FEATURE_SOURCES if path.exists()]
    assert present, "the settings feature's sources moved; update SETTINGS_FEATURE_SOURCES"

    offences: list[str] = []
    for path in present:
        source = path.read_text(encoding="utf-8")
        for literal in sorted(forbidden):
            for match in re.finditer(re.escape(literal), source):
                offences.append(f"{path.relative_to(REPO_ROOT)}: {literal!r} at {match.start()}")

    assert not offences, (
        "a registry weight has been retyped into the settings feature; settings are "
        "an override layer and the registry is the only place a default is written: "
        + "; ".join(offences)
    )
