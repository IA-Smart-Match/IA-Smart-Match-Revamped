"""``smartmatch_domain.synthetic_pilot`` — pure derivation rules, no storage.

No live database is needed: every assertion here is about a deterministic
function of its own arguments. The one exception —
:func:`test_synthetic_match_provenance_matches_the_persisted_vocabulary` —
imports ``smartmatch_persistence.pipeline`` to prove the two independently
spelled provenance literals still agree; see that test's own docstring, and
the module docstring of ``smartmatch_domain.synthetic_pilot``, for why the
layering contract forces this deliberate duplication rather than a shared
import.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from types import ModuleType

import pytest
from smartmatch_domain import synthetic_pilot

#: Score-shaped identifier fragments. Checked against *identifiers* only
#: (see :func:`_fabricated_score_identifiers`) — never against prose — so a
#: module is free to say, in its own docstring, that it computes none of
#: these, without failing its own check for containing the word.
_FABRICATED_SCORE_TOKENS = ("score", "confidence", "match_score", "rank", "weight")


def _fabricated_score_identifiers(module: ModuleType) -> list[str]:
    """Score-shaped names used as assignment targets, parameters, or keyword/column names.

    Walks the module's AST rather than grepping its raw source text. A
    substring scan over the whole source would also scan docstrings,
    comments, and string literals — failing on ordinary English
    ("underscore", "ranking", "frankly") and, worse, on this very module's
    own prose stating that it computes none of these things. What actually
    matters is whether the module *stores* a fabricated value under one of
    these names: as a variable, an attribute, a function parameter, or a
    keyword/column argument to a call (the shape ``.values(score=...)``
    would take), or as a function's own name. Docstrings, comments, and
    string literals are never inspected.
    """
    tree = ast.parse(inspect.getsource(module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        name: str | None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.id
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            name = node.attr
        elif isinstance(node, ast.arg | ast.keyword):
            name = node.arg
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name
        else:
            name = None
        if name is not None and any(token in name.lower() for token in _FABRICATED_SCORE_TOKENS):
            offenders.append(name)
    return offenders


# ---------------------------------------------------------------------------
# synthetic_professional_subject_id
# ---------------------------------------------------------------------------


def test_synthetic_professional_subject_id_is_deterministic() -> None:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()

    first = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, name="Ada Lovelace"
    )
    second = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, name="Ada Lovelace"
    )

    assert first == second


def test_synthetic_professional_subject_id_is_case_and_whitespace_insensitive() -> None:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()

    ids = {
        synthetic_pilot.synthetic_professional_subject_id(
            tenant_id=tenant_id, unit_id=unit_id, name=name
        )
        for name in ("Ada Lovelace", "  ada lovelace  ", "ADA LOVELACE")
    }

    assert len(ids) == 1


def test_synthetic_professional_subject_id_separates_units() -> None:
    tenant_id = uuid.uuid4()

    first = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=uuid.uuid4(), name="Ada Lovelace"
    )
    second = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=uuid.uuid4(), name="Ada Lovelace"
    )

    assert first != second


def test_synthetic_professional_subject_id_separates_tenants() -> None:
    unit_id = uuid.uuid4()

    first = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=uuid.uuid4(), unit_id=unit_id, name="Ada Lovelace"
    )
    second = synthetic_pilot.synthetic_professional_subject_id(
        tenant_id=uuid.uuid4(), unit_id=unit_id, name="Ada Lovelace"
    )

    assert first != second


@pytest.mark.parametrize("blank_name", ["", "   "])
def test_synthetic_professional_subject_id_refuses_a_blank_name(blank_name: str) -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        synthetic_pilot.synthetic_professional_subject_id(
            tenant_id=uuid.uuid4(), unit_id=uuid.uuid4(), name=blank_name
        )


# ---------------------------------------------------------------------------
# synthetic_opportunity_event_id
# ---------------------------------------------------------------------------


def test_synthetic_opportunity_event_id_is_deterministic() -> None:
    tenant_id = uuid.uuid4()
    review_item_id = uuid.uuid4()

    first = synthetic_pilot.synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=review_item_id
    )
    second = synthetic_pilot.synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=review_item_id
    )

    assert first == second


def test_synthetic_opportunity_event_id_differs_for_a_different_review_item() -> None:
    tenant_id = uuid.uuid4()

    first = synthetic_pilot.synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=uuid.uuid4()
    )
    second = synthetic_pilot.synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=uuid.uuid4()
    )

    assert first != second


# ---------------------------------------------------------------------------
# synthetic_professional_external_subject / synthetic_professional_email
# ---------------------------------------------------------------------------


def test_synthetic_professional_external_subject_is_prefixed() -> None:
    subject_id = uuid.uuid4()

    external_subject = synthetic_pilot.synthetic_professional_external_subject(subject_id)

    assert external_subject.startswith("synthetic-professional:")
    assert external_subject == f"synthetic-professional:{subject_id}"


def test_synthetic_professional_email_is_on_the_invalid_tld() -> None:
    subject_id = uuid.uuid4()

    email = synthetic_pilot.synthetic_professional_email(subject_id)

    assert email.endswith("@synthetic.invalid")


# ---------------------------------------------------------------------------
# Provenance — exact, and pinned equal to the persistence-layer spelling
# ---------------------------------------------------------------------------


def test_synthetic_match_provenance_is_exact() -> None:
    assert synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE == "synthetic / coordinator-accepted"


def test_synthetic_match_provenance_matches_the_persisted_vocabulary() -> None:
    """The layering control: two independently spelled literals must agree.

    ``smartmatch_domain`` may not import ``smartmatch_persistence`` (the
    import-linter layering contract forbids it), so
    :data:`synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE` and
    ``smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``
    are two separately hand-typed literals rather than one shared constant.
    A failure here means the domain constant and the database's CHECK
    vocabulary have drifted, and every synthetic write would raise
    ``IntegrityError`` at runtime. Do not delete or weaken this test — it is
    the only thing standing between that drift and a runtime failure.
    """
    from smartmatch_persistence.pipeline import (
        MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        MATCH_PROVENANCE_VALUES,
    )

    assert synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE == MATCH_PROVENANCE_SYNTHETIC_COORDINATOR
    assert synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE in MATCH_PROVENANCE_VALUES


# ---------------------------------------------------------------------------
# Negative — no fabricated score
# ---------------------------------------------------------------------------


def test_module_stores_no_fabricated_score_identifier() -> None:
    offenders = _fabricated_score_identifiers(synthetic_pilot)
    assert not offenders, f"score-shaped identifier(s) found in synthetic_pilot: {offenders}"


# ---------------------------------------------------------------------------
# Attendance method
# ---------------------------------------------------------------------------


def test_synthetic_attendance_method_is_coordinator_entry_not_qr_scan() -> None:
    assert synthetic_pilot.SYNTHETIC_ATTENDANCE_METHOD == "coordinator_entry"
    assert synthetic_pilot.SYNTHETIC_ATTENDANCE_METHOD != "qr_scan"
