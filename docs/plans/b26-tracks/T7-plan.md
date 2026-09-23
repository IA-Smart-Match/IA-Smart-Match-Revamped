# B26 T7 — `VolunteerProfile` close-out (Q3 = a)

**Next action:** write the two failing Vitest files in §3 and commit them red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §1 fact 1,
§6 row `VolunteerProfile.tsx`, §7 row 12, §8 row T7. Owner decision Q3 = (a) is final.
Estimate 0.5 day. No dependency. No backend route, no migration.

## 1. Files to touch (all under `apps/web/legacy-frontend/`)

| File | Today (file:line) | Change |
|---|---|---|
| `src/app/pages/volunteer/VolunteerProfile.tsx` | `:17` imports `PortalDatasetUnavailable`; `:48-53` the dead panel, `endpoints={["/api/portals/volunteers/{id}"]}` at `:51`; `:1-15` header comment still describes the legacy read | Remove the panel and its import. Render `PortalIdentityCard` plus an Organization link. Rewrite the header comment. |
| `src/lib/api.ts` | `:1853-1866` `interface VolunteerProfile`; `:1868` `AssignmentStage`; `:1879-1890` `VolunteerAssignment`; `:1892-1899` `fetchVolunteerProfile` (URL `${API_BASE}/portals/volunteers/…` at `:1897`, `API_BASE = "/api"` at `:1694`); `:1901-1912` `fetchVolunteerAssignments` (URL at `:1909`) | Delete all five. No caller in `src/` (grep: only `tests/portalSubject.test.ts`). `stripG1ScoreFields` stays — `:1195` still uses it. |
| `src/app/pages/volunteer/VolunteerAssignments.tsx` | 56 lines; unrouted — no import in `routes.tsx`, `/volunteer-portal/assignments` redirects to `/volunteer-portal` (`src/app/legacyRedirects.ts:75`); `:51` names `/api/portals/volunteers/{id}/assignments` | Delete (orphan). |
| `tests/portalSubject.test.ts` | `:15-16` imports, `:49-50` list entries for the two deleted functions | Remove those 4 lines. |
| `src/app/pages/volunteer/VolunteerProfile.test.tsx` | — | New (§3). |
| `src/app/legacyPortalVolunteers.guard.test.tsx` | — | New source guard (§3). |

Data already in the frontend — no new fetch needed:

- `GET /v1/me` → `useAuthenticatedPrincipal()` (`src/app/hooks/useSession.tsx:131`), type `MeResponse` (`src/lib/api.ts:1926`: `email`, `memberships`).
- `GET /v1/me/portals` → `usePortalAccess()` (`src/app/hooks/usePortalAccess.tsx:145`) + `grantedPortal(state, "volunteer")` (`src/app/components/PortalGate.tsx:145`), type `PortalDescriptor` (`src/lib/api.ts:2019`: `role`, `roles`, `org_unit_path`, `units`).
- `PortalIdentityCard` (`src/app/components/PortalContent.tsx:57-130`) already renders exactly email, role, org unit and granted units from those two. `VolunteerHome.tsx:294` uses it.

Organization route: `path: "organization"` under `volunteer-portal` (`src/app/routes.tsx:419`) → `/volunteer-portal/organization`; nav entry `VolunteerPortalLayout.tsx:43`; precedent link `VolunteerHome.tsx:107`.

## 2. Contract

The page renders, in order:

1. `<h1>Profile</h1>` and one line "Your Event Host record." (kept from `:41-42`).
2. `<PortalIdentityCard me={principal} grant={grant} />` — fields and labels as the card has them: "Role assigned by the server" (`grant.role`), "Org unit" (`grant.org_unit_path`), "Signed in as" (`me.email`), "Units this grant covers" (`grant.units[].display_name`, or the card's no-unit sentence).
3. A section "Your organization": one sentence ("Your organization is described on its own page.") and a React Router `<Link to="/volunteer-portal/organization">Go to Organization</Link>`.

Nothing else. No `PortalDatasetUnavailable`, no `/api/portals/*` string, no editable field.
Headings: the card carries its own `<h1>` (display name, `PortalContent.tsx:65`), as on
`VolunteerHome.tsx:209`+`:294`; the page keeps that precedent and does not edit the shared card.

States — owned by the shell, not re-implemented on the page:

| State | Who renders it | Page behaviour |
|---|---|---|
| loading (`/v1/me` or `/v1/me/portals` in flight) | `VolunteerPortalLayout.tsx:67-68` `SessionGate` / `:77-78` `PortalGate` | never mounted; if mounted with `grant === null`, returns `null` (unchanged `:34-36`) |
| error (`/v1/me/portals` unreachable) | `PortalGate` with retry | never mounted |
| denied (no `volunteer` grant) | `PortalGate` | returns `null` |
| ready | page | items 1-3 |

Hooks: `useAuthenticatedPrincipal` + `usePortalAccess`/`grantedPortal` only. `useScopedQuery`
is **not** used: the page issues no request of its own. Both identity reads are the
per-page-load contexts every shell shares; adding a query would duplicate
`/v1/me/portals` for no new data. Principal isolation is inherited from
`PrincipalIdentityTracker`, which clears the cache on identity change.

## 3. TDD test list (Vitest, `src/**/*.test.tsx`, run in CI by `npm run test:components`)

`src/app/pages/volunteer/VolunteerProfile.test.tsx` — mocks `../../hooks/useSession` and
`../../hooks/usePortalAccess` as in `CoordinatorRedemptionQueue.test.tsx:20-54`; wraps in
`MemoryRouter`; stubs `fetch` to fail the test on any call.

1. `renders the host's own record: email, role, org unit and units`
2. `renders the no-unit sentence when the grant covers no unit`
3. `links to /volunteer-portal/organization with the name "Go to Organization"`
4. `does not render the legacy volunteer-profile panel` — no text "Your volunteer profile", no `/api/portals` text
5. `renders nothing when the volunteer grant is not resolved` — `usePortalAccess` → `{ status: "loading" }`
6. `makes no network request` — `fetch` call count 0

`src/app/legacyPortalVolunteers.guard.test.tsx` — reads files with `node:fs` (`import.meta.url`):

7. `no source file under src/ requests portals/volunteers` — walk `src/**/*.{ts,tsx}` excluding `*.test.tsx`; fail on `/portals\/volunteers/` in a `requestJson(`/`fetch(` argument or template (see C1 for scope)
8. `VolunteerProfile.tsx contains no /api/portals string and no PortalDatasetUnavailable`

Existing node tests still to pass locally (`node --test tests/portalSubject.test.ts tests/volunteerLinks.test.ts`): not run in CI (`verify.yml` runs only `test:components`), so run both by hand.

## 4. Commit milestones

1. `test: T7 failing tests for Host profile close-out` — §3 tests 1-8; 3, 4, 7 and 8 red.
2. `feat: Host profile shows own record and Organization link` — page, `api.ts` deletions, orphan page deleted, `portalSubject.test.ts` trimmed; `npx tsc --noEmit -p .` clean.
3. `docs: T7 close-out notes` — rewritten header comment in `VolunteerProfile.tsx`; mark §6 row T7 done in the parent plan.

## 5. Out of scope

- The Home assignments panel `VolunteerHome.tsx:299-302` (label `/api/portals/volunteers/{id}/assignments`). It is a different dataset; Q3 covers Profile only.
- Showing the organization's name or status on Profile (Home already does, over `GET …/host/organization`).
- Mapping `grant.role` to "Event Host" inside the shared `PortalIdentityCard` (see C2).
- Any Speaker portal, availability, or ELI work (T1-T8d).
- Coordinator / student `/api/portals/*` functions in `api.ts:1740-1837`.

## 6. Contradictions with options

**C1 — guard scope.** The task brief says "no `/api/portals/volunteers` string remains in src"; parent §7 row 12 says "no `/api/portals/volunteers` **call** remains". After T7 one string remains that is a label, not a call: `VolunteerHome.tsx:301`.
- (a) **Recommended:** guard = no request (`requestJson`/`fetch` argument) to `portals/volunteers` anywhere in `src/`, plus test 8 on `VolunteerProfile.tsx`. Matches the parent's wording; Home untouched.
- (b) Strict string guard: also remove the Home assignments panel. Changes Home, which Q3 did not decide.

**C2 — role wording.** Parent §1 fact 1 says the user is an "Event Host", but `PortalIdentityCard:77` prints the stored role `volunteer`.
- (a) **Recommended:** keep the card as is in T7 (shared by 3 homes; the header line already says "Event Host").
- (b) Card renders `visibleRoleLabel(grant.role) ?? grant.role` (`src/lib/roleLabels.ts:126`, precedent `CoordinatorRedemptionQueue.tsx:120`). Changes coordinator and student homes too — separate small PR.

**C3 — parent §6 says "All reads use `useScopedQuery`".** T7 has no read of its own (§2). No option needed; recorded so a reviewer does not flag it.
