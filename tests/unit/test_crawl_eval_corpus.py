"""Offline MP-1..5 evaluation corpus for the crawler (g3-crawler-decision section 7).

Runs every fixture in `tests/fixtures/crawl_eval/` through the existing
fixture-ingest seam and scores it against `manifest.json`. No network: the
modules involved are import-checked and `socket.socket` raises during the run.
Cases whose seam does not exist yet are strict xfails, so building the seam
flips them loudly. Live crawl stays gated on T-07/T-13.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import socket
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from smartmatch_domain.event_candidate import CandidateRefusal
from smartmatch_domain.events import TagVocabulary
from smartmatch_providers.fixture_ingest import IngestReport, ingest_fixture_file

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "crawl_eval"
CASES: list[dict[str, Any]] = json.loads((ROOT / "manifest.json").read_text())["cases"]
VOCAB = TagVocabulary(version="v0-eval", terms=frozenset({"careers"}))
CATEGORY_FLOORS = {
    "flyer_unknown": 1.0,
    "ambiguous_date": 1.0,
    "out_of_scope": 1.0,
    "injection": 1.0,
    "subdivision_200": 1.0,
}
WHOLE_SET_FLOOR = 0.9


def _ics_200() -> str:
    events = "".join(
        f"BEGIN:VEVENT\nUID:eval-{i}@example.edu\nDTSTART;TZID=America/Los_Angeles:"
        f"20261102T{i % 24:02d}0000\nSUMMARY:Synthetic Session {i}\nEND:VEVENT\n"
        for i in range(200)
    )
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Synthetic Eval//EN\n{events}END:VCALENDAR\n"


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, IngestReport]:
    """Ingest every case once, with the network made unreachable."""
    generated = tmp_path_factory.mktemp("subdivision") / "subdivision_200.ics"
    generated.write_text(_ics_200(), encoding="utf-8")
    real_socket = socket.socket

    def _no_network(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted during crawl eval")

    socket.socket = _no_network  # type: ignore[misc,assignment]
    try:
        out: dict[str, IngestReport] = {}
        for case in CASES:
            root, name = (
                (generated.parent, generated.name)
                if case["file"] == "@generated"
                else (ROOT, case["file"])
            )
            out[case["id"]] = ingest_fixture_file(
                name,
                root=root,
                source_time_zone="America/Los_Angeles",
                host_org_unit="synthetic-university",
                vocabulary=VOCAB,
            )
        return out
    finally:
        socket.socket = real_socket  # type: ignore[misc]


def _passes(case: dict[str, Any], report: IngestReport) -> bool:
    expect = case["expect"]
    kind = expect["kind"]
    if kind == "refused":
        return isinstance(report.outcome, CandidateRefusal)
    if isinstance(report.outcome, CandidateRefusal):
        return False
    events = report.events
    if kind == "no_events":
        return events == ()
    if kind == "unresolved":
        return bool(events) and all(
            type(e.candidate.event_time).__name__ == "UnresolvedTime" and e.identity_key is None
            for e in events
        )
    if kind == "inert":
        # Hostile text is data: carried verbatim, never obeyed (time not overridden).
        return len(events) == 1 and (
            events[0].candidate.title == expect["title"]
            and type(events[0].candidate.event_time).__name__ == expect["time"]
        )
    if kind == "no_contact":
        return not any(token in repr(report) for token in expect["forbidden"])
    if kind == "hosts":
        urls = [e.candidate.source_url for e in events if e.candidate.source_url]
        return all(urlparse(u).hostname in expect["allowed"] for u in urls)
    if kind == "reports_incomplete":
        return getattr(report, "complete", True) is False
    if kind == "count_unique":
        keys = {e.identity_key for e in events}
        return len(events) == expect["count"] and None not in keys and len(keys) == expect["count"]
    raise AssertionError(f"unknown expectation kind {kind!r}")


def _param(case: dict[str, Any]) -> Any:
    marks = [pytest.mark.xfail(strict=True, reason=case["xfail"])] if case.get("xfail") else []
    return pytest.param(case, id=case["id"], marks=marks)


@pytest.mark.parametrize("case", [_param(c) for c in CASES])
def test_case(case: dict[str, Any], reports: dict[str, IngestReport]) -> None:
    assert _passes(case, reports[case["id"]])


def test_category_and_whole_set_floors(reports: dict[str, IngestReport]) -> None:
    """Cases awaiting an unbuilt seam (xfail) are excluded until it exists."""
    by_cat: dict[str, list[bool]] = defaultdict(list)
    for case in CASES:
        if not case.get("xfail"):
            by_cat[case["category"]].append(_passes(case, reports[case["id"]]))
    for category, floor in CATEGORY_FLOORS.items():
        results = by_cat[category]
        assert results, f"no scored fixtures for floor category {category}"
        assert sum(results) / len(results) >= floor, category
    flat = [r for results in by_cat.values() for r in results]
    assert sum(flat) / len(flat) >= WHOLE_SET_FLOOR


def test_manifest_covers_every_fixture_and_mp_rule() -> None:
    on_disk = {
        p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.suffix in {".ics", ".jsonld"}
    }
    listed = {c["file"] for c in CASES} - {"@generated"}
    assert on_disk == listed
    assert {mp for c in CASES for mp in c["mp"]} >= {f"MP-{n}" for n in range(1, 6)}


@pytest.mark.parametrize(
    "module",
    [
        "smartmatch_providers.fixture_ingest",
        "smartmatch_domain.event_candidate",
        "smartmatch_domain.ical_parser",
        "smartmatch_domain.jsonld_parser",
    ],
)
def test_no_network_imports_in_seams(module: str) -> None:
    spec = importlib.util.find_spec(module)
    assert spec is not None and spec.origin is not None
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    roots = {
        (a.name if isinstance(n, ast.Import) else n.module or "").split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not roots & {"socket", "http", "urllib", "httpx", "requests", "aiohttp", "subprocess"}


def test_harness_itself_imports_no_http_client() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    names = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    } | {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert not names & {"httpx", "requests", "aiohttp", "http", "subprocess"}
