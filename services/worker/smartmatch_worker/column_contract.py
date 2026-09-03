"""Load the ratified pilot column contract for import validation (P9 card W1).

`docs/pilot-data/columns.yaml` was ratified on 28 August 2026 and then sat
unread by application code: ``handlers.py`` called
``smartmatch_domain.ingest.validate_columns`` with ``required=()`` and
``optional=()``, so the contract constrained fixtures and nothing else. This
module is the adapter that ends that gap. It lives in the worker, not the
domain, because reading a file needs ``pathlib`` and ``yaml`` — both forbidden
inside ``smartmatch_domain`` by the import-linter contract in
``pyproject.toml``, which is exactly the separation that keeps import
validation testable without a filesystem.

**The YAML is the single source of truth.** No column name is written out
again here. A change to the contract is a change to that file; this module
only reads it, and refuses rather than guessing when it cannot.

Gate posture
------------
`columns.yaml` carries two ratified sections. Both of its originally
still-open questions (`open_questions`) — P9 Gate A's ``board_role`` and P9
Gate B's three published contact fields — closed 2 Sep 2026, so no column is
gate-pending today. Card W1's partial-ratification rule remains in force for
whatever comes next: enforcement is *section-level*, W1 "must not treat a
still-open ``open_questions`` entry as ratified contract", and a column still
behind a gate would be declared under its dataset's ``gate_pending`` map, with
the gate that owns it and one of two postures:

``accept``
    The column is recognized (never reported as unexpected), persisted
    normally, and reported in a ``columns_pending_gate`` **warning** so a
    coordinator sees that its meaning is not settled. Used where the open
    question is about *modelling* — P9 Gate A's ``board_role`` was this
    posture's first and, so far, only example, while the gate was open:
    whether it belonged on a professional or on a unit relationship was
    undecided, so nothing was lost by persisting it flat meanwhile. The gate
    closed relationship-scoped; ``board_role`` is no longer a
    ``professionals`` column, and now lives on
    ``professional_unit_relationship``
    (``python/smartmatch_persistence/smartmatch_persistence/schema.py``).

``withhold``
    The column is recognized, but its values are **dropped before anything is
    written**, and the drop is reported in a ``columns_withheld_pending_gate``
    warning naming every column withheld. Used for P9 Gate B's published
    contact fields while that gate was open, because the question was
    *privacy*: quarantine is collection, and a review item is persistence.
    Accepting the import while declining to store those values was the only
    posture that neither fabricated an authorization nor threw away the rest
    of a coordinator's submission. Gate B has since closed collecting all
    three; they are ordinary ratified ``events`` columns now.

Neither posture rejects. A gate-pending column never makes a dataset unusable —
that would be enforcing an answer the gate has not given either.

Refusal, not silence
--------------------
A missing, unreadable, or malformed contract file raises
:class:`ColumnContractError`, which the handler turns into a terminal
``column_contract_unavailable`` policy failure. Falling back to the old
unconstrained call would be worse than failing: an import would appear to
validate against a contract that was never read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml  # type: ignore[import-untyped]

__all__ = [
    "ColumnContractError",
    "DatasetColumnContract",
    "GatePendingColumn",
    "default_contract_path",
    "get_column_contract",
    "load_column_contract",
]


#: Postures a ``gate_pending`` column may declare. See the module docstring.
_POSTURES: Final = frozenset({"accept", "withhold"})


class ColumnContractError(RuntimeError):
    """The ratified column contract could not be read or does not parse.

    Deliberately not a subclass of anything the handler catches by accident.
    The caller decides what refusing looks like in its own vocabulary; this
    module's job is to be unambiguous that no contract is in hand.
    """


@dataclass(frozen=True, slots=True)
class GatePendingColumn:
    """One column that ``columns.yaml`` declares as still behind a gate."""

    #: Column name, spelled exactly as the contract spells it.
    column: str
    #: Human-readable gate identifier, e.g. ``"P9 Gate B"``.
    gate: str
    #: ``"accept"`` or ``"withhold"`` — see the module docstring.
    posture: str
    #: Why the gate has not answered, copied from the contract.
    reason: str


@dataclass(frozen=True, slots=True)
class DatasetColumnContract:
    """The ratified contract for one dataset, ready to hand to the domain."""

    dataset: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    blank_sentinels: tuple[str, ...]
    blank_sentinels_by_column: Mapping[str, tuple[str, ...]]
    gate_pending: tuple[GatePendingColumn, ...]
    #: Columns whose values `smartmatch_worker.handlers` validates with
    #: `smartmatch_domain.public_url.validate_static_url_shape` before an
    #: import writes them (P9 pilot columns V2). Declared per dataset, the
    #: same reasoning `blank_sentinels_by_column` already uses: a column is
    #: checked only where it is declared to hold a URL, never inferred from
    #: its name. A shape failure is reported as a `url_shape_invalid`
    #: WARNING finding, never a rejection and never a silent drop.
    url_shaped_columns: tuple[str, ...] = ()

    @property
    def withheld_columns(self) -> tuple[str, ...]:
        """Columns whose values must not be persisted while their gate is open."""
        return tuple(entry.column for entry in self.gate_pending if entry.posture == "withhold")

    @property
    def accepted_pending_columns(self) -> tuple[str, ...]:
        """Gate-pending columns that are persisted but flagged for review."""
        return tuple(entry.column for entry in self.gate_pending if entry.posture == "accept")


def default_contract_path() -> Path:
    """Locate ``columns.yaml`` relative to this file's checkout.

    Four parents up from ``services/worker/smartmatch_worker/`` is the
    repository root. A deployed image has no repository, which is why
    ``Dockerfile.worker`` copies the file in and sets
    ``SMARTMATCH_COLUMN_CONTRACT_PATH`` explicitly rather than relying on this.
    """
    return Path(__file__).resolve().parents[3] / "docs" / "pilot-data" / "columns.yaml"


def load_column_contract(path: Path) -> Mapping[str, DatasetColumnContract]:
    """Read and validate the contract file at ``path``.

    Raises:
        ColumnContractError: if the file is absent, unreadable, not a mapping,
            carries no ``datasets``, or declares a ``gate_pending`` entry that
            is malformed or names a column the dataset does not list.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ColumnContractError(f"column contract could not be read at {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ColumnContractError(f"column contract at {path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, Mapping) or not isinstance(raw.get("datasets"), Mapping):
        raise ColumnContractError(f"column contract at {path} declares no 'datasets' mapping")

    return {
        str(name): _build_dataset(str(name), declared, path)
        for name, declared in raw["datasets"].items()
    }


def _build_dataset(dataset: str, declared: Any, path: Path) -> DatasetColumnContract:
    """Turn one raw ``datasets`` entry into a validated contract."""
    if not isinstance(declared, Mapping):
        raise ColumnContractError(f"{path}: dataset {dataset!r} is not a mapping")

    required = _string_tuple(declared.get("required", ()), dataset, "required", path)
    optional = _string_tuple(declared.get("optional", ()), dataset, "optional", path)
    sentinels = _string_tuple(declared.get("blank_sentinels", ()), dataset, "blank_sentinels", path)

    by_column_raw = declared.get("blank_sentinels_by_column") or {}
    if not isinstance(by_column_raw, Mapping):
        raise ColumnContractError(
            f"{path}: dataset {dataset!r} blank_sentinels_by_column is not a mapping"
        )
    by_column = {
        str(column): _string_tuple(values, dataset, f"blank_sentinels_by_column[{column}]", path)
        for column, values in by_column_raw.items()
    }

    gate_pending = _build_gate_pending(
        declared.get("gate_pending") or {}, dataset, required + optional, path
    )
    url_shaped_columns = _string_tuple(
        declared.get("url_shaped_columns", ()), dataset, "url_shaped_columns", path
    )
    declared_columns = required + optional
    for column in url_shaped_columns:
        if column not in declared_columns:
            raise ColumnContractError(
                f"{path}: dataset {dataset!r} declares url_shaped_columns "
                f"{column!r}, which is in neither 'required' nor 'optional'"
            )

    return DatasetColumnContract(
        dataset=dataset,
        required=required,
        optional=optional,
        blank_sentinels=sentinels,
        blank_sentinels_by_column=by_column,
        gate_pending=gate_pending,
        url_shaped_columns=url_shaped_columns,
    )


def _build_gate_pending(
    raw: Any, dataset: str, declared_columns: tuple[str, ...], path: Path
) -> tuple[GatePendingColumn, ...]:
    """Validate a dataset's ``gate_pending`` map.

    A gate-pending column that the dataset does not otherwise declare is a
    contract typo of the same kind ``validate_columns`` already raises on: the
    posture would silently apply to nothing.
    """
    if not isinstance(raw, Mapping):
        raise ColumnContractError(f"{path}: dataset {dataset!r} gate_pending is not a mapping")

    entries: list[GatePendingColumn] = []
    for column, spec in raw.items():
        name = str(column)
        if name not in declared_columns:
            raise ColumnContractError(
                f"{path}: dataset {dataset!r} declares gate_pending column {name!r}, "
                "which is in neither 'required' nor 'optional'"
            )
        if not isinstance(spec, Mapping):
            raise ColumnContractError(
                f"{path}: dataset {dataset!r} gate_pending[{name!r}] is not a mapping"
            )
        posture = str(spec.get("posture", ""))
        if posture not in _POSTURES:
            raise ColumnContractError(
                f"{path}: dataset {dataset!r} gate_pending[{name!r}] declares posture "
                f"{posture!r}; expected one of {sorted(_POSTURES)}"
            )
        gate = str(spec.get("gate", "")).strip()
        if not gate:
            raise ColumnContractError(
                f"{path}: dataset {dataset!r} gate_pending[{name!r}] names no gate"
            )
        entries.append(
            GatePendingColumn(
                column=name,
                gate=gate,
                posture=posture,
                reason=str(spec.get("reason", "")).strip(),
            )
        )
    return tuple(entries)


def _string_tuple(value: Any, dataset: str, field: str, path: Path) -> tuple[str, ...]:
    """Coerce a declared list of column names or sentinels to a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ColumnContractError(
            f"{path}: dataset {dataset!r} field {field} must be a list, got {type(value).__name__}"
        )
    return tuple(str(item) for item in value)


@lru_cache(maxsize=1)
def get_column_contract() -> Mapping[str, DatasetColumnContract]:
    """Return the process-wide contract, read once.

    Cached because the contract is a shipped artifact, not configuration that
    changes under a running worker. Tests that need a different contract call
    :func:`load_column_contract` directly rather than clearing this cache.
    """
    from smartmatch_worker.config import get_settings

    configured = get_settings().column_contract_path
    path = Path(configured) if configured else default_contract_path()
    return load_column_contract(path)
