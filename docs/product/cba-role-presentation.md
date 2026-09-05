# CBA role presentation

**Status:** Implemented (Wave 1, `CBA-ROLE-PRESENTATION`)
**Implementation:** [`python/smartmatch_domain/smartmatch_domain/role_presentation.py`](../../python/smartmatch_domain/smartmatch_domain/role_presentation.py), mirrored by [`apps/web/legacy-frontend/src/lib/roleLabels.ts`](../../apps/web/legacy-frontend/src/lib/roleLabels.ts)
**Customer source:** [`cba-smart-match-customer-requirements.md`](cba-smart-match-customer-requirements.md) §§2–4
**Register of open decisions:** [`docs/plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md)

This is the one place that answers "what do we call the person holding this
role". The API's portal mapping and the frontend's label helper both read it.
Neither invents its own, and neither derives a permission from it.

## The map

Stored strings are what the database holds and what every authorizer gates on.
Visible labels are what a reader is shown. The two columns are independent by
construction.

| Stored `membership.role` | Persona | Visible role label | Portal name |
|---|---|---|---|
| `student` | `student` | Student | Student Portal |
| `volunteer` | `event_host` | Event Host | Event Host Portal |
| `coordinator` | `speaker_connector` | Speaker Connector | Speaker Connector Portal |
| `admin` | `speaker_connector` | Speaker Connector (administrator) | CBA Administration |
| *(none)* | `speaker` | — | — |

Portal ids (`student`, `coordinator`, `volunteer`, `admin`) and the paths their
shells are mounted at are **unchanged**. Only the names moved.

## A label is not a power

Three separate things, and this change touches exactly one of them:

| | Decided by | Changed by this track |
|---|---|---|
| What a person **may do** | `smartmatch_authz`, per route, deny-by-default, over the stored role | No |
| Which shell they **may open** | `GET /v1/me/portals`, over the same stored roles | No |
| What either is **called** | This map | Yes |

Editing a label here cannot widen access, and that is checked rather than
asserted: `tests/authz/test_route_roles.py` proves no `required_roles` set
contains a persona or a visible label, and `tests/contract/test_portals_api.py`
shows an account listed a portal still refused an operation its role does not
carry. The reverse is equally forbidden — no capability, nav item, or route may
ever be gated on a label.

Login is untouched: one form, email and password, no portal chooser and no role
in the request (customer §3). A persona is something the server tells you after
you sign in, never something you tell the server.

## Stored strings stay as they are

`student`, `coordinator`, `volunteer`, `admin` are unchanged in the database, in
the seeds ([`tools/seed_pilot_logins.py`](../../tools/seed_pilot_logins.py)), and
in every `required_roles` set. A permanent rename touches all three plus any
operator runbook naming a role; doing it inside a presentation change would make
one reviewable decision look like two unreviewable ones. **Deferred** — see the
open questions below.

## Open questions this map records rather than resolves

### OQ-1 — `coordinator` and `admin` both present as Speaker Connector

Customer §2 gives all connector work — maintaining contact lists, receiving
requests, running matching, sending invitations, tracking responses — to one
persona. This system has long split those powers across two stored roles with
genuinely different reach: `admin` is tenant-wide for aggregates (policy rule 7),
`coordinator` is subtree-scoped. Both are therefore shown inside the Speaker
Connector persona, with distinguishable labels so a reader can still tell which
row they hold, and with exactly the powers they had before.

**What would settle it:** an owner decision on whether CBA wants one connector
role (merge the two, a migration) or two (a platform administrator that is *not*
a Speaker Connector, and its own label). Until then the shared persona is
presentation only.

### OQ-2 — customer §2 maps `coordinator` differently from the wave plan

The requirements table maps "Event Organizer / Volunteer → Event Host" and
"Chapter Admin → Speaker Connector", which would put `coordinator` under Event
Host. The wave plan's card for this track instead specifies "event-requesting
`volunteer` → Event Host, Connector powers over current `coordinator`/approved
admin context", which is what is implemented above — `coordinator` is the role
that actually holds the connector powers §2 describes (matching, invitations,
imports, review), and `volunteer` is the event-requesting shell.

**What would settle it:** owner confirmation of which stored role the customer's
"Event Host" means. Changing the answer is a one-line edit to the map and its
mirror; nothing else moves.

### OQ-3 — Speaker has no login

Customer §2 names Speaker as a persona. No `membership.role` grants it, because
speakers are represented as contact records rather than accounts. The persona is
named and left unmapped: inventing a role to fill it would be a schema decision
smuggled in as a label.

**What would settle it:** an owner decision on whether speakers sign in at all
this phase. Institutional SSO is separately deferred
([`a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md)).

## Where an unmapped role goes

Nowhere, deliberately. A role the map does not name has no persona, no label,
and no portal: `GET /v1/me/portals` returns an empty list, and the frontend shows
the stored string as the server spelled it rather than rounding it to the nearest
persona. An invented label is indistinguishable from a correct one until
something built on it is refused.
