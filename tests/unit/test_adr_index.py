"""The ADR index agrees with the ADRs it indexes.

`docs/architecture/decisions/README.md` is a table of every architecture
decision record. A table maintained by hand goes stale the first time someone
adds an ADR and forgets it, and a stale index is worse than none: it is read as
a complete list, so an ADR missing from it is an ADR nobody finds.

These tests are the control that makes the index a statement about the directory
rather than a statement about what someone remembered. They compare the table
against the files, both ways, and compare each row's title, status, and date
against the ADR's own header.

**What is not checked, and cannot be.** The "Decides" column is a one-line
summary written by a person. No test can tell whether it still describes the
decision after the ADR is amended — only that the amendment happened. That
column is the index's one silent failure mode, and the README says so.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO_ROOT / "docs" / "architecture" / "decisions"
INDEX_PATH = DECISIONS_DIR / "README.md"

#: An ADR filename: the number is what the index keys on.
_ADR_FILENAME = re.compile(r"^ADR-(\d{4})-[a-z0-9-]+\.md$")

#: A row of the index table. The link text carries the ADR number and the link
#: target carries the filename, so a row that points at the wrong file is
#: detectable without reading the file it points at.
_INDEX_ROW = re.compile(
    r"^\|\s*\[ADR-(?P<number>\d{4})\]\((?P<target>[^)]+)\)\s*"
    r"\|(?P<title>[^|]*)"
    r"\|(?P<status>[^|]*)"
    r"\|(?P<date>[^|]*)"
    r"\|(?P<decides>[^|]*)"
    r"\|(?P<amended>[^|]*)"
    r"\|(?P<supersedes>[^|]*)"
    r"\|(?P<superseded_by>[^|]*)\|\s*$"
)

#: One ADR reference. The boundaries on *both* sides are load-bearing: without
#: the lookbehind `XADR-0001` reads as ADR-0001, and with a trailing class
#: narrower than `\w` so do `ADR-0001_oops` and `ADR-0001é` — `\w` is
#: Unicode-aware in Python, which is what makes the last of those fail. A hyphen
#: is still allowed after the digits, because that is how the link target
#: `ADR-0004-hand-written-schema-and-ltree.md` is spelled.
_ADR_REFERENCE = re.compile(r"(?<![0-9A-Za-z_])ADR-(\d{4})(?!\w)")

#: One entry in a supersession cell: a bare `ADR-NNNN`, or a link. Link text and
#: target are compared in :func:`_supersession_references` rather than with a
#: backreference, because the readable version of that pattern needs the number
#: twice inside a repetition and a named group cannot be reused there.
_SUPERSESSION_ENTRY = re.compile(
    r"^(?:ADR-(?P<bare>\d{4})"
    r"|\[ADR-(?P<text>\d{4})\]\(ADR-(?P<target>\d{4})-[a-z0-9-]+\.md\))$"
)

#: A date at the very start of an Amended cell, and not a longer number.
#: `startswith` alone accepts `20 August 20260 — wrong` for `20 August 2026`.
_LEADING_DATE = re.compile(r"^(?P<date>\d{1,2}\s+[A-Za-z]+\s+\d{4})(?!\d)")

#: A fenced code block delimiter. The marker character and its run length are
#: captured because a fence is closed only by the *same* character, at least as
#: long — a `~~~` inside a ```` ``` ```` block is ordinary content, not a
#: closer.
_CODE_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")

#: An ATX heading at level 1 or 2, ending the index section. Up to three leading
#: spaces are allowed — four would make it an indented code block — and the
#: separator may be a tab, which CommonMark permits and a literal `"## "` misses.
_INDEX_SECTION_END = re.compile(r"^ {0,3}#{1,2}(?:[ \t]|$)")

#: Ends an ADR's header block. Level 2 only, not 1: an ADR's own title on line 1
#: is a level-1 heading, and a terminator that matched it would make every
#: header block empty.
_SECTION_HEADING = re.compile(r"^ {0,3}##(?:[ \t]|$)")

#: The index heading itself, with the same indentation and separator rules.
_INDEX_HEADING = re.compile(r"^ {0,3}##[ \t]+The index[ \t]*$")

#: The statuses an ADR may carry. A closed vocabulary rather than a free string:
#: without it, `test_a_superseded_adr_does_not_still_read_as_accepted` rejects
#: only the exact word `Accepted`, so any other text — including a typo, or a
#: lowercase `accepted` — satisfies it while saying nothing.
_VALID_STATUSES = frozenset({"Accepted", "Proposed", "Rejected", "Superseded", "Deprecated"})

#: `**Status:** Accepted — amended 19 August 2026, see ...` — the index records
#: the bare status, and the amendment separately, so this splits at the dash.
_HEADER_FIELD = re.compile(r"^\*\*(?P<name>Status|Date):\*\*\s*(?P<value>.+?)\s*$", re.MULTILINE)

#: `**Status:** Accepted — amended 19 August 2026, see ...`
_AMENDMENT_DATE = re.compile(r"amended\s+(?P<date>\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)

_TITLE_HEADING = re.compile(r"^#\s+ADR-(?P<number>\d{4})\s+—\s+(?P<title>.+?)\s*$")


def _supersession_references(number: str, column: str, cell: str) -> list[str]:
    """Every ADR named in a supersession cell, with the whole cell validated.

    Harvesting references with `findall` and checking only what it returns lets
    a malformed name hide behind a well-formed one: `ADR-0002 and ADR-9999oops`
    yields `['0002']`, and the broken half is silently discarded rather than
    reported. So the cell is parsed as a closed grammar — `—`, or a
    comma-separated list of `ADR-NNNN` or `[ADR-NNNN](ADR-NNNN-slug.md)` — and
    anything else is an error naming the cell it came from.
    """
    if cell == "—":
        return []
    references: list[str] = []
    for raw in cell.split(","):
        entry = raw.strip()
        match = _SUPERSESSION_ENTRY.match(entry)
        assert match is not None, (
            f"ADR-{number}'s {column} cell contains {entry!r}, which is not an ADR "
            f"reference. Use `—` for none, or `ADR-NNNN`, or "
            f"`[ADR-NNNN](ADR-NNNN-slug.md)`, comma-separated."
        )
        if match.group("bare"):
            references.append(match.group("bare"))
            continue
        assert match.group("text") == match.group("target"), (
            f"ADR-{number}'s {column} cell links the text ADR-{match.group('text')} "
            f"to the file for ADR-{match.group('target')}"
        )
        references.append(match.group("text"))
    return references


def _adr_files() -> dict[str, Path]:
    """Every ADR in the directory, keyed by its four-digit number.

    Two files claiming the same number would silently collapse into one entry if
    this assigned straight into a dict — and every check below would then run
    against whichever sorted last, leaving the other file real, unindexed, and
    invisible to `test_every_adr_has_a_row`. So the collision is an error here,
    where it is nameable, rather than a gap downstream.
    """
    found: dict[str, Path] = {}
    for path in sorted(DECISIONS_DIR.glob("ADR-*.md")):
        match = _ADR_FILENAME.match(path.name)
        assert match is not None, f"{path.name} does not follow ADR-NNNN-slug.md"
        number = match.group(1)
        assert number not in found, (
            f"two files claim ADR-{number}: {found[number].name} and {path.name}"
        )
        found[number] = path
    return found


def _fenced_lines(lines: list[str], source: str) -> list[bool]:
    """For each line, whether it is inside a fenced code block or is a fence.

    Toggling a boolean on every ``` *or* `~~~` is not enough, and this is the
    one bypass round 3 called blocking. CommonMark closes a fence only with the
    **same** marker character, at least as long as the opener and with no info
    string; inside a backtick fence a `~~~` line is ordinary content. Under the
    toggle, ```` ```py ````/`~~~`/*row*/`~~~`/```` ``` ```` left the row outside
    any fence, so a real index row could be deleted and replaced by a fenced
    copy with the suite still green. Reproduced before this was written.
    """
    flags: list[bool] = []
    marker: str | None = None
    for line in lines:
        match = _CODE_FENCE.match(line)
        if marker is None:
            if match is not None and not (
                match.group("marker").startswith("`") and "`" in match.group("info")
            ):
                marker = match.group("marker")
                flags.append(True)
                continue
            flags.append(False)
            continue
        flags.append(True)
        if (
            match is not None
            and match.group("marker")[0] == marker[0]
            and len(match.group("marker")) >= len(marker)
            and not match.group("info").strip()
        ):
            marker = None
    assert marker is None, f"{source} has an unclosed code fence"
    return flags


def _content_lines(lines: list[str], source: str) -> list[str]:
    """The lines that are real content — everything outside a fence."""
    fenced = _fenced_lines(lines, source)
    return [line for line, inside in zip(lines, fenced, strict=True) if not inside]


def _index_section() -> list[str]:
    """The lines of the `## The index` section, and only those.

    Scanning the whole README would let any eight-column line elsewhere — an
    example, a second table, a row quoted in prose — count as an official index
    row. The real table could then omit an ADR while an unintended line
    satisfied both the membership and the field checks.

    **Fences are resolved before boundaries are found, not after.** Locating the
    section first and stripping fences second treats a `## Example` written
    inside a fenced block as a real section heading, which ends the slice early
    — and leaves the slice holding an opening fence with no closer, so the
    failure arrives as a confusing "unclosed code fence" rather than as anything
    about the index.
    """
    source = f"{INDEX_PATH.name}'s `## The index` section"
    lines = INDEX_PATH.read_text(encoding="utf-8").splitlines()
    fenced = _fenced_lines(lines, source)
    real = [(i, line) for i, line in enumerate(lines) if not fenced[i]]

    starts = [i for i, line in real if _INDEX_HEADING.match(line)]
    assert len(starts) == 1, (
        f"expected exactly one `## The index` heading in {INDEX_PATH.name}, found {len(starts)}"
    )
    after = [(i, line) for i, line in real if i > starts[0]]
    end = next(
        (i for i, line in after if _INDEX_SECTION_END.match(line)),
        len(lines),
    )
    return [line for i, line in after if i < end]


def _index_rows() -> dict[str, dict[str, str]]:
    """Every row of the index table, keyed by ADR number."""
    rows: dict[str, dict[str, str]] = {}
    for line in _index_section():
        match = _INDEX_ROW.match(line)
        if match is None:
            continue
        number = match.group("number")
        assert number not in rows, f"ADR-{number} appears twice in the index"
        rows[number] = {
            name: (match.group(name) or "").strip()
            for name in (
                "target",
                "title",
                "status",
                "date",
                "decides",
                "amended",
                "supersedes",
                "superseded_by",
            )
        }
    return rows


def _header_block(path: Path) -> str:
    """The ADR's preamble: everything before its first `## ` section.

    Searching the whole document would let a `**Status:**` line quoted inside a
    body section masquerade as the header — and because the last match won, a
    quoted example *after* the real one would be the one compared. The header of
    an ADR is by construction above its first section heading, so that is where
    this looks.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    fenced = _fenced_lines(lines, f"{path.name}")
    real = [(i, line) for i, line in enumerate(lines) if not fenced[i]]
    end = next((i for i, line in real if _SECTION_HEADING.match(line)), len(lines))
    return "\n".join(line for i, line in real if i < end)


def _header_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in _HEADER_FIELD.finditer(_header_block(path)):
        name = match.group("name")
        assert name not in fields, f"{path.name} has more than one `**{name}:**` header line"
        fields[name] = match.group("value")
    return fields


def _declared_title(path: Path) -> tuple[str, str]:
    """The ADR's title, which must be its very first line.

    Anchored to line one rather than searched for: an H1 anywhere in the body
    would otherwise be accepted as the document's title.
    """
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    match = _TITLE_HEADING.match(first_line)
    assert match is not None, (
        f"{path.name}'s first line is not a `# ADR-NNNN — Title` heading: {first_line!r}"
    )
    return match.group("number"), match.group("title")


def _row(number: str) -> dict[str, str]:
    """One index row, with a readable failure when there is none.

    Without this, every per-ADR test below raises `KeyError` for an unindexed
    ADR — a worse diagnostic than the one `test_every_adr_has_a_row` already
    prints. The guard keeps the noise readable rather than adding signal.
    """
    rows = _index_rows()
    assert number in rows, (
        f"ADR-{number} has no row in docs/architecture/decisions/README.md "
        f"(see test_every_adr_has_a_row for the full list)"
    )
    return rows[number]


ADR_NUMBERS = sorted(_adr_files())


def test_the_index_exists_and_parses() -> None:
    """A table nothing can read is not an index."""
    assert INDEX_PATH.is_file(), f"{INDEX_PATH} is missing"
    assert _index_rows(), "the index table has no ADR rows — did the format change?"


def test_every_adr_has_a_row() -> None:
    """The failure this whole file exists to catch: a new ADR, unindexed."""
    missing = sorted(set(_adr_files()) - set(_index_rows()))
    assert not missing, (
        "these ADRs are not listed in docs/architecture/decisions/README.md: "
        + ", ".join(f"ADR-{n}" for n in missing)
    )


def test_every_row_has_an_adr() -> None:
    """The other direction: a row for an ADR that was renamed or removed."""
    extra = sorted(set(_index_rows()) - set(_adr_files()))
    assert not extra, (
        "the index lists ADRs with no file in docs/architecture/decisions/: "
        + ", ".join(f"ADR-{n}" for n in extra)
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_row_links_to_the_adr_it_names(number: str) -> None:
    """A row whose link points at a different ADR reads as correct and is not."""
    row = _row(number)
    assert row["target"] == _adr_files()[number].name, (
        f"ADR-{number}'s row links to {row['target']!r}, "
        f"but ADR-{number} is {_adr_files()[number].name!r}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_row_title_matches_the_adr_heading(number: str) -> None:
    path = _adr_files()[number]
    heading_number, title = _declared_title(path)
    assert heading_number == number, (
        f"{path.name} is filed as ADR-{number} but its heading says ADR-{heading_number}"
    )
    assert _row(number)["title"] == title, (
        f"ADR-{number}'s index title does not match its heading.\n"
        f"  index:   {_row(number)['title']!r}\n"
        f"  heading: {title!r}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_row_status_matches_the_adr_header(number: str) -> None:
    """The index carries the bare status; the ADR may append an amendment note.

    `**Status:** Accepted — amended 19 August 2026, see ...` indexes as
    `Accepted`, with the amendment in its own column. Comparing only up to the
    em dash keeps both readable while still catching an ADR that has actually
    been superseded or rejected without the index noticing.
    """
    path = _adr_files()[number]
    declared = _header_fields(path).get("Status")
    assert declared is not None, f"{path.name} has no `**Status:**` line"
    bare_status = declared.split("—")[0].strip()
    assert _row(number)["status"] == bare_status, (
        f"ADR-{number}'s index status is {_row(number)['status']!r} "
        f"but the ADR says {bare_status!r}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_row_date_matches_the_adr_header(number: str) -> None:
    path = _adr_files()[number]
    declared = _header_fields(path).get("Date")
    assert declared is not None, f"{path.name} has no `**Date:**` line"
    assert _row(number)["date"] == declared, (
        f"ADR-{number}'s index date is {_row(number)['date']!r} but the ADR says {declared!r}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_an_amended_adr_is_marked_amended_in_the_index(number: str) -> None:
    """An ADR whose body has moved on since its date should say so in the index.

    This is the half of the "Decides" problem that *is* checkable: not whether
    the summary is still true, but whether the reader is told to go and look.
    """
    path = _adr_files()[number]
    declared = _header_fields(path)["Status"]
    is_amended = "amended" in declared.lower()
    row_amended = _row(number)["amended"]
    if is_amended:
        assert row_amended and row_amended != "—", (
            f"{path.name}'s status says it was amended, but its index row's "
            f"Amended column reads {row_amended!r}"
        )
        # Non-emptiness alone would let any text stand in for the amendment.
        # The date is the one field both the ADR's status line and the index
        # row state independently, so it is the one that can be compared.
        amendment_date = _AMENDMENT_DATE.search(declared)
        assert amendment_date is not None, (
            f"{path.name}'s status says it was amended but names no date: {declared!r}"
        )
        # Containment is not enough: `21 August 2026 — corrected from 20 August
        # 2026` contains `20 August 2026`, so a cell naming the wrong date
        # passes a substring test while displaying the wrong one first. The
        # house format opens the cell with the date, so that is what is
        # compared — the date the reader's eye lands on.
        expected = amendment_date.group("date")
        leading = _LEADING_DATE.match(row_amended)
        assert leading is not None, (
            f"ADR-{number}'s Amended cell must begin with a date. It reads {row_amended!r}."
        )
        assert leading.group("date") == expected, (
            f"ADR-{number}'s Amended cell opens with {leading.group('date')!r}, "
            f"but its status line dates the amendment {expected!r}."
        )
    else:
        assert row_amended == "—", (
            f"{path.name}'s status records no amendment, but its index row claims {row_amended!r}"
        )


def test_adr_numbers_are_contiguous_from_one() -> None:
    """A gap means an ADR was deleted, which is not how ADRs are retired.

    A decision that stops being true gets a superseding ADR and keeps its file.
    A missing number is therefore a mistake — either a deletion, or a reserved
    number that grew a file somewhere other than this directory.
    """
    numbers = [int(n) for n in ADR_NUMBERS]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"ADR numbers are not contiguous from 0001: {ADR_NUMBERS}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_supersession_columns_name_real_adrs(number: str) -> None:
    """Parsing a column and never asserting on it is not coverage.

    Both supersession columns are `—` today, because no ADR has been superseded.
    That is exactly when a check is worth writing: the first time one is, the
    columns will be filled in by hand, and this is what stops the entry naming
    an ADR that does not exist. It cannot be written later from evidence,
    because by then the mistake is already in the table.
    """
    row = _row(number)
    known = set(_adr_files())
    for column in ("supersedes", "superseded_by"):
        referenced = _supersession_references(number, column, row[column])
        unknown = sorted(set(referenced) - known)
        assert not unknown, f"ADR-{number}'s {column} column names ADRs with no file: " + ", ".join(
            f"ADR-{n}" for n in unknown
        )
        assert number not in referenced, f"ADR-{number}'s {column} column names itself"


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_supersession_is_recorded_from_both_ends(number: str) -> None:
    """If A supersedes B, B's row must say it is superseded by A.

    A one-sided entry is the failure mode of a hand-maintained cross-reference:
    the person writing the new ADR fills in its `Supersedes` cell and does not
    go back to edit the old row, so the superseded ADR still reads as current.
    """
    row = _row(number)
    for this_column, other_column in (
        ("supersedes", "superseded_by"),
        ("superseded_by", "supersedes"),
    ):
        for other in _supersession_references(number, this_column, row[this_column]):
            other_row = _row(other)
            reciprocal = _supersession_references(other, other_column, other_row[other_column])
            assert number in reciprocal, (
                f"ADR-{number}'s {this_column} column names ADR-{other}, but "
                f"ADR-{other}'s {other_column} column does not name ADR-{number}"
            )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_a_superseded_adr_does_not_still_read_as_accepted(number: str) -> None:
    """The status and the supersession column cannot disagree.

    An ADR listed as superseded whose status is still a bare `Accepted` is the
    table contradicting itself, and a reader who checks only the status column
    reads a replaced decision as current.
    """
    row = _row(number)
    if row["superseded_by"] == "—":
        return
    assert row["status"] == "Superseded", (
        f"ADR-{number} is listed as superseded by {row['superseded_by']}, so its "
        f"status must read 'Superseded'. It reads {row['status']!r}."
    )


def test_the_index_is_in_number_order() -> None:
    """The README calls itself a list "in number order"; this is that claim.

    Membership is checked with sets everywhere else, so a shuffled table would
    otherwise pass every test in this file while the document's first sentence
    was untrue.
    """
    listed = [
        _INDEX_ROW.match(line).group("number")  # type: ignore[union-attr]
        for line in _index_section()
        if _INDEX_ROW.match(line)
    ]
    assert listed == sorted(listed), f"the index table is not in number order: {listed}"


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_the_status_is_one_of_the_known_statuses(number: str) -> None:
    """A status outside the vocabulary is not a status.

    Without this, `test_a_superseded_adr_does_not_still_read_as_accepted` was
    an inequality against one literal: a lowercase `accepted`, a trailing full
    stop, or a typo satisfied it while telling the reader nothing. Pinning the
    vocabulary is what turns that test into a statement about the decision's
    actual state.
    """
    status = _row(number)["status"]
    assert status in _VALID_STATUSES, (
        f"ADR-{number}'s status is {status!r}, which is not one of {sorted(_VALID_STATUSES)}"
    )


@pytest.mark.parametrize("number", ADR_NUMBERS)
def test_a_superseded_adr_names_what_replaced_it(number: str) -> None:
    """The inverse of the rule above, and the half that was missing.

    `Superseded by` implies status `Superseded` was already enforced. Without
    this, the other direction was free: a row could read `Superseded` with `—`
    in its `Superseded by` cell, telling the reader the decision has been
    replaced and not by what — which is the one thing they need next.
    """
    row = _row(number)
    if row["status"] != "Superseded":
        return
    assert row["superseded_by"] != "—", (
        f"ADR-{number}'s status is 'Superseded' but its `Superseded by` cell is "
        f"`—`, so the table does not say what replaced it"
    )
