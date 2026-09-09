"""What a QR check-in token does, and every way it refuses.

Covers :mod:`smartmatch_domain.checkin`. The module's whole value is that an
unverifiable token is refused rather than partly believed, so most of this file
is refusals: a forged MAC, an altered payload, a token from another secret, an
expired one, and a genuine one presented at the wrong scanner each get their
own named exception, and the assertions are on the *type* rather than on the
message so a caller can act on them.

``tests/unit/test_checkin_wiring.py`` covers what the module is not allowed to
do — reach an HTTP surface — which no test of its behavior can see.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.checkin import (
    CHECK_IN_TOKEN_VERSION,
    MAX_CHECK_IN_TOKEN_TTL,
    MIN_CHECK_IN_SECRET_BYTES,
    CheckInTokenExpiredError,
    CheckInTokenScopeError,
    CheckInTokenSignatureError,
    MalformedCheckInTokenError,
    issue_check_in_token,
    verify_check_in_token,
)

SECRET = b"s" * MIN_CHECK_IN_SECRET_BYTES
OTHER_SECRET = b"t" * MIN_CHECK_IN_SECRET_BYTES

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
UNIT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
EVENT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")

ISSUED_AT = datetime(2026, 9, 4, 17, 0, tzinfo=UTC)
TTL = timedelta(hours=4)
DURING = ISSUED_AT + timedelta(hours=1)


def _issue(**overrides: object) -> str:
    """Mint the canonical token, with named parts replaced."""
    kwargs: dict[str, object] = {
        "tenant_id": TENANT_ID,
        "unit_id": UNIT_ID,
        "event_id": EVENT_ID,
        "nonce": "nonce-0001",
        "issued_at": ISSUED_AT,
        "ttl": TTL,
        "secret": SECRET,
    }
    kwargs.update(overrides)
    return issue_check_in_token(**kwargs)  # type: ignore[arg-type]


def _claims(token: str) -> dict[str, object]:
    """Decode a token's payload without verifying it — for inspection only."""
    payload = token.split(".")[0]
    decoded: dict[str, object] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
    )
    return decoded


class TestRoundTrip:
    """A token this module minted is a token it reads back exactly."""

    def test_a_freshly_issued_token_verifies_and_carries_its_scope(self):
        verified = verify_check_in_token(_issue(), secret=SECRET, at=DURING)

        assert verified.tenant_id == TENANT_ID
        assert verified.unit_id == UNIT_ID
        assert verified.event_id == EVENT_ID
        assert verified.nonce == "nonce-0001"
        assert verified.issued_at == ISSUED_AT
        assert verified.expires_at == ISSUED_AT + TTL

    def test_issuing_is_deterministic(self):
        """Identical inputs produce identical bytes.

        The property the module's "no clock, no entropy" discipline buys: a
        golden expectation is possible, and a caller cannot come to depend on
        this package reading a clock it is forbidden to read.
        """
        assert _issue() == _issue()

    def test_a_different_nonce_produces_a_different_token(self):
        assert _issue(nonce="nonce-0002") != _issue()

    def test_the_token_is_url_and_qr_safe(self):
        """Unpadded base64url in two parts: nothing here needs escaping."""
        token = _issue()
        payload, signature = token.split(".")

        assert "=" not in token
        assert set(payload + signature) <= set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )

    def test_the_caller_may_assert_the_scope_it_expects(self):
        verified = verify_check_in_token(
            _issue(),
            secret=SECRET,
            at=DURING,
            expected_tenant_id=TENANT_ID,
            expected_unit_id=UNIT_ID,
            expected_event_id=EVENT_ID,
        )

        assert verified.event_id == EVENT_ID


class TestTheSignatureIsWhatIsTrusted:
    """Nothing inside the payload is believed before the MAC passes."""

    def test_a_token_minted_under_another_secret_is_refused(self):
        with pytest.raises(CheckInTokenSignatureError):
            verify_check_in_token(_issue(secret=OTHER_SECRET), secret=SECRET, at=DURING)

    def test_an_altered_payload_is_refused(self):
        """Editing one byte of the payload breaks the MAC over it."""
        payload, signature = _issue().split(".")
        tampered = ("A" if payload[0] != "A" else "B") + payload[1:]

        with pytest.raises(CheckInTokenSignatureError):
            verify_check_in_token(f"{tampered}.{signature}", secret=SECRET, at=DURING)

    def test_a_truncated_signature_is_refused(self):
        payload, signature = _issue().split(".")

        with pytest.raises(CheckInTokenSignatureError):
            verify_check_in_token(f"{payload}.{signature[:-4]}", secret=SECRET, at=DURING)

    def test_a_forged_payload_cannot_choose_its_own_scope(self):
        """The ordering claim, stated as a test rather than as a comment.

        A payload naming another tenant, presented without a matching MAC, is
        refused as a *signature* failure — not as a scope failure. If the scope
        comparison ran first, an attacker could pick which check they faced by
        writing whatever tenant into an unsigned payload.
        """
        forged = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "v": CHECK_IN_TOKEN_VERSION,
                        "tid": str(uuid.uuid4()),
                        "uid": str(UNIT_ID),
                        "eid": str(EVENT_ID),
                        "nonce": "forged",
                        "iat": int(ISSUED_AT.timestamp()),
                        "exp": int((ISSUED_AT + TTL).timestamp()),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            .rstrip(b"=")
            .decode("ascii")
        )

        with pytest.raises(CheckInTokenSignatureError):
            verify_check_in_token(
                f"{forged}.{_issue().split('.')[1]}",
                secret=SECRET,
                at=DURING,
                expected_tenant_id=TENANT_ID,
            )


class TestExpiry:
    """The window closes, and it closes at the instant it says it does."""

    def test_a_token_verifies_up_to_the_last_instant_before_expiry(self):
        just_inside = ISSUED_AT + TTL - timedelta(seconds=1)

        assert verify_check_in_token(_issue(), secret=SECRET, at=just_inside).nonce == "nonce-0001"

    def test_a_token_is_expired_at_its_own_expiry_instant(self):
        """The boundary is exclusive: `exp` is when it stops, not its last working second."""
        with pytest.raises(CheckInTokenExpiredError):
            verify_check_in_token(_issue(), secret=SECRET, at=ISSUED_AT + TTL)

    def test_a_token_presented_after_its_window_is_refused(self):
        with pytest.raises(CheckInTokenExpiredError):
            verify_check_in_token(_issue(), secret=SECRET, at=ISSUED_AT + timedelta(days=1))

    def test_a_ttl_beyond_the_maximum_is_refused_at_issue(self):
        """Refused where it is minted, so no long-lived token ever exists to verify."""
        with pytest.raises(MalformedCheckInTokenError):
            _issue(ttl=MAX_CHECK_IN_TOKEN_TTL + timedelta(seconds=1))

    def test_the_maximum_ttl_itself_is_allowed(self):
        assert _issue(ttl=MAX_CHECK_IN_TOKEN_TTL)

    @pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
    def test_a_non_positive_ttl_is_refused(self, ttl: timedelta):
        with pytest.raises(MalformedCheckInTokenError):
            _issue(ttl=ttl)


class TestScope:
    """A genuine token presented at the wrong scanner is refused, and says so."""

    @pytest.mark.parametrize(
        "expectation",
        ["expected_tenant_id", "expected_unit_id", "expected_event_id"],
    )
    def test_a_mismatched_expectation_is_a_scope_error_not_a_signature_error(
        self, expectation: str
    ):
        with pytest.raises(CheckInTokenScopeError):
            verify_check_in_token(_issue(), secret=SECRET, at=DURING, **{expectation: uuid.uuid4()})

    def test_naming_no_expectation_checks_no_scope(self):
        """Optional by design, so the function stays usable before a scope is known."""
        assert verify_check_in_token(_issue(), secret=SECRET, at=DURING).unit_id == UNIT_ID


class TestMalformedInput:
    """Everything that is not a check-in token is refused as one."""

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "no-separator",
            "too.many.parts",
            ".missing-payload",
            "missing-signature.",
            "!!!.!!!",
        ],
    )
    def test_a_string_that_is_not_a_token_is_refused(self, token: str):
        with pytest.raises(MalformedCheckInTokenError):
            verify_check_in_token(token, secret=SECRET, at=DURING)

    def test_a_blank_nonce_is_refused_at_issue(self):
        with pytest.raises(MalformedCheckInTokenError):
            _issue(nonce="   ")

    def test_a_naive_issued_at_is_refused(self):
        with pytest.raises(MalformedCheckInTokenError):
            _issue(issued_at=datetime(2026, 9, 4, 17, 0))

    def test_a_naive_verification_instant_is_refused(self):
        with pytest.raises(MalformedCheckInTokenError):
            verify_check_in_token(
                _issue(),
                secret=SECRET,
                at=datetime(2026, 9, 4, 18, 0),
            )

    @pytest.mark.parametrize("secret", [b"", b"short", b"s" * (MIN_CHECK_IN_SECRET_BYTES - 1)])
    def test_a_short_secret_is_refused_at_both_ends(self, secret: bytes):
        """Fails closed on a weakened deployment rather than accepting forgeries."""
        with pytest.raises(MalformedCheckInTokenError):
            _issue(secret=secret)
        with pytest.raises(MalformedCheckInTokenError):
            verify_check_in_token(_issue(), secret=secret, at=DURING)


class TestWhatTheTokenNeverCarries:
    """The identity claim in the module docstring, held as a test."""

    def test_the_payload_names_no_person(self):
        claims = _claims(_issue())

        assert set(claims) == {"v", "tid", "uid", "eid", "nonce", "iat", "exp"}
        assert not {key for key in claims if "subject" in key or "user" in key}
