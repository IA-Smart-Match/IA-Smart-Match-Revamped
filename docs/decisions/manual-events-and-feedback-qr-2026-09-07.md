# Manual events and external feedback QR decision

**Status:** Accepted  
**Date:** 2026-09-07

## Decision

Administrators may create, edit, and publish events directly in Smart Match for an authorized organizational unit. Coordinators may read published events for their authorized units. Manual values are observed data and retain their explicit time precision and IANA time zone.

This authorization is independent of the crawler. It does not authorize crawler routes, provider calls, scheduled discovery, background scraping, or a bypass of the existing crawler security gate. Manual entry is the primary event source.

Each event may have one feedback QR code. An administrator supplies an external HTTPS form URL. Smart Match stores that destination and generates a stable, opaque public redirect URL; changing the destination preserves the public token so printed codes keep working. The redirect is active only for a published event.

The public redirect records only its QR identifier and open time. It stores no cookie, IP address, user agent, referrer, or other visitor identifier. The interface calls the resulting count “QR opens” and makes no claim about form completion or conversion.

Smart Match validates URL structure but never fetches, inspects, proxies, hosts, or submits the external form. Local application code renders QR image assets, so event or form URLs are not disclosed to a third-party QR-rendering service.

## Compatibility and scope

- Existing attendance and match-progress event references receive initially non-validating foreign keys so legacy orphan rows do not block rollout while new writes remain constrained.
- `/opportunities` redirects to `/events` for bookmarked frontend links.
- Matching scores, assignments, external feedback schemas, cancellation, deletion, recurrence, and coordinator editing are unchanged.
- The retired `/api/qr/*` backend may remain temporarily for compatibility, but no new frontend may call it.
