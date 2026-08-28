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

from collections.abc import Iterable, Mapping, Sequence, Set
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
    blank_sentinels: Iterable[str] = (),
    blank_sentinels_by_column: Mapping[str, Iterable[str]] | None = None,
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
        blank_sentinels: Source-specific tokens that stand for "no value" in
            this import, e.g. ``("nan", "NULL")`` for an export that writes them
            for empty fields. Empty by default: only ``None`` and whitespace are
            blank on their own, because ``"Null"`` and ``"None"`` are real
            surnames and place names, and this module cannot tell a marker from
            a value. The adapter that parsed the rows can, and declares it here.
            Compared case-insensitively against the stripped cell text.
            Applies to every column that ``blank_sentinels_by_column`` does not
            name.
        blank_sentinels_by_column: Sentinels for named columns, overriding
            ``blank_sentinels`` for exactly those columns. A token is a
            placeholder in one column and a value in the next, and one global
            set cannot say so: declaring ``"NULL"`` to clean up a blank
            ``metro_region`` also blanked a professional genuinely surnamed
            ``"Null"`` — in every field on their row, since the same set was
            applied to every column. So the set is addressable per column:
            ``{"metro_region": ("NULL", "nan", "N/A"), "name": ()}`` declares
            the markers where they are markers and, with the empty tuple, opts
            the surname column out. A column named here uses *only* its own
            set, never its own set unioned with the global one — otherwise a
            column could not opt out of a sentinel it is given by default,
            which is the whole point. Keys are compared after
            :func:`normalize_header`, like every other column name.

    Returns:
        A :class:`DatasetQuality` describing every problem found. Findings
        accumulate; validation never stops at the first error, so a coordinator
        fixing an import sees the whole list at once.

    Raises:
        ValueError: If ``required`` and ``optional`` together declare the same
            column twice after normalization. That is a caller contract error,
            not a data problem: the duplicate would silently collapse and the
            column would be validated under whichever spelling won.

            Also if ``blank_sentinels_by_column`` names a column twice after
            normalization, or names one that is in neither ``required`` nor
            ``optional``. Both are caller contract errors of the same kind: a
            sentinel declared against a column nobody validates is a typo that
            does nothing, and silence would let a coordinator believe they had
            cleaned a column they had not.
    """
    required_normalized, optional_normalized = _normalize_declared(required, optional)
    default_sentinels = _sentinel_set(blank_sentinels)
    column_sentinels = _normalize_column_sentinels(
        blank_sentinels_by_column, required_normalized, optional_normalized
    )

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

    normalized_rows, source_headers, collisions = _index_rows(rows)

    # The column set is the union across every row, not row 0's keys. Ragged
    # rows are ordinary in real exports (a JSON-lines dump that omits null keys,
    # a sheet with trailing empty cells dropped); reading the first row alone
    # made the verdict depend on the order the rows happened to arrive in.
    present = set(source_headers)

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
    unexpected = sorted(source_headers[norm] for norm in present if norm not in known)
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

    findings.extend(_collision_findings(dataset, collisions, required_normalized))
    findings.extend(_ragged_findings(dataset, normalized_rows, source_headers, required_normalized))

    # A required column that exists but is blank in every row is as unusable as
    # a missing one; the legacy loader reported it as present and healthy.
    # What counts as blank is resolved per column, not once for the dataset:
    # see ``blank_sentinels_by_column``.
    for norm, original in required_normalized.items():
        if norm not in present:
            continue
        sentinels = column_sentinels.get(norm, default_sentinels)
        if all(_is_blank(row.get(norm), sentinels) for row in normalized_rows):
            findings.append(
                QualityFinding(
                    severity=Severity.ERROR,
                    code="required_column_entirely_blank",
                    message=f"{dataset}: required column {original!r} is blank in every row",
                    columns=(original,),
                )
            )

    return DatasetQuality(dataset=dataset, row_count=len(rows), findings=tuple(findings))


def _normalize_declared(
    required: Iterable[str], optional: Iterable[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Map declared column names to their normalized form, rejecting duplicates."""
    required_normalized: dict[str, str] = {}
    optional_normalized: dict[str, str] = {}
    seen: dict[str, str] = {}
    for group, names in (("required", required), ("optional", optional)):
        target = required_normalized if group == "required" else optional_normalized
        for name in names:
            norm = normalize_header(name)
            if norm in seen:
                raise ValueError(
                    f"column {name!r} duplicates {seen[norm]!r} after normalization; "
                    "declare each column exactly once across required and optional"
                )
            seen[norm] = name
            target[norm] = name
    return required_normalized, optional_normalized


def _sentinel_set(tokens: Iterable[str]) -> frozenset[str]:
    """Fold declared sentinel tokens into the form :func:`_is_blank` compares."""
    return frozenset(token.strip().lower() for token in tokens)


def _normalize_column_sentinels(
    declared: Mapping[str, Iterable[str]] | None,
    required_normalized: Mapping[str, str],
    optional_normalized: Mapping[str, str],
) -> dict[str, frozenset[str]]:
    """Map per-column sentinel declarations onto normalized column names.

    Rejects the two ways a declaration can be quietly meaningless, on the same
    reasoning as :func:`_normalize_declared`'s duplicate check: a column named
    twice under two spellings would have one declaration silently overwrite the
    other, and a column named here but declared in neither ``required`` nor
    ``optional`` is validated by nothing, so its sentinels would never be
    consulted. Failing loudly keeps a caller from believing a column is being
    cleaned when it is not — the failure mode this parameter exists to end.
    """
    if declared is None:
        return {}

    normalized: dict[str, frozenset[str]] = {}
    seen: dict[str, str] = {}
    known = set(required_normalized) | set(optional_normalized)
    for name, tokens in declared.items():
        norm = normalize_header(name)
        if norm in seen:
            raise ValueError(
                f"blank sentinels for column {name!r} duplicate those for {seen[norm]!r} "
                "after normalization; declare each column exactly once"
            )
        if norm not in known:
            raise ValueError(
                f"blank sentinels declared for column {name!r}, which is neither required "
                "nor optional; a sentinel for a column nobody validates has no effect"
            )
        seen[norm] = name
        normalized[norm] = _sentinel_set(tokens)
    return normalized


def _index_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, str], dict[str, tuple[str, ...]]]:
    """Index rows by normalized column name.

    Returns the per-row normalized values, the first source header seen for each
    normalized column (so findings quote the coordinator's own header rather
    than the normalized name they will not find in their file), and any headers
    within one row that collapsed onto a column already taken. The first
    occurrence in a row wins, so the value used is at least deterministic — but
    it is reported, because the other value is silently dropped.
    """
    normalized_rows: list[dict[str, object]] = []
    source_headers: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for row in rows:
        values: dict[str, object] = {}
        row_sources: dict[str, str] = {}
        for key, value in row.items():
            norm = normalize_header(key)
            if norm in values:
                shadowed = collisions.setdefault(norm, [row_sources[norm]])
                if key not in shadowed:
                    shadowed.append(key)
                continue
            values[norm] = value
            row_sources[norm] = key
            source_headers.setdefault(norm, key)
        normalized_rows.append(values)
    return normalized_rows, source_headers, {k: tuple(v) for k, v in collisions.items()}


def _collision_findings(
    dataset: str,
    collisions: Mapping[str, tuple[str, ...]],
    required_normalized: Mapping[str, str],
) -> list[QualityFinding]:
    """Report headers that collapsed onto the same column within a row."""
    findings: list[QualityFinding] = []
    for norm in sorted(collisions):
        headers = collisions[norm]
        is_required = norm in required_normalized
        findings.append(
            QualityFinding(
                severity=Severity.ERROR if is_required else Severity.WARNING,
                code="colliding_headers",
                message=(
                    f"{dataset}: headers {', '.join(repr(h) for h in headers)} are the same "
                    f"column after normalization; the first was used and the rest were "
                    f"dropped"
                ),
                columns=headers,
            )
        )
    return findings


def _ragged_findings(
    dataset: str,
    normalized_rows: Sequence[Mapping[str, object]],
    source_headers: Mapping[str, str],
    required_normalized: Mapping[str, str],
) -> list[QualityFinding]:
    """Report columns that some rows carry and others omit entirely.

    Split by severity on the same rule as everything else here: a *required*
    column absent from any row is an error, because the import contract says
    every row has it; anything else is a quality warning.
    """
    absent_counts = {
        norm: sum(1 for row in normalized_rows if norm not in row) for norm in source_headers
    }
    ragged = {norm: count for norm, count in absent_counts.items() if count}
    if not ragged:
        return []

    findings: list[QualityFinding] = []
    for severity, is_required in ((Severity.ERROR, True), (Severity.WARNING, False)):
        group = sorted(
            (source_headers[norm], count)
            for norm, count in ragged.items()
            if (norm in required_normalized) is is_required
        )
        if not group:
            continue
        detail = ", ".join(f"{header} (absent from {count} row(s))" for header, count in group)
        subject = "required columns" if is_required else "columns"
        findings.append(
            QualityFinding(
                severity=severity,
                code="ragged_rows",
                message=f"{dataset}: {subject} are missing from some rows: {detail}",
                columns=tuple(header for header, _ in group),
            )
        )
    return findings


def _is_blank(value: object, sentinels: Set[str]) -> bool:
    """Whether a cell counts as empty.

    ``None`` and whitespace-only text are blank on their own. Source-specific
    null markers are blank only when the caller declared them (see
    ``blank_sentinels``): the domain is handed already-parsed rows and knows
    nothing about where they came from, so it cannot decide that the text
    ``"Null"`` is an absent value rather than a coordinator's surname.

    ``sentinels`` is whatever the caller declared *for this column* — the
    resolution happens in :func:`validate_columns`, so that the same token can
    be a marker in one column and a value in another.
    """
    if value is None:
        return True
    text = str(value).strip().lower()
    return text == "" or text in sentinels
