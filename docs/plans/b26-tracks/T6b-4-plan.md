# B26 T6b-4 — the `/speaker-portal` shell: Home, Invitations, Engagements, Availability, Contact preferences

**Next action:** wait for the §0 start gate, then run milestone 0 (the two merges).

**Revision 2, 2026-09-23.** Applies the plan gate (CHANGES, 1 HIGH + 3 MED + 4 LOW): G1 "Go back" name (§8.3, §9.2 E4/E12); G2 `aria-disabled` pressed button (§4.2, §5.2 I5, §5.5 C5, §8.3, m9); G3 `PagedList` for Answered invitations and Engagements (§5.2, §5.3, §8.3, §9.3); G4 page titles and h1 focus (§2.4); G5 re-pinned inputs, X1/X2 closed, OQs ruled (§0, §11, §12); G6 file-set scan (§9.3 item 0); G7 speaker role loop (§1); G8 switcher slot above the identity block (§2.2). Revision 1 was the first plan. Docs only: no source file, route or test is written by this document.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2 (privacy), §4.2 item 4 (portal mapping), §4.3, §4.4, §6 (`/speaker-portal` row and the accessibility paragraph), §7 row 12, §8 T6b-4.
Inputs (all final): T6b-1 plan `origin/feat/b26-t6b-1` @ `3e9a7ef4` (rev 3); T6b-2 plan `origin/feat/b26-t6b-2` @ `f30f85e9`; T6b-3 plan `origin/feat/b26-t6b-3` @ `78432e2f` (stacks on T6b-2, imports its authorizer); T5 plan `origin/feat/b26-t5` @ `f0c060e5`; T3 plan `origin/feat/b26-t3` §5 (types).
Line numbers are `main` @ `1909278f` unless a track is named. Frontend paths are relative to `apps/web/legacy-frontend/`.

## 0. Branch, stack and start gate

**Stack.** T6b-4 is frontend only. It consumes T6b-2's 5 adapters, T6b-3's routes, T5's form and T6b-1's gated route, `PortalKind` and capability flag. On `feat/b26-t6b-4` (this plan commit, from `origin/main`), merge, not rebase, so the pushed plan commit stays (the T5 and T6b-2 pattern):

1. `git merge origin/feat/b26-t6b-3`. T6b-3 now stacks on T6b-2 (T6b-3 @ `78432e2f`, "Base and merge order"), so this one merge brings T6b-3, T6b-2, T8a → T6b-1 → T2 → T1, and T3. The T6b-2 / T6b-3 overlaps (`main.py` router rows, the policy-matrix `SPEAKER_SELF_OPERATIONS` test, the `_SPEAKER_SELF` route-roles literal) are resolved on T6b-3's branch, not here.
2. `git merge origin/feat/b26-t5`. Common base is T3. Expected conflicts, resolved as a union:
   - `CoordinatorSpeakerContacts.tsx` `ContactRow`: T5's "Availability" disclosure next to T6b-1's `SpeakerPortalInvite`; keep both elements.
   - `contracts/openapi/smartmatch.json`, if touched: never hand-merge. Take either side, then `make openapi VENV=$VENV`.
3. The PR targets `main`. Body line 1: **"Merge #210, #212, then the T6b-1, T8a, T3, T6b-2, T6b-3 and T5 PRs first."** After they land, merge `main` into `feat/b26-t6b-4` so the diff is T6b-4 only.
4. T6b-4 writes no migration and no Python source. Backend conflicts are merge hygiene, not T6b-4 design: if one needs more than a union, stop and escalate to the orchestrator.

**Start gate** (implementation, not this plan). All pushed on their branches:

| Track | Needed from it | Used in milestone |
|---|---|---|
| T6b-1 | `speaker_portal: false` in `src/lib/productScope.ts`; `"speaker"` in `PortalKind` (`src/lib/principal.ts:83`); `speaker` row in `src/lib/roleLabels.ts`; gated `/speaker-portal` placeholder route and `SpeakerPortalPlaceholder.tsx`; `src/app/routes.test.tsx` | 7, 8 |
| T6b-2 | `fetchMyAvailability`, `updateMyAvailability`, `fetchMyInvitations`, `answerMyInvitation`, `fetchMyEngagements` and their types (T6b-2 §6); `src/lib/speakerSelfApi.test.tsx` green | 3–6 |
| T6b-3 | `/v1/me/contact-channels` routes and the §5.3 `View` shape. T6b-3 ships **no** adapter (T6b-3 §13 item 1): T6b-4 writes it | 1, 2, 5, 6 |
| T5 | `SpeakerAvailabilityForm` (`src/app/components/speakerAvailability/`), `src/lib/speakerAvailabilityDraft.ts` with `COPY.connector`, `availabilityErrorMessage`, `formatCalendarDate`, `utcToday` | 5, 6 |

If T5's or T6b-2's names differ as built, follow the built names and list the difference in the PR body.

## 1. Files

| Path | Change |
|---|---|
| `src/lib/api.ts` | **3 adapters and their types** for `/v1/me/contact-channels` (§6.1), after T6b-2's `fetchMyEngagements`. `SpeakerSelfErrorCode` already holds `"speaker_invitation_response_conflict"` (T6b-2 @ `f30f85e9` §6). |
| `src/app/components/PagedList.tsx` | One **additive, optional** prop `revealIndex?: number \| null`: when it becomes a number, an effect keyed on `[revealIndex, pageSize]` sets the requested page to `Math.floor(revealIndex / pageSize) + 1`. Absent or `null` → today's behaviour exactly; every existing caller is unchanged. The caller clears it to `null` after focusing, so the same index can be revealed again. (G3) |
| `src/app/pages/speaker/useSpeakerPageTitle.ts` | **New.** `useSpeakerPageTitle(h1Text)`: sets `document.title = "{h1Text} · Speaker Portal"` on mount and restores the previous title on unmount, so leaving for another shell does not keep a Speaker title. (G4) |
| `src/app/hooks/useSpeakerSelf.ts` | **New.** `SPEAKER_SELF_RESOURCE` (the 4 resource names), 4 read hooks, 3 mutation hooks (§4). The only file that builds a `my-*` key. |
| `src/app/pages/speaker/speakerPortalErrors.ts` | **New, pure.** `speakerPortalError(context, cause) -> { message, refetch }` (§7). Fixed strings only; never the server's message text. |
| `src/app/pages/speaker/speakerPortalFormat.ts` | **New, pure.** `formatEventWhen(event)`, `formatInstant(iso)`, `engagementStateLabel`, `invitationStatusLabel`, `channelStatusSentence(view)`. |
| `src/app/pages/speaker/SpeakerSelfNotice.tsx` | **New.** The page-level not-linked / denied / signed-out / read-error block, with Retry where safe. |
| `src/app/pages/speaker/SpeakerHome.tsx` | **New.** §3. |
| `src/app/pages/speaker/SpeakerInvitations.tsx` | **New.** List, grouping and the page's one status region. |
| `src/app/pages/speaker/InvitationRow.tsx` | **New.** One invitation, its Accept / Decline buttons and the inline confirm row. |
| `src/app/pages/speaker/SpeakerEngagements.tsx` | **New.** Upcoming / Past through `?when=`. |
| `src/app/pages/speaker/EngagementRow.tsx` | **New.** Used by Engagements and Home. |
| `src/app/pages/speaker/SpeakerOwnAvailability.tsx` | **New.** The Speaker's wiring around T5's form. Named `Own` so it never collides with T3's `SpeakerAvailability` type in one import list. |
| `src/app/pages/speaker/SpeakerContactPreferences.tsx` | **New.** List and status region. |
| `src/app/pages/speaker/ContactChannelRow.tsx` | **New.** One channel, Opt in / Opt out, the inline opt-out confirm row. |
| `src/lib/speakerAvailabilityDraft.ts` (T5's) | Add `COPY.speaker` (§5.4). Give `availabilityErrorMessage` an optional last parameter `copy = COPY.connector` (additive; every T5 call site unchanged). |
| `src/app/components/speakerAvailability/SpeakerAvailabilityForm.tsx` (T5's) | Only if T5 derives the form's `aria-labelledby` from `idPrefix` internally: add an optional `labelledBy` prop, default unchanged. |
| `src/app/components/SpeakerPortalLayout.tsx` | **New.** The shell (§2.2). Two marked slots for T6b-5's switcher. |
| `src/app/routes.tsx` | Replace T6b-1's placeholder element with `SpeakerPortalLayout` and 5 children (§2.1). T6b-1's capability gate expression stays exactly as it is. |
| `src/app/pages/speaker/SpeakerPortalPlaceholder.tsx` (T6b-1's; path as T6b-1 builds it) | **Deleted.** |
| `src/app/navPrefetch.ts` | `SPEAKER_PREFETCH` (§2.3), spread into `PORTAL_PREFETCH` (`:162-166`). |
| `apps/web/DESIGN.md` | "Signed-in shells" (`:148-160`): the Speaker Portal is the fourth shell; its home puts open invitations before engagements. T6b-1 already rewrites the "Speaker is a non-account contact persona" sentences (`:150-152`); T6b-4 adds only its bullets after them. |
| `tests/unit/test_frontend_auth_contract.py` | `PORTAL_SHELLS` (`:127-131`) gains `app/components/SpeakerPortalLayout.tsx` ("three shells" → "four"). `PAGES_WITH_NO_LEGACY_PORTAL_ID` (`:198`) gains the 5 speaker pages: every request they make is `/v1/me/*`, subject resolved from the bearer token. The derivation list (`:353-360`) gains `'role === "speaker"'`, and that loop runs over `PORTAL_PAGES + PORTAL_SHELLS + PAGES_WITH_NO_LEGACY_PORTAL_ID` (today it skips the third tuple, so the speaker pages would escape it). (G7) |
| `tests/unit/test_frontend_paged_list_contract.py` | `PAGED_SURFACES` (`:47-65`) gains `"speaker/SpeakerInvitations.tsx": ("answered",)` and `"speaker/SpeakerEngagements.tsx": ("engagements",)`. The existing `<PagedList` count and `items={…}` checks (`:270-283`) then apply. (G3) |
| `tests/unit/test_frontend_speaker_portal_contract.py` | **New** source scan (§9.3). |
| Vitest files | §9.2. All `src/**/*.test.tsx`, so CI runs them. |

**Not touched:** any Python source, migration, OpenAPI file, `VolunteerPortalLayout.tsx`, `CoordinatorPortalLayout.tsx`, `PortalGate.tsx`, `Home.tsx`. `Home.tsx:80-102` already lands a Speaker-only account on `/speaker-portal`, because it navigates to the server's `default_portal` `home_path` and T6b-1 maps `speaker` → `/speaker-portal` (`portals.py` `_PORTAL_FOR_ROLE`). `NotFound.tsx:50-73` and `PortalGate.tsx:113-127` already list every granted portal, so "Speaker Portal" appears there without an edit.

## 2. Routes, shell and navigation

### 2.1 Routes

Mounted only when `isCapabilityEnabled("speaker_portal")` (T6b-1 §1 `routes.tsx` row, §7 "Gate"). The flag is `false` in the build, so with it off `/speaker-portal/*` falls to `NotFound`. This is the one deliberate departure from the file's "mount unconditionally" rule (`routes.tsx:401-422`), and T6b-1 already made it.

| Path | Element | Nav label | Icon (`lucide-react`, `aria-hidden`) |
|---|---|---|---|
| `/speaker-portal` (index) | `SpeakerHome` | Home | `LayoutDashboard` |
| `/speaker-portal/invitations` | `SpeakerInvitations` | Invitations | `Mail` |
| `/speaker-portal/engagements` | `SpeakerEngagements` (reads `?when=upcoming\|past`) | Engagements | `CalendarCheck` |
| `/speaker-portal/availability` | `SpeakerOwnAvailability` | Availability | `CalendarX` |
| `/speaker-portal/contact-preferences` | `SpeakerContactPreferences` | Contact preferences | `BellRing` |

Each child is `lazy()` + `withSuspense()` like every other portal page (`routes.tsx:15-34`, `:165-167`). `errorElement: <NotFound />` on the parent. `?when=` values other than `past` read as `upcoming`, the server's default (T6b-2 §2.4).

### 2.2 `SpeakerPortalLayout`

The volunteer shell's structure (`VolunteerPortalLayout.tsx`), with the coordinator shell's nav accessibility (`CoordinatorPortalLayout.tsx:342-370`), which the volunteer shell lacks.

1. `useSession()`; `session.status !== "signed-in"` → `<SessionGate state={session} />` (pinned by `test_every_portal_shell_gates_on_the_server_session`).
2. `grantedPortal(usePortalAccess(), "speaker")`; `null` → `<PortalGate state={portalAccess} me={session.me} />`. No role is read here (`test_no_portal_page_derives_a_portal_from_a_role_it_read`).
3. Sidebar identity: `BrandLogo label={grant.display_name}` ("Speaker Portal", T6b-1's `role_presentation` row), `principalDisplayName`, `grant.org_unit_path`, `grant.display_name`, Sign out.
4. `<nav aria-label="Speaker Portal navigation">`; the active link carries `aria-current="page"` (Home exact; others prefix).
5. Hover and focus call `prefetchPortalRoute(queryClient, principalKey, grant.default_unit_id, href)`.
6. **T6b-5 slots.** Two JSX comments, nothing rendered:
   - sidebar footer, **above** the identity block: `{/* SLOT(T6b-5): portal switcher, shown only with 2+ portals */}`. Not between the profile and Sign out: DESIGN.md `:155` keeps sign-out directly beneath the profile area (G8);
   - mobile header, replacing the right-hand spacer (the volunteer shell's `<div className="w-6" />`, `:193`): `{/* SLOT(T6b-5): portal switcher (mobile) */}` next to a same-width spacer.
   A §9.3 source scan pins both markers, so T6b-5 finds them and nothing else is built early.

7. **Focus on route change (G4).** A layout effect on `location.pathname` moves focus to the new page's `h1` (`main h1`, which every page renders with `tabIndex={-1}` and `scroll-mt-20`). It skips the shell's first render, so signing in or reloading does not move focus. A `?when=` change on Engagements keeps the pathname, so focus stays on the period link the user pressed.

### 2.3 Prefetch

`SPEAKER_PREFETCH` keys on nav `href` and prefetches exactly each page's page-load reads, with `SPEAKER_SELF_RESOURCE` imported from `useSpeakerSelf.ts` so the prefetched slot and the page's slot are the same key. The Speaker reads take no unit, so each spec ignores `unitId`, for example `spec(SPEAKER_SELF_RESOURCE.invitations, () => [], () => fetchMyInvitations())`. `prefetchPortalRoute` still returns early when `default_unit_id` is `null` (`navPrefetch.ts:179-181`); that only skips a hint.

| `href` | Prefetches |
|---|---|
| `/speaker-portal` | `my-invitations`; `my-engagements` + `upcoming` |
| `/speaker-portal/invitations` | `my-invitations` |
| `/speaker-portal/engagements` | `my-engagements` + `upcoming` |
| `/speaker-portal/availability` | `my-availability` |
| `/speaker-portal/contact-preferences` | `my-contact-channels` |

### 2.4 Page titles (G4, WCAG 2.4.2)

Each page calls `useSpeakerPageTitle(<its h1 text>)`:

| Page | `h1` | `document.title` |
|---|---|---|
| Home | "Home" | "Home · Speaker Portal" |
| Invitations | "Invitations" | "Invitations · Speaker Portal" |
| Engagements | "Engagements" | "Engagements · Speaker Portal" |
| Availability | "Your availability" | "Your availability · Speaker Portal" |
| Contact preferences | "Contact preferences" | "Contact preferences · Speaker Portal" |

The title is set from the page's own constant, not read from the server, so it is correct while data is still loading and in every read-failure state.

## 3. Component tree

```text
SpeakerPortalLayout
├─ SessionGate | PortalGate                       (instead of the shell, never around it)
└─ shell
   ├─ aside#speaker-portal-sidebar
   │  ├─ BrandLogo · Close button (below lg)
   │  ├─ nav "Speaker Portal navigation" → 5 Links (aria-current)
   │  └─ footer: SLOT(T6b-5) · initials · name · unit path · "Speaker Portal" · Sign out
   ├─ header (below lg): Open menu button · BrandLogo · SLOT(T6b-5)
   └─ main → Outlet
      ├─ SpeakerHome                              h1 "Home"
      │  ├─ SpeakerSelfNotice                     (not linked / denied / signed out: replaces both sections)
      │  ├─ section h2 "Invitations waiting for your answer"  → up to 5 · link "Answer on the Invitations page"
      │  └─ section h2 "Your upcoming engagements"             → up to 5 EngagementRow · link "See all engagements"
      ├─ SpeakerInvitations                       h1 "Invitations" · one role=status
      │  ├─ section h2 "Waiting for your answer"  → InvitationRow (Accept · Decline → confirm row)
      │  └─ section h2 "Answered"                 → PagedList items={answered} (revealIndex) → InvitationRow (read-only)
      ├─ SpeakerEngagements                       h1 "Engagements"
      │  ├─ nav "Engagement period": Upcoming · Past  (links, aria-current)
      │  └─ PagedList items={engagements} key={when} → ol → EngagementRow
      ├─ SpeakerOwnAvailability                   h1#my-availability-heading "Your availability"
      │  ├─ read states (loading · SpeakerSelfNotice · error + Retry)
      │  ├─ SLOT(T8d): load band                  (comment only)
      │  └─ SpeakerAvailabilityForm (T5)          copy=COPY.speaker · idPrefix="my-availability"
      └─ SpeakerContactPreferences                h1 "Contact preferences" · one role=status
         └─ ul → ContactChannelRow (address · status sentence · last set by · Opt in | Opt out → confirm row)
```

- **Home has no answer buttons.** The Invitations page is the one place an answer is given, so there is one confirm flow and one status region for it.
- **T8d slot.** `SpeakerOwnAvailability` carries `{/* SLOT(T8d): the Speaker's own load band — a band word only, never a number (OQ-CBA-005) */}` between the read states and the form. T6b-4 ignores any `load` field the response already carries (T3 says T8 adds it additively); a Vitest test pins that nothing numeric from it is rendered (§9.2 G7).

## 4. Queries, mutations, invalidation

### 4.1 Reads (all `useScopedQuery`, key `[principalKey, resource, ...params]`, `useScopedQuery.ts:77-90`)

| Hook | Resource / params | Adapter | Used by |
|---|---|---|---|
| `useMyInvitations()` | `"my-invitations"` | `fetchMyInvitations()` | Home, Invitations |
| `useMyEngagements(when)` | `"my-engagements"`, `when` | `fetchMyEngagements(when)` | Home (`upcoming`), Engagements |
| `useMyAvailability()` | `"my-availability"` | `fetchMyAvailability()` | Availability |
| `useMyContactChannels()` | `"my-contact-channels"` | `fetchMyContactChannels()` | Contact preferences |

- The first three names are T6b-2 §6's. They do not collide with the volunteer shell's `"my-speaker-requests"`, which matters once T6b-5 gives one principal both shells.
- No read takes a professional id, unit id or user id (MM-A01). The principal key is the only identity in a key.
- `enabled` is the principal check only. No page waits for a unit.
- 4xx is never retried (`shouldRetryQuery`, `queryClient.ts:148`), so 403 and 404 settle at once.
- A page decides "read state vs content" from `query.data === undefined`, not `isError`: a failed background refetch keeps the last good data on screen (TanStack v5), with the error in the page's alert region (T5 §4 rule).

### 4.2 Writes (all `useMutation`; no `onMutate`; no optimistic update)

| Mutation hook | Adapter | On success | On error | Never touched |
|---|---|---|---|---|
| `useAnswerMyInvitation()` | `answerMyInvitation(invitationId, response)` | `return queryClient.invalidateQueries({ queryKey: [pk, "my-invitations"], exact: true })`. Returning the promise keeps `isPending` true until the re-read lands, so the buttons stay blocked (G2 rule below) until the row has moved. | `speaker_invitation_not_found`, `speaker_invitation_already_answered`, `speaker_invitation_response_conflict` → the same exact invalidation | `my-engagements` (an accept writes no pipeline row, T6b-2 §2.3), `my-availability`, `my-contact-channels` |
| `useUpdateMyAvailability()` | `updateMyAvailability(payload)` | `setQueryData([pk, "my-availability"], saved)` — the committed row read back, so a second save carries the new `version` (T5 §3 step 1). Then the form re-seeds. | `speaker_availability_stale` → `refetchQueries({ queryKey: [pk, "my-availability"], exact: true })`; the draft is kept (T5 §4.3) | Everything else. T5's `match-run` and `invitation-compose` invalidations are Connector keys under another principal; a Speaker's browser has neither. |
| `useMyChannelChoice()` | `optInMyContactChannel(id)` or `optOutMyContactChannel(id)` | `return queryClient.invalidateQueries({ queryKey: [pk, "my-contact-channels"], exact: true })` | `speaker_contact_channel_not_found`, `…_suppression_not_liftable`, `…_address_unverified`, `…_opt_in_unavailable`, `…_transition_conflict` → the same exact invalidation | the other three keys |

- **Re-read, not splice**, for invitations and channels: the list is the one owning query (the `useRedemptionQueue.ts:1-11` rule, ADR-0011 rule 3). A channel row's `send_eligible`, `last_set_by` and `can_opt_*` are server-computed; T6b-4 never recomputes them.
- Every key is built from `usePrincipalKey()`. While it is `null`, every submit button is disabled and no request is sent.
- **One mutation in flight per page (G2).** While an answer (or channel choice) is pending:
  - the **pressed** button stays enabled in the DOM, gets `aria-disabled="true"`, reads "Saving…", and its `onClick` returns early while `isPending` (the click guard). It is not given `disabled`, because a natively disabled button drops keyboard focus to `<body>`;
  - every **other** answer (or choice) button on the page gets native `disabled`.
  Both clear when `isPending` ends, which is after the list re-read (the returned invalidation promise above).
- No mutation is retried automatically (TanStack mutation default `retry: 0`; not overridden).

## 5. Page states

Common rule (all five pages). Before first data, a read failure replaces the content:

| Read outcome | Renders |
|---|---|
| Pending | `aria-busy="true"` on the region and a text label ("Loading invitations…"). Not a skeleton row, never an empty list. |
| 404 `speaker_profile_not_linked` | `SpeakerSelfNotice` "not linked" (§7). No Retry: repeating cannot change it. |
| 403 (any) | `SpeakerSelfNotice` "denied". Does not imply a record exists. No Retry. |
| 401 | `SpeakerSelfNotice` "signed out", with a link to `/login`. |
| 429, 5xx, network, anything else | Page-specific read-error sentence + **Retry** (`refetch()`, safe for a GET). |

### 5.1 Home

| # | State | Renders |
|---|---|---|
| H1 | Either read is not-linked, 403 or 401 | One `SpeakerSelfNotice` in place of both sections (not two copies of it). |
| H2 | Invitations pending / failed | That section only shows its label or error + Retry; the engagements section is independent. |
| H3 | No open invitations | "No invitations are waiting for your answer." |
| H4 | Open invitations | "{n} invitation(s) waiting for your answer" (n = loaded `answerable` rows; "at least {n}" when `truncated`), up to 5 titles with their dates, then a link "Answer on the Invitations page". |
| H5 | No upcoming engagements | "No upcoming engagements. An engagement appears here once a Speaker Connector confirms you for an event." |
| H6 | Upcoming engagements | Up to 5 `EngagementRow`s (server order) and "See all engagements". |

Open invitations come first: DESIGN.md's "action queue before summary" rule (`:159`).

### 5.2 Invitations

| # | State | Renders |
|---|---|---|
| I1 | Empty | "No invitations yet. When a Speaker Connector invites you to an event, it appears here." |
| I2 | List | "Waiting for your answer" (`answerable`, not paged: it is the action list), then "Answered" through `<PagedList items={answered} label="answered invitations" idPrefix="answered-invitations" revealIndex={…}>` (G3). Each row: title; "Date in the invitation: {date_text}" verbatim; the formatted `local_date` when present; "Sent {dispatched_at}" (not "delivered": T6b-2 §2.2). |
| I3 | Answered row | "You accepted" / "You declined" + time when `recorded_by = "speaker"`; "Your Speaker Connector recorded that you accepted/declined" when `speaker_connector`. Never a user id. |
| I4 | Confirming | The row's buttons are replaced by the confirm row (§8.3): "Accept this invitation? Your first answer is final. To change it later, contact your Speaker Connector." + "Confirm accept" + "Go back". Same for Decline. |
| I5 | Pending | The pressed button ("Confirm accept" / "Confirm decline") keeps focus with `aria-disabled="true"`, a click guard and "Saving…"; every other answer button is `disabled` (§4.2, G2). |
| I6 | Recorded | Status region: "You accepted {title}." `recorded: false` → "Your answer to {title} was already recorded. Nothing changed." Shown only after the 200. |
| I7 | Answer error | Row-level `role="alert"` with the §7 message; the list re-reads for the refetch codes. |
| I8 | Truncated | "Showing your 200 most recent invitations." |

### 5.3 Engagements

| # | State | Renders |
|---|---|---|
| E1 | Upcoming empty | "No upcoming engagements." |
| E2 | Past empty | "No past engagements yet." |
| E3 | List | `<PagedList items={engagements} label="engagements" idPrefix="engagements-{when}" key={when}>` (G3; `key` resets to page 1 when the period changes). Each `EngagementRow`: title; when (§6.3); state chip Confirmed / Attended / Cancelled (icon + word). Cancelled adds "Cancelled on {date}" and never who cancelled. `event: null` → "Event details are no longer available." |
| E4 | Date unknown | "Date not set yet" (the server lists these under Upcoming, T6b-2 C8). |
| E5 | Truncated | "Showing the first 200." |

No actions: a Speaker cannot cancel a booking or change an answer here (OQ-CBA-044; T6b-2 §10).

### 5.4 Availability (T5's states, Speaker copy)

T5 §4 states 1–10 apply, with these differences:

| T5 state | Speaker page |
|---|---|
| 2 Not stated | "**Not stated.** You have not said when you can speak, so Speaker Connectors see your availability as unknown." Button "Save: no dates blocked" while empty; hint "Saving an empty form tells Speaker Connectors you have no dates blocked." |
| 3 / 4 source labels | "Added by you" / "Added by a Speaker Connector"; "Last changed {time} by you / by a Speaker Connector" (`updated_source`). |
| 5 Stale | "**This changed** since you opened it — a Speaker Connector may have updated it. Your changes are still in the form and were not saved." Then T5 §4.3 steps 4–7 unchanged ("Save my changes over it", "Discard my changes"). |
| 8 Denied | `SpeakerSelfNotice` "denied". |
| 9 Not found | Replaced by `SpeakerSelfNotice` "not linked" (the only 404 the Speaker route returns, T6b-2 §2.5). A PATCH that gets it shows the same words in the form alert and keeps the draft. |

`COPY.speaker` also sets: windows legend "Dates you cannot speak"; pause hint "Optional. No new invitations are sent through this date. Latest {date}."; capacity hint "Optional. How many hours of speaking you can give in any 90 days. If you leave it blank, your workload cannot be measured." The T5 wording rule holds: no `/\bavailable\b/i` anywhere on the page.

### 5.5 Contact preferences

| # | State | Renders |
|---|---|---|
| C1 | Intro (always) | "Choose which of your addresses may receive invitations. Opting out is immediate. To stop invitations for a while instead, set a pause on the Availability page." (links to it; parent §2: pausing is not an opt-out) |
| C2 | Empty | "No addresses are on file for you. Your Speaker Connector adds them." |
| C3 | Row | `<h3>` the address; `channelStatusSentence` (below); "Last set by you" / "Last set by your Speaker Connector" (`last_set_by`); the one button the server allows. |
| C4 | Opt-out confirm | Row buttons replaced by: "Stop invitations to {address}? An invitation already being sent at this moment may still arrive." + "Confirm opt out" + "Keep receiving" (§8.3). |
| C5 | Pending | The pressed button ("Confirm opt out" / "Opt in") keeps focus with `aria-disabled="true"`, a click guard and "Saving…"; every other choice button is `disabled` (§4.2, G2). |
| C6 | Done | Status region, from the response: opt-out `changed` → "You opted out of invitations to {address}."; opt-out not `changed` → "{address} was already opted out. Nothing changed."; opt-in `changed` and `channel.send_eligible` → "Invitations can be emailed to {address} again."; opt-in `changed`, not eligible → "Your choice is saved. {address} still cannot receive invitations: {status sentence}."; opt-in not `changed` → "{address} was already opted in. Nothing changed." |
| C7 | Error | Row-level `role="alert"`, §7 message; list re-reads for the refetch codes. |
| C8 | Truncated | "Showing the first 50 addresses." |

`channelStatusSentence(view)` reads server fields only; `send_eligible` is shown, never re-derived (`api.ts:3978` rule):

| Server says | Sentence |
|---|---|
| `send_eligible` | "Invitations can be emailed here." |
| `suppression_reason = your_opt_out` | "You opted out." |
| `= unsubscribed` | "Unsubscribed through an email link." |
| `= connector` | "Your Speaker Connector stopped messages to this address." |
| `= delivery` | "Messages to this address could not be delivered." |
| not suppressed, not eligible | "Not yet confirmed for invitations." |

Buttons: "Opt in" when `can_opt_in`; "Opt out" when `can_opt_out`; neither → the sentence plus "To change this, ask your Speaker Connector." Hidden rather than disabled, because a disabled native button cannot take focus, so its reason would be unreachable by keyboard; the sentence is always visible text.

## 6. Contracts consumed

### 6.1 New adapters (T6b-4 writes; T6b-3 §5.3 contract)

```ts
export type MyChannelSuppressionReason = "your_opt_out" | "unsubscribed" | "connector" | "delivery";
export interface MyContactChannel {
  contact_channel_id: string; channel_kind: string; address: string; contact_state: string;
  send_eligible: boolean; suppressed: boolean; suppression_reason: MyChannelSuppressionReason | null;
  speaker_choice: "opt_in" | "opt_out" | null; last_set_by: "speaker" | "connector";
  can_opt_in: boolean; can_opt_out: boolean; updated_at: string;
}
export interface MyContactChannelList { channels: MyContactChannel[]; truncated: boolean }
export interface MyContactChannelChange { channel: MyContactChannel; changed: boolean }
export type MyContactChannelErrorCode =
  | "speaker_profile_not_linked" | "speaker_contact_channel_not_found"
  | "speaker_contact_channel_suppression_not_liftable" | "speaker_contact_channel_address_unverified"
  | "speaker_contact_channel_opt_in_unavailable" | "speaker_contact_channel_transition_conflict";

export async function fetchMyContactChannels(): Promise<MyContactChannelList>;           // GET  /v1/me/contact-channels
export async function optInMyContactChannel(channelId: string): Promise<MyContactChannelChange>;  // POST …/{id}/opt-in, no body
export async function optOutMyContactChannel(channelId: string): Promise<MyContactChannelChange>; // POST …/{id}/opt-out, no body
```

- `requestJson<T>(path, init, { authenticated: true })` (`api.ts:484`); `channelId` through `encodeURIComponent`; no retry, no default, no normalizing; errors stay `ApiRequestError` (`:330`) with `code` and `details`.
- No parameter names a professional, unit or user (MM-A01), pinned by §9.3.
- `speaker_contact_channel_speaker_opted_in` / `_opted_out` are **Connector-side** 409s (T6b-3 §5.4 G1–G3). No `/v1/me` route returns them, so they are not in this union (OQ-3).

### 6.2 Reused (T6b-2 §6, T3 §5): `MyInvitation`, `MyInvitationList`, `MyInvitationAnswerResult`, `MyEngagement`, `MyEngagementList`, `EngagementWhen`, `SpeakerAvailability`, `SpeakerAvailabilityUpdatePayload`.

### 6.3 Dates and times

- Calendar dates (`local_date`, `invitations_paused_until`): T5's `formatCalendarDate` (`en-US`, `dateStyle: "long"`, `timeZone: "UTC"`), so a date never shifts a day.
- An exact engagement: date plus `Intl.DateTimeFormat("en-US", { timeStyle: "short", timeZone: event.time_zone, timeZoneName: "short" })` over `starts_at`–`ends_at`, e.g. "October 14, 2026, 10:00 AM – 11:15 AM PDT". `date_only` → the date and "Time not set". `time_zone: null` with an instant → the date only.
- Instants (`recorded_at`, `dispatched_at`, `cancelled_at`, `updated_at`): `formatInstant` = `toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })` in the viewer's zone. Tests use midday-UTC fixtures so the date part is zone-proof.
- Every rendered date sits in `<time dateTime="…">`.

## 7. Error code → message map (`speakerPortalError`)

Branch on `ApiRequestError.code`, then `status`; never on message text. Every message is fixed text: DESIGN.md "do not show raw server text" (`:62`). `refetch` = invalidate the page's own list key exactly (§4.2).

| Context | Status | Code | Message | `refetch` |
|---|---|---|---|---|
| any | 404 | `speaker_profile_not_linked` | "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation." | no |
| any | 403 | any | "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector." | no |
| any | 401 | any | "Your session has ended. Sign in again; nothing on this page was changed." | no |
| any | 429 | `rate_limited` | "Too many requests just now. Wait a minute, then try again." | no |
| write | 422 | `invalid_request` | "The server could not read this request, so nothing was changed." | no |
| read | other | other / network | "{Your invitations / Your engagements / Your availability / Your addresses} could not be loaded, and the server gave no reason. Try again." | no |
| write | other | other / network | "This could not be saved, and the server gave no reason. Nothing was changed. Try again." | no |
| answer | 404 | `speaker_invitation_not_found` | "This invitation is no longer open to you. The list has been refreshed." | yes |
| answer | 409 | `speaker_invitation_already_answered` | "This invitation already has a different answer, and the first answer is final. To change it, contact your Speaker Connector." | yes |
| answer | 409 | `speaker_invitation_response_conflict` | "Your answer could not be recorded just now. The list has been refreshed; try again." | yes |
| availability | 409 / 422 | `speaker_availability_*` | T5 §6's `availabilityErrorMessage(code, details, draft, COPY.speaker)`; stale follows T5 §4.3 | stale → refetch exact |
| channel | 404 | `speaker_contact_channel_not_found` | "This address is no longer on your record. The list has been refreshed." | yes |
| channel | 409 | `speaker_contact_channel_suppression_not_liftable`, `details.reason = "connector"` | "Your Speaker Connector stopped messages to this address, so it cannot be turned back on here. Ask your Speaker Connector." | yes |
| channel | 409 | same, `details.reason = "delivery"` (or absent) | "Messages to this address could not be delivered, so it cannot be turned back on. Ask your Speaker Connector to add a different address." | yes |
| channel | 409 | `speaker_contact_channel_address_unverified` | "This address was unsubscribed and is not the one you sign in with. Ask your Speaker Connector." (T6b-3 §5.3's text) | yes |
| channel | 409 | `speaker_contact_channel_opt_in_unavailable` | "This address has not been confirmed for invitations yet, so you cannot opt in here. Ask your Speaker Connector." (`details.contact_state` not shown) | yes |
| channel | 409 | `speaker_contact_channel_transition_conflict` | "Something changed while you were opting in. The list has been refreshed; try again." | yes |

## 8. Accessibility — WCAG 2.2 AA

### 8.1 Shell

- Landmarks: `aside` > `nav aria-label="Speaker Portal navigation"`; `main`; the mobile `header`. Active link `aria-current="page"`.
- Mobile menu button: `aria-label="Open navigation"`, `aria-expanded`, `aria-controls="speaker-portal-sidebar"`. Opening moves focus to the Close button; Escape, the overlay or a link closes it and returns focus to the menu button (the volunteer shell does neither).
- Icons `aria-hidden="true"`. Links and buttons `min-h-11` (2.5.8) with the CPP focus ring (2.4.7).
- Page titles (2.4.2) and focus to the new page's `h1` on route change (2.4.3): §2.4 and §2.2 item 7.

### 8.2 Pages

- One `h1` per page, then `h2` per section, `h3` per row (address, invitation or engagement title). Sequential outline.
- **One** `role="status"` region per page, always mounted, for mutation outcomes only. Loading uses `aria-busy` plus visible text, not the status region.
- Errors: row-level `<p role="alert" id="{row}-error">`, referenced from the row's buttons by `aria-describedby`; page-level read errors in one `role="alert"`. A new submit clears the old error first, so nothing is announced twice.
- State chips and channel status: an icon plus a word. Colour never carries meaning alone (1.4.1).
- Engagements period switch: `<nav aria-label="Engagement period">` with two links, `aria-current="page"` on the current one (the `CoordinatorReviewQueue.tsx:293-298` idea, as links so Back works).
- Focus targets that sit near the top get `scroll-mt-20`, so the sticky mobile header never covers a focused element (2.4.11).
- Layout: rows use `grid gap-3 sm:grid-cols-[1fr_auto]` and stack below `sm`; long addresses `break-all`. No horizontal overflow at 360 px. Browser check at 360, 768, 1024 and 1440.

### 8.3 Buttons with names and confirmation (parent §6 a11y paragraph)

| Button | Visible text | Accessible name |
|---|---|---|
| Accept | "Accept" | "Accept invitation to {title}" (sr-only suffix; name starts with the visible label, 2.5.3) |
| Decline | "Decline" | "Decline invitation to {title}" |
| Confirm accept / decline | "Confirm accept" / "Confirm decline" | "… invitation to {title}" |
| Go back | "Go back" | "Go back, keep invitation to {title} unanswered" — markup `Go back<span className="sr-only">, keep invitation to {title} unanswered</span>`, so the name contains and starts with the visible label (2.5.3, G1) |
| Opt in | "Opt in" | "Opt in to invitations at {address}" |
| Opt out | "Opt out" | "Opt out of invitations at {address}" |
| Confirm opt out | "Confirm opt out" | "Confirm opt out of invitations at {address}" |
| Keep receiving | "Keep receiving" | "Keep receiving invitations at {address}" |

Every accessible name above is the visible label followed by an sr-only suffix; none uses `aria-label`, so no name can drift from its visible text. All are native `<button type="button">`. While its request is pending, the pressed button uses `aria-disabled="true"` plus a click guard, never `disabled`, so keyboard focus stays on it (§4.2, G2). The confirm row is inline, not a modal (`RedemptionTicketRow.tsx:118-200`): opening it moves focus to the Confirm button; "Go back" / "Keep receiving" closes it and returns focus to the button that opened it.

Focus after a success: once the re-read lands, focus moves to the affected row's `h3` (`tabIndex={-1}`, found by its id). For a channel it is the same row (Contact preferences is not paged; cap 50), whose button has flipped. For an answer it is the row now under "Answered", which is paged, so the row must be on the visible page first (G3):

1. Find the row's index in the freshly read `answered` array.
2. Pass it as `revealIndex` to that `PagedList`, which moves to the page holding it.
3. On the next render the row's `h3` exists; focus it, then set `revealIndex` back to `null`.

Focus is never dropped to `<body>`. After an error, focus stays on the pressed button, which stays mounted and was never `disabled`.

## 9. Tests — written first (TDD)

### 9.1 Harness and local run

- The `CoordinatorRedemptionQueue.test.tsx` harness: `vi.stubGlobal("fetch", …)` keyed `"METHOD path"`; a fresh `QueryClient({ defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } } })` per test; `usePrincipalKey` mocked through a `vi.hoisted` mutable; `usePortalAccess` mocked with a `speaker` descriptor (`home_path: "/speaker-portal"`, `display_name: "Speaker Portal"`); `fireEvent` only (no user-event, no jest-dom); `cleanup()` and `vi.unstubAllGlobals()` in `afterEach`. Pages are rendered inside `createMemoryRouter` + `RouterProvider` where they use links or search params. `@/lib/productScope` is mocked for the capability-on cases.
- Dates pinned with `vi.useFakeTimers({ toFake: ["Date"] })` and `vi.setSystemTime(new Date("2026-10-06T12:00:00Z"))`.
- No bearer-token-looking literal (env rule 8); the token for adapter tests is built at runtime, as T6b-2 §7.6.
- CI: `npm run test:components`. Locally, from a Linux-FS copy, one file at a time (env rule 5):

  ```bash
  cp -r apps/web/legacy-frontend /tmp/t6b4-web && (cd /tmp/t6b4-web && npm ci)   # background, ~16 min
  rsync -a --delete apps/web/legacy-frontend/src/ /tmp/t6b4-web/src/
  (cd /tmp/t6b4-web && npx vitest run --pool=threads <file>)
  ```

  `npx tsc --noEmit -p .` runs in place.

### 9.2 Vitest files

**A. `src/lib/speakerContactChannelsApi.test.tsx`**

1. `fetchMyContactChannels sends GET /v1/me/contact-channels with Authorization`
2. `opt-in and opt-out POST to the encoded channel id with no body`
3. `each §6.1 error code surfaces as ApiRequestError.code with details kept` (`it.each`)
4. `no adapter takes a professional, unit or user id` (arity check: 0, 1, 1)

**B. `src/app/pages/speaker/speakerPortalErrors.test.tsx`** (pure)

1. `every §7 row maps to its message and refetch flag` (`it.each`, one case per row)
2. `suppression_not_liftable picks the message by details.reason; absent reason reads as delivery`
3. `no message contains the server's message text` (the error carries a sentinel message; it never appears in the output)
4. `a non-ApiRequestError reads as the no-reason fallback`

**C. `src/app/pages/speaker/speakerPortalFormat.test.tsx`** (pure)

1. `exact engagement formats in the event's zone` (`America/Los_Angeles`, 17:00Z → "10:00 AM")
2. `date_only says Time not set; unresolved says Date not set yet; null event says details unavailable`
3. `calendar dates never shift a day` (`2026-11-02` at 03:00Z system time)
4. `channelStatusSentence covers every row of the §5.5 table`
5. `engagementStateLabel and invitationStatusLabel cover every enum value`

**D. `src/app/pages/speaker/SpeakerHome.test.tsx`**

1. `loads invitations and upcoming engagements and nothing else` (exactly 2 GETs: `/v1/me/invitations`, `/v1/me/engagements?when=upcoming`)
2. `open invitations come before engagements in DOM order`
3. `shows answerable invitations only, at most 5, with a link to the Invitations page and no answer buttons`
4. `says "at least" when the list is truncated`
5. `each section's empty state` · `a failed invitations read leaves the engagements section working, with Retry`
6. `not linked from either read renders one notice, not two`
7. `query keys are [principal, "my-invitations"] and [principal, "my-engagements", "upcoming"]`

**E. `src/app/pages/speaker/SpeakerInvitations.test.tsx`**

1. `groups rows into Waiting for your answer and Answered`
2. `shows date_text verbatim and the local date when present; says Sent, never delivered`
3. `answered rows say who recorded the answer and never show an id`
4. `Accept opens the confirm row and moves focus to Confirm accept; Go back (named "Go back, keep invitation to {title} unanswered") returns focus to Accept` (G1)
5. `Confirm accept sends exactly one POST {"response":"accept"} to the encoded id`
6. `while pending, the pressed button has aria-disabled="true", keeps focus, reads Saving…, and a second click sends no second POST; every other answer button is disabled; all clear only after the list re-read resolves` (deferred GET after the POST; asserts `document.activeElement`, `hasAttribute("disabled") === false` on the pressed button, and the POST count) (G2)
7. `success announces in role=status only after the 200; recorded:false says nothing changed`
8. `success invalidates exactly [principal, "my-invitations"] and nothing else` (spy on `invalidateQueries`; no `setQueryData`, no engagements key)
9. `after the re-read, focus is on the answered row's heading`
10. `404 not_found, 409 already_answered and 409 response_conflict show their messages and re-read the list` (`it.each`)
11. `403, 429 and network errors keep the row and re-read nothing`
12. `every button's accessible name contains and starts with its visible text, and carries the invitation title` (`it.each` over Accept, Decline, Confirm accept, Confirm decline, Go back: `name.startsWith(textContent visible part)`; no button has `aria-label`) (G1) · `truncated says 200`
13. `Answered pages through PagedList; answering a row that lands on page 2 shows page 2 and focuses that row's heading` (15 answered rows at the default size of 10; the answered row sorts 12th) (G3)
14. `sets document.title to "Invitations · Speaker Portal" and restores the previous title on unmount` (G4)

**F. `src/app/pages/speaker/SpeakerEngagements.test.tsx`**

1. `defaults to upcoming and reads ?when=upcoming`
2. `the Past link sets ?when=past, carries aria-current, and reads that key` (two cache entries, `[pk, "my-engagements", "upcoming"]` and `…"past"`)
3. `an unknown ?when value reads upcoming`
4. `cancelled shows Cancelled on {date} and nothing about who` · `attended and confirmed chips have a word and an aria-hidden icon`
5. `empty upcoming and empty past have their own sentences` · `event null says details unavailable`
6. `no button renders in any row`
7. `engagements page through PagedList; switching Upcoming to Past returns to page 1` (G3)
8. `sets document.title to "Engagements · Speaker Portal"; a ?when change does not move focus` (G4)

**G. `src/app/pages/speaker/SpeakerOwnAvailability.test.tsx`** (stubbed `fetch`, real T5 form)

1. `reads GET /v1/me/availability under [principal, "my-availability"] and never a unit route`
2. `Not stated uses Speaker copy and never says "available"` (`/\bavailable\b/i` absent from `main`)
3. `sources read "Added by you" and "Added by a Speaker Connector"`
4. `save sends one PATCH /v1/me/availability with the T5 body; Save is disabled while pending`
5. `success writes the saved row with setQueryData and invalidates nothing` (spies)
6. `409 stale keeps every typed value, re-reads exactly my-availability, and says This changed`
7. `a response carrying a load field renders no number from it` (stub adds `load: { band: "moderate", utilization: 0.61 }`; neither `0.61` nor `61` appears)
8. `404 speaker_profile_not_linked on GET shows the not-linked notice and no form; on PATCH it keeps the draft`
9. `GET 403 shows the denied notice and no form` · `GET 500 shows Retry, which re-reads`
10. `the form is labelled by the page h1`

**H. `src/app/pages/speaker/SpeakerContactPreferences.test.tsx`**

1. `lists every channel with its address as an h3, status sentence and last set by`
2. `shows only Opt in when can_opt_in, only Opt out when can_opt_out, and the reason when neither`
3. `Opt out asks first; Confirm opt out moves focus in and Keep receiving returns it`
4. `Confirm opt out sends one POST …/opt-out with no body; Opt in sends one POST …/opt-in with no confirm step`
5. `while pending, the pressed button has aria-disabled="true", keeps focus and ignores a second click; other choice buttons are disabled; all clear after the re-read; success invalidates exactly [principal, "my-contact-channels"]` (G2)
6. `each C6 success sentence follows changed and send_eligible from the response` (`it.each`, 5 cases)
7. `each §7 channel code shows its message and re-reads the list` (`it.each`, 6 cases incl. both `details.reason` values)
8. `accessible names carry the address` (`getByRole("button", { name: "Opt out of invitations at dana@example.edu" })`)
9. `the intro links to the Availability page`
10. `after the re-read, focus is on the channel's heading` · `truncated says 50`
11. `sets document.title to "Contact preferences · Speaker Portal"` (G4)

Home (D) and Availability (G) each gain one title case: "Home · Speaker Portal", "Your availability · Speaker Portal" (G4).

**I. `src/app/components/SpeakerPortalLayout.test.tsx`**

1. `signed-out renders SessionGate and no nav` · `no speaker grant renders PortalGate and no nav`
2. `granted renders the nav with 5 links named Home, Invitations, Engagements, Availability, Contact preferences`
3. `the current link has aria-current=page; Home only on the index`
4. `the sidebar shows the server's display name and unit path`
5. `the menu button toggles aria-expanded; Escape closes and returns focus`
6. `hovering a link prefetches exactly that page's keys` (spy on `prefetchQuery`)
7. `navigating from Home to Invitations moves focus to the Invitations h1; the shell's first render moves no focus` (G4)
8. `Sign out directly follows the profile block in the footer` (rendered order: identity block, then Sign out, no element between). The slot comment itself renders nothing, so its position is pinned by §9.3 item 5 (G8)

**L. `src/app/components/PagedList.test.tsx`** (new; G3)

1. `without revealIndex, behaviour is unchanged` (starts on page 1; Next moves to page 2)
2. `revealIndex 12 at page size 10 shows page 2`
3. `revealIndex null after a reveal leaves the page where it is; the same index can be revealed again after null`

**J. `src/app/routes.test.tsx`** (T6b-1's file, updated)

1. `capability off: no speaker-portal route` (unchanged)
2. `capability on: speaker-portal has the layout and the 5 child paths` (replaces T6b-1's placeholder assertion)

**K. `src/app/navPrefetch.test.tsx`** (new)

1. `every /speaker-portal href prefetches the keys its page reads` (keys built from `SPEAKER_SELF_RESOURCE`)
2. `nothing is prefetched while the principal key is null`

**Principal-key isolation** (in D, E and G): switching the mocked principal on one client re-reads and never shows the first principal's rows; no request while the key is `null`.

### 9.3 Python source scans (CI runs `pytest tests/`)

`tests/unit/test_frontend_speaker_portal_contract.py` (the `_code_only` helper of `test_frontend_invitation_compose_contract.py:53`):

0. `test_the_speaker_portal_file_set_exists` (G6), asserted **first** so a missing or renamed file fails by name rather than as a vacuous pass of items 1–5: `app/components/SpeakerPortalLayout.tsx`, `app/hooks/useSpeakerSelf.ts`, and under `app/pages/speaker/` exactly `SpeakerHome.tsx`, `SpeakerInvitations.tsx`, `SpeakerEngagements.tsx`, `SpeakerOwnAvailability.tsx`, `SpeakerContactPreferences.tsx`, `InvitationRow.tsx`, `EngagementRow.tsx`, `ContactChannelRow.tsx`, `SpeakerSelfNotice.tsx`, `speakerPortalErrors.ts`, `speakerPortalFormat.ts`, `useSpeakerPageTitle.ts`. Red from milestone 1 until milestone 8 creates the layout; each intermediate green commit body names it as the one expected red.
1. `test_speaker_pages_call_only_me_routes`: `app/pages/speaker/**` and `app/hooks/useSpeakerSelf.ts` contain no `/v1/units/` literal and none of `fetchSpeakerAvailability(`, `updateSpeakerAvailability(`, `fetchSpeakerContactChannels(`, `fetchSpeakerInvitationBatches(`.
2. `test_contact_channel_adapters_take_no_subject`: the 3 adapters exist with those URLs; no parameter named `professionalId`, `unitId` or `userId`.
3. `test_speaker_portal_reuses_the_t5_form`: `SpeakerOwnAvailability.tsx` imports `SpeakerAvailabilityForm`; no `type="date"` input anywhere under `app/pages/speaker/`.
4. `test_no_optimistic_update_in_the_speaker_portal`: no `onMutate` in the speaker files; `setQueryData` appears once, for `my-availability`.
5. `test_the_t6b5_and_t8d_slots_are_marked`: `SLOT(T6b-5)` twice in `SpeakerPortalLayout.tsx`, the sidebar one **before** the identity block's `principalDisplayName(` call and none between that call and the `Sign out` button (G8); `SLOT(T8d)` once in `SpeakerOwnAvailability.tsx`.

Plus the `test_frontend_auth_contract.py` tuple and loop edits (§1, G7), the two `PAGED_SURFACES` rows in `test_frontend_paged_list_contract.py` (§1, G3), and, unchanged and run one at a time: `test_frontend_no_fake_success_contract.py`, `test_frontend_zero_coercion_contract.py`, `test_frontend_portal_landing_contract.py`, T6b-2's `test_frontend_speaker_self_contract.py`, T3's `test_frontend_speaker_availability_contract.py`.

## 10. Commit milestones (red → green, one commit each, pushed)

Every commit ends with the `Co-Authored-By` trailer. Each red commit body records the red run (for example "A 0/4 pass; module not found").

0. `chore: merge origin/feat/b26-t6b-3 into feat/b26-t6b-4` (brings T6b-2), then `chore: merge origin/feat/b26-t5 into feat/b26-t6b-4` (§0; `make openapi VENV=$VENV` if the JSON conflicted).
1. `test: speaker portal adapters, error map and formatters (red)` — §9.2 A, B, C; §9.3 items 0–2 (item 0 is the file-set check, G6).
2. `feat: /v1/me/contact-channels adapters, speaker portal error map and formatters` — A, B, C green.
3. `test: speaker Home, Invitations and Engagements pages (red)` — D, E, F, L; the two `PAGED_SURFACES` rows.
4. `feat: speaker Home, Invitations and Engagements with useSpeakerSelf hooks` — `PagedList` `revealIndex`, `useSpeakerPageTitle`; D, E, F, L and the paged-list contract green.
5. `test: speaker Availability and Contact preferences pages (red)` — G, H; §9.3 items 3–4.
6. `feat: speaker Availability on the T5 form and Contact preferences opt-in and opt-out` — `COPY.speaker`, the optional `copy` parameter, G, H green.
7. `test: speaker portal shell, routes and prefetch (red)` — I, J, K; §9.3 item 5; the `test_frontend_auth_contract.py` tuple and loop edits.
8. `feat: /speaker-portal shell, nav, prefetch and gated routes` — layout, `routes.tsx`, `navPrefetch.ts`, placeholder deleted; I, J, K and every §9.3 scan green; `npx tsc --noEmit -p .` clean.
9. `docs: DESIGN.md Speaker Portal shell` — plus the browser check at 360, 768, 1024 and 1440 with the capability flipped on locally (not committed), recorded in the PR. The check also covers, keyboard only and with the network throttled so a request stays pending: focus stays on the pressed Confirm accept / Confirm opt out button while it reads "Saving…" (G2); focus lands on the answered row's heading on its page of "Answered" (G3); each route change focuses the new `h1` and the tab title reads "{h1} · Speaker Portal" (G4).

Before each push: `$VENV/bin/ruff format` and `ruff check` on touched Python and this plan.

PR title: `feat: Speaker portal shell and pages (B26 T6b-4)`. Body: line 1 from §0; the test plan (12 Vitest files, tsc, the Python scans); the widths checked; ends with the Claude Code line; edited with `gh api -X PATCH …/pulls/N -F body=@file` (env rule 9).

## 11. Contradictions checked

| # | Found | Handling |
|---|---|---|
| X1 | Revision 1 found T6b-2 §3.1 (404, then 403) and T6b-3 §5.2 (403, then 404, own `speaker_subject.py`) disagreeing. | **Closed.** T6b-3 @ `78432e2f` imports T6b-2's `_authorize_speaker_self` and uses its order; no `speaker_subject.py`. The UI still handles both codes on every page (§5 common rule). |
| X2 | Revision 1 found T6b-2 §6's `SpeakerSelfErrorCode` missing `speaker_invitation_response_conflict`. | **Closed.** T6b-2 @ `f30f85e9` adds it. |
| X3 | The dispatch brief lists `speaker_opted_in` among the opt-in codes. T6b-3 §5.4 returns `speaker_contact_channel_speaker_opted_in` / `_opted_out` only on Connector routes. | Not in the Speaker map (§6.1). Connector copy for them: OQ-3. |
| X4 | T5's `availabilityErrorMessage` has no copy parameter; its not-found path names `speaker_contact_not_found`, which the Speaker route never returns. | Additive `copy` parameter; the Speaker's only 404 is `speaker_profile_not_linked`, handled before delegation (§7). |
| X5 | DESIGN.md `:150-152` says a Speaker has no signed-in shell. | T6b-1 rewrites those sentences (T6b-1 §1 Docs row); T6b-4 only adds shell bullets after them. |

## 12. Open questions — ruled by the orchestrator (2026-09-23)

All five are ruled as recommended; OQ-2 is refined by gate finding G8, and OQ-4 is done upstream. None is open.

| # | Question | Ruling |
|---|---|---|
| OQ-1 | Accept and Decline are both final (T6b-2 C7: a different second answer is 409). The parent asks for confirmation only on opt-out. Confirm both answers too? | **Yes, inline confirm on both** (§8.3). One extra click, no modal, and the confirm text says the answer is final. A mistaken answer otherwise needs a Connector. |
| OQ-2 | Where exactly does T6b-5's switcher go? The parent says "header", but on `lg` and up the shells have no header, only the sidebar (DESIGN.md `:156`: no desktop top bar). | **Sidebar footer, above the identity block** (G8: sign-out stays directly beneath the profile, DESIGN.md `:155`), **plus the mobile header**. Both slots are marked (§2.2); T6b-5 builds. |
| OQ-3 | No track maps the Connector-side `speaker_contact_channel_speaker_opted_in` / `_opted_out` 409s to words on the Connector pages. They fall to a generic error today. | **A small follow-up card** (Connector copy: "The Speaker opted in/out themselves; their choice stands"), not T6b-4: it edits Connector pages that T5, T6b-1 and T8a are also changing. |
| OQ-4 | T6b-2 and T6b-3 disagree on subject-resolution order and on which module owns it (X1). | **Done.** T6b-3 @ `78432e2f` stacks on T6b-2 and imports `_authorize_speaker_self`: one authorizer, one order (404 first, then 403). |
| OQ-5 | Opt-in records `self_service` consent in one click. Should it confirm too? | **No.** The parent asks only for opt-out, opt-in is undoable on the same page, and the success sentence says how to undo it. Revisit if the privacy owner (parent §10 row 2) asks. |

## 13. Out of scope

- The load band on the Availability page (T8d; slot only). The portal switcher (T6b-5; slots only).
- Any Python, route, migration or OpenAPI change. The adapters for T6b-2's routes (T6b-2 writes them).
- A Speaker cancelling a booking or changing an answer (OQ-CBA-044). Paging past 200 invitations or engagements, or 50 channels.
- Adding or editing a contact address (the Speaker Connector does that).
- Turning `SPEAKER_PORTAL` on (T6b-1 C5: T6b-5 merged and parent §10 rows 1, 2 and 4 cleared).
- The parent §7 row 13 e2e click-through.

---

**Next action (under two minutes):** `git log --oneline -3 origin/feat/b26-t6b-2 origin/feat/b26-t6b-3 origin/feat/b26-t5` to see whether any implementation commit has landed yet.
