# Frontend migration plan — legacy inventory, defect catalog, and phasing

**Status:** planning only. No screens, clients, or wiring are authorized by this
document.
**Legacy source:** `Nebiux-Team-IA-West-SmartMatch@bdce024` (the
`legacy_sha` pinned in `docs/migration/migration-manifest.yaml`).
**Copy in this tree:** `apps/web/legacy-frontend/` (retrieved 26 August 2026;
presentational inventory only — not the new web app).
**Blocked on:** `apps/web/DESIGN.md` (D-0). Architecture v1.1 §5.1 forbids a
hand-maintained client. Gate G1 blocks match-run screens.

This plan answers four questions: what the old frontend *is*, what in it is
broken or invented, what in the current backend it could honestly connect to,
and in what order a later team should rebuild. It does not authorize building
anything. `apps/web/README.md` remains on hold.

---

## 0. How to read this document

- **Inventory** is descriptive of the copy under `apps/web/legacy-frontend/`.
- **Defect catalog** (`H-*` hard-coded / invented data, `B-*` broken
  interactives) is exhaustive against that copy. The focused button checklist
  lives in [`frontend-broken-buttons.md`](frontend-broken-buttons.md).
- **Backend mapping** is against `contracts/openapi/smartmatch.json` as it
  stands today (five public resources) plus domain packages under
  `python/smartmatch_domain/` and the R1/R2 backlog. A row marked **no
  counterpart** means the current API cannot serve that screen truthfully.
- **Phasing** follows `apps/web/DESIGN.md` sequencing (W4 before W3 and W5) and
  `docs/plans/remaining-foundation-r1-work.md`. It is a plan, not a schedule.

Do not port `mockData.ts`, `mockProfilePhotos.ts`, `studentPoints.ts`, the
in-browser rewards catalog, or the MM-A01 login client. Those are the defects
this revamp exists to end.

---

## 1. Full inventory of the old frontend

**Framework.** React 18.3 + TypeScript + Vite 6 (`package.json`). Router is
`react-router` 7 (`createBrowserRouter` in `src/app/routes.tsx`). Styling is
Tailwind CSS 4 plus a large shadcn/Radix primitive set under
`src/app/components/ui/` (49 files), with leftover MUI (`@mui/material` 7) and
Emotion declared but barely used in pages. Charts are Recharts. Motion is
`motion`. Toasts are Sonner (wired, almost unused). The Vite dev server proxies
`/api` to `http://127.0.0.1:8000` (`vite.config.ts`).

**Not in this copy.** No `node_modules`, no `dist` / `.next` / `build`. The
legacy Streamlit UI (`Category 3…/src`) and the Figma mockup
(`docs/mockup/V1.1/IA-West_UI`) were not copied; this directory is the Vite
app only.

### 1.1 Routes

From `src/app/routes.tsx`. **There are no route guards.** Any URL is
reachable without a session. Role is a client suggestion stored in
`sessionStorage` key `iaw_session`.

| Path | Page module | Audience (claimed) | Layout |
|---|---|---|---|
| `/` | `LandingPage.tsx` | public | none |
| `/login` | `LoginPage.tsx` | public | none |
| `/student-portal` | `student/StudentHome.tsx` | student | `StudentLayout` |
| `/student-portal/events` | `student/StudentEvents.tsx` | student | `StudentLayout` |
| `/student-portal/history` | `student/StudentHistory.tsx` | student | `StudentLayout` |
| `/student-portal/connect` | `student/StudentConnect.tsx` | student | `StudentLayout` |
| `/student-portal/rewards` | `student/StudentRewards.tsx` | student | `StudentLayout` |
| `/coordinator-portal` | `coordinator/CoordinatorHome.tsx` | event coordinator | `CoordinatorPortalLayout` |
| `/coordinator-portal/events` | `coordinator/CoordinatorEvents.tsx` | event coordinator | `CoordinatorPortalLayout` |
| `/coordinator-portal/outreach` | `coordinator/CoordinatorOutreach.tsx` | event coordinator | `CoordinatorPortalLayout` |
| `/coordinator-portal/meetings` | `coordinator/CoordinatorMeetings.tsx` | event coordinator | `CoordinatorPortalLayout` |
| `/volunteer-portal` | `volunteer/VolunteerHome.tsx` | professional / speaker | `VolunteerPortalLayout` |
| `/volunteer-portal/assignments` | `volunteer/VolunteerAssignments.tsx` | professional / speaker | `VolunteerPortalLayout` |
| `/volunteer-portal/profile` | `volunteer/VolunteerProfile.tsx` | professional / speaker | `VolunteerPortalLayout` |
| `/dashboard` | `Dashboard.tsx` | IA admin | `Layout` |
| `/opportunities` | `Opportunities.tsx` | IA admin | `Layout` |
| `/volunteers` | `Volunteers.tsx` | IA admin | `Layout` |
| `/ai-matching` | `AIMatching.tsx` | IA admin | `Layout` |
| `/pipeline` | `Pipeline.tsx` | IA admin | `Layout` |
| `/calendar` | `Calendar.tsx` | IA admin | `Layout` |
| `/outreach` | `Outreach.tsx` | IA admin | `Layout` |

Twenty-one page modules. Four portal shells plus a public landing/login pair.
This is the “four portal experiences, two landing pages” `DESIGN.md` warns
against reproducing without a navigation decision (D-5).

### 1.2 Components (non-primitive)

| Module | Role |
|---|---|
| `src/app/components/Layout.tsx` | Admin shell. Hard-codes footer identity “IA Admin” / `admin@ia.org`. No sign-out. |
| `src/app/components/StudentLayout.tsx` | Student shell; reads `iaw_session`; sign-out clears storage. |
| `src/app/components/CoordinatorPortalLayout.tsx` | Coordinator shell; same session pattern. |
| `src/app/components/VolunteerPortalLayout.tsx` | Volunteer shell; same session pattern. |
| `src/app/components/CrawlerContext.tsx` | Polls crawler status for the admin banner. |
| `src/app/components/MetricCard.tsx` | Admin KPI tile. Optional `href` navigates to a *different* page, not a same-query drill-down. |
| `src/app/components/ScrollToTop.tsx` | Scroll reset on navigation. |
| `src/app/components/figma/ImageWithFallback.tsx` | Image fallback. |
| `src/app/components/ui/DemoModeBadge.tsx` | Page-level “demo” chip. Not a per-value provenance label. |
| `src/components/AppIcon.tsx` | Named icon map. |
| `src/components/CrawlerFeed.tsx` | Start / clear / poll crawler. |
| `src/components/QRCodeCard.tsx` | Generate + download QR asset. |
| `src/components/FeedbackForm.tsx` | Accept/decline + submit feedback. |
| `src/components/OutreachWorkflowModal.tsx` | Displays `initiateWorkflow` result; “Upgrade to Agentic” jumps portals. |
| `src/components/AgenticOutreachPanel.tsx` | SSE client for `/api/outreach/agentic-workflow/stream`. |

Plus 49 shadcn/Radix primitives (button, dialog, sheet, chart, sidebar, …).
Licensing of the upstream set is **D-1 / MM-F01** — confirm before any reuse.

### 1.3 State management

There is **no** Redux, Zustand, React Query, or generated API cache.

- **Session:** `sessionStorage["iaw_session"]` JSON `{ user, role }`, written
  only by `LoginPage.handleLogin`. Every portal page re-parses it and falls
  back to a hard-coded id (`stu-001`, `coord-001`, `shana-demarinis`).
- **Server data:** per-page `useState` + `useEffect` fetch. Failures on admin
  pages swap in `src/lib/mockData.ts`. Portal pages generally error-empty
  instead, except they still default the *identity* used in the URL.
- **Ephemeral UI:** local `Set`s for “request sent”, in-memory “recent
  emails”, `setTimeout` success toasts that do not persist.
- **Crawler:** `CrawlerContext` polls `fetchCrawlerStatus`.

### 1.4 API client layer

A single hand-written module: `src/lib/api.ts` (~1,546 lines).

- **Transport.** `requestJson` (`api.ts:259`) and ad-hoc `fetch` against
  `API_BASE = "/api"`. No auth header. No idempotency key. No error envelope
  matching `ErrorEnvelope` in the current OpenAPI.
- **Normalization.** Large parsers (`normalizeCalendarEvent`,
  `normalizeQrStats`, `normalizeFeedbackStats`) default missing numbers to
  **0** via `parseNumber(..., 0)` — the unknown=zero defect (Fix #8 / S2).
- **Source flag.** `WithSource<T>` treats `source !== "live"` as
  `isMockData`. `fetchCoordinatorEvents` defaults `source` to `"demo"` when
  the payload omits it (`api.ts:1474`).
- **Legacy routes called** (none exist on the current OpenAPI surface):

  | Client function | Legacy path |
  |---|---|
  | `fetchSpecialists` | `GET /api/data/specialists` |
  | `fetchEvents` | `GET /api/data/events` |
  | `fetchPipeline` | `GET /api/data/pipeline` |
  | `fetchCalendar` | `GET /api/data/calendar` |
  | `fetchCalendarEvents` | `GET /api/calendar/events` |
  | `fetchCalendarAssignments` | `GET /api/calendar/assignments` |
  | `fetchContacts` | `GET /api/data/contacts` |
  | `fetchCourses` | `GET /api/data/courses` |
  | `fetchUniversityContacts` | `GET /api/data/university-contacts` |
  | `fetchQrStats` / `generateQrAsset` | `GET /api/qr/stats`, `POST /api/qr/generate` |
  | `fetchFeedbackStats` / `submitFeedback` | `GET /api/feedback/stats`, `POST /api/feedback/submit` |
  | `rankSpeakers` / `scoreSpeaker` / `rankSpeakersForCourse` | `POST /api/matching/rank`, `/score`, `/rank-for-course` |
  | `generateEmail` / `generateIcs` / `initiateWorkflow` | `POST /api/outreach/email`, `/ics`, `/workflow` |
  | `startCrawl` / results / status | `POST /api/crawler/start`, `GET|DELETE /api/crawler/results`, `GET /api/crawler/status` |
  | `mockLogin` | `POST /api/portals/auth/` + the MM-A01 login route (archived; tests assert 404) |
  | student portal fetches | `GET /api/portals/students/{id}` and subresources |
  | coordinator portal fetches | `GET /api/portals/event-coordinators/{id}` and subresources |
  | volunteer portal fetches | `GET /api/portals/volunteers/{id}` and `/assignments` |
  | `AgenticOutreachPanel` | `POST /api/outreach/agentic-workflow/stream` |

`fetchVolunteerRecovery` does not hit a recovery endpoint; it folds
calendar assignments in the browser (`api.ts:920–945`).

### 1.5 Auth flow (as implemented)

1. `LoginPage` presents four role cards with **pre-filled demo emails**
   (`LoginPage.tsx:13–41`) including `alex.rivera@cal.edu` and
   `shana.demarinis@testset.com`.
2. Submit calls `mockLogin(email, role)` which POSTs `{ email, role }` to the
   MM-A01 route (`api.ts:1354–1375`). The caller chooses the role.
3. On 200, the client stores `{ user, role }` in `sessionStorage` and
   navigates to `response.redirect_path`.
4. Portal pages read that blob. If it is missing they still load
   `stu-001` / `coord-001` / `shana-demarinis`.
5. Admin `Layout` does not read the session at all. The footer always says
   “IA Admin”.

This is Fix #7 on the **client**. The current API already asserts that route
is gone (`tests/contract/test_api_health.py`,
`tests/integration/test_command_path.py`). A login that still posts a role
in the body cannot be connected to this backend; identity is derived from a
verified token (A1a done, live JWKS is A1b).

### 1.6 Styling system

- Tailwind 4 via `@tailwindcss/vite`; `src/styles/index.css` plus
  `public-shell` / `public-button-*` utility classes on landing/login.
- shadcn-style tokens (`bg-primary`, `border-border/70`, `rounded-2xl`).
- Admin pages mix those tokens with hard-coded hex (`#005394`, `#d5e0f7`) —
  two visual languages in one shell.
- No provenance primitive, no “unknown” primitive, no designed empty /
  partial / denied / stale / failed treatments (DESIGN.md D-6).
- `DemoModeBadge` is a page banner, not a per-cell source label (DESIGN.md
  §1.1).

---

## 2. Catalog of broken and hard-coded functionality

Each item: **id**, path, lines, what it does, what it should do. Interactive
controls are duplicated with effort estimates in
[`frontend-broken-buttons.md`](frontend-broken-buttons.md).

**Count: 68 items** (H01–H28 invented data / identity / metrics; B01–B40
non-working or lying interactives).

### 2.1 Hard-coded identity, records, and formulas (H01–H28)

| ID | Location | Currently | Should |
|---|---|---|---|
| H01 | `LoginPage.tsx:13–41, 56–62` | Caller picks a role and a canned email; POSTs both to the MM-A01 login route; stores the response as the session. | Role comes from the verified session. No role picker. No demo emails in source. |
| H02 | `api.ts:1352–1375` | `mockLogin` sends `{ email, role }`. | Delete. Do not generate a client method for an archived route. |
| H03 | Every portal page (`StudentHome.tsx:31`, `CoordinatorHome.tsx:37`, `VolunteerHome.tsx:25–27`, …) | Missing session → hard-coded `stu-001` / `coord-001` / `shana-demarinis`. | Unauthenticated → login. Never a default person. |
| H04 | `Layout.tsx:154–164` | Footer always “IA Admin” / `admin@ia.org`. No session, no sign-out. | Principal from token; sign-out clears the real session. |
| H05 | `src/lib/mockData.ts` (entire file, ~690 lines) | `MOCK_SPECIALISTS`, `MOCK_PIPELINE`, `MOCK_EVENTS`, `MOCK_CALENDAR_*`, `MOCK_QR_STATS`, `MOCK_FEEDBACK_STATS`, `MOCK_RANKED_MATCHES`. Invented names, scores, funnel counts. | Do not port. Unlabeled seed content is MM-A03 / DESIGN.md §1.1. |
| H06 | `Dashboard.tsx:318–375` | On fetch failure, assigns the mock constants and sets `isMockData`. | Truthful empty/failed state. Never populate with fixtures that look live. |
| H07 | `Volunteers.tsx:275–317` | Same mock fallback. | Same as H06. |
| H08 | `Pipeline.tsx:172–212` | Same mock fallback. | Same as H06. |
| H09 | `Calendar.tsx:174–200` | Same mock fallback. | Same as H06. |
| H10 | `AIMatching.tsx:337–349, 484` | Unreachable matcher → `MOCK_EVENTS` + `MOCK_RANKED_MATCHES`. | No scores until gate G1 and a real `match_run`. |
| H11 | `src/lib/mockProfilePhotos.ts:16–17` | Seeded avatar URLs for “stable mock users”. | Real consent-backed photos or initials only. |
| H12 | `studentPoints.ts:3–5` | `attendance_streak * 100 + events_attended * 25`, commented “demo formula”. | Server fold over `point_ledger_entry` (ADR-0013, S7). |
| H13 | `studentRewardsCatalog.ts:23–80` | Seven items, costs 2,500…45,000, hard-coded in the bundle. | Server catalog with `budget_owner_id` + `funded` (S8, D6, D7). |
| H14 | `StudentHome.tsx:96, 186–197` and `StudentHistory.tsx:42, 99–104` | Points and streak rendered from H12. | Ledger balance; unknown if no attendance. |
| H15 | `StudentRewards.tsx:72–81, 152–165` | “Closest unlock” progress toward catalog items that attendance cannot reach. | Progress only toward a *reachable* reward (engagement-model.md §4); otherwise no bar. |
| H16 | `StudentConnect.tsx:604–608` | `isAlreadyConnected` = `stableHash(key) % 2 === 0`. Half the roster is “already connected”. | Connection is a consent-gated record (ADR-0014), not a hash. |
| H17 | `StudentConnect.tsx:91–128, 610+` | Inbox threads and copy invented by `makeMockThreadMessages`. | In-app chat is archived (MM-F04). Do not rebuild. |
| H18 | `api.ts:379, 834, 851, 961–966` | `parseNumber` and `emptyFeedbackStatsSummary` coerce missing rates/scores/`pain_score` to 0. | Optional / unknown. Domain already returns `None` for empty `acceptance_rate`. |
| H19 | `api.ts:1474` | Coordinator events default `source: "demo"`. | Source is a server field or the request failed. |
| H20 | `api.ts:920–945` | Volunteer recovery is a client fold of assignments. | Server-authored ELI / recovery with provenance (eli.py is proposed only). |
| H21 | `Opportunities.tsx:29–47` | Crawler rows get fabricated `date: "See link for details"`, `role: "Guest speaker"`. | Unresolved dates do not reach a publishable list (ADR-0010). Quarantine unmapped tags (ADR-0012). |
| H22 | `Calendar.tsx` / `StudentEvents.tsx:159–207` | Times/dates rendered without an IANA zone or precision. Student calendar is a month grid labeled “Google Calendar Style Mock”. | **Both surfaces:** event-local zone named, `date_only` as a date, `unresolved` never placed on a day (ADR-0010). **Student surface only:** agenda, not a month grid (engagement-model.md §5, Fix #10 — the argument is that a sparse grid reads as a dead chapter to a prospective attendee). The admin `Calendar.tsx` month grid is *retained* under the ratified G1 worksheet directive “Month calendar bottom of events page”; see `apps/web/DESIGN.md` §2.1 before changing either. |
| H23 | `Dashboard.tsx` funnel + `Pipeline.tsx:253–316` | Funnel counts computed in the page from `pipeline` records (and mocks). Two admin views can disagree. Metric cards link to other routes. | One owning query (S12, ADR-0011). Clicking N returns those N rows (S1). |
| H24 | `LandingPage.tsx:75–76` | “Start Matching” → `/login?role=ia_admin`, pre-selecting a role. | Public CTA to real auth, no role in the query string. |
| H25 | Templates in `Outreach.tsx` | Subject/body templates live in the component; “Create Template” does not save (see B22). | Versioned templates server-side, or omit until R4. |
| H26 | `CoordinatorHome.tsx:132–162` vs `164–189` | Statistics (hosted events, threads, meetings) render *before* Quick Actions. | Action queue first; when n is small, name the people (DESIGN.md §1.11, Fix #13). |
| H27 | `VolunteerProfile.tsx` entire page | Fatigue % and recovery are displayed; there is no editor for availability or workload inputs. | Professionals must see *and correct* the data used about them (DESIGN.md §1.6, R2 self-service). |
| H28 | `FeedbackForm` + dashboard “Pain Score” / “Match Depth” / “Topic Relevance” via mock stats | Mock feedback invents 0-valued metrics. | Metric register (S1); unknown ≠ 0 (S2). No score until G1. |

### 2.2 Broken or lying interactives (B01–B40)

Summaries here; full checklist with effort in the companion doc.

| ID | Control | Currently | Should |
|---|---|---|---|
| B01 | Login **Sign In** | Posts MM-A01 body; 404 against this API. | OIDC / Identity Platform (A1b). |
| B02 | Login **role cards** | Set role + canned email. | Remove. |
| B03 | Student Home **nudge CTA** (`StudentHome.tsx:225`) | `<button>` with **no `onClick`**. | Navigate/register against a real command, or omit the CTA. |
| B04 | Student Home **Register** | Link to `/student-portal/events`. Does not register. | Registration command; or label as “View events”. |
| B05 | **Add to Calendar** (`StudentEvents.tsx:59–62, 128–132`) | Toast “Calendar event added” only. No ICS, no provider. | `smartmatch_domain.ics` via a command; never fabricate a slot (F-003 / MM-001). |
| B06 | **QR / check-in** (`StudentEvents.tsx:134–141`) | `href="/api/qr/stats"` — GET of a stats JSON blob in a new tab. | Phone-first check-in (MM-F02, S6, S11). Stats are not a check-in token. |
| B07 | Connect **Connect** (`StudentConnect.tsx:330–344`) | Adds id to a local `Set`; “Request sent!”. | Coordinator-mediated mentor request *or* opt-in LinkedIn URL (ADR-0014). No email/phone from research. |
| B08 | Connect **Connect with speaker** (`:447–461`) | Same local `Set`. | Same as B07, consent-gated. |
| B09 | Connect **Chat** | Opens a sheet of invented messages. | Do not ship in-app chat (MM-F04, Fix #11). |
| B10 | Chat **Send** (`:572–578`) | Clears the draft. Comment: “Demo-only: messages are not persisted.” | Remove with B09. |
| B11 | Rewards **Request redemption** (`StudentRewards.tsx:226–228`) | Local `demoRequested` Set; label “Request sent (demo)”. | `redemption` command requested→approved→… (S9). Needs D6+D7. |
| B12 | Coordinator **Send** (`CoordinatorOutreach.tsx:69–77`) | `console.log`; fake “Message sent!” then close. | Consent-gated outreach command (R4). Domain `consent.py` has no API resource yet. |
| B13 | Coordinator **New thread** (`:79–87`) | `console.log`; fake success. | Same as B12. |
| B14 | Agentic **Approve & Send** (`AgenticOutreachPanel.tsx:324–328`) | `setPhase("approved")`; banner claims “Outreach sent ✓ Pipeline updated”. | Nothing executes from ambient conversation (DESIGN.md §1.7). Same confirmation UI as conventional send. No send path exists. |
| B15 | Agentic **Reject** (`:330–335`) | Local phase; reason never submitted. | If an agent draft exists, rejection is an audited command. Today: do not build this panel. |
| B16 | **Book meeting** (`CoordinatorMeetings.tsx:58–67`) | `console.log`; fake success. No event created. | Scheduling command with ADR-0010 timestamps. Calendar API is gated G5; ICS only until then. |
| B17 | Coordinator **Request Match** (`CoordinatorEvents.tsx:138–145`) | Link to `/ai-matching` (admin matcher, unguarded). | Coordinator intake command, not a jump into the admin matcher. Matcher blocked on G1. |
| B18 | Outreach **Save Draft** (`Outreach.tsx:463–466`) | `<button>` with **no `onClick`**. | Draft command, or remove until R4. |
| B19 | Outreach **AI Enhance** (`:146–150, 412–418`) | Appends a hard-coded sentence to the body. | Typed, editable intent + autonomy tier (R5). Not a silent string splice. |
| B20 | Outreach **Generate / Refresh** (`:152–191`) | `POST /api/outreach/email` — not in current OpenAPI. | Template draft only when AI unavailable, labeled as such (DESIGN.md §1.2). R4. |
| B21 | Outreach **ICS** (`:193–214`) | `POST /api/outreach/ics`. Legacy generator fabricated dates (F-003). | Domain `ics.py` already refuses unresolved datetimes. Expose as a command, not a live POST from the browser to a provider. |
| B22 | **Create Template** (`Outreach.tsx:534–538`) | Closes the dialog. Inputs are uncontrolled; nothing is saved. | Persist a template, or remove the dialog. |
| B23 | Outreach **Generate QR** | `POST /api/qr/generate`. | MM-F02 attendance QR, phone-first, with a data-minimization statement (D8). |
| B24 | Dashboard **Connect** (`Dashboard.tsx:442–456, 986–993`) | `initiateWorkflow` → missing `/api/outreach/workflow`. | Same as B12, after consent. |
| B25 | AI Matching **Initiate outreach** (`AIMatching.tsx:504–523`) | Same workflow POST. | Same as B24. |
| B26 | **Log feedback** | `FeedbackForm` → `POST /api/feedback/submit`. | Feedback is R2; domain `feedback.py` has no HTTP resource. |
| B27 | Crawler **Start** | `POST /api/crawler/start`. | R3, behind a crawler threat model. Do not port. |
| B28 | Crawler **Clear / load saved** | `DELETE` / `GET /api/crawler/results`. | Same as B27. |
| B29 | Pipeline stage **KPI tiles** (`Pipeline.tsx:308+`) | Not clickable. Counts from client filter + mocks. | Drill-down invariant (Fix #12, S1). |
| B30 | Dashboard **MetricCard** links (`Dashboard.tsx:554–581`) | Navigate to a different list page (different query). | Same query’s rows; count equals N. |
| B31 | Opportunities **Run matcher** (`Opportunities.tsx:327`) | `navigate("/ai-matching", { state: { eventName } })`. Matcher is mocked (H10). | Blocked on G1. Do not navigate to a scoreboard of fixtures. |
| B32 | Volunteer Home **View profile / assignments** | Links work as navigation. Profile cannot be edited (H27). | Correction commands for availability/workload. |
| B33 | Admin crawler banner **View feed** | Link to `/outreach`. Feed talks to missing crawler API. | Omit until R3. |
| B34 | `OutreachWorkflowModal` **Upgrade to Agentic** (`:157–166`) | Closes and `navigate("/coordinator-portal/outreach")` — cross-portal, unguarded. | Jarvis is R5 and is not a second send path. |
| B35 | Student History **attended count** | Display only; no drill-down. Past Events was the 5 s finding (S11). | Same-query drill-down; performance budget. |
| B36 | Coordinator Home **stat tiles** | Display only; no drill-down; stats before actions (H26). | Named people when n is small; actions first. |
| B37 | Volunteer **assignment cards** | Display only. No accept/decline, no ICS, no “I need rest”. | R2 accept/decline + ICS + ELI correction. |
| B38 | Calendar day cells | Switch views. Coverage/recovery numbers still unknown=0 (H18) and unzoned (H22). | ADR-0010 + S2 primitives. |
| B39 | Landing **View Demo** | In-page `#proof` anchor. Fine as marketing; must not be confused with live data. | Keep only if labeled synthetic. |
| B40 | All admin data-entry that “succeeds” with only a toast | Unconditional success UX. | Never report success when the write did not happen (v1.1 §3.6 N2). |

---

## 3. Mapping to the current backend

### 3.1 What the OpenAPI contract actually exposes

`contracts/openapi/smartmatch.json` currently describes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness. No topology detail. |
| GET | `/u/{token}` | Unsubscribe confirmation page (signed POST is the mutation). |
| GET | `/v1/jobs/{job_id}` | Durable job status. |
| GET | `/v1/jobs/{job_id}/events` | SSE / poll of `job_event.sequence`. |
| POST | `/v1/jobs/{job_id}/redrive` | Privileged re-drive (admin/coordinator). |
| POST | `/v1/jobs/{job_id}/abandon` | Permanently close a parked job. |
| POST | `/v1/units/{unit_id}/imports` | Import **command** (202 + job id). Worker cannot execute until J10 (`job.payload`). |

There is **no** route for matching, specialists, events, pipeline, calendar,
QR, feedback, crawler, portals, outreach, points, rewards, or login.

A generated TypeScript client (W2) can only wrap the table above. Every
legacy `api.ts` function is therefore either (a) a future resource not yet
specified or (b) a forbidden pattern that must not return.

### 3.2 Domain capabilities that exist *without* an HTTP resource

These can become endpoints later; they are not callable from a browser today.

| Domain module | Capability | Frontend implication |
|---|---|---|
| `factor_registry.py` | Proposed 9-factor registry; `assert_registry_approved()` fails closed | **No match scores on any screen** until G1 (M1). H10/B31 stay dark. |
| `eli.py` | Proposed ELI formula | Volunteer fatigue UI must wait on D2 + R2 self-service. |
| `feedback.py` | Aggregates; `acceptance_rate` is `None` when empty | Do not port `parseNumber(..., 0)`. S2 render primitive. |
| `ics.py` | ICS only if timezone-aware and resolved; else `UnschedulableEventError` | B05/B21 must use this, labeled. No Calendar provider until G5. |
| `consent.py` | Contact-confidence state machine; scraped ≠ send-eligible | B12/B14/B24 cannot send. Distinct from disclosure consent (ADR-0014). |
| `jobs.py` / command path | Import, redrive, abandon, SSE | **No operator UI exists** in the legacy frontend for any of this. |
| `ingest.py` | Import validation (command not executable until J10) | No import screen in the old app. |

### 3.3 Feature → endpoint or gap

| Legacy feature | Map to | Status |
|---|---|---|
| Health (unused by UI) | `GET /api/health` | Exists; optional status chip later |
| Login / role picker | — | **Forbidden.** MM-A01 archived. Use A1b OIDC. |
| Admin specialists/events/pipeline/calendar GETs | Future read models | **No counterpart.** Needs schema + authz (A4, A5). |
| Rank / score / match board | `match_run` after M8 | **Blocked on G1.** |
| Outreach email / workflow / agentic stream | R4 send path + consent | **No counterpart.** Agentic panel contradicts §1.7. |
| ICS download | `ics.py` via command | Domain yes, HTTP no. |
| QR generate / stats / student check-in | MM-F02, S6, S11 | **No counterpart.** B06 is the wrong URL even against the *legacy* QR stats route. |
| Feedback submit / stats | R2 + `feedback.py` | Domain yes, HTTP no. |
| Crawler start/results | R3 + threat model | **Do not port.** |
| Student profile / registrations / nudge / recommendations | Engagement tables S6–S10 | **No counterpart.** |
| Student points / rewards / redemption | ADR-0013 | **No counterpart.** Needs D6, D7. |
| Student connect / chat | ADR-0014, MM-F04 | Chat archived. “People you met” + LinkedIn opt-in **not built**. |
| Coordinator threads / meetings / events | R2 coordinator intake | **No counterpart.** |
| Volunteer profile / assignments | R2 professional self-service | **No counterpart.** Read-only page fails §1.6. |
| Job status / SSE / redrive / abandon | OpenAPI jobs + redrive | **Exists. No legacy screen.** New work. |
| Import command | `POST /v1/units/{unit_id}/imports` | **Exists (cannot execute: J10). No legacy screen.** New work. |
| Unsubscribe | `GET /u/{token}` | **Exists. No legacy screen.** New work. |
| Provenance labels | DESIGN.md §1.1, W4 | **No counterpart in old UI** (badge ≠ per-value label). |
| Drill-down | ADR-0011, S1 | **No counterpart.** MetricCard navigates away. |
| Classroom reset | architecture diagram 3 | **No counterpart anywhere.** Unnumbered backlog row. |

### 3.4 Features with no backend counterpart yet (explicit)

1. Matching control center (13 views, W5) — blocked G1 / M8.
2. All portal CRUD (register, send, book, redeem, connect, check in).
3. Points ledger, catalog listing, redemption.
4. Disclosure-consent grant/revoke UI.
5. Professional availability/workload correction.
6. Funnel as a single owning query.
7. Event temporal model on the wire (S3).
8. Crawler / research scout (R3).
9. Jarvis conversational surface (R5) — do not revive `AgenticOutreachPanel`.
10. Operator surfaces for imports, jobs, SSE, redrive, abandon, unsubscribe.
11. Classroom-reset tooling.

---

## 4. Stakeholder requirements → frontend work

Source: Dr. Ann Wang test log (19–20 August 2026) as classified in
`docs/architecture/review/stakeholder-test-log-audit.md` and planned in
`docs/plans/stakeholder-audit-integration.md`. Contract review
(`docs/architecture/review/contract-findings.md`) is cited where it
intersects the UI.

### 4.1 Fix list → frontend work items

| Fix | Requirement | Old frontend | New frontend work | Backend ready? |
|---|---|---|---|---|
| #1 | Real identities not in git / demos | Canned emails and invented specialists in source (H01, H05). Mock photos (H11). | No PII and no unlabeled people in the bundle. Session principal only. | MM-A09 is a legacy-repo decision (Q1), not a screen. |
| #2 | *(not in the log we have)* | — | **Cannot plan.** | — |
| #3 | Funnel Matched → Contacted → Confirmed → Attended → Member Inquiry | Client-side stage counts on Dashboard and Pipeline; tiles not drillable (H23, B29). | One funnel view bound to S12’s owning query; each stage is a drill-down. | **No.** S12 not built. |
| #4 | Event data quality (dates, dupes, tags, titles) | Opportunities fabricates dates (H21); calendar ignores precision. | Do not render `unresolved`; quarantine tags; titles without source-page leakage. | **No.** S3–S5 / ADR-0010, 0012. |
| #5 | Two “opportunities” pages must agree | `/opportunities` (events+crawler) vs dashboard/pipeline opportunity counts (H23). | One metric name, one query, both views subscribe (S1). | **No.** |
| #6 | Times not 3 AM / 7 AM | Naive `toLocaleString` / `event_date` strings (H22). | Event zone named beside the time; `date_only` as a date. | **Partial.** ICS exporter only; no event column yet (S3). |
| #7 | No caller-chosen role | **Still in the UI** (H01, B01, B02). Backend COVERED (404 tests). | Delete login role cards and `mockLogin`. Wire A1b. | Authn fixture exists; live JWKS is A1b. |
| #8 | Unknown ≠ zero | `parseNumber` → 0; empty feedback summary is 0% (H18). | W4 unknown primitive (S2). **ON HOLD behind D-0.** | Domain `acceptance_rate` is already `None`; HTTP does not expose it. |
| #9 | Points not a browser formula | `studentPoints.ts` used on Home, History, Rewards (H12–H14). | Display ledger fold only. | **No.** S6–S7. |
| #10 | Student calendar not a dead month grid | `MockStudentCalendar` (H22). | Unified agenda (engagement-model.md §5). | **No.** Needs events + registrations. |
| #11 | Chat cut; peer visibility decided | Full mock chat + Connect buttons (B07–B10, H16–H17). | Remove chat. Ship “people you met” + LinkedIn opt-in + coordinator-mediated mentor request, with an honest limited-list state. | **No.** S10 blocked on D8. |
| #12 | Clicking 15 returns 15 | MetricCard `href` to another page (B30); pipeline tiles dead (B29). | Aggregate component requires a drill-down slot (S1). | **No.** |
| #13 | Dashboard: actions before stats; name people when n is small | Coordinator home stats-first (H26); admin dashboard is a chart wall. | DESIGN.md §1.11 on coordinator and admin home. | Layout-only once data exists. |
| #14 | *(not in the log we have)* | — | **Cannot plan.** | — |
| #15 | Rewards reachable | Catalog 2,500–45,000 vs 25 pts/event (H13, H15, B11). | No progress bar toward unreachable items; listing requires D6+D7. | **No.** S8–S9. |
| #16 | Student Connect classified | Chat + hash-connected peers + speaker connect (H16–H17). | MM-F04 archive chat; rebuild under ADR-0014. | **No.** |

### 4.2 Test-log rows without a fix number

| Finding | Old frontend | Frontend work |
|---|---|---|
| Past Events takes 5 s | `StudentHistory` fetches registrations + profile; no pagination. | S11 performance budget on this view. |
| QR under 50 concurrent scans | No real check-in UI (B06 hits stats). | Phone-first check-in + load test. **Not in the old app.** |
| No data-minimization statement for QR signup | Absent. | Copy/consent UI blocked on D8. **No coverage.** |
| Nothing defines “FERPA-aware” | Absent. | D8. **No coverage.** |
| Classroom reset (diagram 3) | Absent. | **No coverage.** No backlog id. |
| Missing LICENSE / SECURITY.md / CONTRIBUTING.md / CODEOWNERS | N/A (not UI). | F13 — not frontend. |

### 4.3 Contract-review intersections (F-001…F-006)

| Finding | Frontend consequence |
|---|---|
| F-001 factor registry 9 vs 7 | **Do not display match scores** until G1. Legacy board deflates totals to 0.90. |
| F-002 44 legacy routes | Inventory only. None of those 44 are in the current OpenAPI. |
| F-003 ICS fabrication | B05/B21 must not call a generator that invents “30 days from now”. Use `ics.py`. |
| F-004 consent | Any Send/Approve control is dishonest until a send-eligible API exists. |
| F-005 process-local jobs | Old crawler/outreach “live feed” cannot be the job UI. Use `/v1/jobs`. |
| F-006 open decisions | Factor registry, ELI, consent-origin, calendar auth, retention, travel matrix, agents, DNS — all still block corresponding screens. |

### 4.4 Stakeholder requirements the old frontend does **not** cover

These are absent from `apps/web/legacy-frontend/`, not merely broken:

1. **Per-value provenance** (Observed / Inferred / Heuristic / Model / Synthetic) — DESIGN.md §1.1. Only a page-level demo chip exists.
2. **Designed truthful failure states** (travel unavailable, coarse estimate, partial discovery, AI-unavailable draft, calendar unsynchronized, rate-limit retry window, unknown vs zero) — DESIGN.md §1.2 / D-6.
3. **Event IANA zone named on every time**, `date_only` vs `exact` — ADR-0010.
4. **Professional correction of availability and ELI inputs** — DESIGN.md §1.6. Volunteer profile is read-only.
5. **Action queue of named people** when n is small — Fix #13 / §1.11.
6. **Same-query drill-down** on every aggregate — Fix #12 / ADR-0011.
7. **Unified student agenda** (not a month grid) — Fix #10.
8. **Disclosure-consent lifecycle UI** (grant/revoke, limited-list explanation) — ADR-0014 / D8 / D-10.
9. **Server-authoritative points ledger and a reachable catalog** — Fix #9, #15.
10. **Phone-first QR check-in** with data-minimization copy — MM-F02, Q31.
11. **Unsubscribe / suppression** surface — OpenAPI `/u/{token}` has no legacy page.
12. **Import + job/SSE/redrive/abandon operator UI** — the only implemented command path.
13. **Classroom-reset tooling** — diagram 3; unnumbered.
14. **Jarvis as accelerator** (visible typed intent, same confirmation UI) — DESIGN.md §1.7. The legacy “agentic” panel is a parallel send path that lies about success.
15. **WCAG 2.2 AA with CI smoke** — W6. No a11y test script in the copy.
16. **Generated OpenAPI client + drift check** — W2.
17. **Fix #2 and Fix #14** — not recoverable without the test log (Q7).
18. **F13 governance files and D9 licensing** — not frontend, listed so they are not mistaken for UI gaps.

Kickoff questions the old UI also does not answer: **Q1** (which factors matching uses — the board shows scores without a registry), **Q4** (how times are resolved — they are not), **Q13** (student surface scope — chat and unreachable rewards are in; agenda and consent are not), **Q14** (QR at event scale — no check-in).

---

## 5. Phased migration plan

Planning only. **D-0** (DESIGN.md owner + D-1…D-11) blocks W1–W7.
Accept the hold: a screen built before provenance components and before its
data exists will be filled with the same unlabeled placeholders this catalog
documents.

### Phase 0 — Decisions and inventory freeze

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 0.1 | Assign DESIGN.md owner; settle D-1 (design system / shadcn license), D-5 (one shell vs four portals), D-6 (six states), D-7 remainder. | — | Part 2 of DESIGN.md answers its four “done” questions. |
| 0.2 | Treat `apps/web/legacy-frontend/` as read-only inventory. Do not `npm install` it as the new app. | copy present | CI does not build this tree as `apps/web`. |
| 0.3 | Confirm MM-F01 licensing before any primitive is copied. | 0.1 | Written license decision. |

### Phase 1 — Scaffold and client (W1, W2, W7)

| Task | Files (target, not legacy) | Depends | Acceptance |
|---|---|---|---|
| 1.1 W1 | Scaffold React 18 + TS + Vite under `apps/web/` **without** copying pages or `src/lib/api.ts`. | D-0 | `npm` scripts exist; DESIGN.md hold lifted by owner. |
| 1.2 W2 | Generate TS client from `contracts/openapi/smartmatch.json`; CI drift check. | 1.1 | Client matches the five resources; no hand-written `/api/data/*`. |
| 1.3 W7 | `npm ci`, `tsc`, vitest, bundle budget, Playwright in CI. | 1.1 | Gates listed in `verify.yml` are no longer “deferred”. |
| 1.4 | Auth: attach bearer from A1b; **no** role query param, **no** `sessionStorage` principal. | 1.2, A1b | Login cannot POST a role. Unguarded URLs hide doors but API remains authoritative (DESIGN.md §1.3). |

### Phase 2 — Primitives before screens (W4, W6, S2)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 2.1 W4 Provenance | Value primitive that cannot render without a source label. | 1.1 | Unlabeled value is unrepresentable. |
| 2.2 W4 Unknown | Optional number → “unknown”, never `0` / `0%`. | 2.1, S2 domain | Fixture: empty feedback set does not render 0%. |
| 2.3 W4 Failure states | Six non-happy treatments (D-6). | 2.1 | Each DESIGN.md §1.2 sentence has a component. |
| 2.4 W4 Time | Render UTC instant + IANA zone + precision. | S3 | `date_only` is a date; zone is named; unresolved does not list. |
| 2.5 W4 Drill-down | Aggregate slot whose click returns the same rows. | S1 | Test: clicked N equals result length. |
| 2.6 W6 | axe/Playwright a11y smoke, WCAG 2.2 AA. | 1.3 | CI red on the regressions `.github/workflows/verify.yml` names. |

**Do not start W3 or any portal page before 2.1–2.5.** Retrofit will be skipped.

### Phase 3 — Presentational port (W3)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 3.1 | Port *layout chrome* from shadcn primitives only if D-1 allows. Leave `mockData.ts` and photos behind. | 2.x, MM-F01 | No `MOCK_*` imports. |
| 3.2 | Public landing without role-preselect CTA. | 3.1 | No `?role=` on login. |
| 3.3 | Unsubscribe page bound to `GET /u/{token}`. | 1.2 | First screen with a real contract. |

### Phase 4 — Operator command-path UI (new; not a port)

The only honest screens the API can support today.

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 4.1 | Import submit → 202 + job id; dry_run default true. | 1.2, J10 | Worker can execute; UI follows SSE. |
| 4.2 | Job status + event stream (`Last-Event-ID`). | 4.1 | Partial/failed/rate-limited states use 2.3. |
| 4.3 | Redrive / abandon with reason; 409/403 truthful. | 4.2, A4 | No “success” on refusal. |

### Phase 5 — Student engagement (R2, S6–S11)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 5.1 | Agenda of registered + open events (not month grid). | 2.4, event read API | Fix #10 closed on the surface. |
| 5.2 | QR check-in, phone-first, minimization copy. | S6, D8, S11 | B06 gone; load test exists. |
| 5.3 | History with drill-down; budget vs 5 s finding. | 5.2, 2.5, S11 | Count equals rows. |
| 5.4 | Points from ledger fold only. | S7 | `studentPoints.ts` not ported. |
| 5.5 | Rewards catalog + redemption. | S8, S9, D6, D7 | Cheapest item reachable in N events; no bar otherwise. |
| 5.6 | Connect: people you met + LinkedIn opt-in + mentor request. **No chat.** | S10, D8 | Limited list explains itself. |

### Phase 6 — Professional and coordinator (R2)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 6.1 | Professional profile **edit** of availability/workload used by ELI. | D2, ELI API | §1.6 satisfied. |
| 6.2 | Assignments: accept/decline, ICS from `ics.py`. | 6.1, consent | No send from scraped evidence. |
| 6.3 | Coordinator home: action queue first; named people. | 2.5 | Fix #13. |
| 6.4 | Intake / staffing request — not a link to the admin matcher. | G1 for matches | B17 gone. |

### Phase 7 — Matching control center (W5)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 7.1 | Thirteen views per v1.1 §5.2, after M8. | G1, M8, 2.x | Scores carry registry version + provenance “heuristic score”. |
| 7.2 | Funnel from S12 only. | S12 | Dashboard and pipeline cannot diverge. |
| 7.3 | Scenario comparison (v1.1 §5.3). | M10 | No fabricated rank. |

### Phase 8 — Outreach and Jarvis (R4, R5)

| Task | Detail | Depends | Acceptance |
|---|---|---|---|
| 8.1 | Draft/send only through consent lifecycle; confirmation UI shared. | F-004 API, G4 | B12/B14/B18 cannot exist as console.log or local phase. |
| 8.2 | Jarvis accelerator: visible typed intent, autonomy tier, opens normal editors. | R5 | No `AgenticOutreachPanel` port. |

### Dependency order (critical path)

```
D-0 → W1 → W2 → W4 (provenance, unknown, time, drill-down)
                → W3 chrome
                → W6 a11y
         → A1b auth
J10 → Phase 4 operator UI (only live writes)
G1 → M8 → W5 control center
S6 → S7 → S9 (D6, D7) → student rewards
D8 → S10 → student connect
R3 threat model → any crawler UI (default: never from this copy)
```

---

## 6. Deliberate non-ports

Do not carry forward:

- `src/lib/mockData.ts`, `mockProfilePhotos.ts`, `studentPoints.ts`, in-bundle rewards catalog.
- `mockLogin` and role cards (MM-A01, Fix #7).
- `AgenticOutreachPanel` and `/api/outreach/agentic-workflow/stream`.
- `StudentConnect` chat sheet (MM-F04).
- `CrawlerFeed` / `CrawlerContext` until R3 is actually scheduled.
- Hand-written `src/lib/api.ts` (replaced by W2).
- Fallback identities `stu-001`, `coord-001`, `shana-demarinis`.
- Demo emails in `LoginPage.tsx`.
- MetricCard-as-navigation standing in for drill-down.

The copy under `apps/web/legacy-frontend/` stays as evidence for this plan
and for MM-F01 licensing review. It is not an application to evolve in place.
