"""Fixtures shared by every test directory.

Only what more than one directory needs belongs here. Today that is Ann's two
exercise files, parsed once for the whole session: the golden tests, the
vocabulary tests and the seed's integration tests all read the same 300 rows,
and reading them once is the point (CE-SEED).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from smartmatch_domain.exercise.ingest import IngestRefusal, ParsedDataset


@pytest.fixture(scope="session")
def ann_full_dataset() -> ParsedDataset:
    """Ann's full file (``SmartMatch_Student_Body_300.xlsx``), parsed once."""
    # Imported here so collecting a test that never asks for Ann's file does
    # not import the workbook reader.
    from tests.unit.exercise_workbooks import ann_full_parsed

    return ann_full_parsed()


@pytest.fixture(scope="session")
def ann_sample_dataset() -> ParsedDataset | IngestRefusal:
    """Ann's 20-row sample, parsed once; a refusal, by design spec §3's floor."""
    from tests.unit.exercise_workbooks import ann_sample_parsed

    return ann_sample_parsed()


@pytest.fixture(autouse=True)
def _fresh_ranked_list_memo() -> Iterator[None]:
    """Clear the class-load memos (ranked list, before/after) between tests.

    In production a dataset's profiles never change; test fakes reuse one
    dataset id across modules with different profiles, so a kept list would leak.
    Looked up in ``sys.modules`` so tests that never import the API pay nothing.
    """
    for name, memo in (
        ("smartmatch_api.routers.exercise_matching", "_LIST_MEMO"),
        ("smartmatch_api.routers.exercise_results_compare", "_MEMO"),
    ):
        module = sys.modules.get(name)
        if module is not None:
            getattr(module, memo).clear()
    yield
