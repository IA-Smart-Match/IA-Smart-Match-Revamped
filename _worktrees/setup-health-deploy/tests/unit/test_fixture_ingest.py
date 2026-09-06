"""The fixture-only crawl/ingest scaffold (`smartmatch_providers.fixture_ingest`).

These tests are the specification for the reading-and-assembly half of card S6
(`docs/plans/2026-08-28-g3-events-s3-s5-plan.md`), written while the fetching
half is unauthorized: the signed threat model
(`docs/security/crawler-threat-model-draft.md` revision 4, ratified 2026-09-03,
recorded in `docs/decisions/r3-signing-decisions-2026-09-03.md`) states plainly
that it "does **not** authorize HTTP crawl code".

Four properties are pinned here, in this order:

1. **A URL is refused, not attempted** (`TestOnlyLocalPathsAreAccepted`). The
   refusal happens before the filesystem is touched and before any parser
   runs, and it is refused for being URL-shaped rather than for happening not
   to exist — a distinction that matters, because "not found" would quietly
   become "found" the day someone added a fetch.
2. **Nothing outside the root is readable** (`TestContainment`), including via
   `..`, an absolute path, or a symlink pointing away.
3. **Unknown is not zero (ADR-0011)** (`TestUnknownIsNotZero`). An event whose
   source states no date stays unkeyed *and is still returned*; a tag the
   vocabulary does not recognize is quarantined on the returned structure *and
   is still reachable*. Both failure modes this guards against — dropping the
   event, and dropping the tag — would look like success to a caller counting
   rows.
4. **Malformed documents fail closed** (`TestMalformedFailsClosed`), carrying
   the Stage 0 typed refusal rather than an empty tuple that reads as "the
   source published nothing today".

Every input is a committed synthetic fixture under
`tests/fixtures/crawl_sources/` or a file the test writes into `tmp_path`. No
test here reaches a network, and the module under test has no way to.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from smartmatch_domain.event_candidate import CandidateRefusal, CandidateRefusalReason
from smartmatch_domain.events import (
    DateOnlyTime,
    ExactTime,
    TagVocabulary,
    UnresolvedTime,
)
from smartmatch_providers.fixture_ingest import (
    MAX_FIXTURE_BYTES,
    FixtureRejected,
    FixtureSourceFormat,
    IngestReport,
    RejectionReason,
    format_for_suffix,
    ingest_fixture_directory,
    ingest_fixture_file,
    read_fixture_document,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl_sources"

SOURCE_ZONE = "America/Los_Angeles"

#: The org unit under which these synthetic events are keyed. Supplied by the
#: caller, never read out of the document — ADR-0012 keys on the host org unit
#: precisely so two pages describing the same event agree.
HOST_ORG_UNIT = "synthetic-university"

#: A deliberately tiny vocabulary. "careers" is in it; every other tag in the
#: fixture tree is not, which is what makes the quarantine assertions below
#: about behavior rather than about vocabulary content. The real terms are an
#: S5 product decision (ADR-0012 declines to make it).
VOCABULARY = TagVocabulary(version="v0-scaffold", terms=frozenset({"careers"}))


def _ingest(location: Path | str, **overrides: object) -> IngestReport:
    """Ingest one fixture with the standard synthetic settings."""
    kwargs: dict[str, object] = {
        "root": FIXTURES,
        "source_time_zone": SOURCE_ZONE,
        "host_org_unit": HOST_ORG_UNIT,
        "vocabulary": VOCABULARY,
    }
    kwargs.update(overrides)
    return ingest_fixture_file(location, **kwargs)  # type: ignore[arg-type]


def _module_source() -> str:
    """The module under test, as text, for the structural guards below."""
    import smartmatch_providers.fixture_ingest as module

    assert module.__file__ is not None
    return Path(module.__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Only local paths. A URL is refused, not fetched and not "not found".
# ---------------------------------------------------------------------------


class TestOnlyLocalPathsAreAccepted:
    """The loader takes filesystem paths. It has no concept of a remote source."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.edu/events.ics",
            "http://example.edu/events.ics",
            "HTTPS://EXAMPLE.EDU/events.ics",
            "  https://example.edu/events.ics",
            "file:///etc/passwd",
            "ftp://example.edu/events.ics",
            "data:text/calendar;base64,QkVHSU4=",
        ],
    )
    def test_a_url_is_refused_as_not_a_local_path(self, url: str):
        """Refused for *being a URL*, not for failing to exist.

        The reason code is the whole point. `NOT_A_FILE` would mean the loader
        tried to treat it as a path and found nothing there — behavior that
        turns into a live fetch the moment a transport is added. Refusing it as
        `NOT_A_LOCAL_PATH` means the string never became a candidate at all.
        """
        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document(url, root=FIXTURES)

        assert excinfo.value.reason is RejectionReason.NOT_A_LOCAL_PATH

    def test_a_url_is_refused_by_the_ingest_entry_point_too(self):
        """Not only by the reader — the caller-facing function refuses it as well."""
        with pytest.raises(FixtureRejected) as excinfo:
            _ingest("https://example.edu/events.ics")

        assert excinfo.value.reason is RejectionReason.NOT_A_LOCAL_PATH

    def test_a_url_is_refused_by_the_directory_walk_too(self):
        with pytest.raises(FixtureRejected) as excinfo:
            ingest_fixture_directory(
                "https://example.edu/events/",
                root=FIXTURES,
                source_time_zone=SOURCE_ZONE,
                host_org_unit=HOST_ORG_UNIT,
                vocabulary=VOCABULARY,
            )

        assert excinfo.value.reason is RejectionReason.NOT_A_LOCAL_PATH

    def test_the_module_imports_no_http_client(self):
        """A structural guard, not a behavioral one.

        Asserting "this call made no request" only covers the paths a test
        happens to exercise. Asserting the module's import list contains no
        transport covers every path, including ones not written yet.
        """
        imported: set[str] = set()
        for node in ast.walk(ast.parse(_module_source())):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        forbidden = {
            "urllib",
            "urllib3",
            "http",
            "httpx",
            "requests",
            "aiohttp",
            "socket",
            "ssl",
            "ftplib",
            "subprocess",
        }
        assert not (imported & forbidden), f"transport imported: {sorted(imported & forbidden)}"

    def test_a_windows_drive_letter_is_still_a_path(self):
        """The scheme rule must not swallow `C:\\...`.

        A one-character scheme is a drive letter, not a protocol. Pinned so a
        future tightening of the pattern cannot make Windows checkouts
        unreadable without failing here first.
        """
        from smartmatch_providers.fixture_ingest import _SCHEME_PATTERN

        assert _SCHEME_PATTERN.match("https://example.edu/a.ics")
        assert not _SCHEME_PATTERN.match(r"C:\fixtures\a.ics")


# ---------------------------------------------------------------------------
# 2. Containment. Nothing outside the caller's root is readable.
# ---------------------------------------------------------------------------


class TestContainment:
    """The root is a boundary, not a default."""

    def test_a_relative_path_is_resolved_against_the_root(self):
        report = _ingest("campus_calendar.ics")

        assert report.source == "campus_calendar.ics"
        assert report.source_format is FixtureSourceFormat.ICAL

    def test_a_dot_dot_escape_is_refused(self):
        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document("../event_sources/date_only.ics", root=FIXTURES)

        assert excinfo.value.reason is RejectionReason.OUTSIDE_ROOT

    def test_an_absolute_path_outside_the_root_is_refused(self, tmp_path: Path):
        outside = tmp_path / "elsewhere.ics"
        outside.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")

        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document(outside, root=FIXTURES)

        assert excinfo.value.reason is RejectionReason.OUTSIDE_ROOT

    def test_a_symlink_pointing_outside_the_root_is_refused(self, tmp_path: Path):
        """Containment is about where the bytes are, not how the path is spelled.

        A root-relative name that resolves elsewhere is exactly how a
        containment check written against the *unresolved* path gets bypassed.
        """
        root = tmp_path / "root"
        root.mkdir()
        secret = tmp_path / "outside.ics"
        secret.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
        link = root / "innocent.ics"
        try:
            link.symlink_to(secret)
        except (OSError, NotImplementedError):  # pragma: no cover - unprivileged Windows
            pytest.skip("symlink creation is not permitted in this environment")

        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document("innocent.ics", root=root)

        assert excinfo.value.reason is RejectionReason.OUTSIDE_ROOT

    def test_a_missing_file_inside_the_root_is_refused_as_not_a_file(self):
        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document("no_such_calendar.ics", root=FIXTURES)

        assert excinfo.value.reason is RejectionReason.NOT_A_FILE

    def test_an_unrecognized_suffix_is_refused_rather_than_sniffed(self):
        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document("README.md", root=FIXTURES)

        assert excinfo.value.reason is RejectionReason.UNSUPPORTED_FORMAT

    def test_non_utf8_bytes_are_refused_rather_than_mangled(self, tmp_path: Path):
        bad = tmp_path / "latin1.ics"
        bad.write_bytes(b"BEGIN:VCALENDAR\nSUMMARY:caf\xe9\nEND:VCALENDAR\n")

        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document(bad, root=tmp_path)

        assert excinfo.value.reason is RejectionReason.UNDECODABLE

    def test_a_document_past_the_byte_cap_is_refused(self, tmp_path: Path):
        """The 5 MiB cap the R3 signing record fixed for T-04."""
        oversized = tmp_path / "huge.ics"
        oversized.write_bytes(b"x" * (MAX_FIXTURE_BYTES + 1))

        with pytest.raises(FixtureRejected) as excinfo:
            read_fixture_document(oversized, root=tmp_path)

        assert excinfo.value.reason is RejectionReason.TOO_LARGE

    def test_suffix_mapping_is_case_insensitive_and_closed(self):
        assert format_for_suffix(".ICS") is FixtureSourceFormat.ICAL
        assert format_for_suffix(".jsonld") is FixtureSourceFormat.JSONLD
        assert format_for_suffix(".md") is None
        assert format_for_suffix("") is None


# ---------------------------------------------------------------------------
# 3. Unknown is not zero (ADR-0011).
# ---------------------------------------------------------------------------


class TestUnknownIsNotZero:
    """Unresolved dates stay unkeyed; unmapped tags stay quarantined and visible."""

    @pytest.fixture
    def calendar(self) -> IngestReport:
        return _ingest("campus_calendar.ics")

    def test_both_events_are_returned(self, calendar: IngestReport):
        """Including the one with no date. Dropping it is the defect."""
        assert [event.candidate.title for event in calendar.events] == [
            "Spring Analytics Hackathon",
            "Guest Lecture - date to be announced",
        ]

    def test_the_dated_event_resolves_to_an_identity_key(self, calendar: IngestReport):
        dated = calendar.events[0]

        assert isinstance(dated.candidate.event_time, ExactTime)
        assert dated.is_keyed
        assert dated.identity_key is not None
        assert dated.identity_key.host_org_unit == HOST_ORG_UNIT
        assert dated.identity_key.normalized_title == "spring analytics hackathon"
        assert dated.identity_key.resolved_date == date(2026, 4, 15)

    def test_the_undated_event_stays_unresolved_and_unkeyed(self, calendar: IngestReport):
        """No fabricated date, and therefore no fabricated key.

        The alternative failure — defaulting to today, or to midnight — is the
        exact defect ADR-0010 and ADR-0012 exist to prevent, and it would make
        this event silently collide with any other undated event.
        """
        undated = calendar.events[1]

        assert isinstance(undated.candidate.event_time, UnresolvedTime)
        assert not undated.is_keyed
        assert undated.identity_key is None

    def test_the_report_names_which_events_are_unkeyed(self, calendar: IngestReport):
        """Countable, not merely absent — a caller can report the gap."""
        assert [event.candidate.title for event in calendar.unkeyed_events] == [
            "Guest Lecture - date to be announced"
        ]

    def test_a_known_tag_maps_and_an_unknown_tag_is_quarantined(self, calendar: IngestReport):
        dated = calendar.events[0]

        assert [tag.term for tag in dated.mapped_tags] == ["careers"]
        assert [tag.raw_value for tag in dated.quarantined] == ["Quidditch Club"]

    def test_a_quarantined_tag_is_carried_not_dropped(self, calendar: IngestReport):
        """Reachable from the report, and stamped with the vocabulary version.

        Silently dropping it would leave a caller unable to distinguish "this
        source used only known tags" from "this source used tags we threw
        away", which is the review-queue signal S5 depends on.
        """
        quarantined = calendar.quarantined

        assert [tag.raw_value for tag in quarantined] == ["Quidditch Club"]
        assert {tag.vocabulary_version for tag in quarantined} == {"v0-scaffold"}

    def test_a_quarantined_tag_exposes_no_matchable_term(self, calendar: IngestReport):
        """ADR-0012: quarantined values are never rendered and never matched on."""
        assert not hasattr(calendar.quarantined[0], "term")

    def test_mapped_and_quarantined_together_account_for_every_raw_tag(
        self, calendar: IngestReport
    ):
        """A partition, not a filter. Nothing falls between the two buckets."""
        for event in calendar.events:
            assert len(event.mapped_tags) + len(event.quarantined) == len(event.candidate.raw_tags)

    def test_a_date_only_jsonld_event_keys_on_its_stated_date(self):
        report = _ingest("department/seminar_series.jsonld")

        assert report.source_format is FixtureSourceFormat.JSONLD
        (event,) = report.events
        assert isinstance(event.candidate.event_time, DateOnlyTime)
        assert event.is_keyed
        assert event.identity_key is not None
        assert event.identity_key.resolved_date == date(2026, 9, 20)
        assert [tag.raw_value for tag in event.quarantined] == ["Underwater Basket Weaving"]

    def test_no_organizer_or_contact_field_survives_into_the_ingest(self):
        """The Stage 0 allowlist still holds through this layer.

        This module wraps `ContactFreeEventCandidate`; it must not have grown
        a field that reintroduces what that type omits.
        """
        report = _ingest("campus_calendar.ics")
        candidate = report.events[0].candidate

        for absent in ("organizer_name", "attendees", "raw", "contact_email"):
            assert not hasattr(candidate, absent)


# ---------------------------------------------------------------------------
# 4. Malformed documents fail closed, visibly.
# ---------------------------------------------------------------------------


class TestMalformedFailsClosed:
    """A broken feed is a refusal, never an empty success."""

    def test_a_truncated_calendar_yields_a_typed_refusal(self):
        report = _ingest("department/unterminated.ics")

        assert report.refused
        assert isinstance(report.refusal, CandidateRefusal)
        assert report.refusal.reason is CandidateRefusalReason.UNPARSEABLE_ICAL

    def test_a_refusal_reports_no_events_but_is_distinguishable_from_empty(self):
        """`events == ()` alone is ambiguous; `refused` is what disambiguates it."""
        report = _ingest("department/unterminated.ics")

        assert report.events == ()
        assert report.refused is True

    def test_an_unknown_time_zone_is_a_refusal_not_a_substitution(self):
        report = _ingest("campus_calendar.ics", source_time_zone="Mars/Olympus_Mons")

        assert report.refused
        assert report.refusal is not None
        assert report.refusal.reason is CandidateRefusalReason.UNPARSEABLE_ICAL

    def test_a_blank_host_org_unit_is_refused_by_the_domain(self):
        """Not absorbed into a report. An unkeyable ingest is a caller error."""
        with pytest.raises(ValueError, match="host_org_unit"):
            _ingest("campus_calendar.ics", host_org_unit="   ")


# ---------------------------------------------------------------------------
# The directory walk.
# ---------------------------------------------------------------------------


class TestDirectoryWalk:
    """Deterministic, recursive, and tolerant of non-source files."""

    @pytest.fixture
    def reports(self) -> tuple[IngestReport, ...]:
        return ingest_fixture_directory(
            FIXTURES,
            root=FIXTURES,
            source_time_zone=SOURCE_ZONE,
            host_org_unit=HOST_ORG_UNIT,
            vocabulary=VOCABULARY,
        )

    def test_every_recognized_document_is_reported_in_sorted_order(
        self, reports: tuple[IngestReport, ...]
    ):
        assert [report.source for report in reports] == [
            "campus_calendar.ics",
            "department/seminar_series.jsonld",
            "department/unterminated.ics",
        ]

    def test_the_readme_is_skipped_rather_than_refused(self, reports: tuple[IngestReport, ...]):
        """A non-source file beside the fixtures is not an ingest failure."""
        assert all(not report.source.endswith(".md") for report in reports)

    def test_the_broken_document_still_gets_a_report(self, reports: tuple[IngestReport, ...]):
        """Skipping it would make a broken feed indistinguishable from an absent one."""
        broken = [report for report in reports if report.refused]

        assert [report.source for report in broken] == ["department/unterminated.ics"]

    def test_the_walk_is_repeatable(self, reports: tuple[IngestReport, ...]):
        again = ingest_fixture_directory(
            FIXTURES,
            root=FIXTURES,
            source_time_zone=SOURCE_ZONE,
            host_org_unit=HOST_ORG_UNIT,
            vocabulary=VOCABULARY,
        )

        assert [report.source for report in again] == [report.source for report in reports]
        assert again[0].events[0].identity_key == reports[0].events[0].identity_key

    def test_a_file_is_refused_where_a_directory_is_required(self):
        with pytest.raises(FixtureRejected) as excinfo:
            ingest_fixture_directory(
                FIXTURES / "campus_calendar.ics",
                root=FIXTURES,
                source_time_zone=SOURCE_ZONE,
                host_org_unit=HOST_ORG_UNIT,
                vocabulary=VOCABULARY,
            )

        assert excinfo.value.reason is RejectionReason.NOT_A_FILE

    def test_the_walk_persists_nothing(self):
        """The result is in memory and nowhere else.

        Event persistence is a later card (P-EVENTS-SCHEMA); this scaffold must
        not have quietly acquired it. Checked structurally: the module names no
        session, engine, or table.
        """
        body = "\n".join(
            line for line in _module_source().splitlines() if not line.lstrip().startswith("#")
        )

        for forbidden in ("sqlalchemy", "session.add", "INSERT INTO", "commit()"):
            assert forbidden not in body
