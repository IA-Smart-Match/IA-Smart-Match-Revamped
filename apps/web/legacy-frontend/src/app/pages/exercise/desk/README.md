# The invitation desk — shared exercise layer

Shared tokens, motion and components for the class exercise redesign.
Spec: [`docs/design/class-exercise/DESIGN.md`](../../../../../../../../docs/design/class-exercise/DESIGN.md).
Page tracks compose these; they do not restyle or copy them.

```ts
// from a page in src/app/pages/exercise/
import { Button, Notice, WeightSlider, MarkerChip, ceMotion, usePrefersReducedMotion } from "./desk";
```

## 1. Tokens (§3)

| What | Where | How to use |
|---|---|---|
| Colour, type, spacing, radius, elevation, grid | `src/styles/exercise.css` | Tokens live on `.ce-root`. `ExerciseScreen` already renders it, so every page inside the shell has them. CBA screens never do. |
| Tailwind utilities | same file, `@theme inline` | `bg-ce-page` `bg-ce-surface` `text-ce-ink` `text-ce-ink-muted` `bg-ce-primary` `text-ce-on-primary` `bg-ce-gold-tint` `text-ce-gold-ink` `border-ce-line-strong` … (every `--ce-*` colour), `p-ce-1`…`p-ce-9`, `min-h-ce-target` (44px), `min-h-ce-control` (48/56px), `rounded-ce-seat/control/card/sheet/pill`, `shadow-ce-0…3`, `font-ce-display/serif/body` |
| Type roles | `.ce-type-display` `.ce-type-h1` `.ce-type-h2` `.ce-type-h3` `.ce-type-lead` `.ce-type-body` `.ce-type-reason` `.ce-type-label` `.ce-type-meta` `.ce-type-rank` `.ce-type-value` | Desktop sizes at ≥768px, 390 sizes below. Numeric roles already set `tabular-nums`; add `.ce-tabular` elsewhere. `.ce-measure` caps prose at 72ch. |
| Layout | `.ce-container` (1152 max, 16/32/40/64 side margin), `.ce-grid` (4/8/12 columns, 16/20/24 gutter), `.ce-card` (surface + elev-1 + card radius), `.ce-scroll-x` | §3.8 |
| Chart and seat colours | `--ce-series-{invited,signed,attended}-{fill,stroke}`, `--ce-seat-added`, `--ce-seat-added-mark`, `--ce-seat-open-outline` | §3.3; follow light/dark automatically |
| Browser surfaces | focus ring (3px primary, 3px offset, unlayered so no utility can thin it), selection, caret, link underline | §3.9; automatic inside `.ce-root` |
| Colour table as data | `tokens.ts` (`CE_COLORS`, `contrastRatio`) | `tokens.test.tsx` keeps it identical to the CSS and checks every pair |

Added "on-*" aliases (all existing theme values): `--ce-on-primary-tint`, `--ce-on-gold`, `--ce-on-danger`. Dark `--ce-avocado-tint` is `#29473B` (`.dark --input`); §3.2 gave none.

## 2. Motion (§5)

CSS classes (`src/styles/exercise-motion.css`, reduced-motion forms included):

| Class | Motion | Note |
|---|---|---|
| `.ce-press` | `ce-press` | Button already has it |
| `.ce-lift` | `ce-lift` | hoverable cards |
| `.ce-fade-rise` / `.ce-notice-in` / `.ce-card-save` | entrances | CSS alternative to `ceMotion` |
| `.ce-row-join` | gold wash fades over 900ms | remove the class after `CE_MOTION_MS.rowJoin` |
| `.ce-overlap-pulse` | one pulse per overlap row | set `style={{"--ce-i": index}}` for the 30ms stagger |
| `.ce-rebuildable` + `aria-busy="true"` | `ce-list-rebuilding` dims to 0.6 | |
| `.ce-choice-dim` | unchosen asking cards at 0.55 | |
| `.ce-unlock-lift` | shackle lifts 4px | |
| `.ce-skeleton` | breathing block | `Skeleton` uses it |

JavaScript (`motion.ts`, `confirmWindow.tsx`, `seatFill.tsx`):

| Export | Use |
|---|---|
| `usePrefersReducedMotion()` | `boolean`, live; pass it to everything below |
| `ceMotion(name, reduced)` | Motion props for `"fade-rise" \| "notice-in" \| "card-save" \| "row-reorder" \| "row-enter" \| "row-leave" \| "choice-dim"` — `<motion.li {...ceMotion("row-reorder", reduced)} />` |
| `CE_EASE`, `CE_SPRING_ROW`, `CE_MOTION_MS` | raw tokens |
| `useCountUp(target, { reduced, durationMs?, delayMs? })` | `ce-count-up`; once per mount; reduced → final number |
| `useConfirmWindow({ onConfirm, windowMs? })` → `{ armed, press, cancel, onKeyDown }` | `ce-confirm-window` (§6.18): first press arms for 5s, second commits, Escape/lapse reverts. A second press within `CONFIRM_GUARD_MS` (300ms) of arming is ignored (double-click). Page supplies the words. |
| `<ConfirmWindowUnderline active reduced windowMs? />` | the shrinking 2px underline; reduced → static helper derived from `windowMs` ("5 seconds") |
| `seatFillPlan({ total, taken, added })` | `ce-seat-fill` (§5.1): each seat's kind and start delay, front row first, stagger compressed to fit each step |
| `useSeatFill({ play, reduced })` → `{ step, announce, animating, skip }` | the 0/240/700/1400/1800ms clock; `play` only on the first render after a run (flipping it false → true replays from step 1); render the `aria-live` sentences when `announce` |
| `<Seat kind delayMs animate />` | one `aria-hidden` seat square, styled per §3.3 |

## 3. Components (§6)

| Component | File | Props | DESIGN.md |
|---|---|---|---|
| `ExerciseScreen` | `../ExerciseScreen.tsx` | `title`, `intro?`, `aside?`, `children` | §6.1 — `.ce-root`, compact logo, ribbon, one `h1` (focused on route change), lead, aside |
| Fictional-data ribbon | `components/provenance/SyntheticDataMarker.tsx` | `SyntheticDataBanner tone="quiet" label="Fictional data —" reason` | §6.2, ruling 5 — rendered by `ExerciseScreen`; `EXERCISE_RIBBON_LABEL` exported there |
| `Button` | `Button.tsx` | `variant?: "primary" \| "secondary" \| "quiet" \| "destructive"`, `pending?`, `pendingLabel?`, `disabled?` (stays focusable), `describedBy?`, `leadingIcon?`, + button attrs; `type` defaults to `"button"` | §6.3 |
| `Notice` | `Notice.tsx` | `message` (verbatim), `tone?: "calm" \| "problem" \| "done"`, `action?`, `children?`, `id?` | §6.20 — always `role="status"`; `ExerciseNotice` delegates here |
| `Skeleton`, `SkeletonRegion`, `SkeletonRankedRows`, `SkeletonCard` | `Skeleton.tsx` | `SkeletonRegion label="Loading the list…"` wraps blocks; `SkeletonRankedRows rows?` (8); `SkeletonCard lines?` | §6.21 |
| `MarkerChip` | `MarkerChip.tsx` | `marker` (API wire value) | §6.8 — icon + words; unknown → raw string, neutral |
| `WeightSlider` | `WeightSlider.tsx` | `id`, `label` (server's words), `value` (last accepted), `onCommit(value)`, `onLiveChange?(value \| null)` (the box's number as it changes, before any commit), `refusal?: { message } \| null` (pass the hook's `ExerciseRefusal` as is — a new object per refused attempt; the controls revert on each one and show the sentence as `role="status"`), `pending?`, `disabled?`, `name?` | §6.6, §8.6, ruling 2 |
| weight helpers | `weightValue.ts` | `strictDecimal`, `weightFieldMessage`, `clampWeight`, `formatWeight`, `weightTotal`, `formatWeightTotal` (two decimals, never a percentage), `WEIGHT_*` | same rule and words as `WeightsControls.tsx` |

`WeightSlider` owns one weight. The queue/in-flight logic stays in `WeightsControls.tsx`: render four sliders there and call its existing `commit` path from `onCommit`. A number typed in the box is committed exactly as typed, even outside 0–1: the server refuses a negative weight in its own sentence and accepts one above 1. Only the thumb's position (and weights the slider itself produces) stay on 0–1.

## 4. Rules for page tracks

1. Keep every page inside `ExerciseScreen`. `ProfileCardMockup.tsx` still renders its own loud banner outside the shell; that page's track moves it in.
2. Server sentences, factor labels, choice labels and the license line go in verbatim. New words only from DESIGN.md §11.1.
3. Data wording: "fictional profiles shaped by overall survey percentages" only. Never "real student(s)" or "respondent(s)"; no `OQ-CE-` strings in UI.
4. One primary `Button` per region; gold for at most one highlight per screen.
5. Tests: `src/test/vitestSetup.ts` stubs `ResizeObserver` for Radix Slider. For reduced-motion tests use `stubReducedMotion(true)` from `./desk/testMatchMedia`.
