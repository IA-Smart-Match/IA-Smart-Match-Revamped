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
from smartmatch_worker.column_contract import (
    DatasetColumnContract,
    GatePendingColumn,
    default_contract_path,
    load_column_contract,
)
from smartmatch_worker.handlers import (
    PolicyFailure,
    _dataset_contract,
    _gate_pending_findings,
    _normalize_row,
    _url_shape_findings,
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

    def test_board_role_produces_no_gate_finding_now_that_gate_a_is_closed(
        self, professionals
    ) -> None:
        """P9 Gate A closed 2026-09-02: board_role is not gate_pending any more.

        It is not part of the ``professionals`` contract at all now (it is
        relationship-scoped, on ``professional_unit_relationship``), so a
        submission that still sends it produces no ``columns_pending_gate``
        finding here — ``_gate_pending_findings`` only fires for columns the
        contract actually declares as gate_pending, and none are declared.
        Whether an unrecognized ``board_role`` key is itself worth a finding
        is ``validate_columns``'s ``unexpected_columns`` concern, not this
        function's.
        """
        rows = [{"name": "A. Rivera", "metro_region": "Coastal", "board_role": "Chair"}]
        assert _gate_pending_findings(professionals, rows) == ()

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

    def test_a_gate_finding_never_carries_error_severity(self) -> None:
        """A gate that has not answered cannot make a dataset unusable.

        ``is_usable`` is the domain's verdict on the *ratified* contract. If a
        gate finding could be an ERROR, an open question would fail imports —
        which is enforcing an answer the gate has not given.

        Both real gates (A and B) are closed today, so the shipped contract
        has no ``gate_pending`` entry left to exercise this against — see
        ``test_no_dataset_has_a_gate_pending_column_today`` in
        ``test_column_contract.py``. This constructs a synthetic contract with
        one, the same way a future column behind a new gate would arrive, so
        the WARNING-only invariant stays covered rather than going untested
        the moment a real example no longer exists.
        """
        contract = DatasetColumnContract(
            dataset="professionals",
            required=(),
            optional=("board_role",),
            blank_sentinels=(),
            blank_sentinels_by_column={},
            gate_pending=(
                GatePendingColumn(
                    column="board_role",
                    gate="Some Future Gate",
                    posture="accept",
                    reason="synthetic, for this test only",
                ),
            ),
        )
        rows = [{"board_role": "Chair"}]
        findings = _gate_pending_findings(contract, rows)
        assert findings, "expected the synthetic gate_pending entry to produce a finding"
        for finding in findings:
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

    def test_an_undeclared_column_is_not_dropped_by_normalize_row(self, professionals) -> None:
        """``_normalize_row`` only drops what ``withhold`` names — nothing else.

        ``board_role`` is no longer part of the professionals contract at all
        (P9 Gate A closed relationship-scoped), so ``professionals.optional``
        no longer contains it and it is not in ``withheld_columns`` either.
        ``_normalize_row`` does not consult the contract's declared columns —
        only its ``withhold`` parameter — so an undeclared key still survives
        normalization exactly as a declared one would. Whether it belongs in
        the submission at all is ``validate_columns``'s ``unexpected_columns``
        concern, not this function's.
        """
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


class TestUrlShapeFindings:
    """P9 pilot columns V2: a URL-shaped column is checked, never rejected or dropped."""

    def test_no_findings_for_a_shape_valid_url(self, events) -> None:
        rows = [
            {
                "Event / Program": "Career Day",
                "Category": "Outreach",
                "Public URL": "https://example.edu/career-day",
            }
        ]
        assert _url_shape_findings(events, rows) == ()

    def test_a_shape_invalid_url_is_a_warning_naming_the_column(self, events) -> None:
        rows = [
            {
                "Event / Program": "Career Day",
                "Category": "Outreach",
                "Public URL": "http://example.edu/career-day",
            }
        ]
        (finding,) = _url_shape_findings(events, rows)
        assert finding.code == "url_shape_invalid"
        assert finding.severity == "warning"
        assert finding.columns == ("Public URL",)
        assert "scheme_not_https" in finding.message

    def test_blank_and_absent_values_are_not_failures(self, events) -> None:
        rows = [
            {"Event / Program": "A", "Category": "Outreach", "Public URL": ""},
            {"Event / Program": "B", "Category": "Outreach"},
        ]
        assert _url_shape_findings(events, rows) == ()

    def test_a_non_string_value_is_skipped_rather_than_raising(self, events) -> None:
        """A submitter's stray number where a URL belongs must not crash the import."""
        rows = [{"Event / Program": "A", "Category": "Outreach", "Public URL": 12345}]
        assert _url_shape_findings(events, rows) == ()

    def test_column_names_normalize_the_same_way_validate_columns_does(self, events) -> None:
        rows = [{"event_program": "A", "category": "Outreach", "public_url": "not a url"}]
        (finding,) = _url_shape_findings(events, rows)
        assert finding.columns == ("Public URL",)

    def test_no_findings_when_the_contract_declares_no_url_shaped_column(
        self, professionals
    ) -> None:
        rows = [{"name": "A. Rivera", "metro_region": "Coastal"}]
        assert _url_shape_findings(professionals, rows) == ()

    def test_multiple_invalid_rows_are_aggregated_into_one_finding_per_column(self, events) -> None:
        """One reviewable finding per column, not one per offending row.

        A per-row finding for every bad URL in a large export would be noise
        that trains a coordinator to skim; the aggregate names how many rows
        and which rules failed instead.
        """
        rows = [
            {"Event / Program": "A", "Category": "Outreach", "Public URL": "http://x.edu/a"},
            {"Event / Program": "B", "Category": "Outreach", "Public URL": "http://x.edu/b"},
            {"Event / Program": "C", "Category": "Outreach", "Public URL": "https://x.edu/c?q=1"},
        ]
        findings = _url_shape_findings(events, rows)
        assert len(findings) == 1
        (finding,) = findings
        assert "3 row(s)" in finding.message
        assert "scheme_not_https" in finding.message
        assert "query_present" in finding.message

    def test_the_invalid_value_itself_is_not_dropped_by_normalize_row(self) -> None:
        """A shape-invalid URL is a finding, never a silent drop from storage.

        ``_url_shape_findings`` only reports; it does not touch ``withhold``.
        ``_normalize_row`` still carries the raw value through untouched
        unless a column is explicitly named in ``withhold``, which a
        shape-invalid URL never is on its own.
        """
        row = {"Category": "Outreach", "Public URL": "http://example.edu/x"}
        normalized = _normalize_row(row, withhold=())
        assert normalized["public_url"] == "http://example.edu/x"
