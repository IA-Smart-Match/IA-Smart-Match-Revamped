"""Unit coverage for the inline-``rows`` shape of ``ImportRequest``.

No database needed: this exercises the pydantic model and the pure
row/byte-bound check directly, which is everything about this change that does
not require a running worker or PostgreSQL. The full path — a live import
actually creating ``review_item`` rows, a dry run creating none, an unusable
dataset failing closed, and cross-tenant/re-drive behaviour — is covered
end-to-end in ``tests/integration/test_import_rows.py``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smartmatch_api.errors import ApiError
from smartmatch_api.routers.imports import (
    MAX_INLINE_ROWS,
    MAX_INLINE_ROWS_BYTES,
    ImportRequest,
    _validate_inline_rows,
)


def test_a_request_may_carry_rows_alone():
    body = ImportRequest(dataset="professionals", rows=[{"full_name": "A. Rivera"}])
    assert body.source_reference is None
    assert body.rows == [{"full_name": "A. Rivera"}]


def test_a_request_may_carry_source_reference_alone():
    body = ImportRequest(dataset="professionals", source_reference="gs://bucket/roster.csv")
    assert body.rows is None
    assert body.source_reference == "gs://bucket/roster.csv"


def test_a_request_may_carry_neither_at_the_pydantic_level():
    """Both fields are optional on the model itself.

    The mutual-exclusivity rule — exactly one, not "at most one" — is enforced
    by ``create_import`` as an explicit ``ApiError`` (400, ``code`` distinct
    from the 422 pydantic would produce), not by the model. That keeps the
    error in the API's own stable envelope and lets ``charge_quota`` run first
    (ADR-0015) before the refusal, which a pydantic-level validator — run
    before the route function is ever called — could not do. This test pins
    the model's permissiveness; ``tests/integration/test_import_rows.py``
    covers the route's refusal of both and neither.
    """
    body = ImportRequest(dataset="professionals")
    assert body.source_reference is None
    assert body.rows is None


def test_an_empty_rows_list_is_distinct_from_no_rows_at_all():
    """``rows=[]`` is a legal, explicit submission — not the same as omitting it.

    It is what makes the empty-dataset failure path reachable through the API
    at all: ``smartmatch_domain.ingest.validate_columns`` treats zero rows as
    an unusable (``empty_dataset``) dataset, and a caller has to be able to
    submit that state on purpose to exercise the fail-closed path.
    """
    body = ImportRequest(dataset="professionals", rows=[])
    assert body.rows == []
    assert body.rows is not None


def test_dataset_is_still_required():
    with pytest.raises(ValidationError):
        ImportRequest(rows=[{"full_name": "A"}])


def test_dry_run_still_defaults_true():
    body = ImportRequest(dataset="professionals", rows=[{"full_name": "A"}])
    assert body.dry_run is True


# ---------------------------------------------------------------------------
# _validate_inline_rows
# ---------------------------------------------------------------------------


def test_rows_within_both_bounds_are_accepted():
    _validate_inline_rows([{"full_name": "A. Rivera"}, {"full_name": "B. Osei"}])


def test_more_than_the_row_count_bound_is_refused():
    rows = [{"full_name": f"person-{i}"} for i in range(MAX_INLINE_ROWS + 1)]

    with pytest.raises(ApiError) as excinfo:
        _validate_inline_rows(rows)

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "import_rows_too_many"


def test_exactly_the_row_count_bound_is_accepted():
    rows = [{"i": i} for i in range(MAX_INLINE_ROWS)]

    _validate_inline_rows(rows)


def test_more_than_the_byte_bound_is_refused_even_with_few_rows():
    """Row count alone does not bound this — a handful of huge rows must too."""
    huge_value = "x" * (MAX_INLINE_ROWS_BYTES + 1)
    rows = [{"note": huge_value}]

    with pytest.raises(ApiError) as excinfo:
        _validate_inline_rows(rows)

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "import_rows_too_large"


def test_the_row_count_bound_is_checked_before_the_byte_bound():
    """Both a huge row count and a huge byte size: the cheap check fires first.

    Distinguishes the two failure codes rather than merely asserting *an*
    ``ApiError`` — if the byte check ran first here (paying to serialize
    ``MAX_INLINE_ROWS + 1`` oversized rows) the more expensive check would have
    done needless work before the cheap one ever got a chance to short-circuit.
    """
    huge_value = "x" * 1000
    rows = [{"note": huge_value} for _ in range(MAX_INLINE_ROWS + 1)]

    with pytest.raises(ApiError) as excinfo:
        _validate_inline_rows(rows)

    assert excinfo.value.code == "import_rows_too_many"
