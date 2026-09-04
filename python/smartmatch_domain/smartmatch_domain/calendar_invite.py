"""Calendar invite facade — ICS bytes from an already-resolved time slot.

Architecture v1.1 §3.1 makes ICS the only supported calendar artifact until an
institutional Calendar authorization model is approved. The synthetic pilot
development authorization (2026-09-03, §3) keeps gate **G5 (Calendar API)**
deferred to public-release planning and permits exactly one thing in the
meantime: *ICS artifacts*. So this module deliberately has no Google Calendar
client, no OAuth scope, no G5 environment variable and no network import — the
whole of "calendar integration" available today is handing the caller a byte
string it may write to disk or attach.

This is a **facade, not a second implementation**. Every RFC 5545 rule —
escaping, 75-octet line folding on codepoint boundaries, UTC conversion, the
deliberate absence of ``METHOD`` — lives in :mod:`smartmatch_domain.ics` and is
reached through :func:`~smartmatch_domain.ics.generate_ics`. Duplicating any of
it here would fork the behavior that finding F-003's golden tests pin.

What the facade adds over calling ``generate_ics`` directly is one narrower
contract, aimed at the caller most likely to get it wrong:

* **The slot must already be resolved.** ``starts_at`` and ``ends_at`` are both
  required and may not be ``None``. F-003 is the finding that the legacy
  generator turned an unparsed recurrence string ("Every Tuesday") into a
  confident invite 30 days out; the shape of that defect is a *missing* value
  flowing into a code path willing to supply one. Here a missing value has
  nowhere to go but :class:`~smartmatch_domain.ics.UnschedulableEventError`.
* **No default duration.** ``generate_ics`` falls back to one hour when
  ``ends_at`` is omitted, preserved from the legacy so the port stayed a port.
  A one-hour guess is still a guess, and this facade is the layer where the
  answer is "the caller knows the end time or there is no invite".
* **Bytes, not ``str``.** An .ics artifact is transported as UTF-8 octets, and
  RFC 5545 line folding is defined over octets. Encoding here keeps the one
  place that could pick a different codec next to the one place that folded to
  the octet limit.

Unwired by design: nothing imports this module from the API or worker
composition roots, and it adds no HTTP route. See
``tests/unit/test_calendar_invite_wiring.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from smartmatch_domain.ics import (
    ICS_CONTENT_TYPE,
    CalendarInvite,
    UnschedulableEventError,
    generate_ics,
)

__all__ = [
    "ICS_CONTENT_TYPE",
    "ICS_ENCODING",
    "UnschedulableEventError",
    "build_invite_ics",
]

#: The charset named in :data:`~smartmatch_domain.ics.ICS_CONTENT_TYPE`. Named
#: rather than inlined so the declared content type and the actual encoding
#: cannot drift apart silently.
ICS_ENCODING: Final[str] = "utf-8"


def build_invite_ics(
    *,
    title: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    generated_at: datetime,
    location: str | None = None,
    description: str | None = None,
    uid: str | None = None,
) -> bytes:
    """Render one resolved event as RFC 5545 ICS bytes.

    Args:
        title: SUMMARY text. Must be non-blank.
        starts_at: Timezone-aware start instant. ``None`` means the event's time
            was never resolved, which is refused rather than filled in.
        ends_at: Timezone-aware end instant. Also required: unlike
            ``generate_ics``, this facade does not fall back to a one-hour
            event, because a guessed duration is still a value the source data
            did not contain.
        generated_at: Timezone-aware DTSTAMP instant, injected by the caller.
            The domain package reads no clock, so identical inputs always
            produce identical bytes.
        location: Optional LOCATION text.
        description: Optional DESCRIPTION text.
        uid: Optional explicit UID. Omit to get the deterministic UID derived
            from title and start instant, so re-issuing an unchanged invite
            updates the recipient's calendar entry instead of duplicating it.

    Returns:
        The complete .ics document encoded as UTF-8 octets, CRLF-terminated and
        folded to 75 octets per line by :func:`generate_ics`.

    Raises:
        UnschedulableEventError: if either endpoint is unresolved (``None``),
            not a ``datetime``, or naive. Callers must surface an explicit
            "unscheduled"/"unsynchronized" state (architecture v1.1 §3.6 N1)
            rather than substituting a plausible-looking slot.
        ValueError: if ``title`` is blank or ``ends_at`` precedes ``starts_at``.
    """
    invite = CalendarInvite(
        event_name=title,
        starts_at=_require_resolved(starts_at, "starts_at"),
        ends_at=_require_resolved(ends_at, "ends_at"),
        location=location,
        description=description,
        uid=uid,
    )
    return generate_ics(invite, generated_at=generated_at).encode(ICS_ENCODING)


def _require_resolved(value: datetime | None, field: str) -> datetime:
    """Refuse an endpoint the caller never resolved, and return it otherwise.

    ``CalendarInvite`` already rejects naive and non-``datetime`` values; what
    it cannot reject is ``None`` for ``ends_at``, which it reads as "default to
    one hour". This closes that one gap before the value reaches the dataclass,
    and gives ``None`` the same unschedulable signal as an unparsed recurrence
    string so a caller has a single exception to handle.

    Returning the narrowed value rather than asserting in place is what lets the
    call site stay a single expression, and makes "the value was checked" and
    "the value was used" the same statement — there is no unchecked path to the
    dataclass to forget about later.
    """
    if value is None:
        raise UnschedulableEventError(
            f"{field} is unresolved. SmartMatch never infers a time slot "
            "(architecture v1.1 §3.6); surface the event as unscheduled instead."
        )
    return value
