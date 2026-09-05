"""The CBA role-presentation map (Wave 1, ``CBA-ROLE-PRESENTATION``).

A *presentation* map, and nothing else. It answers "what do we call this
person on screen"; it never answers "what may this person do". Those are
separate concerns on purpose, and these tests are what keep them separate:

1. The map lives in exactly one place and classifies every stored role
   explicitly — an unmapped role produces ``None``, never a guess and never a
   default persona.
2. Stored ``membership.role`` strings are unchanged. A permanent database
   rename is a separate, deferred decision
   (``docs/plans/2026-09-05-cba-pivot-waves.md``), so the storage vocabulary is
   pinned here and a rename has to come through this test on purpose.
3. A visible label is not a role. No persona label may appear in an
   authorization role set — which is what makes "editing a label cannot widen
   access" checkable rather than merely stated.
4. The API and the frontend read the *same* labels. The frontend mirror is
   checked against the Python map rather than trusted, the way
   ``tests/unit/test_cba_scope_policy.py`` checks ``productScope.ts``.

Sources: ``docs/product/cba-smart-match-customer-requirements.md`` §§2–3;
``docs/product/cba-role-presentation.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from smartmatch_api import job_authz
from smartmatch_api.routers import imports as imports_router
from smartmatch_api.routers import review as review_router
from smartmatch_domain.role_presentation import (
    KNOWN_ROLES,
    Persona,
    RolePresentation,
    persona_for_role,
    portal_display_name_for_role,
    presentation_for_role,
    visible_role_label,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_LABELS_PATH = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "roleLabels.ts"
)

#: The stored ``membership.role`` strings this pilot writes
#: (``tools/seed_pilot_logins.py``) and every authorizer gates on. Written as
#: literals so a rename fails here rather than passing as a silent diff.
STORED_ROLES = frozenset({"student", "coordinator", "volunteer", "admin"})


def test_the_stored_role_vocabulary_is_unchanged() -> None:
    """Presentation must not have renamed a single stored role."""
    assert set(KNOWN_ROLES) == STORED_ROLES


def test_every_stored_role_has_exactly_one_presentation() -> None:
    for role in STORED_ROLES:
        presentation = presentation_for_role(role)
        assert isinstance(presentation, RolePresentation)
        assert presentation.role_label.strip()
        assert presentation.portal_display_name.strip()


def test_the_customer_personas_are_the_ones_shown() -> None:
    """Customer §2's four personas, over the roles that exist today."""
    assert visible_role_label("student") == "Student"
    assert visible_role_label("volunteer") == "Event Host"
    assert visible_role_label("coordinator") == "Speaker Connector"
    # Both connector-side roles present as the same persona family, and the
    # administrator qualifier keeps the two stored roles distinguishable to a
    # reader — see `docs/product/cba-role-presentation.md` for the ambiguity
    # this records rather than resolves.
    assert persona_for_role("coordinator") is Persona.SPEAKER_CONNECTOR
    assert persona_for_role("admin") is Persona.SPEAKER_CONNECTOR
    assert visible_role_label("admin") != visible_role_label("coordinator")
    assert "Speaker Connector" in (visible_role_label("admin") or "")


def test_no_ia_west_or_chapter_wording_survives_in_a_visible_label() -> None:
    """Customer §4 removes these words from anything a user reads."""
    shown = " ".join(
        f"{presentation_for_role(role).role_label} "
        f"{presentation_for_role(role).portal_display_name}"
        for role in KNOWN_ROLES
    ).lower()
    for banned in ("ia west", "iawest", "insights association", "chapter", "volunteer"):
        assert banned not in shown, f"a visible label still says {banned!r}"


def test_an_unmapped_role_gets_no_persona_and_no_label() -> None:
    """Deny-by-default, applied to naming: nothing is invented for it."""
    for unknown in ("", "   ", "speaker", "dean", "Student", "coordinator "):
        assert persona_for_role(unknown) is None
        assert visible_role_label(unknown) is None
        assert portal_display_name_for_role(unknown) is None
        with pytest.raises(KeyError):
            presentation_for_role(unknown)


def test_the_speaker_persona_exists_and_no_stored_role_grants_it() -> None:
    """Speakers are represented as contact records, not as login accounts.

    Customer §2 names Speaker as a persona, so the vocabulary carries it. No
    ``membership.role`` maps to it, because inventing a role to satisfy a
    label would be exactly the thing this track forbids — the persona is
    named and left unmapped until an approved decision creates the role.
    """
    assert Persona.SPEAKER in set(Persona)
    assert all(persona_for_role(role) is not Persona.SPEAKER for role in KNOWN_ROLES)


def test_a_visible_label_is_never_a_role_an_authorizer_accepts() -> None:
    """Renaming a persona cannot widen access, checked rather than asserted."""
    labels = {presentation_for_role(role).role_label for role in KNOWN_ROLES}
    personas = {persona.value for persona in Persona}
    for role_set in (
        job_authz.JOB_OVERSIGHT_ROLES,
        imports_router._IMPORT_ROLES,
        review_router._REVIEW_ROLES,
    ):
        assert not (labels & set(role_set))
        assert not (personas & set(role_set))
    # ...and no label is itself a stored role, so a label pasted into a
    # `membership.role` column would map to no portal at all.
    assert not (labels & STORED_ROLES)


# ---------------------------------------------------------------------------
# One map, read in two places
# ---------------------------------------------------------------------------

_TS_ENTRY = re.compile(
    r'(?P<role>[a-z_]+):\s*\{\s*persona:\s*"(?P<persona>[a-z_]+)",\s*'
    r'roleLabel:\s*"(?P<role_label>[^"]+)",\s*'
    r'portalDisplayName:\s*"(?P<portal>[^"]+)",\s*\}',
)


def _frontend_map() -> dict[str, tuple[str, str, str]]:
    source = FRONTEND_LABELS_PATH.read_text(encoding="utf-8")
    body = source.split("export const ROLE_PRESENTATION", 1)[1]
    body = body.split("} as const;", 1)[0]
    return {
        match["role"]: (match["persona"], match["role_label"], match["portal"])
        for match in _TS_ENTRY.finditer(body)
    }


def test_the_frontend_mirror_matches_the_python_map_role_for_role() -> None:
    mirror = _frontend_map()
    expected = {
        role: (
            presentation_for_role(role).persona.value,
            presentation_for_role(role).role_label,
            presentation_for_role(role).portal_display_name,
        )
        for role in KNOWN_ROLES
    }
    assert mirror == expected, (
        "apps/web/legacy-frontend/src/lib/roleLabels.ts has drifted from "
        "smartmatch_domain.role_presentation. Edit both, deliberately."
    )
