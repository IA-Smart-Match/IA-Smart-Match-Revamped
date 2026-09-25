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

**A tie sentence must describe the tie it names.** Ann's second phrase says
*tied on major*, and that is a claim about the evidence, not a label for "the
year key ran". Two profiles that both score zero share no major at all; two
identical completed cards are tied on all four factors, not on the major. Both
would be told "tied on major" by a rule that keyed only on which tie-break
column separated them, and both would be wrong. So her phrase is emitted only
when the tie really is on the major — ``same_major`` is the one thing that
counted, **for this name and for the neighbour it tied with** — and every
other tie gets a sentence that names what actually happened.

**Which reason a name gets.** In order, first match wins:

1. The year key decided this name's place against an equal neighbour: Ann's
   sentence when the tie was on major alone, otherwise the sibling phrase.
2. Nothing but the major is on file — Ann's major-only sentence. The trigger is
   the *marker*, not whether the major matched: "for everyone else the reason
   line says so" is about what is on file, and a profile whose major is not a
   target major still has nothing else on file to say.
3. Another key decided the tie — how much is on file, or the fixed order. Each
   names its own key and claims nothing about the major.
4. Otherwise: the factors that contributed, named in Ann's plain words, in
   registry order.
5. Nothing contributed although something is on file — said plainly rather
   than left blank.

Rules 1 and 2 can both be true of one name: a major-only profile whose place
was decided by the year. The requirements list both lines as things "the
reason line says" and do not say which wins, so the choice is
:data:`TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE` — one flag, one line to flip, and
a question recorded for Ann on PR #180 rather than a precedence buried in an
``if``.

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
from smartmatch_domain.student_factors import CAREER_GOAL_FIT_FACTOR_KEY

__all__ = [
    "ANN_MAJOR_ONLY_PHRASE",
    "ANN_TIED_ON_YEAR_PHRASE",
    "TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE",
    "TieBreakKey",
    "exercise_reason",
    "phrase_as_sentence",
]

#: Ann's words for a profile with nothing but a major on file, verbatim from
#: the requirements "Matching" row. Never edited, never reworded.
ANN_MAJOR_ONLY_PHRASE: Final[str] = "same major; nothing else on file"

#: Ann's words for a name the year key placed, verbatim from the same row.
ANN_TIED_ON_YEAR_PHRASE: Final[str] = "tied on major; ordered by year"

#: **PLACEHOLDER (wording pending Ann; see PR #180).** Ann wrote a line for a
#: tie on major and for nothing else. This is the same sentence with the claim
#: it cannot make removed: the year still decided the order, but what the two
#: names were tied on was everything that counted, not the major. No open-question
#: row governs it yet, so it is marked rather than treated as settled.
_TIED_ON_WHAT_COUNTED_YEAR_PHRASE: Final[str] = "tied on what counted; ordered by year"

#: **PLACEHOLDER (wording pending Ann; see PR #180).** The other two tie-break
#: keys, each naming the key that actually decided and claiming nothing about
#: the major. Phrases, not sentences, so they go through the same rendering
#: Ann's two do.
_TIED_ON_INFORMATION_PHRASE: Final[str] = "tied; more information on file first"
_TIED_ON_FIXED_ORDER_PHRASE: Final[str] = "tied; placed in a fixed order that never changes"

#: Whether a tie line replaces Ann's major-only line when both apply — a
#: major-only profile whose place the tie-break decided. The requirements name
#: both lines and rank neither, so the choice is stated here, in one place, and
#: is a question for Ann (PR #180). ``True`` keeps the behaviour the list
#: shipped with: the tie line wins, because it is the more specific account of
#: *why this name is here rather than one row lower*.
TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE: Final[bool] = True

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


#: The phrase for each tie-break key that makes no claim about the major.
#: :attr:`TieBreakKey.YEAR` is absent because it is the one key whose phrase
#: depends on *what* the tie was on; :func:`exercise_reason` chooses it.
_TIE_PHRASES: Final[Mapping[TieBreakKey, str]] = {
    TieBreakKey.INFORMATION: _TIED_ON_INFORMATION_PHRASE,
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


#: Opens the sentence that names the contributing factors. A frame is needed
#: rather than the bare label: "same major" alone is a two-word fragment, which
#: :func:`~smartmatch_domain.one_sentence.assert_one_sentence` refuses — and
#: rightly, because a class participant cannot tell a deliberate fragment from
#: a truncated line. The frame is four plain words and adds no number.
_CONTRIBUTION_OPENER: Final[str] = "what counted"


#: What an undecided career goal's half fit on an exploratory event is called
#: in the reason line (OQ-CE-14). "Career goal fits this event" would be false
#: next to a card that says "Undecided". The team's wording, not Ann's; no number.
_UNDECIDED_GOAL_PHRASE: Final[str] = "undecided goal suits a broad event"


def _factor_phrase(contributing_keys: Sequence[str], *, undecided_goal: bool = False) -> str:
    """The contributing factors named in Ann's words, as one phrase."""
    labels = [
        _UNDECIDED_GOAL_PHRASE
        if undecided_goal and key == CAREER_GOAL_FIT_FACTOR_KEY
        else EXERCISE_FACTOR_LABELS[key]
        for key in contributing_keys
    ]
    if len(labels) == 1:
        joined = labels[0]
    elif len(labels) == 2:
        joined = f"{labels[0]} and {labels[1]}"
    else:
        joined = f"{', '.join(labels[:-1])}, and {labels[-1]}"
    return f"{_CONTRIBUTION_OPENER}: {joined}"


def exercise_reason(
    *,
    marker: InformationMarker,
    contributing_keys: Sequence[str],
    tie_break_key: TieBreakKey = TieBreakKey.NONE,
    tied_on_major: bool = False,
    undecided_goal: bool = False,
) -> str:
    """The one sentence shown next to one name.

    Args:
        marker: The profile's "how much we know" group.
        contributing_keys: The factor keys whose value was known and above
            zero, in registry order.
        tie_break_key: Which tie-break key settled this name's place, or
            :attr:`TieBreakKey.NONE` when no neighbour composed to the same
            value.
        tied_on_major: Whether the tie was on the major *alone* — ``same_major``
            the only thing that counted, for this name and for the neighbour it
            tied with. Ann's "tied on major" sentence is emitted when and only
            when this is true, because otherwise it would be a false statement
            about two names that may share no major at all.
        undecided_goal: Whether "career goal fits this event" counted only as
            an undecided goal's half fit on an exploratory event (OQ-CE-14).
            The factor is then named "undecided goal suits a broad event".

    Returns:
        Exactly one sentence, checked by
        :func:`~smartmatch_domain.one_sentence.assert_one_sentence`. No number
        appears in it (ADR-0025 D8).
    """
    tied = tie_break_key is not TieBreakKey.NONE
    if tied and (TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE or marker is not InformationMarker.MAJOR_ONLY):
        if tie_break_key is TieBreakKey.YEAR:
            return phrase_as_sentence(
                ANN_TIED_ON_YEAR_PHRASE if tied_on_major else _TIED_ON_WHAT_COUNTED_YEAR_PHRASE
            )
        return phrase_as_sentence(_TIE_PHRASES[tie_break_key])
    if marker is InformationMarker.MAJOR_ONLY:
        return phrase_as_sentence(ANN_MAJOR_ONLY_PHRASE)
    if contributing_keys:
        return phrase_as_sentence(_factor_phrase(contributing_keys, undecided_goal=undecided_goal))
    return phrase_as_sentence(_NOTHING_MATCHED_PHRASE)
