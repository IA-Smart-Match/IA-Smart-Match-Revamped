"""Weight settings are durable, audited, and cannot reach a run already recorded.

Three claims this card makes, checked against the database rather than against a
return value:

1. **A change is stored.** ``get_session`` rolls back unconditionally, so a route
   that returned 200 without committing would look identical to one that worked.
   Every persistence assertion here reads the table on a *separate* connection.
2. **A change is logged, and the log cannot be rewritten.** One revision row per
   accepted version, and migration ``0027``'s trigger refuses an ``UPDATE``.
3. **A change cannot alter a historical run.** The proof drives the real worker
   path — accept, dispatch, execute — records a run under one weighting, changes
   the weighting, and requires the stored run to still report the weights it was
   scored with.

That third one goes through the worker rather than over HTTP on purpose.
OQ-CBA-031 records that ``POST /v1/units/{unit_id}/match-runs`` still scores with
``rank_candidates`` under the superseded composition, so no run is yet stored
under registry ``2.0.0`` through any client path. The durable command path *is*
the path that writes a ``match_run`` row (card M8a: "executed through the
existing durable-command path"), so proving the snapshot there proves it where it
actually happens — and the proof keeps holding when OQ-CBA-031 closes, because
closing it changes the caller and not the writer.

## Why this file is not called ``test_cba_weight_settings.py``

The card asked for that name and it cannot have it. ``tests/unit/`` already holds
a ``test_cba_weight_settings.py``, and this repository runs pytest in the default
*prepend* import mode with no ``__init__.py`` anywhere under ``tests/``, which
makes a test module's identity its bare basename. Two files sharing one basename
is a collection error for the whole run — not a warning — and every other
basename in this tree is unique, which is the invariant that keeps ``pytest
tests`` working at all.

Both escapes were worse. ``--import-mode=importlib`` drops the
directory-insertion that ``from conftest import ...`` depends on, and roughly
forty integration modules do that. Adding ``__init__.py`` files changes the same
resolution for every file in the directory at once. So this file carries the
suffix and the unit file keeps the card's name.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from conftest import unique_subject
from smartmatch_domain.factor_registry import CBA_PHYSICAL_MODEL, normalize_weights
from smartmatch_domain.factors.industry_match import INDUSTRY_MATCH_FACTOR_KEY
from smartmatch_domain.factors.role_match import ROLE_MATCH_FACTOR_KEY
from smartmatch_domain.jobs import JobState
from smartmatch_domain.match_run import MATCH_RUN_COMMAND_TYPE, weights_fingerprint
from smartmatch_domain.weight_settings import applied_weights, validate_weight_overrides
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.match_weight_settings import (
    MatchWeightSettingRepository,
    StaleWeightSettingsError,
)
from smartmatch_persistence.outbox import OutboxRepository
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import default_registry
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: This card's revision, and the head it must be once this card lands.
_THIS_REVISION = "0027_match_weight_setting"

#: The revision it chains to — the head before this card, taken from the
#: ``revision =`` line rather than from a filename. Alembic revision ids are not
#: filenames, and reading one off a directory listing is how a chain gets
#: attached to the wrong link.
_PREVIOUS_REVISION = "0026_event_registration"

#: The head, which is no longer this card's revision. ``CBA-IMPORT-CLASSIFY``
#: added ``0028_classification_provenance`` on top of ``0027``, so the head
#: assertion below moved off :data:`_THIS_REVISION` rather than being deleted —
#: an assertion softened to "some head exists" would still pass on the day two
#: of them do, which is the failure it exists to catch.
#:
#: The two constants are now genuinely different things and are kept apart on
#: purpose: :data:`_THIS_REVISION` is what this card added and what the chain
#: test below pins, and this is where the graph currently ends. Collapsing them
#: back into one name is what would let the next card's bump silently rewrite
#: this file's claim about its own revision.
#:
#: ``0028`` composes with ``0027``: it touches ``speaker_profile`` only, adding
#: six nullable columns and two ``CHECK``s over them, and neither
#: ``match_weight_setting`` nor its revision log is read or written by it.
_HEAD_REVISION = "0028_classification_provenance"

NEED = "need-weight-settings-1"

#: A synthetic pool. The utilities are invented for this file and stand for
#: "already scored by whoever assembled the pool"; they are not a claim about any
#: real professional, and nothing here computes them.
POOL = (
    {"subject_id": "prof-weights-a", "utility": 0.82},
    {"subject_id": "prof-weights-b", "utility": 0.4},
    {"subject_id": "prof-weights-c", "utility": 0.61},
)
PORTFOLIO_SIZE = 2

_settings = MatchWeightSettingRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _script_directory():
    """The Alembic script directory, loaded from ``db/alembic.ini``.

    Imported inside the function rather than at module scope, so the revision
    tests skip cleanly where Alembic is not installed instead of failing
    collection for this whole module.
    """
    alembic_config = pytest.importorskip("alembic.config")
    alembic_script = pytest.importorskip("alembic.script")

    config = alembic_config.Config(str(_REPO_ROOT / "db" / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "db" / "migrations"))
    return alembic_script.ScriptDirectory.from_config(config)


def _an_account(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account`` to attribute a settings change to.

    Routed through :func:`conftest.unique_subject` because ``external_subject``
    is globally unique as of migration ``0003``; ``0007`` dropped the
    tenant-scoped constraint that used to stand beside it.
    """
    account_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": account_id,
            "tid": tenant_id,
            "sub": unique_subject(f"weights-{account_id.hex[:8]}"),
            "email": f"{account_id.hex[:8]}@example.edu",
        },
    )
    return account_id


@pytest.fixture
def actor_id(engine, tenant_id) -> uuid.UUID:
    with engine.begin() as conn:
        return _an_account(conn, tenant_id)


def _stored_setting(engine, tenant_id: uuid.UUID):
    """Read the settings row on a fresh connection.

    A *separate* connection, deliberately. Reading through the session that wrote
    would see uncommitted work, and would report a route that never committed as
    a route that stored something.
    """
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM match_weight_setting WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).one_or_none()


def _stored_revisions(engine, tenant_id: uuid.UUID):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT * FROM match_weight_setting_revision WHERE tenant_id = :tid "
                "ORDER BY version"
            ),
            {"tid": tenant_id},
        ).all()


def _write(session_factory, tenant_id, unit_id, actor, overrides, expected_version=None):
    """Put a setting through the repository and commit, as the route does."""
    with session_factory() as session:
        record = _settings.put(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            overrides=validate_weight_overrides(overrides),
            actor_user_id=actor,
            expected_version=expected_version,
        )
        session.commit()
    return record


def _payload() -> dict[str, object]:
    """A CBA physical run.

    ``scoring_mode`` is named rather than omitted, and that matters here: under
    ADR-0016 Proposal 7 a command naming no mode resolves to
    ``SUPERSEDED_G1_MODEL``, whose two factors are ``topic_relevance`` and
    ``travel_burden``. Those are not configurable — ``CONFIGURABLE_FACTOR_KEYS``
    is the registry's *approved* set — so a run under that model would ignore
    every override and this file would be asserting nothing.
    """
    return {
        "event_need_id": NEED,
        "portfolio_size": PORTFOLIO_SIZE,
        "random_seed": 0,
        "scoring_mode": CBA_PHYSICAL_MODEL.scoring_mode,
        "candidates": [dict(candidate) for candidate in POOL],
    }


def _accept(session_factory, tenant_id, unit_id) -> uuid.UUID:
    """Accept a match-run command the way ``submit_command`` does."""
    with session_factory() as session:
        job = JobRepository().create(
            session,
            tenant_id=tenant_id,
            command_type=MATCH_RUN_COMMAND_TYPE,
            owning_unit_id=unit_id,
            payload=_payload(),
        )
        OutboxRepository().enqueue(
            session, tenant_id=tenant_id, job_id=job.id, command_type=MATCH_RUN_COMMAND_TYPE
        )
        session.commit()
    return job.id


def _execute(session_factory, tenant_id, job_id):
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    return TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )


# ---------------------------------------------------------------------------
# The revision graph. No database.
# ---------------------------------------------------------------------------


def test_there_is_exactly_one_head_and_it_is_the_provenance_revision():
    """One head, and it is :data:`_HEAD_REVISION`.

    Two heads is the failure mode of parallel migration work and it is quiet:
    Alembic refuses ``upgrade head`` with an ambiguity error only at deploy time,
    on a branch that has already merged. Asserting the *name* as well as the
    count means a later card extending the chain has to come here and say so,
    which is the point at which somebody checks that the two revisions compose.

    ``CBA-IMPORT-CLASSIFY`` is the first card to do that here. This card's own
    revision is now a link rather than the end, so the assertion moved to
    :data:`_HEAD_REVISION` — and the chain test below still pins
    :data:`_THIS_REVISION` to its parent, so nothing about this card's place in
    the graph stopped being asserted.
    """
    heads = _script_directory().get_heads()

    assert heads == [_HEAD_REVISION], (
        f"expected {_HEAD_REVISION} to be the single Alembic head, got {heads}. "
        "More than one head means `alembic upgrade head` is ambiguous; a "
        "different single head means a revision was added without this "
        "assertion being updated."
    )


def test_this_revision_chains_to_the_registration_revision():
    """``0027`` follows ``0026``, so ``0026`` stays reachable from ``head``.

    The head test above would pass on a ``0027`` that branched from ``0025`` and
    left ``0026`` on a second head only if the graph happened to collapse — and
    it would not. This states the link directly.
    """
    script = _script_directory().get_revision(_THIS_REVISION)

    assert script.down_revision == _PREVIOUS_REVISION


# ---------------------------------------------------------------------------
# The write is durable, and asserted against the table
# ---------------------------------------------------------------------------


def test_a_unit_with_no_row_has_no_settings_and_that_is_a_real_answer(
    session_factory, tenant_id, owning_unit_id
):
    """``None`` rather than an empty settings object — different histories."""
    with session_factory() as session:
        assert _settings.get(session, tenant_id=tenant_id, owning_unit_id=owning_unit_id) is None
        assert (
            dict(
                _settings.overrides_for(session, tenant_id=tenant_id, owning_unit_id=owning_unit_id)
            )
            == {}
        )


def test_a_written_setting_is_in_the_table_not_only_in_the_response(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """The check two earlier tracks in this repository needed and did not have.

    A repository that never commits and a route that forgets to are
    indistinguishable from the return value, so this reads the row back on
    another connection.
    """
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})

    row = _stored_setting(engine, tenant_id)
    assert row is not None, "the change was reported but not stored"
    assert row.owning_unit_id == owning_unit_id
    assert row.version == 1
    assert row.updated_by_user_id == actor_id
    assert row.overrides == {INDUSTRY_MATCH_FACTOR_KEY: 5.0}


def test_only_the_overridden_factors_are_stored(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """The rule this whole card exists for, checked at the storage boundary.

    A row carrying all four approved weights would be a second copy of the
    registry's figures. What is stored is the one factor somebody changed.
    """
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {ROLE_MATCH_FACTOR_KEY: 2.0})

    row = _stored_setting(engine, tenant_id)
    assert set(row.overrides) == {ROLE_MATCH_FACTOR_KEY}, (
        "a registry default was persisted alongside the override; settings are an "
        "override layer and the registry is the only place a default lives"
    )


def test_a_reset_stores_an_empty_map_rather_than_the_registry_values(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """Clearing an override deletes the entry; it does not write the default back."""
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {})

    row = _stored_setting(engine, tenant_id)
    assert row.overrides == {}
    assert row.version == 2, "a reset is a change, and a change advances the version"


def test_each_accepted_change_appends_one_revision(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {ROLE_MATCH_FACTOR_KEY: 3.0})

    revisions = _stored_revisions(engine, tenant_id)
    assert [row.version for row in revisions] == [1, 2]
    assert revisions[0].overrides == {INDUSTRY_MATCH_FACTOR_KEY: 5.0}
    assert revisions[1].overrides == {ROLE_MATCH_FACTOR_KEY: 3.0}
    assert all(row.changed_by_user_id == actor_id for row in revisions)


def test_a_revision_cannot_be_rewritten(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """Migration ``0027``'s trigger, exercised rather than assumed.

    A guarantee nothing attempts to violate is a guarantee nobody knows is still
    there — ``test_match_run_snapshot.py`` makes the same argument about ``0018``.
    """
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})

    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE match_weight_setting_revision SET overrides = '{}'::jsonb "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )


def test_a_stale_expected_version_is_refused(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """The lost update, refused. Two Connectors with the page open is the ordinary case."""
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})

    with pytest.raises(StaleWeightSettingsError), session_factory() as session:
        _settings.put(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            overrides={ROLE_MATCH_FACTOR_KEY: 9.0},
            actor_user_id=actor_id,
            expected_version=7,
        )

    assert _stored_setting(engine, tenant_id).overrides == {INDUSTRY_MATCH_FACTOR_KEY: 5.0}


def test_the_current_version_is_accepted_as_expected_version(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    _write(session_factory, tenant_id, owning_unit_id, actor_id, {INDUSTRY_MATCH_FACTOR_KEY: 5.0})
    _write(
        session_factory,
        tenant_id,
        owning_unit_id,
        actor_id,
        {ROLE_MATCH_FACTOR_KEY: 3.0},
        expected_version=1,
    )

    assert _stored_setting(engine, tenant_id).version == 2


def test_the_database_refuses_a_non_object_override_payload(engine, tenant_id, owning_unit_id):
    """``ck_match_weight_setting_overrides_object``, exercised.

    The domain refuses far more than this; the constraint is the floor under a
    write that never went through the domain at all.
    """
    with engine.begin() as conn:
        account = _an_account(conn, tenant_id)

    with pytest.raises(IntegrityError, match="overrides_object"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO match_weight_setting "
                "(id, tenant_id, owning_unit_id, overrides, version, updated_by_user_id) "
                "VALUES (:id, :tid, :uid, '[]'::jsonb, 1, :actor)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": owning_unit_id, "actor": account},
        )


def test_the_database_refuses_a_version_below_one(engine, tenant_id, owning_unit_id):
    """``ck_match_weight_setting_version``. Versions start at 1 and only rise.

    A zero or negative version could not have come from an accepted change, and
    a row carrying one would make ``expected_version`` — the whole
    lost-update defence — compare against a number nobody wrote.
    """
    with engine.begin() as conn:
        account = _an_account(conn, tenant_id)

    with (
        pytest.raises(IntegrityError, match="ck_match_weight_setting_version"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO match_weight_setting "
                "(id, tenant_id, owning_unit_id, overrides, version, updated_by_user_id) "
                "VALUES (:id, :tid, :uid, '{}'::jsonb, 0, :actor)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": owning_unit_id, "actor": account},
        )


def test_the_revision_log_refuses_a_non_object_payload(engine, tenant_id, owning_unit_id):
    """``ck_match_weight_setting_revision_overrides_object``.

    The log gets the same floor the settings row does. A revision recording an
    array would be an entry nobody could read back as a weighting, in the one
    table that is supposed to be readable years later.
    """
    with engine.begin() as conn:
        account = _an_account(conn, tenant_id)

    with pytest.raises(IntegrityError, match="revision_overrides_object"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO match_weight_setting_revision "
                "(id, tenant_id, owning_unit_id, overrides, version, changed_by_user_id) "
                "VALUES (:id, :tid, :uid, '\"nonsense\"'::jsonb, 1, :actor)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": owning_unit_id, "actor": account},
        )


def test_the_revision_log_refuses_a_version_below_one(engine, tenant_id, owning_unit_id):
    """``ck_match_weight_setting_revision_version``.

    The log's versions are the settings row's versions; a zero here would be an
    entry claiming to describe a state that never existed.
    """
    with engine.begin() as conn:
        account = _an_account(conn, tenant_id)

    with (
        pytest.raises(IntegrityError, match="ck_match_weight_setting_revision_version"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO match_weight_setting_revision "
                "(id, tenant_id, owning_unit_id, overrides, version, changed_by_user_id) "
                "VALUES (:id, :tid, :uid, '{}'::jsonb, 0, :actor)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": owning_unit_id, "actor": account},
        )


# ---------------------------------------------------------------------------
# The snapshot, and what a later change cannot touch
# ---------------------------------------------------------------------------


def test_a_run_records_the_weights_this_unit_actually_configured(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """The applied weights are the unit's, not the registry's bare defaults."""
    overrides = {INDUSTRY_MATCH_FACTOR_KEY: 9.0}
    _write(session_factory, tenant_id, owning_unit_id, actor_id, overrides)

    job_id = _accept(session_factory, tenant_id, owning_unit_id)
    outcome = _execute(session_factory, tenant_id, job_id)
    assert outcome.state is JobState.SUCCEEDED

    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT * FROM match_run WHERE tenant_id = :tid AND job_id = :jid"),
            {"tid": tenant_id, "jid": job_id},
        ).one()

    expected = dict(applied_weights(overrides, model=CBA_PHYSICAL_MODEL))
    assert stored.weights == pytest.approx(expected)
    assert stored.weights != pytest.approx(dict(normalize_weights(model=CBA_PHYSICAL_MODEL))), (
        "the run recorded the registry's bare defaults; the unit's configuration "
        "never reached the scoring path"
    )
    assert stored.registry_hash == weights_fingerprint(expected)


def test_changing_the_weights_does_not_change_a_run_already_recorded(
    session_factory, engine, tenant_id, owning_unit_id, actor_id
):
    """The mission, stated as a test.

    A Connector adjusts the weights *after* a run was recorded, and the run must
    still report what it was actually scored with. Asserted against the
    ``match_run`` row on a fresh connection, because the guarantee is about
    storage and not about what a response happens to render.
    """
    original = {INDUSTRY_MATCH_FACTOR_KEY: 9.0}
    _write(session_factory, tenant_id, owning_unit_id, actor_id, original)

    job_id = _accept(session_factory, tenant_id, owning_unit_id)
    assert _execute(session_factory, tenant_id, job_id).state is JobState.SUCCEEDED

    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT weights, registry_hash FROM match_run WHERE job_id = :jid"),
            {"jid": job_id},
        ).one()

    # The Connector changes their mind, decisively.
    _write(
        session_factory,
        tenant_id,
        owning_unit_id,
        actor_id,
        {ROLE_MATCH_FACTOR_KEY: 40.0},
        expected_version=1,
    )

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT weights, registry_hash FROM match_run WHERE job_id = :jid"),
            {"jid": job_id},
        ).one()

    assert after.weights == before.weights, (
        "a settings change reached a stored run. The run carries a snapshot of the "
        "weights it was scored with, never a reference to the settings that "
        "produced them"
    )
    assert after.registry_hash == before.registry_hash
    assert after.weights == pytest.approx(dict(applied_weights(original, model=CBA_PHYSICAL_MODEL)))

    # And the new weighting is genuinely in force for whatever runs next, so the
    # assertion above is proving immutability rather than a change that never
    # landed in the first place.
    with session_factory() as session:
        assert dict(
            _settings.overrides_for(session, tenant_id=tenant_id, owning_unit_id=owning_unit_id)
        ) == {ROLE_MATCH_FACTOR_KEY: 40.0}


def test_a_unit_with_no_settings_records_the_registrys_own_weights(
    session_factory, engine, tenant_id, owning_unit_id
):
    """The feature's mere existence changes nothing for a unit that never used it.

    This is what leaves the twelve approved goldens untouched: with no overrides,
    ``applied_weights`` is ``normalize_weights``.
    """
    job_id = _accept(session_factory, tenant_id, owning_unit_id)
    assert _execute(session_factory, tenant_id, job_id).state is JobState.SUCCEEDED

    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT weights FROM match_run WHERE job_id = :jid"), {"jid": job_id}
        ).one()

    assert stored.weights == pytest.approx(dict(normalize_weights(model=CBA_PHYSICAL_MODEL)))
