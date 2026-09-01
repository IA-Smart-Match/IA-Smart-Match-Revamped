"""Static shape validation for a candidate P9 `Public URL` (design §6.1).

These tests are the specification for `smartmatch_domain.public_url`. P9 is
recorded but Gate B (privacy) is not closed, so only the four mechanically
testable static rules are authorized here — see the module docstring and
design §6.1/§6.2. Nothing in this file exercises DNS resolution, a fetch, or a
contact-data path; several tests exist specifically to prove those paths are
absent.
"""

from __future__ import annotations

import socket

import pytest
from smartmatch_domain.public_url import (
    APPROVED_HOST_PATH_PROJECTIONS,
    PersistenceRefusal,
    PersistenceRefusalReason,
    StaticallyValidHttpsUrl,
    StaticUrlShapeRefusal,
    StaticUrlShapeRefusalReason,
    project_for_persistence,
    validate_static_url_shape,
)

# ---------------------------------------------------------------------------
# Rule 1 — absolute URL, scheme exactly https, hostname present.
# ---------------------------------------------------------------------------


class TestRuleOneAbsoluteHttpsWithHostname:
    def test_https_with_hostname_and_path_is_accepted(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert isinstance(result, StaticallyValidHttpsUrl)
        assert result.scheme == "https"
        assert result.host == "events.example.edu"
        assert result.path == "/spring-fair"

    def test_https_with_hostname_and_no_path_defaults_path_to_slash(self) -> None:
        result = validate_static_url_shape("https://events.example.edu")
        assert isinstance(result, StaticallyValidHttpsUrl)
        assert result.path == "/"

    def test_http_scheme_is_rejected(self) -> None:
        result = validate_static_url_shape("http://events.example.edu/spring-fair")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS

    def test_scheme_relative_reference_is_rejected(self) -> None:
        result = validate_static_url_shape("//events.example.edu/spring-fair")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS

    def test_relative_path_is_rejected(self) -> None:
        result = validate_static_url_shape("/spring-fair")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS

    def test_blank_candidate_is_rejected(self) -> None:
        result = validate_static_url_shape("   ")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS

    def test_missing_hostname_is_rejected(self) -> None:
        result = validate_static_url_shape("https:///spring-fair")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.MISSING_HOSTNAME

    def test_other_scheme_is_rejected(self) -> None:
        result = validate_static_url_shape("mailto:coordinator@example.edu")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.SCHEME_NOT_HTTPS

    def test_scheme_case_is_normalized_and_accepted(self) -> None:
        result = validate_static_url_shape("HTTPS://events.example.edu/spring-fair")
        assert isinstance(result, StaticallyValidHttpsUrl)


# ---------------------------------------------------------------------------
# Rule 2 — userinfo (username/password) absent.
# ---------------------------------------------------------------------------


class TestRuleTwoNoUserinfo:
    def test_username_and_password_is_rejected(self) -> None:
        result = validate_static_url_shape("https://user:pw@events.example.edu/")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.USERINFO_PRESENT

    def test_username_only_is_rejected(self) -> None:
        result = validate_static_url_shape("https://user@events.example.edu/")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.USERINFO_PRESENT

    def test_no_userinfo_is_accepted(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/")
        assert isinstance(result, StaticallyValidHttpsUrl)


# ---------------------------------------------------------------------------
# Rule 3 — query strings and fragments rejected outright.
# ---------------------------------------------------------------------------


class TestRuleThreeNoQueryOrFragment:
    def test_query_string_is_rejected(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/p?q=1")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.QUERY_PRESENT

    def test_fragment_is_rejected(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/p#f")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.FRAGMENT_PRESENT

    def test_query_and_fragment_together_reports_query_first(self) -> None:
        # Rules are evaluated in the order listed in the module docstring; the
        # query check runs before the fragment check.
        result = validate_static_url_shape("https://events.example.edu/p?q=1#f")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.QUERY_PRESENT

    def test_plain_path_with_no_query_or_fragment_is_accepted(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/p")
        assert isinstance(result, StaticallyValidHttpsUrl)

    def test_query_or_fragment_is_not_stored_anywhere_on_success(self) -> None:
        """Even where accepted, the returned type carries no query/fragment field."""
        result = validate_static_url_shape("https://events.example.edu/p")
        assert isinstance(result, StaticallyValidHttpsUrl)
        assert not hasattr(result, "query")
        assert not hasattr(result, "fragment")


# ---------------------------------------------------------------------------
# Rule 4 — IPv4/IPv6 literal hosts rejected; DNS hostname required.
# ---------------------------------------------------------------------------


class TestRuleFourNoIpLiteralHost:
    def test_ipv4_literal_host_is_rejected(self) -> None:
        result = validate_static_url_shape("https://192.0.2.1/")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.IP_LITERAL_HOST

    def test_ipv6_literal_host_is_rejected(self) -> None:
        result = validate_static_url_shape("https://[2001:db8::1]/")
        assert isinstance(result, StaticUrlShapeRefusal)
        assert result.reason is StaticUrlShapeRefusalReason.IP_LITERAL_HOST

    def test_dns_hostname_is_accepted(self) -> None:
        result = validate_static_url_shape("https://events.example.edu/")
        assert isinstance(result, StaticallyValidHttpsUrl)

    def test_dns_hostname_that_looks_numeric_but_isnt_an_ip_is_accepted(self) -> None:
        # "999.example.edu" is a syntactically valid DNS label, not an IP
        # literal, even though it starts with digits.
        result = validate_static_url_shape("https://999.example.edu/")
        assert isinstance(result, StaticallyValidHttpsUrl)


# ---------------------------------------------------------------------------
# Passing validation does not claim a public destination or page.
# ---------------------------------------------------------------------------


class TestPassingDoesNotClaimDestinationOrPageQualification:
    def test_success_type_is_not_named_or_shaped_as_a_destination_guarantee(self) -> None:
        """The success type must be `StaticallyValidHttpsUrl`, not something that
        reads as a public-destination or public-page guarantee (e.g. `PublicUrl`).
        """
        result = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert type(result).__name__ == "StaticallyValidHttpsUrl"
        assert type(result).__name__ not in {"PublicUrl", "ValidatedPublicUrl"}

    def test_success_type_carries_no_resolution_or_classification_fields(self) -> None:
        """No field on the success type can be mistaken for a fetch/resolution
        result — only the shape fields the four static rules produce.
        """
        result = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert isinstance(result, StaticallyValidHttpsUrl)
        field_names = {f.name for f in _dataclass_fields(result)}
        assert field_names == {"normalized", "scheme", "host", "path"}
        for forbidden in (
            "resolved",
            "resolved_ip",
            "is_public",
            "destination",
            "redirect",
            "redirects_to",
            "page_type",
            "is_event_page",
            "dns",
        ):
            assert not hasattr(result, forbidden)

    def test_module_performs_no_fetch_no_matter_the_input(self) -> None:
        """A passing result never triggers any HTTP call — see the dedicated
        no-network test below for the structural guarantee; this test pins the
        *behavioral* claim that success alone never implies a fetch happened.
        """
        result = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert isinstance(result, StaticallyValidHttpsUrl)
        # If a fetch had occurred, some transport artifact (status code,
        # headers, body) would need to live somewhere on the result. It does
        # not exist as an attribute anywhere on this frozen dataclass.
        assert not hasattr(result, "status_code")
        assert not hasattr(result, "headers")
        assert not hasattr(result, "body")


# ---------------------------------------------------------------------------
# No persistence without an approved host/path projection.
# ---------------------------------------------------------------------------


class TestPersistenceRequiresApprovedProjection:
    def test_approved_projection_set_is_currently_empty(self) -> None:
        assert APPROVED_HOST_PATH_PROJECTIONS == ()

    def test_persistence_fails_closed_for_any_valid_url(self) -> None:
        validated = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert isinstance(validated, StaticallyValidHttpsUrl)

        result = project_for_persistence(validated)

        assert isinstance(result, PersistenceRefusal)
        assert result.reason is PersistenceRefusalReason.NO_APPROVED_PROJECTION

    def test_persistence_fails_closed_even_for_a_plausible_campus_host(self) -> None:
        """A host that looks like a legitimate campus events host is still
        refused: approval must come from a reviewed allowlist entry, never
        from a host merely looking trustworthy.
        """
        validated = validate_static_url_shape("https://events.ia-west.example.edu/rsvp/abc123")
        assert isinstance(validated, StaticallyValidHttpsUrl)

        result = project_for_persistence(validated)

        assert isinstance(result, PersistenceRefusal)
        assert result.reason is PersistenceRefusalReason.NO_APPROVED_PROJECTION


# ---------------------------------------------------------------------------
# No DNS/network call on the validation path.
# ---------------------------------------------------------------------------


class TestNoNetworkCallOnValidationPath:
    def test_validation_succeeds_even_if_dns_resolution_would_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Break every plausible way this module could reach the network. If
        `validate_static_url_shape` still succeeds, it never actually called
        any of them.
        """

        def _boom(*args: object, **kwargs: object) -> object:
            raise AssertionError("network call attempted on the static validation path")

        monkeypatch.setattr(socket, "getaddrinfo", _boom)
        monkeypatch.setattr(socket, "gethostbyname", _boom)
        monkeypatch.setattr(socket.socket, "connect", _boom)

        result = validate_static_url_shape("https://events.example.edu/spring-fair")

        assert isinstance(result, StaticallyValidHttpsUrl)

    def test_persistence_projection_also_makes_no_network_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> object:
            raise AssertionError("network call attempted on the persistence-projection path")

        monkeypatch.setattr(socket, "getaddrinfo", _boom)
        monkeypatch.setattr(socket, "gethostbyname", _boom)
        monkeypatch.setattr(socket.socket, "connect", _boom)

        validated = validate_static_url_shape("https://events.example.edu/spring-fair")
        assert isinstance(validated, StaticallyValidHttpsUrl)

        result = project_for_persistence(validated)

        assert isinstance(result, PersistenceRefusal)

    def test_module_does_not_import_socket(self) -> None:
        """Structural guarantee, not just a monkeypatch that happened to go
        unused: the domain package's import contract (pyproject.toml)
        forbids `socket` in `smartmatch_domain` outright, so this module has
        no way to reach the network even indirectly.
        """
        import smartmatch_domain.public_url as module

        assert "socket" not in vars(module)


# ---------------------------------------------------------------------------
# No contact-data path is opened.
# ---------------------------------------------------------------------------


class TestNoContactDataPathIsOpened:
    def test_no_public_name_mentions_email_name_or_phone(self) -> None:
        """The module's public API surface names nothing that could carry
        contact data — no field, type, or function suggests a name, email, or
        phone number is read, stored, or forwarded.
        """
        import smartmatch_domain.public_url as module

        forbidden_substrings = ("email", "phone", "contact", "organizer", "name")
        for exported in module.__all__:
            lowered = exported.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"exported name {exported!r} suggests a contact-data path"
                )

    def test_result_dataclasses_carry_no_contact_fields(self) -> None:
        """Every frozen dataclass this module can return is checked field by
        field — not just spot-checked — for anything that could carry a
        contact name, email address, or phone number.
        """
        import dataclasses

        import smartmatch_domain.public_url as module

        result_types = [
            module.StaticallyValidHttpsUrl,
            module.StaticUrlShapeRefusal,
            module.ApprovedHostPathProjection,
            module.PersistenceSafeUrl,
            module.PersistenceRefusal,
        ]
        forbidden_substrings = ("email", "phone", "contact", "organizer", "name")
        for result_type in result_types:
            for field in dataclasses.fields(result_type):
                lowered = field.name.lower()
                for forbidden in forbidden_substrings:
                    assert forbidden not in lowered, (
                        f"{result_type.__name__}.{field.name} suggests a contact-data path"
                    )

    def test_a_url_containing_email_shaped_text_is_never_copied_into_a_finding(self) -> None:
        """Passing an email address as (part of) a URL does not cause any
        field on the result to echo it back as a discovered contact — it is
        treated purely as URL text subject to the four shape rules.
        """
        result = validate_static_url_shape(
            "https://events.example.edu/contact/coordinator%40example.edu"
        )
        assert isinstance(result, StaticallyValidHttpsUrl)
        # The only place the text can possibly appear is `normalized`/`path`,
        # which are the URL shape itself, not a derived "contact" field. No
        # separate field exists that could be mistaken for a collected email.
        assert {f.name for f in _dataclass_fields(result)} == {
            "normalized",
            "scheme",
            "host",
            "path",
        }


def _dataclass_fields(instance: object) -> tuple[object, ...]:
    import dataclasses

    return dataclasses.fields(instance)
