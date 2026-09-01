"""Static shape validation for a candidate P9 `Public URL` — no resolution, no fetch.

Ratification design §6.1 (`docs/superpowers/specs/2026-08-31-ratification-and-
feature-delivery-design.md`). P9 is recorded but Gate B — the privacy gate that
would authorize collecting or persisting contact data — has not closed. This
module is the narrow, gate-independent slice that *is* authorized: a pure,
static check of a candidate URL's textual shape. Exactly four mechanically
testable rules, and no more:

1. the value is an absolute URL with the scheme exactly `https` and a
   hostname;
2. URL userinfo (username or password) is absent;
3. query strings and fragments are rejected — not stored, not stripped;
4. IPv4 and IPv6 literal hosts are rejected; a DNS hostname is required.

**What passing does NOT mean.** `StaticallyValidHttpsUrl` is named the way it
is — not `PublicUrl`, not `ValidatedPublicUrl` — on purpose. Passing these
checks proves only that the *text* has the right shape. It proves nothing
about whether the hostname resolves, whether any redirect stays on a public
destination, or whether the resource served at that URL is actually a public
event page. Those are DNS resolution, destination classification, redirect
checking, and public-page/allowlist qualification — all reserved for the
future *approved fetch seam*, which does not exist yet. This module performs
no resolution and no fetch of any kind, and cannot be made to: the domain
package's import contract (`pyproject.toml`) forbids `os`, `pathlib`, and
`socket` here, so there is no network capability to reach for even by mistake.

**Persistence stays blocked.** A token can appear in an otherwise ordinary
path (`https://example.edu/rsvp/tok_9f3a…`), and no static check can tell that
apart from a legitimate path segment. So raw URL persistence is not offered by
this module under any name. The only path toward a persistence-safe URL is
`project_for_persistence`, which builds one *exclusively* from an explicitly
approved `ApprovedHostPathProjection` entry — an allowlisted exact host and
exact literal path prefix, decided by reviewed code change, never inferred at
runtime from a candidate URL's own content. `APPROVED_HOST_PATH_PROJECTIONS`
is empty today, because no projection has been approved, so every call to
`project_for_persistence` refuses today. That is deliberate fail-closed
behavior, not a placeholder bug: populate the tuple only when a specific
host/path allowlist is actually approved.

**Contact data.** Quarantine is collection. This module never reads, derives,
stores, or forwards a contact name, email address, or phone number — there is
no field, parameter, or code path here that could carry one. It also does not
inspect a URL's path for what a human name, email, or phone number might look
like; deciding "this path segment looks like a token, redact it" is exactly
the unsafe path-inspection this module refuses to do.

`board_role` (design §6.2) is out of scope for this module — no code here
references it.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias
from urllib.parse import urlsplit

__all__ = [
    "APPROVED_HOST_PATH_PROJECTIONS",
    "ApprovedHostPathProjection",
    "PersistenceProjectionResult",
    "PersistenceRefusal",
    "PersistenceRefusalReason",
    "PersistenceSafeUrl",
    "StaticUrlShapeRefusal",
    "StaticUrlShapeRefusalReason",
    "StaticUrlShapeResult",
    "StaticallyValidHttpsUrl",
    "project_for_persistence",
    "validate_static_url_shape",
]


class StaticUrlShapeRefusalReason(StrEnum):
    """Stable, mechanically testable reasons `validate_static_url_shape` refuses.

    Each member names exactly one of the four rules in the module docstring
    (or the syntactic precondition for evaluating them), so a caller — or a
    test — can assert on the specific rule that failed rather than on prose.
    """

    #: The candidate could not be parsed as a URL at all (e.g. malformed IPv6
    #: brackets, an invalid percent-escape in the authority).
    INVALID_URL_SYNTAX = "invalid_url_syntax"
    #: Not an absolute `https` URL: missing scheme, a scheme-relative or
    #: relative reference, or any scheme other than `https` (including `http`).
    SCHEME_NOT_HTTPS = "scheme_not_https"
    #: The scheme is `https` but no hostname is present (e.g. `https:///path`).
    MISSING_HOSTNAME = "missing_hostname"
    #: A username or password is present in the URL authority.
    USERINFO_PRESENT = "userinfo_present"
    #: A query string (`?...`) is present.
    QUERY_PRESENT = "query_present"
    #: A fragment (`#...`) is present.
    FRAGMENT_PRESENT = "fragment_present"
    #: The host is an IPv4 or IPv6 literal rather than a DNS hostname.
    IP_LITERAL_HOST = "ip_literal_host"
    #: The host is neither an IP literal nor a syntactically valid DNS
    #: hostname (RFC 1123 labels: letters, digits, and interior hyphens).
    #: §6.1 requires a DNS hostname, so anything that is not one is refused
    #: rather than assumed to be one.
    HOST_NOT_DNS_HOSTNAME = "host_not_dns_hostname"


@dataclass(frozen=True, slots=True)
class StaticallyValidHttpsUrl:
    """A candidate URL that passed all four static shape checks.

    This is a *shape* claim only — see the module docstring's "What passing
    does NOT mean" section. It is not evidence that the host resolves, that a
    redirect from it stays public, or that it serves a public event page, and
    it must never be treated as such by any caller.

    Attributes:
        normalized: The candidate text with the scheme and host lowercased —
            RFC 3986 §6.2.2.1 case normalization, the only transformation
            applied. The path is left exactly as supplied, because path case
            is significant. Query, fragment, and userinfo are absent by
            construction (validation refuses otherwise), so there is nothing
            to strip. The field is named `normalized` and must therefore
            actually be normalized: returning the raw text here would let a
            caller persist or compare two spellings of one URL as though they
            were different.
        scheme: Always `"https"`.
        host: The lowercase DNS hostname (never an IP literal — validation
            refuses those).
        path: The URL path, or `"/"` if the candidate had none.
    """

    normalized: str
    scheme: str
    host: str
    path: str


@dataclass(frozen=True, slots=True)
class StaticUrlShapeRefusal:
    """A candidate URL that failed at least one static shape check.

    `detail` is human-readable context for logs/audits; `reason` is the stable,
    machine-comparable value a caller should branch or assert on.
    """

    candidate: str
    reason: StaticUrlShapeRefusalReason
    detail: str


#: `validate_static_url_shape` returns exactly one of these — never `None`,
#: never a bare exception, for any input this module knows how to classify.
StaticUrlShapeResult: TypeAlias = StaticallyValidHttpsUrl | StaticUrlShapeRefusal


def validate_static_url_shape(candidate: str) -> StaticUrlShapeResult:
    """Statically validate a candidate `Public URL` against the four P9 rules.

    Pure string parsing only — no DNS resolution, no socket, no fetch. The
    checks run in the order the four rules are listed in the module docstring;
    the first rule the candidate fails is the reason returned.

    Args:
        candidate: The raw candidate URL text, exactly as supplied.

    Returns:
        A `StaticallyValidHttpsUrl` if all four rules pass, otherwise a
        `StaticUrlShapeRefusal` naming the first failing rule.
    """
    text = candidate.strip()
    if not text:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS,
            detail="candidate is blank; not an absolute https URL",
        )

    try:
        parts = urlsplit(text)
        hostname = parts.hostname
        username = parts.username
        password = parts.password
    except ValueError as exc:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.INVALID_URL_SYNTAX,
            detail=f"could not be parsed as a URL: {exc}",
        )

    if parts.scheme.lower() != "https":
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS,
            detail=f"scheme is {parts.scheme!r}, not 'https'",
        )

    if not hostname:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.MISSING_HOSTNAME,
            detail="no hostname present in the URL authority",
        )

    if username is not None or password is not None:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.USERINFO_PRESENT,
            detail="URL authority contains userinfo (username or password)",
        )

    # The delimiter's presence is what is refused, not merely a non-empty
    # value after it. §6.1: query strings and fragments are "rejected rather
    # than stored or stripped" — accepting "https://host/path?" and returning
    # a path of "/path" would be stripping the delimiter, silently, which is
    # the one handling the rule names and forbids. `parts.query` is the empty
    # string in that case, so the raw text is what has to be checked: a
    # literal "?" in the candidate always opens the query component, and a
    # literal "#" always opens the fragment.
    if "?" in text:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.QUERY_PRESENT,
            detail="URL contains a query string"
            if parts.query
            else "URL contains an empty query delimiter '?'",
        )

    if "#" in text:
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.FRAGMENT_PRESENT,
            detail="URL contains a fragment"
            if parts.fragment
            else "URL contains an empty fragment delimiter '#'",
        )

    if _is_ip_literal(hostname):
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.IP_LITERAL_HOST,
            detail=f"host {hostname!r} is an IP literal, not a DNS hostname",
        )

    # §6.1 requires a DNS hostname, and "not an IP literal" is not the same
    # claim: it leaves every other string — "bad_host", "a..b", "-x-" —
    # classified as a hostname by default. Rejecting what is not a valid DNS
    # hostname is the fail-closed reading, and the only one under which the
    # `host` field means what its name says.
    if not _is_dns_hostname(hostname):
        return StaticUrlShapeRefusal(
            candidate=candidate,
            reason=StaticUrlShapeRefusalReason.HOST_NOT_DNS_HOSTNAME,
            detail=f"host {hostname!r} is not a syntactically valid DNS hostname",
        )

    return StaticallyValidHttpsUrl(
        normalized=_normalize(text, hostname=hostname),
        scheme="https",
        host=hostname,
        path=parts.path or "/",
    )


def _normalize(text: str, *, hostname: str) -> str:
    """Return `text` with the scheme and host lowercased, nothing else changed.

    RFC 3986 §6.2.2.1: scheme and host are case-insensitive and their
    normalized form is lowercase. The path is deliberately untouched — path
    case is significant, and this function is not in the business of altering
    what the source actually pointed at. `urlunsplit` is not used: it would
    re-encode and re-assemble components, which is a larger transformation
    than the case normalization claimed here.
    """
    scheme_end = text.index(":")
    remainder = text[scheme_end:]
    # `hostname` is already lowercase (urlsplit lowercases it), so finding the
    # host in the remainder requires a case-insensitive search of exactly the
    # authority span.
    authority_start = scheme_end + len("://")
    authority_end = len(text)
    for delimiter in ("/", "?", "#"):
        position = text.find(delimiter, authority_start)
        if position != -1:
            authority_end = min(authority_end, position)
    authority = text[authority_start:authority_end]
    remainder = authority.lower() + text[authority_end:]
    return "https://" + remainder


#: Matches one RFC 1123 hostname label: a letter or digit at each end, with
#: letters, digits, and hyphens between, and at most 63 characters overall.
_DNS_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _is_dns_hostname(hostname: str) -> bool:
    """Return whether `hostname` is a syntactically valid DNS hostname.

    RFC 1123 §2.1 labels, joined by dots, at most 253 characters in total. An
    empty label is refused, which also refuses a trailing dot, a leading dot,
    and a doubled dot. Underscores are refused: they are legal in DNS records
    generally but not in a hostname, and a permissive reading here is what
    lets a value that is not a hostname pass a check named for hostnames.

    This is syntax only. That a syntactically valid hostname resolves, or
    resolves to a public destination, is the future fetch seam's question —
    see the module docstring.
    """
    if not hostname or len(hostname) > 253:
        return False
    return all(_DNS_LABEL.match(label) for label in hostname.split("."))


def _is_ip_literal(hostname: str) -> bool:
    """Return whether `hostname` is an IPv4 or IPv6 literal.

    `urlsplit(...).hostname` already strips the `[...]` brackets an IPv6
    literal carries in a URL authority, so the bracket-free form is what
    `ipaddress.ip_address` expects. A string that is not any kind of IP
    literal raises `ValueError`, which is the (far more common) DNS-hostname
    case — not an error condition here.
    """
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


class PersistenceRefusalReason(StrEnum):
    """Stable reason `project_for_persistence` refuses to build a persisted URL."""

    #: No entry in `APPROVED_HOST_PATH_PROJECTIONS` covers this host/path.
    #: This is the only reachable reason today, because that tuple is empty.
    NO_APPROVED_PROJECTION = "no_approved_projection"


@dataclass(frozen=True, slots=True)
class ApprovedHostPathProjection:
    """One reviewed, allowlisted host + path-prefix entry.

    An entry authorizes `project_for_persistence` to construct a
    persistence-safe URL for any `StaticallyValidHttpsUrl` whose host equals
    `host` (case-insensitive DNS host, already lowercase from validation) and
    whose path starts with `path_prefix`. Entries must be added only as a
    deliberate, reviewed code change naming the exact host and exact literal
    path prefix — never computed, inferred, or copied from a candidate URL's
    own content, which is exactly the "guess whether this segment is a token"
    behavior this seam exists to avoid.
    """

    host: str
    path_prefix: str


#: No host/path projection has been approved. Empty on purpose, not a stub to
#: fill in later without review: every call to `project_for_persistence`
#: refuses with `NO_APPROVED_PROJECTION` while this stays empty, so raw URL
#: persistence remains blocked exactly as design §6.1 requires. Populate only
#: through a deliberate, reviewed change that names an approved allowlist.
APPROVED_HOST_PATH_PROJECTIONS: Final[tuple[ApprovedHostPathProjection, ...]] = ()


@dataclass(frozen=True, slots=True)
class PersistenceSafeUrl:
    """A canonical URL built only from an approved host/path allowlist entry.

    Carries no query, fragment, or userinfo by construction — there is no
    field for any of them, and nothing here reads them from the candidate.
    """

    host: str
    path: str


@dataclass(frozen=True, slots=True)
class PersistenceRefusal:
    """A `StaticallyValidHttpsUrl` that no approved projection covers."""

    candidate: str
    reason: PersistenceRefusalReason
    detail: str


#: `project_for_persistence` returns exactly one of these — never `None` and
#: never a raw, unprojected URL.
PersistenceProjectionResult: TypeAlias = PersistenceSafeUrl | PersistenceRefusal


def project_for_persistence(validated: StaticallyValidHttpsUrl) -> PersistenceProjectionResult:
    """Attempt to build a persistence-safe URL via an approved host/path projection.

    This is the *only* route to a persisted representation of a `Public URL`
    anywhere in this module. `validate_static_url_shape` alone never authorizes
    persistence — it only tests text shape. `APPROVED_HOST_PATH_PROJECTIONS` is
    empty (see its docstring), so today this function refuses for every input.

    Args:
        validated: A URL that already passed `validate_static_url_shape`.

    Returns:
        A `PersistenceSafeUrl` built strictly from the matching allowlist
        entry's `host` and `path_prefix` if one covers `validated`, otherwise
        a `PersistenceRefusal`.
    """
    for projection in APPROVED_HOST_PATH_PROJECTIONS:
        if validated.host == projection.host.lower() and validated.path.startswith(
            projection.path_prefix
        ):
            return PersistenceSafeUrl(host=projection.host, path=projection.path_prefix)

    return PersistenceRefusal(
        candidate=validated.normalized,
        reason=PersistenceRefusalReason.NO_APPROVED_PROJECTION,
        detail=(
            "no approved host/path projection covers this URL; raw URL "
            "persistence remains blocked pending an approved allowlist (design §6.1)"
        ),
    )
