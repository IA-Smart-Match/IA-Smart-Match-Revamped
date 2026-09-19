"""The fixed random order, and the digest it is derived from.

Design spec §4.4's last tie-break is "a fixed random order that never changes"
(requirements, "Matching"). *Never changes* is the whole requirement, and it is
the one a plausible implementation gets wrong without failing anywhere else:

* ``hash()`` of a string is salted per process (``PYTHONHASHSEED``), so an
  order derived from it differs between today's process and tomorrow's.
* ``random.seed(some_string)`` inherits the same salt through the same hash,
  and ``random.shuffle`` additionally depends on the Mersenne Twister's
  implementation, which is a runtime detail rather than a promise.

So the order here is a pure function of the dataset checksum and the profile
numbers, through SHA-256 over length-prefixed fields — the same construction
:mod:`smartmatch_domain.exercise.simulation` uses for its chance draws, shared
rather than copied. Two teams, two processes, two machines, and two Python
versions all produce the same permutation for the same dataset.

The checksum, not the dataset id, is what seeds it: two uploads of the same
file give the same order, and a different file gives a different one, which is
what "fixed for this data" means.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from types import MappingProxyType

__all__ = [
    "exercise_permutation",
    "permutation_key",
    "stable_digest",
]


def stable_digest(*fields: object) -> bytes:
    """A stable SHA-256 digest over some fields, each one length-prefixed.

    Length-prefixed rather than joined by ``":"`` so that a field containing
    the separator cannot produce the digest of a different set of fields. A
    dataset checksum and an event key are both free text from a data file, so
    this is reachable rather than theoretical.
    """
    hasher = hashlib.sha256()
    for field in fields:
        encoded = str(field).encode()
        hasher.update(f"{len(encoded)}:".encode())
        hasher.update(encoded)
    return hasher.digest()


def permutation_key(dataset_checksum: str, profile_no: int) -> bytes:
    """One profile's place in the fixed order, as an orderable key.

    The digest itself, so the ordering is the ordering of 32 independent bytes
    — stable across runs, teams, processes, and interpreter versions, and
    depending on nothing but its two arguments.
    """
    return stable_digest(dataset_checksum, profile_no)


def exercise_permutation(dataset_checksum: str, profile_nos: Iterable[int]) -> Mapping[int, int]:
    """The fixed shuffle of a dataset's profile numbers.

    Args:
        dataset_checksum: The checksum of the loaded data file. The whole of
            the seed.
        profile_nos: Every profile number in the dataset. Duplicates are
            refused: a permutation of a multiset is not a permutation.

    Returns:
        An immutable ``{profile_no: position}`` mapping over ``0 .. n-1``,
        ordered by each profile's :func:`permutation_key` and, should two
        digests ever collide, by the profile number itself — so the result is
        a total order under every input rather than merely under almost all of
        them.

    Raises:
        ValueError: when ``profile_nos`` contains a duplicate.
    """
    numbers = tuple(profile_nos)
    if len(set(numbers)) != len(numbers):
        raise ValueError("profile_nos: duplicate profile number in the dataset")
    ordered = sorted(
        numbers, key=lambda number: (permutation_key(dataset_checksum, number), number)
    )
    return MappingProxyType({number: position for position, number in enumerate(ordered)})
