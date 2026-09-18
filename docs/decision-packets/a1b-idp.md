# A1b — live identity-provider wiring

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Whether, when, and on whose authority the A1b worksheet's outstanding
identity-provider configuration fields are recorded and approved, given that the
pilot now runs on an owner-authorized database-credential login instead.

## Owner(s) of the decision

- **Google Cloud IdP provisioner (P2): Danny Tran (@BrooklynD23)**, named
  2026-09-03 — [`../decisions/owner-roster.md`](../decisions/owner-roster.md)
  row 6, with the note "Worksheet Part 1 fields still required".
- **OQ-A1b-006** asks for "The named owner who approves the completed worksheet,
  the approval date, and the administrative location of the configuration
  (worksheet §1.4)" — that approver is **not named** in
  [`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md).
- The pilot-login deviation was decided "by the project owner, 2026-09-04" —
  [`../decisions/pilot-login-decision-2026-09-04.md`](../decisions/pilot-login-decision-2026-09-04.md);
  that file states the status without naming the individual in its header.
- Every one of OQ-A1b-001 through -005 is a tenant fact, not a decision an
  owner picks from options; the register says so explicitly (see below).

## Current safe default in force

[`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md)
states one default for all six rows:

> The safe default is the same in every case: the API keeps building
> `FixtureTokenVerifier` (`smartmatch_providers.registry.build_token_verifier`,
> called from `services/api/smartmatch_api/main.py`), and any live issuer is
> *refused*, never guessed. A missing decision fails toward nobody being able to
> sign in, not toward somebody being trusted on an unverified token. That
> asymmetry is the whole policy — a wrong refusal costs a pilot user a login; a
> wrong acceptance is an authentication bypass no later decision can undo.

and the prohibition on filling the gaps:

> Nothing here is a placeholder that *reports success*. Where a decision is
> missing, the code refuses, and it says which decision it is waiting on. **No
> agent may fill any of these in**; the worksheet's own rule stands.

[`../decisions/a1b-idp-configuration-worksheet.md`](../decisions/a1b-idp-configuration-worksheet.md):

> **Status:** **TENANT PROCURED — WORKSHEET UNFILLED.** Google Cloud IdP
> dev/test tenant exists (confirmed 2026-09-02). Part 1 configuration fields
> below remain blank until the provisioner commits values.

> **It is not a decision artifact and does not satisfy the stop-gate.** Cards
> A1–A4 remain blocked until every field below is filled in and approved by a
> named owner, and the completed artifact is committed.

[`../decisions/pilot-login-decision-2026-09-04.md`](../decisions/pilot-login-decision-2026-09-04.md)
records a scoped deviation, not a closure:

> **Status: DECIDED for the pilot, by the project owner, 2026-09-04.**
> **Scope: the synthetic pilot only. Not production authentication.**
> … Production SSO is **explicitly deferred until after the pilot**. … recorded
> here because it is a deviation and not a completion.

**Conflict flagged.** [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§3 Wave C item 4 sequences "Configure A1b and replace the truthful
unavailable-login state with the real institutional sign-in flow", and §4 step 1
requires the login page to "render a non-interactive unavailable state that
clearly says institutional sign-in is not connected". The 2026-09-04 pilot-login
decision supersedes that unavailable state for the pilot with a
database-credential login. The plan has not been amended to record the
deviation.

## Options

Neutral; each has consequences. This packet selects none, and records no
issuer, audience, endpoint, scope, or client identifier.

1. **Complete the worksheet now.** The provisioner records Part 1 in full and a
   named owner approves it. *Consequence:* the P2 stop-gate becomes passable;
   cards A1–A4 become runnable work (this packet authorizes none of it); the
   pilot-login path would then need its own retirement decision.
2. **Complete only the fields the pilot needs and defer the rest.**
   *Consequence:* the A1b plan's stop-gate explicitly refuses this shape — "A
   decision naming only issuer/audience/JWKS is incomplete for card A2; the
   executor stops and reports the missing client-flow fields rather than
   inventing endpoints or scopes."
3. **Defer A1b until after the pilot, as the 2026-09-04 decision states.**
   *Consequence:* the status quo; `FixtureTokenVerifier` and the pilot
   credential path remain in force; the six OQ-A1b rows stay open, and the
   remaining-engineering plan's Wave C item 4 needs a dated supersession note.
4. **Retire the A1b worksheet in favour of a different identity approach.**
   *Consequence:* requires a new decision artifact of its own; the register's
   refusal asymmetry ("a wrong acceptance is an authentication bypass no later
   decision can undo") would have to be restated for whatever replaces it.

## Evidence needed to close

From
[`../plans/2026-08-28-a1b-institutional-sign-in-plan.md`](../plans/2026-08-28-a1b-institutional-sign-in-plan.md)
(stop-gate), a committed decision artifact naming:

> 1. the IdP and environment (a development/test tenant is acceptable and
>    expected — live production SSO is out of scope under standing constraints);
> 2. issuer URL, audience, and JWKS retrieval approach, plus key-rotation
>    policy;
> 3. the full client-flow contract the PKCE implementation needs: client ID,
>    authorization endpoint (or discovery-document policy), registered redirect
>    URI(s), requested scopes, token-exchange model (public client + PKCE
>    assumed; the artifact must confirm), token storage and refresh policy for
>    the browser, and logout / post-logout redirect URI;
> 4. the owner who approved the configuration.

Per row, from
[`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md):
OQ-A1b-001 the exact `iss`; -002 the `aud`; -003 the JWKS retrieval approach;
-004 "Rotation cadence, overlap window, rollover procedure, and the refresh
trigger a cache would honour"; -005 "Which algorithms the tenant signs with, and
how much clock skew is tolerated"; -006 the approver, approval date, and
administrative location.

The register is explicit that these are recorded, not chosen: "An `iss` an agent
produced would be indistinguishable from one a provisioner recorded — the single
failure the worksheet exists to prevent."

## What stays blocked until closure

- Cards **A1–A4** of the A1b plan, per the worksheet's own rule.
- Per [`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md),
  OQ-A1b-006's safe default: "The API imports nothing from
  `smartmatch_providers.jwks`, the module is not re-exported from
  `smartmatch_providers.__init__`, `Settings` carries no `SMARTMATCH_JWKS_*`,
  issuer, or audience field, and no JWKS route exists".
- Per [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
  §4 follow-up list: attaching a bearer obtained from a live IdP, route guards
  as UX, and removal of `sessionStorage["iaw_session"]` fallback identities are
  sequenced after A1b, "not part of Fix #7A".
- Standing, per the same §4 list: "Do not revive `mockLogin`, post a role in a
  body, or store a role asserted by the browser."

## Source links

- [`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md) — OQ-A1b-001 to -006, enforcement table
- [`../decisions/a1b-idp-configuration-worksheet.md`](../decisions/a1b-idp-configuration-worksheet.md) — Part 1 status, fill rule
- [`../decisions/a1b-gcp-console-guide.md`](../decisions/a1b-gcp-console-guide.md) — provisioning guide
- [`../decisions/pilot-login-decision-2026-09-04.md`](../decisions/pilot-login-decision-2026-09-04.md) — pilot deviation, production SSO deferred
- [`../plans/2026-08-28-a1b-institutional-sign-in-plan.md`](../plans/2026-08-28-a1b-institutional-sign-in-plan.md) — stop-gate, current state
- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md) — §2 row 7, §3 Wave C, §4
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — row 6, provisioner
