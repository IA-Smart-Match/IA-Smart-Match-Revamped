# B26 T5 — Connector availability panel in `CoordinatorSpeakerContacts`

**Next action:** once the T3 implementation is pushed, run `git fetch origin && git merge origin/feat/b26-t3` on `feat/b26-t5`. Then write `src/lib/speakerAvailabilityDraft.test.tsx` (§8 file A) and commit it red.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §3.1 (domain limits), §4.1, §6 (T5 row and the accessibility paragraph), §7 row 12, §8 T5.
Inputs: T3 plan (`origin/feat/b26-t3:docs/plans/b26-tracks/T3-plan.md`) and T1 as built (`origin/feat/b26-t1:python/smartmatch_domain/smartmatch_domain/speaker_availability.py`).
Branch `feat/b26-t5`. Frontend only: no route, migration or Python source changes.

**Branch strategy (stacked).** T5 consumes T3's `api.ts` adapter. `origin/feat/b26-t3` holds only T3's plan today (`e1def09a`, `f8c12bfb`), so the build starts once T3's adapter commit is pushed.
The implementer **merges** `origin/feat/b26-t3` into `feat/b26-t5`, which brings T1 and T2 with it. It is a merge, not a rebase, so the pushed plan commit stays.
The PR targets `main`, and the first line of its body is **"Merge #210, #212 and the T3 PR first."** Once those have landed, merge `main` into `feat/b26-t5` so the diff shows T5 only.

**Rulings this plan inherits (orchestrator, final):**

| # | Ruling | Effect here |
|---|---|---|
| T3-C1 | "Today" is the **UTC** date (`utc_now().date()`). | The client computes today as `new Date().toISOString().slice(0, 10)`. The pause `min`/`max` and the window horizon count from that date. |
| T3-C9 | `409 speaker_availability_stale` has **no `details`**. The client re-reads with GET. | The stale path refetches the availability key and never reads a version out of the error. |
| T2-C1 / T3-C4 | `expected_version: null` means "I read `stated: false`". It is required, not optional. | The draft keeps `baseVersion: number \| null` from the read and always sends it. |
| T3 §3 step 6 | A past pause equal to the stored value is dropped to `null` on save. Any other past pause returns `pause_invalid`. | Client validation exempts the unchanged, stored, expired pause, and the UI says that saving clears it (§4.2). |
| T3 §3 | PATCH is a full replace. Omitted windows are deleted. `unavailable: []` keeps `stated: true`. The version increases on every accepted PATCH. | The form always sends every field and every window, in form order. |

## 0. Facts this plan rests on (checked on `feat/b26-t5` = `origin/main` `1909278f`)

1. The page is `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorSpeakerContacts.tsx` (570 lines). It is **not** under `src/pages/`.
   - `ContactRow` is at `:136-230`. It already has a disclosure-style toggle ("Correct classification", `:181-187`, `min-h-11`, focus ring classes).
   - The roster read is at `:245-250`: `useScopedQuery({ resource: "speaker-contacts", params: [unitId] })`.
   - The unit comes from `grantedPortal(usePortalAccess(), "coordinator")?.default_unit_id` (`:238-240`). The page renders nothing while `grant === null` (`:363-365`).
2. `useScopedQuery` (`src/app/hooks/useScopedQuery.ts:77-88`) keys `scopedQueryKey(principalKey ?? "unresolved-principal", resource, ...params)`. It sets `enabled: principalKey !== null && spec.enabled !== false`.
   `scopedQueryKey` is `src/lib/queryClient.ts:74` and returns `[principalKey, resource, ...params]`.
3. `shouldRetryQuery` (`queryClient.ts:148`) never retries a 4xx. A 403 or 404 on GET therefore settles at once.
4. `ApiRequestError` (`src/lib/api.ts:330`) carries `status`, `code` and `details`. `requestJson` (`:484`) sends a relative `/v1/...` path, so a stubbed `fetch` sees `"/v1/units/{u}/speaker-contacts/{p}/availability"`.
5. Two keys are read-time consumers of current availability after T4:
   - `resource: "match-run"`, params `[unitId, runId]` (`src/app/pages/AIMatching.tsx:299-304`), which carries "changed since this run".
   - `resource: "invitation-compose"`, params `[unitId, matchRunId]` (`CoordinatorInvitations.tsx:331-333`), which re-reads the run for the compose re-check.
6. Precedents for idioms:
   - Mutations use `useMutation`, `useQueryClient` and `usePrincipalKey` (`CoordinatorEvents.tsx:292-371`).
   - A 403 is named as a refusal (`VolunteerConfirmedSpeaker.tsx:108` `refusalMessage`).
   - Date-only values are formatted as `new Date(`${d}T00:00:00Z`)` with `timeZone: "UTC"` (`src/app/pages/student/studentPanels.tsx:42-45`), so a calendar date never shifts by a day.
7. Vitest runs only `src/**/*.test.tsx` (`vitest.config.ts`, jsdom, `globals: false`). The CI web job is `npm run test:components` (`package.json:13`).
   - Installed: `@testing-library/react` 16 and `@testing-library/dom` 10.
   - **Not installed:** `@testing-library/user-event`, `jest-dom` and `axe`. Tests use `fireEvent` and plain DOM assertions (the `CoordinatorRedemptionQueue.test.tsx` style), and no dependency is added.
8. T6b-1 renders its new `pages/coordinator/SpeakerPortalInvite.tsx` from `ContactRow` too (T6b-1 plan §1). Both tracks add one element to `ContactRow`, so whichever PR merges second resolves a small conflict.
9. The source scans that cover every file:
   - `tests/unit/test_frontend_auth_contract.py:214` scans all `src/**/*.ts(x)`: no `fetchMe()`, no `sessionStorage` access.
   - `test_frontend_opportunities_contract.py:213`: no `x.value / y.value` division.
   - `test_frontend_paged_list_contract.py:52` pins `contacts` paging in this page. It must stay green.

## 1. Files

| Path | Change |
|---|---|
| `apps/web/legacy-frontend/src/lib/speakerAvailabilityDraft.ts` | **New**, pure (no React). Holds the draft types, `draftFromAvailability`, `payloadFromDraft`, `isDraftUnchanged`, `validateDraft`, `utcToday`, `addMonths`, `spanDays`, `formatCalendarDate`, `availabilityErrorMessage`, `readInput`, and the `COPY.connector` string table. The limits are re-declared here with a comment citing T1 (§5). |
| `apps/web/legacy-frontend/src/app/components/speakerAvailability/SpeakerAvailabilityForm.tsx` | **New**, presentational. It renders the state line, the form, the status region and the error regions, and holds the draft in local state. Props are in §2. T6b-4's Speaker page reuses it with a `COPY.speaker` table. |
| `apps/web/legacy-frontend/src/app/pages/coordinator/SpeakerAvailabilityPanel.tsx` | **New**, the Connector wiring. It holds the query, the mutation, invalidation, the stale re-read, and the read-side loading, denied and error states. It sits beside T6b-1's `SpeakerPortalInvite.tsx`. |
| `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorSpeakerContacts.tsx` | `ContactRow` gains an "Availability" disclosure button, which mounts the panel only when open. Add a module docstring section, "Availability is the Speaker's statement, not ours" (§4.1). |
| `apps/web/DESIGN.md` | One bullet under "Speaker roster and invitation workflow": Connectors read and correct a Speaker's stated availability from the roster row; "Not stated" is never shown as available. |
| Tests (new) | `src/lib/speakerAvailabilityDraft.test.tsx`, `src/app/components/speakerAvailability/SpeakerAvailabilityForm.test.tsx`, `src/app/pages/coordinator/SpeakerAvailabilityPanel.test.tsx`, `src/app/pages/coordinator/CoordinatorSpeakerContacts.test.tsx` (§8). All are `.test.tsx` so CI runs them. |

**Consumed from T3, not edited:** `fetchSpeakerAvailability`, `updateSpeakerAvailability`, and the types `SpeakerAvailability`, `SpeakerAvailabilityWindowView`, `SpeakerAvailabilityUpdatePayload` and `SpeakerAvailabilityErrorCode` (T3 plan §5). If T3's names differ as built, follow T3 and note the difference in the PR.

**Not touched:** `navPrefetch.ts`. The panel reads on demand when it opens, not on page load, so there is nothing to pre-warm. `routes.tsx` and the nav are not touched either.

## 2. Component structure

```text
CoordinatorSpeakerContacts
└─ PagedList → ContactRow (per contact)
   ├─ [Correct classification] (existing)
   ├─ [Availability] disclosure button   aria-expanded, aria-controls="availability-panel-{pid}"
   └─ {open && <SpeakerAvailabilityPanel unitId professionalId contactName />}
      ├─ <section id="availability-panel-{pid}" aria-labelledby="availability-heading-{pid}" aria-busy={loading}>
      │   <h3 id="availability-heading-{pid}">Availability</h3>
      ├─ read states: loading | denied | not found | error+Retry   (panel-owned)
      └─ <SpeakerAvailabilityForm
            idPrefix="availability-{pid}"  availability={data}  today={utcToday()}
            copy={COPY.connector}  saving={mutation.isPending}
            stale={staleState}  serverError={mapped}  savedAt={lastSavedAt}
            onSave={(payload) => mutation.mutate(payload)}
            onDiscardStale={...} />
```

- **`SpeakerAvailabilityPanel` props:** `{ unitId: string; professionalId: string; contactName: string }`. It takes no principal: that comes from `usePrincipalKey()` inside.
- **`SpeakerAvailabilityForm` owns the draft.** It re-seeds from `availability` only when:
  - it mounts;
  - a save succeeds (the response is the new truth);
  - the user chooses "Discard my changes".

  A background refetch **never** overwrites what the user typed. That is what keeps input through a stale re-read.
- **Draft shape** (`speakerAvailabilityDraft.ts`):

  ```ts
  interface WindowDraft { key: string; starts_on: string; ends_on: string; startsBad: boolean; endsBad: boolean }
  interface AvailabilityDraft {
    baseVersion: number | null;          // version the draft was read at; null = stated:false
    pause: string; pauseBad: boolean;    // "" = no pause; YYYY-MM-DD
    capacity: string; capacityBad: boolean; // "" = not stated — never "0"
    windows: WindowDraft[];              // form order == request order == server error index
  }
  ```

  `key` is a per-form counter (`w1`, `w2`, …), not a date, so two windows with the same dates stay distinct. The `…Bad` flags record `input.validity.badInput` (§5, rule 0).
- `payloadFromDraft(draft, expectedVersion)` produces:
  - `pause` → `string | null`;
  - `capacity` → `Number(capacity)` or `null` (a JSON number, T3 C6);
  - `windows` → `{ starts_on, ends_on }[]` in form order, **never sorted**, so `details.index` from the server names the same row.

## 3. Queries, mutation and invalidation

**Read.** Only while the disclosure is open:

```ts
useScopedQuery({
  resource: "speaker-availability",
  params: [unitId, professionalId],
  queryFn: () => fetchSpeakerAvailability(unitId, professionalId),
})
// key: [principalKey, "speaker-availability", unitId, professionalId]
```

T6b-4's Speaker page uses its own resource (`"my-availability"`, T6b-4's call), never this one.

**Write.** `useMutation({ mutationFn: (payload) => updateSpeakerAvailability(unitId, professionalId, payload) })`.

- There is no optimistic update.
- Save is disabled and reads "Saving…" while `isPending`, and a second click is ignored.
- `onSuccess(saved)`, in this order:
  1. `queryClient.setQueryData(scopedQueryKey(principalKey, "speaker-availability", unitId, professionalId), saved)`. The PATCH response is the committed row read back (T3 §3 step 9). Writing it into the cache is an update with server data, not an optimistic one. It gives the form the new `version` at once, so a quick second save cannot 409 against the user's own write.
  2. `invalidateQueries({ queryKey: [principalKey, "match-run", unitId] })`. This is a prefix over every run in the unit, because "changed since this run" (T4 §3) is computed at read time from current availability.
  3. `invalidateQueries({ queryKey: [principalKey, "invitation-compose", unitId] })`. This is a prefix too, because the compose re-check reads current availability.
  4. Re-seed the form from `saved`, and set `lastSavedAt = saved.updated_at`.

  **Nothing else** is invalidated. The roster (`speaker-contacts`) does not carry availability.
- On `speaker_contact_not_found` (GET or PATCH), invalidate `[principalKey, "speaker-contacts", unitId]`, because the roster row is now wrong (§4, state 9).
- On `speaker_availability_stale`, run `refetchQueries({ queryKey: <availability key>, exact: true })` (§4.3).

**Principal isolation.** The principal is always the first key segment, through `useScopedQuery` and `scopedQueryKey`. Every `invalidateQueries`/`setQueryData` call builds its key from `usePrincipalKey()`, never from a literal. While the principal key is `null`, the query does not run and the mutation button is disabled.

## 4. UI states

Every state renders inside the panel `<section>`. "Speaker" and "Speaker Connector" are the product's role words (`DESIGN.md` role names).

| # | State | Trigger | What renders |
|---|---|---|---|
| 1 | **Loading** | `query.isPending` | `aria-busy="true"` on the section, plus the text "Loading availability…". The form is not shown, and the status region is not used for loading. |
| 2 | **Not stated** | `stated === false` | The state line reads "**Not stated.** This Speaker has not said when they can speak, so matching treats their availability as unknown." It never says "Available". The form is empty. The primary button reads **"Save: no dates blocked"** while the draft is empty, and "Save availability" once anything is entered. A hint beside it says: "Saving an empty form records that this Speaker told you they have no dates blocked. Only save if they did." |
| 3 | **Stated, nothing blocked** | `stated`, no windows, pause `null` or expired | "**Stated: no dates blocked.**" Capacity reads "{n} hours per 90 days" or "Capacity not stated". A `null` capacity is never shown as 0. Then "Last changed {date, time} by the Speaker / by a Speaker Connector" (`updated_source`, `updated_at`). |
| 4 | **Windows / paused** | `stated`, with windows or an active pause | "**Stated:** {k} blocked date range(s)." When `pause >= today`, it adds "Invitations paused until {date}." Each window fieldset shows "Added by the Speaker" or "Added by a Speaker Connector" when its `(starts_on, ends_on)` matches a stored window. New and edited windows show "Not saved yet". |
| 5 | **Stale** | PATCH → `409 speaker_availability_stale` | See §4.3. The draft is kept, the panel re-reads, and it says "Someone changed this". |
| 6 | **Save error** | any other PATCH failure | A message from §6 goes in the right `role="alert"` region. The draft is kept and focus rules follow §7. |
| 7 | **Read error** | GET fails, not 403/404 | "Availability could not be loaded. {server message}", plus a **Retry** button (`refetch()`, which is safe for a GET). No form is shown. |
| 8 | **Denied** | GET → 403 | "The server refused this request (403). {message} Reading a Speaker's availability is granted to Speaker Connectors in this unit; this account was not granted it here." There is no form and no claim that a record exists. A PATCH 403 shows the same words as a save error, and the draft is kept. |
| 9 | **Not found** | GET or PATCH → `404 speaker_contact_not_found` | "This contact is no longer in your unit's roster, so its availability cannot be read or saved." The roster is re-read (§3). |
| 10 | **Saved** | PATCH 200 | The status region says "Availability saved {time from `updated_at`}." The form re-seeds from the response. Success is shown only after the 200. |

### 4.1 Wording rules

- Nothing in the panel contains the word "available" (`/\bavailable\b/i`) in any state. The capacity label is "Capacity (hours per 90 days)". This keeps "Not stated" from ever reading as "Available" (§8 test C2).
- Dates render through `formatCalendarDate("2026-11-02")`, which gives "November 2, 2026". It uses `new Date(`${d}T00:00:00Z`).toLocaleDateString("en-US", { dateStyle: "long", timeZone: "UTC" })`, the `studentPanels.tsx:42` idiom with a fixed locale so tests are deterministic.
- `updated_at` renders with `toLocaleString()` like `VolunteerConfirmedSpeaker.tsx:96`.
- No version number is shown to the user.

### 4.2 Expired pause

The stored `invitations_paused_until` can be earlier than today. GET does not hide it (T3 §3).

- The input keeps the stored value, so the form does not silently change.
- The hint reads: "This pause ended on {date}. Saving clears it."
- `validateDraft` exempts `pause === stored && stored < today`, which mirrors T3's drop rule. After the save, the response has `null` and the form re-seeds to empty.
- A **different** past date fails client validation with the `pause_invalid` message.

### 4.3 Stale path (409)

1. `onError` sees `code === "speaker_availability_stale"`. The draft (every field and window) is left **as typed**, and `staleState = { at: Date.now() }`.
2. The panel re-reads the availability key with an exact refetch. The form does not re-seed, per the rule in §2.
3. The form-level `role="alert"` reads: "**Someone changed this** availability since you opened it. Your changes are still in the form and were not saved."
4. Under the alert, a read-only "Saved now" summary is built from the fresh read: the state line, the pause, capacity, the windows, and "last changed … by …". The user can compare it with their draft.
5. The primary button keeps its DOM position and focus, and its label changes to **"Save my changes over it"**. Clicking it sends the draft with `expected_version = fresh.version`, or `null` if the fresh read says `stated: false`.
6. A secondary **"Discard my changes"** button re-seeds the draft from the fresh read and clears the stale state.
7. If the re-read itself fails, the alert keeps the stale text and adds the read error. The draft is still kept, and "Save my changes over it" stays disabled until a read succeeds, with the reason shown.

   Rationale: without a fresh version there is nothing to send, and T3 C9 forbids guessing one.

The client never retries a stale PATCH automatically. Each overwrite is one explicit click after the saved version has been shown.

## 5. Client-side validation (courtesy; the server decides)

`validateDraft(draft, today, stored)` returns the **first** failure, `{ code, field, index? }`, in T1's order (`validate_availability_statement`: capacity, pause, count, windows). It uses the same codes, so one message table (§6) serves both client and server errors. The server stays authoritative:

- a draft that passes locally is still sent, and any 422 is shown;
- the client never blocks a value the server might accept, except where T1 is certain.

The limits are re-declared from T1 (`speaker_availability.py` as built): `MAX_WINDOWS = 20`, `WINDOW_MAX_SPAN_DAYS = 366`, `WINDOW_HORIZON_MONTHS = 18`, `PAUSE_HORIZON_MONTHS = 12`, `CAPACITY_MAX = 720`, 1 decimal place.

| Order | Rule | Client check | Code |
|---|---|---|---|
| 0 | Unreadable input | `capacityBad`, `pauseBad`, `startsBad` or `endsBad` is set. A number or date input with half-typed text reports `value === ""` and `validity.badInput === true`. Without this check a typo would save as "not stated" or "no pause". | Field-specific: "Enter a number of hours, like 24 or 24.5." / "Enter a full date." |
| 1 | Capacity | Blank → `null` (allowed). Otherwise it must match `/^\d{1,3}(\.\d)?$/`, and `0 < Number(v) <= 720`. | `speaker_availability_capacity_invalid` |
| 2 | Pause | Blank → `null`. Otherwise `today <= p <= addMonths(today, 12)`, **except** the unchanged, stored, expired pause (§4.2). | `speaker_availability_pause_invalid` |
| 3 | Count | `windows.length > 20`. The UI cannot reach this, because "Add" is disabled at 20. It is kept for parity. | `speaker_availability_too_many_windows` |
| 4 | Each window, in form order | Both dates present (blank → `window_invalid`, the server would send `invalid_request`); `ends_on >= starts_on`; `spanDays <= 366`; `ends_on <= addMonths(today, 18)`; not equal to an earlier window (the **later** index is reported). Past windows are allowed. | `speaker_availability_window_invalid`, `index` |

- `addMonths` mirrors T1's `_add_months`: calendar months, with the day clamped to the month's end. For example, `addMonths("2026-08-31", 18)` is `"2028-02-29"`.
- `spanDays` uses `Date.UTC` differences, so no zone is involved.
- `today` is `utcToday()` (T3-C1). Near UTC midnight the client and server can disagree by one day, and the server's answer is the one shown.
- Native constraints are set as information, not enforcement:
  - pause: `min={today}`, `max={addMonths(today, 12)}`;
  - windows' "To": `max={addMonths(today, 18)}`;
  - capacity: `min="0.1" max="720" step="0.1" inputMode="decimal"`.

  The `<form>` has `noValidate`, so the page's own messages (§6) are what the user gets, the same in every browser.
- Client-only, specific window messages add a reason the server cannot give (T1 reports only the code and index): "Window 2: the end date is before the start date." / "…covers more than 367 days." / "…ends after {max date}." / "…repeats window 1." / "…needs both dates."

## 6. Error code → message map (`availabilityErrorMessage(code, details, draft)`)

Branch on `ApiRequestError.code` or on `status`, never on message text (DESIGN.md "Queries, mutations, and errors"). Window numbers are 1-based: `details.index + 1`. The server never echoes a value, and neither does the client, except the user's own dates for the window it names.

| Status | Code | Where it shows | Message |
|---|---|---|---|
| 409 | `speaker_availability_stale` | form alert | "Someone changed this availability since you opened it. Your changes are still in the form and were not saved." (then §4.3) |
| 422 | `speaker_availability_window_invalid` | alert on window `details.index` | "Window {i+1} ({from} to {to}) cannot be saved. The end must be on or after the start, the range can cover at most 367 days, it must end by {addMonths(today,18)}, and it cannot repeat another window." |
| 422 | `speaker_availability_too_many_windows` | alert beside "Add unavailable dates" | "A Speaker can have at most 20 blocked date ranges. Remove one, then save again." (Uses `details.limit` when present.) |
| 422 | `speaker_availability_pause_invalid` | alert on the pause input | "The pause must end today ({today}) or later, and no later than {addMonths(today,12)}. Dates count in UTC." |
| 422 | `speaker_availability_capacity_invalid` | alert on the capacity input | "Capacity must be more than 0 and at most 720 hours per 90 days, with at most one decimal place. Leave it blank if not stated." |
| 404 | `speaker_contact_not_found` | panel (state 9) | "This contact is no longer in your unit's roster, so its availability cannot be read or saved." |
| 404 | `unit_not_found` | form alert / panel | The server's message, plus "Nothing was changed." |
| 403 | `forbidden` (any 403) | form alert / panel (state 8) | "The server refused this request (403). {message} … Nothing was changed." (the `refusalMessage` shape) |
| 422 | `invalid_request` | form alert | "The server could not read this form, so nothing was saved. {message}" |
| 429 | `rate_limited` | form alert | "Too many requests just now. Wait a moment, then save again. Your changes are still in the form." |
| 401 | `unauthenticated` | form alert | "Your session has ended. Sign in again; your changes on this page were not saved." |
| — | anything else, or not an `ApiRequestError` | form alert | "Availability could not be saved and the server gave no reason. Nothing was changed; your changes are still in the form." |

After a server 422 with a field (`details.field`/`details.index`), focus moves to that field. For a window, that is its "From" input. The error is attached there (§7).

## 7. Accessibility — WCAG 2.2 AA

**Disclosure (in `ContactRow`).**

- It is a `<button type="button">` with `aria-expanded` and `aria-controls="availability-panel-{pid}"`.
- Its visible text is "Availability", with `<span className="sr-only"> for {full_name}</span>`. The accessible name starts with the visible label (2.5.3) and tells rows apart.
- Its classes are `min-h-11` (2.5.8) plus the existing focus ring.
- When the panel closes, focus stays on the button.

**Structure.**

- The panel is a `<section aria-labelledby>` with an `<h3>`. The page outline is h1 "Speaker contacts" → h2 "This unit's contacts" → h3 "Availability".
- The form is `<form noValidate aria-labelledby="availability-heading-{pid}">`.

**Inputs.** All inputs are native, and every one has a persistent `<label htmlFor>`.

- **Pause:** `<input type="date" id="{p}-pause">`, labelled "Pause invitations until". Its hint `{p}-pause-hint` reads "Optional. The last day no invitations go out. Latest {date}." A **"Clear pause"** button follows it.
- **Capacity:** `<input type="number" id="{p}-capacity">`, labelled "Capacity (hours per 90 days)". Its hint reads "Optional. Leave blank if not stated."
- Each input has `aria-describedby="{hint-id}"`. When it has an error, `aria-describedby` becomes `"{hint-id} {error-id}"` and `aria-invalid="true"` is set.

**Windows.**

- The outer `<fieldset>` has `<legend>Dates this Speaker cannot speak</legend>`. Inside is an ordered list, with one nested `<fieldset>` per window and `<legend>Unavailable dates {n}</legend>`.
- Each window has two date inputs, labelled "From" (`{p}-w{key}-from`) and "To, inclusive" (`{p}-w{key}-to`). The labels are scoped by the legend, so each group reads "Unavailable dates 2, From".
- The **remove** button's visible text is "Remove". Its accessible name comes from an sr-only suffix:
  - "Remove unavailable dates November 2, 2026 to November 6, 2026";
  - with dates missing: "Remove unavailable dates {n} (no dates yet)".
- The **"Add unavailable dates"** button is disabled at 20 windows. `aria-describedby` points at the visible reason: "20 is the most a Speaker can have. Remove one to add another."

**Focus management.**

- Add → focus the new window's "From".
- Remove → focus the next window's "From", else the previous window's "From", else "Add unavailable dates". Focus is never dropped to `<body>`.
- Client or server field error → focus the invalid input.
- Stale → focus stays on the primary button, which keeps its element and changes its label (§4.3).
- Success → focus stays where it is, and the status region announces.

**Live regions.**

- **Exactly one** `role="status"` region per panel (`{p}-status`). It is always mounted, and it carries only save results: "Availability saved …" and "Changes discarded."
- **Errors.** Only one error is shown at a time, matching T1's first-failure rule:
  - A field error is `<p id="{field}-error" role="alert">` beside its field, linked from the field's `aria-describedby`.
  - A form-level error (stale, 403, 429, network) goes in `<div id="{p}-form-error" role="alert">`. It is always mounted and empty until used, so the reference from the Save button's `aria-describedby` always resolves (the T8a pattern).
  - A new submit clears the previous error before it sets the next one, so nothing is announced twice.

**Keyboard order.** DOM order equals visual order, with no `tabIndex > 0`:

1. Pause date
2. Clear pause
3. Capacity
4. For each window: From, To, Remove
5. Add unavailable dates
6. Save (or "Save my changes over it")
7. Discard changes / Discard my changes (only when there is something to discard)

**Buttons.**

- Save is disabled when the draft equals the stored statement (`isDraftUnchanged`) and `stated` is true. The visible reason "No changes to save." is linked by `aria-describedby`.
- In Not stated, Save is never disabled for being unchanged (state 2).
- While saving, Save is disabled and reads "Saving…".
- All buttons are at least 44 px (`min-h-11`), with the CPP focus ring.

**Layout.** Window rows use `grid gap-3 sm:grid-cols-[1fr_1fr_auto]` and stack below `sm`. There is no horizontal overflow at 360 px. Check at 360, 768, 1024 and 1440 widths in the browser pass.

**Other.** Icons are `aria-hidden="true"`. Nothing is conveyed by color alone: the state line and the source labels are text.

## 8. Tests — Vitest, written first (TDD)

- **CI:** `npm run test:components` (`vitest run`, `src/**/*.test.tsx`).
- **Locally**, from a Linux-FS copy, one file at a time (env rule 5):

  ```bash
  cp -r apps/web/legacy-frontend /tmp/t5-web && (cd /tmp/t5-web && npm ci)  # background, ~16 min
  rsync -a --delete apps/web/legacy-frontend/src/ /tmp/t5-web/src/
  (cd /tmp/t5-web && npx vitest run --pool=threads <file>)
  ```

  `npx tsc --noEmit -p .` runs in place.
- **Harness:** the `CoordinatorRedemptionQueue.test.tsx` pattern:
  - a `vi.stubGlobal("fetch", …)` keyed by `"METHOD path"`;
  - a fresh `QueryClient({ defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } } })` per test;
  - `usePrincipalKey` mocked through a `vi.hoisted` mutable (`principal.key`);
  - `fireEvent` only;
  - `cleanup()` and `vi.unstubAllGlobals()` in `afterEach`.
- **Dates** are pinned with `vi.useFakeTimers({ toFake: ["Date"] })` and `vi.setSystemTime(new Date("2026-10-06T03:00:00Z"))`. Only `Date` is faked, so TanStack's timers and `waitFor` still run. Real timers are restored in `afterEach`.
- No bearer-token-looking literal appears in any test (env rule 8).

**A. `src/lib/speakerAvailabilityDraft.test.tsx`** (pure)

1. `utcToday returns the UTC date` (at 2026-10-06T03:00Z, which is 5 Oct in Pacific, → `"2026-10-06"`).
2. `addMonths clamps to month end`: `2026-08-31 +18 → 2028-02-29`; `2027-08-31 +18 → 2029-02-28`; `2026-10-06 +12 → 2027-10-06`.
3. `draftFromAvailability: stated false gives an empty draft with baseVersion null` · `stated keeps server window order and sources` · `null capacity is "" never "0"`.
4. `payloadFromDraft: blanks become null, capacity is a JSON number, windows keep form order, expected_version is baseVersion`.
5. `validateDraft reports the first failure in T1 order`. Parametrized cases:
   - capacity `0`, `-1`, `720.1`, `24.05` → invalid; `0.1`, `720`, `""` → ok;
   - pause yesterday → invalid; today → ok; today+12m → ok; today+12m+1d → invalid;
   - `21 windows → too_many`;
   - blank date, reversed, span 367 → invalid; span 366 → ok; past today+18m → invalid;
   - duplicate → reports the later index;
   - a past window → ok.
6. `an unchanged stored expired pause is exempt; a changed past pause is not`.
7. `badInput on capacity or a date is an error, not a blank`.
8. `availabilityErrorMessage covers every §6 code` (`it.each`) · `window message uses index+1 and the draft's dates` · `unknown code falls back and does not echo the server message as a value`.

**B. `src/app/components/speakerAvailability/SpeakerAvailabilityForm.test.tsx`**

1. `pause and capacity are native inputs with visible labels`. `getByLabelText` returns `type="date"` with `min`/`max` = today / today+12m, and `type="number"` with `min="0.1" max="720" step="0.1"`.
2. `each window is a group named by its legend` (`getByRole("group", { name: "Unavailable dates 2" })`), and `From` and `To, inclusive` are found within it.
3. `remove buttons are named with their dates`: "Remove unavailable dates November 2, 2026 to November 6, 2026". A blank window gets "… {n} (no dates yet)".
4. `adding focuses the new From input` · `removing focuses the next, else previous, else Add`.
5. `Add is disabled at 20 with a described reason`.
6. `a client error sets role=alert, aria-invalid and aria-describedby, moves focus, and calls no onSave`.
7. `keyboard order follows the documented sequence`: the accessible names of the focusable elements, in DOM order, match §7.
8. `there is exactly one role=status region`.
9. `unchanged stated draft disables Save with a reason` · `not-stated empty draft offers "Save: no dates blocked"`.
10. `a new availability prop from a refetch does not overwrite typed input`.

**C. `src/app/pages/coordinator/SpeakerAvailabilityPanel.test.tsx`** (stubbed `fetch`, real adapter)

1. `loading sets aria-busy and a label before GET resolves` (a deferred response).
2. `not stated says Not stated and never "available"` (`/\bavailable\b/i` absent from the section's text).
3. `stated with nothing blocked says so and shows "Capacity not stated", never 0`.
4. `windows render with their source; an active pause is named; an expired pause says saving clears it`.
5. `save sends exactly one PATCH with the exact body` (expected_version echoed, windows in form order).
   - `Save is disabled and reads Saving… while pending`.
   - `success announces in role=status and re-seeds from the response`.
   - `a second save sends the new version without a GET in between`.
6. `409 stale keeps every typed value, re-reads with GET, and says Someone changed this` · `Save my changes over it sends the fresh version with the draft` · `Discard my changes re-seeds from the fresh read` · `no automatic retry after 409`.
7. `422 window_invalid with details.index 1 attaches the error to window 2 and focuses its From input`.
8. `each §6 code shows its message and keeps the draft` (`it.each` over every §6 row).
9. `GET 403 renders the refusal and no form` · `PATCH 403 keeps the draft`.
10. `GET 500 shows Retry, which re-reads` · `404 speaker_contact_not_found shows the roster message and invalidates the speaker-contacts prefix`.
11. **Principal-key isolation:**
    - `the query key is [principal, "speaker-availability", unit, professional]` (`client.getQueryCache().getAll()`);
    - `switching principal on one client fetches again and never shows the first principal's data`: the stub answers principal-1 and principal-2 with different capacities;
    - `no request while the principal key is null`.
12. `success writes the availability key and invalidates exactly the match-run and invitation-compose prefixes` (spies on `setQueryData` and `invalidateQueries`; the exact arguments; no other call).

**D. `src/app/pages/coordinator/CoordinatorSpeakerContacts.test.tsx`** (new)

1. `each row has an Availability disclosure named with the contact, with aria-expanded and aria-controls`.
2. `no availability GET until a row is opened; one GET per opened row`.
3. `the roster still pages` (it keeps the `PagedList` behaviour the Python scan pins).

**Python safeguards (run one at a time, and unchanged):** `tests/unit/test_frontend_paged_list_contract.py`, `test_frontend_auth_contract.py`, `test_frontend_opportunities_contract.py`, `test_frontend_no_fake_success_contract.py`, `test_frontend_zero_coercion_contract.py`, and T3's `test_frontend_speaker_availability_contract.py`.

## 9. Commit milestones (one commit each, pushed)

0. `chore: merge origin/feat/b26-t3 into feat/b26-t5` — the stacked base (T1 + T2 + T3 adapter).
1. `test: failing T5 availability draft, form, panel and roster tests` — all four §8 files, red. The commit body records the red summary (for example, "A 0/8, B 0/10, C 0/12, D 0/3 pass; modules not found").
2. `feat: speaker availability draft model, validation and error messages` — `speakerAvailabilityDraft.ts`; file A green.
3. `feat: SpeakerAvailabilityForm with labelled date and number inputs` — file B green.
4. `feat: Connector availability panel in CoordinatorSpeakerContacts` — the panel, the `ContactRow` disclosure and the docstring. Files C and D green; `npx tsc --noEmit -p .` clean; the §8 Python scans green.
5. `docs: DESIGN.md availability panel bullet` — plus a browser check at 360 and 1440 px, recorded in the PR.

PR title: `feat: Connector availability panel (B26 T5)`.

- The first body line is **"Merge #210, #212 and the T3 PR first."**
- The body includes a test plan (the four Vitest files, tsc, and the Python scans) and the browser widths checked.
- It ends with the Claude Code line.
- Edit the body with `gh api -X PATCH …/pulls/N -F body=@file` (env rule 9).

## 10. Out of scope

- The load band. That is T8d, and T3 adds `load` as an additive field, which T5 ignores.
- The Speaker's own page. That is T6b-4, which reuses `SpeakerAvailabilityForm` with `COPY.speaker`.
- "Invite to portal". That is T6b-1.
- A roster-level "stated" column. It would need a list endpoint.
- Clearing a statement back to "Not stated". T3 has no DELETE (OQ-1).

## 11. Open questions (none blocks the build)

| # | Question | Recommendation |
|---|---|---|
| OQ-1 | Once saved, a statement cannot return to **Not stated**, because T3 has no DELETE. A Connector who saves by mistake has made "said free" permanent until it is edited. | Keep the explicit "Save: no dates blocked" label and hint (state 2) for the pilot. Log a follow-up card for a `DELETE …/availability` route (T3-level work), not in T5. |
| OQ-2 | After a 409, should the Connector be allowed to overwrite? | Yes: "Save my changes over it" only after the fresh saved version is shown, one explicit click, no auto-retry (§4.3). Forcing a discard would lose a phone-call correction. |
| OQ-3 | Invalidating the `match-run` and `invitation-compose` prefixes goes beyond the availability key. | Keep it. Both compute "changed since" or the re-check from current availability at read time (T4). Invalidation only refetches mounted queries, so the cost is small. |
| OQ-4 | "Today" is UTC (T3-C1). After 17:00 Pacific, a Connector cannot pause until the local today's date. | Accept, as ruled. The hint shows the concrete earliest and latest dates, so the refusal is never a surprise. |
| OQ-5 | Open-on-demand (one GET per opened row) versus showing every row's state up front (N GETs). | Open on demand. A roster-level state needs a batched read. Card it with T8d if Connectors ask. |

---

**Next action (under two minutes):** `git fetch origin && git log --oneline origin/feat/b26-t3 -3` to see whether the T3 adapter commit has landed yet.
