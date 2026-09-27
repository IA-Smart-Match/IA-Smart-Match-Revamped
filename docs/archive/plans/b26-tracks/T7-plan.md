# B26 T7 — `VolunteerProfile` close-out (Q3 = a)

**Next action:** write the failing Vitest files in §3 and commit them red.

**Revision 3 (2026-09-22), final plan round.** It applies the Codex round-1 changes, the
orchestrator's guard ruling, and the Opus review changes R1-R5 plus nits 1, 2, 3 and 5.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` — §1 fact 1,
§6 row "`VolunteerProfile.tsx` | T7", §7 row 12, §8 row T7. Owner decision Q3 = (a) is final.
Estimate 0.5 day. No dependency. No backend route, no migration.

## 1. Files to touch

Frontend paths are under `apps/web/legacy-frontend/`.

| File | Today (file:line) | Change |
|---|---|---|
| `src/app/pages/volunteer/VolunteerProfile.tsx` | `:17` imports `PortalDatasetUnavailable`; `:48-53` dead panel, `endpoints={["/api/portals/volunteers/{id}"]}` at `:51`; `:1-15` header comment describes the legacy read; `:25-28` seam literals | Remove panel and import; render §2; rewrite header comment (milestone 2). Keep `:25-28` **verbatim** — `test_frontend_auth_contract.py` asserts `useAuthenticatedPrincipal()`, `usePortalAccess()`, `grantedPortal(portalAccess,`. |
| `src/lib/api.ts` | `:1849-1913` the "Volunteer portal types" section: `VolunteerProfile`, `AssignmentStage`, `VolunteerAssignment`, `fetchVolunteerProfile` (URL `:1897`), `fetchVolunteerAssignments` (URL `:1909`) | Delete `:1849-1913` as one block (section banner through the blank line before "Identity + accountable metrics"). No caller in `src/`. `stripG1ScoreFields` stays (`:1195`). |
| `src/app/pages/volunteer/VolunteerAssignments.tsx` | 56 lines; unrouted; `/volunteer-portal/assignments` redirects (`src/app/legacyRedirects.ts:75`) | Delete (orphan). |
| `tests/portalSubject.test.ts` | `:15-16`, `:49-50` | Remove the 4 lines for the deleted functions. |
| `tests/unit/test_frontend_auth_contract.py` (repo root) | `:170` `PORTAL_PAGES` entry; `:145` comment names `VolunteerAssignments`; loops `:328-329`, `:351-352` read every entry; CI runs it (`verify.yml:117`) | Remove `:170`; reword `:145` to name only `VolunteerConfirmedSpeaker` and note `VolunteerAssignments` was deleted in B26 T7. |
| `tests/unit/test_frontend_host_portal_contract.py` (repo root) | `:54-57` comment: "`VolunteerConfirmedSpeaker` and `VolunteerAssignments` stay in the directory unmounted" | Reword: only `VolunteerConfirmedSpeaker` stays; `VolunteerAssignments` was deleted in B26 T7. |
| `docs/plans/frontend-migration.md` (repo root) | `:73` row `/volunteer-portal/assignments` → `volunteer/VolunteerAssignments.tsx` | Mark the page deleted in B26 T7 (address redirects to `/volunteer-portal`). |
| `src/app/pages/volunteer/VolunteerProfile.test.tsx` | — | New (§3 tests 1-7). |
| `src/app/legacyPortalVolunteers.guard.test.tsx` | — | New guard (§3 tests 8-10). |

**Not touched:** `docs/plans/frontend-broken-buttons.md` belongs to PR #208 and is out of bounds for B26. It has 3 stale lines for an **owner follow-up** after T7 merges:
- line 111: the B26 row still describes the `PortalDatasetUnavailable` panel for `/api/portals/volunteers/{id}`;
- line 112: the B27 row still says "Delete the orphan file";
- line 157: the inventory row still lists `app/pages/volunteer/VolunteerAssignments.tsx`.

Data already in the frontend — no new fetch:

- `GET /v1/me` → `useAuthenticatedPrincipal()` (`src/app/hooks/useSession.tsx:131`), type `MeResponse` (`src/lib/api.ts:1926`).
- `GET /v1/me/portals` → `usePortalAccess()` (`src/app/hooks/usePortalAccess.tsx:145`) + `grantedPortal(state, "volunteer")` (`src/app/components/PortalGate.tsx:145`), type `PortalDescriptor` (`src/lib/api.ts:2019`).
- `PortalIdentityCard` (`src/app/components/PortalContent.tsx:57-130`) includes email, role, org unit and granted units. `VolunteerHome.tsx:294` uses it.

Organization route: `src/app/routes.tsx:419` → `/volunteer-portal/organization`; nav `VolunteerPortalLayout.tsx:43`; precedent link `VolunteerHome.tsx:107`.

## 2. Contract

The page renders, in order:

1. Eyebrow `<p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Profile</p>` (not a heading) and `<p>` "Your Event Host record."
2. `<PortalIdentityCard me={principal} grant={grant} />` — its `<h1>` (display name, `PortalContent.tsx:65`) is the page's only `h1` (`apps/web/DESIGN.md:297`). Labels as the card has them: "Role assigned by the server", "Org unit", "Signed in as", "Units this grant covers".
3. `<section aria-labelledby="host-profile-organization">` with `<h2 id="host-profile-organization">Your organization</h2>`, the sentence "Your organization is described on its own page." and `<Link to="/volunteer-portal/organization">Go to Organization</Link>`. Link classes include `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background` (CPP Green `--ring`, `src/styles/theme.css:32`; `DESIGN.md:296`).

Nothing else: no `PortalDatasetUnavailable`, no editable field, and **no `/api/portals` string anywhere in the file, the header comment included**. Heading outline: `h1` (card) → `h2`. The shared card is not edited.

| State | Who renders it | Page behaviour |
|---|---|---|
| loading | `VolunteerPortalLayout.tsx:67-68` `SessionGate` / `:77-78` `PortalGate` | not mounted; if mounted with `grant === null`, returns `null` (`:34-36`) |
| error (`/v1/me/portals` unreachable) | `PortalGate` with retry | not mounted |
| denied (no `volunteer` grant) | `PortalGate` | returns `null` |
| ready | page | items 1-3 |

Hooks: `useAuthenticatedPrincipal` + `usePortalAccess`/`grantedPortal` only; no `useScopedQuery`.
The page issues no request. It reads the gated session and portal-access contexts directly and
owns no query cache. It shows whichever principal those contexts hold on each render (test 7).

## 3. TDD test list (Vitest, `src/**/*.test.tsx`, CI via `npm run test:components`, `verify.yml:276`)

`src/app/pages/volunteer/VolunteerProfile.test.tsx` mocks `../../hooks/useSession` and
`../../hooks/usePortalAccess` as in `CoordinatorRedemptionQueue.test.tsx:20-54`, wraps in
`MemoryRouter`, and stubs `fetch` to fail on any call. The fixtures use the full shapes:
- `MeResponse`: `user_id`, `tenant_id`, `email`, `suspended`, `memberships`.
- `PortalDescriptor`: `portal`, `display_name`, `home_path`, `role`, `roles`, `org_unit_path`, `units[]` (`unit_id`, `path`, `unit_type`, `display_name`, `roles`), `default_unit_id`.
- IDs are fresh test UUIDs and `*@example.test` emails. Do not reuse IDs or addresses from `tools/seed_*.py`.

1. `renders the host's own record: email, role, org unit and units`
2. `heading outline is one h1 then h2 "Your organization"; "Profile" is an eyebrow` — heading levels `[1, 2]`; `getByText("Profile").tagName === "P"`, its `className` lacks `text-2xl`
3. `links to /volunteer-portal/organization with the name "Go to Organization"`; the section is named by its `h2` (`getByRole("region", { name: "Your organization" })`)
4. `organization link is keyboard-focusable with the visible focus ring` — `<a href>`, no negative `tabIndex`; `link.focus()` → `document.activeElement === link`; `className` includes `focus-visible:ring-2`, `focus-visible:ring-ring`, `focus-visible:ring-offset-background`. (No `user-event`/`jest-dom` in `package.json`; add neither.)
5. `does not render the legacy volunteer-profile panel` — no "Your volunteer profile", no `/api/portals` text
6. `renders nothing and makes no request when the grant is not resolved` — `{ status: "loading" }`; container empty; `fetch` count 0
7. `re-renders for a new principal without showing the old one` — `rerender` after switching the mocks to principal B / grant B → B's email and unit shown, A's email absent

`src/app/legacyPortalVolunteers.guard.test.tsx` — a fail-closed string guard that reads files with `node:fs` via `import.meta.url`. The needle is built from parts (`["portals", "volunteers"].join("/")`), so neither test file contains the literal.

8. `no portals/volunteers string under src/ outside the allowlist` — walk every file under `src/`, skipping the guard file by path.
   - Assert that more than 50 files were walked, and that the walked set includes `lib/api.ts` and `app/pages/volunteer/VolunteerHome.tsx`.
   - Split each file on `/\r?\n/` and trim each line.
   - Any line containing the needle fails, unless it matches the single allowlist entry `{ file: "app/pages/volunteer/VolunteerHome.tsx", line: 'endpoints={["/api/portals/volunteers/{id}/assignments"]}' }` (written from parts) by file plus exact trimmed content.
   - Assert that the entry matched exactly once.
9. `guard self-test` — the matcher run on in-memory files:
   - ``requestJson(`/api/portals/volunteers/${id}`)`` in `lib/x.ts` → 1 violation;
   - the Home allowlist line in `lib/x.ts` → 1 violation;
   - the Home line with `fetch(` appended, in `app/pages/volunteer/VolunteerHome.tsx` → 1 violation;
   - the exact Home line in `VolunteerHome.tsx` → 0 violations.
10. `VolunteerProfile.tsx contains no /api/portals string and no PortalDatasetUnavailable`

**Expected red at milestone 1:** tests 1-5, 7, 8 and 10. This is R3's list (1-5, 7, 9) renumbered after nit 1 inserted test 7. Test 7 is red because today's page does not render unit names. Test 6 passes (today's `:34-36`). Test 9 passes by construction.

## 4. Commit milestones

1. `test: T7 failing tests for Host profile close-out` — §3 tests 1-10.
2. `feat: Host profile shows own record and Organization link` — page and header comment, `api.ts:1849-1913`, orphan page, `portalSubject.test.ts`, both Python contract comments/lists, `frontend-migration.md:73`. Checks, run one at a time:
   - `npx tsc --noEmit -p .` (in place);
   - `pytest tests/unit/test_frontend_auth_contract.py tests/unit/test_frontend_host_portal_contract.py`;
   - `node --test tests/portalSubject.test.ts tests/volunteerLinks.test.ts` (no CI step runs `node --test`);
   - `npx vitest run --pool=threads src/app/pages/volunteer/VolunteerProfile.test.tsx src/app/legacyPortalVolunteers.guard.test.tsx`, run from a Linux-filesystem copy of `apps/web/legacy-frontend` (vitest cannot start on `/mnt/c`).
3. `docs: mark B26 T7 done` — only marks parent §6 row "`VolunteerProfile.tsx` | T7" done.

## 5. Out of scope

- Home assignments panel `VolunteerHome.tsx:299-302`; its label is the guard's one allowlisted line.
- Organization name or status on Profile (Home already shows it).
- `docs/plans/frontend-broken-buttons.md` (PR #208; follow-up lines listed in §1).
- Mapping `grant.role` to "Event Host" in the shared card (C2).
- Speaker portal, availability, ELI (T1-T8d); coordinator/student `/api/portals/*` functions (`api.ts:1740-1837`).

## 6. Contradictions with options

**C1 — guard scope. Resolved (orchestrator ruling, 2026-09-22):** fail-closed string guard, one-entry allowlist (§3 test 8).

**C2 — role wording.** Parent §1 fact 1 says "Event Host"; `PortalContent.tsx:77` prints the stored role `volunteer`.
- (a) **Recommended:** keep the card as is in T7 (shared by 3 homes; the page line says "Event Host").
- (b) Card renders `visibleRoleLabel(grant.role) ?? grant.role` (`src/lib/roleLabels.ts:126`, precedent `CoordinatorRedemptionQueue.tsx:120`), separate small PR.

**C3 — parent §6 "All reads use `useScopedQuery`".** T7 has no read of its own (§2). Recorded so a reviewer does not flag it.
