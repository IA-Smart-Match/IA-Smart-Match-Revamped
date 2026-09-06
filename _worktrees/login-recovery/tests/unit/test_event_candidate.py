"""The public contact-free candidate seam (V3 / P6 Stage 0, fixture-only).

These tests are the specification for `smartmatch_domain.event_candidate`, the
safe exposed-wrapper design authorized by
`docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
§7 and the "P6 Stage 0 scope" row of §3.3. The unsigned P6/R3 stop-gate is
**not** passed; only this wrapper — internal parser, allowlist projection,
`ContactFreeEventCandidate` — is authorized, with no runtime caller.

Every case runs against a committed synthetic fixture. `contact_free_
candidate.ics` and `contact_free_candidate.jsonld` under
`tests/fixtures/event_sources/` carry four distinctive, greppable synthetic
sentinel values, placed exactly as documented in each fixture:

* Organizer name: ``ZZQORGANIZER-NAME`` — placed in the source's organizer
  display name (`ORGANIZER;CN=` / `organizer.name`), which both internal
  parsers *do* read into `ParsedSourceEvent.organizer_name`. Its absence from
  the public candidate proves the wrapper's own allowlist drops it — this is
  the core test of the design, not a test of the parser.
* Contact name: ``ZZQCONTACT-NAME`` — placed only in `ATTENDEE` (iCal) and
  `organizer.contactPoint.name` (JSON-LD), properties neither parser reads at
  all.
* Email: ``zzqcontact@example.invalid`` / ``zzqorganizer@example.invalid`` —
  placed both in never-read contact properties *and* in the `DESCRIPTION`/
  `description` free text, where the parser's own MP-4 redaction replaces it
  with a redaction marker before this module ever sees it.
* Phone: ``+1-555-0100-ZZQ`` — placed only in never-read contact properties
  (`ATTENDEE`, `organizer.telephone`/`contactPoint.telephone`).

The four required properties under test:

1. The contact fields are absent from the candidate type and its serialized
   shape (`TestCandidateTypeExcludesContactFields`).
2. None of the four distinctive sentinel values cross the wrapper, checked by
   recursively stringifying the whole returned candidate
   (`TestNoSentinelCrossesTheWrapper`).
3. Malformed/unsupported fixtures fail closed with a typed `CandidateRefusal`
   (`TestMalformedFixturesFailClosed`).
4. The seam performs no network, filesystem, model dispatch, or persistence
   (`TestSeamPerformsNoIO`).
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest
from smartmatch_domain.event_candidate import (
    CandidateRefusal,
    CandidateRefusalReason,
    ContactFreeEventCandidate,
    candidates_from_ical_fixture,
    candidates_from_jsonld_fixture,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "event_sources"

SOURCE_ZONE = "America/Los_Angeles"

#: The four distinctive synthetic sentinel values embedded in both fixtures.
#: See the module docstring for exactly where each one is placed and why.
ORGANIZER_NAME_SENTINEL = "ZZQORGANIZER-NAME"
CONTACT_NAME_SENTINEL = "ZZQCONTACT-NAME"
EMAIL_SENTINELS = ("zzqcontact@example.invalid", "zzqorganizer@example.invalid")
PHONE_SENTINEL = "+1-555-0100-ZZQ"

ALL_SENTINELS = (ORGANIZER_NAME_SENTINEL, CONTACT_NAME_SENTINEL, *EMAIL_SENTINELS, PHONE_SENTINEL)

#: The exact, closed field set `ContactFreeEventCandidate` may carry. Any name
#: suggesting organizer, contact, or a catch-all is a design regression.
EXPECTED_CANDIDATE_FIELDS = frozenset(
    {
        "title",
        "event_time",
        "source_uid_digest",
        "source_url",
        "location",
        "description",
        "raw_tags",
        "is_cancelled",
        "has_unexpanded_recurrence",
    }
)

#: Substrings that must never appear in a `ContactFreeEventCandidate` field
#: name — organizer/contact identity, or a generic escape hatch a leak could
#: travel through.
FORBIDDEN_FIELD_NAME_SUBSTRINGS = (
    "organizer",
    "contact",
    "email",
    "phone",
    "raw_prop",
    "extra",
    "meta",
)


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _ical_candidates() -> tuple[ContactFreeEventCandidate, ...]:
    result = candidates_from_ical_fixture(
        _load("contact_free_candidate.ics"), source_time_zone=SOURCE_ZONE
    )
    assert isinstance(result, tuple), "expected a successful candidate tuple, not a refusal"
    return result


def _jsonld_candidates() -> tuple[ContactFreeEventCandidate, ...]:
    result = candidates_from_jsonld_fixture(
        _load("contact_free_candidate.jsonld"), source_time_zone=SOURCE_ZONE
    )
    assert isinstance(result, tuple), "expected a successful candidate tuple, not a refusal"
    return result


def _recursive_text(value: object) -> str:
    """Flatten any value — dataclass, tuple, string, whatever — into one string.

    Used to prove a sentinel is absent *anywhere* in a returned value, not just
    in the one or two fields a hand-picked check happens to look at. Frozen
    dataclasses (`ContactFreeEventCandidate` and the `EventTime` variants) fall
    through to `repr`, whose default implementation already recurses into every
    field, nested dataclass included.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return repr(value)
    if isinstance(value, (tuple, list, set, frozenset)):
        return " ".join(_recursive_text(item) for item in value)
    return repr(value)


class TestCandidateTypeExcludesContactFields:
    """Property 1: contact fields are absent from the type and its shape."""

    def test_dataclass_field_names_are_exactly_the_allowlist(self) -> None:
        names = {f.name for f in dataclasses.fields(ContactFreeEventCandidate)}
        assert names == EXPECTED_CANDIDATE_FIELDS

    def test_no_field_name_or_annotation_suggests_contact_data_or_a_catch_all(self) -> None:
        for f in dataclasses.fields(ContactFreeEventCandidate):
            lowered = f.name.lower()
            for forbidden in FORBIDDEN_FIELD_NAME_SUBSTRINGS:
                assert forbidden not in lowered, f"field {f.name!r} looks contact-shaped"
            # No `dict[str, Any]` / `**extra`-shaped catch-all field.
            assert "dict" not in str(f.type).lower()
            assert "any" not in str(f.type).lower()

    def test_type_carries_no_raw_or_extra_attribute(self) -> None:
        (candidate,) = _ical_candidates()
        for banned in ("raw", "extra", "organizer_name", "organizer", "contact"):
            assert not hasattr(candidate, banned)

    def test_serialized_shape_has_no_contact_keys(self) -> None:
        """`dataclasses.asdict` is the serialized shape a caller would persist
        or transmit; its keys must match the allowlist exactly."""
        (candidate,) = _ical_candidates()
        serialized = dataclasses.asdict(candidate)
        assert set(serialized.keys()) == EXPECTED_CANDIDATE_FIELDS
        for forbidden in FORBIDDEN_FIELD_NAME_SUBSTRINGS:
            assert forbidden not in " ".join(serialized.keys()).lower()

    def test_ical_source_parsed_organizer_name_but_wrapper_dropped_it(self) -> None:
        """The load-bearing assertion: the *internal* parser did retain the
        sentinel (proving this is a real allowlist test, not a fixture that
        never carried the value), and the public candidate does not have it."""
        from smartmatch_domain.ical_parser import parse_ical

        (parsed,) = parse_ical(_load("contact_free_candidate.ics"), source_time_zone=SOURCE_ZONE)
        assert parsed.organizer_name == ORGANIZER_NAME_SENTINEL

        (candidate,) = _ical_candidates()
        assert not hasattr(candidate, "organizer_name")

    def test_jsonld_source_parsed_organizer_name_but_wrapper_dropped_it(self) -> None:
        from smartmatch_domain.jsonld_parser import parse_jsonld

        (parsed,) = parse_jsonld(
            _load("contact_free_candidate.jsonld"), source_time_zone=SOURCE_ZONE
        )
        assert parsed.organizer_name == ORGANIZER_NAME_SENTINEL

        (candidate,) = _jsonld_candidates()
        assert not hasattr(candidate, "organizer_name")


class TestNoSentinelCrossesTheWrapper:
    """Property 2: none of the four sentinel values reach the candidate.

    Every emitted string field is covered: `title`, `description`, `location`,
    `raw_tags`, and `source_url` are all present on `ContactFreeEventCandidate`
    and are all included by `_recursive_text`'s walk over every field.
    """

    @pytest.mark.parametrize("loader", [_ical_candidates, _jsonld_candidates])
    def test_no_sentinel_anywhere_in_the_full_candidate(self, loader) -> None:
        (candidate,) = loader()
        blob = _recursive_text(candidate)
        for sentinel in ALL_SENTINELS:
            assert sentinel not in blob, f"{sentinel!r} leaked into the candidate: {blob!r}"

    @pytest.mark.parametrize("loader", [_ical_candidates, _jsonld_candidates])
    def test_no_sentinel_in_any_individual_named_field(self, loader) -> None:
        """Belt-and-suspenders: check each emitted string field by name too,
        not only the aggregate blob."""
        (candidate,) = loader()
        named_text_fields = (
            candidate.title,
            candidate.description or "",
            candidate.location or "",
            candidate.source_url or "",
            *candidate.raw_tags,
        )
        for field_text in named_text_fields:
            for sentinel in ALL_SENTINELS:
                assert sentinel not in field_text

    def test_ical_candidate_still_carries_the_expected_safe_content(self) -> None:
        """A leak-free candidate that is also empty would be a hollow proof —
        confirm the safe fields survived the trip."""
        (candidate,) = _ical_candidates()
        assert candidate.title == "Spring Analytics Hackathon"
        assert candidate.location == "Engineering Building, Room 101"
        assert candidate.raw_tags == ("Competitions", "Student Life")
        assert candidate.source_url == (
            "https://example.edu/events/spring-analytics-hackathon-candidate"
        )
        assert candidate.description is not None
        assert "[redacted]" in candidate.description

    def test_ical_candidate_digests_rather_than_carries_the_source_uid(self) -> None:
        """The fixture's UID is address-shaped; the digest is what crosses."""
        (candidate,) = _ical_candidates()
        raw_uid = "synthetic-candidate-0001@example.edu"
        assert candidate.source_uid_digest == hashlib.sha256(raw_uid.encode()).hexdigest()
        assert candidate.source_uid_digest is not None
        assert raw_uid not in candidate.source_uid_digest
        assert "@" not in candidate.source_uid_digest

    def test_jsonld_candidate_still_carries_the_expected_safe_content(self) -> None:
        (candidate,) = _jsonld_candidates()
        assert candidate.title == "Spring Analytics Hackathon"
        assert candidate.location == "Engineering Building, Room 101"
        assert candidate.raw_tags == ("Competitions", "Student Life")
        assert candidate.description is not None
        assert "[contact removed]" in candidate.description


class TestSourceUidNeverCrossesVerbatim:
    """Property: an address-shaped UID cannot reach the public seam.

    RFC 5545 suggests a domain-qualified UID and every committed fixture has
    one, so a verbatim `source_uid` would carry an email address through a
    seam whose whole claim is that it carries none. The digest is what makes
    that impossible rather than merely unlikely.
    """

    #: An email sentinel placed where a source's UID goes, not in prose.
    UID_EMAIL_SENTINEL = "zzquid-person@example.invalid"

    def _candidate_from_uid(self, uid: str) -> ContactFreeEventCandidate:
        text = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//synthetic//test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            "DTSTART:20260901T120000Z\r\n"
            "SUMMARY:Synthetic Event\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        outcome = candidates_from_ical_fixture(text, source_time_zone="America/Los_Angeles")
        assert not isinstance(outcome, CandidateRefusal)
        (candidate,) = outcome
        return candidate

    def test_an_email_shaped_uid_does_not_appear_anywhere_in_the_candidate(self) -> None:
        candidate = self._candidate_from_uid(self.UID_EMAIL_SENTINEL)
        assert self.UID_EMAIL_SENTINEL not in repr(candidate)
        for value in dataclasses.astuple(candidate):
            assert self.UID_EMAIL_SENTINEL not in str(value)

    def test_the_local_part_of_an_email_shaped_uid_does_not_survive_either(self) -> None:
        """A digest, not a domain strip — the local part is identifying too."""
        candidate = self._candidate_from_uid(self.UID_EMAIL_SENTINEL)
        assert "zzquid-person" not in repr(candidate)

    def test_the_same_uid_always_digests_to_the_same_value(self) -> None:
        """Identity across two reads of a source is what a UID is kept for."""
        first = self._candidate_from_uid("synthetic-0042@example.edu")
        second = self._candidate_from_uid("synthetic-0042@example.edu")
        assert first.source_uid_digest == second.source_uid_digest

    def test_two_different_uids_digest_differently(self) -> None:
        first = self._candidate_from_uid("synthetic-0042@example.edu")
        second = self._candidate_from_uid("synthetic-0043@example.edu")
        assert first.source_uid_digest != second.source_uid_digest

    def test_the_digest_is_hex_and_carries_no_source_punctuation(self) -> None:
        candidate = self._candidate_from_uid(self.UID_EMAIL_SENTINEL)
        assert candidate.source_uid_digest is not None
        assert all(character in "0123456789abcdef" for character in candidate.source_uid_digest)


class TestMalformedFixturesFailClosed:
    """Property 3: malformed/unsupported fixtures fail closed, typed.

    Reuses the already-committed malformed fixtures the parser test suites
    exercise (`truncated.ics`, `malformed.jsonld`) — this fence forbids
    modifying existing fixtures, and these already carry no contact-sentinel
    content and are proven-malformed by the parsers' own test suites.
    """

    def test_structurally_malformed_ical_returns_a_typed_refusal(self) -> None:
        result = candidates_from_ical_fixture(_load("truncated.ics"), source_time_zone=SOURCE_ZONE)
        assert result == CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_ICAL)

    def test_nested_vevent_ical_returns_a_typed_refusal(self) -> None:
        result = candidates_from_ical_fixture(
            _load("nested_vevent.ics"), source_time_zone=SOURCE_ZONE
        )
        assert result == CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_ICAL)

    def test_malformed_jsonld_returns_a_typed_refusal(self) -> None:
        result = candidates_from_jsonld_fixture(
            _load("malformed.jsonld"), source_time_zone=SOURCE_ZONE
        )
        assert result == CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_JSONLD)

    def test_blank_source_time_zone_returns_a_typed_refusal_not_a_raise(self) -> None:
        """An unsupported *call*, not just an unsupported document, still fails
        closed as a typed value rather than propagating the parser's raise."""
        result = candidates_from_ical_fixture(
            _load("contact_free_candidate.ics"), source_time_zone=""
        )
        assert result == CandidateRefusal(reason=CandidateRefusalReason.UNPARSEABLE_ICAL)

    def test_refusal_carries_no_exception_object_or_partial_candidate(self) -> None:
        result = candidates_from_ical_fixture(_load("truncated.ics"), source_time_zone=SOURCE_ZONE)
        assert isinstance(result, CandidateRefusal)
        fields = {f.name for f in dataclasses.fields(CandidateRefusal)}
        assert fields == {"reason"}
        assert isinstance(result.reason, CandidateRefusalReason)


class TestSeamPerformsNoIO:
    """Property 4: no network, filesystem, model dispatch, or persistence."""

    def test_module_imports_are_limited_to_stdlib_and_the_two_parsers(self) -> None:
        """Static proof: the module's own `import`/`from ... import` statements
        name only the standard library and the two internal parser modules —
        nothing capable of network, filesystem, subprocess, ORM, or a model
        client is even importable from here."""
        import ast
        import importlib.util

        spec = importlib.util.find_spec("smartmatch_domain.event_candidate")
        assert spec is not None and spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)

        allowed_roots = {
            "__future__",
            "dataclasses",
            "enum",
            # Pure stdlib, and the reason the seam can digest a source UID
            # rather than carry it verbatim. No I/O of any kind.
            "hashlib",
            "typing",
            "smartmatch_domain",
        }
        forbidden_roots = {
            "os",
            "pathlib",
            "socket",
            "subprocess",
            "sqlalchemy",
            "fastapi",
            "httpx",
            "requests",
            "boto3",
            "smartmatch_providers",
            "smartmatch_persistence",
        }

        found_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                found_roots.add(node.module.split(".")[0])

        assert found_roots <= allowed_roots, f"unexpected import root(s): {found_roots}"
        assert not (found_roots & forbidden_roots)

    def test_wrapper_performs_no_filesystem_or_socket_access(self, monkeypatch) -> None:
        """Functional proof, not just static: patch `open` and `socket.socket`
        to fail loudly, then confirm the wrapper still succeeds using only the
        `text` argument already in hand."""
        import builtins
        import socket

        ical_text = _load("contact_free_candidate.ics")
        jsonld_text = _load("contact_free_candidate.jsonld")

        def _forbidden_open(*args: object, **kwargs: object) -> None:
            raise AssertionError("event_candidate must not touch the filesystem")

        def _forbidden_socket(*args: object, **kwargs: object) -> None:
            raise AssertionError("event_candidate must not touch the network")

        monkeypatch.setattr(builtins, "open", _forbidden_open)
        monkeypatch.setattr(socket, "socket", _forbidden_socket)

        ical_result = candidates_from_ical_fixture(ical_text, source_time_zone=SOURCE_ZONE)
        jsonld_result = candidates_from_jsonld_fixture(jsonld_text, source_time_zone=SOURCE_ZONE)

        assert isinstance(ical_result, tuple) and len(ical_result) == 1
        assert isinstance(jsonld_result, tuple) and len(jsonld_result) == 1

    def test_no_persistence_or_model_dispatch_symbol_is_reachable(self) -> None:
        """No repository, session, provider, or model-client symbol is even
        importable from this module's namespace — there is nothing here for a
        caller to invoke even by accident."""
        import smartmatch_domain.event_candidate as module

        banned_substrings = ("session", "repository", "provider", "client", "dispatch", "publish")
        for name in dir(module):
            lowered = name.lower()
            for banned in banned_substrings:
                assert banned not in lowered, f"unexpected symbol {name!r} on the public seam"
