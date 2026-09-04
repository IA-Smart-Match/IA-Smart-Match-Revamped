# Pilot login — an owner-authorized substitute for institutional sign-in

**Status: DECIDED for the pilot, by the project owner, 2026-09-04.**
**Scope: the synthetic pilot only. Not production authentication.**

## What was decided

For the pilot, **institutional sign-in is removed as the only path**, and a real
login page backed by database credentials takes its place. The owner supplies
the credentials from their end; there is one login per role, and the roles are
designated in the database.

Production SSO is **explicitly deferred until after the pilot**.

This is a scoped, authorized deviation from the plan in
[`../plans/2026-08-28-a1b-institutional-sign-in-plan.md`](../plans/2026-08-28-a1b-institutional-sign-in-plan.md),
recorded here because it is a deviation and not a completion.

## Why

Two things were true at once, and neither was going to resolve itself:

1. The login page said "Institutional sign-in is not connected yet" and accepted
   no input, because A1b's identity-provider worksheet
   ([`a1b-idp-configuration-worksheet.md`](a1b-idp-configuration-worksheet.md))
   is unfilled — there is no issuer, no audience, no JWKS URI, and no client id,
   and none of those may be invented.
2. The coordinator portal rendered a banner saying it was unavailable until the
   API provided an authenticated account-to-portal mapping.

So nobody could sign in, and if they could, no portal would open. A pilot that
cannot be signed into cannot be piloted. The owner's decision unblocks the
demonstration without waiting on an institutional process that has not started.

## What this decision does **not** do

* **It does not close A1b, A0, or A1.** A1b remains blocked on the same thing it
  was blocked on: an identity provider nobody has configured. This document is
  not a substitute for that configuration and must not be read as progress
  toward it.
* **It does not wire the JWKS verifier.** The verifier core landed in PR #27 and
  stays unwired. `smartmatch_providers.jwks` is not called by the login path, by
  `get_current_principal`, or by anything else this change touches.
* **It invents no IdP identifiers.** No issuer, audience, JWKS URI, or client id
  appears anywhere in this work. The worksheet stays unfilled.
* **It is not the archived caller-selected identity endpoint.** That route
  (MM-A01, stakeholder Fix #7) let the *caller choose an identity*. This one
  requires a secret only the account holder has.

## The property that does not bend

> **The login form supplies a credential. It never supplies a role, a tenant, or
> a unit.**

Authentication resolves an `external_subject`, and stops. Authorization still
reads `membership` rows written by an administrator, and `smartmatch_authz`
still decides every operation deny-by-default. Concretely:

* `LoginRequest` sets `extra="forbid"`, so a body carrying `role`, `tenant_id`,
  or `unit_path` is **rejected with a 422** rather than accepted and ignored.
  Rejection is the stronger of the two readings: an ignored field is one careless
  edit away from being an honoured one.
* The session token is 32 bytes of randomness with **no claims in it at all**.
  There is nothing in it to forge because there is nothing in it to read.
* `GET /v1/me` remains the single source of the principal and its roles, exactly
  as it was before anyone could sign in. Nothing about identity moved into the
  browser.
* Roles are written by an operator tool (`tools/seed_pilot_logins.py`) into
  `membership`, never by a request. There is no endpoint in this API that sets a
  password or grants a role.

This preserves what PR #10 and PR #32 established, and a login that let the
browser assert a role would have undone both.

## How credentials are handled

**Where they come from.** Environment variables the owner fills in a gitignored
`.env`. No credential is committed, and none has a default:

```
SMARTMATCH_PILOT_COORDINATOR_EMAIL / SMARTMATCH_PILOT_COORDINATOR_PASSWORD
SMARTMATCH_PILOT_STUDENT_EMAIL     / SMARTMATCH_PILOT_STUDENT_PASSWORD
SMARTMATCH_PILOT_ADMIN_EMAIL       / SMARTMATCH_PILOT_ADMIN_PASSWORD
SMARTMATCH_PILOT_VOLUNTEER_EMAIL   / SMARTMATCH_PILOT_VOLUNTEER_PASSWORD
```

A role whose pair is unset is **not created**, and the seed says so by name. It
does not invent a default password and does not skip silently. Setting only one
half of a pair is an error, not a half-configured login.

`student` is worth naming individually: the rewards catalog and redemption
routes are gated on the `student` role alone, so without that pair no login in
the system can demonstrate rewards.

**How they are stored.** PBKDF2-HMAC-SHA256 (`hashlib.pbkdf2_hmac`, standard
library, no new dependency), 600,000 iterations, a 16-byte per-user random salt
generated at run time. The algorithm, iteration count, and salt are stored beside
the digest, so the count can be raised later without invalidating existing rows
and so a row written under an unrecognised scheme is refused rather than
misread. Comparison is `hmac.compare_digest`. There is no plaintext column and
no reversible one.

A memory-hard KDF (scrypt, Argon2) would be the better choice for a real
credential store. Adopting one is part of standing up production authentication,
not part of a stand-in that is meant to be switched off.

**Sessions.** An opaque random token, stored server-side as a SHA-256 hash —
the token itself is written nowhere, so a database dump does not contain live
credentials. Twelve-hour expiry, checked in the query. Log-out sets `revoked_at`
rather than deleting the row, so "this session was deliberately ended" survives
as a fact.

**Brute force.** The login route charges a fixed-window counter keyed on the
client address as its first statement, committed immediately (ADR-0015's
ordering applied to a route that precedes authentication). Every failure that is
not a suspension returns one code and one message, so the route cannot be used
to discover which addresses exist.

## Known limitations, stated rather than discovered later

* **A timing difference remains** between an unknown address and a wrong
  password: the KDF runs only when a stored credential exists. Removing it means
  deriving a key against a manufactured credential, and a fabricated row is a
  worse thing to have in the code than a measurable difference in how fast a 401
  comes back.
* **Rotating a password does not revoke existing sessions.** Re-running the seed
  replaces the digest; sessions issued earlier keep working until they expire.
  Revoking them is a manual operator action this pilot does not automate.
* **No password reset, no sign-up, no lockout.** Credentials are issued and
  rotated out of band by the owner.
* **A malformed login body is not charged quota.** FastAPI answers it with a 422
  before the handler runs. Such a request carries no well-formed email and
  password, so it cannot be a credential guess.

## Before this may be used for anything real

All of the following, not a subset:

1. **A real identity provider.** A1b configured, the worksheet filled with real
   values, and `smartmatch_providers.jwks` wired into `get_current_principal`.
2. **This path disabled or gated.** The pilot login must be switched off, or
   fenced behind an edition check the way `dev_principals` already is
   (`Settings._validate_isolation` refuses it outside `edition=dev`). Shipping
   both paths at once means the weaker one is the one that gets attacked.
3. **Every pilot credential rotated and the accounts removed.** The pilot
   passwords were chosen for a demonstration, shared out of band, and typed into
   a stack running `SMARTMATCH_EDITION=dev`. None of them may survive into an
   environment holding real data.
4. **A memory-hard KDF**, if any credential store is kept at all.
5. **A security review of the session lifecycle** — rotation on privilege
   change, revocation on password change, and idle timeout, none of which this
   pilot implements.

Until every one of those is done, this is a demonstration mechanism. Nothing in
this repository should be read as a production-readiness claim, and this
document is not one.

## Related

* [`../plans/2026-08-28-a1b-institutional-sign-in-plan.md`](../plans/2026-08-28-a1b-institutional-sign-in-plan.md)
  — the plan this deviates from. Still the record of what A1b requires, and
  still open: this decision closes none of A0, A1, or A1b.
* [`a1b-idp-configuration-worksheet.md`](a1b-idp-configuration-worksheet.md) —
  still unfilled, deliberately.
* [`pilot-decisions.md`](pilot-decisions.md) — the tentative-decision register.
  This decision is *not* filed there: it is an owner decision rather than an
  interim development one, and it is recorded separately for that reason.
