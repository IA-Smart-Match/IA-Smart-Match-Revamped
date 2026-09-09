"""QR check-in tokens — issue and verify, and nothing else (MM-F02, B08).

``docs/plans/frontend-broken-buttons.md`` **B08** records what the legacy
offered as "QR / check-in": an anchor to ``GET /api/qr/stats`` that opened a
JSON document in a new tab. There was no token, nothing was verified, and
nothing was recorded. The replacement B08 asks for is "phone-first check-in
with a reusable token (v1.1 §1.9)", and this module is the *token* half of it,
stated as a pure function pair so the rule that makes a scan trustworthy lives
somewhere a test can hold it.

What a check-in token is here
-----------------------------
A short, opaque string a coordinator can render as a QR code for one event in
one unit of one tenant, and which a later request can present as evidence that
**this** organizer issued **this** scan target and that it has not expired.
:func:`issue_check_in_token` produces one; :func:`verify_check_in_token` either
returns the :class:`CheckInToken` it carried or raises. There is no third
outcome, and no "probably valid".

What this module deliberately is not
------------------------------------
* **Not attendance.** Verifying a token records nothing. Writing an
  ``attendance_record`` row is
  :class:`~smartmatch_persistence.attendance.AttendanceRepository`'s job, and a
  verified token is a *precondition* a caller may choose to require before
  asking for that write — never the write itself. Points derive from recorded
  attendance and nothing else (ADR-0013); a token is not a recorded fact.
* **Not identity.** The payload names a tenant, a unit and an event. It names
  no student, carries no subject id, and has no field one could be put in. Who
  scanned is the verified bearer token on the eventual request, exactly as
  ``routers/rewards.py`` takes ``subject_id`` from ``principal.user_id`` and
  never from a body (MM-A01, stakeholder Fix #7). A QR code is handed to a
  room, so anything inside it is public to that room, and a student identifier
  in a public artifact is precisely the disclosure D8 has not decided.
* **Not a QR renderer.** No image, no barcode library, no data URL. This module
  returns text; drawing it is a presentation concern and none of the security
  lives there.
* **Not an HTTP surface.** Nothing in ``services/`` imports this module, and
  ``tests/unit/test_checkin_wiring.py`` holds it that way. B08 lists the
  check-in *flow* as blocked on S11 and D8; the token rule is not, and landing
  the rule without the surface is what lets the surface be reviewed on its own
  terms later. This is the same posture
  :mod:`smartmatch_domain.calendar_invite` takes for B07.
* **Not a clock and not a source of randomness.** Every instant is passed in
  and the nonce is passed in, the same discipline
  :func:`~smartmatch_domain.calendar_invite.build_invite_ics` applies to
  ``generated_at``: identical inputs produce identical bytes, so a golden test
  is possible and a caller cannot accidentally depend on this package reading a
  clock it has no business reading (the import-linter contract "Domain is pure"
  forbids it the modules it would need anyway).

Why HMAC and not a signature
----------------------------
The issuer and the verifier are the same service reading the same secret from
its own configuration, so there is no third party who must verify without being
able to issue. A shared-secret MAC is the smaller mechanism for that, and the
smaller mechanism is the one whose failure modes fit in this docstring. The MAC
covers the encoded payload with a fixed domain-separation prefix
(:data:`_MAC_DOMAIN`), so a token minted for some other purpose under the same
secret cannot be replayed as a check-in token.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

__all__ = [
    "CHECK_IN_TOKEN_VERSION",
    "MAX_CHECK_IN_TOKEN_TTL",
    "MIN_CHECK_IN_SECRET_BYTES",
    "CheckInToken",
    "CheckInTokenError",
    "CheckInTokenExpiredError",
    "CheckInTokenScopeError",
    "CheckInTokenSignatureError",
    "MalformedCheckInTokenError",
    "issue_check_in_token",
    "verify_check_in_token",
]

#: The payload version, carried in the token and checked on the way back. A
#: token whose shape changes gets a new number rather than a new optional
#: field, so an old token is rejected outright instead of being read under
#: rules it was not minted under.
CHECK_IN_TOKEN_VERSION: Final[int] = 1

#: Prefix mixed into the MAC input. Domain separation: a MAC over the same
#: secret produced for any other purpose cannot be presented here, because the
#: bytes that were signed there did not begin with this.
_MAC_DOMAIN: Final[bytes] = b"smartmatch.checkin.v1|"

#: The shortest secret this module will use. A 32-byte secret is the output
#: width of the hash underneath the MAC; anything shorter is a weaker input to
#: a construction whose whole value is that guessing it is infeasible. Refused
#: at issue *and* at verify, so a deployment that shortens the secret fails on
#: the next scan rather than quietly accepting forgeries.
MIN_CHECK_IN_SECRET_BYTES: Final[int] = 32

#: The longest life a check-in token may be issued with. A QR code is pinned to
#: a wall for the duration of one event, not for a term: v1.1 §1.9's "reusable
#: token" is reusable by every attendee *at that event*, which is a matter of
#: hours, and a token that outlives its event is a credential to a room nobody
#: is standing in. Twelve hours covers a full-day event and refuses a week.
MAX_CHECK_IN_TOKEN_TTL: Final[timedelta] = timedelta(hours=12)


class CheckInTokenError(ValueError):
    """Base class for every refusal in this module.

    A ``ValueError`` and not a ``PermissionError``: an unverifiable token is a
    malformed input to a check-in attempt, and the authorization decision about
    *who* is checking in is made elsewhere, against a bearer token. Callers that
    want one ``except`` clause for "this scan is not usable" catch this.
    """


class MalformedCheckInTokenError(CheckInTokenError):
    """The token is not a check-in token at all — shape, encoding, or fields."""


class CheckInTokenSignatureError(CheckInTokenError):
    """The MAC does not match. The token was forged, altered, or minted elsewhere."""


class CheckInTokenExpiredError(CheckInTokenError):
    """The token verified but its window has closed."""


class CheckInTokenScopeError(CheckInTokenError):
    """The token verified but names a different tenant, unit, or event.

    Distinct from :class:`CheckInTokenSignatureError` on purpose: a genuine
    token presented at the wrong scanner is an operator error worth reporting as
    such, and a forgery is not. Both refuse; only one is a bug report.
    """


@dataclass(frozen=True, slots=True)
class CheckInToken:
    """What a verified check-in token claims. Immutable, and never a person.

    Attributes:
        tenant_id: The tenant the event belongs to.
        unit_id: The org unit that owns the event — the ``owning_unit_id`` an
            ``attendance_record`` written after this scan carries (A5).
        event_id: The event being checked into.
        nonce: The caller-supplied uniqueness value. Two tokens issued for the
            same event in the same second differ here, so a token is a
            distinguishable artifact that can be revoked or superseded by
            whatever issues them, without this module holding any state.
        issued_at: When the token was minted, timezone-aware and in UTC.
        expires_at: When it stops verifying, timezone-aware and in UTC.
    """

    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    event_id: uuid.UUID
    nonce: str
    issued_at: datetime
    expires_at: datetime


def issue_check_in_token(
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    event_id: uuid.UUID,
    nonce: str,
    issued_at: datetime,
    ttl: timedelta,
    secret: bytes,
) -> str:
    """Mint one check-in token for one event.

    Args:
        tenant_id: The tenant the event belongs to.
        unit_id: The org unit that owns the event.
        event_id: The event this token admits a scan for.
        nonce: A non-blank, caller-supplied uniqueness value. Supplied rather
            than generated because this package reads no clock and no entropy
            source; see the module docstring.
        issued_at: Timezone-aware minting instant.
        ttl: How long the token verifies for. Must be positive and no longer
            than :data:`MAX_CHECK_IN_TOKEN_TTL`.
        secret: The shared MAC secret, at least
            :data:`MIN_CHECK_IN_SECRET_BYTES` bytes.

    Returns:
        ``<base64url payload>.<base64url mac>``, ASCII, unpadded — safe in a QR
        code, in a URL path, and in a query string without further escaping.

    Raises:
        MalformedCheckInTokenError: the secret is too short, ``nonce`` is blank,
            ``issued_at`` is naive, or ``ttl`` is non-positive or beyond
            :data:`MAX_CHECK_IN_TOKEN_TTL`.
    """
    _require_usable_secret(secret)
    if not nonce.strip():
        raise MalformedCheckInTokenError(
            "nonce must be a non-blank string; it is what distinguishes two tokens "
            "issued for the same event, and this package generates none of its own"
        )
    minted_at = _require_aware(issued_at, "issued_at")
    if ttl <= timedelta(0):
        raise MalformedCheckInTokenError(f"ttl must be positive, not {ttl!r}")
    if ttl > MAX_CHECK_IN_TOKEN_TTL:
        raise MalformedCheckInTokenError(
            f"ttl {ttl!r} exceeds the maximum check-in token life "
            f"{MAX_CHECK_IN_TOKEN_TTL!r}; a token that outlives its event is a "
            "credential to a room nobody is standing in"
        )

    payload = {
        "v": CHECK_IN_TOKEN_VERSION,
        "tid": str(tenant_id),
        "uid": str(unit_id),
        "eid": str(event_id),
        "nonce": nonce,
        "iat": int(minted_at.timestamp()),
        "exp": int((minted_at + ttl).timestamp()),
    }
    encoded = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_b64encode(_mac(encoded, secret=secret))}"


def verify_check_in_token(
    token: str,
    *,
    secret: bytes,
    at: datetime,
    expected_tenant_id: uuid.UUID | None = None,
    expected_unit_id: uuid.UUID | None = None,
    expected_event_id: uuid.UUID | None = None,
) -> CheckInToken:
    """Return what ``token`` claims, or raise. There is no third outcome.

    The order of the checks is the contract, not an implementation detail:

    1. **Shape and encoding**, so nothing downstream parses arbitrary bytes.
    2. **The MAC**, in constant time, over the payload exactly as received.
       Nothing inside the payload is read as a claim before this passes — an
       unverified payload is attacker-controlled text, and reading a scope out
       of it first would let a forged token choose which comparison it faced.
    3. **Expiry**, against the caller's ``at``.
    4. **Scope**, against whichever of the three expectations the caller named.

    Args:
        token: The string a scan produced.
        secret: The shared MAC secret, at least
            :data:`MIN_CHECK_IN_SECRET_BYTES` bytes.
        at: Timezone-aware instant to judge expiry against, injected for the
            reason the module docstring gives.
        expected_tenant_id: Refuse a token minted for another tenant. Optional
            only so this function stays usable before a caller knows its scope;
            an HTTP caller always knows all three and should pass all three.
        expected_unit_id: Refuse a token minted for another unit.
        expected_event_id: Refuse a token minted for another event.

    Returns:
        The verified :class:`CheckInToken`.

    Raises:
        MalformedCheckInTokenError: the string is not a check-in token.
        CheckInTokenSignatureError: the MAC does not match.
        CheckInTokenExpiredError: the window has closed.
        CheckInTokenScopeError: a named expectation does not match.
    """
    _require_usable_secret(secret)
    now = _require_aware(at, "at")

    encoded_payload, encoded_mac = _split(token)
    presented = _b64decode(encoded_mac, "signature")
    if not hmac.compare_digest(presented, _mac(encoded_payload, secret=secret)):
        raise CheckInTokenSignatureError(
            "check-in token signature does not verify; it was forged, altered in "
            "transit, or minted under a different secret"
        )

    claims = _decode_payload(encoded_payload)
    expires_at = _read_instant(claims, "exp")
    if now >= expires_at:
        raise CheckInTokenExpiredError(
            f"check-in token expired at {expires_at.isoformat()}; it was presented at "
            f"{now.isoformat()}"
        )

    verified = CheckInToken(
        tenant_id=_read_uuid(claims, "tid"),
        unit_id=_read_uuid(claims, "uid"),
        event_id=_read_uuid(claims, "eid"),
        nonce=_read_nonce(claims),
        issued_at=_read_instant(claims, "iat"),
        expires_at=expires_at,
    )
    _assert_scope(verified, expected_tenant_id, expected_unit_id, expected_event_id)
    return verified


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _mac(encoded_payload: str, *, secret: bytes) -> bytes:
    """MAC the encoded payload under the module's domain-separation prefix."""
    return hmac.new(secret, _MAC_DOMAIN + encoded_payload.encode("ascii"), hashlib.sha256).digest()


def _require_usable_secret(secret: bytes) -> None:
    """Refuse a secret too short to be worth MACing with, at both ends."""
    if len(secret) < MIN_CHECK_IN_SECRET_BYTES:
        raise MalformedCheckInTokenError(
            f"the check-in MAC secret must be at least {MIN_CHECK_IN_SECRET_BYTES} bytes; "
            f"got {len(secret)}"
        )


def _require_aware(value: datetime, field: str) -> datetime:
    """Return ``value`` in UTC, refusing a naive instant.

    A naive datetime is not a moment — it is a moment plus an assumption — and
    an expiry window computed from an assumption is the F-003 shape ADR-0010
    exists to keep out of this codebase.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise MalformedCheckInTokenError(
            f"{field} must be timezone-aware; a naive instant is a moment plus an "
            "assumption, and this module never supplies the assumption"
        )
    return value.astimezone(UTC)


def _split(token: str) -> tuple[str, str]:
    """Split ``payload.mac``, refusing anything else."""
    parts = token.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise MalformedCheckInTokenError(
            "a check-in token is exactly '<payload>.<signature>'; this is not that shape"
        )
    return parts[0], parts[1]


def _b64encode(raw: bytes) -> str:
    """Unpadded base64url — QR-, URL-, and query-string-safe without escaping."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(encoded: str, what: str) -> bytes:
    """Decode unpadded base64url, refusing anything that is not.

    ``validate=True`` matters here and is not a stylistic choice: the default
    *discards* characters outside the alphabet, so ``"!!!"`` would decode to
    something rather than fail, and a plainly malformed token would then be
    reported as a signature failure — an attack — instead of as the malformed
    input it is. ``base64.b64decode`` with ``altchars`` is the only spelling
    that takes the flag; ``urlsafe_b64decode`` does not.
    """
    try:
        return base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MalformedCheckInTokenError(
            f"the check-in token's {what} is not valid base64url"
        ) from exc


def _decode_payload(encoded_payload: str) -> dict[str, Any]:
    """Decode the *already MAC-verified* payload into claims.

    Called only after :func:`verify_check_in_token` has compared the MAC, which
    is why this may raise ``Malformed`` rather than ``Signature``: bytes that
    survived the MAC came from the issuer, so a shape problem here is this
    module's own bug or a version skew — not an attack.
    """
    try:
        claims = json.loads(_b64decode(encoded_payload, "payload").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedCheckInTokenError("the check-in token's payload is not UTF-8 JSON") from exc
    if not isinstance(claims, dict):
        raise MalformedCheckInTokenError("the check-in token's payload is not a JSON object")
    if claims.get("v") != CHECK_IN_TOKEN_VERSION:
        raise MalformedCheckInTokenError(
            f"check-in token version {claims.get('v')!r} is not "
            f"{CHECK_IN_TOKEN_VERSION}; a token of another version is refused rather "
            "than read under rules it was not minted under"
        )
    return claims


def _read_uuid(claims: dict[str, Any], field: str) -> uuid.UUID:
    """Read one UUID claim, refusing a missing or unparseable one."""
    raw = claims.get(field)
    if not isinstance(raw, str):
        raise MalformedCheckInTokenError(
            f"check-in token claim {field!r} is missing or not a string"
        )
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise MalformedCheckInTokenError(f"check-in token claim {field!r} is not a UUID") from exc


def _read_instant(claims: dict[str, Any], field: str) -> datetime:
    """Read one epoch-second claim as an aware UTC instant."""
    raw = claims.get(field)
    # `bool` is an `int` in Python, and `True` is not a timestamp.
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise MalformedCheckInTokenError(
            f"check-in token claim {field!r} is missing or not an integer instant"
        )
    try:
        return datetime.fromtimestamp(raw, tz=UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise MalformedCheckInTokenError(
            f"check-in token claim {field!r} is not a representable instant"
        ) from exc


def _read_nonce(claims: dict[str, Any]) -> str:
    """Read the nonce, refusing a blank one for the reason issue does."""
    raw = claims.get("nonce")
    if not isinstance(raw, str) or not raw.strip():
        raise MalformedCheckInTokenError("check-in token claim 'nonce' is missing or blank")
    return raw


def _assert_scope(
    verified: CheckInToken,
    expected_tenant_id: uuid.UUID | None,
    expected_unit_id: uuid.UUID | None,
    expected_event_id: uuid.UUID | None,
) -> None:
    """Refuse a genuine token presented against a scope it was not minted for."""
    for field, expected, actual in (
        ("tenant", expected_tenant_id, verified.tenant_id),
        ("unit", expected_unit_id, verified.unit_id),
        ("event", expected_event_id, verified.event_id),
    ):
        if expected is not None and expected != actual:
            raise CheckInTokenScopeError(
                f"this check-in token was minted for {field} {actual}, not the "
                f"{expected} it was presented against"
            )
