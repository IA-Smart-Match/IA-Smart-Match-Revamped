# Smart Match frontend design and integration standard

**Status:** Active and authoritative

**Applies to:** `apps/web/legacy-frontend` and any replacement frontend created under `apps/web`

**Last updated:** 2026-09-03

This file is the implementation contract for people and coding agents changing the Smart Match frontend. Read it before editing a screen, component, route, or frontend API call. Existing code may not satisfy every rule yet; new work must move toward this standard and must not introduce a new exception.

The priorities, in order, are:

1. Show truthful, authorized data.
2. Make the next action clear to a non-technical user.
3. Use the CPP visual system consistently.
4. Work well with a keyboard, screen reader, phone, and desktop.
5. Reuse shared components and contract-backed API adapters.

When this document conflicts with a screenshot, prototype prompt, fixture, or old frontend implementation, follow this document. When it conflicts with the API contract, the API contract is authoritative for data and behavior.

## Agent quick start

Before changing the frontend:

- Read this file and `apps/web/AGENTS.md`.
- Inspect the relevant route and its nearest shared shell/component before creating anything new.
- Inspect [`contracts/openapi/smartmatch.json`](../../contracts/openapi/smartmatch.json) before wiring data. Never infer an endpoint or response shape from a mockup.
- Reuse the brand tokens in `src/styles/theme.css`, font roles in `src/styles/fonts.css`, and API boundary in `src/lib/api.ts`.
- Preserve `null`, provenance, authorization, tenant/unit scope, and event time-zone information from the API.
- Do not add hard-coded statistics, identities, roles, successful outcomes, or production-looking fixture records.
- Finish with the checks in [Definition of done](#definition-of-done).

## Product voice

Smart Match helps people coordinate volunteers and events. Write for a person doing that work, not for a software buyer or data scientist.

### Writing rules

- Prefer a direct verb: “Find events,” “Choose volunteers,” “Send invitation,” “Review assignment.”
- Name the object and outcome. Avoid vague claims such as “optimize engagement” or “unlock insights.”
- Explain unfamiliar measurements next to where they are used.
- Use sentence case for page titles, headings, buttons, tabs, and table columns.
- Keep button labels specific. Use “Save availability,” not “Submit.”
- Explain how to recover from an error. Do not show raw server, database, or stack-trace text.
- Public pages must not call the product a demo. Signed-in fixture-backed screens must retain a visible “Synthetic data” or development notice.

### Preferred terminology

| Avoid in visible copy | Use instead |
|---|---|
| AI-driven coordination | Volunteer coordination |
| Algorithm / signals | How the match was determined |
| Pipeline | Match progress |
| CRM-style reporting | Assignment and outreach history |
| Scrape / ingestion | Find opportunities / import records |
| Fatigue Index | Break need |
| Average fatigue | Average break need |

“Break need” describes recent workload, not a medical condition or judgment about the volunteer.

- `Available`: recent workload does not indicate a break.
- `Consider a break`: recent assignments suggest checking with the volunteer.
- `Break recommended`: recent workload strongly suggests giving the volunteer time off.
- Missing evidence: `Not enough recent assignment data`.

Use `src/lib/breakNeed.ts` for these labels. Wherever a percentage appears, include: “A higher percentage means this volunteer has had more recent assignments and may need a break.” Never convert a missing value to `0%`.

## Visual system

### Brand colors

Use semantic tokens, not hard-coded hex values in components. The source of truth is `apps/web/legacy-frontend/src/styles/theme.css`.

| Token | Hex | Primary use |
|---|---:|---|
| CPP Green | `#005030` | Primary actions, active navigation, links, focus |
| CPP Gold | `#FFB81C` | Small highlights and attention accents |
| Eggwhite | `#F2EEE8` | Muted surfaces and page warmth |
| Bay Brown | `#CFBAB0` | Borders and quiet controls |
| Avocado | `#A4D65E` | Positive/supporting accents and charts |

Use white or near-white cards on an Eggwhite-tinted page background. Use restrained borders and shadows. Red is reserved for destructive actions and errors; do not use brand green as the only indication of success.

If a gradient is necessary, it may only be a subtle CPP Gold-to-Avocado accent. Do not use gradients as a page background, button fill, or text fill when a solid surface is clearer.

All foreground/background combinations must meet WCAG 2.2 AA contrast. Do not communicate state using color alone.

### Typography

| Role | Typeface | Fallback behavior |
|---|---|---|
| Page headline (`h1`) | Transducer CPP Medium/Bold | Arial Narrow, sans-serif |
| Section title and subhead (`h2`–`h6`) | Proxima Sera | Georgia, serif |
| Body, label, control, metadata | Usual | Inter/system sans-serif |

The local Transducer files live in `public/fonts`. Proxima Sera and Usual load from the licensed Adobe Fonts web project configured by `VITE_ADOBE_FONTS_URL`. Put that value in `apps/web/legacy-frontend/.env.local`; commit only the empty placeholder in an example environment file. Vite environment values are delivered to the browser, so this variable may contain only Adobe's public stylesheet URL, never an Adobe account credential, API token, or secret.

Pages must remain legible and retain their hierarchy when Adobe Fonts is blocked or slow.

### Logo

Use the horizontal CPP logo through `src/app/components/BrandLogo.tsx`. The bundled asset is `public/brand/cpp-horizontal-green.png`.

- Use meaningful alternative text such as “Cal Poly Pomona.”
- Preserve the original aspect ratio and clear space.
- Never recolor, crop, stretch, trace, or replace the logo with initials.
- Use a compact but still legible treatment in mobile headers and collapsed sidebars.

### Shape, spacing, and motion

- Use the shared radius token; cards are softly rounded, not pill-shaped.
- Reserve pills for compact statuses, filters, and tags.
- Use the established spacing scale. Prefer whitespace and grouping over extra divider lines.
- Shadows should communicate elevation, not decoration.
- Honor `prefers-reduced-motion`. No required information may depend on animation.

## Page and shell patterns

### Public landing page

- Sticky header: CPP logo, minimal navigation, and one clean text-style “Sign in” action. Do not put a bordered capsule around the top sign-in link.
- Hero headline: “Match volunteers with events where they can help most.”
- Supporting copy: “Smart Match helps coordinators find opportunities, compare volunteer experience and availability, and keep assignments organized in one place.”
- Workflow section heading: “How Smart Match works.”
- Describe finding events, choosing volunteers, and tracking assignments in plain language.
- Do not add eyebrow badges above headlines. This includes phrases such as “Volunteer coordination made clearer” and “A straightforward process.”
- Do not add hard-coded statistics, fake live activity, simulated terminals, a “View Demo” action, public demo wording, a second/lower sign-in promotion, or a sign-in link in the footer.
- End with a semantic footer whose year is generated at runtime: `© [current year] Cal Poly Pomona. All rights reserved.`

### Signed-in shells

Administrator, coordinator, volunteer, and student experiences share the same visual language but may expose different navigation based on server-authorized roles.

- The left sidebar owns the product identity, current section navigation, profile summary, and sign-out action.
- Place sign out directly beneath the profile area on desktop. Use the corresponding account area on mobile.
- Do not add a desktop top bar that repeats the page or portal name already shown in the sidebar/content.
- Use one `h1` for the page name. Do not place a generic category label such as “Volunteer management” or “Master calendar” above it.
- Do not place decorative icons beside page headings. Icons are appropriate inside actions, statuses, empty states, or navigation when they improve recognition.
- Put the action queue before summary statistics on administrator and coordinator home pages. For a small count, name the people or records rather than hiding them behind an average.
- Mobile layouts use a compact header and a usable navigation drawer. Student and volunteer tasks are phone-first; administrator and coordinator tables must remain useful at tablet and desktop widths and collapse deliberately on phones.

### Components

Use existing primitives in `src/app/components/ui` before adding a new one. A feature component may compose primitives but must not fork the visual tokens.

**Buttons**

- One primary action per region.
- Secondary actions use a quieter solid or text treatment.
- Destructive actions require clear destructive styling and confirmation proportional to impact.
- Disabled controls must explain why when the reason is not obvious.

**Forms**

- Every control has a persistent text label; placeholders are examples, not labels.
- Show validation next to the relevant field and keep entered values after a failed submission.
- Prevent duplicate submissions while a request is in flight.
- Announce success and error messages to assistive technology.

**Cards and lists**

- A card groups one subject or task. Do not wrap every text block in a card.
- Use a list/table when users compare repeated records.
- Keep primary actions and status in consistent positions across repeated items.

**Tables**

- Use real table semantics for tabular data.
- Keep columns focused on the decision the user is making.
- Provide an explicit mobile presentation; do not rely on clipping.
- Sort and filter state must be visible, keyboard operable, and reflected in accessible names.

**Charts and aggregate values**

- A chart needs a plain-language title, labeled axes/units, legend, and a non-color-only distinction.
- Supply an accessible textual summary or table.
- Every aggregate must open the exact records used to calculate it. The drill-down count must match the aggregate.
- Display source/provenance and freshness with the aggregate, not only in a page-wide disclaimer.

## Required UI states

Every data-backed region must deliberately handle these states:

| State | Required treatment |
|---|---|
| Loading | Stable skeleton or concise progress label; preserve layout where practical |
| Empty | Explain that no records exist and offer the next relevant action |
| Unknown | Say why evidence is unavailable; never render zero or a measurement-like dash |
| Partial | Keep useful results visible and name what is missing |
| Denied | Explain that the signed-in account lacks access; do not imply the record exists |
| Error | Plain-language failure plus retry/recovery when safe |
| Stale/unsynced | Show last known time and clearly label that the view is not current |
| Success | Confirm only after the backend confirms the operation |

Examples of truthful language include “Travel estimate unavailable,” “Estimate quality: coarse,” “Partial results: 3 of 5 sources,” and “Calendar not synchronized.” A deterministic fallback must be identified as a fallback rather than presented as model output.

## Data provenance and truthfulness

Every displayed value must inherit a visible source label, either directly or from a clearly bounded row/card/section:

| Label | Meaning |
|---|---|
| Observed | Entered by a person or captured by a system |
| Inferred | Derived deterministically from other data |
| Heuristic score | Calculated from the documented factor registry |
| Model output | Produced by a language or embedding model |
| Synthetic data | Fixture or seed data that is not a real-world record |

Never make an unlabeled fixture look live. Do not replace `null`, an absent field, or an `unknown_reason` with `0`, `0%`, a fabricated date/distance, or a successful state. Preserve the difference between a measured zero and missing evidence through types, adapters, components, and tests.

## Frontend-to-backend wiring contract

### Source of truth and dependency direction

The OpenAPI document at [`contracts/openapi/smartmatch.json`](../../contracts/openapi/smartmatch.json) is the source of truth for HTTP paths, methods, request bodies, response bodies, authentication, and error responses.

The dependency direction is:

```text
route/page → feature query or mutation → API adapter/client → /v1 contract → backend
```

- Pages and presentational components must not call `fetch` directly.
- Existing calls go through `src/lib/api.ts`. Keep transport details and payload normalization at that boundary, not inside components.
- New production endpoints must be added to the OpenAPI contract first. Prefer a generated TypeScript client once the repository generator is available; do not hand-maintain a second schema. Until then, isolate a minimal typed adapter in `src/lib/api.ts` and add contract coverage.
- `/v1` is the application contract. Treat older `/api/*` calls as compatibility/preview paths, not a pattern for new endpoints. `/api/health` is the documented exception.
- In local development, Vite proxies `/api` and `/v1` to `http://127.0.0.1:8000`. Keep browser calls relative so deployment can supply the origin.

### Identity, authorization, and tenancy

- Establish identity with `GET /v1/me`. Roles, grants, tenant, and allowed units come from the authenticated session/API—not a role picker, query string, or hard-coded profile.
- Route guards improve navigation but are not security. Always handle `401` and `403` from the backend.
- Scope unit data with the authorized `unit_id`. Never substitute a convenient fixture unit or trust a user-supplied tenant/role.
- `VITE_SMARTMATCH_BEARER_TOKEN` and `VITE_SMARTMATCH_UNIT_ID` are development aids only. All `VITE_*` values are public in the browser bundle; never store a production secret there.
- Cache keys for protected data must include the principal first and the relevant unit/resource IDs. Preserve the key builders and clear-on-identity-change behavior in `src/lib/queryClient.ts` and `src/lib/principalKey.ts`.

### Types and mapping

- Use contract names and exact field optionality at the network boundary.
- Map a transport DTO to a UI view model once, close to the API adapter. Do not scatter renaming, date parsing, or `null` coercion through JSX.
- Preserve stable IDs for links, keys, mutations, and cache invalidation. Never use a display name as an identifier.
- Preserve provenance, `unknown_reason`, freshness timestamps, time precision, and IANA time zone fields even when the first screen does not display all of them.
- Render an event in the event's own named time zone. A `date_only` event renders as a date, never invented midnight. An unresolved time stays visibly unresolved and cannot be presented as matchable/publishable.

### Queries, mutations, and errors

- Use React Query for authenticated server state. Query keys must be deterministic and principal-scoped.
- Do not retry `4xx` responses. Transient network/`5xx` failures may use the bounded retry policy in `src/lib/queryClient.ts`.
- Backend errors use `{ "error": { "code", "message", "details"? } }`. Branch on `ApiRequestError.code` or status, never by parsing message text.
- A successful HTTP response containing an unknown value is a valid result, not a request failure and not a reason to retry.
- Show a mutation as successful only after a successful backend response. Do not update counts, assignments, invitations, or calendar state with fake client-only success.
- Disable duplicate mutation triggers while pending. When safe, allow retry without losing user input.
- After a mutation, invalidate or update only the affected principal-scoped keys. If an optimistic update is justified, provide rollback and do not use it for irreversible/external actions.
- Respect idempotency and confirmation requirements documented by the endpoint. Never invent client-side idempotency semantics.

### Provenance and fixture-backed screens

Signed-in screens may currently consume fixture-backed compatibility endpoints. Keep their visible data-source disclosure until the response itself proves a live source. Replacing a fixture endpoint with a live `/v1` endpoint requires verifying authorization, unknown handling, and failure states—not merely removing the notice.

## Accessibility and responsive behavior

- Target WCAG 2.2 AA.
- Use native elements first and Radix primitives when richer interaction is required.
- All interaction must work by keyboard with a clearly visible CPP Green focus ring.
- Keep one logical `h1` and a sequential heading outline.
- Icon-only buttons require accessible names; decorative icons are hidden from assistive technology.
- Dialogs manage focus, have an accessible title, close by documented keyboard behavior, and return focus to the trigger.
- Status changes and asynchronous errors use an appropriate live region without causing repeated announcements.
- Touch targets should be at least 44 by 44 CSS pixels where practical.
- Check at approximately 360 px, 768 px, 1024 px, and 1440 px widths. No horizontal page overflow is acceptable.

## File ownership and reuse

Current implementation locations:

| Concern | Location |
|---|---|
| App routes and screens | `apps/web/legacy-frontend/src/app` |
| Shared UI primitives | `apps/web/legacy-frontend/src/app/components/ui` |
| Shared feature components | `apps/web/legacy-frontend/src/components` |
| Brand/theme tokens | `apps/web/legacy-frontend/src/styles/theme.css` |
| Font declarations | `apps/web/legacy-frontend/src/styles/fonts.css` |
| API adapters and network types | `apps/web/legacy-frontend/src/lib/api.ts` |
| Query/cache safety | `apps/web/legacy-frontend/src/lib/queryClient.ts` |
| Canonical API contract | `contracts/openapi/smartmatch.json` |

Do not copy a component merely to change its colors or spacing. Extend the shared primitive or add a documented variant. Keep domain calculations in the backend/domain layer; the frontend may format and explain a value but must not reimplement matching scores, eligibility, authorization, or workload rules.

## Definition of done

A frontend change is complete only when all relevant items are true:

- It follows the product voice, typography, color, layout, and shell rules above.
- It uses contract-backed data with no invented endpoint, field, identity, role, or successful response.
- Loading, empty, unknown, partial, denied, error, and success states are handled where applicable.
- Provenance and synthetic-data disclosures remain truthful.
- Keyboard navigation, focus, accessible names, heading order, contrast, reduced motion, and responsive overflow were checked.
- Existing authentication, tenant isolation, unknown-versus-zero, and no-fake-success safeguards still pass.
- New behavior has a focused automated test at the lowest useful level.

Run from `apps/web/legacy-frontend`:

```powershell
npm test
npm run typecheck
npm run build
```

Run relevant frontend contract safeguards from the repository root:

```powershell
python -m pytest tests/unit/test_frontend_auth_contract.py tests/unit/test_frontend_dashboard_accountable_contract.py tests/unit/test_frontend_matching_contract.py tests/unit/test_frontend_no_fake_success_contract.py tests/unit/test_frontend_opportunities_contract.py tests/unit/test_frontend_zero_coercion_contract.py -q
```

For a UI change, also inspect the affected route in a browser at mobile and desktop widths. A production build warning must be recorded and assessed; an unexplained test or type failure blocks completion.

## Pull request checklist

- [ ] I read this design standard before implementing the change.
- [ ] I reused shared tokens and components instead of creating a local visual system.
- [ ] Visible language is understandable without technical or marketing jargon.
- [ ] The OpenAPI contract supports every endpoint and field I used, or the compatibility path is clearly identified.
- [ ] Authentication, role, tenant/unit, and cache scope come from trusted backend/session data.
- [ ] Missing evidence remains unknown; no UI fallback turns it into zero or success.
- [ ] Provenance and fixture notices are accurate.
- [ ] I checked keyboard, focus, contrast, headings, reduced motion, and responsive layouts.
- [ ] Frontend tests, typecheck, build, and relevant Python contract tests pass.
