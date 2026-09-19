"""The refusal an exercise route raises, in the API's one error envelope.

Why this is not :class:`smartmatch_api.errors.ApiError`
=======================================================

It would be, if it could be. ``errors.py`` imports :mod:`smartmatch_authz` (for
the 403 handler) and :mod:`smartmatch_persistence.idempotency` (for the 409),
and the import-linter contract "Class exercise routers carry no principal or
tenancy" follows chains: an exercise router that imported ``errors`` would
reach both, and the contract would fail — correctly, because the point of the
rule is that an exercise handler cannot get to the authorization machinery by
any path, including a convenient one.

So the *exception* lives here, in a module that imports nothing but the
standard library, and the *rendering* stays in ``errors.py``, which already
owns the envelope and registers a handler for every other exception type in the
application. One envelope, one place that builds it, and no import edge from
the exercise into authz.

Not the CBA error codes
=======================

The codes raised through this class are the exercise's own
(``exercise_no_dataset``, ``exercise_unknown_workspace``, …). A no-login
product answering ``unauthenticated`` or ``forbidden`` would be telling a class
participant that there is an identity they failed to present, and would put the
exercise's refusals in the same namespace a CBA client branches on. There is no
login here; there is a cookie that points at a team's workspace, and a request
that does not carry one has simply not entered a team number yet.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ExerciseError"]


class ExerciseError(Exception):
    """A refusal from an exercise route, carrying its status, code and sentence.

    The message is written as one plain sentence for a class participant to
    read on a projector, per the requirements document's tone throughout. It
    names no table, no column, no identifier and no count — a refusal here is
    read by a student in a marketing class, not by an operator.
    """

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code: Final[int] = status_code
        self.code: Final[str] = code
        self.message: Final[str] = message
