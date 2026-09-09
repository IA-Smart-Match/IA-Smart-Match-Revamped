# A1b live IdP — open questions carried by the JWKS verifier scaffold

**Date:** 2026-09-04 · **Slice:** isolated JWKS/JWT verifier core (plan P2, cards A1–A4)

Every item here is a decision a human has to make that engineering could not
make for them. Each is a Part 1 field of
`docs/decisions/a1b-idp-configuration-worksheet.md` that is still marked
**OUTSTANDING — EXTERNAL DEPENDENCY**, and none of them stopped the scaffold:
`python/smartmatch_providers/smartmatch_providers/jwks.py` takes every trust
anchor as a constructor argument, so the module knows nothing on its own and
the only callers are tests supplying test literals.

The safe default is the same in every case: the API keeps building
`FixtureTokenVerifier` (`smartmatch_providers.registry.build_token_verifier`,
called from `services/api/smartmatch_api/main.py`), and any live issuer is
*refused*, never guessed. A missing decision fails toward nobody being able to
sign in, not toward somebody being trusted on an unverified token. That
asymmetry is the whole policy — a wrong refusal costs a pilot user a login; a
wrong acceptance is an authentication bypass no later decision can undo.

Nothing here is a placeholder that *reports success*. Where a decision is
missing, the code refuses, and it says which decision it is waiting on. No
agent may fill any of these in; the worksheet's own rule stands.

---

## OQ-A1b-001 — the issuer URL (`iss`)

**Question.** Which exact `iss` string does the procured Google Cloud IdP
dev/test tenant put in its tokens?

**Why engineering cannot answer it.** It is a property of a tenant that exists
outside this repository. An `iss` an agent produced would be
indistinguishable from one a provisioner recorded — the single failure the
worksheet exists to prevent.

**Safe default, implemented.** `StaticJWKSTokenVerifier.issuer` is a required
constructor argument with no default, and `_assert_issuer_is_not_live` raises
`ProviderConfigurationError` for any host in `BLOCKED_ISSUER_HOSTS` — which
includes `securetoken.google.com`, `accounts.google.com`, and
`identitytoolkit.googleapis.com`, matched on subdomains too. Pointing the
scaffold at a live issuer is therefore a deliberate edit to that file under a
cleared gate, not a configuration slip. `test_no_live_issuer_is_baked_into_the_module_as_a_value`
holds the blocklist to being a fence rather than a source of defaults.

## OQ-A1b-002 — the audience (`aud`)

**Question.** Which client or resource identifier must appear in `aud`?

**Why engineering cannot answer it.** It is the tenant's client registration,
recorded by whoever administers the tenant.

**Safe default, implemented.** `audience` is a required constructor argument;
an empty one raises `ProviderConfigurationError`. Verification requires an
exact match against `aud` (or membership, when `aud` is a list), so there is no
"accept any audience" mode to fall into.

## OQ-A1b-003 — JWKS retrieval (discovery document URL, or static JWKS URI)

**Question.** Where do the signing keys come from, and over what transport?

**Why engineering cannot answer it.** It is a tenant configuration fact, and
fetching keys is exactly what an uncleared stop-gate must not authorise.

**Safe default, implemented.** The constructor takes a `StaticJWKS` — decoded,
in-memory keys. There is no JWKS URI parameter, no discovery-document
parameter, and no HTTP client in the module;
`test_the_verifier_module_imports_no_network_client` fails the build if one
appears. A key set that is not already in memory cannot be reached.

## OQ-A1b-004 — key-rotation policy and JWKS cache TTL

**Question.** Rotation cadence, overlap window, rollover procedure, and the
refresh trigger a cache would honour.

**Why engineering cannot answer it.** Rotation is the tenant's operational
policy; a cache TTL chosen without it is either a stale-key outage or an
unnecessary fetch rate.

**Safe default, implemented.** No cache exists, because nothing is fetched.
Rotation is handled structurally instead: tokens name their `kid`, `StaticJWKS`
rejects a duplicate `kid` as ambiguous, and a set may hold several keys — so an
overlap window is expressible the moment a real policy exists, without this
module having assumed one.

## OQ-A1b-005 — accepted signing algorithms and clock-skew tolerance

**Question.** Which algorithms the tenant signs with, and how much clock skew
is tolerated on `exp`/`nbf`.

**Why engineering cannot answer it.** Both are tenant facts. The worksheet
lists RS256 only as an example, not as a recorded value.

**Safe default, implemented.** `_ALGORITHM` is `RS256` and is deliberately
*not* configurable — an algorithm the caller can widen is one an attacker can
narrow, and `{"alg": "none"}` is how that goes wrong. `leeway_seconds`
defaults to `0.0`, refuses a negative value, and is documented as a test
convenience that asserts nothing about any tenant.

## OQ-A1b-006 — who signs off, and where the configuration is administered

**Question.** The named owner who approves the completed worksheet, the
approval date, and the administrative location of the configuration
(worksheet §1.4).

**Why engineering cannot answer it.** An approval is an accountability claim
about a person. Recording one on their behalf would fabricate it.

**Safe default, implemented.** Cards A1–A4 stay blocked. The API imports
nothing from `smartmatch_providers.jwks`, the module is not re-exported from
`smartmatch_providers.__init__`, `Settings` carries no `SMARTMATCH_JWKS_*`,
issuer, or audience field, and no JWKS route exists — each asserted by a test
in `tests/unit/test_static_jwks_verifier.py`, so clearing the gate has to be a
visible, deliberate change rather than a drift.

---

## Where these are enforced

| Artefact | What it guarantees |
|---|---|
| `python/smartmatch_providers/smartmatch_providers/jwks.py` | Static keys only, live issuers refused at construction, RS256 fixed, `sub`/`email` only |
| `tests/unit/test_static_jwks_verifier.py` | Wrong `alg`/`kid`/`exp`/`iss`/`aud` refused; no network import; not wired into the API; no `SMARTMATCH_JWKS_*` setting |
| `smartmatch_providers.registry.build_token_verifier` | Live Google Identity Platform verifier raises `ProviderConfigurationError`; `FixtureTokenVerifier` remains what the API builds |
| `docs/decisions/a1b-idp-configuration-worksheet.md` | The place a human records the answers. It stays unfilled until a provisioner commits them. |
