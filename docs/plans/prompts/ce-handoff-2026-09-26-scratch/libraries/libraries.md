# Component & asset shortlist — class exercise visual refresh

Stack confirmed from `apps/web/legacy-frontend/package.json`: React 18.3.1, Radix UI primitives (13 packages), `motion` 12.23.24 (Framer Motion's renamed package), `recharts` 2.15.2, `lucide-react` 0.487.0, `sonner` 2.0.3, `canvas-confetti` 1.9.4, `class-variance-authority` + `tailwind-merge` (shadcn-style setup), Tailwind CSS 4.1.12, `@iconify/react`, `@mui/material` (present but unused in exercise pages — do not add to it). Brand tokens live in `apps/web/legacy-frontend/src/styles/theme.css` (CPP green `#005030`, gold `#ffb81c`); brand fonts in `src/styles/fonts.css` are licensed (Transducer CPP, proxima-sera, usual) — not Google Fonts, so a Google Fonts pick below is for supplementary use only, not a replacement.

## 1. Component primitives

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Radix UI primitives** (already used) | Unstyled, accessible; matches existing `@radix-ui/react-*` set (slider, dialog, tabs already in the exercise flow) | MIT | ~2-5 KB/primitive | Yes | Yes |
| Alternate: shadcn/ui pattern (cva + tailwind-merge, no runtime dep) | Codegen approach, copies source into repo; `class-variance-authority`/`tailwind-merge` already installed, just missing the `components/ui` folder convention | MIT | 0 KB (source copied) | Yes | Partially (deps yes, generator not run) |

## 2. Motion / animation

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Motion (`motion` npm package, formerly Framer Motion)** | Already a dependency (12.23.24); `AnimatePresence`, `layout` animations cover reordering and reveals | MIT | ~18 KB gzip (motion/react entry) | Yes | Yes |
| Alternate: native View Transitions API (`document.startViewTransition`) | Zero JS cost for the results "reveal" page transition; supported in Chrome/Edge, graceful no-op elsewhere | Web std | 0 KB | Yes | N/A (browser API) |

## 3. Number & rank transitions

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Motion's `animate()` + `useSpring`/`useMotionValue`** for counters, `layout` prop on list items for reordering | One library covers both counters and list reorder, no new dependency | MIT | included in Motion | Yes | Yes |
| Alternate: `@formkit/auto-animate` for the ranked list | Drop-in `useAutoAnimate()` hook, zero-config FLIP reordering, very small | MIT | ~2.2 KB gzip | Yes | No (new dep) |

## 4. Charts (seats, sign-up funnel)

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Recharts** (already used in `ExerciseResultsChart.tsx`) | Existing bar chart already implements the accessible-table fallback and hatch-pattern requirement; keep it, restyle only | MIT | ~90 KB gzip (already paid) | Yes | Yes |
| Alternate: `visx` (Airbnb) for a custom funnel/seat-grid visual if Recharts can't express it | Low-level primitives, full control over the seat-grid metaphor | MIT | pick-your-parts, ~10-20 KB per module | Yes | No (new dep) |

## 5. Icons

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **lucide-react** (already used) | Consistent stroke icon set already in the app; has seat/chair, mail, users, badge glyphs needed here | ISC | tree-shaken per icon (~1 KB each) | Yes | Yes |
| Alternate: `@iconify/react` (already installed) for one-off glyphs lucide lacks (e.g. envelope-open, party-popper variants) | Already a dependency, pulls from Iconify's aggregated open sets on demand | MIT (per-icon-set) | on-demand fetch/bundle | Yes | Yes |

## 6. Illustrations / SVG spot art

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Author original inline SVGs** (see `assets/`) | No licensing risk, matches brand palette exactly via `currentColor`/CSS vars, tiny | N/A (original) | <4 KB each | Yes | N/A |
| Alternate: `unDraw` (recolorable open-licence illustration set) for filler scenes beyond the 8 authored here | Free for commercial/personal use, no attribution required, SVGs recolor to brand palette | MIT-style (unDraw licence) | varies, pick per-asset | Yes | No (manual download) |

## 7. Fonts (Google Fonts only, supplementary — brand fonts stay as-is)

| Pick | Fit | Licence | Notes |
|---|---|---|---|
| **Public Sans** | Neutral, highly legible geometric sans; good stand-in for `--font-body` on any surface where the licensed "usual" font isn't loaded (e.g. print/export) | OFL | Google Fonts |
| Alternate: **Space Grotesk** | Slightly playful geometric display face for headlines/badges (team badge, empty-state), pairs well with CPP green/gold without competing with "Transducer CPP" | OFL | Google Fonts |

## 8. Sliders

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **`@radix-ui/react-slider`** (already used in `WeightsControls.tsx`) | Already wired to the 4 weight sliders; keep behavior, restyle track/thumb/value-bubble only | MIT | ~3 KB | Yes | Yes |
| Alternate: none needed — do not add a second slider library | — | — | — | — | — |

## 9. Toasts

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Sonner** (already used) | Already installed; supports stacked, swipeable toasts good for "settings saved" / "results unlocked" notices | MIT | ~4 KB gzip | Yes | Yes |
| Alternate: none needed | — | — | — | — | — |

## 10. Skeleton / loading states

| Pick | Fit | Licence | Bundle | React 18/19 | Installed |
|---|---|---|---|---|---|
| **Hand-rolled Tailwind skeleton** (`animate-pulse` + `bg-muted` token) | Zero new dependency; `ExerciseLoading` in `ExerciseScreen.tsx` already exists as the hook point — restyle it as a skeleton, not a spinner | N/A | 0 KB | Yes | Yes (Tailwind util) |
| Alternate: `react-loading-skeleton` if a shimmer effect is wanted beyond `animate-pulse` | Configurable shimmer skeletons, low footprint | MIT | ~3 KB gzip | Yes | No (new dep) |

---

## Motion spec

All durations/easings assume Motion (`motion/react`); all patterns get a `prefers-reduced-motion` fallback via `useReducedMotion()` (Motion hook) or the CSS media query, downgrading to a instant/opacity-only change.

1. **Ranked list reordering on slider move**
   - `layout` prop on each list-row `motion.li`, spring transition `{ type: "spring", stiffness: 500, damping: 40 }` (~250 ms perceived settle).
   - Reduced motion: disable `layout` animation, snap to new position, keep a 150 ms opacity crossfade only.

2. **Results "reveal" on instructor unlock**
   - Container fade+rise: `initial={{ opacity: 0, y: 16 }}`, `animate={{ opacity: 1, y: 0 }}`, `duration: 0.4s`, `ease: [0.16, 1, 0.3, 1]` (expo-out), staggered per panel with `staggerChildren: 0.08`.
   - Reduced motion: opacity-only fade, `duration: 0.15s`, no y-offset, no stagger.

3. **Seat-count ticking**
   - Animate the numeric value with Motion's `animate(from, to, { duration: 0.8, ease: "easeOut" })` driving a `useMotionValue` rendered via `useTransform(Math.round)`.
   - Reduced motion: no count-up; render the final number immediately.

4. **Saved-setting cards**
   - Card entrance: scale+fade `initial={{ opacity: 0, scale: 0.96 }}` → `{ opacity: 1, scale: 1 }`, `duration: 0.2s`, `ease: "easeOut"`.
   - Selected-state border highlight: `boxShadow` transition `0.15s ease-in-out` (color token, not motion-sensitive — keep in reduced motion).
   - Reduced motion: entrance becomes an immediate opacity swap (0.05s), no scale.

5. **Compare-highlight pulses**
   - One-shot pulse ring using `keyframes` on `boxShadow`/`outline-color` opacity: `[0, 1, 0]` over `0.6s`, `ease: "easeInOut"`, fired once on comparison-select, not looping.
   - Reduced motion: replace the pulse with a static outline (`outline: 2px solid var(--primary)`) applied for the same 0.6s then removed, no animated ring.

---

## What could not be verified

- No `tailwind.config.*` file found — this project uses Tailwind CSS 4's CSS-first config (`@theme`/`@custom-variant` inline in `theme.css`), confirmed by the `@tailwindcss/vite` devDependency and `@custom-variant dark` line in `theme.css`. Could not find a separate token-scale file (spacing/radius scale) beyond what's in `theme.css`.
- Could not run `npm ls` inside the worktree to confirm exact resolved versions vs. `package.json` ranges (no lockfile install verified in this pass) — versions above are taken directly from `package.json`.
- No `.impeccable*` file exists in the repo; the only design-context file is `apps/web/DESIGN.md`, read and reflected in font/token choices above.
