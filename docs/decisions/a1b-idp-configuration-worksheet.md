# A1b — institutional IdP configuration worksheet

**Status:** **TENANT PROCURED — WORKSHEET UNFILLED.** Google Cloud IdP
dev/test tenant exists (confirmed 2026-09-02). Part 1 configuration fields
below remain blank until the provisioner commits values.
**Ratification status (31 August 2026):** **EXTERNAL DEPENDENCY** until Part 1
is complete. Session approver Danny Tran (@dangt) recorded P2 as **in scope;
proceed** — see `docs/decisions/2026-08-31-session-ratification.md`.
**Created by:** plan P2 card A0 (`docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md`).
**Date:** 2026-08-28 · **Branch:** `plan/a1b-sign-in`

> This file exists so a human owner can record the identity-provider
> configuration that plan P2's stop-gate requires. **It is not a decision
> artifact and does not satisfy the stop-gate.** Cards A1–A4 remain blocked
> until every field below is filled in and approved by a named owner, and the
> completed artifact is committed. No agent may fill these values in.
>
> Standing constraints still apply: a development/test tenant is expected;
> live production SSO is out of scope. No live providers, no production
> credentials, nothing deployed.

**Fill status (2026-09-03).** Two cells in §1.1 now carry values. Neither is a
new decision: both are *transcriptions* of facts already committed elsewhere in
this repository, and each cites the file and line it was copied from. Every
other cell in Part 1 is marked **OUTSTANDING — EXTERNAL DEPENDENCY**, because
no committed material in this repository states it. The rule above stands
unchanged for all of them: an issuer URL, an audience, a JWKS URI, a client ID,
or a redirect URI that an agent produced would be indistinguishable from one a
provisioner recorded, and that is the single failure this worksheet exists to
prevent. They stay blank until the provisioner commits them.

---

## Part 1 — Fields the stop-gate requires

### 1.1 Provider and environment

| Field | Value |
|---|---|
| IdP product / vendor | **Google Cloud IdP (Google Identity Platform).** Transcribed, not decided: `docs/decisions/2026-08-31-session-ratification.md` line 63 ("Google Cloud IdP dev/test **tenant exists** (2026-09-02)"), corroborated by `docs/plans/remaining-foundation-r1-work.md` line 100 ("Live Google Identity Platform verifier") and `python/smartmatch_providers/smartmatch_providers/identity.py` lines 3–4. This is the product name only; it configures nothing. |
| Environment (development / test tenant) | **Development / test tenant; confirmed to exist 2026-09-02.** Transcribed from this file's status header (lines 3–5) and `docs/decisions/2026-08-31-session-ratification.md` line 63. Live production SSO stays out of scope per the standing constraints above. |
| Tenant or directory identifier | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository names the project, tenant, or directory. |

### 1.2 Token verification (card A1 needs these)

| Field | Value |
|---|---|
| Issuer URL (`iss`) | **OUTSTANDING — EXTERNAL DEPENDENCY.** Consumed as `SMARTMATCH_JWKS_ISSUER`; no default exists in the tree. |
| Audience (`aud`) | **OUTSTANDING — EXTERNAL DEPENDENCY.** Consumed as `SMARTMATCH_JWKS_AUDIENCE`; no default exists in the tree. |
| JWKS retrieval approach (discovery document URL, or static JWKS URI) | **OUTSTANDING — EXTERNAL DEPENDENCY.** Consumed as `SMARTMATCH_JWKS_URI`; no default exists in the tree, and no fetching implementation ships (see Part 4). |
| JWKS cache TTL / refresh trigger | **OUTSTANDING — EXTERNAL DEPENDENCY.** Deliberately not defaulted: caching lives behind the `JwksSource` port, which has no fetching implementation until this value is recorded. |
| Signing algorithms accepted (e.g. RS256) | **OUTSTANDING — EXTERNAL DEPENDENCY** for the tenant's actual answer. The verifier's shipped default is the single algorithm `RS256`, overridable by `SMARTMATCH_JWKS_ALGORITHMS`; unsigned (`none`) and symmetric (`HS*`) algorithms are refused unconditionally and cannot be configured back on. |
| Key-rotation policy (cadence, overlap window, rollover procedure) | **OUTSTANDING — EXTERNAL DEPENDENCY.** The verifier's behaviour on an unknown `kid` is fixed regardless: reject. Making the next attempt succeed is a refreshing `JwksSource`'s job, which this policy defines. |
| Clock-skew tolerance | **OUTSTANDING — EXTERNAL DEPENDENCY** for the tenant's actual answer. The verifier's shipped default is 60 seconds, overridable by `SMARTMATCH_JWKS_LEEWAY_SECONDS`. |

### 1.3 Client flow (card A2 needs these; issuer/audience/JWKS alone is NOT enough)

| Field | Value |
|---|---|
| Client ID | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Public client + PKCE? (confirm yes/no) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Token-exchange model (if not public+PKCE, describe) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Authorization endpoint, or "use discovery document at &lt;URL&gt;" | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Token endpoint (or discovery) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Registered redirect URI(s) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Requested scopes | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Browser token storage policy | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Refresh policy (refresh tokens? silent renew? re-auth only?) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Session lifetime | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Logout endpoint | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Post-logout redirect URI | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |

### 1.4 Approval

| Field | Value |
|---|---|
| Owner who approved this configuration | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Approval date | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Where the configuration is administered | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |

---

## Part 2 — Fallback-identity audit (card A0 output)

Ripgrep of `apps/web/legacy-frontend/src/` on 2026-08-28, branch
`plan/a1b-sign-in`. This is the **exact fence for card A3**.

### 2.1 Verdicts on the three claims plan P2 asserted

| Claim in plan P2 | Verdict |
|---|---|
| "inventoried the readers (**15 files** …)" | **HOLDS, with a labelling nuance.** Exactly **15** files perform a `getItem("iaw_session")` read, matching the count. The enumerated list, however, has **16** entries, because it also includes `pages/Dashboard.tsx` — which the plan itself annotates "(remove-only)" and which contains a `removeItem` and no read. So: 15 readers, 16 files touching the key, no file missing and none spurious. A0 recommends A3 state the fence as **16 files** to avoid the ambiguity. |
| "**no `setItem` writer exists** — the reads can only ever yield the fallbacks" | **HOLDS.** `rg -n "setItem" src/` returns **zero** matches; `rg -n "localStorage" src/` also returns zero. Nothing in the frontend ever writes `iaw_session`. Every read therefore resolves to `{}` and every identity below is the hard-coded fallback. |
| "`fetchMe()` is defined in `api.ts` but **never called** from any component" | **HOLDS.** `rg -n "fetchMe" src/` matches only the definition at `src/lib/api.ts:1652`. (The other hits are `fetchMetricDrillDown`, a different function, matched as a substring.) Card A2 would introduce its first caller. |

**Additional finding not in the plan:** the bearer key `api.ts` reads at
`src/lib/api.ts:328` — `sessionStorage["smartmatch_bearer_token"]` — likewise
has **no writer** anywhere in `src/`. Today it can only ever be supplied by the
`VITE_SMARTMATCH_BEARER_TOKEN` build-time env var (`src/lib/api.ts:325`). Card
A2 must introduce the writer.

### 2.2 `sessionStorage["iaw_session"]` — every occurrence (16 files, 19 sites)

| File (under `apps/web/legacy-frontend/`) | Line | Kind |
|---|---|---|
| `src/app/components/StudentLayout.tsx` | 30 | read (`getItem`) |
| `src/app/components/StudentLayout.tsx` | 50 | write-clear (`removeItem`, sign-out) |
| `src/app/components/CoordinatorPortalLayout.tsx` | 28 | read |
| `src/app/components/CoordinatorPortalLayout.tsx` | 48 | write-clear |
| `src/app/components/VolunteerPortalLayout.tsx` | 26 | read |
| `src/app/components/VolunteerPortalLayout.tsx` | 46 | write-clear |
| `src/app/pages/Dashboard.tsx` | 273 | write-clear (remove-only; **no read**) |
| `src/app/pages/student/StudentHome.tsx` | 21 | read |
| `src/app/pages/student/StudentEvents.tsx` | 10 | read |
| `src/app/pages/student/StudentHistory.tsx` | 15 | read |
| `src/app/pages/student/StudentConnect.tsx` | 30 | read |
| `src/app/pages/student/StudentRewards.tsx` | 20 | read |
| `src/app/pages/coordinator/CoordinatorHome.tsx` | 20 | read |
| `src/app/pages/coordinator/CoordinatorEvents.tsx` | 11 | read |
| `src/app/pages/coordinator/CoordinatorOutreach.tsx` | 11 | read |
| `src/app/pages/coordinator/CoordinatorMeetings.tsx` | 9 | read |
| `src/app/pages/volunteer/VolunteerHome.tsx` | 15 | read |
| `src/app/pages/volunteer/VolunteerAssignments.tsx` | 13 | read |
| `src/app/pages/volunteer/VolunteerProfile.tsx` | 9 | read |

Totals: 15 `getItem` reads across 15 files, plus 4 `removeItem` clears across 4
files (the three portal layouts and `Dashboard.tsx`). 16 distinct files.

### 2.3 Fallback identity literals — every occurrence (12 sites, 12 files)

| File | Line | Literal | Shape |
|---|---|---|---|
| `src/app/pages/student/StudentHome.tsx` | 31 | `stu-001` | `?? "stu-001"` on `student_id` |
| `src/app/pages/student/StudentEvents.tsx` | 32 | `stu-001` | `?? "stu-001"` |
| `src/app/pages/student/StudentHistory.tsx` | 34 | `stu-001` | `?? "stu-001"` |
| `src/app/pages/student/StudentRewards.tsx` | 43 | `stu-001` | `?? "stu-001"` |
| `src/app/pages/student/StudentConnect.tsx` | 44 | `stu-001` | ternary fallback (blank/`"undefined"`-guarding variant) |
| `src/app/pages/coordinator/CoordinatorHome.tsx` | 37 | `coord-001` | `?? "coord-001"` on `coordinator_id` |
| `src/app/pages/coordinator/CoordinatorEvents.tsx` | 35 | `coord-001` | `?? "coord-001"` |
| `src/app/pages/coordinator/CoordinatorOutreach.tsx` | 35 | `coord-001` | `?? "coord-001"` |
| `src/app/pages/coordinator/CoordinatorMeetings.tsx` | 29 | `coord-001` | `?? "coord-001"` |
| `src/app/pages/volunteer/VolunteerHome.tsx` | 26 | `shana-demarinis` | `?? "shana-demarinis"` on `volunteer_id` |
| `src/app/pages/volunteer/VolunteerAssignments.tsx` | 38 | `shana-demarinis` | `?? "shana-demarinis"` |
| `src/app/pages/volunteer/VolunteerProfile.tsx` | 26 | `shana-demarinis` | `?? "shana-demarinis"` |

The three portal layouts (`StudentLayout`, `CoordinatorPortalLayout`,
`VolunteerPortalLayout`) read `iaw_session` for display but carry **no** id
literal; they are in the A3 fence for the read + sign-out path only.
`Dashboard.tsx` carries neither a read nor a literal — remove-only, as plan P2
already noted.

### 2.4 Card A3 fence, restated exactly

The 16 files in §2.2. Card A3's test (`iaw_session`, `stu-001`, `coord-001`,
`shana-demarinis` appear nowhere in `src/`) must pass against all 19 sites in
§2.2 and all 12 sites in §2.3.

---

## Part 3 — Blockers recorded at A0 time

1. **Stop-gate not satisfied.** `docs/decisions/` contains only
   `metrics-authorization-decision-draft.md` and `pilot-decisions.md`. Neither
   names an IdP. Cards A1–A4 did not run. Status: **IdP decision artifact
   missing.**
2. **Cross-plan file conflict on the A3 fence.** `src/app/pages/Dashboard.tsx`
   is currently owned by a concurrently running plan. Card A3 touches it (the
   `removeItem` at line 273). A3 must either be sequenced after that plan lands
   or negotiate that one line explicitly.
3. Card A2's fence includes `src/lib/api.ts`, which is also concurrently owned.
   Same sequencing note applies.

---

## Part 4 — What card A1 landed while Part 1 is outstanding (2026-09-03)

Card A1's verifier is in the tree, switched off. It exists now so that the day
Part 1 is filled in, the remaining work is configuration and a signature
backend — not design, and not code written under time pressure against a live
tenant.

**Module.** `python/smartmatch_providers/smartmatch_providers/identity_jwks.py`,
tested by `tests/unit/test_identity_jwks_verifier.py` (68 cases, all offline).

**Feature flag.** `SMARTMATCH_JWKS_VERIFIER_ENABLED`, default **off** — unset,
blank, `false`, `0`, `no`, `off`, and any unrecognised value all mean off, so a
typo cannot switch live verification on. With the flag off,
`build_jwks_token_verifier(fallback)` returns the verifier it was handed,
unchanged and unwrapped; the fixture path that `tests/contract/test_me.py`
exercises is byte-identical.

**Configuration**, read from the environment and validated when the flag is on:
`SMARTMATCH_JWKS_ISSUER`, `SMARTMATCH_JWKS_AUDIENCE`, `SMARTMATCH_JWKS_URI`
(all three required, no defaults), plus optional `SMARTMATCH_JWKS_ALGORITHMS`
and `SMARTMATCH_JWKS_LEEWAY_SECONDS`. Flag on with any required value missing
raises `ProviderConfigurationError` naming every absent variable at once, and
**never** falls back to the fixture: a deployment that believes it checks
signatures and does not is the outcome worth failing a boot to avoid.

**What it verifies**, in this order: the token is a well-formed, size-bounded
three-part JWS; the header's algorithm is not `none`/`HS*`/`dir` (banned
unconditionally, before any backend is consulted), is configured here, and is
supported by the backend; the `kid` resolves to a published key whose own `alg`
agrees with the header; the **signature** verifies — before any claim is read;
then `iss` equals the configured issuer, `aud` matches (string or array), `exp`
is present and not past beyond the leeway, `nbf`/`iat` are not in the future,
and `sub` is a non-blank string. It returns only `VerifiedIdentity(subject,
email)`, and the email only when the issuer set `email_verified`. Any tenant,
role, or membership claim in the token is ignored — that is MM-A01 in a JWT.

**What it deliberately does not do.** It does not fetch: `JwksSource` is a
port, and the only implementation shipped is `StaticJwksSource`, so caching,
TTL, and refresh-on-unknown-`kid` wait on §1.2's blank cells. It ships **no
signature backend** — `requirements/runtime.txt` still carries no asymmetric
primitive (the same S-001/CP-A1B gap the worker records), and with the flag on
and no backend supplied, construction refuses. It runs no browser flow: card
A2's authorization-code/PKCE work is untouched and stays blocked on §1.3. And
it is **not wired in** — the provider registry, API settings, and app bootstrap
are another track's files this session, so selecting it at startup is a
follow-up change of a few lines in
`python/smartmatch_providers/smartmatch_providers/registry.py`,
`services/api/smartmatch_api/config.py`, and the app's lifespan.
