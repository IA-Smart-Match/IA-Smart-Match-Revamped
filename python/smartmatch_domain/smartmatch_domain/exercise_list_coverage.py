"""Which majors and years among the whole set have nobody on the current list.

The class exercise's requirements row "Who is on the list"
(`docs/product/class-exercise-requirements.md`) asks for *"a one-line notice
when a major or year that exists among the 300 has nobody on the list"*. The
design spec §7 parks that notice behind the counts table as backlog; this
module is the notice's decision, and only its decision.

**What this module deliberately does not know.** It holds no vocabulary of
majors and no vocabulary of class years, because OQ-CE-01 — the data file's
column names and value vocabularies — is open until Ann's sample lands. Every
label comes in as data. It also reads no table, takes no dataset or team
identifier, and returns no sentence: the wording belongs to the surface that
shows it, and the reading belongs to the caller that will later compose this
with the exercise's profile rows.

**Unknown is not a group (ADR-0011).** A profile whose major or year is not
on file arrives as ``None``. It is never coerced to a label, never counted as
a group of its own, and never treated as a zero-sized group, so "nobody on
this list is a Finance major" can only ever be said about a label that some
profile in the whole set actually carries. An unknown value *on the list* is
equally inert: it covers no label, because a profile whose major nobody
recorded is not evidence that any particular major is represented.

**No number leaves this module (ADR-0025 D8).** It reports which groups are
uncovered, never how many profiles are in them, and never a share or a score.

Ordering is by first appearance in ``all_profiles``. That is deterministic
for a given input without this module learning a single major or year name,
and it hands the ordering decision to the caller: once Ann's year vocabulary
is settled the caller can present the whole set in that order and the notice
follows, with nothing here to change.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "GroupValues",
    "ListCoverage",
    "find_uncovered_groups",
    "uncovered_labels",
]


def _as_labels(
    values: Iterable[str | None], *, dimension: str, side: str
) -> tuple[str | None, ...]:
    """Freeze one side's per-profile values, rejecting blanks.

    A blank string is rejected rather than read as unknown: silently mapping
    ``""`` onto ``None`` would make a data-file defect indistinguishable from
    a profile that genuinely has no major on file, which is exactly the
    distinction ADR-0011 exists to keep.
    """
    frozen = tuple(values)
    for value in frozen:
        if value is not None and not value.strip():
            raise ValueError(
                f"{dimension}.{side}: blank value — use None for unknown, not a blank string"
            )
    return frozen


@dataclass(frozen=True, slots=True)
class GroupValues:
    """One grouping dimension's values, for the whole set and for the list.

    Attributes:
        dimension: What is being grouped by, in the caller's own words (for
            example ``"major"`` or ``"class_year"``). Non-blank. Carried so a
            caller composing several dimensions can tell error messages and
            results apart; this module attaches no meaning to its value.
        all_profiles: The value of this dimension for every profile in the
            whole set, one entry per profile, ``None`` where the value is not
            on file. Duplicates are expected and are what make it per-profile
            rather than a set.
        on_list: The same, for the profiles on the current ranked list.
    """

    dimension: str
    all_profiles: tuple[str | None, ...] = ()
    on_list: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if not self.dimension.strip():
            raise ValueError("dimension: must not be empty or blank")
        # Any iterable is accepted and frozen here, so a caller handing over a
        # list cannot later mutate what this value object reports.
        object.__setattr__(
            self,
            "all_profiles",
            _as_labels(self.all_profiles, dimension=self.dimension, side="all_profiles"),
        )
        object.__setattr__(
            self,
            "on_list",
            _as_labels(self.on_list, dimension=self.dimension, side="on_list"),
        )


@dataclass(frozen=True, slots=True)
class ListCoverage:
    """The groups that exist in the whole set and have nobody on the list.

    Attributes:
        missing_majors: Majors carried by at least one profile in the whole
            set and by no profile on the list, in first-appearance order.
        missing_class_years: The same for class years.
    """

    missing_majors: tuple[str, ...]
    missing_class_years: tuple[str, ...]

    @property
    def has_uncovered_group(self) -> bool:
        """Whether there is anything at all for a notice to say."""
        return bool(self.missing_majors) or bool(self.missing_class_years)


def uncovered_labels(values: GroupValues) -> tuple[str, ...]:
    """The labels present in the whole set and absent from the list.

    Args:
        values: One dimension's per-profile values on both sides.

    Returns:
        Each such label once, ordered by its first appearance in
        ``values.all_profiles``. ``None`` entries take part on neither side:
        unknown is not a group, and an unknown on the list covers nothing.
    """
    covered = {value for value in values.on_list if value is not None}
    uncovered: list[str] = []
    seen: set[str] = set()
    for value in values.all_profiles:
        if value is None or value in covered or value in seen:
            continue
        seen.add(value)
        uncovered.append(value)
    return tuple(uncovered)


def find_uncovered_groups(*, majors: GroupValues, class_years: GroupValues) -> ListCoverage:
    """Both dimensions of the "who is on the list" notice in one value.

    Args:
        majors: Per-profile majors for the whole set and for the list.
        class_years: Per-profile class years for the same two populations.

    Returns:
        A :class:`ListCoverage` naming the uncovered groups of each
        dimension. Every entry is a label some profile in the whole set
        carries; no count, share, or score is returned (ADR-0025 D8).
    """
    return ListCoverage(
        missing_majors=uncovered_labels(majors),
        missing_class_years=uncovered_labels(class_years),
    )
