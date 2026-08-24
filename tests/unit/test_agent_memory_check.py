"""Self-tests for the agent-memory ledger validator.

A gate nobody has verified is worse than no gate: it produces a green check that
means nothing. These feed the validator known-bad records and assert it fires,
and known-good records and assert it stays quiet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "agent_memory_check", REPO_ROOT / "tools" / "agent_memory_check.py"
)
assert _spec and _spec.loader
amc = importlib.util.module_from_spec(_spec)
sys.modules["agent_memory_check"] = amc
_spec.loader.exec_module(amc)


GOOD = """---
schema: agent-memory/record/v1
entry_id: 018f3c2a-7b4e-7c1d-9a2f-3e5d6c7b8a90
project_id: smartmatch
repository_id: 9b1c4f28-2d3a-4e57-8f60-71a2b3c4d5e6
status: approved
authority: observation
privacy_class: repo-public
claim: The outbox claim order is a contract obligation, not an emergent property.
sources:
  - docs/architecture/decisions/ADR-0005-transactional-outbox-and-cte-claim.md@abc123
produced_by_tool: claude-code
produced_by_session: 57e35539-b0e2-4365-9a0f-3f8d01a25be9
produced_by_commit: 4e35430
reviewed_by: maintainer
approved_at: 2026-08-24T00:00:00Z
expires_at: null
supersedes: null
superseded_by: null
conflicts_with:
content_hash: sha256:placeholder
---

Read ADR-0005 before assuming the ordering is incidental.
"""


def _codes(record: str) -> set[str]:
    fields, _ = amc.parse_front_matter(record)
    return {finding.code for finding in amc.validate_fields(fields, path="x.md")}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_a_well_formed_record_produces_no_findings():
    assert _codes(GOOD) == set()


def test_the_body_is_returned_separately_from_the_fields():
    fields, body = amc.parse_front_matter(GOOD)
    assert fields["project_id"] == "smartmatch"
    assert body.startswith("Read ADR-0005")
    assert "schema:" not in body


def test_a_list_field_parses_as_a_list():
    fields, _ = amc.parse_front_matter(GOOD)
    assert fields["sources"] == [
        "docs/architecture/decisions/"
        "ADR-0005-transactional-outbox-and-cte-claim.md@abc123"
    ]
    assert fields["conflicts_with"] == []


def test_a_record_without_front_matter_is_rejected():
    with pytest.raises(amc.FrontMatterError):
        amc.parse_front_matter("no front matter here\n")


def test_unclosed_front_matter_is_rejected():
    with pytest.raises(amc.FrontMatterError):
        amc.parse_front_matter("---\nschema: x\n\nbody\n")


def test_a_nested_mapping_is_rejected_rather_than_silently_flattened():
    """The grammar is flat on purpose; nesting must fail loudly."""
    record = GOOD.replace(
        "produced_by_tool: claude-code",
        "produced_by:\n    tool: claude-code",
    )
    with pytest.raises(amc.FrontMatterError):
        amc.parse_front_matter(record)


def test_a_duplicate_key_is_rejected():
    record = GOOD.replace("status: approved", "status: approved\nstatus: revoked")
    with pytest.raises(amc.FrontMatterError):
        amc.parse_front_matter(record)


# ---------------------------------------------------------------------------
# Field rules
# ---------------------------------------------------------------------------


def test_a_missing_required_field_is_reported():
    record = GOOD.replace("reviewed_by: maintainer\n", "")
    assert "missing-field" in _codes(record)


def test_an_unknown_field_is_reported():
    record = GOOD.replace("status: approved", "status: approved\nvibes: good")
    assert "unknown-field" in _codes(record)


def test_an_unknown_status_is_reported():
    assert "bad-status" in _codes(GOOD.replace("status: approved", "status: vibing"))


def test_authority_decision_is_refused():
    """Decisions are ADRs. Memory may not hold one."""
    record = GOOD.replace("authority: observation", "authority: decision")
    assert "bad-authority" in _codes(record)


def test_a_privacy_class_other_than_repo_public_is_refused():
    record = GOOD.replace("privacy_class: repo-public", "privacy_class: internal")
    assert "bad-privacy-class" in _codes(record)


def test_external_research_without_an_expiry_is_refused():
    record = GOOD.replace("authority: observation", "authority: external-research")
    assert "missing-expiry" in _codes(record)


def test_external_research_with_an_expiry_is_accepted():
    record = GOOD.replace("authority: observation", "authority: external-research")
    record = record.replace("expires_at: null", "expires_at: 2026-09-23T00:00:00Z")
    assert "missing-expiry" not in _codes(record)


def test_a_record_with_no_sources_is_refused():
    record = GOOD.replace(
        "sources:\n  - docs/architecture/decisions/"
        "ADR-0005-transactional-outbox-and-cte-claim.md@abc123\n",
        "sources:\n",
    )
    assert "no-sources" in _codes(record)
