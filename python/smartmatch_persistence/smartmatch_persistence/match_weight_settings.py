"""The ``match_weight_setting`` read/write path (migration ``0027``).

One table for the current value, one insert-only table for the log of how it got
there, and one method that changes either. Customer §5 gives a Speaker Connector
the ability to adjust the matching weights; this module is where that adjustment
becomes durable, and where the properties that make it safe are enforced.

## A setting is an override layer, and reading one can return nothing

:meth:`MatchWeightSettingRepository.get` returns ``None`` for a unit that has
never configured anything, and that is not the same answer as an empty override
map. A unit with no row has no author and no timestamp; a unit whose row holds
``{}`` reset its weights, and somebody did that at a particular moment. Both
score identically — on the registry's own weights — and their histories differ,
so the read keeps them apart rather than collapsing one into the other.

:meth:`MatchWeightSettingRepository.overrides_for` is the shape the scoring path
wants instead: the override map, empty when there is no row. It exists so the
worker's one line reads as "this unit's overrides" rather than as a ``None``
check whose two branches produce the same weights.

## Every accepted change writes two rows, in one transaction

The settings row moves to the next ``version`` and a revision row is inserted at
that version. They are written together, so there is no window in which the
current value has changed and the log does not say so. The revision table's
``uq_match_weight_setting_revision_version`` is what makes that idempotent under
a retry: a second attempt at the same version cannot append a second entry
claiming a change that happened once.

## Transaction boundaries belong to the caller

Like every other repository here, this takes a :class:`~sqlalchemy.orm.Session`
per call and **never commits**. The API's ``get_session`` rolls back
unconditionally, so a route that calls :meth:`MatchWeightSettingRepository.put`
and forgets to commit returns a clean 2xx and stores nothing — a failure two
earlier tracks in this repository shipped.
``tests/integration/test_cba_weight_settings_persistence.py`` asserts against the
tables rather than against the response for exactly that reason.

## What this module never does

It never touches ``match_run``. A stored run carries the weights it was scored
with, and no foreign key runs from a run to a setting — a change here cannot
reach a run that is already recorded, and the schema is what guarantees that
rather than the care of whoever writes the next feature.

It also never invents a weight. There is no default in this module, no seed and
no backfill: absence of an override means the registry answers, which is the one
rule that keeps ADR-0016's figures the only copy of themselves.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from smartmatch_domain.weight_settings import (
    CONFIGURABLE_FACTOR_KEYS,
    MatchWeightSettings,
)
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "MatchWeightSettingRecord",
    "MatchWeightSettingRepository",
    "StaleWeightSettingsError",
    "WeightSettingRevision",
]


class StaleWeightSettingsError(RuntimeError):
    """Raised when a write names a version that is no longer the current one.

    The optimistic-concurrency refusal. Two Connectors editing one unit's weights
    from two screens is not a rare case — it is the ordinary case for a settings
    page left open — and the alternative to refusing is that the second save
    silently discards the first, with the audit log dutifully recording both as
    successful changes.
    """


@dataclass(frozen=True, slots=True)
class MatchWeightSettingRecord:
    """One unit's stored configuration, as it stands after a read or a write.

    Attributes:
        id: The settings row's own identifier.
        tenant_id: The owning tenant, from the row rather than from a caller.
        owning_unit_id: The unit this configuration applies to.
        settings: The value object — overrides, version, author, timestamp.
        ignored_factor_keys: Stored keys that no current registry model admits,
            reported rather than silently dropped or fatally raised. The write
            path refuses such a key, so this can only be non-empty when the
            registry has *retired* a factor since the setting was made, or when
            somebody wrote the row out of band. Neither is a reason to fail a
            read — the remaining overrides are still exactly what the unit
            configured — and both are reasons a person should be told, which is
            why the API renders this field instead of the repository swallowing
            it.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    settings: MatchWeightSettings
    ignored_factor_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeightSettingRevision:
    """One entry in a unit's immutable change log."""

    version: int
    overrides: Mapping[str, float]
    changed_by_user_id: uuid.UUID
    changed_at: datetime


def _split_stored_overrides(raw: object) -> tuple[dict[str, float], tuple[str, ...]]:
    """Stored JSON to ``(overrides, ignored_keys)``.

    A stored value that is not an object, or an entry whose value is not a
    number, cannot have come from
    :func:`~smartmatch_domain.weight_settings.validate_weight_overrides` and is
    reported as ignored rather than coerced — coercing it would be the repair
    this feature exists to refuse, applied at the one boundary where nobody is
    watching.
    """
    if not isinstance(raw, dict):
        return {}, ()
    overrides: dict[str, float] = {}
    ignored: list[str] = []
    for key, value in raw.items():
        if (
            key in CONFIGURABLE_FACTOR_KEYS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            overrides[str(key)] = float(value)
        else:
            ignored.append(str(key))
    return overrides, tuple(sorted(ignored))


class MatchWeightSettingRepository:
    """Reads and writes one unit's matching-weight overrides."""

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
    ) -> MatchWeightSettingRecord | None:
        """The unit's configuration, or ``None`` if it has never had one.

        ``None`` is a real answer and not a missing one — see the module
        docstring on why it is not collapsed into an empty override map.
        """
        table = schema.match_weight_setting
        row = session.execute(
            sa.select(table).where(
                table.c.tenant_id == tenant_id,
                table.c.owning_unit_id == owning_unit_id,
            )
        ).one_or_none()
        if row is None:
            return None
        return self._to_record(row)

    def overrides_for(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
    ) -> Mapping[str, float]:
        """The unit's overrides, empty when it has none.

        The scoring path's read. An empty map and a missing row are the same
        weights, and this is the one caller for which that is the whole truth —
        so it gets an answer it can hand straight to ``normalize_weights``
        instead of a ``None`` it would have to branch on.
        """
        record = self.get(session, tenant_id=tenant_id, owning_unit_id=owning_unit_id)
        return {} if record is None else record.settings.overrides

    def put(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        overrides: Mapping[str, float],
        actor_user_id: uuid.UUID,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> MatchWeightSettingRecord:
        """Record an accepted change, and log it.

        The row is locked for update before it is read, so two concurrent writes
        serialize rather than both reading version *n* and both writing *n+1* —
        which the revision table's unique constraint would then refuse as a
        duplicate, reporting a database error where the honest answer is "someone
        else changed this first".

        Args:
            overrides: An **already validated** override map — this method does
                not validate. Validation belongs to
                :func:`~smartmatch_domain.weight_settings.validate_weight_overrides`
                at the request boundary, where the caller can be told which field
                is wrong; a repository that re-validated would be a second
                opinion about admissibility, and the two would drift.
            actor_user_id: The account making the change. Not optional and not
                defaulted: a settings change with no author is not auditable, and
                the foreign key would refuse a placeholder anyway.
            expected_version: The version the caller believes is current, or
                ``None`` to write without an opinion. Pass the version read from
                a GET to make a lost update impossible.
            now: The change's timestamp, injected so a test can pin it.

        Returns:
            The configuration as it stands after the change, at the new version.

        Raises:
            StaleWeightSettingsError: when ``expected_version`` does not match
                what is stored — including the case where the caller expected a
                version and the unit has no row at all.
        """
        settings_table = schema.match_weight_setting
        revision_table = schema.match_weight_setting_revision

        current = session.execute(
            sa.select(settings_table)
            .where(
                settings_table.c.tenant_id == tenant_id,
                settings_table.c.owning_unit_id == owning_unit_id,
            )
            .with_for_update()
        ).one_or_none()

        stored_version = None if current is None else int(current.version)
        if expected_version is not None and expected_version != stored_version:
            raise StaleWeightSettingsError(
                f"expected version {expected_version}, but the stored version is "
                f"{stored_version}. Someone else changed this unit's weights first; "
                "re-read the current settings before writing."
            )

        next_version = 1 if stored_version is None else stored_version + 1
        payload = {key: float(value) for key, value in overrides.items()}
        moment = now or datetime.now(tz=UTC)

        if current is None:
            settings_id = uuid.uuid4()
            session.execute(
                sa.insert(settings_table).values(
                    id=settings_id,
                    tenant_id=tenant_id,
                    owning_unit_id=owning_unit_id,
                    overrides=payload,
                    version=next_version,
                    updated_by_user_id=actor_user_id,
                    created_at=moment,
                    updated_at=moment,
                )
            )
        else:
            settings_id = current.id
            session.execute(
                sa.update(settings_table)
                .where(settings_table.c.id == settings_id)
                .values(
                    overrides=payload,
                    version=next_version,
                    updated_by_user_id=actor_user_id,
                    updated_at=moment,
                )
            )

        session.execute(
            sa.insert(revision_table).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                overrides=payload,
                version=next_version,
                changed_by_user_id=actor_user_id,
                changed_at=moment,
            )
        )

        return MatchWeightSettingRecord(
            id=settings_id,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            settings=MatchWeightSettings(
                overrides=payload,
                version=next_version,
                updated_by_user_id=str(actor_user_id),
                updated_at=moment,
            ),
            ignored_factor_keys=(),
        )

    def revisions(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
    ) -> tuple[WeightSettingRevision, ...]:
        """The unit's change log, newest first.

        Read-only by construction: nothing in this module updates or deletes a
        revision, and migration ``0027``'s trigger refuses an UPDATE that reaches
        the table any other way.
        """
        table = schema.match_weight_setting_revision
        rows = session.execute(
            sa.select(table)
            .where(
                table.c.tenant_id == tenant_id,
                table.c.owning_unit_id == owning_unit_id,
            )
            .order_by(table.c.version.desc())
        ).all()
        return tuple(
            WeightSettingRevision(
                version=int(row.version),
                overrides=_split_stored_overrides(row.overrides)[0],
                changed_by_user_id=row.changed_by_user_id,
                changed_at=row.changed_at,
            )
            for row in rows
        )

    @staticmethod
    def _to_record(row: sa.Row) -> MatchWeightSettingRecord:
        overrides, ignored = _split_stored_overrides(row.overrides)
        return MatchWeightSettingRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            owning_unit_id=row.owning_unit_id,
            settings=MatchWeightSettings(
                overrides=overrides,
                version=int(row.version),
                updated_by_user_id=str(row.updated_by_user_id),
                updated_at=row.updated_at,
            ),
            ignored_factor_keys=ignored,
        )
