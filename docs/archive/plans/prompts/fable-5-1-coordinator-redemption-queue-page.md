# Fable 5.1 — coordinator redemption queue page (design + build)

Paste the block below as the **first message** of a fresh Fable 5.1 session in
this repository. It designs and ships the coordinator-facing page for the
redemption queue API that PR #200 merged (`GET /v1/units/{unit_id}/redemptions/queue`).

Design skills are invoked in order: `/ui-ux-pro-max:ui-ux-pro-max` sets the
system (style, palette, type, UX rules), `/impeccable` runs the critique and
polish loop on what gets built.

---

```text
/goal Ship the coordinator redemption queue page for IA-Smart-Match-Revamped as one reviewed PR: a coordinator lists the reward tickets students have requested under their unit and decides each one (approve → fulfil, or deny), using only the three routes that already exist. Design first with /ui-ux-pro-max:ui-ux-pro-max, then build, then critique and polish with /impeccable. No backend change, no migration, no OpenAPI change, no new authz surface.

<role>
You are a senior product engineer on the coordinator portal. You design the page yourself and implement it yourself in this session (no subagents needed; use one code-reviewer agent at the end). You never invent data the API does not return.
</role>

<read_first order="strict">
1. contracts/openapi/smartmatch.json — the three redemption operations and schemas: RedemptionQueueResponse, RedemptionQueueItemResponse, RedemptionDecisionRequest, RedemptionResponse. Note: queue rows carry redemption_id, item_name, points_cost, state, requested_at ONLY. No student identity of any kind. `status` query param defaults to `requested`; `truncated: true` means more than the returned rows exist (no paging).
2. services/api/smartmatch_api/routers/rewards.py — read_redemption_queue and decide_redemption: roles {admin, coordinator}; the state machine `requested -> approved -> fulfilled | denied | expired`; `expired` is not a decision a human can make; 409 on a second decision; the refusal/error envelope shape.
3. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorReviewQueue.tsx — the closest sibling: a queue the coordinator works with accept/reject. Match its data hook pattern, its refusal-as-sentence rendering, its once-only button handling, and its test style. Also skim CoordinatorHome.tsx (nav/cards) and CoordinatorSpeakerRequests.tsx.
4. apps/web/legacy-frontend/src/app/routes.tsx — how coordinator-portal children are registered (path "coordinator-portal", lazy pages, role gate comment). This is a SERIAL file: touch only to add the one route.
5. apps/web/legacy-frontend/src/app/components/CoordinatorPortalLayout.tsx and navPrefetch.ts — where the nav entry and prefetch go.
6. apps/web/legacy-frontend/src/app/hooks/useRewards.ts — the student-side rewards hook; reuse its API client conventions, do NOT reuse its student-only routes.
7. docs/product/cba-role-presentation.md and docs/product/cba-terminology.md — words the coordinator sees ("ticket", "reward", "points"); use the repo's terms, not new ones.
8. docs/architecture/decisions/ ADR-0011 (unknown ≠ zero: never render 0/empty for "not loaded"; an unknown is a sentence) and ADR-0015 (rate-limit refusals are sentences too).
9. docs/pilot-data/rewards-catalog-worksheet.md — the synthetic catalog the page will show in the pilot; every value is TENTATIVE (pilot-decisions.md). The page must not present them as ratified.
</read_first>

<design_phase>
Invoke /ui-ux-pro-max:ui-ux-pro-max FIRST with this brief, and write its output to docs/design/coordinator-redemption-queue.md before writing any component:
- Product type: internal admin queue inside an existing React + legacy-frontend portal (find the stack: React, plain CSS modules or whatever the sibling pages use — match it, do not add Tailwind/shadcn or any dependency).
- Users: one coordinator, a few times a week, deciding 0–20 tickets. Speed and certainty over delight. Keyboard-first: tab through rows, Enter/Space on actions.
- Style: whatever CoordinatorReviewQueue already is — extract its tokens (colors, type scale, spacing, radius) and reuse; propose at most ONE new token if a state color is missing (e.g. "fulfilled").
- Required content per row: item name, points cost, requested-at (absolute date + relative "3 days ago", both from the API timestamp), state chip, actions permitted by the state machine ONLY (requested → Approve / Deny; approved → Mark fulfilled / Deny; fulfilled|denied|expired → none). No student name/email exists — do not leave a blank "student" column; say in the empty-state copy and a one-line note that tickets are anonymous by design.
- Status filter: segmented control over the five states, default "requested"; the count in the tab label comes only from a loaded response (unknown → no number, per ADR-0011).
- States to design explicitly, each as a sentence, never a spinner alone: loading, empty per status ("No tickets waiting." vs "No approved tickets."), refused (403 sentence from the API, page still usable), rate-limited (429 sentence + when to retry), truncated (banner: "Showing the oldest N; more exist — decide these to see the rest"), decision in flight (row's buttons disabled until the reload settles), decision conflict (409: "Someone already decided this ticket" + row refreshes), network error.
- Confirmation: Deny gets an inline confirm (second click or small confirm row), Approve/Fulfil do not. No modals.
- Accessibility: table semantics or a list with proper roles; each action button's accessible name includes the item ("Approve Bronco Bookstore $10 Gift Card"); live region announces the result sentence; color is never the only state signal; 4.5:1 contrast; focus visible.
- Responsive: usable at 360px (cards) and 1280px (table). No horizontal scroll.
- Copy: plain sentences, the repo's terminology, no exclamation marks, no "Oops".
Output of the design phase: the tokens used, the row/card spec, the state matrix (state × copy × action), the a11y checklist, and a wireframe in ASCII for both breakpoints.
</design_phase>

<build_phase>
1. Write failing tests first, in the sibling pages' test style (the repo's `npm test` runner — check package.json; Vitest cannot start on the dev machine, so also keep tests runnable in CI): renders rows from a fixture response; default filter is requested; switching filter refetches with the right `status`; only the permitted actions render per state; Approve posts {decision:"approved"} to the decision route and disables the row until reload; Deny requires confirm; 409 shows the conflict sentence and refetches; 403 renders the refusal sentence and keeps the filter usable; 429 renders the retry sentence; truncated banner; empty states per status; unknown count renders no number.
2. Implement: pages/coordinator/CoordinatorRedemptionQueue.tsx (+ one hook useRedemptionQueue.ts, + a small RedemptionTicketRow component if the page passes ~300 lines). Immutable state updates, const over let, no `any`, no console.log, no new dependencies. Reuse the API client; regenerate frontend types from the OpenAPI contract only if the repo has a generator (check package.json scripts) — never hand-edit generated files.
3. Route + nav: one child route under coordinator-portal (path "rewards" or "redemptions" — match sibling naming), lazy import with the same role-gate comment, nav entry + prefetch beside the review queue entry.
4. Run: npx tsc --noEmit, eslint, npm test, npx vite build. All clean.
</build_phase>

<polish_phase>
Invoke /impeccable on the built page: critique against the design doc's state matrix and a11y checklist, fix what it finds, re-run tests. Record the critique and what changed in the design doc under "Impeccable pass". Then run one code-reviewer agent (Output style: follow ~/.claude/rules/common/subagent-output.md (i-have-adhd)) over the diff and fix CRITICAL/HIGH before opening the PR.
</polish_phase>

<non_negotiables>
- No backend edits, no migration (head stays 0037_exercise_tables), no OpenAPI change (84 ops), no authz matrix change. If the page needs a route that does not exist, STOP and report — do not build it.
- ADR-0011: never render 0, "—", or an empty cell for something that did not load; render the sentence.
- ADR-0025 is not in play (this is CBA scope) — but do not import anything from pages/exercise.
- Anonymous rows are a product decision (owner, 2026-09-21): do not add a student identifier, do not fetch one from another route.
- Serial file routes.tsx: one additive hunk only.
- ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, ALLOW_CLOUD_DEPLOY=false.
- Commit per milestone (design doc; tests red; green; route+nav; polish). `git fetch origin && git switch -c feat/coordinator-redemption-queue origin/main` first. Commit format `<type>: <description>`; end commit messages with: Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
- Do not merge. Do not force-push. Do not skip hooks. Do not declare production readiness.
</non_negotiables>

<success_criteria>
- docs/design/coordinator-redemption-queue.md exists with tokens, state matrix, a11y checklist, both wireframes, and the Impeccable pass.
- Tests listed in build_phase step 1 exist and pass in CI (`web — install, types, build, audit` green; component tests green).
- Page reachable at the new coordinator-portal route; nav entry present; prefetch wired.
- PR via `gh pr create --base main`: Summary, screenshots or ASCII of both breakpoints, the state matrix, Test plan, Files changed (full list), ends with 🤖 Generated with [Claude Code](https://claude.com/claude-code). Body edits later via `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/N -F body=@file` (gh pr edit fails silently here).
- Final report: PR URL | route path | files changed | tests + CI | design decisions the owner may want to veto (max 3) | status DONE / DONE_WITH_CONCERNS / BLOCKED.
</success_criteria>
```
