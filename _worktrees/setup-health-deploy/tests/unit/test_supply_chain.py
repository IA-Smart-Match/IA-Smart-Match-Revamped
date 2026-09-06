"""Self-tests for the license-policy gate and the SBOM generator.

A gate nobody has verified is worse than no gate: it produces a green check that
means nothing. These tests feed the checker known-bad metadata and assert it
fires, feed it known-good metadata and assert it stays quiet, and pin the
properties the SBOM is supposed to have — the lock hashes, and byte-identical
output for identical input.

They also cover the two failure modes specific to reading licenses from the
*environment* rather than from the lock: a locked distribution that is not
installed, and one installed at a version other than the one pinned. Both must
fail closed, because in both cases the license read does not describe the
artifact that ships.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "supply_chain", REPO_ROOT / "tools" / "supply_chain.py"
)
assert _spec and _spec.loader
supply_chain = importlib.util.module_from_spec(_spec)
sys.modules["supply_chain"] = supply_chain
_spec.loader.exec_module(supply_chain)

LockedDistribution = supply_chain.LockedDistribution


class FakeMetadata:
    """The subset of ``email.message.Message`` the resolver actually uses."""

    def __init__(self, **fields: object) -> None:
        self._fields = {key.replace("_", "-"): value for key, value in fields.items()}

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self._fields.get(key, default)
        return value if isinstance(value, str) or value is None else None

    def get_all(self, key: str) -> list[str] | None:
        value = self._fields.get(key)
        if value is None:
            return None
        return list(value) if isinstance(value, list) else [str(value)]

    def __getitem__(self, key: str) -> str | None:
        return self.get(key)


class FakeDistribution:
    """A stand-in for ``importlib.metadata.Distribution``."""

    def __init__(self, version: str, **fields: object) -> None:
        self.version = version
        self.metadata = FakeMetadata(**fields)


def _locked(name: str = "widget", version: str = "1.0.0") -> LockedDistribution:
    return LockedDistribution(name, version, ("0" * 64,), ("requirements/runtime.txt",))


# ---------------------------------------------------------------------------
# Lock parsing — the lock is the authority for the package set
# ---------------------------------------------------------------------------


def test_parses_a_pinned_requirement_with_hashes():
    lock = (
        "alembic==1.19.1 \\\n"
        "    --hash=sha256:" + "a" * 64 + " \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "    # via -r requirements/runtime.in\n"
    )
    parsed = supply_chain.parse_lock(lock)
    assert parsed == {"alembic": ("1.19.1", ("a" * 64, "b" * 64))}


def test_extras_are_stripped_from_the_name():
    """``psycopg[binary]`` and ``psycopg`` are one distribution, not two."""
    parsed = supply_chain.parse_lock("psycopg[binary]==3.3.4 --hash=sha256:" + "c" * 64)
    assert list(parsed) == ["psycopg"]


def test_names_are_normalized():
    parsed = supply_chain.parse_lock("Import_Linter==2.13 --hash=sha256:" + "d" * 64)
    assert list(parsed) == ["import-linter"]


def test_comments_and_options_are_ignored():
    parsed = supply_chain.parse_lock("# a comment\n--index-url https://example.invalid\n\n")
    assert parsed == {}


def test_same_pin_twice_in_one_file_merges_hashes():
    lock = (
        "psycopg[binary]==3.3.4 --hash=sha256:" + "e" * 64 + "\n"
        "psycopg==3.3.4 --hash=sha256:" + "f" * 64 + "\n"
    )
    assert supply_chain.parse_lock(lock)["psycopg"][1] == ("e" * 64, "f" * 64)


def test_conflicting_versions_in_one_file_raise():
    lock = "widget==1.0.0\nwidget==2.0.0\n"
    with pytest.raises(ValueError, match="pinned twice"):
        supply_chain.parse_lock(lock)


def test_conflicting_versions_across_locks_are_reported(tmp_path: Path):
    """Two locks disagreeing is a real defect: CI installs one and the other lies."""
    first = tmp_path / "runtime.txt"
    second = tmp_path / "dev.txt"
    first.write_text("widget==1.0.0 --hash=sha256:" + "1" * 64 + "\n")
    second.write_text("widget==2.0.0 --hash=sha256:" + "2" * 64 + "\n")
    _merged, conflicts = supply_chain.load_locks([first, second])
    assert conflicts and "widget" in conflicts[0]


def test_merging_locks_unions_the_hashes_and_records_both_sources(tmp_path: Path):
    first = tmp_path / "runtime.txt"
    second = tmp_path / "dev.txt"
    first.write_text("widget==1.0.0 --hash=sha256:" + "1" * 64 + "\n")
    second.write_text("widget==1.0.0 --hash=sha256:" + "2" * 64 + "\n")
    merged, conflicts = supply_chain.load_locks([first, second])
    assert not conflicts
    assert merged["widget"].sha256 == ("1" * 64, "2" * 64)
    assert len(merged["widget"].locks) == 2


# ---------------------------------------------------------------------------
# License resolution
# ---------------------------------------------------------------------------


def test_license_expression_wins_over_everything():
    dist = FakeDistribution(
        "1.0.0",
        License_Expression="BSD-3-Clause",
        License="MIT",
        Classifier=["License :: OSI Approved :: MIT License"],
    )
    assert supply_chain.declared_license(dist) == ("BSD-3-Clause", "License-Expression")


def test_free_text_license_is_normalized():
    dist = FakeDistribution("1.0.0", License="BSD 2-Clause License")
    assert supply_chain.declared_license(dist) == ("BSD-2-Clause", "License")


def test_classifiers_are_the_last_resort():
    dist = FakeDistribution("1.0.0", Classifier=["License :: OSI Approved :: MIT License"])
    assert supply_chain.declared_license(dist) == ("MIT", "Classifier")


def test_several_license_classifiers_become_an_or_expression():
    """A package offering a choice of licenses is SPDX ``OR``, not ``AND``."""
    dist = FakeDistribution(
        "1.0.0",
        Classifier=[
            "License :: OSI Approved :: Apache Software License",
            "License :: OSI Approved :: MIT License",
        ],
    )
    expression, _source = supply_chain.declared_license(dist)
    assert expression == "Apache-2.0 OR MIT"


def test_bare_osi_approved_classifier_carries_no_identifier():
    dist = FakeDistribution("1.0.0", Classifier=["License :: OSI Approved"])
    assert supply_chain.declared_license(dist)[0] is None


def test_full_license_text_in_the_license_field_is_not_guessed_at():
    """A License field holding the whole license is prose, not a name."""
    dist = FakeDistribution("1.0.0", License="Copyright (c) 2020\n" + "x" * 400)
    expression, source = supply_chain.declared_license(dist)
    assert expression is None
    assert "unrecognized" in source


def test_unrecognized_license_reports_what_the_package_said():
    dist = FakeDistribution("1.0.0", License="Weird Corp Internal v3")
    expression, source = supply_chain.declared_license(dist)
    assert expression is None
    assert "Weird Corp Internal v3" in source


def test_no_license_metadata_at_all_is_undetermined():
    assert supply_chain.declared_license(FakeDistribution("1.0.0")) == (None, "none")


# ---------------------------------------------------------------------------
# SPDX expression evaluation
# ---------------------------------------------------------------------------


def test_and_requires_every_operand():
    assert supply_chain.evaluate("MIT AND PSF-2.0", {"MIT", "PSF-2.0"})
    assert not supply_chain.evaluate("MIT AND LGPL-3.0-only", {"MIT"})


def test_or_requires_only_one_operand():
    assert supply_chain.evaluate("Apache-2.0 OR BSD-2-Clause", {"BSD-2-Clause"})
    assert not supply_chain.evaluate("GPL-3.0-only OR AGPL-3.0-only", {"MIT"})


def test_parentheses_group():
    assert supply_chain.evaluate("(MIT OR GPL-3.0-only) AND BSD-2-Clause", {"MIT", "BSD-2-Clause"})
    assert not supply_chain.evaluate("MIT OR (GPL-3.0-only AND BSD-2-Clause)", {"BSD-2-Clause"})


def test_with_clause_is_decided_by_the_license_not_the_exception():
    assert supply_chain.evaluate("Apache-2.0 WITH LLVM-exception", {"Apache-2.0"})
    assert not supply_chain.evaluate("GPL-3.0-only WITH Classpath-exception-2.0", {"MIT"})


def test_license_ids_ignores_operators_and_exception_names():
    assert supply_chain.license_ids("(MIT OR Apache-2.0 WITH LLVM-exception) AND PSF-2.0") == [
        "MIT",
        "Apache-2.0",
        "PSF-2.0",
    ]


@pytest.mark.parametrize("expression", ["", "AND MIT", "(MIT", "MIT WITH", "MIT )"])
def test_malformed_expressions_raise_rather_than_defaulting_to_allowed(expression: str):
    """A gate that fails open on malformed input is not a gate."""
    with pytest.raises(supply_chain.ExpressionError):
        supply_chain.evaluate(expression, {"MIT"})


def test_an_unparseable_expression_is_a_finding_not_a_pass():
    dist = FakeDistribution("1.0.0", License_Expression="MIT AND")
    resolution = supply_chain.resolve_one(_locked(), {"widget": dist})
    assert resolution.status == "unknown"
    assert not resolution.ok


# ---------------------------------------------------------------------------
# The policy decision
# ---------------------------------------------------------------------------


def test_allowlisted_license_passes():
    dist = FakeDistribution("1.0.0", License_Expression="MIT")
    assert supply_chain.resolve_one(_locked(), {"widget": dist}).status == "allowed"


def test_license_outside_the_allowlist_fails():
    dist = FakeDistribution("1.0.0", License_Expression="AGPL-3.0-only")
    resolution = supply_chain.resolve_one(_locked(), {"widget": dist})
    assert resolution.status == "disallowed"
    assert "AGPL-3.0-only" in resolution.detail


def test_undeterminable_license_is_a_finding_not_a_pass():
    """Fail closed. 'No license declared' is not 'no obligations'."""
    resolution = supply_chain.resolve_one(_locked(), {"widget": FakeDistribution("1.0.0")})
    assert resolution.status == "unknown"
    assert not resolution.ok


def test_locked_but_not_installed_fails_closed():
    resolution = supply_chain.resolve_one(_locked(), {})
    assert resolution.status == "not-installed"
    assert not resolution.ok


def test_installed_at_a_different_version_fails_closed():
    """The license read would describe an artifact other than the pinned one."""
    dist = FakeDistribution("9.9.9", License_Expression="MIT")
    resolution = supply_chain.resolve_one(_locked(version="1.0.0"), {"widget": dist})
    assert resolution.status == "version-mismatch"
    assert not resolution.ok


def test_an_exception_permits_one_distribution():
    dist = FakeDistribution("1.0.0", License_Expression="LGPL-3.0-only")
    resolution = supply_chain.resolve_one(
        _locked(),
        {"widget": dist},
        exceptions={("widget", "LGPL-3.0-only"): "a reason recorded by a reviewer"},
    )
    assert resolution.status == "exception"
    assert resolution.ok
    assert "recorded by a reviewer" in resolution.detail


def test_an_exception_does_not_leak_to_another_distribution():
    """The whole point of keying exceptions by distribution."""
    dist = FakeDistribution("1.0.0", License_Expression="LGPL-3.0-only")
    resolution = supply_chain.resolve_one(
        _locked(name="other"),
        {"other": dist},
        exceptions={("widget", "LGPL-3.0-only"): "a reason recorded by a reviewer"},
    )
    assert resolution.status == "disallowed"


def test_an_exception_satisfies_only_the_operand_it_names():
    """LGPL excepted, GPL not: an AND expression containing both still fails."""
    dist = FakeDistribution("1.0.0", License_Expression="LGPL-3.0-only AND GPL-3.0-only")
    resolution = supply_chain.resolve_one(
        _locked(),
        {"widget": dist},
        exceptions={("widget", "LGPL-3.0-only"): "a reason recorded by a reviewer"},
    )
    assert resolution.status == "disallowed"
    assert "GPL-3.0-only" in resolution.detail


# ---------------------------------------------------------------------------
# Policy-table hygiene — an unexplained entry defeats the gate
# ---------------------------------------------------------------------------


def test_every_allowed_license_has_a_reason():
    for identifier, reason in supply_chain.ALLOWED_LICENSES.items():
        assert reason and len(reason) > 15, f"{identifier} is allowed without a stated reason"


def test_every_exception_has_a_substantial_reason():
    """An exception is a decision. A decision with no argument is not reviewable."""
    for key, reason in supply_chain.LICENSE_EXCEPTIONS.items():
        assert reason and len(reason) > 80, f"exception {key} lacks a real justification"


def test_no_exception_duplicates_the_allowlist():
    """A redundant exception implies a restriction that is not there."""
    for _dist, identifier in supply_chain.LICENSE_EXCEPTIONS:
        assert identifier not in supply_chain.ALLOWED_LICENSES


def test_every_exception_names_a_distribution_the_locks_pin():
    """A stale exception outlives the dependency it was written for."""
    locked, _conflicts = supply_chain.load_locks([supply_chain.RUNTIME_LOCK, supply_chain.DEV_LOCK])
    for dist_name, identifier in supply_chain.LICENSE_EXCEPTIONS:
        assert dist_name in locked, (
            f"exception for {dist_name} ({identifier}) names a distribution no lock pins"
        )


# ---------------------------------------------------------------------------
# The SBOM
# ---------------------------------------------------------------------------


def test_sbom_is_a_cyclonedx_1_5_document():
    document = supply_chain.build_sbom()
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.5"
    assert document["version"] == 1
    assert document["serialNumber"].startswith("urn:uuid:")
    assert document["metadata"]["component"]["type"] == "application"


def test_sbom_carries_the_hashes_the_lock_pins():
    """What makes it worth more than a package list."""
    document = supply_chain.build_sbom()
    locked, _conflicts = supply_chain.load_locks([supply_chain.RUNTIME_LOCK])
    for component in document["components"]:
        expected = locked[component["name"]].sha256
        assert [h["content"] for h in component["hashes"]] == list(expected)
        assert {h["alg"] for h in component["hashes"]} == {"SHA-256"}
        assert component["hashes"], f"{component['name']} has no pinned hash"


def test_sbom_component_set_is_exactly_the_lock():
    """Not what happens to be installed — the environment holds more."""
    document = supply_chain.build_sbom()
    locked, _conflicts = supply_chain.load_locks([supply_chain.RUNTIME_LOCK])
    assert {c["name"] for c in document["components"]} == set(locked)


def test_sbom_is_byte_identical_across_runs():
    """No timestamp, and a content-derived serial: two builds can be diffed."""
    first = json.dumps(supply_chain.build_sbom(), sort_keys=True)
    second = json.dumps(supply_chain.build_sbom(), sort_keys=True)
    assert first == second


def test_sbom_serial_number_changes_when_the_content_does(tmp_path: Path):
    lock = tmp_path / "runtime.txt"
    lock.write_text("widget==1.0.0 --hash=sha256:" + "1" * 64 + "\n")
    first = supply_chain.build_sbom([lock])["serialNumber"]
    lock.write_text("widget==2.0.0 --hash=sha256:" + "2" * 64 + "\n")
    second = supply_chain.build_sbom([lock])["serialNumber"]
    assert first != second


def test_sbom_marks_an_undeterminable_license_rather_than_inventing_one(tmp_path: Path):
    lock = tmp_path / "runtime.txt"
    lock.write_text("definitely-not-installed==1.0.0 --hash=sha256:" + "3" * 64 + "\n")
    component = supply_chain.build_sbom([lock])["components"][0]
    assert "licenses" not in component
    properties = {p["name"]: p["value"] for p in component["properties"]}
    assert properties["smartmatch:license"] == "undetermined"
    assert properties["smartmatch:license-source"] == "not-installed"


def test_sbom_uses_an_spdx_expression_for_a_compound_license(tmp_path: Path):
    lock = tmp_path / "runtime.txt"
    lock.write_text("greenlet==3.5.5 --hash=sha256:" + "4" * 64 + "\n")
    components = supply_chain.build_sbom([lock])["components"]
    licenses = components[0].get("licenses")
    if licenses is None:  # greenlet absent from this environment
        pytest.skip("greenlet is not installed here")
    assert "expression" in licenses[0] or "license" in licenses[0]


def test_sbom_purl_and_bom_ref_agree():
    for component in supply_chain.build_sbom()["components"]:
        assert component["purl"] == component["bom-ref"]
        assert component["purl"].startswith("pkg:pypi/")


def test_sbom_refuses_to_build_from_conflicting_locks(tmp_path: Path):
    first = tmp_path / "runtime.txt"
    second = tmp_path / "dev.txt"
    first.write_text("widget==1.0.0 --hash=sha256:" + "1" * 64 + "\n")
    second.write_text("widget==2.0.0 --hash=sha256:" + "2" * 64 + "\n")
    with pytest.raises(ValueError, match="pinned at"):
        supply_chain.build_sbom([first, second])


# ---------------------------------------------------------------------------
# The gate, run against this repository as it stands
# ---------------------------------------------------------------------------


def test_repository_license_policy_is_clean():
    report = supply_chain.check_licenses()
    assert report.resolutions, "no locked distributions found — check the lock paths"
    assert report.ok, "\n".join(
        f"{f.name}=={f.version} [{f.status}] {f.expression} — {f.detail}" for f in report.findings
    ) or "; ".join(report.conflicts)
