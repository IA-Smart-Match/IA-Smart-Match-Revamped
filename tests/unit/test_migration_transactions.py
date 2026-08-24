"""Transaction boundaries in the generated migration script.

What this pins is a property of ``db/migrations/env.py`` rather than of any one
revision: each revision is applied in its own transaction, so a lock taken by a
revision is released when *that revision* ends rather than when the whole
``alembic upgrade`` run commits.

This lives in the unit lane because offline mode never opens a connection — the
URL below is deliberately unreachable, and the script is still emitted. That
matters: it means the decision recorded in ADR-0009 stays protected on a machine
with no PostgreSQL, which is not true of anything else that touches migrations.

**Scope, stated honestly.** This exercises ``run_migrations_offline``. The online
path is the same ``transaction_per_migration`` decision at a different call
site, and while ``0003`` is head there is no online-observable difference at all
— the lock is taken in the final revision, so it is released at the end of the
run either way. No online test can fail-before and pass-after today, and a test
that raced an upgrade against another connection to catch an intermediate
``alembic_version`` would be timing-dependent against migrations that finish in
milliseconds. A flaky test asserting a transaction boundary is worse than no
test. The online call site is covered by review, and by sitting three lines from
this one in a small file.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Offline mode never connects, so this URL is never dialled. Pointing it at a
#: closed port is the assertion: if a future change made the offline path open a
#: connection, this test would fail loudly rather than quietly start depending
#: on a live database.
_UNREACHABLE_URL = "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nope"

_BEGIN = re.compile(r"^BEGIN;", re.MULTILINE)
_COMMIT = re.compile(r"^COMMIT;", re.MULTILINE)
_RUNNING_UPGRADE = re.compile(r"^-- Running upgrade", re.MULTILINE)


def _transaction_blocks(script: str) -> list[str]:
    """The script's transactional regions, in order.

    Counting ``BEGIN`` statements and comparing the total to the revision count
    is tempting and wrong: ``op.get_context().autocommit_block()`` — the form
    ``CREATE INDEX CONCURRENTLY`` requires — makes Alembic close the surrounding
    transaction and open a fresh one afterwards, so a *correct* four-revision
    script containing one autocommit block emits five ``BEGIN``/``COMMIT``
    pairs. An equality assertion would reject exactly the pattern ADR-0009
    prescribes.

    What survives that is the containment property, which is what the setting
    actually buys: no single transaction may span more than one revision.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    for line in script.splitlines():
        if line.startswith("BEGIN;"):
            current = []
            continue
        if line.startswith("COMMIT;"):
            if current is not None:
                blocks.append("\n".join(current))
            current = None
            continue
        if current is not None:
            current.append(line)
    return blocks


def _offline_script() -> str:
    """Emit the full upgrade script the way a reviewing DBA would.

    ``sys.executable -m alembic`` rather than the console script, for the same
    reason ``test_principal_identity._alembic`` does it: the interpreter running
    the tests is the one running Alembic, and there is no virtualenv layout to
    guess.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "base:head", "--sql"],
        cwd=_REPO_ROOT / "db",
        env=dict(os.environ, SMARTMATCH_DATABASE_URL=_UNREACHABLE_URL),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, f"offline script generation failed: {completed.stderr}"
    return completed.stdout


def test_each_revision_is_its_own_transaction():
    """No transaction may span more than one revision.

    Asserted as containment rather than as a count of ``BEGIN`` statements, so
    that a future revision using ``autocommit_block()`` — which legitimately
    adds a ``COMMIT``/``BEGIN`` pair — does not fail a test that is supposed to
    be protecting it. See :func:`_transaction_blocks`.
    """
    script = _offline_script()

    revisions = len(_RUNNING_UPGRADE.findall(script))
    assert revisions >= 3, (
        "expected at least the three revisions that exist; "
        f"found {revisions} — has the script format changed?"
    )

    assert len(_BEGIN.findall(script)) == len(_COMMIT.findall(script)), (
        "unbalanced BEGIN/COMMIT: the script leaves a transaction open."
    )

    blocks = _transaction_blocks(script)
    oversized = [
        index for index, block in enumerate(blocks) if len(_RUNNING_UPGRADE.findall(block)) > 1
    ]
    assert not oversized, (
        f"transaction(s) {oversized} span more than one revision. A lock taken "
        "by one revision is then held until the whole run commits — see "
        "ADR-0009."
    )

    covered = sum(len(_RUNNING_UPGRADE.findall(block)) for block in blocks)
    assert covered == revisions, (
        f"{revisions} revisions but only {covered} are inside a transaction; "
        "a revision applying outside one would not roll back on failure."
    )


def test_the_user_account_lock_is_released_with_its_own_revision():
    """``0003``'s ``ACCESS EXCLUSIVE`` lock must not outlive its revision.

    This is the concrete consequence the setting exists for, and it is the one
    that stops being hypothetical the moment a ``0004`` exists: upgrading a live
    database from ``0002`` would otherwise hold ``user_account`` locked across
    ``0003``, ``0004``, and everything after it in the same run — blocking every
    authenticated request for the whole upgrade rather than for an index build.
    """
    script = _offline_script()

    lock_at = script.find("LOCK TABLE user_account")
    assert lock_at != -1, (
        "0003 no longer takes an explicit lock on user_account; if that is "
        "deliberate, this test should be re-aimed rather than deleted."
    )

    # Located by regex rather than string offsets: the first BEGIN sits at the
    # very start of the file, so searching for a leading newline misses it and
    # reports "not in a transaction" for a script that plainly is one.
    opens_before = [m.start() for m in _BEGIN.finditer(script) if m.start() < lock_at]
    assert opens_before, "the lock is not inside a transaction at all"
    opening = max(opens_before)

    closes_after = [m.start() for m in _COMMIT.finditer(script) if m.start() > lock_at]
    assert closes_after, "the transaction holding the lock is never committed"
    closing = min(closes_after)

    enclosing = script[opening:closing]
    revisions_sharing_the_lock = len(_RUNNING_UPGRADE.findall(enclosing))
    assert revisions_sharing_the_lock == 1, (
        f"{revisions_sharing_the_lock} revisions share the transaction holding "
        "the user_account lock; it must be held by exactly one."
    )


def test_creating_an_index_concurrently_never_appears_inside_a_transaction():
    """A guard against the conflation ADR-0009 exists to prevent.

    ``transaction_per_migration=True`` gives each revision *its own*
    transaction. It does not give any revision *no* transaction, which is what
    ``CREATE INDEX CONCURRENTLY`` requires — that still needs
    ``op.get_context().autocommit_block()`` inside the revision.

    This asserts *position*, not absence. A correct ``CONCURRENTLY`` migration
    emits the statement between an emitted ``COMMIT`` and the following
    ``BEGIN``, and must pass; one written on the assumption that this setting
    was enough emits it inside a transaction, and would fail at run time
    against PostgreSQL. Verified empirically against a probe revision before
    this test was written.
    """
    script = _offline_script()

    assert _BEGIN.search(script), (
        "no BEGIN at all: revisions are no longer transactional, which would "
        "make this repository's rollback story different from the one ADR-0009 "
        "records."
    )

    offenders = [block for block in _transaction_blocks(script) if "CONCURRENTLY" in block.upper()]
    assert not offenders, (
        "a revision emits CONCURRENTLY inside a transaction; PostgreSQL "
        "refuses that at run time. Wrap it in "
        "op.get_context().autocommit_block() — see ADR-0009."
    )
