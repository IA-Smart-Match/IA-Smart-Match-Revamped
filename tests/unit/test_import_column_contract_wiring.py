"""The import handler enforces the ratified contract (P9 card W1).

No database and no running worker: this exercises the handler's contract
helpers directly, which is everything about the wiring that does not need
PostgreSQL. The full path — a live import writing ``review_item`` rows with a
withheld column absent from ``row_data`` — is covered in
``tests/integration/test_import_rows.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from smartmatch_worker.column_contract import default_contract_path, load_column_contract
from smartmatch_worker.handlers import (
    PolicyFailure,
    _dataset_contract,
    _gate_pending_findings,
    _normalize_row,
)


@pytest.fixture(scope="module")
def professionals():
    return load_column_contract(default_contract_path())["professionals"]


@pytest.fixture(scope="module")
def events():
    return load_column_contract(default_contract_path())["events"]


class TestDatasetLookup:
    """Both refusals are terminal, and neither degrades to validating nothing."""

    def test_a_declared_dataset_resolves(self) -> None:
        assert _dataset_contract("professionals").required == ("name", "metro_region")

    def test_an_undeclared_dataset_is_refused_terminally(self) -> None:
        with pytest.raises(PolicyFailure) as caught:
            _dataset_contract("rosters")
        assert caught.value.reason == "dataset_contract_unknown"
        # The message names what *is* declared, so a coordinator can correct it.
        assert "professionals" in str(caught.value)

    def test_an_unreadable_contract_refuses_rather_than_validating_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The failure direction is a refused import, never a permissive one."""
        import smartmatch_worker.handlers as handlers

        def explode() -> dict:
            from smartmatch_worker.column_contract import load_column_contract as loader

            return dict(loader(tmp_path / "absent.yaml"))

        monkeypatch.setattr(handlers, "get_column_contract", explode)
        with pytest.raises(PolicyFailure) as caught:
            _dataset_contract("professionals")
        assert caught.value.reason == "column_contract_unavailable"


class TestGatePendingFindings:
    """A gate-pending column is warned about — never rejected, never silent."""

    def test_no_findings_when_the_submission_carries_no_gate_pending_column(
        self, professionals
    ) -> None:
        rows = [{"name": "A. Rivera", "metro_region": "Inland Empire"}]
        assert _gate_pending_findings(professionals, rows) == ()

    def test_board_role_is_reported_as_accepted_and_stored(self, professionals) -> None:
        rows = [{"name": "A. Rivera", "metro_region": "Coastal", "board_role": "Chair"}]
        (finding,) = _gate_pending_findings(professionals, rows)
        assert finding.code == "columns_pending_gate"
        assert finding.severity == "warning"
        assert finding.columns == ("board_role",)
        assert "P9 Gate A" in finding.message

    def test_gate_b_contact_fields_are_stored_when_gate_is_closed(self, events) -> None:
        rows = [
            {
                "Event / Program": "Career Day",
                "Category": "Outreach",
                "Public URL": "https://example.edu/career-day",
                "Contact Email / Phone (published)": "nobody@example.edu",
            }
        ]
        assert _gate_pending_findings(events, rows) == ()

    def test_a_gate_finding_never_carries_error_severity(self, events, professionals) -> None:
        """A gate that has not answered cannot make a dataset unusable.

        ``is_usable`` is the domain's verdict on the *ratified* contract. If a
        gate finding could be an ERROR, an open question would fail imports —
        which is enforcing an answer the gate has not given.
        """
        rows = [{"board_role": "Chair"}]
        for contract in (events, professionals):
            for finding in _gate_pending_findings(contract, rows):
                assert finding.severity == "warning"

    def test_public_url_normalizes_without_gate_withhold(self, events) -> None:
        """``"Public URL"`` and ``public_url`` normalize the same after Gate B close."""
        normalized = _normalize_row({"public_url": "https://example.edu/x"})
        assert normalized == {"public_url": "https://example.edu/x"}


class TestWithholding:
    """Withheld values are dropped at the write, and only at the write."""

    def test_gate_b_contact_fields_persist_after_gate_close(self, events) -> None:
        row = {
            "Event / Program": "Career Day",
            "Category": "Outreach",
            "Public URL": "https://example.edu/career-day",
            "Point(s) of Contact (published)": "R. Vance",
            "Contact Email / Phone (published)": "nobody@example.edu",
        }
        normalized = _normalize_row(row, withhold=events.withheld_columns)
        assert normalized["public_url"] == "https://example.edu/career-day"
        assert normalized["point_s_of_contact_published"] == "R. Vance"
        assert normalized["contact_email_phone_published"] == "nobody@example.edu"

    def test_an_accepted_gate_pending_column_is_still_stored(self, professionals) -> None:
        """Gate A is a modelling question, not a privacy one — keep the value."""
        row = {"name": "A. Rivera", "metro_region": "Coastal", "board_role": "Chair"}
        normalized = _normalize_row(row, withhold=professionals.withheld_columns)
        assert normalized["board_role"] == "Chair"

    def test_withholding_still_applies_when_a_column_is_declared_withhold(self) -> None:
        normalized = _normalize_row(
            {"category": "Outreach", "  public-url ": "https://example.edu/x"},
            withhold=("Public URL",),
        )
        assert normalized == {"category": "Outreach"}

    def test_no_withholding_by_default(self) -> None:
        """The default is unchanged behaviour, so nothing drops by accident."""
        assert _normalize_row({"Public URL": "https://example.edu/x"}) == {
            "public_url": "https://example.edu/x"
        }
