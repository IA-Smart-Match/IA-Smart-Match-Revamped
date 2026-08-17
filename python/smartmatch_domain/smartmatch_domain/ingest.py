"""Import validation and normalization.

Ported from Nebiux-Team-IA-West-SmartMatch@bdce024:src/data_loader.py under
migration manifest entry MM-004.

Retained: the column-validation and data-quality-reporting behavior, which was
the genuinely useful part — it caught missing columns and empty datasets before
they reached scoring.

Rejected: everything coupled to reading CSVs off local disk
(``_try_read_csv``, the ``DATA_DIR`` constants, the pandas DataFrame return
type, encoding sniffing). Architecture v1.1 makes PostgreSQL the system of
record; repository-local CSVs are demo persistence, and file parsing belongs in
an adapter, not in the domain. These functions therefore operate on
already-parsed rows and know nothing about where they came from.

Import parsing feeds the quarantine-and-review path (v1.1 §1.5): a validated
import produces review items, not verified records.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "DatasetQuality",
    "QualityFinding",
    "Severity",
    "normalize_header",
    "validate_columns",
]


class Severity(StrEnum):
    """How badly a finding compromises the dataset."""

    #: The dataset cannot be used. Import fails closed.
    ERROR = "error"
    #: The dataset is usable but degraded. Surfaced to the coordinator.
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class QualityFinding:
    """One problem found in an imported dataset."""

    severity: Severity
    code: str
    message: str
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatasetQuality:
    """The outcome of validating one imported dataset.

    Attributes:
        dataset: Logical dataset name, e.g. ``"professionals"``.
        row_count: Number of rows seen.
        findings: Every problem found, in detection order.
    """

    dataset: str
    row_count: int
    findings: tuple[QualityFinding, ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        """Whether the dataset may proceed to review.

        False when any ``ERROR`` finding is present. The legacy loader returned
        a partially-populated DataFrame in this case and let downstream code
        proceed with missing columns; here the import fails closed.
        """
        return not any(f.severity is Severity.ERROR for f in self.findings)

    @property
    def errors(self) -> tuple[QualityFinding, ...]:
        """Only the blocking findings."""
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[QualityFinding, ...]:
        """Only the non-blocking findings."""
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)


def normalize_header(header: str) -> str:
    """Normalize a column header for comparison.

    Case-insensitive, whitespace-collapsed, and punctuation-insensitive, so
    ``"Metro Region"``, ``"metro_region"``, and ``"  Metro-Region "`` are the
    same column. Header text is presentation; it is never an identity.
    """
    lowered = header.strip().lower()
    collapsed = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return "_".join(collapsed.split())


def validate_columns(
    dataset: str,
    rows: Sequence[Mapping[str, object]],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> DatasetQuality:
    """Validate that imported rows carry the expected columns.

    Args:
        dataset: Logical dataset name, used in findings.
        rows: Already-parsed rows. The domain does not read files.
        required: Column names that must be present. Compared after
            :func:`normalize_header`, so import sources may differ in casing and
            punctuation without failing.
        optional: Columns that are recognized but not required. Anything outside
            ``required | optional`` is reported as an unexpected column —
            a warning, not an error, since extra source columns are common and
            harmless once ignored.

    Returns:
        A :class:`DatasetQuality` describing every problem found. Findings
        accumulate; validation never stops at the first error, so a coordinator
        fixing an import sees the whole list at once.
    """
    findings: list[QualityFinding] = []

    if not rows:
        findings.append(
            QualityFinding(
                severity=Severity.ERROR,
                code="empty_dataset",
                message=f"{dataset}: no rows were supplied",
            )
        )
        return DatasetQuality(dataset=dataset, row_count=0, findings=tuple(findings))

    present = {normalize_header(key) for key in rows[0]}
    required_normalized = {normalize_header(name): name for name in required}
    optional_normalized = {normalize_header(name): name for name in optional}

    missing = sorted(
        original for norm, original in required_normalized.items() if norm not in present
    )
    if missing:
        findings.append(
            QualityFinding(
                severity=Severity.ERROR,
                code="missing_required_columns",
                message=f"{dataset}: required columns are absent: {', '.join(missing)}",
                columns=tuple(missing),
            )
        )

    known = set(required_normalized) | set(optional_normalized)
    unexpected = sorted(name for name in present if name not in known)
    if unexpected:
        findings.append(
            QualityFinding(
                severity=Severity.WARNING,
                code="unexpected_columns",
                message=(
                    f"{dataset}: columns present but not part of the import contract "
                    f"and therefore ignored: {', '.join(unexpected)}"
                ),
                columns=tuple(unexpected),
            )
        )

    # A required column that exists but is blank in every row is as unusable as
    # a missing one; the legacy loader reported it as present and healthy.
    for norm, original in required_normalized.items():
        if norm not in present:
            continue
        if all(_is_blank(_get_normalized(row, norm)) for row in rows):
            findings.append(
                QualityFinding(
                    severity=Severity.ERROR,
                    code="required_column_entirely_blank",
                    message=f"{dataset}: required column {original!r} is blank in every row",
                    columns=(original,),
                )
            )

    return DatasetQuality(dataset=dataset, row_count=len(rows), findings=tuple(findings))


def _get_normalized(row: Mapping[str, object], normalized_key: str) -> object:
    """Fetch a value from ``row`` by its normalized column name."""
    for key, value in row.items():
        if normalize_header(key) == normalized_key:
            return value
    return None


def _is_blank(value: object) -> bool:
    """Whether a cell counts as empty.

    The literal strings ``"nan"``, ``"none"``, and ``"null"`` are treated as
    blank: they are what a CSV export of a null field produces, and the legacy
    code scattered ad-hoc ``str(x).lower() == "nan"`` checks to cope. Centralizing
    it means the rule is stated once and tested once.
    """
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null"}
