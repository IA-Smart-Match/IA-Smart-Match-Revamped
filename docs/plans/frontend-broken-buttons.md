# Legacy frontend — broken and lying interactive controls

**Companion to** [`frontend-migration.md`](frontend-migration.md).
**Scope:** every button, link, or control in `apps/web/legacy-frontend/` that
does not perform the action it advertises, or that performs it against a
missing / archived / invented backend.
**Not in scope:** shadcn primitive `disabled:` CSS, sidebar open/close, calendar
view switching that only changes local view state, and landing in-page anchors
that do what they say.

Effort: **S** = wire to an existing contract or delete a stub (hours);
**M** = new API resource + UI (days);
**L** = blocked on a gate, ADR, or program-owner decision (weeks+).

**Count: 42 controls. Last surveyed 2026-09-22** against `main` at `012080f1`
(PR #205 merged): **40 closed, 2 still open** (B09 partly, B26 — both wait on an owner decision; B41 and B42 closed by `fix/open-broken-buttons`). No new
dead control was found on any coordinator page — see *Coordinator re-survey*
below for what was checked.

Paths follow the original survey: `src/…` is relative to
`apps/web/legacy-frontend/`; bare `student/…`, `coordinator/…`, `volunteer/…`
paths sit under `src/app/pages/`; `pages/…` and `app/…` under `src/` or
`src/app/` as written; bare `components/…` is the legacy `src/components/`. Line numbers are as of the survey date. A ✅
row keeps its ID and says what the defect was, what replaced it, and the commit
that closed it.

---

## Auth and public

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B01 ✅ *closed — pilot sign-in is real* | `src/app/pages/LoginPage.tsx:192` form, `:238–245` **Sign in** | **Was:** `mockLogin(email, role)` POST `{ email, role }` to a 404 route. **Now:** `submitCredentials` → `postLogin` → `POST /v1/auth/login` (`src/lib/api.ts:1960–1975`) with email + password only; identity is then read from `GET /v1/me`. The server's `LoginRequest` rejects a `role` field with 422. | Authenticate with Identity Platform; role from membership, never from the body. | `/v1/auth/login` + `/v1/auth/logout` **in `smartmatch.json`** — pilot-scoped, per `docs/decisions/pilot-login-decision-2026-09-04.md`. A1b (JWKS / IdP) is still the long-term replacement. | **Closed by `131b6793`** (PR #35). Swap to OIDC when A1b lands; the form carries no role input to remove. | — |
| B02 ✅ *closed — cards removed* | `LoginPage.tsx` **role cards** | **Removed.** No role cards, no role `<select>`, no canned demo emails; the file's header says why and `tests/unit/test_frontend_auth_contract.py` guards it. | No caller-chosen role. | None — forbidden (Fix #7). | **Closed by `169b95d1`** (Fix #7A). | — |
| B03 ✅ *closed — no role in the CTA* | `LandingPage.tsx:77–82`, `:105–108`, `:239–241` | Every CTA is `Link to="/login"`; no `?role=` query. `roleFromUrl` is gone from `LoginPage.tsx`. | CTA to real auth with no role in the query string. | — | **Closed by `169b95d1`.** | — |
| B04 ✅ *closed — shell retired, real principal + sign-out* | `app/components/CoordinatorPortalLayout.tsx:299–304` identity, `:416` **Sign out** | `Layout.tsx` (the admin shell with the hard-coded “IA Admin” / `admin@ia.org`) is **deleted**; admin and coordinator share `CoordinatorPortalLayout`, which shows `principalDisplayName(session.me)` from `GET /v1/me` and a Sign-out that revokes the session. | Show the verified principal; sign-out clears the real session. | `/v1/me`, `/v1/auth/logout` | **Closed by `e76fcd26`** (PR #156). | — |

---

## Student portal

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B05 ✅ *closed — button gone* | `student/StudentHome.tsx:206–218` | **Removed.** No nudge CTA is rendered. A `MissingCapability` panel names the absent `/api/portals/students/{id}/nudge` read and says no `/v1` route recommends or nudges. | Perform the nudge’s action using `nudge.nudge_type` / `event_id`. | Student nudge + commands: **no counterpart** (engagement tables S6–S10). | **Closed by `131b6793`** by taking the second option: no button until the command exists. Re-open as new work if a nudge command ships. | — |
| B06 ✅ *closed — Register is a real command* | `student/StudentEvents.tsx:267–275` **Register / Cancel registration**; `StudentHome.tsx:105–110` **Browse all events** | The Home link is relabelled “Browse all events” (`c9435cea`). The Events page carries a **Register** button per event: `registerForEvent` → `POST /v1/units/{unit_id}/student/events/{event_id}/registration` (cancel is `DELETE`). Label comes from the server’s `registration` row on every read; a refused write shows the server’s message; repeat clicks are idempotent. | Registration command (idempotent), or the label must say “View events”. | **Shipped:** migration `0026` `event_registration` table (OQ-CBA-018 resolved), both verbs in `smartmatch.json`. | **Closed by `f788e61a`** (PR #61) + `c9435cea` (PR #156). | — |
| B07 ✅ *closed — button gone, endpoint shipped, link now rendered* | `student/StudentEvents.tsx:277–279` **calendar download** | **Removed.** `handleAddToCalendar` and its 3 s “Calendar event added” toast went with the rest of the legacy page body. Each event now renders the server’s `calendar` object: a download link where `download_path` is set, else the reason (`event_time_unresolved`, `event_end_unknown`, `event_not_on_your_agenda`). | Download ICS from `smartmatch_domain.ics` for a *resolved* event; refuse `unresolved` (F-003). | **Shipped:** `GET /v1/units/{unit_id}/events/{event_id}/invite.ics` returns `text/calendar` bytes through `calendar_invite.build_invite_ics`; refuses with `409 event_time_unresolved` / `event_end_unknown` / `event_not_presentable`; `admin`+`coordinator` unit-wide, `student` only with an `attendance_record` or active registration (else `404`). The Calendar *API* stays gated at G5 — `docs/plans/open-questions/calendar-deferred.md`. | **Closed by `CBA-STUDENT-EVENTS`** (`34f5e9bc`). The link is **not** composed in the browser. `tests/contract/test_student_events_api.py` asserts the field and then calls the .ics route, requiring the two to agree. | — |
| B08 ✅ *closed — dead link removed; check-in still absent* | `student/StudentEvents.tsx` **QR / check-in** | **Removed.** The `<a href="/api/qr/stats">` is gone; no QR or check-in control is rendered on any student page. | Phone-first check-in with a reusable token (v1.1 §1.9, MM-F02). | **No counterpart.** S6, S11, D8 (minimization copy). | **Link closed by `131b6793`.** The check-in *capability* is still new work (L); do not reuse `/qr/stats`. | L (new feature) |
| B09 ✅ *partly closed — grid is real, cells still inert* | `StudentEvents.tsx:336–427` `MonthCalendar` | Prev/next month buttons (`:372–385`) work; day cells are non-interactive, and the caption under the grid says so. | Time-ordered agenda of registered + open events (Fix #10). | Event read API: **shipped** (`/student/events`, `/student/agenda`). Registration: **shipped** (B06). | **Mostly done.** Two time-ordered lists lead the page; the grid sits below them (customer §15). Registering is done from the lists, not a day cell. Whether a day should open or filter anything is **OQ-CBA-020**, still open — its own precondition (“decide once registration exists”) is now met by B06, so it is ready for the owner, and no handler is added until it is decided; ordering is pinned by `tests/unit/test_student_events_layout_contract.py`. | S |
| B10 ✅ *closed — button gone* | `student/StudentConnect.tsx:65–103` | **Removed.** No peer list, no Connect button, no local `Set`, no `stableHash` “Connected”. The page is a `MissingCapability` panel (“People to connect with”) plus links to the two real surfaces. | Opt-in LinkedIn URL the peer supplied, or a coordinator-mediated mentor request (ADR-0014). | `disclosure_consent` (S10) **blocked on D8**. No student-scoped roster route exists at any path. | **Closed by `131b6793`.** Building the feature is still L, blocked on D8. | L (new feature) |
| B11 ✅ *closed — button gone* | `StudentConnect.tsx` | **Removed** with B10 (`speakerRequested` `Set` gone). | Same as B10. | S10, contact consent — HTTP **none**. | **Closed by `131b6793`.** | L (new feature) |
| B12 ✅ *closed — deleted* | `StudentConnect.tsx` **Chat** | **Removed**, with `makeMockThreadMessages`. | In-app chat is archived (MM-F04, Fix #11). | None — do not build. | **Closed by `169bf4b3`** (PR #7). | — |
| B13 ✅ *closed — deleted* | `StudentConnect.tsx` **Send** | **Removed** with B12. | N/A — control should not exist. | None | **Closed by `169bf4b3`.** | — |
| B14 ✅ *closed — real redemption command* | `student/StudentRewards.tsx:179–184` **Request redemption** | `onRequest` → `useRewards.requestItem` (`app/hooks/useRewards.ts:184`) → `requestRedemption` → `POST /v1/units/{unit_id}/redemptions` (`src/lib/api.ts:2720`). Label is “Requesting…” in flight, “Not enough points” when the server’s `affordable` is false. Tickets list from `GET …/redemptions`. No local `Set`, no browser points formula. | `redemption` command: requested → approved → fulfilled \| denied \| expired (ADR-0013, S9). | **Shipped:** `GET`/`POST /v1/units/{unit_id}/redemptions`; coordinator side `GET …/redemptions/queue` (PR #200) and `POST …/redemptions/{redemption_id}/decision`, surfaced by `coordinator/CoordinatorRedemptionQueue.tsx` at `/coordinator-portal/redemptions` (PR #205). | **Closed by `a1dbb9bd`** (PR #32). | — |
| B15 ✅ *closed — ledger-backed* | `StudentHome.tsx:163–168` `PointsPanel`, `:184–189` **See the catalogue** | Balance is `rewards.balance` from `GET /v1/units/{unit_id}/rewards`; “N of M funded rewards are within your balance” counts the server’s `affordable` flags. `getStudentTotalPoints` is gone. | Navigate to a ledger-backed catalog. | S7 — shipped with the rewards API. | **Closed by `c9435cea`** (PR #156) on top of `a1dbb9bd`. | — |
| B16 ✅ *closed — tile gone, rows shown* | `student/StudentHistory.tsx:95–150` | **Removed.** No “Total Attended” number; the page lists the past rows themselves (`PagedList`, `:136`) from `GET …/student/agenda`, and deliberately avoids the word “attended” because the route unions attendance and registration. | Drill-down to the same attendance rows; performance budget S11. | `/student/agenda` — shipped. | **Closed by `131b6793`** (tile) + `c9435cea` (rows). | — |

---

## Coordinator portal

Re-surveyed after the Track-D restyle and PR #205. The coordinator portal is now
also the admin shell (`e76fcd26`, PR #156): `/dashboard`, `/opportunities`,
`/events`, `/ai-matching`, `/pipeline`, `/calendar`, `/volunteers` and
`/outreach` redirect into it (`app/legacyRedirects.ts`).

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B17 ✅ *closed — Send submits a durable command* | `coordinator/CoordinatorOutreach.tsx:663–677` **Send** | `outreach.sendDraft` (`app/hooks/useOutreach.ts:217`) → `submitOutreachSend` → `POST /v1/units/{unit_id}/outreach/drafts/{draft_id}/send`. Disabled unless the draft is `approved`; on `202` the page says “queued”, never “sent”; delivery status is read back from `…/outreach/sends`. | Consent-gated outreach command; never send to scraped addresses (F-004, `consent.py`). | **Shipped** (R4): drafts, send, sends. Consent re-checked at delivery. | **Closed by `9a82d5ab`** (PR #37). Fake success removed earlier in `131b6793`. | — |
| B18 ✅ *closed — control gone* | `CoordinatorOutreach.tsx` **create thread** | **Removed.** No thread UI at all: `/v1` outreach stores drafts and sends, with no inbound leg (OQ-008), and the page says so rather than renaming sends “threads”. | Create a durable thread/command for a named event. | None — a thread is not a shape this API has. | **Closed by `131b6793`.** | — |
| B19 ✅ *closed — button gone* | `CoordinatorOutreach.tsx` **Agentic outreach** | **Removed** from the page. `components/AgenticOutreachPanel.tsx` still exists but has **no importer** — dead file. | Jarvis is R5 and must not be a parallel send path (DESIGN.md §1.7). | **No counterpart.** | **Closed by `131b6793`.** Delete the orphan file. | S to delete file |
| B20 ✅ *closed — deleted* | `components/AgenticOutreachPanel.tsx` **Approve & Send** | **Removed**; replaced with a non-interactive “Draft only. No send path exists” note. Panel is now unmounted anyway (B19). | Same confirmation UI as conventional send. | Send path now exists (B17), but not from the stream. | **Closed by `169bf4b3`** (PR #7). | — |
| B21 ✅ *closed — deleted* | `AgenticOutreachPanel.tsx` **Reject** | **Removed** with B20. | Audited rejection of a draft command. | — | **Closed by `169bf4b3`.** | — |
| B22 ✅ *closed — real meeting record* | `coordinator/CoordinatorMeetings.tsx:319` form, `:375–383` **Record meeting** | **Was:** `handleBook` + `console.log` + 2.5 s fake success. **Now:** `createMeeting` → `POST /v1/units/{unit_id}/meetings` (`src/lib/api.ts:5127`) with `scheduled_at` (offset ISO), `time_zone`, optional `location_or_link`; refuses to submit when the browser cannot name a zone; list is re-read after the write. The page says on screen that this is an internal record — no invitation, no calendar write. | Scheduling command storing UTC + IANA zone + precision (ADR-0010). ICS only until G5. | **Shipped:** migration `0034`, `routers/meetings.py`. No per-meeting .ics (G5). | **Closed by `131b6793`** (fake removed) + `e845513f` (PR #130). | — |
| B23 ✅ *closed — no link rendered* | `CoordinatorMeetings.tsx:168–170` | **Removed** `href={mtg.meeting_link}`. `location_or_link` is shown as **plain text** exactly as a coordinator typed it; nothing renders it as a clickable join URL. | Only render provider links that the server marked as observed. | `GET /v1/units/{unit_id}/meetings` — shipped. | **Closed by `131b6793`.** | — |
| B24 ✅ *closed — replaced by a real match run* | `coordinator/CoordinatorEvents.tsx:770–788`; successor `CoordinatorSpeakerRequests.tsx:310` **Start a match** → `CoordinatorMatchRuns.tsx:683–690` **Submit match run** | **Removed** the `Link` to `/ai-matching`. Events page has a “Staffing is not part of this listing” section linking to outreach. Matching starts from a filed Speaker Request: `POST /v1/units/{unit_id}/match-runs`; the run’s shortlist is `/coordinator-portal/match-runs?run={id}` (`AIMatching.tsx`, which now only links on to `invitations?run=` at `:457`). | Coordinator intake command for staffing. | **Shipped:** speaker requests, `POST …/match-runs`. | **Closed by `131b6793`** (link) + the match-runs track (router comment: “Card B24’s replacement”). | — |
| B25 ✅ *closed — actions first, rows drill down* | `coordinator/CoordinatorHome.tsx:804–868` `ActionQueue`, rendered first at `:1113` | Home now leads with “What needs your attention”: each row’s number is the length of the list the linked page reads from the **same route** (speaker requests, review queue, invitation batches), and the match-runs row states why it has no number. Measured aggregates (Speaker Pipeline, attendance, feedback) follow. | Actions first; click-through is same-query drill-down; when n is small, list names (Fix #13). | Coordinator reads: shipped for the rows shown. | **Closed by `0280baa2`** (PR #156). The aggregate cards below now open their rows too — see B41/B42. | — |

### Coordinator re-survey (2026-09-22) — no new dead controls

Every `<button>` in `app/pages/coordinator/*.tsx`, `RedemptionTicketRow.tsx`,
`app/components/CoordinatorPortalLayout.tsx` and `app/components/speakerPipeline/*`
has an `onClick`, is `type="submit"` on a form with a handler, or is a Radix
`TooltipTrigger` (`PipelineMetricGrid.tsx:73`, opens the metric definition). No
`console.log`, `setTimeout` success, `alert()` or `href="#"` remains. Every
in-app link targets a mounted route. Pages checked:

| Page | Route | Controls and what they call |
|---|---|---|
| `CoordinatorHome.tsx` | `/coordinator-portal` | Action-queue links only; counts from the linked pages’ own routes. |
| `CoordinatorSpeakerRequests.tsx` | `…/speaker-requests` | Open / Back (`:132`, `:233`), **Start a match** (`:310`) → `match-runs?request=`. |
| `CoordinatorReviewQueue.tsx` | `…/review-queue` | Accept / Reject (`:175`, `:183`) → review-item decision. |
| `CoordinatorRedemptionQueue.tsx` + `RedemptionTicketRow.tsx` (PR #205) | `…/redemptions` | Status tabs (`:156`); per-ticket moves and two-step **Deny → Confirm deny / Keep** (`RedemptionTicketRow.tsx:159–195`) → `useRedemptionQueue.decide` → `POST …/redemptions/{redemption_id}/decision`. |
| `CoordinatorEvents.tsx` | `…/events` | New / Edit / **Save draft** / **Publish event** / Refresh (`:478`, `:204`, `:720–745`) → `/v1` manual-event routes; feedback QR save + PNG/SVG download (`components/QRCodeCard.tsx:221–245`). |
| `CoordinatorMatchRuns.tsx`, `AIMatching.tsx` | `…/match-runs[?run=]` | **Submit match run** (`:683`); shortlist → invitations link. |
| `CoordinatorInvitations.tsx` | `…/invitations[?run=]` | Compose submit (`:639`) → `POST …/speaker-invitations/batches`; without `?run=` the page says “Open a shortlist first” and blocks submit. |
| `CoordinatorMeetings.tsx` | `…/meetings` | B22. |
| `CoordinatorSpeakerContacts.tsx` | `…/speaker-contacts` | Expand (`:183`), **Save correction** (`:216–221`), **Add contact** submit (`:486–492`). |
| `CoordinatorSpeakerFeedback.tsx` | `…/speaker-feedback` | Read-only aggregate. |
| `CoordinatorOutreach.tsx` | `…/outreach` | B17 Send; **Open** batch (`:334`), **Send invitations** (`:363`) → dispatch; **They accepted / They declined** (`:260–269`) → record response. |
| `CoordinatorMatchingWeights.tsx` | `…/matching-weights` | **Save weights** (`:337–342`) → `PATCH …/matching-weights`; Retry (`:363`). |

---

## Volunteer / professional portal

The volunteer portal is now the **Event Host** portal (Home, Request a speaker,
My requests, Organization, Profile).

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B26 | `volunteer/VolunteerProfile.tsx` **(missing Save)** | Still no editor. The page now shows only the signed-in principal and a `PortalDatasetUnavailable` panel for `/api/portals/volunteers/{id}` — the fabricated region / board role / fatigue % display is gone (`131b6793`). The host’s *organization* is editable on `VolunteerOrganization.tsx`; the person’s own availability and workload are not. | Professionals must correct the data used about them (DESIGN.md §1.6). | ELI + profile write: **none** (eli.py proposed; D2). | **Still open — owner decision.** Nothing stores an availability or workload for any principal today, and the glossary defines an Event Host as the role that files a Speaker Request, *not* a speaker (`docs/architecture/GLOSSARY.md:92`); ELI (`smartmatch_domain/eli.py`) measures speakers, and its open D2 sub-question is about committed future engagements. What an Event Host may correct about themselves is therefore a product decision, not an endpoint to wire. Add editors only after it is decided and the write API exists. | L |
| B27 ✅ *closed — page retired* | `volunteer/VolunteerAssignments.tsx` | **Unrouted.** `/volunteer-portal/assignments` redirects to `/volunteer-portal` (`app/legacyRedirects.ts`); the file is an unmounted `PortalDatasetUnavailable` stub. Event Hosts file and track speaker requests instead of accepting assignments. | Accept/decline command; ICS from `ics.py`; rest/availability feeds ELI. | Speaker-side accept/decline now exists as `/v1/speaker-invitations/respond` and the coordinator-recorded response (B17 page). | **Closed by `e76fcd26`** (redirect). Delete the orphan file. | S to delete file |
| B28 ✅ *closed — nav targets are real* | `volunteer/VolunteerHome.tsx:106`, `:217`, `:221`, `:249`, `:275` | Links go to Organization, Request a speaker and My requests — all `/v1`-backed pages. No link to Assignments remains. | Keep nav; pair with B26/B27. | — | **Closed by `98440ce3`** (PR #156). | — |

---

## IA admin portal

**Every page in this section is unmounted.** `Dashboard.tsx`, `Opportunities.tsx`,
`Pipeline.tsx`, `Outreach.tsx`, `Events.tsx`, `Calendar.tsx` and `Volunteers.tsx`
have no importer; their addresses redirect into the coordinator portal
(`e76fcd26`, PR #156). Only `AIMatching.tsx` is still mounted, as the
`match-runs?run=` shortlist. Rows below are closed where the control is gone or
unreachable; the files still holding legacy calls are listed under *Dead code
left behind*.

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B29 ✅ *closed — control gone* | `pages/Dashboard.tsx` **Connect** | **Removed** `handleConnect`; `initiateWorkflow` has no caller outside `src/lib/api.ts`. Page unmounted. | Consent-gated outreach command; job id + SSE. | Shipped as B17 on the coordinator outreach page. | **Closed by `db0eb09e`** (PR #7) + `e76fcd26`. | — |
| B30 ✅ *closed — control gone* | `pages/AIMatching.tsx` **Initiate outreach** | **Removed** `openWorkflowModal`. The mounted page’s only control is the link to `invitations?run=` (`:457`), which composes through `POST …/speaker-invitations/batches`. | Same as B29. | G1 + match_run: shipped. Send: B17. | **Closed by `69611b2f`** (PR #7). | — |
| B31 ✅ *closed — control gone* | `AIMatching.tsx` **Log feedback** | **Removed** the `FeedbackForm` trigger; `components/FeedbackForm.tsx` has no importer. | Feedback command; empty set must not become 0% (S2). | Domain `feedback.py`; **no HTTP**. R2. | **Closed by `69611b2f`.** A feedback command is still new work if wanted. | — |
| B32 ✅ *closed — deleted* | `pages/Outreach.tsx` **Save Draft** | **Removed.** | Persist a draft. | Shipped as `/v1/units/{unit_id}/outreach/drafts`. | **Closed by `169bf4b3`** (PR #7). | — |
| B33 ✅ *closed — deleted* | `Outreach.tsx` **AI Enhance** | **Removed.** | Labeled model output (R5). | — | **Closed by `169bf4b3`.** | — |
| B34 ✅ *closed — unreachable* | `Outreach.tsx:155`, `:286`, `:425` **Generate / Refresh** | Handler still calls `generateEmail` → `POST /api/outreach/email`, but the page is **unmounted**; `/outreach` redirects to the coordinator outreach page. | Deterministic template labeled “AI unavailable” if no model. | — | **Closed by `e76fcd26`.** Delete the file. | S to delete file |
| B35 ✅ *closed — unreachable* | `Outreach.tsx:192`, `:294`, `:433` **ICS** | Still calls `generateIcs` → `POST /api/outreach/ics`; page unmounted. The real .ics route is the event invite (B07). | Domain `ics.py` only; refuse unresolved. | Shipped for events (B07). | **Closed by `e76fcd26`.** Delete the file. | S to delete file |
| B36 ✅ *closed — unreachable* | `Outreach.tsx:215` **Referral QR** (`QRCodeCard` referral variant) | Still calls `generateQrAsset` → `POST /api/qr/generate`; page unmounted. The only mounted QR is the per-event **feedback** QR on `CoordinatorEvents.tsx:751`, generated locally and saved through `/v1`. | Attendance QR (MM-F02). | — | **Closed by `e76fcd26`.** Attendance check-in is still B08’s open feature. | S to delete file |
| B37 ✅ *closed — deleted* | `Outreach.tsx` **Create Template** | **Removed.** | Save a named template or do not offer Create. | — | **Closed by `169bf4b3`.** | — |
| B38 ✅ *closed — surface retired* | `components/CrawlerFeed.tsx` **Start crawl** | **Removed.** The component is a static “Web-crawler surface retired” card (MM-A08, G3) and is rendered only by the unmounted `Outreach.tsx`. `startCrawl` survives only in `src/lib/api.ts`. | R3 research scout, after crawler threat model. | **No counterpart.** | **Closed by `b1204ed7`** (PR #7). | — |
| B39 ✅ *closed — surface retired* | `CrawlerFeed.tsx` **Clear / load saved** | **Removed** with B38. | Same as B38. | None | **Closed by `b1204ed7`.** | — |
| B40 ✅ *closed — control gone* | `pages/Opportunities.tsx` **Run matcher** | **Removed** the `navigate("/ai-matching")`; page unmounted and `/opportunities` redirects to speaker requests, where matching starts for real (B24). | Matching after G1/M8. | Shipped (B24). | **Closed by `df4e2181`** (PR #7) + `e76fcd26`. | — |
| B41 ✅ *closed — every measured card opens its rows* | was `pages/Dashboard.tsx` **MetricCard** links; live successor `components/speakerPipeline/PipelineMetricGrid.tsx:81` on `CoordinatorHome.tsx:1120` | Each KPI card with a measured value renders that value as a `<button type="button">` named “Open the N rows behind …” (`PipelineMetricGrid.tsx:81–90`). It opens `MetricDrilldownSheet` (`SpeakerPipelineSection.tsx:188`), which fetches the server-issued `drill_down_url` from the same `speaker-pipeline` payload (`fetchMetricDrillDownAt`, `lib/api.ts:2239`) and refuses to render rows that do not reconcile with N. An unmeasured card has no button. Pipeline rows name the furthest stage reached (`lib/metrics.ts:223`). | Clicking N opens the N rows from the owning query (ADR-0011). | Metric register: **shipped** (S12). Drill-down read: **shipped** — `GET /v1/units/{unit_id}/metrics/{metric_name}/drill-down?surface=cba`, served from `_OWNING_QUERIES` in `routers/metrics.py`, `admin`/`coordinator` only (metrics-authorization decision §4). No new endpoint was needed. | **Closed by `fix/open-broken-buttons`.** `SpeakerPipelineSection.test.tsx` (click → the server’s link → N rows; unmeasured → no button; 403 → the server’s refusal); `tests/contract/test_speaker_pipeline_api.py::test_every_figure_drills_down_to_exactly_its_own_rows` follows every `drill_down_url` and asserts `len(rows) == value`. | — |
| B42 ✅ *closed — every measured band opens its rows* | was `pages/Pipeline.tsx` **funnel tiles**; live successor `components/speakerPipeline/PipelineFunnelCard.tsx:130` | Each band with a measured count is a `<button type="button">` with the same geometry (`Band`, `PipelineFunnelCard.tsx:130`) and the same opener as its KPI card, so band and card open the one `drill_down_url`. An unmeasured band stays a plain outlined shape. | One owning query (S12); each tile drills down (S1). | S12 shipped; S1 drill-down **shipped** (same route as B41). | **Closed by `fix/open-broken-buttons`**, same tests as B41. | — |

---

## Dead code left behind

Not controls a user can reach — listed so nobody re-mounts them by accident.
Each still calls a legacy `/api/*` path that is not in `smartmatch.json`.

| File | Still calls | Rows |
|---|---|---|
| `app/pages/Outreach.tsx` | `/api/outreach/email`, `/api/outreach/ics`, `/api/qr/generate` | B34–B36 |
| `app/pages/Dashboard.tsx`, `DashboardSections.tsx` | links to `/calendar`, `/ai-matching` (now redirects) | B29, B41 |
| `app/pages/Pipeline.tsx`, `Opportunities.tsx`, `Events.tsx`, `Calendar.tsx`, `Volunteers.tsx` | legacy admin reads | B40, B42 |
| `components/AgenticOutreachPanel.tsx`, `components/FeedbackForm.tsx`, `components/OutreachWorkflowModal.tsx` | `/api/outreach/agentic-workflow/stream`, `/api/feedback/submit`, `/api/outreach/workflow` | B19–B21, B29–B31 |
| `app/pages/volunteer/VolunteerAssignments.tsx` | none (stub) | B27 |

---

## Cross-cutting controls that look live

These are not extra IDs; they are how several rows above fail in the same way.
Status as of 2026-09-22.

| Pattern | Where | What to do | Status |
|---|---|---|---|
| `console.log` + `setTimeout` success | B17, B18, B22 | Ban in the new app. Success requires a 2xx of a command that committed. | **Gone from every mounted page** — no `console.log` or `setTimeout` success in `app/pages/coordinator/`. B17 reports “queued” on `202`, never “sent”. |
| Local `Set` as “request sent” | B10, B11, B14 | Ban. Optimistic UI only after an accepted command id. | **Gone.** B10/B11 removed; B14 and B06 render the server’s row after each write. |
| Vite proxy `/api` and `/v1` → API | `vite.config.ts:54–68` | Keep as a *dev* proxy to the revamped API, not as a promise that legacy paths exist. | Unchanged in intent; `/v1` is now proxied too. |
| `DemoModeBadge` | `app/components/provenance/SyntheticDataMarker.tsx`; the unmounted `Dashboard.tsx`, `Pipeline.tsx`, `Volunteers.tsx` | Not a substitute for per-value provenance. Do not treat “we showed the badge” as Fix #8 closed. | Unchanged guidance. |
| Fallback people `stu-001` / `coord-001` / `shana-demarinis` | Was every portal `getSession` | If session missing → login, never a default id. | **Gone.** Every portal page reads `GET /v1/me` via `useAuthenticatedPrincipal`, which throws rather than substitute a fixture principal (Fix #7). |

---

## Mapping to OpenAPI

**This section is superseded.** At the first survey none of the 42 controls
bound to a path in `contracts/openapi/smartmatch.json`. On 2026-09-22 every
**mounted** control named in this doc that performs an action calls a path that
is in the contract:

| Row | Control | Path in `smartmatch.json` |
|---|---|---|
| B01 | Sign in | `POST /v1/auth/login` |
| B04 | Sign out | `POST /v1/auth/logout` |
| B06 | Register / Cancel registration | `POST` / `DELETE /v1/units/{unit_id}/student/events/{event_id}/registration` |
| B07 | Calendar download | `GET /v1/units/{unit_id}/events/{event_id}/invite.ics` |
| B14 | Request redemption | `POST /v1/units/{unit_id}/redemptions` |
| — | Coordinator ticket decision (PR #205) | `POST /v1/units/{unit_id}/redemptions/{redemption_id}/decision` |
| B17 | Send | `POST /v1/units/{unit_id}/outreach/drafts/{draft_id}/send` |
| B22 | Record meeting | `POST /v1/units/{unit_id}/meetings` |
| B24 | Submit match run | `POST /v1/units/{unit_id}/match-runs` |

The legacy `/api/*` calls that remain live only in the files listed under
*Dead code left behind*, none of which is mounted.

---

## Suggested deletion set

The original S-effort set (B02, B12, B13, B20, B21, B32, B33, B37, B38, B39) is
**done** — each control is gone. What is left to delete is files, not controls:
the *Dead code left behind* table above, plus the legacy `/api/*` client
functions in `src/lib/api.ts` that only those files call (`initiateWorkflow`,
`generateEmail`, `generateIcs`, `generateQrAsset`, `startCrawl`,
`submitFeedback`). Deleting them changes no reachable behaviour; grep
`apps/web/legacy-frontend/tests/` and `tests/` for source-scanning guards first.

Still open and not deletable: B09 (OQ-CBA-020, owner decision) and B26 (what an
Event Host may correct about themselves, owner decision; then a profile write API).
B41/B42 are closed: both open the shipped S1 drill-down.
