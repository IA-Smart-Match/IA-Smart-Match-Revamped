"""One sentence per name (requirements "Matching"; design spec §4.5).

Ann asks for a reason line next to every name, and fixes two of them word for
word:

* ``same major; nothing else on file`` — for a profile the other three factors
  cannot speak about.
* ``tied on major; ordered by year`` — for a name the tie-break's year key put
  where it is.

**Her words, and the sentence rule, are both kept.** The repository's
:func:`~smartmatch_domain.one_sentence.assert_one_sentence` requires a capital
letter and a closing full stop, which Ann's phrases (written as table cells in
a requirements document) do not carry. Rewording them would lose the
requirement; skipping the check would lose the contract. So her phrase is the
constant — :data:`ANN_MAJOR_ONLY_PHRASE` and :data:`ANN_TIED_ON_YEAR_PHRASE`,
byte for byte — and the rendered line is that same phrase as a sentence:
capitalised, full-stopped, and checked. ``tests/unit/test_exercise_reasons.py``
asserts both halves, so neither can drift from the other. **This is the only
liberty taken with Ann's wording, and it is noted on this track's pull
request.**

**Which reason a name gets.** In order, first match wins:

1. The year key decided this name's place against an equal neighbour — Ann's
   tie sentence. It takes precedence over everything below because it is the
   case she wrote it for.
2. Nothing but the major is on file — Ann's major-only sentence. The trigger is
   the *marker*, not whether the major matched: "for everyone else the reason
   line says so" is about what is on file, and a profile whose major is not a
   target major still has nothing else on file to say.
3. Another key decided the tie — how much is on file, or the fixed order. Said
   in the same shape as Ann's sentence so the three read as one family.
4. Otherwise: the factors that contributed, named in Ann's plain words, in
   registry order.
5. Nothing contributed although something is on file — said plainly rather
   than left blank.

A factor "contributes" when its value is known and above zero. A measured zero
adds nothing to the composition, and naming it would tell a class participant
that something they can see counted when it did not.

**No number appears in any of these sentences** (ADR-0025 D8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final

from smartmatch_domain.exercise.markers import InformationMarker
from smartmatch_domain.exercise.registry import EXERCISE_FACTOR_LABELS
from smartmatch_domain.one_sentence import assert_one_sentence

__all__ = [
    "ANN_MAJOR_ONLY_PHRASE",
    "ANN_TIED_ON_YEAR_PHRASE",
    "TieBreakKey",
    "exercise_reason",
    "phrase_as_sentence",
]

#: Ann's words for a profile with nothing but a major on file, verbatim from
#: the requirements "Matching" row. Never edited, never reworded.
ANN_MAJOR_ONLY_PHRASE: Final[str] = "same major; nothing else on file"

#: Ann's words for a name the year key placed, verbatim from the same row.
ANN_TIED_ON_YEAR_PHRASE: Final[str] = "tied on major; ordered by year"

#: The same shape as Ann's tie sentence, for the two tie-break keys she did not
#: write a line for. Phrases, not sentences, so they go through the same
#: rendering her two do.
_TIED_ON_INFORMATION_PHRASE: Final[str] = "tied on major; ordered by how much is on file"
_TIED_ON_FIXED_ORDER_PHRASE: Final[str] = "tied on major; ordered by the fixed order"

#: Said when a profile has a card or past events on file and none of it
#: overlapped this event. Not blank, and not Ann's major-only line, which would
#: be untrue of a profile that does have a card.
_NOTHING_MATCHED_PHRASE: Final[str] = "nothing on file matches this event"


class TieBreakKey(StrEnum):
    """Which key settled one name's place against an equal neighbour."""

    #: No neighbour composed to the same value: the factors decided.
    NONE = "none"
    #: Equal value, and how much is on file decided.
    INFORMATION = "information"
    #: Equal value and equal information, and the year decided.
    YEAR = "year"
    #: Equal on everything the data says, and the fixed order decided.
    FIXED_ORDER = "fixed_order"


_TIE_PHRASES: Final[Mapping[TieBreakKey, str]] = {
    TieBreakKey.INFORMATION: _TIED_ON_INFORMATION_PHRASE,
    TieBreakKey.YEAR: ANN_TIED_ON_YEAR_PHRASE,
    TieBreakKey.FIXED_ORDER: _TIED_ON_FIXED_ORDER_PHRASE,
}


def phrase_as_sentence(phrase: str, *, field: str = "reason") -> str:
    """Render one of the phrases above as a checked sentence.

    Args:
        phrase: The phrase, in the words the requirements state it.
        field: The field name a failure should name.

    Returns:
        The phrase capitalised and full-stopped, having passed
        :func:`~smartmatch_domain.one_sentence.assert_one_sentence`. The words
        in between are untouched.
    """
    sentence = f"{phrase[:1].upper()}{phrase[1:]}."
    return assert_one_sentence(sentence, field=field)


def _factor_phrase(contributing_keys: Sequence[str]) -> str:
    """The contributing factors named in Ann's words, as one phrase."""
    labels = [EXERCISE_FACTOR_LABELS[key] for key in contributing_keys]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def exercise_reason(
    *,
    marker: InformationMarker,
    contributing_keys: Sequence[str],
    tie_break_key: TieBreakKey = TieBreakKey.NONE,
) -> str:
    """The one sentence shown next to one name.

    Args:
        marker: The profile's "how much we know" group.
        contributing_keys: The factor keys whose value was known and above
            zero, in registry order.
        tie_break_key: Which tie-break key settled this name's place, or
            :attr:`TieBreakKey.NONE` when no neighbour composed to the same
            value.

    Returns:
        Exactly one sentence, checked by
        :func:`~smartmatch_domain.one_sentence.assert_one_sentence`. No number
        appears in it (ADR-0025 D8).
    """
    if tie_break_key is TieBreakKey.YEAR:
        return phrase_as_sentence(ANN_TIED_ON_YEAR_PHRASE)
    if marker is InformationMarker.MAJOR_ONLY:
        return phrase_as_sentence(ANN_MAJOR_ONLY_PHRASE)
    if tie_break_key is not TieBreakKey.NONE:
        return phrase_as_sentence(_TIE_PHRASES[tie_break_key])
    if contributing_keys:
        return phrase_as_sentence(_factor_phrase(contributing_keys))
    return phrase_as_sentence(_NOTHING_MATCHED_PHRASE)
