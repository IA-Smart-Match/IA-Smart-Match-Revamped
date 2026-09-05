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

**Count: 42 controls.**

---

## Auth and public

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B01 | `src/app/pages/LoginPage.tsx:204–210` **Sign In** | `handleSubmit` → `mockLogin(email, role)` POST `{ email, role }` to the MM-A01 portal login route (`src/lib/api.ts:1354`). Against this repo that route is 404. | Authenticate with Identity Platform; role from membership, never from the body. | Live JWKS verifier (backlog A1b). No login resource in `smartmatch.json`. | Delete this client. New login uses OIDC redirect + generated client. Do not regenerate the archived method. | M (blocked on A1b) |
| B02 | `LoginPage.tsx:119–129` **role cards** | Click sets `selectedRole` and a canned email (`alex.rivera@cal.edu`, `jordan.lee@cpp.edu`, `admin@iawest.org`, `shana.demarinis@testset.com`). | No caller-chosen role. | None — forbidden (Fix #7). | Remove the four cards and the role `<select>`. | S |
| B03 | `LandingPage.tsx:75–76` **Start Matching** | `Link` to `/login?role=ia_admin`, pre-selecting admin. | CTA to real auth with no role in the query string. | A1b | Change the href; drop `roleFromUrl` in `LoginPage.tsx:47`. | S |
| B04 | `Layout.tsx:154–164` admin footer | Not a button. Displays “IA Admin” / `admin@ia.org` with no session and no sign-out (unlike the three portal layouts). Included because it is an interactive identity surface people trust. | Show the verified principal; sign-out clears the real session. | A1b | Read principal from the generated auth context; add sign-out. | S |

---

## Student portal

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B05 | `student/StudentHome.tsx:225–227` **nudge CTA** | `<button>{nudge.cta_label}</button>` — **no `onClick`**. Dead. | Perform the nudge’s action (open agenda, start check-in, open rewards) using `nudge.nudge_type` / `event_id`. | Student nudge + commands: **no counterpart** (engagement tables S6–S10). | Either bind to a command or do not render a button until the command exists. | M |
| B06 | `StudentHome.tsx:256–261` **Register** | `Link` to `/student-portal/events`. Does not create a registration. | Registration command (idempotent), or the label must say “View events”. | **No counterpart.** | New command resource; until then relabel. | M |
| B07 ✅ *button gone; endpoint shipped; link still blocked* | `student/StudentEvents.tsx` **Add to Calendar** | **Removed.** `handleAddToCalendar` and its 3 s “Calendar event added” toast went with the rest of the legacy page body; the page now renders `/v1/me` + `/v1/me/portals`, an honest `PortalDatasetUnavailable`, and a section saying what the .ics route does and why no link appears yet. | Download ICS from `smartmatch_domain.ics` for a *resolved* event; refuse `unresolved` (F-003). | **Shipped:** `GET /v1/units/{unit_id}/events/{event_id}/invite.ics` returns `text/calendar` bytes through `calendar_invite.build_invite_ics`; refuses with `409 event_time_unresolved` / `event_end_unknown` / `event_not_presentable`; `admin`+`coordinator` unit-wide, `student` only with an `attendance_record` (else `404`). The Calendar *API* stays gated at G5 — `docs/plans/open-questions/calendar-deferred.md`. | **Remaining:** no student-scoped event read exists (`/v1/units/{unit_id}/events` is coordinator-gated), so this page has no `event_id` to link with. Do **not** add a placeholder event to hang the link on — that is B07 again with a real URL attached. Blocked on OQ-004. | S, once a student event read exists |
| B08 | `StudentEvents.tsx:134–141` **QR / check-in** | `<a href="/api/qr/stats">` opens GET JSON stats in a new tab. | Phone-first check-in with a reusable token (v1.1 §1.9, MM-F02). | **No counterpart.** S6, S11, D8 (minimization copy). | New QR check-in flow; do not reuse `/qr/stats`. | L |
| B09 | `StudentEvents.tsx:97` month grid | `MockStudentCalendar` is not a button but is the only “calendar” control; cells are inert. Students cannot register from a day. | Time-ordered agenda of registered + open events (Fix #10). | Event + registration read API: **none**. | Replace the grid (engagement-model.md §5). | M |
| B10 | `student/StudentConnect.tsx:330–344` **Connect** (peer) | `setRequested` local `Set`. Label becomes “Request sent!” with no network. Half of peers are pre-“Connected” via `stableHash % 2` (`:604–608`). | Opt-in LinkedIn URL the peer supplied, or a coordinator-mediated mentor request (ADR-0014). Research emails/phones never shown. | `disclosure_consent` (S10) **blocked on D8**. | Remove local Set. Do not ship chat. | L |
| B11 | `StudentConnect.tsx:447–461` **Connect with speaker** | Same local `Set` (`speakerRequested`). | Same as B10; speakers are professionals — consent-gated, coordinator-mediated. | S10, contact consent (`consent.py`) — HTTP **none**. | Same as B10. | L |
| B12 | `StudentConnect.tsx:346–358` / `:462–474` **Chat** | Opens a sheet of `makeMockThreadMessages`. | In-app chat is archived (MM-F04, Fix #11). | None — do not build. | Delete the sheet and buttons. | S |
| B13 | `StudentConnect.tsx:572–578` **Send** | Clears `draftMessage`. Caption: “Demo-only: messages are not persisted.” | N/A — control should not exist. | None | Delete with B12. | S |
| B14 | `student/StudentRewards.tsx:222–243` **Request redemption** | `setDemoRequested` local `Set`; button reads “Request sent (demo)”. Affordability uses `studentPoints.ts` (browser formula). | `redemption` command: requested → approved → fulfilled \| denied \| expired (ADR-0013, S9). | **No counterpart.** D6 budget owner, D7 calibration N. | Do not port the catalog or the button until S8–S9 and D6/D7. | L |
| B15 | `StudentHome.tsx:128–138` **points chip** | Link to rewards; balance is `getStudentTotalPoints` (H12 in the master plan). | Navigate to a ledger-backed catalog. | S7 | Replace the formula; keep the link once 5.4–5.5 exist. | M |
| B16 | `student/StudentHistory.tsx:95–97` **Total Attended** | Number is not clickable. Stakeholder: Past Events 5 s; Fix #12 shape. | Drill-down to the same attendance rows; performance budget S11. | Attendance read API: **none**. | Aggregate primitive from Phase 2 + S6. | M |

---

## Coordinator portal

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B17 | `coordinator/CoordinatorOutreach.tsx:211–216` **Send** | `handleSend` (`:69–77`): `console.log("Message sent:")`, then “Message sent!” for 2 s, then close. No fetch. | Consent-gated outreach command; never send to scraped addresses (F-004, `consent.py`). | **No send resource.** R4, G4. | Remove fake success. Disable until R4. | L |
| B18 | `CoordinatorOutreach.tsx:256–261` **create thread** | `handleNewThread` (`:79–87`): `console.log`, fake success, close. Thread list unchanged. | Create a durable thread/command for a named event. | **No counterpart.** | Same as B17. | L |
| B19 | `CoordinatorOutreach.tsx:117–120` **Agentic outreach** | Opens `AgenticOutreachPanel`, which POSTs `/api/outreach/agentic-workflow/stream` (not in OpenAPI). | Jarvis is R5 and must not be a parallel send path (DESIGN.md §1.7). | **No counterpart.** R3/R5 agent work is explicitly not in Foundation. | Do not port the panel. | L (do not schedule) |
| B20 | `src/components/AgenticOutreachPanel.tsx:324–328` **Approve & Send** | `setPhase("approved")`. Banner: “Outreach sent ✓ Pipeline updated — Speaker contacted successfully.” No second request. | Same confirmation UI as conventional send; nothing executes from the stream. | Send path **absent**. | Delete. Unconditional success is v1.1 §3.6 N2. | S to delete |
| B21 | `AgenticOutreachPanel.tsx:330–335` **Reject** | `setPhase("rejected")`. Optional reason is never submitted. | Audited rejection of a draft command. | **No counterpart.** | Delete with B19. | S to delete |
| B22 | `coordinator/CoordinatorMeetings.tsx:189–193` **Book** | `handleBook` (`:58–67`): `console.log`, fake success 2.5 s, dialog closes, meetings list unchanged. | Scheduling command storing UTC + IANA zone + precision (ADR-0010). ICS only until G5. | **No counterpart.** | Remove fake success. | L |
| B23 | `CoordinatorMeetings.tsx:136` **Join / meeting link** | `href={mtg.meeting_link}` from portal GET. If the legacy payload invented join URLs, this is F-003-class fabrication. | Only render provider links that the server marked as observed. | Meeting read API: **none**. | Provenance on the link; refuse unlabeled URLs. | M |
| B24 | `coordinator/CoordinatorEvents.tsx:138–145` **Request Match** | `Link` to `/ai-matching` (admin matcher, no guard). | Coordinator intake command for staffing. Matcher blocked on G1. | Match runs: **blocked G1**. Intake: **none**. | New intake command; do not deep-link the admin scoreboard. | L |
| B25 | `coordinator/CoordinatorHome.tsx:133–161` **stat tiles** | Not clickable. Rendered *before* Quick Actions (`:164`). | Actions first; click-through is same-query drill-down; when n is small, list names (Fix #13). | Coordinator read models: **none**. | Layout + S1 primitive. | M |

---

## Volunteer / professional portal

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B26 | `volunteer/VolunteerProfile.tsx` **(missing Save)** | Page is display-only: region, board role, recovery, fatigue %. No control to correct availability or workload. | Professionals must correct the data used about them (DESIGN.md §1.6). | ELI + profile write: **none** (eli.py proposed; D2). | Add editors only after the write API exists. | L |
| B27 | `volunteer/VolunteerAssignments.tsx` **assignment cards** | No accept, decline, ICS, or “I need rest”. | Accept/decline command; ICS from `ics.py`; rest/availability feeds ELI. | **No counterpart.** R2. | New commands; do not invent a local stage toggle. | L |
| B28 | `volunteer/VolunteerHome.tsx:166–179` **View assignments / profile** | Navigation works. Destination cannot fulfill §1.6 (B26). | Keep nav; pair with B26/B27. | Same as B26–B27 | — | S (nav) / L (destinations) |

---

## IA admin portal

| ID | Location | Current behavior | Expected behavior | Backend needed | Fix approach | Effort |
|---|---|---|---|---|---|---|
| B29 | `pages/Dashboard.tsx:986–993` **Connect** | `handleConnect` (`:442–456`) calls `initiateWorkflow` → `POST /api/outreach/workflow`. Modal shows loading/error; success claims pipeline updated. | Consent-gated outreach command; job id + SSE, not a synchronous “workflow”. | `/api/outreach/workflow` **not in OpenAPI**. Jobs API exists for *other* commands. | Do not call the legacy path. After R4, use the command pattern (`202` + `events_url`). | L |
| B30 | `pages/AIMatching.tsx:879–882` **Initiate outreach** | `openWorkflowModal` (`:504–523`) — same `initiateWorkflow`. | Same as B29. Matcher results themselves are mockable (H10). | G1 + match_run **and** R4 send. | Dark the button until both exist. | L |
| B31 | `AIMatching.tsx:887` **Log feedback** | Opens `FeedbackForm` → `POST /api/feedback/submit` (`api.ts:999`). | Feedback command; empty set must not become 0% (S2). | Domain `feedback.py`; **no HTTP**. R2. | New resource; client must preserve `null` rates. | M |
| B32 | `pages/Outreach.tsx:463–466` **Save Draft** | `<button>` **no `onClick`**. | Persist a draft (versioned, actor from token). | **No counterpart.** R4. | Remove until the command exists, or implement the command. | S to remove / L to implement |
| B33 | `Outreach.tsx:412–418` **AI Enhance** | `handleAIEnhance` (`:146–150`) appends a hard-coded sentence to the body. | Visible typed intent, editable, with autonomy tier (R5). Labeled “model output”. | **No counterpart.** | Delete the fake enhance. | S |
| B34 | `Outreach.tsx:455–461` **Generate / Refresh** | `generateEmail` → `POST /api/outreach/email`. On failure, error string; no unlabeled seed email if the fetch throws — but templates already fill the body. | Deterministic template labeled “AI unavailable” if no model (DESIGN.md §1.2). | **No counterpart.** | Template-only until R4; provenance “deterministic template”. | M |
| B35 | `Outreach.tsx:467–473` **ICS** | `generateIcs` → `POST /api/outreach/ics` then `downloadTextFile`. Legacy generator fabricated dates (F-003). | Domain `ics.py` only; refuse unresolved. | Domain yes; HTTP no. | New command wrapping `ics.py`; golden tests already exist. | M |
| B36 | `Outreach.tsx:445–452` **Referral QR** (`QRCodeCard` primary) | `generateQrAsset` → `POST /api/qr/generate`. | Attendance QR (MM-F02), not a “referral” side channel, unless a later contract says otherwise. | **No counterpart.** | Fold into B08’s check-in design; do not port “referral QR” without a contract. | L |
| B37 | `Outreach.tsx:534–538` **Create Template** | Closes the dialog. Name `<input>` is uncontrolled; nothing is stored. | Save a named template or do not offer Create. | **No counterpart.** | Remove dialog or add a command. | S to remove |
| B38 | `components/CrawlerFeed.tsx:214` **Start crawl** | `startCrawl` → `POST /api/crawler/start`. | R3 research scout, after crawler threat model. | **No counterpart.** Explicitly not Foundation. | Do not port. | L (do not schedule) |
| B39 | `CrawlerFeed.tsx:203` / `:263` **Clear / load saved** | `DELETE` / `GET /api/crawler/results`. | Same as B38. | None | Do not port. | S to delete |
| B40 | `pages/Opportunities.tsx:327` **Run matcher** | `navigate("/ai-matching", { state: { eventName } })`. Destination ranks via missing API then `MOCK_RANKED_MATCHES`. | No navigation to a fixture scoreboard. Matching after G1/M8. | Gate G1, M8, then a match_run read. | Disable until W5. | L |
| B41 | `pages/Dashboard.tsx:554–581` **MetricCard** links | `href` to `/opportunities`, `/volunteers`, `/calendar`, `/pipeline` — different queries (Fix #12). | Clicking N opens the N rows from the owning query (ADR-0011). | Metric register + read APIs: **none** (S1, S12). | Replace `href` with the Phase 2 drill-down slot. | M |
| B42 | `pages/Pipeline.tsx:308–329+` **funnel tiles** (Matched, Contacted, …) | Counts from client `stageCount`; **not clickable**. Two pages can disagree with Opportunities (Fix #5). | One owning query (S12); each tile drills down (S1). | **No counterpart.** | Do not port the five independent counters. | L |

---

## Cross-cutting controls that look live

These are not extra IDs; they are how several rows above fail in the same way.

| Pattern | Where | What to do |
|---|---|---|
| `console.log` + `setTimeout` success | B17, B18, B22 | Ban in the new app. Success requires a 2xx of a command that committed. |
| Local `Set` as “request sent” | B10, B11, B14 | Ban. Optimistic UI only after an accepted command id. |
| Vite proxy `/api` → `:8000` | `vite.config.ts:20–25` | Keep as a *dev* proxy to the revamped API, not as a promise that legacy paths exist. |
| `DemoModeBadge` | Many pages | Not a substitute for per-value provenance. Do not treat “we showed the badge” as Fix #8 closed. |
| Fallback people `stu-001` / `coord-001` / `shana-demarinis` | Every portal `getSession` | If session missing → login, never a default id. That default makes every button above run as someone else. |

---

## Mapping to OpenAPI (what *can* be wired without new resources)

**None of the 42 controls** bind to a path in `contracts/openapi/smartmatch.json` today.

The only interactives a later team can build *without* inventing routes are
**new** screens, not rows in this table:

- Submit import (`POST /v1/units/{unit_id}/imports`) — no legacy button.
- Follow job (`GET /v1/jobs/{job_id}`, `GET …/events`) — no legacy button.
- Redrive / abandon — no legacy button.
- Unsubscribe (`GET /u/{token}`) — no legacy button.

Until those exist as UI, every advertised action in the retrieved frontend is
either a stub, a call to a deleted legacy route, or a navigation into another
stub.

---

## Suggested deletion set (effort S, do first when D-0 lifts)

Safe to remove rather than “fix”: B02, B12, B13, B20, B21, B32 (if R4 is far),
B33, B37, B38, B39. They teach the wrong success story. The rest wait on
contracts listed in the master plan’s Phase 5–8.
