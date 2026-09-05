"""Customer §18's contact fields are declared once, and email is not consent.

CBA-IMPORT-CONTRACT extends the ratified pilot column contract
(``docs/pilot-data/columns.yaml``) so that every field customer §18 names — the
source columns a coordinator's export carries, and the additional fields §18
says matching needs — is representable on an import, without adding
persistence, inference, or a second copy of any column name in Python.

Four promises are held here:

1. **Every §18 field appears exactly once.** Not once per spelling, and not
   once in YAML plus once in a Python list. Where §18's wording names a
   concept the contract already ratified under a different spelling
   (``company`` for "Company Name", ``title`` for "Current Position",
   ``expertise_tags`` for "Topic/interests/expertise text"), the ratified
   spelling stays and the customer's wording is *not* added beside it — that
   would be the same field twice.
2. **Nothing new is required.** §18 opens by saying the customer's data is
   scattered across people and systems with no authoritative export. A
   contract that made "Graduation Year" mandatory would refuse most real
   submissions for a reason the customer already told us about.
3. **A privacy question is withheld, not guessed.** A speaker's personal
   ``contact_email`` has no closed gate: P9 Gate B decided *published* event
   contact fields, which is a different question about different data. It is
   therefore declared ``gate_pending`` with the ``withhold`` posture — the
   mechanism the contract already carries — so the column is recognized and
   the value is not stored.
4. **Collecting an email is never consent.** Neither ``contact_email`` nor
   ``willingness_to_partner_with_cpp`` is a
   :class:`~smartmatch_domain.consent.ConsentSource`, and no import path
   reaches ``CONSENTED``. Customer §18 asks for a stated willingness on a
   contact record; ``smartmatch_domain.consent`` decides who may be emailed,
   and the two never touch.

No expectation here is imported from application code: the YAML is the source
of truth, so the column names below are written out in the test and compared
against what the loader returns.
"""

from __future__ import annotations

import json

import pytest
from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_transition,
)
from smartmatch_domain.ingest import Severity, normalize_header, validate_columns
from smartmatch_worker.column_contract import default_contract_path, load_column_contract
from smartmatch_worker.handlers import _gate_pending_findings, _normalize_row

#: Customer §18's "Expected source columns" table, mapped onto the contract
#: column that represents each one. The three ``None``-free entries that do not
#: spell the customer's wording are deliberate: they were ratified earlier
#: under a different spelling, and re-declaring the customer's wording beside
#: them would be the field twice. See ``docs/pilot-data/cba-field-mapping.md``.
SOURCE_FIELD_COLUMNS: dict[str, str] = {
    "Name": "name",
    "Company Name": "company",
    "Current Position": "title",
    "Contact Email": "contact_email",
    "Alumni (Y/N)": "alumni",
    "Graduation Year": "graduation_year",
    "Major": "major",
    "Willingness to Partner with CPP (Y/N)": "willingness_to_partner_with_cpp",
    "Past Engagement (free text)": "past_engagement",
}

#: §18's "Additional fields required by matching", mapped the same way. The
#: column names are `speaker_profile`'s (migration 0024), so an import column
#: and the column it will eventually be reviewed into share a spelling —
#: except the topic text, which ``expertise_tags`` already covers.
MATCHING_FIELD_COLUMNS: dict[str, str] = {
    "primary Industry sector": "primary_industry_code",
    "primary Role category": "primary_role_code",
    "Topic/interests/expertise text": "expertise_tags",
    "city": "location_city",
    "ZIP code": "location_postal_code",
    "optional prior talk information": "prior_talk",
}

#: The one column whose collection posture no gate has answered.
WITHHELD_COLUMN = "contact_email"


@pytest.fixture(scope="module")
def professionals():
    """The shipped contract's ``professionals`` dataset."""
    return load_column_contract(default_contract_path())["professionals"]


@pytest.fixture(scope="module")
def rows() -> list[dict[str, object]]:
    """The CBA contact fixture, as a coordinator's export would arrive."""
    path = default_contract_path().parent / "fixtures" / "professionals_cba_contact.json"
    with path.open(encoding="utf-8") as handle:
        loaded: list[dict[str, object]] = json.load(handle)
    return loaded


class TestEveryCustomerFieldIsRepresented:
    """§18's fields are all declared, each exactly once."""

    @pytest.mark.parametrize(
        ("field", "column"),
        sorted(SOURCE_FIELD_COLUMNS.items()) + sorted(MATCHING_FIELD_COLUMNS.items()),
    )
    def test_the_field_is_declared(self, professionals, field: str, column: str) -> None:
        declared = professionals.required + professionals.optional
        assert column in declared, (
            f"customer §18 field {field!r} has no column in the ratified contract; "
            f"expected {column!r} among {declared}"
        )

    def test_no_field_is_declared_twice_under_two_spellings(self, professionals) -> None:
        """``validate_columns`` raises on a duplicate; catch it here, not there.

        The failure this guards is subtler than an exact duplicate: adding
        ``company_name`` beside the ratified ``company`` normalizes to a
        *different* column, so nothing raises — the same customer field is
        simply declared twice and a coordinator's export satisfies whichever
        one they happened to spell.
        """
        declared = professionals.required + professionals.optional
        normalized = [normalize_header(column) for column in declared]
        assert len(set(normalized)) == len(normalized), (
            f"a column is declared twice after normalization: {sorted(declared)}"
        )
        for customer_spelling in ("company_name", "current_position", "topic_text", "zip_code"):
            assert customer_spelling not in normalized, (
                f"{customer_spelling!r} duplicates a field the contract already declares "
                "under its ratified spelling; see docs/pilot-data/cba-field-mapping.md"
            )

    def test_the_required_set_is_unchanged(self, professionals) -> None:
        """§18 says the source data is scattered; nothing new may be mandatory."""
        assert professionals.required == ("name", "metro_region")

    def test_every_new_cba_column_is_optional(self, professionals) -> None:
        new_columns = set(SOURCE_FIELD_COLUMNS.values()) | set(MATCHING_FIELD_COLUMNS.values())
        for column in sorted(new_columns - {"name", "metro_region"}):
            assert column in professionals.optional, (
                f"{column!r} must be optional: customer §18 describes a scattered source, "
                "so requiring it would refuse real submissions"
            )


class TestContactEmailPosture:
    """The one sensitive field defers to a gate instead of guessing."""

    def test_contact_email_is_withheld_pending_a_gate(self, professionals) -> None:
        assert professionals.withheld_columns == (WITHHELD_COLUMN,)

    def test_the_withheld_entry_names_its_gate_and_reason(self, professionals) -> None:
        entry = next(e for e in professionals.gate_pending if e.column == WITHHELD_COLUMN)
        assert entry.posture == "withhold"
        assert entry.gate, "a gate_pending column must name the gate that owns it"
        assert entry.reason, "a withheld column must say why the gate has not answered"

    def test_the_withheld_column_stays_declared_so_it_is_never_unexpected(
        self, professionals
    ) -> None:
        """Not storing a value must not read as "you sent something wrong"."""
        assert WITHHELD_COLUMN in professionals.optional

    def test_a_submission_carrying_it_is_warned_about_not_rejected(self, professionals) -> None:
        rows = [
            {
                "name": "A. Rivera",
                "metro_region": "Inland Empire",
                "Contact Email": "nobody@example.edu",
            }
        ]
        findings = _gate_pending_findings(professionals, rows)
        assert [f.code for f in findings] == ["columns_withheld_pending_gate"]
        assert findings[0].severity is Severity.WARNING
        assert findings[0].columns == (WITHHELD_COLUMN,)

    def test_the_value_is_dropped_before_anything_is_written(self, professionals) -> None:
        row = {
            "name": "A. Rivera",
            "metro_region": "Inland Empire",
            "Contact Email": "nobody@example.edu",
            "major": "Finance",
        }
        normalized = _normalize_row(row, withhold=professionals.withheld_columns)
        assert "contact_email" not in normalized
        assert normalized["name"] == "A. Rivera"
        assert normalized["major"] == "Finance"

    def test_a_full_cba_row_is_usable_despite_the_open_gate(self, professionals) -> None:
        """A gate that has not answered may not make a dataset unusable."""
        row = {column: "x" for column in professionals.required + professionals.optional}
        quality = validate_columns(
            "professionals",
            [row],
            required=professionals.required,
            optional=professionals.optional,
            blank_sentinels=professionals.blank_sentinels,
            blank_sentinels_by_column=professionals.blank_sentinels_by_column,
        )
        assert quality.findings == (), quality.findings
        assert quality.is_usable


class TestEmailCollectionIsNotConsent:
    """Customer §18 collects contact data; ``consent`` decides who may be emailed."""

    def test_no_consent_source_comes_from_an_import(self) -> None:
        approved = {source.value for source in APPROVED_CONSENT_SOURCES}
        assert approved == {
            "self_service",
            "authenticated",
            "in_person",
            "institutional_relationship",
        }
        for guess in ("import", "imported", "spreadsheet", "contact_email", "willingness"):
            assert guess not in approved

    def test_a_willingness_column_is_not_a_consent_source(self, professionals) -> None:
        """§18's "Willingness to Partner with CPP" is a stated preference only.

        It is a column on a contact record. Reading it as permission to send
        would be exactly the inference ``consent`` exists to forbid, and there
        is no ``ConsentSource`` member it could map onto.
        """
        assert "willingness_to_partner_with_cpp" in professionals.optional
        assert not any(
            "willing" in source.value or "partner" in source.value for source in ConsentSource
        )

    def test_reaching_consented_still_needs_an_approved_source(self) -> None:
        with pytest.raises(ConsentViolationError):
            assert_transition(
                ContactState.RELATIONSHIP_RECORDED,
                ContactState.CONSENTED,
                consent_source=None,
            )

    def test_the_import_contract_declares_no_consent_column(self, professionals) -> None:
        """No column on this dataset can be mistaken for a recorded consent.

        An import that could write a consent state would make a coordinator's
        spreadsheet an authorization surface. The contract carries the
        contact's own fields and nothing about permission.
        """
        declared = {normalize_header(c) for c in professionals.required + professionals.optional}
        for forbidden in ("consent", "consent_source", "consented", "opt_in", "send_eligible"):
            assert forbidden not in declared


class TestTheCbaFixture:
    """A CBA-shaped export validates clean against the extended contract.

    ``docs/pilot-data/verify_fixtures.py`` checks every fixture against the
    contract, but nothing in CI runs it. This is the same check for the one
    fixture this card added, in a place CI does run — the claim being checked
    is that a coordinator's export spelled the customer's way needs no alias
    table to satisfy a contract written in snake_case.
    """

    def test_the_fixture_carries_every_declared_column(self, professionals, rows) -> None:
        present = {normalize_header(str(key)) for row in rows for key in row}
        declared = {
            normalize_header(column)
            for column in professionals.required + professionals.optional
            # `initials` and `pronouns` predate the CBA pivot and §18 names
            # neither; a CBA export is not expected to carry them.
            if column not in ("initials", "pronouns")
        }
        assert declared <= present, f"fixture is missing {sorted(declared - present)}"

    def test_it_validates_with_no_findings(self, professionals, rows) -> None:
        """Customer header spellings and snake_case declarations agree.

        ``"Graduation Year"`` and ``graduation_year`` are the same column
        after ``normalize_header``, so no finding is produced — in particular
        no ``unexpected_columns``, which is what a header the contract does
        not declare would produce.
        """
        quality = validate_columns(
            "professionals",
            rows,
            required=professionals.required,
            optional=professionals.optional,
            blank_sentinels=professionals.blank_sentinels,
            blank_sentinels_by_column=professionals.blank_sentinels_by_column,
        )
        assert quality.findings == (), quality.findings
        assert quality.is_usable
        assert quality.row_count == len(rows)

    def test_every_address_in_it_is_a_reserved_example_domain(self, rows) -> None:
        """A fixture is committed data; it may not carry a real address."""
        for row in rows:
            address = str(row["Contact Email"])
            assert address.endswith(("@example.edu", "@example.com", "@example.org")), address
