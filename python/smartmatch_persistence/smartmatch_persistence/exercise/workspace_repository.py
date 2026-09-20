"""Team workspaces for the class exercise (design spec §15, §11's reset).

A team enters a number 1-6. The server creates or returns *the* workspace for
``(active dataset, team number)`` and the browser gets an opaque pointer to it.
This module is the whole of that, plus the per-team reset.

ADR-0025 D2 in one sentence
===========================

Every statement here names a table beginning ``exercise_``. There is no
``tenant_id``, no ``owning_unit_id``, no join to ``user_account``, and no
principal: a team is not a tenant and a made-up profile is not an account. The
claim is checked rather than promised — ``tests/unit/test_exercise_persistence_tables.py``
walks every module in this package and refuses a table name that does not carry
the prefix.

What "the active dataset" means today
=====================================

Nothing in the schema marks a dataset active, and this track adds no migration
to give it one. :func:`active_dataset` states the rule in one place —
**most recently uploaded row wins** — so that the instructor track has one
function to replace when "active" becomes a stored fact rather than an ordering.
See its docstring.

It is **not** the rule for where an entry lands. Owner ruling, 2026-09-19: a
team that already has a workspace re-enters *that* workspace, on whatever data
file it is on, and only an instructor re-point moves a team.
:meth:`ExerciseWorkspaceRepository.entry_dataset_for` states that rule, and
``active_dataset`` is the fallback it uses when no team has entered at all.

Transaction boundaries belong to the caller
===========================================

Like every other repository in this package, each method takes a
:class:`~sqlalchemy.orm.Session` and **never commits**. The API's
``get_exercise_session`` rolls back unconditionally, so a route that writes and
forgets to commit returns a clean 2xx and stores nothing. The integration tests
assert against the tables rather than against a response, for that reason.

Nothing here returns an ORM row
===============================

Every method returns a frozen dataclass built from explicitly named columns.
``sa.select(table)`` would carry whatever the table grows next straight into a
response model's ``**row`` — which for this family includes
``exercise_team_workspace.seed`` and ``workspace_token_hash``, neither of which
may ever reach a class participant. Naming the columns is what makes the leak
impossible rather than unlikely.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
    new_workspace_seed,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.settings_repository import lock_saved_settings

__all__ = [
    "WORKSPACE_MEMBERSHIP_LOCK_KEY",
    "ExerciseDatasetSummary",
    "ExerciseWorkspace",
    "ExerciseWorkspaceRepository",
    "active_dataset",
    "lock_workspace_membership",
]

#: The advisory-lock key every statement that changes *which data file a team
#: is in* takes first (review finding F2 on PR #184).
#:
#: **Why an advisory lock and not ``FOR UPDATE``.** ``SELECT … FOR UPDATE``
#: locks the rows it finds. It cannot lock a row that does not exist yet, and
#: the row that breaks a re-point is exactly that one: a team entering at the
#: same moment inserts a *new* ``(target dataset, team N)`` row, which no
#: predicate lock held by the re-point's scan covers, and the re-point's own
#: ``UPDATE`` of some other row to that pair then trips
#: ``uq_exercise_team_workspace_dataset_team`` and aborts the whole transaction
#: — after some teams have already been reset. Both sides taking one
#: transaction-level advisory lock is what makes them take turns.
#:
#: **Derived, not chosen.** A literal would be a number nobody could check
#: against anything; this is the first eight bytes of the SHA-256 of the table's
#: own name, read as PostgreSQL's signed ``bigint``. It is stable across
#: processes and releases because SHA-256 is, and it cannot silently collide
#: with another subsystem's key unless that subsystem picked the same name.
#:
#: **Lock ordering.** This lock is taken **first**, before any row lock, on
#: every path that takes it. One lock always acquired before any other cannot
#: participate in a deadlock cycle with them.
WORKSPACE_MEMBERSHIP_LOCK_KEY: Final[int] = int.from_bytes(
    hashlib.sha256(b"exercise_team_workspace").digest()[:8], "big", signed=True
)


def lock_workspace_membership(session: Session) -> None:
    """Take :data:`WORKSPACE_MEMBERSHIP_LOCK_KEY` for the caller's transaction.

    ``pg_advisory_xact_lock`` rather than ``pg_advisory_lock``: the transaction
    form is released when the transaction ends, whichever way it ends, so a
    caller that raises cannot leave the classroom's entry path wedged until the
    connection is recycled. Nothing has to unlock it and nothing may.

    Blocking rather than ``pg_try_advisory_xact_lock``: the waits here are a
    re-point against a team pressing "enter", measured in milliseconds, and the
    alternative to waiting is refusing one of them for no reason a person in
    the room could act on.

    Re-entrant within a transaction, which is what lets
    :meth:`ExerciseWorkspaceRepository.entry_dataset_for` and
    :meth:`ExerciseWorkspaceRepository.get_or_create_workspace` each call it
    while together holding the key exactly once, continuously, from the
    decision to the commit.

    **Said plainly (OQ-CE-06, owner Danny):** this serialises *every* entry —
    a public, unauthenticated, in-process-rate-limit-free route — on one
    key, per database. Six teams on classroom laptops is nothing, and the work
    inside the lock is three short statements; a deployment that opened this
    route to more than a classroom would want the edge limiting OQ-CE-06 is
    open about before it wanted a finer-grained lock. Behaviour is unchanged
    until that is answered.
    """
    session.execute(sa.select(sa.func.pg_advisory_xact_lock(WORKSPACE_MEMBERSHIP_LOCK_KEY)))


@dataclass(frozen=True, slots=True)
class ExerciseDatasetSummary:
    """The dataset facts a team's entry screen needs, and nothing else.

    No ``checksum``, no ``source_filename``, no ``row_count``: those belong to
    the instructor page, and a value a screen does not show is a value that
    cannot be leaked by a response model written over this dataclass.
    """

    id: uuid.UUID
    label: str
    invite_limit: int


@dataclass(frozen=True, slots=True)
class ExerciseWorkspace:
    """One team's workspace, as the API surface may see it.

    Deliberately carries **no** ``seed`` and **no** ``workspace_token_hash``.
    The seed is the simulated-results rule's business (design spec §11) and the
    hash is the pointer's; a handler that could reach either from the value it
    already has is a handler one ``model_dump()`` away from publishing it. A
    later track that needs the seed adds a read that names it, at which point
    the exception is visible at the call site.

    ``id`` is here because the reset and the token derivation need it. It is
    not on any response model — ``tests/unit/test_exercise_workspace_router.py``
    walks the models and refuses it — because a workspace id in a response
    would be one guessable identifier away from the token that addresses it.
    """

    id: uuid.UUID
    dataset_id: uuid.UUID
    team_number: int
    dataset_label: str
    invite_limit: int


def active_dataset(session: Session) -> ExerciseDatasetSummary | None:
    """The dataset a team entering a number today joins, or ``None``.

    **The rule, stated once, on purpose.** "Active" is the most recently
    uploaded ``exercise_dataset`` row — ``uploaded_at DESC``, then ``id DESC``
    so that two rows written inside the same clock tick still order the same
    way for every reader. There is no ``is_active`` column and this track adds
    no migration to create one; the instructor track (design spec §3, "replace
    the data file") owns the question of whether replacing a file should be a
    stored flag, a re-point of live workspaces, or both, and when it answers,
    **this function is the only thing it has to change**.

    Returns ``None`` when no dataset has been uploaded, which is a real answer
    and not an error: before the instructor loads the student body there is
    nothing for a team to enter. The API turns that ``None`` into one plain
    sentence; the repository does not know what HTTP is.
    """
    table = schema.exercise_dataset
    row = session.execute(
        sa.select(table.c.id, table.c.label, table.c.invite_limit)
        .order_by(table.c.uploaded_at.desc(), table.c.id.desc())
        .limit(1)
    ).one_or_none()
    if row is None:
        return None
    return ExerciseDatasetSummary(id=row.id, label=row.label, invite_limit=row.invite_limit)


class ExerciseWorkspaceRepository:
    """Creates, finds, and resets ``exercise_team_workspace`` rows."""

    def get_or_create_workspace(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        team_number: int,
        workspace_secret: str,
    ) -> ExerciseWorkspace:
        """*The* workspace for ``(dataset_id, team_number)``, creating it if new.

        Race-safe by the constraint rather than by timing. Two laptops on team
        3 pressing "enter" in the same second both run this; both insert;
        ``uq_exercise_team_workspace_dataset_team`` admits one, the other's
        insert is discarded by ``ON CONFLICT DO NOTHING``, and **both then read
        back the same row**. There is no read-then-write window to lose, and no
        second row for team 3 to exist in.

        The token is derived from the row that won (see
        :mod:`smartmatch_domain.exercise.workspace_token` — PLACEHOLDER,
        OQ-CE-08), which is why the loser's discarded hash costs nothing: the
        hash stored is a function of the winning id, and every caller that
        re-derives from the id it read back gets exactly that value.

        **Repairs the stored hash on the way through**, which is what makes
        rotating ``SMARTMATCH_EXERCISE_WORKSPACE_SECRET`` survivable. Without
        it, ``ON CONFLICT DO NOTHING`` keeps the hash derived under the *old*
        secret while this method hands the team a cookie derived under the new
        one, so every later request 401s forever and no amount of re-entering
        the team number fixes it — permanent damage from an operation the
        documentation calls an inconvenience. See :meth:`repair_token_hash` for
        why ``ON CONFLICT DO UPDATE`` cannot do this.

        Args:
            session: Not committed here.
            dataset_id: The active dataset, from :func:`active_dataset`.
            team_number: Already validated against
                ``smartmatch_domain.exercise.EXERCISE_TEAM_NUMBERS`` by the
                caller. The table's ``CHECK (team_number BETWEEN 1 AND 6)`` is
                the backstop, not the validation.
            workspace_secret: The deployment's workspace secret. Used to derive
                the token, never stored and never returned.

        Returns:
            The workspace, joined to its dataset's label and invite limit.

        Raises:
            RuntimeError: if the row cannot be read back after the insert, which
                would mean the dataset was deleted concurrently. Raised rather
                than returning ``None``, because every caller of this method has
                already established that a dataset exists and has no sensible
                branch for "it stopped existing mid-statement".
        """
        # First, and before any row is touched: see
        # :data:`WORKSPACE_MEMBERSHIP_LOCK_KEY`. A re-point holds this while it
        # moves teams, so the insert below cannot land on a pair the re-point
        # has already decided to move into — which is the unique violation that
        # used to abort the whole re-point. Called again here rather than left
        # to the caller: this method is reached from the instructor's tests and
        # tools as well as from ``entry_dataset_for``'s caller, and an advisory
        # lock is re-entrant within a transaction, so asking twice costs one
        # round trip and guarantees the invariant at every entrance.
        lock_workspace_membership(session)
        candidate_id = uuid.uuid4()
        table = schema.exercise_team_workspace
        session.execute(
            pg_insert(table)
            .values(
                id=candidate_id,
                dataset_id=dataset_id,
                team_number=team_number,
                workspace_token_hash=hash_workspace_token(
                    derive_workspace_token(secret=workspace_secret, workspace_id=candidate_id)
                ),
                seed=new_workspace_seed(),
            )
            .on_conflict_do_nothing(constraint="uq_exercise_team_workspace_dataset_team")
        )
        found = self._select_one(
            session,
            table.c.dataset_id == dataset_id,
            table.c.team_number == team_number,
        )
        if found is None:  # pragma: no cover - requires a concurrent dataset delete
            raise RuntimeError(
                "the team workspace could not be read back after insert; "
                "the dataset was removed while the team was entering"
            )
        self.repair_token_hash(session, workspace_id=found.id, workspace_secret=workspace_secret)
        return found

    def entry_dataset_for(self, session: Session, *, team_number: int) -> uuid.UUID | None:
        """Which data file a team entering its number right now lands in.

        **Owner ruling, 2026-09-19: an existing workspace wins over the newest
        data file.** Entry used to go straight to :func:`active_dataset`, so
        the moment the instructor uploaded a file, a team that pressed reload
        was handed a *second*, empty workspace on the new file and its work
        appeared to be gone — while design spec §3 says in as many words that
        uploading moves nobody. Only an instructor re-point moves a team, and
        this function is what makes that true of entry as well as of the table.

        The rule, in three branches, and each one is tested:

        1. **The team already has a workspace** — on any data file — and that
           workspace's file is the answer. This is the ruling.
        2. **A legacy team has workspaces on more than one file.** Nothing
           creates that state any more; rows written before this ruling can
           still be in it. The tie is broken by **the most recently created
           workspace row** (``created_at DESC``, then ``id DESC`` so two rows
           written inside one clock tick still order the same way for every
           reader). That is the file the team most recently entered, which is
           the one whose work it was last looking at — and after any re-point
           the question does not arise, because a re-point leaves each team
           exactly one row.
        3. **A brand-new team**, with no workspace anywhere, joins **the file
           the other teams are on** — again the file carrying the most recently
           created workspace row — so that team 5 arriving late lands in the
           lesson the other five are in rather than in a file nobody else can
           see. With no workspace anywhere at all, the newest upload is the
           answer — the first team of the lesson has no classroom to join — and
           it is read **here, under the lock**, rather than left to the caller
           (review follow-up, PR #186). ``None`` is returned only when no data
           file exists at all, which is the caller's 409.

        One ordering serves branches 2 and 3, which is deliberate: "the data
        file this classroom is most recently working in" is one fact, and
        giving it two definitions is how the two would drift.

        **This reads, and it still takes the lock** (review round 1 on PR
        #186). A decision made outside the lock is a decision that can be stale
        before it is used, and the window is one a classroom produces on its
        own: team 3 presses enter, this method answers "data file A", the
        instructor's re-point — holding the lock — moves team 3 to B and
        commits, and the entry then takes the lock and inserts a **new**
        ``(A, team 3)`` row because the row it read has moved out from under
        it. Team 3 ends up holding two workspaces, branch 2's newest-created
        tie-break pins it to A for good, the re-point silently moved nobody,
        and every instructor action without an explicit ``dataset_id`` refuses
        with "the teams are split across more than one data file".

        So :func:`lock_workspace_membership` is this method's first statement,
        and the caller must run it and the create **in one transaction with no
        commit between them** — which is what ``enter_team_workspace`` does.
        ``get_or_create_workspace``'s own acquire then costs nothing: a
        PostgreSQL advisory lock is re-entrant within a transaction, so the
        second call returns at once and the key is held continuously from the
        decision to the commit. The lock-first ordering is unchanged and still
        total: on every path that takes both, this key is taken before any row
        lock, so it cannot be one edge of a cycle.

        **The fallback is read here too** (review follow-up, PR #186). It used
        to be the caller's: this method returned ``None`` and
        ``enter_team_workspace`` used the ``ActiveDataset`` dependency, which
        had resolved :func:`active_dataset` *before* the lock was taken. So the
        one branch that decides where a brand-new classroom starts was decided
        on a value read outside the lock, and an upload committing in the window
        put the first team of the lesson in a data file that was no longer the
        newest — invisibly, since nothing afterwards disagrees with it. It is a
        narrow window and it is the one branch nothing else corrects, because
        every later team joins whatever this one chose. Reading the newest
        upload inside the lock costs one statement and removes the window.

        ``None`` now means one thing only: **no data file exists at all**. The
        caller's dependency turns that into design spec §3's 409.

        Args:
            session: Not committed here. Reads only, but **does** take a
                transaction-level advisory lock, which the caller's commit or
                rollback releases.
            team_number: The number entered on the laptop.

        Returns:
            The dataset id to open the workspace in, or ``None`` when no data
            file has been uploaded.
        """
        lock_workspace_membership(session)
        table = schema.exercise_team_workspace
        newest_first = (table.c.created_at.desc(), table.c.id.desc())
        own = session.execute(
            sa.select(table.c.dataset_id)
            .where(table.c.team_number == team_number)
            .order_by(*newest_first)
            .limit(1)
        ).one_or_none()
        if own is not None:
            return uuid.UUID(str(own.dataset_id))
        classroom = session.execute(
            sa.select(table.c.dataset_id).order_by(*newest_first).limit(1)
        ).one_or_none()
        if classroom is not None:
            return uuid.UUID(str(classroom.dataset_id))
        # No workspace anywhere: the newest upload, read under the lock this
        # method already holds rather than handed in from before it.
        newest = active_dataset(session)
        return newest.id if newest is not None else None

    def repair_token_hash(
        self, session: Session, *, workspace_id: uuid.UUID, workspace_secret: str
    ) -> bool:
        """Make the stored hash agree with the secret this process is holding.

        The one statement that lets ``SMARTMATCH_EXERCISE_WORKSPACE_SECRET`` be
        rotated. A row written under an older secret carries a hash no cookie
        this process can mint will ever match; re-deriving from the row's own
        id and writing it back restores the invariant the whole design rests
        on — *the stored hash is the hash of the token derived from this row's
        id under this process's secret*.

        **Why not ``ON CONFLICT DO UPDATE``.** The obvious fix is to let the
        insert update the hash on conflict. It cannot: ``EXCLUDED`` carries the
        *losing candidate's* id, so the conflict path would store
        ``SHA-256(HMAC(secret, candidate_id))`` for a row whose id is something
        else entirely — turning a repair into the exact corruption it is meant
        to undo, and doing it on every ordinary entry rather than only after a
        rotation.

        Guarded by ``workspace_token_hash != expected`` so the ordinary case —
        six teams entering their numbers all lesson under an unchanged secret —
        writes no row at all.

        Args:
            session: Not committed here.
            workspace_id: The row to repair. Its own id is the HMAC input, which
                is why nothing else has to be passed.
            workspace_secret: The secret this process booted with.

        Returns:
            ``True`` if a row was rewritten, which means a rotation happened and
            every tab holding an older cookie has just been logged out. They
            lose no work: re-entering the team number returns this same
            workspace, because the workspace is identified by
            ``(dataset, team number)`` and only *addressed* by the token.
        """
        table = schema.exercise_team_workspace
        expected = hash_workspace_token(
            derive_workspace_token(secret=workspace_secret, workspace_id=workspace_id)
        )
        # ``RETURNING id`` rather than ``rowcount``: the row count on a
        # ``Result`` is a DBAPI detail that mypy will not vouch for and that
        # some drivers report as -1. What is wanted is "did a row change", and
        # asking the database to name the changed row answers it directly.
        changed = session.execute(
            sa.update(table)
            .where(table.c.id == workspace_id, table.c.workspace_token_hash != expected)
            .values(workspace_token_hash=expected)
            .returning(table.c.id)
        ).all()
        return bool(changed)

    def find_by_token_hash(self, session: Session, *, token_hash: str) -> ExerciseWorkspace | None:
        """The workspace a cookie addresses, or ``None`` if it addresses nothing.

        Looked up **by hash**, not by comparing a presented token against a
        stored one: the column holds the SHA-256 and the index on it does the
        constant-time work an equality comparison would otherwise have to be
        careful about. ``None`` covers every "no" the same way — a token minted
        under a secret that has since been rotated, one whose workspace was
        deleted, or one simply invented — so the route cannot be used to tell
        those apart.

        A cookie from a **previous dataset** is not on that list, and an earlier
        draft of this docstring wrongly said it was. An upload does not re-point
        live workspaces: design spec §3 has existing workspaces keep pointing at
        their old dataset until the instructor re-points them, and a re-point
        resets every team. So an old cookie keeps resolving, to its own dataset,
        and this lookup is deliberately **not** scoped to the active dataset —
        scoping it would break the spec's stated behaviour in order to make a
        docstring true.
        """
        return self._select_one(
            session, schema.exercise_team_workspace.c.workspace_token_hash == token_hash
        )

    def reset_team(self, session: Session, *, workspace_id: uuid.UUID) -> None:
        """Design spec §11: "A team's reset deletes its overlay, runs, and settings
        and regenerates its seed."

        Four statements, every one of them keyed on ``workspace_id`` and
        therefore incapable of reaching another team's rows — the isolation is a
        key, not a discipline (design spec §2 on the overlay). The workspace row
        itself survives, and so does its token: a reset is a team clearing its
        own work, not a team being logged out of the browser it is sitting at.

        The seed is regenerated because the simulated-results rule is
        deterministic in it. A reset that kept the seed would hand the team the
        same "chance" results it just cleared, which is the one thing a reset in
        a classroom is for.

        ``asking_choice`` and ``refreshed_at`` return to NULL together, which the
        table's ``ck_exercise_team_workspace_refresh_after_choice`` requires —
        clearing the choice while leaving the refresh timestamp would be a
        refresh with no share behind it.

        This module deliberately lets a driver exception reach its caller — a
        team route with its own error envelope — rather than scrubbing it the
        way ``instructor_repository`` does. Since 2026-09-19 that exception
        renders without ``[parameters: …]``, because the shared engine is built
        with ``hide_parameters=True``
        (``smartmatch_persistence.engine.resolve_hide_parameters``). Note the
        remaining gap: PostgreSQL's own ``DETAIL: Failing row contains (…)``
        for a CHECK or NOT NULL refusal is outside that flag's reach, so a
        caller that logs ``str(exc)`` verbatim is still logging row values.

        **Takes the saved-settings key first** (review round 1). Without it a
        reset racing a team's save loses to it: the save holds
        :data:`~smartmatch_persistence.exercise.settings_repository.SAVED_SETTING_LOCK_KEY`
        while it counts and inserts, the reset's ``DELETE`` runs in between and
        under READ COMMITTED simply does not see the uncommitted row, and the
        save then commits — leaving the team holding a setting the reset was
        meant to clear, with no error anywhere to say so. Taking the key makes
        the two take turns, and a reset that waits for a save then deletes what
        it wrote.

        The order is the family's, stated on that constant: membership key, then
        saved-settings key, then row locks. This method takes no membership
        lock, so it cannot be the edge that closes a cycle.

        Not committed here.
        """
        lock_saved_settings(session)
        for child in (
            schema.exercise_profile_overlay,
            schema.exercise_saved_setting,
            schema.exercise_result_run,
        ):
            session.execute(sa.delete(child).where(child.c.workspace_id == workspace_id))
        table = schema.exercise_team_workspace
        session.execute(
            sa.update(table)
            .where(table.c.id == workspace_id)
            .values(
                seed=new_workspace_seed(),
                asking_choice=None,
                refreshed_at=None,
            )
        )

    @staticmethod
    def _select_one(
        session: Session, *conditions: sa.ColumnElement[bool]
    ) -> ExerciseWorkspace | None:
        """One workspace joined to its dataset, with every column named.

        The single read shape in this module, so that "which columns does a
        workspace read carry" has one answer. ``seed`` and
        ``workspace_token_hash`` are absent from it by construction rather than
        dropped afterwards.
        """
        workspace = schema.exercise_team_workspace
        dataset = schema.exercise_dataset
        row = session.execute(
            sa.select(
                workspace.c.id,
                workspace.c.dataset_id,
                workspace.c.team_number,
                dataset.c.label,
                dataset.c.invite_limit,
            )
            .select_from(workspace.join(dataset, workspace.c.dataset_id == dataset.c.id))
            .where(*conditions)
        ).one_or_none()
        if row is None:
            return None
        return ExerciseWorkspace(
            id=row.id,
            dataset_id=row.dataset_id,
            team_number=row.team_number,
            dataset_label=row.label,
            invite_limit=row.invite_limit,
        )
