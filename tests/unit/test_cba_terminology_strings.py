"""Visible naming contract for the CPP role vocabulary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src/app"


def test_shells_use_the_approved_role_names() -> None:
    files = [
        ROOT / "components/Layout.tsx",
        ROOT / "components/CoordinatorPortalLayout.tsx",
        ROOT / "components/VolunteerPortalLayout.tsx",
        ROOT / "components/StudentLayout.tsx",
    ]
    visible = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for label in ("Speaker Connector", "Event Host", "Speaker", "Student"):
        assert label in visible
    assert "IA West" not in visible


def test_public_pages_use_cpp_branding() -> None:
    visible = "\n".join(
        (ROOT / "pages" / name).read_text(encoding="utf-8")
        for name in ("LandingPage.tsx", "LoginPage.tsx")
    )
    assert "Cal Poly Pomona" in visible
    assert "CBA Smart Match" not in visible
