"""Hold ``ck_job_status`` and ``smartmatch_domain.jobs.JobState`` to each other.

``0001_foundation_baseline.py`` writes the twelve job states into a CHECK
constraint and comments that the constraint is "kept in sync by
tests/integration/test_job_states_match_domain.py". Until this module existed
that sentence named a guard nobody had written: the two lists were transcriptions
of each other maintained by hand, and a state added to the domain enum would have
been rejected by the database the first time a job reached it — in a worker, at
runtime, as an ``IntegrityError`` naming a constraint rather than the enum that
had outgrown it.

Two tests, deliberately different in kind, so that a failure of one does not
depend on the other being right.
``test_check_constraint_admits_exactly_the_domain_states`` reads the
constraint's expression out of the catalog and compares the state *set* both
directions — a state in the enum the database would reject, and a state the
database admits that the enum never produces, are different defects and are
reported separately. ``test_every_domain_state_can_be_written`` takes the same
question to the database instead of reading it: one insert per ``JobState``,
each of which must be accepted. That one holds even if PostgreSQL's rendering
ever defeats the parse, which is the failure mode a regex over catalog text
invites.

The opposite direction — a status that is *not* a ``JobState`` must be rejected
— is already proved by
``test_tenant_isolation.py::test_job_status_check_rejects_an_unknown_state``, which inserts
``not_a_real_state`` and requires ``IntegrityError``. It is not repeated here.
That test is also what would catch ``ck_job_status`` being made inert — dropped,
or replaced by one that admits anything — which neither test in this module would
notice on its own.

It would **not** catch it being re-added as ``NOT VALID``, and this sentence used
to say it would. Verified against PostgreSQL 16.15: a ``NOT VALID`` CHECK rejects
new inserts exactly as a validated one does, because ``NOT VALID`` skips only the
initial scan of rows already in the table. No attempted write can distinguish the
two. ``test_check_constraints.py::test_every_check_constraint_is_validated``
reads ``pg_constraint.convalidated``, which is the only thing that can, and
covers ``ck_job_status`` along with the other seven.

Reading expression text is a thing ``docs/plans/defect-remediation.md`` §6.3
argues against for the schema drift test, and the objection does not apply here.
There the expression *is* the assertion, and PostgreSQL's rewriting of
``status IN (...)`` into ``status = ANY (ARRAY[...])`` makes comparing two
renderings of the same rule pointless. Here the rendering is incidental and the
quoted literals are the payload — the set of states is what the two definitions
must agree on, whatever syntax surrounds it.
"""

from __future__ import annotations

import re
import uuid

import pytest
from smartmatch_domain.jobs import JobState
from sqlalchemy import Engine, inspect, text

pytestmark = pytest.mark.integration

_CONSTRAINT = "ck_job_status"

#: The quoted literals in the constraint expression. The states carry no quotes
#: of their own, so this is the whole of the parse.
_LITERAL = re.compile(r"'([^']*)'")


def _states_in_check_constraint(engine: Engine) -> set[str]:
    """The states ``ck_job_status`` admits, read from the live constraint.

    Fails rather than returning an empty set if the constraint is missing or the
    expression stops looking the way it does today. A parse that quietly matches
    nothing would make the comparison below pass for a schema with no states in
    it at all, which is the failure mode this function exists to not have.
    """
    constraints = {c["name"]: c["sqltext"] for c in inspect(engine).get_check_constraints("job")}
    assert _CONSTRAINT in constraints, (
        f"{_CONSTRAINT} is not on the job table; the states are unconstrained in the database"
    )

    states = set(_LITERAL.findall(constraints[_CONSTRAINT]))
    assert states, (
        f"no quoted states could be read out of {_CONSTRAINT}: "
        f"{constraints[_CONSTRAINT]!r} — the parse, not the schema, is what failed here"
    )
    return states


def test_check_constraint_admits_exactly_the_domain_states(engine: Engine):
    """Both directions, because each one breaks something different.

    A state in the enum but not the constraint is a job the database refuses to
    record, discovered by a worker mid-transition. A state in the constraint but
    not the enum is dead vocabulary the state machine will never produce and no
    reader can account for.
    """
    in_database = _states_in_check_constraint(engine)
    in_domain = {state.value for state in JobState}

    assert in_database == in_domain, (
        f"job states diverge — in the domain enum but rejected by {_CONSTRAINT}: "
        f"{sorted(in_domain - in_database)}; admitted by {_CONSTRAINT} but absent from "
        f"the enum: {sorted(in_database - in_domain)}"
    )


@pytest.mark.parametrize("state", sorted(JobState), ids=lambda state: state.value)
def test_every_domain_state_can_be_written(engine: Engine, tenant_id: uuid.UUID, state: JobState):
    """The set comparison proved on the constraint's own terms.

    If the parse above ever drifts from what PostgreSQL enforces, this fails
    instead: it does not read the constraint, it runs into it.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO job (id, tenant_id, command_type, status) "
                "VALUES (:id, :tenant_id, :command_type, :status)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "command_type": "match.run",
                "status": state.value,
            },
        )
