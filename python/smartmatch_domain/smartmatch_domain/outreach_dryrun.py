"""The outreach **dry run**, now a thin view over the real composition path.

## What this module is, after R4

Everything it used to implement — the closed template registry, the renderer,
the eligibility-gated composition — moved to
:mod:`smartmatch_domain.outreach` when G4 opened and the send path was built.
What is left here is :func:`compose_dry_run`, which calls
:func:`~smartmatch_domain.outreach.compose_draft` and labels the result
``"would_send"``.

That is deliberately the *entire* difference. A dry run is now, precisely, a
real composition that nobody submitted — not a separate code path that
approximates one. Before R4 the distinction did not arise, because there was no
send path for the dry run to approximate; now there is, and two implementations
of "may this person be written to, and what would it say" is exactly the shape
that produces a preview a coordinator approves and a send that does something
else. The dry run is what someone is shown before they decide, so it has to be
the same computation the decision is about, or the approval is for a question
nobody asked.

## Why the module still exists at all

It could have been deleted and its callers repointed. It was not, for one
reason: ``tests/unit/test_outreach_dryrun.py`` is a careful, well-argued body of
tests about composition and consent, and it passes against this shim unchanged.
Deleting the module would have turned a domain change into a test rewrite in
the same commit, and a reviewer would then have had to check two things at once
— whether the rules changed, and whether the tests that would have caught a
change still ran. Keeping the shim lets the first question be answered by
reading a diff of ten lines.

The names below are re-exported rather than reimplemented. There is no second
copy of any rule in this file; the ``import`` list *is* the module.

## What is no longer true here

The old docstring said this module was unwired, that nothing imported it, and
that its absence from the running system was itself asserted by
``tests/unit/test_outreach_dryrun_wiring.py``. All three statements were correct
when G4 was deferred and none of them is correct now: R4 landed
``outreach.send`` on the worker registry, published the draft and send routes,
and rewrote those absence tests into presence tests (plan card L7,
``docs/plans/2026-09-04-r4-outreach-g4-implementation-plan.md``). The claim that
survives unchanged is the one that was never about wiring — the domain layer
still cannot open a socket, read a credential, or import
``smartmatch_providers``, because the import-linter contract "Domain is pure"
forbids it. A dry run cannot send; neither can anything else in this package.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from smartmatch_domain.outreach import (
    DRY_RUN_DISPOSITION,
    ELIGIBILITY_RULE,
    RESERVED_INVALID_SUFFIX,
    TEMPLATES,
    ContentStatus,
    DraftRecipient,
    EligibilityEvidence,
    OutreachCompositionError,
    OutreachTemplate,
    compose_draft,
    get_template,
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

#: The recipient type, under the name this module has always used for it.
#: :class:`~smartmatch_domain.outreach.DraftRecipient` is the same class — an
#: alias rather than a subclass, so ``isinstance`` and equality hold across both
#: names and a value composed by one caller is usable by the other.
DryRunRecipient = DraftRecipient


@dataclass(frozen=True, slots=True)
class OutreachDryRunResult:
    """A message that *would* be sent, and the proof it would be allowed to be.

    Never a receipt. :attr:`disposition` is always
    :data:`~smartmatch_domain.outreach.DRY_RUN_DISPOSITION`, and nothing in this
    module can construct a result that says otherwise — the field is set by
    :func:`compose_dry_run` from the constant and is never taken from a caller.

    This stays a distinct type from
    :class:`~smartmatch_domain.outreach.ComposedDraft` for exactly that reason.
    The two carry nearly the same data, and the difference is the ``disposition``
    field: a ``ComposedDraft`` makes no claim about what happens next, while this
    type asserts that nothing did. Merging them would mean one class that
    sometimes carries a disposition, which is a class that can be constructed
    without one.
    """

    disposition: str
    recipient_address: str
    template_id: str
    subject: str
    body: str
    evidence: EligibilityEvidence
    recipient_address_is_reserved_invalid: bool

    #: The template's review status, carried through from the composition. Not
    #: part of this type before R4 because no distinction existed to record.
    content_status: ContentStatus = ContentStatus.SYNTHETIC


def compose_dry_run(
    *,
    recipient: DryRunRecipient,
    template_id: str,
    values: Mapping[str, str],
) -> OutreachDryRunResult:
    """Compose the message that *would* be sent to ``recipient``, and send nothing.

    Delegates to :func:`~smartmatch_domain.outreach.compose_draft` — same gate,
    same order (consent before any text exists), same templates — and labels the
    result as a dry run.

    Args:
        recipient: The addressee's consent-relevant facts.
        template_id: A key of the closed
            :data:`~smartmatch_domain.outreach.TEMPLATES` registry.
        values: Exactly the template's declared placeholders.

    Returns:
        An :class:`OutreachDryRunResult` whose ``disposition`` is
        :data:`~smartmatch_domain.outreach.DRY_RUN_DISPOSITION`.

    Raises:
        ConsentViolationError: if the recipient is not send-eligible.
        OutreachCompositionError: if the template is unknown or the placeholder
            values do not match it exactly.
    """
    draft = compose_draft(recipient=recipient, template_id=template_id, values=values)

    return OutreachDryRunResult(
        disposition=DRY_RUN_DISPOSITION,
        recipient_address=draft.recipient_address,
        template_id=draft.template_id,
        subject=draft.subject,
        body=draft.body,
        evidence=draft.evidence,
        recipient_address_is_reserved_invalid=draft.recipient_address_is_reserved_invalid,
        content_status=draft.content_status,
    )
