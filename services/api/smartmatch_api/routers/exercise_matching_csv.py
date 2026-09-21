"""Design spec §8's download: six columns, and a cell that cannot be a formula.

Split out of ``exercise_matching_models.py`` in review round 2 (F4), which had
grown past this repository's 800-line ceiling. The cut is along a seam the
module already had: everything here is about turning one already-built
:class:`~smartmatch_api.routers.exercise_matching_models.RankedListView` into
text, and none of it is part of the response contract.

Nothing here reads a table, decides a status code or imports FastAPI, and
nothing here names ``hidden_true_interests`` — the view it renders has no field
for it (ADR-0025 D6), and the six columns are written out below rather than
derived from a row, so a column cannot appear by accident.

``csv.writer`` into a :class:`io.StringIO`. Never pandas, never the pandas
writer — ``tools/scan_forbidden.py`` refuses both by name — and never a file on
disk: the whole document is at most an invite limit's worth of rows, and a
temporary file is a thing to clean up and a thing to leak.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from smartmatch_api.routers.exercise_matching_models import RankedListView

__all__ = [
    "CSV_FORMULA_INTRODUCERS",
    "CSV_LEADING_CONTROL",
    "CSV_LEADING_WHITESPACE",
    "CSV_LIST_COLUMNS",
    "CSV_TEXT_PREFIX",
    "csv_download_filename",
    "neutralised_cell",
    "ranked_list_csv",
]


# ---------------------------------------------------------------------------
# The download (design spec §8)
# ---------------------------------------------------------------------------

#: Design spec §8's columns, in order. Named here rather than written into the
#: writer, so the header row and the value row cannot drift.
CSV_LIST_COLUMNS: Final[tuple[str, ...]] = (
    "rank",
    "name",
    "major",
    "year",
    "marker",
    "reason",
)

#: The four characters Excel and LibreOffice read as the start of a formula.
#:
#: This matters for this product specifically: a display name, a major and a
#: class year all come from a file an instructor uploaded, and the download is
#: opened in a spreadsheet by definition.
CSV_FORMULA_INTRODUCERS: Final[tuple[str, ...]] = ("=", "+", "-", "@")

#: Characters skipped when looking for a cell's first significant character.
#:
#: Review round 1: the first version of this guard compared the cell's first
#: character against the introducers plus tab and carriage return, which its own
#: docstring already said was not the rule — ``" =cmd|…"`` and ``"\n=cmd|…"``
#: both walked straight through it.
#:
#: Review round 2: the replacement was ASCII-only, and the characters that
#: actually arrive in a file somebody pasted a spreadsheet into are not. A
#: no-break space (U+00A0) is what a copy out of a web page leaves in front of a
#: value; a byte-order mark (U+FEFF) is what a Windows editor writes at the head
#: of the first cell; a zero-width space (U+200B) is invisible in every editor
#: that would have shown the others. Each of them sat in front of ``=`` and went
#: through untouched. The set below is the ASCII whitespace plus those three and
#: the Unicode spaces beside them, and the check skips **all** of it.
#:
#: The cell itself is never rewritten — a skipped character is skipped for the
#: purpose of *deciding*, and the value a reader sees is the value that arrived.
CSV_LEADING_WHITESPACE: Final[str] = (
    " \t\r\n\v\f"
    "\x85"  # NEL
    "\xa0"  # NO-BREAK SPACE
    "\u1680"  # OGHAM SPACE MARK
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"  # EN..HAIR
    "\u200b\u200c\u200d"  # ZERO WIDTH SPACE / NON-JOINER / JOINER
    "\u2028\u2029"  # LINE / PARAGRAPH SEPARATOR
    "\u202f"  # NARROW NO-BREAK SPACE
    "\u205f"  # MEDIUM MATHEMATICAL SPACE
    "\u3000"  # IDEOGRAPHIC SPACE
    "\ufeff"  # ZERO WIDTH NO-BREAK SPACE / BOM
)

#: Leading characters that make a cell worth neutralising on their own, whatever
#: follows them: a tab, a carriage return or a newline at the front of a cell is
#: never data anybody typed, and it is how a cell smuggles a row break past a
#: careless reader.
CSV_LEADING_CONTROL: Final[tuple[str, ...]] = ("\t", "\r", "\n")

#: What a neutralised cell is prefixed with. A single quote is what a spreadsheet
#: reads as "this cell is text", and it is what the cell shows if the file is
#: opened by anything else — visible, rather than silently executed.
CSV_TEXT_PREFIX: Final[str] = "'"


def neutralised_cell(value: object) -> str:
    """One cell, with a formula introducer defused.

    The rule is the spreadsheet's own: **strip the leading whitespace first, and
    then look at the character that is left.** Checking the raw first character
    is the version that ships with a docstring describing this rule and does not
    implement it, which is what review round 1 found — ``" =cmd|…"`` and
    ``"\n=cmd|…"`` are the same attack wearing a space.

    A leading tab, carriage return or newline is neutralised even when nothing
    dangerous follows: it is never data, and a cell that begins with a row break
    is a cell worth showing rather than obeying.

    The whitespace skipped is :data:`CSV_LEADING_WHITESPACE`, which is **not**
    only ASCII (review round 2): a no-break space, a byte-order mark and a
    zero-width space are what a value pasted out of a web page or written by a
    Windows editor actually begins with, and all three used to carry an ``=``
    past this guard while being invisible to whoever looked at the file.

    Applied to **every** cell rather than to the ones that look risky: ``rank``
    is an integer today and a rule that exempts a column is a rule that stops
    holding when the column changes.
    """
    text = str(value)
    if text[:1] in CSV_LEADING_CONTROL:
        return f"{CSV_TEXT_PREFIX}{text}"
    if text.lstrip(CSV_LEADING_WHITESPACE)[:1] in CSV_FORMULA_INTRODUCERS:
        return f"{CSV_TEXT_PREFIX}{text}"
    return text


def ranked_list_csv(view: RankedListView) -> str:
    """Design spec §8's download, as text.

    ``csv.writer`` into a :class:`io.StringIO`. Never pandas, never ``to_csv``
    — ``tools/scan_forbidden.py`` refuses both by name — and never a file on
    disk: the whole document is at most an invite limit's worth of rows, and a
    temporary file is a thing to clean up and a thing to leak.

    ``lineterminator="\\r\\n"`` is stated rather than left to the platform, so
    the bytes a classroom downloads do not depend on which machine served them.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_LIST_COLUMNS)
    for entry in view.entries:
        writer.writerow(
            neutralised_cell(cell)
            for cell in (
                entry.rank,
                entry.display_name,
                entry.major,
                entry.class_year,
                entry.marker,
                entry.reason,
            )
        )
    return buffer.getvalue()


#: What a download is called when the event key survives sanitising as nothing.
_UNNAMED_LIST: Final[str] = "list"

#: How much of an event key is kept in a filename.
_MAX_FILENAME_STEM: Final[int] = 60


def csv_download_filename(event_key: str) -> str:
    """A ``Content-Disposition`` filename built from the event key alone.

    The key is data from an uploaded file, and a header value is parsed by the
    browser, so the alphabet is an allow-list rather than a list of characters to
    strip: letters, digits, hyphen and underscore survive and **everything else
    becomes a hyphen**, which cannot close a quoted string, start a second header
    line, or name a directory.

    Nothing else reaches the name — not the team number, not the dataset label,
    not a profile's name — because a filename is the one part of this response
    that a person forwards without reading.
    """
    stem = "".join(
        character if character.isascii() and (character.isalnum() or character in "-_") else "-"
        for character in event_key
    ).strip("-")[:_MAX_FILENAME_STEM]
    return f"{stem or _UNNAMED_LIST}-list.csv"
