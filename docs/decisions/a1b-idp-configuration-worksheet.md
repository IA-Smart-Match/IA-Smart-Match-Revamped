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
| Issuer URL (`iss`) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Audience (`aud`) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| JWKS retrieval approach (discovery document URL, or static JWKS URI) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it, and no JWKS implementation is committed. |
| JWKS cache TTL / refresh trigger | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Signing algorithms accepted (e.g. RS256) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states the tenant's accepted algorithms. |
| Key-rotation policy (cadence, overlap window, rollover procedure) | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |
| Clock-skew tolerance | **OUTSTANDING — EXTERNAL DEPENDENCY.** No committed material in this repository states it. |

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

## Part 4 — Card A1 remains blocked (2026-09-03)

No institutional JWKS verifier implementation is committed. The runtime still
uses the existing fixture verifier and accepts only registered fixture tokens.
Card A1 remains blocked until Part 1 records and a named owner approves the
issuer, audience, JWKS retrieval and rotation policy, accepted algorithms,
clock-skew tolerance, client-flow contract, and configuration ownership.
