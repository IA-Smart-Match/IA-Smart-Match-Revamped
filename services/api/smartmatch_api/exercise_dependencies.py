"""The one database door for class-exercise routers (ADR-0025 D2).

The exercise routers are forbidden the CBA request machinery: no
``smartmatch_api.dependencies``, no ``smartmatch_authz``, no tenant-scoped
repository, and no ``request.app.state`` poking of their own. That rule is
enforced by the import-linter contract "Class exercise routers carry no
principal or tenancy" and by the source walk in
``tests/unit/test_exercise_router_reachability.py``.

A rule with no door is a rule that gets broken the first time somebody needs a
row. The exercise's later tracks — CE-WORKSPACE, CE-SIMULATION, CE-INGEST,
CE-INSTRUCTOR — genuinely need to read and write the ``exercise_`` tables, so
this module is that door, named now, before anybody needs it, so that "the
exercise router reached the database" has exactly one shape a reviewer has to
recognise.

**This is the only way an exercise router may reach a database session, and the
repositories used behind it may touch only ``exercise_``-prefixed tables**
(ADR-0025 D2: those tables carry no ``tenant_id``, no ``owning_unit_id``, and no
foreign key to ``user_account``). A repository behind this dependency that
selected from ``user_account``, ``membership``, ``event``, or any other CBA
table would be the process mixing ADR-0025 D1 exists to prevent, and no test
here can see inside a repository — that half is the reviewer's, and this
paragraph is what they are checking against.

Why not ``smartmatch_api.dependencies.get_session``
===================================================

It would work, and that is the problem. That module also defines
``get_current_principal``, ``CurrentPrincipal``, ``charge_quota`` and the
rate-limit machinery, all of which need a ``ResolvedPrincipal``. An exercise
router that imported it for a session would have the principal one name away,
and the import-linter contract that makes the absence structural would have to
be dropped to allow it. Two functions that look alike are cheaper than one
import that opens a door nobody meant to open.

This module deliberately holds **nothing else**. No principal, no quota, no
authorization, no query. It is imported by exercise routers and by nothing
else.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

__all__ = ["ExerciseSession", "get_exercise_session"]


def get_exercise_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session for the ``exercise_`` tables.

    Rolled back rather than committed on exit, for
    ``smartmatch_api.dependencies.get_session``'s reason: a route that changes
    state commits explicitly, and anything that got here without committing
    either failed or only read. Committing by default would turn a half-finished
    request into a persisted one.

    Issues no query of its own. The session comes from the process-wide factory
    the ``lifespan`` builds in *every* scope — the exercise has its own tables
    and will need it; what it must not have is a principal.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


#: The annotation an exercise route handler writes.
#:
#: Exported as an alias so a handler can take a session without importing
#: SQLAlchemy — which is what lets "class exercise routers do not touch
#: SQLAlchemy directly" be a contract in ``pyproject.toml`` rather than a habit.
ExerciseSession = Annotated[Session, Depends(get_exercise_session)]
