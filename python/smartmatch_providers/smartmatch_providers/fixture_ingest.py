"""Fixture-only event ingest: committed files in, event candidates out.

Scaffold for card S6 (`docs/plans/2026-08-28-g3-events-s3-s5-plan.md` §"Card S6")
with the one capability S6a is about — fetching — deliberately absent. This
module is the *reading and assembly* half of a crawl: it takes documents that
are already in the checkout, runs them through the Stage 0 parsers
(`smartmatch_domain.event_candidate`), resolves ADR-0012 identity keys and tag
vocabulary, and returns the result in memory. It never persists, never
publishes, and never reaches a network.

**No egress, structurally.** The signed threat model
(`docs/security/crawler-threat-model-draft.md`, revision 4, ratified
2026-09-03) does not authorize HTTP crawl code, and T-13's validating
connector does not exist. So this module imports no HTTP client — no
`urllib`, no `httpx`, no `requests`, no `socket` — and the only input it
accepts is a filesystem path underneath a caller-supplied root. A URL is not
an unsupported input that happens to fail later; `read_fixture_document`
rejects anything carrying a scheme *before* it touches the filesystem, so
"pass a URL instead" is not a one-line change away from live crawling. The
absence of a fetch function here is the control, not an unfinished feature.

**Where this lives, and why not the domain.** The Stage 0 parsers and the
contact-free projection are pure and live in `smartmatch_domain`, which the
import contract forbids from importing `os` or `pathlib`
(`pyproject.toml` §importlinter, ADR-0002). Opening a file is therefore a
provider-plane concern by construction, which is why this module sits here
and calls *into* the domain rather than the reverse.

**Deliberately not exported from `smartmatch_providers.__init__`.** The API
and worker composition roots import the package; re-exporting this module
there would import it into both processes for free and quietly undo the
"unwired" property that `tests/unit/test_fixture_ingest_wiring.py` pins.
Callers that want it import `smartmatch_providers.fixture_ingest` explicitly,
which is a visible edit in a diff.

**Unknown is not zero (ADR-0011), twice over.**

* An event whose source states no resolvable date keeps `UnresolvedTime` and
  gets `identity_key is None` — `IngestedEvent.is_keyed` reports that as a
  fact about the event rather than the ingest inventing a date so the row has
  a key. Such an event is still returned; it is unkeyed, not dropped.
* A tag value the vocabulary does not recognize becomes a `QuarantinedTag`
  carried on the returned structure, never a silently discarded string. What
  was quarantined is reachable from the report, so "no unmapped tags" and
  "unmapped tags thrown away" cannot look the same to a caller.

Nothing here is registered on the worker, exposed over HTTP, or written to a
database. Event persistence is a later card (P-EVENTS-SCHEMA).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias

from smartmatch_domain.event_candidate import (
    CandidateRefusal,
    ContactFreeEventCandidate,
    candidates_from_ical_fixture,
    candidates_from_jsonld_fixture,
)
from smartmatch_domain.events import (
    EventIdentityKey,
    MappedTag,
    QuarantinedTag,
    TagVocabulary,
    matchable_tags,
    quarantined_tags,
    resolve_identity_key,
    resolve_tag,
)

__all__ = [
    "FIXTURE_SUFFIXES",
    "MAX_FIXTURE_BYTES",
    "FixtureRejected",
    "FixtureSourceFormat",
    "IngestOutcome",
    "IngestReport",
    "IngestedEvent",
    "RejectionReason",
    "format_for_suffix",
    "ingest_fixture_directory",
    "ingest_fixture_file",
    "read_fixture_document",
]

#: Per-document byte ceiling, matching the 5 MiB cap the R3 signing record
#: fixed for T-04 (`docs/decisions/r3-signing-decisions-2026-09-03.md`). A
#: committed fixture has no business approaching it; the cap is here so the
#: reading path already has one when a fetching path is eventually written
#: against this seam, rather than acquiring one later under time pressure.
MAX_FIXTURE_BYTES = 5 * 1024 * 1024


class FixtureSourceFormat(StrEnum):
    """The document formats this ingest understands.

    A closed set, not a guess: dispatch is by declared format, and
    `format_for_suffix` maps a file suffix onto one. A file whose suffix names
    no format is refused rather than sniffed — content sniffing is how a
    document ends up parsed by something its author never intended.
    """

    ICAL = "ical"
    JSONLD = "jsonld"


#: Suffix-to-format mapping for directory walks. Exhaustive over
#: `FixtureSourceFormat`; anything else in the tree is not a source document.
#: Read-only by convention and never mutated after import — `format_for_suffix`
#: is the only reader.
FIXTURE_SUFFIXES: dict[str, FixtureSourceFormat] = {
    ".ics": FixtureSourceFormat.ICAL,
    ".ical": FixtureSourceFormat.ICAL,
    ".jsonld": FixtureSourceFormat.JSONLD,
    ".json": FixtureSourceFormat.JSONLD,
}


class RejectionReason(StrEnum):
    """Why a requested source was refused before any parsing happened.

    Stable codes rather than free-text messages, for the same reason
    `CandidateRefusalReason` is: a caller branches on a code, and a code
    cannot accidentally carry a fragment of the rejected input into a log.
    """

    #: The location carried a URL scheme — `https://`, `http://`, `file://`,
    #: `data:`, anything. This ingest reads the checkout, not the internet.
    NOT_A_LOCAL_PATH = "not_a_local_path"
    #: The resolved path lies outside the caller's root, whether by `..`, an
    #: absolute path, or a symlink pointing away.
    OUTSIDE_ROOT = "outside_root"
    #: Nothing readable is at the path, or it is a directory.
    NOT_A_FILE = "not_a_file"
    #: The suffix names no `FixtureSourceFormat`.
    UNSUPPORTED_FORMAT = "unsupported_format"
    #: The file exceeds `MAX_FIXTURE_BYTES`.
    TOO_LARGE = "too_large"
    #: The bytes are not valid UTF-8.
    UNDECODABLE = "undecodable"


class FixtureRejected(ValueError):
    """A requested source was refused, with a stable `reason`.

    A `ValueError` subclass so a caller that does not care about the reason
    still fails loudly; the `reason` is there for one that does. Carries no
    document content and no rejected URL text.
    """

    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(f"fixture source rejected: {reason.value}")
        self.reason = reason


#: Any string with a scheme of two or more characters followed by `:`. Two
#: characters, not one, so a Windows drive letter (`C:\\...`) stays a path
#: while `http:`, `https:`, `file:` and `data:` do not. Matched against the
#: caller's *original* text, before `Path` normalization can hide it.
_SCHEME_PATTERN = re.compile(r"^\s*[A-Za-z][A-Za-z0-9+.\-]+\s*:")


def _reject(reason: RejectionReason) -> FixtureRejected:
    """Build the refusal for `reason`. Centralized so every path refuses alike."""
    return FixtureRejected(reason)


def format_for_suffix(suffix: str) -> FixtureSourceFormat | None:
    """The format a file suffix names, or `None` when it names none."""
    return FIXTURE_SUFFIXES.get(suffix.lower())


def _contained(location: str, *, root_path: Path) -> Path:
    """Resolve `location` against `root_path`, refusing URLs and escapes.

    Both entry points share this, so the URL and containment rules cannot
    drift apart between reading a file and walking a directory.
    """
    if _SCHEME_PATTERN.match(location):
        # Checked on the caller's raw text: `Path("https://example.edu/x")`
        # is a perfectly ordinary relative path object, so a check made after
        # `Path()` would see nothing wrong with it.
        raise _reject(RejectionReason.NOT_A_LOCAL_PATH)
    candidate = Path(location)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    # `resolve` follows symlinks, so containment below is a statement about
    # where the bytes actually live, not about how the path was spelled.
    resolved = candidate.resolve()
    if resolved != root_path and root_path not in resolved.parents:
        raise _reject(RejectionReason.OUTSIDE_ROOT)
    return resolved


def read_fixture_document(location: str | Path, *, root: str | Path) -> str:
    """Read one committed source document from inside `root`.

    The only way text enters this module. Every refusal below happens before
    the file is opened, except the size and decode checks, which need bytes.

    Args:
        location: A filesystem path, absolute or relative to `root`. **Not** a
            URL: any value carrying a scheme is refused outright.
        root: The directory the fixture tree lives under — the checkout, or a
            `tests/fixtures` subtree. Resolved, so a symlinked root is
            compared as its real location rather than its alias.

    Returns:
        The document's full text, decoded as UTF-8.

    Raises:
        FixtureRejected: with `RejectionReason.NOT_A_LOCAL_PATH` for anything
            URL-shaped, `OUTSIDE_ROOT` for a path that resolves outside
            `root` (including through a symlink), `UNSUPPORTED_FORMAT` for a
            suffix naming no format, `NOT_A_FILE` when nothing readable is
            there, `TOO_LARGE` past `MAX_FIXTURE_BYTES`, or `UNDECODABLE` for
            bytes that are not UTF-8.
    """
    resolved = _contained(str(location), root_path=Path(root).resolve())
    if format_for_suffix(resolved.suffix) is None:
        raise _reject(RejectionReason.UNSUPPORTED_FORMAT)
    if not resolved.is_file():
        raise _reject(RejectionReason.NOT_A_FILE)

    raw = resolved.read_bytes()
    if len(raw) > MAX_FIXTURE_BYTES:
        raise _reject(RejectionReason.TOO_LARGE)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _reject(RejectionReason.UNDECODABLE) from exc


@dataclass(frozen=True, slots=True)
class IngestedEvent:
    """One candidate, plus what this ingest could resolve about it.

    Attributes:
        candidate: The contact-free candidate exactly as the Stage 0 seam
            produced it. Nothing is added to it here; this type wraps it.
        identity_key: The ADR-0012 key, or `None` when the source stated no
            resolvable date. `None` is the honest answer, not a defect —
            see `is_keyed`.
        mapped_tags: Tag values that resolved into the supplied vocabulary.
        quarantined: Tag values that did not. Carried, never dropped.
    """

    candidate: ContactFreeEventCandidate
    identity_key: EventIdentityKey | None
    mapped_tags: tuple[MappedTag, ...]
    quarantined: tuple[QuarantinedTag, ...]

    @property
    def is_keyed(self) -> bool:
        """Whether this event resolved to an identity key.

        A named property rather than a truthiness check on `identity_key`, so
        "this event has no key" reads as a deliberate state at every call site
        instead of an incidental `None`.
        """
        return self.identity_key is not None


#: What ingesting one document produced: the events found (possibly none, for
#: a structurally valid but empty document), or the Stage 0 seam's typed
#: refusal. Same discriminated-union shape as `CandidateOutcome`, so a caller
#: narrows with `isinstance` rather than reading a sentinel.
IngestOutcome: TypeAlias = "tuple[IngestedEvent, ...] | CandidateRefusal"


@dataclass(frozen=True, slots=True)
class IngestReport:
    """The result of ingesting one source document.

    Attributes:
        source: The document's path relative to the ingest root, POSIX-style
            — a stable identifier for the fixture that does not leak the
            machine's directory layout into assertions or logs.
        source_format: The format it was parsed as.
        outcome: The events, or a `CandidateRefusal`.
    """

    source: str
    source_format: FixtureSourceFormat
    outcome: IngestOutcome

    @property
    def events(self) -> tuple[IngestedEvent, ...]:
        """The events found, or `()` for a refusal.

        `()` here cannot by itself distinguish "empty document" from
        "refused", which is why `refused` and `refusal` exist alongside it and
        why a caller summarizing a run must consult both.
        """
        if isinstance(self.outcome, CandidateRefusal):
            return ()
        return self.outcome

    @property
    def refusal(self) -> CandidateRefusal | None:
        """The parser's refusal, or `None` when the document parsed."""
        if isinstance(self.outcome, CandidateRefusal):
            return self.outcome
        return None

    @property
    def refused(self) -> bool:
        """Whether the document was refused rather than parsed."""
        return isinstance(self.outcome, CandidateRefusal)

    @property
    def unkeyed_events(self) -> tuple[IngestedEvent, ...]:
        """Events that resolved to no identity key (ADR-0010 `UnresolvedTime`)."""
        return tuple(event for event in self.events if not event.is_keyed)

    @property
    def quarantined(self) -> tuple[QuarantinedTag, ...]:
        """Every quarantined tag across this document's events, in order."""
        return tuple(tag for event in self.events for tag in event.quarantined)


def _resolve_event(
    candidate: ContactFreeEventCandidate,
    *,
    host_org_unit: str,
    vocabulary: TagVocabulary,
) -> IngestedEvent:
    """Attach identity and tag resolution to one candidate.

    `resolve_identity_key` returns `None` for `UnresolvedTime` and that value
    is stored as-is: there is no fallback date, no "today", and no synthesized
    key. Tag resolution partitions rather than filters — every raw value ends
    up in exactly one of `mapped_tags` or `quarantined`, so the two together
    always account for `candidate.raw_tags`.
    """
    key = resolve_identity_key(
        host_org_unit=host_org_unit,
        title=candidate.title,
        event_time=candidate.event_time,
    )
    resolutions = tuple(resolve_tag(value, vocabulary) for value in candidate.raw_tags)
    return IngestedEvent(
        candidate=candidate,
        identity_key=key,
        mapped_tags=matchable_tags(resolutions),
        quarantined=quarantined_tags(resolutions),
    )


def ingest_fixture_file(
    location: str | Path,
    *,
    root: str | Path,
    source_format: FixtureSourceFormat | None = None,
    source_time_zone: str,
    host_org_unit: str,
    vocabulary: TagVocabulary,
) -> IngestReport:
    """Read and ingest one committed source document.

    Args:
        location: Path to the document, absolute or relative to `root`. A URL
            is refused (see `read_fixture_document`).
        root: The fixture tree the document must live under.
        source_format: The format to parse as. Defaults to the format the
            file's suffix names; an explicit value overrides it.
        source_time_zone: IANA zone the source declares, passed through to the
            Stage 0 parser unchanged.
        host_org_unit: The org unit these events belong to — the ADR-0012 key
            component that is deliberately *not* derived from the source
            document, so two documents describing the same event key alike.
        vocabulary: The closed tag vocabulary to resolve raw tags against.

    Returns:
        An `IngestReport`. A structurally malformed document yields a report
        whose `outcome` is the Stage 0 `CandidateRefusal`, not an exception
        and not an empty result.

    Raises:
        FixtureRejected: if the location is refused before parsing.
        ValueError: if `host_org_unit` is blank — surfaced from the domain
            rather than absorbed.
    """
    root_path = Path(root).resolve()
    text = read_fixture_document(location, root=root_path)
    resolved = _contained(str(location), root_path=root_path)

    chosen = source_format or format_for_suffix(resolved.suffix)
    if chosen is None:  # pragma: no cover - read_fixture_document already refused
        raise _reject(RejectionReason.UNSUPPORTED_FORMAT)

    if chosen is FixtureSourceFormat.ICAL:
        outcome = candidates_from_ical_fixture(text, source_time_zone=source_time_zone)
    else:
        outcome = candidates_from_jsonld_fixture(text, source_time_zone=source_time_zone)

    ingested: IngestOutcome
    if isinstance(outcome, CandidateRefusal):
        ingested = outcome
    else:
        ingested = tuple(
            _resolve_event(candidate, host_org_unit=host_org_unit, vocabulary=vocabulary)
            for candidate in outcome
        )

    return IngestReport(
        source=resolved.relative_to(root_path).as_posix(),
        source_format=chosen,
        outcome=ingested,
    )


def ingest_fixture_directory(
    directory: str | Path,
    *,
    root: str | Path,
    source_time_zone: str,
    host_org_unit: str,
    vocabulary: TagVocabulary,
) -> tuple[IngestReport, ...]:
    """Ingest every recognized source document under `directory`.

    Walks recursively and in sorted order, so two runs over the same tree
    produce the same reports in the same sequence — a property the
    fixture-driven evidence this scaffold exists to support depends on.

    Files whose suffix names no `FixtureSourceFormat` are skipped rather than
    refused: a `README.md` beside the fixtures is not an ingest failure. A
    file that *is* a recognized format but fails to parse still produces a
    report carrying its refusal, so a broken document is never invisible.

    Args:
        directory: The subtree to walk, absolute or relative to `root`.
        root: The fixture tree everything must live under.
        source_time_zone: Passed through to each document's parser.
        host_org_unit: Passed through to identity resolution.
        vocabulary: Passed through to tag resolution.

    Returns:
        One report per recognized document, ordered by relative path.

    Raises:
        FixtureRejected: with `NOT_A_LOCAL_PATH` for a URL, `OUTSIDE_ROOT` if
            `directory` resolves outside `root`, or `NOT_A_FILE` if it is not
            a directory.
    """
    root_path = Path(root).resolve()
    target = _contained(str(directory), root_path=root_path)
    if not target.is_dir():
        raise _reject(RejectionReason.NOT_A_FILE)

    paths = sorted(
        (path for path in target.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(target).as_posix(),
    )
    return tuple(
        ingest_fixture_file(
            path,
            root=root_path,
            source_time_zone=source_time_zone,
            host_org_unit=host_org_unit,
            vocabulary=vocabulary,
        )
        for path in paths
        if format_for_suffix(path.suffix) is not None
    )
