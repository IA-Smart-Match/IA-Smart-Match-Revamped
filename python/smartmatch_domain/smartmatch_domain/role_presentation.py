"""What a server-assigned role is *called* — and nothing more.

This is the single CBA role-presentation map. The API's portal mapping
(``services/api/smartmatch_api/routers/portals.py``) and the frontend's label
helper (``apps/web/legacy-frontend/src/lib/roleLabels.ts``) both read *these*
names; neither invents its own, and neither derives a permission from one.

A label is not a power
======================

``membership.role`` is the string an administrator wrote, the string
:mod:`smartmatch_authz` gates on, and the string this module translates for a
reader. Translating it changes what a person is *called*, never what they may
*do*: every ``/v1`` operation still runs its own tenant-scoped,
deny-by-default authorization against the resource it loaded, and none of them
has ever consulted a display label. Renaming a persona here therefore cannot
widen access — a property ``tests/unit/test_role_presentation.py`` checks
rather than asserts, by proving no label appears in any authorizer's role set.

The corollary matters just as much: nothing may go the other way and turn a
label into a gate. If a capability ever needs limiting, the limit belongs in
the policy matrix over stored roles, not in this file.

Stored strings are unchanged, deliberately
==========================================

The stored vocabulary stays ``student``, ``coordinator``, ``volunteer``,
``admin``. A permanent database rename is a separate, deferred decision
(``docs/plans/2026-09-05-cba-pivot-waves.md``): a rename touches seeds, every
``required_roles`` set, existing rows, and any operator runbook that names a
role, and doing it inside a presentation change would make one reviewable
decision look like two unreviewable ones. So this module is a *translation
layer over stable storage*, and it is the reason a CBA screen can say
"Speaker Connector" while the row still says ``coordinator``.

An unmapped role is reported, never guessed
===========================================

:func:`persona_for_role` returns ``None`` for any role the map does not name —
including a blank one, and including a role differing only in case or
whitespace. It is not rounded to the nearest persona and not defaulted to the
narrowest one, for ``routers/portals.py``'s reason: an invented label is
indistinguishable from a correct one until something built on it is refused.

Ambiguity this map records rather than resolves
===============================================

``coordinator`` and ``admin`` both present inside the Speaker Connector
persona, because customer §2 gives the connector work — maintaining contact
lists, receiving requests, running matching, sending invitations — to a single
persona while this system has long split those powers across two stored roles
with genuinely different reach (``admin`` is tenant-wide for aggregates;
``coordinator`` is subtree-scoped). The two keep distinct *labels*, so a
reader can still tell which row they hold, and exactly the powers they had
before. See ``docs/product/cba-role-presentation.md`` for the open question
and what would settle it.

:attr:`Persona.SPEAKER` is named and unmapped for the mirror-image reason:
customer §2 lists Speaker as a persona, and no ``membership.role`` grants it
today because speakers are represented as contact records rather than as login
accounts. Naming the persona without a role keeps the vocabulary honest;
inventing a role to fill it would be a schema decision smuggled in as a label.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §§2–4
* ``docs/product/cba-role-presentation.md`` (this map, in prose)
* ``docs/plans/2026-09-05-cba-pivot-waves.md`` (CBA-ROLE-PRESENTATION)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "KNOWN_ROLES",
    "Persona",
    "RolePresentation",
    "persona_for_role",
    "portal_display_name_for_role",
    "presentation_for_role",
    "visible_role_label",
]


class Persona(StrEnum):
    """A CBA persona, as customer §2 names them.

    A persona is a *family of presentation*, not a permission and not a
    portal. Two stored roles may share one persona (see the module docstring
    on ``coordinator``/``admin``), and a persona may have no stored role at
    all (:attr:`SPEAKER`).
    """

    #: Browses events, registers, adds events to a calendar, gives feedback.
    STUDENT = "student"

    #: Faculty, staff, or a student club requesting a speaker for a class,
    #: workshop, or club event.
    EVENT_HOST = "event_host"

    #: CBACH, Alumni Relations, and faculty who maintain contact lists,
    #: receive requests, run matching, send invitations, track responses.
    SPEAKER_CONNECTOR = "speaker_connector"

    #: Alumni, employers, and industry guests who receive invitations and view
    #: upcoming engagements. Represented as contact records, not accounts —
    #: no stored role maps here, on purpose.
    SPEAKER = "speaker"


@dataclass(frozen=True, slots=True)
class RolePresentation:
    """Everything visible that one stored role decides.

    Attributes:
        persona: The CBA persona this role presents as.
        role_label: What to call the person holding this role, in prose.
        portal_display_name: What to call the shell this role opens. Kept
            beside the role label rather than in the router, so the two cannot
            drift into naming the same person two different things.
    """

    persona: Persona
    role_label: str
    portal_display_name: str


#: The map. One row per stored ``membership.role``, exhaustive over the roles
#: ``tools/seed_pilot_logins.py`` writes. Adding a row is a deliberate act; a
#: role absent from this table is reported as unmapped rather than guessed.
_PRESENTATION: Final[Mapping[str, RolePresentation]] = MappingProxyType(
    {
        "student": RolePresentation(
            persona=Persona.STUDENT,
            role_label="Student",
            portal_display_name="Student Portal",
        ),
        # Customer §4: "Volunteer — Event Host when referring to the
        # event-requesting role", which is what this shell is: the person
        # asking for a speaker, not the speaker.
        "volunteer": RolePresentation(
            persona=Persona.EVENT_HOST,
            role_label="Event Host",
            portal_display_name="Event Host Portal",
        ),
        "coordinator": RolePresentation(
            persona=Persona.SPEAKER_CONNECTOR,
            role_label="Speaker Connector",
            # "Connector Dashboard" is the customer's own §4 rename of the
            # Chapter Admin Dashboard, and `CBA-TERMINOLOGY` shipped that name
            # in the shell's chrome. Using it here keeps the server the single
            # naming authority instead of a second one that happens to agree.
            portal_display_name="Connector Dashboard",
        ),
        # Same persona, distinguishable label. The qualifier is presentation,
        # not a power: ``admin``'s reach is decided by ``smartmatch_authz``
        # exactly as it was before this map existed.
        "admin": RolePresentation(
            persona=Persona.SPEAKER_CONNECTOR,
            role_label="Speaker Connector (administrator)",
            portal_display_name="CBA Administration",
        ),
    }
)

#: Every stored role this map names, in declaration order.
KNOWN_ROLES: Final[tuple[str, ...]] = tuple(_PRESENTATION)


def presentation_for_role(role: str) -> RolePresentation:
    """The presentation for a stored role.

    Raises:
        KeyError: if ``role`` is not a mapped role. Callers that must tolerate
            an unmapped role should use :func:`persona_for_role` or
            :func:`visible_role_label`, which report the absence as ``None``.
    """
    return _PRESENTATION[role]


def persona_for_role(role: str) -> Persona | None:
    """The persona a stored role presents as, or ``None`` when it maps to none.

    Matched exactly: ``"Student"`` and ``"coordinator "`` are not the stored
    strings and are answered ``None``, because silently normalising them would
    make a malformed row read as a correct one.
    """
    presentation = _PRESENTATION.get(role)
    return None if presentation is None else presentation.persona


def visible_role_label(role: str) -> str | None:
    """What to call the holder of a stored role, or ``None`` for an unmapped one."""
    presentation = _PRESENTATION.get(role)
    return None if presentation is None else presentation.role_label


def portal_display_name_for_role(role: str) -> str | None:
    """What to call the shell a stored role opens, or ``None`` when it opens none."""
    presentation = _PRESENTATION.get(role)
    return None if presentation is None else presentation.portal_display_name
