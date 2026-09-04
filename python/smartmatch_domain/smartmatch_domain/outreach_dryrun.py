"""Synthetic outreach **dry run**: compose a message, prove send eligibility, stop.

G4 (outreach send) is deferred until public-release planning; what engineering
is permitted to build now is the "consent lifecycle, dry-run only" column of the
deferred-gate table in
``docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`` §3.
This module is that column and nothing more.

## What "dry run" means here, precisely

:func:`compose_dry_run` returns a structured description of a message that
*would* be sent — recipient, subject, template id, rendered body, and the
evidence that the recipient was eligible — and the process it runs in never
opens a socket, never reads a credential, and never reaches a provider. There
is no SMTP client here, no Resend/SendGrid/Gmail adapter, and no code path that
consults ``SMARTMATCH_EMAIL_API_KEY``; the domain layer cannot import ``os``,
``socket``, ``httpx``, ``requests``, or ``smartmatch_providers`` at all (the
import-linter contract "Domain is pure" in the root ``pyproject.toml``), so
this is a structural guarantee rather than a promise. The result's
:attr:`OutreachDryRunResult.disposition` is therefore always
:data:`DRY_RUN_DISPOSITION` — ``"would_send"``, never ``"sent"``. Reporting a
send that did not happen is the fake-success defect
``docs/plans/frontend-broken-buttons.md`` B17 catalogues in the legacy
``CoordinatorOutreach`` **Send** button, which logged to the console and then
told the coordinator "Message sent!". A caller that wants a real send will not
find one here.

## Eligibility is asserted before a body exists

The gate runs first, on purpose. :func:`compose_dry_run` calls
:func:`smartmatch_domain.consent.assert_send_eligible` *before* it renders
anything, so an ineligible recipient never gets so far as having message text
composed about them. A research-discovered address — ``DISCOVERED``,
``CORROBORATED``, or consented from a ``SCRAPED``, ``PURCHASED``, or
``INFERRED`` source — raises
:class:`~smartmatch_domain.consent.ConsentViolationError` and produces no
result at all.

## Why there is no "invite to consent" template

The obvious way to make a scraped address usable would be a template asking it
to opt in. ``consent.py`` says why that path does not exist: *"an email asking
a scraped address to opt in is itself prohibited outreach"*. So the closed
:data:`TEMPLATES` registry contains only messages that presuppose an existing
approved consent record, and there is no ``template_id`` — and no way to supply
one — that solicits consent from someone who has not already given it. A test
pins that absence, because the registry growing such an entry later would
reopen exactly the hole the consent lifecycle closes.

## Not wired

Nothing imports this module. It is not registered on
``smartmatch_worker.handlers.default_registry``, no router exposes it, and the
shipped OpenAPI contract is unchanged — an unwired scaffold under a deferred
gate, whose absence from the running system is itself asserted by
``tests/unit/test_outreach_dryrun_wiring.py``.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from smartmatch_domain.consent import (
    APPROVED_CONSENT_SOURCES,
    ConsentSource,
    ContactState,
    assert_send_eligible,
)

__all__ = [
    "DRY_RUN_DISPOSITION",
    "ELIGIBILITY_RULE",
    "RESERVED_INVALID_SUFFIX",
    "TEMPLATES",
    "DryRunRecipient",
    "EligibilityEvidence",
    "OutreachCompositionError",
    "OutreachDryRunResult",
    "OutreachTemplate",
    "compose_dry_run",
    "get_template",
]

#: The only disposition this module can produce. A dry run records what *would*
#: happen; it never claims a send occurred.
DRY_RUN_DISPOSITION: Final[str] = "would_send"

#: The dotted name of the check every result was gated by, recorded on the
#: evidence so an audit reads the rule rather than trusting the caller.
ELIGIBILITY_RULE: Final[str] = "smartmatch_domain.consent.assert_send_eligible"

#: Reserved TLD (RFC 2606) used by every synthetic pilot address. Recorded as
#: evidence, never used as a gate: a real-looking address is not thereby
#: eligible, and a reserved one is not thereby exempt from consent.
RESERVED_INVALID_SUFFIX: Final[str] = ".invalid"


class OutreachCompositionError(ValueError):
    """Raised when a message cannot be composed from the inputs given.

    A ``ValueError``, unlike
    :class:`~smartmatch_domain.consent.ConsentViolationError`: this is a
    malformed request, not an authorization failure. The two are deliberately
    distinct so a caller can never treat a blocked send as a typo.
    """


@dataclass(frozen=True, slots=True)
class OutreachTemplate:
    """One composable message shape.

    Attributes:
        template_id: Stable identifier, recorded on every result.
        subject: ``string.Template`` source for the subject line.
        body: ``string.Template`` source for the plain-text body.
        placeholders: Exactly the names ``subject`` and ``body`` between them
            require. Declared rather than derived, so a template whose text and
            whose contract disagree is caught by a test instead of by a
            half-rendered message.
        presumes_existing_consent: Always ``True``. Present as an explicit,
            assertable field rather than as a comment, so "no template solicits
            consent" is a property of the data a test can read.
    """

    template_id: str
    subject: str
    body: str
    placeholders: frozenset[str]
    presumes_existing_consent: bool = True


def _template(
    template_id: str, *, subject: str, body: str, placeholders: frozenset[str]
) -> OutreachTemplate:
    return OutreachTemplate(
        template_id=template_id, subject=subject, body=body, placeholders=placeholders
    )


#: Placeholders every shipped template takes. One set, so the two templates
#: cannot drift into subtly different call contracts.
_PILOT_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        "professional_name",
        "unit_name",
        "event_name",
        "event_date",
        "coordinator_name",
    }
)

#: The closed set of templates. Every entry addresses someone who has *already*
#: consented through an approved source; none asks anyone to opt in.
TEMPLATES: Final[Mapping[str, OutreachTemplate]] = MappingProxyType(
    {
        template.template_id: template
        for template in (
            _template(
                "pilot.event_invitation.v1",
                subject="$event_name on $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "$unit_name is hosting $event_name on $event_date, and you are "
                    "on the list of professionals who agreed to hear about "
                    "opportunities like it.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_PILOT_PLACEHOLDERS,
            ),
            _template(
                "pilot.visit_confirmation.v1",
                subject="Confirming $event_name on $event_date",
                body=(
                    "Hello $professional_name,\n\n"
                    "Confirming your visit to $unit_name for $event_name on "
                    "$event_date.\n\n"
                    "$coordinator_name\n"
                ),
                placeholders=_PILOT_PLACEHOLDERS,
            ),
        )
    }
)


@dataclass(frozen=True, slots=True)
class DryRunRecipient:
    """The consent-relevant facts about one addressee.

    Every field is required. There is no default for ``consent_source`` or
    ``suppressed``: an unknown consent source is not an approved one, and an
    unknown suppression is not "not suppressed" (ADR-0011 — unknown is never
    silently zero).
    """

    address: str
    contact_state: ContactState
    consent_source: ConsentSource | None
    suppressed: bool


@dataclass(frozen=True, slots=True)
class EligibilityEvidence:
    """Why this recipient was judged send-eligible, recorded with the result.

    The point is auditability: a result carries the facts the decision was made
    from, so a reviewer can re-derive the decision without rerunning anything.
    """

    contact_state: ContactState
    consent_source: ConsentSource
    consent_source_is_approved: bool
    suppressed: bool
    checked_by: str = ELIGIBILITY_RULE


@dataclass(frozen=True, slots=True)
class OutreachDryRunResult:
    """A message that *would* be sent, and the proof it would be allowed to be.

    Never a receipt. :attr:`disposition` is always
    :data:`DRY_RUN_DISPOSITION`; nothing in this module can construct a result
    that says otherwise.
    """

    disposition: str
    recipient_address: str
    template_id: str
    subject: str
    body: str
    evidence: EligibilityEvidence
    recipient_address_is_reserved_invalid: bool


def get_template(template_id: str) -> OutreachTemplate:
    """Return the named template.

    Raises:
        OutreachCompositionError: if ``template_id`` is not in the closed
            :data:`TEMPLATES` registry. Unknown ids are refused rather than
            treated as free-form text, so no caller can compose a message this
            module has not reviewed.
    """
    template = TEMPLATES.get(template_id)
    if template is None:
        raise OutreachCompositionError(
            f"unknown outreach template {template_id!r}; known templates are {sorted(TEMPLATES)}"
        )
    return template


def _render(source: str, values: Mapping[str, str]) -> str:
    """Substitute ``$name`` placeholders, refusing anything left unresolved."""
    try:
        return string.Template(source).substitute(values)
    except (KeyError, ValueError) as exc:
        raise OutreachCompositionError(f"could not render template text: {exc}") from exc


def _validated_values(template: OutreachTemplate, values: Mapping[str, str]) -> Mapping[str, str]:
    """Return ``values`` iff it is exactly the template's declared placeholders."""
    supplied = frozenset(values)
    missing = template.placeholders - supplied
    unexpected = supplied - template.placeholders
    if missing or unexpected:
        raise OutreachCompositionError(
            f"template {template.template_id!r} takes {sorted(template.placeholders)}; "
            f"missing {sorted(missing)}, unexpected {sorted(unexpected)}"
        )
    return values


def compose_dry_run(
    *,
    recipient: DryRunRecipient,
    template_id: str,
    values: Mapping[str, str],
) -> OutreachDryRunResult:
    """Compose the message that *would* be sent to ``recipient``, and send nothing.

    The consent gate runs first, before any message text exists, so an
    ineligible recipient never has a body composed about them.

    Args:
        recipient: The addressee's consent-relevant facts.
        template_id: A key of the closed :data:`TEMPLATES` registry.
        values: Exactly the template's declared placeholders.

    Returns:
        An :class:`OutreachDryRunResult` whose ``disposition`` is
        :data:`DRY_RUN_DISPOSITION`.

    Raises:
        ConsentViolationError: if the recipient is not send-eligible — a
            research-discovered address, an unapproved consent source, or a
            suppression. Raised by
            :func:`~smartmatch_domain.consent.assert_send_eligible`, which owns
            this rule; this module does not restate it.
        OutreachCompositionError: if the template is unknown or the placeholder
            values do not match it exactly.
    """
    assert_send_eligible(
        recipient.contact_state,
        consent_source=recipient.consent_source,
        suppressed=recipient.suppressed,
    )
    consent_source = recipient.consent_source
    if consent_source is None:  # pragma: no cover - assert_send_eligible refuses None
        raise OutreachCompositionError("send-eligible recipient without a consent source")

    template = get_template(template_id)
    checked_values = _validated_values(template, values)

    return OutreachDryRunResult(
        disposition=DRY_RUN_DISPOSITION,
        recipient_address=recipient.address,
        template_id=template.template_id,
        subject=_render(template.subject, checked_values),
        body=_render(template.body, checked_values),
        evidence=EligibilityEvidence(
            contact_state=recipient.contact_state,
            consent_source=consent_source,
            consent_source_is_approved=consent_source in APPROVED_CONSENT_SOURCES,
            suppressed=recipient.suppressed,
        ),
        recipient_address_is_reserved_invalid=recipient.address.endswith(RESERVED_INVALID_SUFFIX),
    )
