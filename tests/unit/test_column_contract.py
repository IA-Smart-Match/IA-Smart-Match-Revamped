"""The ratified column contract is read, validated, and refused — not guessed.

P9 card W1 wires ``docs/pilot-data/columns.yaml`` into worker import
validation. These tests hold that wiring to three promises: the shipped file
parses into what the handler needs, a broken file refuses instead of
degrading, and a still-open ``open_questions`` column is neither enforced as
ratified nor silently ignored.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from smartmatch_worker.column_contract import (
    ColumnContractError,
    default_contract_path,
    load_column_contract,
)


@pytest.fixture(scope="module")
def shipped() -> dict:
    """The real contract, loaded from the repository checkout."""
    return dict(load_column_contract(default_contract_path()))


class TestShippedContract:
    """The file this repository actually ships is the one the worker can use."""

    def test_the_default_path_resolves_to_the_ratified_file(self) -> None:
        path = default_contract_path()
        assert path.name == "columns.yaml"
        assert path.parent.name == "pilot-data"
        assert path.is_file(), f"the ratified contract is missing at {path}"

    def test_both_ratified_datasets_are_declared(self, shipped: dict) -> None:
        assert set(shipped) == {"professionals", "events"}

    def test_professionals_requires_the_ratified_name_column(self, shipped: dict) -> None:
        """Ratification chose ``name`` over ``full_name``; the wiring must agree.

        ``tests/unit/test_ingest.py`` spells the column ``full_name`` as an
        illustrative example. If that spelling ever leaked into the contract,
        every real coordinator export would fail its required-column check for
        a reason nobody wrote down.
        """
        assert shipped["professionals"].required == ("name", "metro_region")
        assert "full_name" not in shipped["professionals"].optional

    def test_per_column_sentinels_survive_the_yaml_anchor(self, shipped: dict) -> None:
        """``*null_markers`` is a YAML anchor; it must arrive as real values."""
        professionals = shipped["professionals"]
        assert professionals.blank_sentinels == ()
        assert professionals.blank_sentinels_by_column["metro_region"] == (
            "NULL",
            "nan",
            "N/A",
        )
        # Empty on purpose: "Null" is a real surname.
        assert professionals.blank_sentinels_by_column["name"] == ()

    def test_public_url_is_declared_url_shaped(self, shipped: dict) -> None:
        """P9 pilot columns V2: the only URL-shaped column declared today."""
        assert shipped["events"].url_shaped_columns == ("Public URL",)
        assert shipped["professionals"].url_shaped_columns == ()


class TestGatePosture:
    """A still-open question is declared, not enforced and not forgotten."""

    def test_board_role_is_no_longer_in_the_professionals_contract(self, shipped: dict) -> None:
        """P9 Gate A closed 2026-09-02, relationship-scoped — not a flat column.

        ``board_role`` used to be ``accept``-postured gate_pending on
        ``professionals`` while Gate A was open. The gate closed deciding the
        column belongs on ``professional_unit_relationship`` instead
        (composite ``(tenant_id, professional_id, unit_id)`` key, no
        effective-date columns for the pilot), so it is removed from this
        dataset entirely — not merely re-postured.
        """
        professionals = shipped["professionals"]
        assert "board_role" not in professionals.optional
        assert "board_role" not in professionals.required
        assert professionals.accepted_pending_columns == ()
        assert professionals.gate_pending == ()

    def test_gate_b_fields_are_no_longer_withheld_after_gate_close(self, shipped: dict) -> None:
        """P9 Gate B closed 2026-09-02 — events carry no gate_pending withhold."""
        events = shipped["events"]
        assert events.withheld_columns == ()
        assert events.gate_pending == ()

    def test_no_dataset_has_a_gate_pending_column_today(self, shipped: dict) -> None:
        """Both gates this file ever named (A and B) are closed.

        The mechanism (``gate_pending``, ``accepted_pending_columns``,
        ``withheld_columns``) stays fully general for the next column a gate
        has not yet answered; today, nothing exercises it.
        """
        for contract in shipped.values():
            assert contract.gate_pending == ()
            assert contract.accepted_pending_columns == ()
            assert contract.withheld_columns == ()

    def test_gate_pending_columns_stay_declared_so_they_are_never_unexpected(
        self, shipped: dict
    ) -> None:
        """Withholding a value must not turn its column into an unexpected one.

        A column dropped from ``optional`` would be reported as unexpected,
        which reads as "you sent something wrong" rather than "we are not
        storing this yet".
        """
        for contract in shipped.values():
            for entry in contract.gate_pending:
                assert entry.column in contract.optional


class TestRefusal:
    """A contract that cannot be trusted refuses; it never degrades quietly."""

    def test_a_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ColumnContractError, match="could not be read"):
            load_column_contract(tmp_path / "absent.yaml")

    def test_a_file_without_datasets_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "columns.yaml"
        path.write_text("something_else: {}\n", encoding="utf-8")
        with pytest.raises(ColumnContractError, match="declares no 'datasets' mapping"):
            load_column_contract(path)

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "columns.yaml"
        path.write_text("datasets: [unclosed\n", encoding="utf-8")
        with pytest.raises(ColumnContractError, match="not valid YAML"):
            load_column_contract(path)

    def test_a_gate_pending_column_nobody_declared_raises(self, tmp_path: Path) -> None:
        """A posture on an undeclared column applies to nothing — a typo."""
        path = tmp_path / "columns.yaml"
        path.write_text(
            "datasets:\n"
            "  professionals:\n"
            "    required: [name]\n"
            "    optional: []\n"
            "    gate_pending:\n"
            "      board_role:\n"
            "        gate: P9 Gate A\n"
            "        posture: accept\n",
            encoding="utf-8",
        )
        with pytest.raises(ColumnContractError, match="in neither 'required' nor 'optional'"):
            load_column_contract(path)

    def test_an_unknown_posture_raises(self, tmp_path: Path) -> None:
        """``reject`` is not a posture. A gate that has not answered cannot refuse."""
        path = tmp_path / "columns.yaml"
        path.write_text(
            "datasets:\n"
            "  events:\n"
            "    required: []\n"
            "    optional: ['Public URL']\n"
            "    gate_pending:\n"
            "      'Public URL':\n"
            "        gate: P9 Gate B\n"
            "        posture: reject\n",
            encoding="utf-8",
        )
        with pytest.raises(ColumnContractError, match="expected one of"):
            load_column_contract(path)

    def test_a_gate_pending_entry_without_a_gate_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "columns.yaml"
        path.write_text(
            "datasets:\n"
            "  events:\n"
            "    required: []\n"
            "    optional: ['Public URL']\n"
            "    gate_pending:\n"
            "      'Public URL':\n"
            "        posture: withhold\n",
            encoding="utf-8",
        )
        with pytest.raises(ColumnContractError, match="names no gate"):
            load_column_contract(path)

    def test_a_scalar_where_a_list_belongs_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "columns.yaml"
        path.write_text(
            "datasets:\n  professionals:\n    required: name\n",
            encoding="utf-8",
        )
        with pytest.raises(ColumnContractError, match="must be a list"):
            load_column_contract(path)

    def test_a_url_shaped_column_nobody_declared_raises(self, tmp_path: Path) -> None:
        """A url_shaped_columns entry outside required/optional applies to nothing."""
        path = tmp_path / "columns.yaml"
        path.write_text(
            "datasets:\n"
            "  events:\n"
            "    required: []\n"
            "    optional: ['Category']\n"
            "    url_shaped_columns: ['Public URL']\n",
            encoding="utf-8",
        )
        with pytest.raises(ColumnContractError, match="in neither 'required' nor 'optional'"):
            load_column_contract(path)
