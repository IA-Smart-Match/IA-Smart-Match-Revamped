# Coordinator redemption queue — design

**Route:** `/coordinator-portal/redemptions`
**Reads:** `GET /v1/units/{unit_id}/redemptions/queue?status=…` (PR #200)
**Writes:** `POST /v1/units/{unit_id}/redemptions/{redemption_id}/decision`
**Sibling it matches:** `CoordinatorReviewQueue.tsx`
**Scope:** no backend, migration, OpenAPI or authz change.

## 1. Design-system pass (`/ui-ux-pro-max:ui-ux-pro-max`)

The skill's `--design-system` run for "internal admin queue dashboard approval
table minimal" recommended the **Data-Dense Dashboard** style (light and dark
supported, WCAG AA) with a slate/green palette and Fira type. The palette and
fonts are **not adopted**: `apps/web/DESIGN.md` fixes the CPP tokens and font
roles, and the brief says match the sibling. What is adopted from the skill:

- "No filtering" is the named anti-pattern for this product type, so the
  status filter is a first-class control, not a dropdown.
- Row highlighting on hover, smooth (150–300 ms) filter transitions, and
  `prefers-reduced-motion` honoured.
- UX rules applied: `confirmation-dialogs` (destructive Deny confirms
  inline), `aria-live-errors`, `empty-states` with a next action,
  `table-handling` (cards below `md`, never horizontal scroll),
  `touch-target-size` (`min-h-11`), `color-not-only`, `disabled-states`.

## 2. Tokens (all existing; no new token)

Extracted from `CoordinatorReviewQueue.tsx` and `src/styles/theme.css`.

| Role | Token / class | Value (light) |
|---|---|---|
| Page title | `text-2xl font-semibold text-foreground` | `#163229` |
| Body / copy | `text-sm text-muted-foreground` | `#59665f` on `#f8f6f1` (5.6:1) |
| Card | `rounded-xl border border-border/70 p-4` | radius `0.875rem` |
| Tab, selected | `border-border bg-muted text-foreground font-semibold` | |
| Tab, idle | `border-border/70 text-muted-foreground font-medium` | |
| Button (secondary) | `min-h-11 rounded-lg border border-border/70 px-3 py-1.5 text-xs font-medium` | |
| Button (destructive confirm) | `border-destructive/60 text-destructive` | `#ba1a1a` on white (6.4:1) |
| Focus ring | `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2` | CPP Green |
| Alert | `border-destructive/40 bg-destructive/5 text-foreground` | |
| Chip `requested` | `bg-muted text-foreground` + Clock icon | |
| Chip `approved` | `bg-primary-container text-on-primary-container` + Check icon | `#003d24` on `#d9eadf` (9.8:1) |
| Chip `fulfilled` | `bg-accent text-accent-foreground` + CheckCheck icon | `#21472f` on `#e8f2d8` (8.6:1) |
| Chip `denied` | `bg-destructive/10 text-foreground` + X icon | |
| Chip `expired` | `bg-muted text-muted-foreground` + Hourglass icon | `#59665f` on `#f2eee8` (5.0:1) |

"Fulfilled" reuses the existing `accent` pair (Avocado-tinted, the token
DESIGN.md names for "positive/supporting accents"), so the one-new-token
allowance is unused. Every chip carries an icon and a word; colour is never the
only signal.

Type: body is `Usual` (system-sans fallback), figures use `tabular-nums`.

## 3. Row spec

| Field | Source | Rendering |
|---|---|---|
| Item | `item_name` | `font-semibold text-foreground`, wraps, never truncates |
| Points | `points_cost` | `{n} points`, `tabular-nums` |
| Requested | `requested_at` | absolute `toLocaleString()` + relative "3 days ago" (`date-fns/formatDistanceToNowStrict`, already a dependency); `<time dateTime>` |
| State | `state` | chip (icon + word) |
| Actions | derived from `state` only | see matrix |

No student column exists and none is drawn. A one-line note under the intro
says tickets are anonymous by design; the empty state repeats it.

Actions by state (state machine `requested -> approved -> fulfilled | denied | expired`):

| State | Buttons | Accessible name |
|---|---|---|
| requested | Approve, Deny | "Approve {item}", "Deny {item}" |
| approved | Mark fulfilled, Deny | "Mark {item} fulfilled", "Deny {item}" |
| fulfilled / denied / expired | none | sentence: "No further decision is possible." |

Deny: first press swaps the two buttons for an inline confirm row
("Deny this ticket? No points are taken; points leave a balance only at fulfillment." — Confirm deny /
Keep). No modal. Approve and Mark fulfilled post at once.

## 4. Status filter

Segmented control, `role="tablist"`-free (plain `nav` + `aria-current`, as the
sibling), five tabs in state-machine order: Requested · Approved · Fulfilled ·
Denied · Expired. Default `requested`. The count in the selected tab's label
is `Requested (3)` **only** when that tab's response has loaded; unknown
renders `Requested` with no number (ADR-0011). Only the active tab's count is
ever known, because only one status is fetched at a time.

## 5. State matrix

| # | State | Trigger | Copy (exact) | Actions available |
|---|---|---|---|---|
| 1 | Loading | query pending | "Loading {status} tickets…" (`role="status"`) | tabs |
| 2 | Empty, requested | 200, 0 rows | "No tickets waiting. Students have not requested a reward, or every request has been decided. Tickets are anonymous by design." | tabs |
| 3 | Empty, approved | | "No approved tickets. Approve a requested ticket and it appears here until you mark it fulfilled." | tabs |
| 4 | Empty, fulfilled | | "No fulfilled tickets. Mark an approved ticket fulfilled and it is recorded here." | tabs |
| 5 | Empty, denied | | "No denied tickets. A ticket you deny is recorded here." | tabs |
| 6 | Empty, expired | | "No expired tickets. A ticket the system closed unanswered is recorded here." | tabs |
| 7 | Refused | 403 | server message verbatim (`role="alert"`); tabs stay usable | tabs |
| 8 | Rate-limited | 429 | server message verbatim ("Rate limit exceeded … Retry in N seconds.") + "The queue is unchanged; try again after that." | tabs |
| 9 | Truncated | `truncated: true` | "Showing the oldest {n} tickets; more exist at this status. Decide these to see the rest." | rows |
| 10 | Decision in flight | POST pending | row's buttons `disabled`, label unchanged; `role="status"` "Recording your decision on {item}…" | other rows |
| 11 | Decision conflict | 409 | "Someone already decided this ticket, or it can no longer make that move: {server message}" then re-read | tabs, refreshed rows |
| 12 | Decision refused | 403/404 on POST | server message; re-read | |
| 13 | Decision ok | 200 | live region: "{item} approved." / "… marked fulfilled." / "… denied."; list re-read | |
| 14 | Network error | fetch throws | "The redemption queue could not be loaded and the server gave no reason. Check your connection and try again." + Retry button | Retry |
| 15 | No unit | grant has no unit | "The server has not assigned this account a unit, so there is no redemption queue to show." | |

Rule from the sibling: after any decision, success or failure, the list is
**re-read**; nothing is spliced locally.

## 6. Accessibility checklist

- [ ] One `h1`; sections use `h2`.
- [ ] Rows in a `<ul>` (cards) below `md`, a real `<table>` with `<th scope="col">` at `md+`. Both render from the same data and both are in the DOM; the inactive one is `display:none` (Tailwind `hidden` / `md:hidden`), which removes it from the accessibility tree and the tab order, so nothing is read or focused twice.
- [ ] Every action button's accessible name includes the item name.
- [ ] One polite live region for decision outcomes; alerts use `role="alert"`.
- [ ] Filter state exposed with `aria-current="page"` and `aria-label="Ticket status"`.
- [ ] Colour never sole state signal (icon + word in every chip).
- [ ] Contrast ≥ 4.5:1 for every pair in §2.
- [ ] Focus visible (CPP Green ring, offset 2).
- [ ] `min-h-11` touch targets, 8px gaps.
- [ ] Deny confirm keeps focus inside the row (moves to Confirm deny; Keep returns to Deny).
- [ ] No horizontal scroll at 360px.
- [ ] `motion-safe:transition-colors` only; no animation carries meaning.

## 7. Wireframes

### 1280px (table)

```
Redemption queue
Reward tickets students have requested under your unit. Approve, then mark
fulfilled when the reward is handed over; deny a request that should not go
through. Tickets are anonymous by design: a ticket names the reward, not the
student.
Signed in as connector@example.edu · coordinator · /cba/finance

[Requested (3)] [Approved] [Fulfilled] [Denied] [Expired]

┌─────────────────────────────────────────────────────────────────────────┐
│ Showing the oldest 200 tickets; more exist at this status. Decide these │
│ to see the rest.                                          (only if trunc)│
└─────────────────────────────────────────────────────────────────────────┘

Item                              Points   Requested              State       Actions
Bronco Bookstore $10 Gift Card    300      18 Sep 2026, 09:12     ◷ Requested [Approve] [Deny]
                                           3 days ago
CBA Career Closet Voucher         600      20 Sep 2026, 14:05     ◷ Requested [Approve] [Deny]
                                           1 day ago
Professional Headshot Session    1000      21 Sep 2026, 08:40     ◷ Requested   Deny this ticket? No points are
                                           2 hours ago                          taken; points leave a balance only at fulfillment.
                                                                                [Confirm deny] [Keep]
```

### 360px (cards)

```
Redemption queue
Reward tickets students have …

[Requested (3)] [Approved]
[Fulfilled] [Denied] [Expired]

┌──────────────────────────────┐
│ Bronco Bookstore $10 Gift    │
│ Card                          │
│ 300 points                    │
│ Requested 18 Sep 2026, 09:12  │
│ 3 days ago                    │
│ ◷ Requested                   │
│ [Approve]  [Deny]             │
└──────────────────────────────┘
┌──────────────────────────────┐
│ CBA Career Closet Voucher     │
│ 600 points                    │
│ …                             │
└──────────────────────────────┘
```

## 8. Catalog values are tentative

The item names and costs a pilot shows come from
`docs/pilot-data/rewards-catalog-worksheet.md`, every value of which is
TENTATIVE. The page renders the server's snapshots and adds no ratification
language; the intro copy says nothing about budgets or approval.

## 9. Impeccable pass

Method: dual-agent critique (Assessment A design review; Assessment B
`impeccable detect`, 0 findings, exit 0). No browser step: no app runs on the
build machine, so the review was source-only.

Verdict before fixes: 15/15 state-matrix rows PASS, 2 of 12 a11y items FAIL,
Nielsen 30/40. Design-specificity: authored for this queue (state machine,
empty sentences, chips), generic only at the edges (focus after a decision,
5xx handling).

| Sev | Finding | Change |
|---|---|---|
| P1 | `{grant.role}` printed the stored key "coordinator"; DESIGN.md forbids exposing role keys | `visibleRoleLabel()` from `src/lib/roleLabels.ts` → "Speaker Connector". (The sibling review queue has the same defect at `CoordinatorReviewQueue.tsx:278`; left for a follow-up, out of this PR's scope.) |
| P1 | Focus dropped to `<body>` after every decision: the row unmounts on the re-read | Live region is `tabIndex={-1}`; the page focuses it once the re-read settles after a `decided` outcome. Test added. |
| P1 | A 5xx was classed "refused": raw server sentence, no retry | New `server_error` kind with its own sentence and the Try again button; 4xx still gets no retry. Test added. |
| P2 | Success sentence outranked a later "Loading…" | Order is now in-flight › loading › last outcome. Outcome still clears on tab change or next decision. |
| P2 | Heading outline skipped h2 | `<h2 class="sr-only">Tickets</h2>` above the list/table. |
| P2 | One shared `busyId` disabled only the busy row; two decisions could race | All action buttons disable while any decision is in flight (once-only, matches "decide these one at a time"). |
| P3 | Keep→Deny focus relied on `queueMicrotask` | Replaced with a commit-time `useEffect` keyed on the closing transition. |
| P3 | Long item name could overflow at 360px | `break-words` on the card `h3` and the table row header. |
| P3 | Empty copy for fulfilled/denied/expired had no next action | One clause added to each. |
| P3 | "fulfilment" vs "fulfilled" | "fulfillment". |

Accepted, not changed: only the selected tab carries a count (five reads per
render would spend the coordinator's own 120/min quota on numbers); the count
is the returned length and can sit above the truncated notice (both are what
the server said; neither claims to be the total); no pager (the cap is 200
and the sibling's `PagedList` windows drawn rows only — a follow-up if the
pilot shows queues that long).

Design-doc corrections from the pass: §3 Deny copy now matches the code
("No points are taken; points leave a balance only at fulfillment."), which
avoids naming a student; §6 wording on the hidden card/table pair corrected.
