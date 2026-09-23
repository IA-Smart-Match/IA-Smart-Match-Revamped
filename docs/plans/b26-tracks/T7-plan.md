# B26 T7 — `VolunteerProfile` close-out (Q3 = a)

**Next action:** write the failing Vitest files in §3 and commit them red.

**Revision 2 (2026-09-22):** Codex round 1 changes and orchestrator guard ruling applied.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` — §1 fact 1,
§6 row "`VolunteerProfile.tsx` | T7", §7 row 12, §8 row T7. Owner decision Q3 = (a) is final.
Estimate 0.5 day. No dependency. No backend route, no migration.

## 1. Files to touch

Frontend paths are under `apps/web/legacy-frontend/`.

| File | Today (file:line) | Change |
|---|---|---|
| `src/app/pages/volunteer/VolunteerProfile.tsx` | `:17` imports `PortalDatasetUnavailable`; `:48-53` the dead panel, `endpoints={["/api/portals/volunteers/{id}"]}` at `:51`; `:1-15` header comment describes the legacy read | Remove the panel and import. Render §2. Rewrite the header comment. |
| `src/lib/api.ts` | `:1853-1866` `interface VolunteerProfile`; `:1868` `AssignmentStage`; `:1879-1890` `VolunteerAssignment`; `:1892-1899` `fetchVolunteerProfile` (URL `${API_BASE}/portals/volunteers/…` at `:1897`, `API_BASE = "/api"` at `:1694`); `:1901-1912` `fetchVolunteerAssignments` (URL at `:1909`) | Delete all five. No caller in `src/`; only `tests/portalSubject.test.ts`. `stripG1ScoreFields` stays (`:1195`). |
| `src/app/pages/volunteer/VolunteerAssignments.tsx` | 56 lines; unrouted (no import in `routes.tsx`; `/volunteer-portal/assignments` redirects to `/volunteer-portal`, `src/app/legacyRedirects.ts:75`); `:51` names `/api/portals/volunteers/{id}/assignments` | Delete (orphan). |
| `tests/portalSubject.test.ts` | `:15-16` imports, `:49-50` list entries for the two deleted functions | Remove those 4 lines. |
| `tests/unit/test_frontend_auth_contract.py` (repo root) | `:170` `PORTAL_PAGES` entry `app/pages/volunteer/VolunteerAssignments.tsx`; `:145` comment names the demoted `VolunteerAssignments`; the loops at `:328-329` and `:351-352` read every `PORTAL_PAGES` file, so they fail on a deleted file. CI runs it (`verify.yml:117`, `pytest tests/ -m "not e2e"`) | Remove the `:170` entry. Reword `:145` to name only `VolunteerConfirmedSpeaker` and record that `VolunteerAssignments` was deleted in B26 T7. Run `pytest tests/unit/test_frontend_auth_contract.py` only. |
| `src/app/pages/volunteer/VolunteerProfile.test.tsx` | — | New (§3 tests 1-6). |
| `src/app/legacyPortalVolunteers.guard.test.tsx` | — | New source guard (§3 tests 7-9). |

Data already in the frontend — no new fetch:

- `GET /v1/me` → `useAuthenticatedPrincipal()` (`src/app/hooks/useSession.tsx:131`), type `MeResponse` (`src/lib/api.ts:1926`: `email`, `memberships`).
- `GET /v1/me/portals` → `usePortalAccess()` (`src/app/hooks/usePortalAccess.tsx:145`) + `grantedPortal(state, "volunteer")` (`src/app/components/PortalGate.tsx:145`), type `PortalDescriptor` (`src/lib/api.ts:2019`: `role`, `roles`, `org_unit_path`, `units`).
- `PortalIdentityCard` (`src/app/components/PortalContent.tsx:57-130`) includes email, role, org unit and granted units from those two. `VolunteerHome.tsx:294` uses it.

Organization route: `path: "organization"` under `volunteer-portal` (`src/app/routes.tsx:419`) → `/volunteer-portal/organization`; nav entry `VolunteerPortalLayout.tsx:43`; precedent link `VolunteerHome.tsx:107`.

## 2. Contract

The page renders, in order:

1. `<p>` "Profile" styled as the page title (same classes as today's `:41`, not a heading) and `<p>` "Your Event Host record." (`:42`).
2. `<PortalIdentityCard me={principal} grant={grant} />` — its `<h1>` is the display name (`PortalContent.tsx:65`), the page's only `h1` (`apps/web/DESIGN.md:297`). Labels as the card has them: "Role assigned by the server" (`grant.role`), "Org unit" (`grant.org_unit_path`), "Signed in as" (`me.email`), "Units this grant covers" (`grant.units[].display_name`, or the card's no-unit sentence).
3. `<section>` with `<h2>Your organization</h2>`, one sentence ("Your organization is described on its own page.") and `<Link to="/volunteer-portal/organization">Go to Organization</Link>`. The link carries `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2` (CPP Green `--ring`, `src/styles/theme.css:32`; `DESIGN.md:296`).

Nothing else: no `PortalDatasetUnavailable`, no `/api/portals/*` string, no editable field.
Heading outline: `h1` (card) → `h2` "Your organization". The shared card is not edited.

States — owned by the shell, not re-implemented on the page:

| State | Who renders it | Page behaviour |
|---|---|---|
| loading (`/v1/me` or `/v1/me/portals` in flight) | `VolunteerPortalLayout.tsx:67-68` `SessionGate` / `:77-78` `PortalGate` | not mounted; if mounted with `grant === null`, returns `null` (unchanged `:34-36`) |
| error (`/v1/me/portals` unreachable) | `PortalGate` with retry | not mounted |
| denied (no `volunteer` grant) | `PortalGate` | returns `null` |
| ready | page | items 1-3 |

Hooks: `useAuthenticatedPrincipal` + `usePortalAccess`/`grantedPortal` only. `useScopedQuery`
is not used: the page issues no request. It reads the gated session and portal-access
contexts directly and owns no query cache, so there is no page-level cache to isolate.
Which principal it shows is exactly what those two contexts hold.

## 3. TDD test list (Vitest, `src/**/*.test.tsx`, CI via `npm run test:components`, `verify.yml:276`)

`src/app/pages/volunteer/VolunteerProfile.test.tsx` — mocks `../../hooks/useSession` and
`../../hooks/usePortalAccess` as in `CoordinatorRedemptionQueue.test.tsx:20-54`; wraps in
`MemoryRouter`; stubs `fetch` and fails on any call.

1. `renders the host's own record: email, role, org unit and units`
2. `heading outline is one h1 (display name) then h2 "Your organization"` — `getAllByRole("heading")` levels `[1, 2]`; no heading named "Profile"
3. `links to /volunteer-portal/organization with the name "Go to Organization"`
4. `organization link is keyboard-focusable with the visible focus ring` — it is an `<a href="/volunteer-portal/organization">` with no negative `tabIndex`; `link.focus()` makes `document.activeElement === link`; `className` contains `focus-visible:ring-2` and `focus-visible:ring-ring`. (No `@testing-library/user-event` or `jest-dom` in `package.json`; do not add either.)
5. `does not render the legacy volunteer-profile panel` — no "Your volunteer profile", no `/api/portals` text
6. `renders nothing and makes no request when the grant is not resolved` — `usePortalAccess` → `{ status: "loading" }`; container empty; `fetch` count 0

`src/app/legacyPortalVolunteers.guard.test.tsx` — fail-closed string guard, `node:fs` via `import.meta.url`:

7. `no portals/volunteers string under src/ outside the allowlist` — walk every file under `src/`; any line containing `portals/volunteers` fails unless it matches the one allowlist entry `{ file: "app/pages/volunteer/VolunteerHome.tsx", line: 'endpoints={["/api/portals/volunteers/{id}/assignments"]}' }`, compared by file plus exact trimmed line content, never by line number. The guard's own file is skipped by path.
8. `guard self-test catches a synthetic request` — run the guard's matcher on an in-memory file `{ file: "lib/x.ts", text: "requestJson(`/api/portals/volunteers/${id}`)" }` → one violation; on the allowlisted Home line → none.
9. `VolunteerProfile.tsx contains no /api/portals string and no PortalDatasetUnavailable`

Expected red at milestone 1: tests 1-4, 7 and 9 (8 passes by construction; 5 and 6 pass on today's page).

Local checks, run one at a time (not all in CI): `node --test tests/portalSubject.test.ts tests/volunteerLinks.test.ts` (`verify.yml` runs no `node --test`); `pytest tests/unit/test_frontend_auth_contract.py`; `npx tsc --noEmit -p .`.

## 4. Commit milestones

1. `test: T7 failing tests for Host profile close-out` — §3 tests 1-9.
2. `feat: Host profile shows own record and Organization link` — page, `api.ts` deletions, orphan page deleted, `portalSubject.test.ts` and `test_frontend_auth_contract.py` updated; the local checks above green.
3. `docs: T7 close-out notes` — rewritten header comment in `VolunteerProfile.tsx`; mark parent §6 row "`VolunteerProfile.tsx` | T7" done.

## 5. Out of scope

- The Home assignments panel `VolunteerHome.tsx:299-302`; its label is the guard's one allowlisted line.
- Showing the organization's name or status on Profile (Home already does, over `GET …/host/organization`).
- Mapping `grant.role` to "Event Host" inside the shared `PortalIdentityCard` (C2).
- Speaker portal, availability, ELI work (T1-T8d); coordinator/student `/api/portals/*` functions (`api.ts:1740-1837`).

## 6. Contradictions with options

**C1 — guard scope. Resolved (orchestrator ruling, 2026-09-22):** fail-closed string guard with a one-entry allowlist (§3 test 7). The brief said "string", parent §7 row 12 said "call"; the allowlisted Home label is the only string left.

**C2 — role wording.** Parent §1 fact 1 says the user is an "Event Host"; `PortalContent.tsx:77` prints the stored role `volunteer`.
- (a) **Recommended:** keep the card as is in T7 (shared by 3 homes; the page line already says "Event Host").
- (b) Card renders `visibleRoleLabel(grant.role) ?? grant.role` (`src/lib/roleLabels.ts:126`, precedent `CoordinatorRedemptionQueue.tsx:120`), in a separate small PR.

**C3 — parent §6 says "All reads use `useScopedQuery`".** T7 has no read of its own (§2). Recorded so a reviewer does not flag it.
