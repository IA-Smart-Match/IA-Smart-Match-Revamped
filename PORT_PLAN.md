# PORT_PLAN — resync PR #125 (`frontend-dev`) onto `origin/main`

Branch: `feat/frontend-dev-resync` (base `origin/main` @ `793678b0`).
Direction: **main is the base; #125's UI is layered on top.** No raw merge.

Legend: **[F]** verified fact (from `git diff`/`git show`) · **[A]** assumption / judgement.

## 0. Audit

### 0.1 What #125 is [F]

`origin/frontend-dev` = 5 commits, merge-base `c72dced9`, 90 commits behind main,
97 files, +13912/−15276. It is **not a UI-only overhaul**. It is three things:

1. **A CPP design system** (`theme.css` palette → CPP green/gold/eggwhite/bay-brown/avocado,
   `fonts.css` → Transducer CPP + Adobe Fonts via `VITE_ADOBE_FONTS_URL`, `BrandLogo.tsx`,
   `public/brand`, `public/fonts`, restyled shells `Layout/CoordinatorPortalLayout/
   StudentLayout/VolunteerPortalLayout`, redesigned `LandingPage`, rewritten
   `apps/web/DESIGN.md` + new `apps/web/AGENTS.md`, `tests/branding.test.ts`).
2. **A new "speaker workflow" subsystem, backend + frontend**:
   - backend: `routers/speakers.py` (speakers CRUD, roster publish, per-event
     speaker match-runs, shortlist → speaker-event records with 11 statuses,
     transitions/notes/corrections, close-attendance, cancel),
     `routers/events.py` **rewritten** as manual `managed_event` CRUD + feedback-QR
     (`/q/{token}` public redirect), persistence `speaker_workflow.py`,
     `manual_events.py`, 12 new tables in `schema.py`, migrations
     `0034_manual_events`, `0035_speaker_workflow`, domain `speaker_invitations.py`,
     `speaker_matching.py`, tests `test_manual_events/test_speaker_*`.
   - frontend: `pages/Events.tsx` (admin manual events + QR), `Volunteers.tsx`
     rewritten as speaker roster, `SpeakerEventsBoard.tsx`, `useAuthorizedUnit.ts`,
     `breakNeed.ts`, `QRCodeCard.tsx` rewritten (local `qrcode` dep), ~215 lines of
     new `api.ts` adapters.
3. **A product-scope pivot that removes consented outreach/email**: deletes
   `useOutreach.ts`, `useSpeakerInvitations.ts`, `AIMatching.tsx`,
   `CoordinatorInvitations.tsx`, `AgenticOutreachPanel.tsx`, `OutreachWorkflowModal.tsx`;
   flips `Capability.CONSENTED_OUTREACH` to `False`; un-gates `events.router`; removes
   `email_api_key`, the worker's outreach-send handler, `/u/{token}` and `/i/{token}`
   pages; deletes/guts ~20 Python frontend-contract tests
   (`test_frontend_invitation_compose_contract` −368, `test_frontend_match_run_contract`
   −343, `test_frontend_handoff_contract` −336, `test_resend_email_adapter` −524, …).
   Its DESIGN.md states: "Email templates, batch invitation actions, send controls …
   do not belong in the frontend or API boundary."

### 0.2 What main has that #125 lacks [F]

Routes on `origin/main` absent from #125's `routes.tsx`:

| Route (main) | Page | #125 status |
|---|---|---|
| `/` → `Home` (portal redirect wrapper) | `Home.tsx` | #125 mounts `LandingPage` directly (Home added on main after divergence) |
| `/ai-matching` | `AIMatching.tsx` | deleted, redirected to `/events` |
| `/opportunities` | `Opportunities.tsx` | redirected to `/events` |
| `/outreach` (capability-gated) | `Outreach.tsx` | gutted to 2 lines, ungated |
| `/pipeline` | `Pipeline.tsx` | kept, −225 lines |
| `/coordinator-portal/speaker-contacts` | `CoordinatorSpeakerContacts.tsx` | route dropped |
| `/coordinator-portal/match-runs` | `CoordinatorMatchRuns.tsx` | route dropped |
| `/coordinator-portal/invitations` | `CoordinatorInvitations.tsx` | file deleted |
| `/coordinator-portal/matching-weights` | `CoordinatorMatchingWeights.tsx` | route dropped |
| `/coordinator-portal/review-queue` | `CoordinatorReviewQueue.tsx` | never existed in #125 |
| `/volunteer-portal/speaker-request` | `VolunteerSpeakerRequest.tsx` | route dropped |
| `/volunteer-portal/confirmed-speaker` | `VolunteerConfirmedSpeaker.tsx` | route dropped |
| `/volunteer-portal/my-requests` | `VolunteerMyRequests.tsx` | route dropped |

Main-only frontend infrastructure since divergence: `PagedList.tsx`, `bearerToken.ts`,
`concurrency.ts`, `Home.tsx`, `CoordinatorReviewQueue.tsx`, paged list shapes in
`api.ts` (`fetchReviewItems`, `fetchMeetings`, review decisions, invitation batches,
outreach drafts/sends, `fetchUnitEvents` → `UnitEventList`), granted-unit scoping in
`useUnitMetrics/useOutreach/useRewards/useSpeakerInvitations`.

Main-only backend since divergence: `meetings.py` router/persistence + migration
`0034_cba_meeting`, review-item list, engine pool changes, pilot dataset tooling.

### 0.3 Contract collisions [F]

| Collision | main | #125 | Resolution |
|---|---|---|---|
| Migration id | `0034_cba_meeting` | `0034_manual_events`, `0035_speaker_workflow` | renumber #125's to `0035_manual_events` (revises `0034_cba_meeting`) and `0036_speaker_workflow` |
| `GET /v1/units/{u}/events` | crawler catalog `EventListResponse{data,withheld…}`; read by `CoordinatorEvents`, `StudentEvents`, contract tests | manual `managed_event` list with `?status=` | keep main's; mount #125's manual events at **`/v1/units/{u}/managed-events`** (+ `/publish`, `/feedback-qr`, `/close-attendance`, `/cancel`, `/speaker-match-runs`) |
| `POST /{u}/match-runs/{id}/shortlist` | `match_runs.py` owns `/match-runs/*` (different run model) | speaker match run | mount at `/v1/units/{u}/speaker-match-runs/{id}/shortlist` |
| `events.router` capability gating | `EVENT_READS` | ungated | keep gated; new routers classified in `CAPABILITY_SCOPED_ROUTERS` + `tests/authz/test_policy_matrix.py` |
| `CONSENTED_OUTREACH` | `True` under CBA | `False` | **keep main (True)** — main's #140–#152 invitation/feedback work depends on it |
| `/outreach` admin route | capability-gated legacy page (test-pinned) | `SpeakerEventsBoard` | board gets its own routes: admin `/invitations`, host `/coordinator-portal/speaker-handoffs` |
| Python contract tests reading TS source | ~20 files pin nav hrefs, gating, copy, adapters | gutted | **main's tests are the gate**; the port must satisfy them |

### 0.4 Backend classification [F]/[A]

| #125 backend change | Class | Action |
|---|---|---|
| speakers router, speaker_workflow/manual_events persistence, domain modules, schema tables, 2 migrations, their unit tests | **still needed** — the ported Events/Speakers/SpeakerEventsBoard UI calls these endpoints and nothing on main serves them | port additively (Track B) with the path/migration renames above [A: renames are mine] |
| `events.py` rewrite | **conflicting** | do not replace main's; port as new `routers/managed_events.py` |
| `product_scope.py` CONSENTED_OUTREACH flip, `config.py` email key removal, worker outreach removal, `main.py` `/u` `/i` page removal, un-gating | **conflicting with main** | not ported — human decision (see §4) |
| test deletions/gutting | conflicting | not ported; main's tests stay |
| ADR/decision docs (`manual-events-and-feedback-qr-2026-09-07.md`, `decisions/README.md`) | additive | port the decision doc; ADR-0018 file is referenced in the stat but absent from the tree [F] |

## 0.5 Codex plan-gate review (external peer review)

Requested model `sol-5.6` → rejected by the Codex backend ("not supported when using
Codex with a ChatGPT account"); fallback `gpt-5.4` → also rejected; the review ran on
the codex plugin's **default model** [F: `codex-companion.mjs status` shows both 400s].

Asked: is the additive backend port sound, what does the parity table miss, are track
boundaries disjoint, which contract tests will break, what silently drops a feature.

| # | Codex finding | Disposition |
|---|---|---|
| 1 MUST-FIX | Renaming #125's speaker-workflow backend to `/managed-events` + `/speaker-match-runs` still ships a second speaker pipeline beside main's speaker-contacts / match-runs / invitation batches / handoff / confirmed-speakers. Rebuild the UI on main's pipeline; port only what main genuinely lacks. | **Accepted.** Track B is cut to *manual event creation + per-event feedback QR* (the 2026-09-07 decision doc's scope), which main has no write path for. `speakers.py`, `speaker_workflow.py`, `0035_speaker_workflow`, domain `speaker_*` modules and `SpeakerEventsBoard` are **not ported**; their user-facing intents map onto main's existing surfaces (§3 parity table). |
| 2 MUST-FIX | A separate `managed_event` table is invisible to main's catalog (`GET /events`, `CoordinatorEvents`, `StudentEvents`) and stores speaker PII main withholds. Settle the canonical event/contact mapping first. | **Accepted.** Manual events are written into the canonical `event` table (`origin="manual"`, `filed_by_user_id`, ADR-0010 temporal columns) through `EventRepository`, so main's reads list them with provenance. Event-level extra fields go in a side table added by migration `0035_manual_event_detail`. No speaker contact table is added. |
| 3 MUST-FIX | Parity table hides behavioural loss: `/volunteers` (−923 lines in #125), `/coordinator-portal/meetings` (real CRUD on main vs placeholder in #125), `CoordinatorEvents` (withheld counts/paging). | **Accepted.** Rule for every main page: **main's implementation is retained and restyled**; #125's versions are design reference only. §3 table now has a "behaviour source" column. |
| 4 SHOULD | Ownership overlaps: `QRCodeCard.tsx` in C and D1; `LoginPage.tsx`, `main.tsx` unowned. | **Accepted.** Explicit owner list per track below; every path appears in exactly one track per wave. |
| 5 MUST-FIX | Gates omit the Python contract tests most likely to break under restyle; do not pre-accept `.env` failures. | **Accepted.** Baseline `make check` in this worktree is green (4885 passed, exit 0) so the gate is fully green; each track prompt names the contract tests it must keep passing. |

## 1. Tracks (disjoint file ownership)

Wave 1 (parallel, disjoint trees):
- **Track A — design system, shells, landing, docs.** Owns (all under `apps/web/`): `DESIGN.md`, `AGENTS.md`, `README.md`, `legacy-frontend/package.json`, `package-lock.json`, `index.html`, `public/**`, `src/main.tsx`, `src/styles/**`, `src/app/components/{BrandLogo,Layout,CoordinatorPortalLayout,StudentLayout,VolunteerPortalLayout,MetricCard,CaliforniaCampusHeatmap,PipelineFunnelTiles,RouteFallback,SessionGate,PortalGate,PortalContent}.tsx`, `src/app/components/ui/**`, `src/app/pages/{LandingPage,LoginPage,Home}.tsx`, `tests/branding.test.ts`.
- **Track B — backend manual events + feedback QR** on the canonical `event` table. Owns: `services/api/smartmatch_api/routers/manual_events.py` (new), `services/api/smartmatch_api/main.py`, `python/smartmatch_persistence/smartmatch_persistence/{schema.py,manual_events.py}`, `db/migrations/versions/0035_*`, `contracts/openapi/smartmatch.json`, `tests/authz/test_policy_matrix.py`, `tests/unit/test_manual_events.py`, `tests/contract/test_manual_events_api.py`, `docs/decisions/manual-events-and-feedback-qr-2026-09-07.md`.

Wave 2 (after A and B; parallel, disjoint files):
- **Track C — api.ts + Events page + routes.** Owns: `src/lib/{api.ts,breakNeed.ts}`, `src/app/hooks/useAuthorizedUnit.ts`, `src/app/pages/Events.tsx` (new), `src/components/QRCodeCard.tsx`, `src/app/routes.tsx`, `src/app/components/Layout.tsx` (nav entry only), `tests/manual-events.test.ts`, `tests/unit/test_frontend_manual_events_contract.py`.
- **Track D1 — admin pages restyle.** Owns: `src/app/pages/{Dashboard,Pipeline,Calendar,Opportunities,AIMatching,Volunteers,Outreach}.tsx`, `src/components/{AgenticOutreachPanel,OutreachWorkflowModal,CrawlerFeed,FeedbackForm,AppIcon}.tsx`, `src/app/components/{DiscoveryFeed,CrawlerContext}.tsx`.
- **Track D2 — coordinator portal pages restyle.** Owns: `src/app/pages/coordinator/**`.
- **Track D3 — student + volunteer portal pages restyle.** Owns: `src/app/pages/student/**`, `src/app/pages/volunteer/**`, `src/app/components/PagedList.tsx`, `src/app/components/provenance/**`.

Wave 3 — orchestrator integration: full gates, parity table, PR.

Per-track ledger (SHAs filled as they land):

| Track | Agent | Commits | Status |
|---|---|---|---|
| A | sonnet | b1ab8765, a0eed51a, d884a93d, 3a83cad1 | done — verified by orchestrator (99 contract tests pass, build ok, npm test 55/2 = baseline) |
| B | sonnet | 80782134, 2863358c, 03d0b615, c7a86539, f88ab5d4 (+ resume: fail-closed gate allowlist, router split) | endpoints verified by orchestrator: POST/GET/PATCH/publish/feedback-qr on canonical `event` + `/q/{token}`; migration 0035_manual_event_detail ← 0034_cba_meeting; openapi-check current (63 paths, +4); targeted pytest exit 0. Full `make check` pending on resume |
| C | sonnet | 7ae4687e, de6aadfe, ca777cf2 (+0052f12d ruff fix) | done — verified: 6 additive api.ts adapters, no main export removed, Events page 350+352 lines, no raw fetch, `/events` route + nav added, all 32 main route literals intact |
| D1 | sonnet | eb1f75f1, 4b68e89, d02553e, 286ef276, a9f077a9 (salvaged WIP: chart/badge tokens — reviewed, correct) | done — Dashboard/Calendar/Volunteers split into *Sections.tsx; one `text-gray-900` kept in Opportunities.tsx because test_frontend_opportunities_contract.py:338 pins it verbatim |
| D2 | sonnet | 2ec171be, f79254af, 0f2f6ea2 | done — diff verified: coordinator pages were already token-based, so Track A's palette restyled them; D2 added 44px targets + focus rings only (16 lines) |
| D3 | sonnet | 15907c4e | done — diff verified: student/volunteer/PagedList/provenance already token-based; 2 files, 3 lines (destructive tokens in MetricDrilldownSheet, sentence-case h1) |

## 2. Validation gates

- `cd apps/web/legacy-frontend && npm run build` (= `tsc --noEmit && vite build`), `npm test`.
- `make check VENV=/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/.venv`
  (3 known `.env`-caused failures on this machine; names recorded in §3 when run).
- `make scan` (CBA terminology), `make openapi-check`.
- Route-by-route parity table (§3).

## 3. Results (HEAD a9f077a9)

### 3.1 Gates [F]
| Gate | Result |
|---|---|
| `npm run build` (tsc + vite) | exit 0 |
| `npm test` | 60 pass / 2 fail — both pre-existing on `origin/main` (`tests/productScope.test.ts`: "every capability carries an explicit decision", "enabledCapabilities returns exactly the preserved set" — 13 != 12); identical on untouched main baseline |
| `make check VENV=…` (at 0052f12d, before the tsx-only WIP commit) | exit 0 — 5047 passed, 2 skipped (baseline main: 4885 passed) |
| frontend/CBA contract pytest subset at a9f077a9 (`-k "frontend or cba_surface or cba_terminology or shortlist_fanout or manual_events"`) | exit 0 |
| `make scan` | clean (150 CBA-visible files) |
| `make openapi-check` | current (63 paths; main had 59; +`POST/GET/PATCH …/events[/{id}]`, `/publish`, `/feedback-qr`, `/q/{public_token}`) |
| `make migrate-check` | NOT run (needs PostgreSQL; prohibited from running migrations) |
| Files deleted vs main | none |
| main `api.ts` exports missing on branch | none |
| The 3 `.env`-caused failures | did not occur — this worktree has no `.env` |

### 3.2 Route parity (routes.tsx, `path:` literals, main vs branch) [F]
`diff` of sorted route literals: the ONLY difference is `+ path: "events"` (admin layout). Every main route below is present and mounted to the same page implementation (restyled, behaviour retained):

| Route | main | branch | Page behaviour source |
|---|---|---|---|
| `/` | Home → LandingPage | same | main (Home portal redirect) + #125 landing copy/visuals |
| `/login` | LoginPage | same | main |
| `/student-portal` + events/history/connect/rewards/speaker-feedback | 6 | 6 | main |
| `/coordinator-portal` + events/outreach/speaker-contacts/speaker-feedback/match-runs/invitations/matching-weights/meetings/review-queue | 10 | 10 | main |
| `/volunteer-portal` + speaker-request/confirmed-speaker/my-requests/assignments/profile | 6 | 6 | main |
| `/dashboard` `/opportunities` `/volunteers` `/ai-matching` `/pipeline` `/calendar` `/outreach`(gated) | 7 | 7 | main |
| `/events` (admin) | — | **new** | #125 concept rebuilt on Track B backend |

### 3.3 #125 surfaces → disposition
| #125 surface | Disposition |
|---|---|
| CPP tokens, fonts, logo, shells, landing, DESIGN.md/AGENTS.md, branding test | **preserved** (Track A) |
| Admin Events page + feedback QR (manual events) | **preserved**, rebuilt on canonical `event` table (B + C) |
| `useAuthorizedUnit.ts`, `breakNeed.ts` | ported (breakNeed currently unused — kept because DESIGN.md names it) |
| `/opportunities`→`/events`, `/ai-matching`→`/events` redirects | **rejected** — would drop main routes pinned by tests |
| Speakers roster page (replacing Volunteers) | **superseded** by main's `/coordinator-portal/speaker-contacts` (§13 roster) — human decision §4.1 |
| `SpeakerEventsBoard` (11 manual statuses) | **superseded** by main's invitation batches / outcomes / handoff / confirmed-speakers — human decision §4.1 |
| Backend `speakers.py`, `speaker_workflow.py`, `0035_speaker_workflow`, outreach/email removal, capability flip | **not ported** (§0.5 Codex finding 1–2; §4.1) |

## 4. Deferred / human decisions

1. **Product-scope pivot in #125 (outreach/email removal) was NOT ported.** #125's DESIGN.md
   and its decision doc say email/batch invitations are out of the product; main's #140–#152
   built exactly those. This branch keeps main's behaviour and both feature sets coexist
   (manual speaker-event tracking beside consented invitation batches). Someone must decide
   which is the product. DESIGN.md's "Speaker roster and invitation workflow" section is
   reworded to describe what actually ships.
2. Migration renumbering and path renames in §0.3 are orchestrator choices, not customer
   decisions; review before merge.
3. Draft manual events are not listed by main's `GET /v1/units/{u}/events` (presentable-only); the Events page keeps a session-local "recent" list seeded from create/patch/publish responses [A, Track C]. A drafts-list endpoint is a follow-up if wanted.
4. Codex reviews ran on the codex plugin's default model: `sol-5.6` and `gpt-5.4` were both rejected by the backend at the time; the coordinator later said `gpt-5.6-sol` is available — no further Codex gate was triggered (no critical/ambiguous bug arose after the plan gate).
5. `VITE_ADOBE_FONTS_URL` is unset in the repo — Proxima Sera/Usual fall back to
   Georgia/Inter until an ops owner supplies the Adobe project URL.
