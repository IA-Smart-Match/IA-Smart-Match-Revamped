"""The one-sentence rule, as a checked contract.

Customer §9 asks Topic matching to return "a simple Topic fit score" **and**
"one sentence explaining the reasoning". The second half is a contract, not a
style preference, and it is the half that decays silently: a rationale is the
one field on a match whose only consumer is a human, so nothing downstream ever
notices when it grows to three sentences of hedging, shrinks to a fragment, or
arrives blank.

It lives in its own module, rather than beside either the factor or the
explanation, so that both can enforce it without importing each other. The
factor checks it when a score is constructed, the fixture provider checks it
when a comparison is *recorded*, and the explanation checks it again when the
sentence is about to be rendered. Three checks on one rule is not redundancy
here: each is the last chance at a different boundary.

**What counts as one sentence.** A declarative statement ending in a single
full stop. Deliberately strict on three counts, each of which has a reason:

* A question or an exclamation is refused. A rationale states what the evidence
  showed; "Does their work match?" is not an account of anything.
* A fragment is refused — both the unterminated kind ("matches the request")
  and the one-word kind ("Matches."). A fragment reads as a truncation, and a
  Speaker Connector cannot tell a deliberate one from a lost half.
* A full stop only ends a sentence when what follows it is whitespace or the
  end of the string. This is what lets the approved neutral basis, which
  contains the policy version ``1.0.0``, remain one sentence rather than three.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "MINIMUM_SENTENCE_WORDS",
    "OneSentenceRationaleError",
    "assert_one_sentence",
]

#: Fewest words a rationale may contain before it is a fragment rather than a
#: sentence. Three is the smallest count that admits a subject, a verb, and an
#: object — the least a reason can say and still be a reason.
MINIMUM_SENTENCE_WORDS: Final[int] = 3

#: A full stop, question mark, or exclamation mark that actually ends a
#: sentence: one followed by whitespace or by the end of the string. A dot
#: inside ``1.0.0`` is followed by a digit and so is not a boundary.
_SENTENCE_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"[.!?](?=\s|$)")


class OneSentenceRationaleError(ValueError):
    """Raised when a rationale is not exactly one declarative sentence.

    A subclass of :class:`ValueError` so that a caller which already refuses
    malformed domain input keeps refusing this too without a second except
    clause, while a caller that wants to report the sentence rule specifically
    still can.
    """


def assert_one_sentence(text: str, *, field: str) -> str:
    """Return ``text`` unchanged if it is exactly one sentence, else raise.

    Args:
        text: The candidate rationale.
        field: The name of the field being checked, so the failure names the
            thing the caller has to fix rather than the rule it broke.

    Returns:
        ``text`` exactly as given, so this can be used inline where the value
        is assigned. Note it is *not* stripped: normalizing the caller's text
        would be a quiet repair, and a rationale with stray whitespace is
        worth surfacing rather than tidying away.

    Raises:
        OneSentenceRationaleError: if ``text`` is blank, does not end in a
            single full stop, contains more than one sentence boundary, or is
            too short to be a sentence at all.
    """
    stripped = text.strip()

    if not stripped:
        raise OneSentenceRationaleError(
            f"{field}: must be exactly one sentence; got a blank string. "
            "Customer §9 requires one sentence of reasoning, and an empty "
            "rationale is an unexplained score."
        )

    if not stripped.endswith("."):
        raise OneSentenceRationaleError(
            f"{field}: must be exactly one sentence ending in a full stop; got {stripped!r}. "
            "A fragment, a question, or an exclamation is not an account of the evidence."
        )

    boundaries = _SENTENCE_BOUNDARY.findall(stripped)
    if len(boundaries) != 1:
        raise OneSentenceRationaleError(
            f"{field}: must be exactly one sentence; got {len(boundaries)} in {stripped!r}. "
            "Not two, and not a paragraph — the surface that renders this has room for one."
        )

    words = stripped.rstrip(".").split()
    if len(words) < MINIMUM_SENTENCE_WORDS:
        raise OneSentenceRationaleError(
            f"{field}: must be exactly one sentence, not a fragment; got {stripped!r}, "
            f"which is under {MINIMUM_SENTENCE_WORDS} words."
        )

    if not stripped[0].isupper():
        raise OneSentenceRationaleError(
            f"{field}: must be exactly one sentence beginning with a capital letter; "
            f"got {stripped!r}. A lowercase opening usually means a sentence lost its start."
        )

    return text
