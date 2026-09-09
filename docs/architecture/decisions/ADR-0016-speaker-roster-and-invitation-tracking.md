# ADR-0016 — Speaker roster and invitation tracking

**Status:** Accepted
**Date:** 8 September 2026
**Contract:** Speaker Roster, Smart Match, and Invitation Tracking plan

## Decision

Smart Match owns a unit-scoped, published speaker roster and a shared speaker–event invitation record. Speaker Connectors maintain the roster and record initial outreach completed outside the platform. Event Hosts run deterministic matching, submit one to three speakers, and manage confirmation and attendance after handoff.

Matching uses topic coverage at 70% and a structured home/service-region match at 30%. Only speakers in the latest published, available roster are eligible. Results are capped at three, omit profiles without topic or region evidence, and expose plain-language explanations without scores or percentages.

The invitation states are Not Emailed Yet, Awaiting Response, Declined, Ready for Handoff, Handed Off, Awaiting Final Confirmation, Confirmed, Withdrawn, Attended, Did Not Attend, and Event Cancelled. Transitions are role-controlled, optimistic-versioned, idempotent where required, and recorded in append-only history. Both roles may add internal notes. Connector corrections require a reason and cannot fabricate attendance or override cancellation.

## Consequences

- Smart Match has no email generation, sending, scheduling, batch invitation, unsubscribe, fake messaging, or delivery-monitoring feature.
- Speaker email and phone remain Connector-only profile data.
- Legacy `pipeline_record` rows remain intact for compatibility but receive no new invitation writes.
- Event cancellation deactivates its feedback QR because public redirects require a published event.
- The prior workshop direction to match before availability and batch-invite is superseded. Availability is an eligibility filter before matching.
