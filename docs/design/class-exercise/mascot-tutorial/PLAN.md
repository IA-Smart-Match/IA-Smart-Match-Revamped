# Mascot tour for the class exercise: plan

**Recommendation:** ship the tour with the **2D art (variant B)**, built in-house on the `motion` package the app already has. Add no new runtime dependency. Keep the 3D model (variant A) as a later option, loaded only when the tour opens.

**Status:** proposal for the owner. Nothing in `apps/` changed. This folder is untracked on `Frontend-Experimental`.
**Date:** 2026-09-28

To open the mockup:

```bash
python3 -m http.server -d docs/design/class-exercise/mascot-tutorial 8765
# then open http://127.0.0.1:8765/mockup/
```

- The tour opens on the first visit.
- To see it again, click **Tour** (bottom right) or **Review controls → Replay tour**.
- **Review controls** can:
  - switch between the 2D and 3D mascot;
  - turn each effect on or off;
  - simulate reduced motion;
  - switch between light and dark;
  - forget the "seen" state.
- Deep links: `?step=5&team=4`, `?screen=results&unlock=1`, `?screen=ab`, `?mascot=3d`, `?rm=1`, `?theme=dark`.

---

## 1. What is in this folder

| Path | What it is |
|---|---|
| `mockup/index.html` | A clickable mockup in one self-contained file. It has 4 exercise screens and a Mascot A/B screen, plus the tour layer. Its only CDN scripts come from jsdelivr, and only when 3D is on. |
| `mockup/mascot3d.js` | The 3D mascot, compiled and minified: 8.2 kB, 3.6 kB gzipped. |
| `mockup/assets/*.webp` | 5 poses and 5 faces cut from the owner's sheet. 86 kB in total. |
| `screenshots/before/` | The live and local app before this work (from the earlier run). |
| `screenshots/after/` | The mockup at 1440×900 and 390×844, plus `img2threejs-gate/`. |
| `img2threejs/` | The full 3D pipeline workspace: `.img2threejs/state.json`, the spec, evidence, `src/`, `viewer/` and `renders/`. |

## 2. 2D or 3D: the verdict

**Use the 2D art.** It *is* the character. The 3D model reads as a close cousin: a vinyl toy of the character, not the character.

| What we judged | A · 3D model (img2threejs) | B · 2D art |
|---|---|---|
| Reads as this character | Same family. Brown mane, green polo, dark hooves, tail and wave all read. The ears come out cat-like, the coat shifts toward salmon, and the face loses the ink line and the thick eyelids. | Exact. It is the art. |
| Gate evidence | Tier 1 silhouette overlap is **0.17** for the generated template and **0.54** after one code refinement (threshold 0.85, no alignment). Agent-vision score **0.50**. The 4-view turntable shows no degenerate view and no holes. | Not needed. |
| Poses | Any pose we write in code. Built so far: idle, wave, celebrate, point, think. | 5 drawn poses and 5 faces. A new pose needs new art. |
| Extra download | three.js: **171 kB** gzipped (675 kB minified), plus 3.6 kB of model code. | **70 kB** for the 5 poses and the launcher face. |
| Main thread, 4× slower CPU | **1,738 ms** of long tasks (5 tasks) when the tour opens in 3D. | **0 long tasks.** |
| Frame rate with no GPU (software WebGL) | 13–15 fps against a 30 fps cap. | No GPU work. |

Evidence (all under `screenshots/after/img2threejs-gate/`):

- `pass1-generated-template-compare.png`: the generated humanoid template beside the reference. It failed.
- `pass1-refined-cmp.png` and `pass1-refined-three-quarter.png`: the refined chibi beside the reference, plus an orbit view.
- `pass1-refined-motion-{idle,celebrate,point}.png`: the motions.
- On the mockup, see the **Mascot A/B** screen and `screenshots/after/10-mascot-ab-*.png`.

### img2threejs pipeline record

The pipeline was followed in order, with every step recorded in `.img2threejs/state.json`:

1. **Setup.** 13 of 13 steps are done or skipped with a reason.
   - Projection was skipped: the reference is ink-lined cel art, and projecting it would bake the line art onto a toy mesh.
   - The spec passed `--strict-quality` after two refinement rounds. Script: `img2threejs/refine_spec.py`. Logs: `evidence/strict-validation-run*.txt`.
2. **Pass 1 (blockout).**
   - Review 1 was `refine-code` at fidelity 0.15.
   - Review 2 is recorded as `request-input` at 0.50. The owner's 2D-or-3D choice decides whether the other 7 passes are worth building.
   - The correction budget used so far is 1 of 3 for this pass and 1 of 6 in total.
3. **Not done.**
   - Passes 2–8 were not built.
   - `part-coverage`, `action-ready`, `emission-target` and `plugin-gates` are still pending.
   - The blockout gate also asks for a `--map-stripped-render` capture, which was not produced.
   - The Tier 1 aspect and scale deltas compare a square 800×800 frame with a tight 262×305 crop, so they measure framing more than shape (see the skill's "Divine Eye caveat").

**Screenshot-gate note:** the chrome-devtools MCP was unreachable (`Target closed`). Every capture instead came from headless Chromium 151, driven over CDP by a 120-line script in the session scratchpad. Each PNG was saved inside the workspace and read back before any claim was made.

## 3. Library shortlist

The app already has React 18.3, Vite 6.4, Tailwind 4.1, Radix, `motion` 12.23, `canvas-confetti` 1.9.4, `lucide-react` and `recharts` (see `apps/web/legacy-frontend/package.json`).

The sizes below are the latest version, minified and gzipped, from the bundlephobia API. We checked them on 2026-09-28; the license comes from the npm registry.

| Library | Version | min+gz | License / cost | Fit for this tour | Source |
|---|---|---|---|---|---|
| **motion** (installed) | 13.4.4 (app has 12.23) | 46.6 kB full; already paid for | MIT | Mascot pop, step transitions, list re-order. **Keep.** | [bundlephobia](https://bundlephobia.com/package/motion) · [motion.dev: reduce bundle size](https://motion.dev/docs/react-reduce-bundle-size) |
| canvas-confetti (installed) | 1.9.4 | 4.2 kB | ISC | Could drive the star burst, but DESIGN.md §4 says it stays unused | [bundlephobia](https://bundlephobia.com/package/canvas-confetti) |
| driver.js | 1.8.0 | 7.2 kB | MIT | Ready-made spotlight and popover. Our layer needs about 150 lines, so it is optional. | [bundlephobia](https://bundlephobia.com/package/driver.js) · [driverjs.com](https://driverjs.com) |
| @reactour/tour | 3.8.0 | 7.0 kB | MIT | React tour provider. Also optional. | [bundlephobia](https://bundlephobia.com/package/@reactour/tour) |
| react-joyride | 3.2.0 | 25.0 kB | MIT | Heavier, with more styling to undo | [bundlephobia](https://bundlephobia.com/package/react-joyride) |
| shepherd.js | 15.3.0 | 14.9 kB | **AGPL-3.0** | Avoid: copyleft | [npm](https://registry.npmjs.org/shepherd.js/latest) |
| intro.js | 8.6.0 | 18.8 kB | **AGPL-3.0** / commercial | Avoid: copyleft | [npm](https://registry.npmjs.org/intro.js/latest) |
| gsap | 3.15.0 | 26.7 kB | GSAP "Standard no-charge" license (not OSI) | Would duplicate `motion` | [bundlephobia](https://bundlephobia.com/package/gsap) · [license](https://gsap.com/standard-license) |
| three | 0.170 build | **171 kB** (`three.module.min.js`, measured) | MIT | Only if 3D wins. Lazy chunk. | measured from [jsdelivr](https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js); npm latest is 0.186.1 |
| @react-three/fiber | 9.8.1 | 55.7 kB, plus three | MIT | Not needed for one small canvas | [bundlephobia](https://bundlephobia.com/package/@react-three/fiber) |
| @react-three/drei | 10.7.9 | **509 kB** | MIT | Avoid | [bundlephobia](https://bundlephobia.com/package/@react-three/drei) |
| @rive-app/react-canvas | 4.35.0 | 57.5 kB, plus `rive.wasm` **528 kB gz** (1.44 MB raw, measured for v2.31.2) | MIT runtime; Rive editor is a paid plan for exports | Best-in-class state-machine mascots, but needs an animator and is heavy on first load | [bundlephobia](https://bundlephobia.com/package/@rive-app/react-canvas) · [Rive web runtime](https://rive.app/docs/runtimes/web/web-js) |
| @lottiefiles/dotlottie-react | 0.19.16 | 33.1 kB, plus player wasm **496 kB gz** (1.24 MB raw, measured) | MIT | Needs After Effects or Lottie Creator authoring | [bundlephobia](https://bundlephobia.com/package/@lottiefiles/dotlottie-react) |
| lottie-web | 5.13.0 | 75.0 kB | MIT | Older, JSON player | [bundlephobia](https://bundlephobia.com/package/lottie-web) |
| Magic UI | copy-paste | 0 (you own the code) | MIT | Shimmer and border-beam snippets, but they are Tailwind + `motion` recipes we can write to our own tokens | [magicui.design](https://magicui.design) |
| Aceternity UI | copy-paste | 0 | Free tier plus a paid "Pro" | Showy landing-page effects that clash with DESIGN.md | [ui.aceternity.com](https://ui.aceternity.com) |
| shadcn/ui | copy-paste (CLI) | 0 | MIT | The app already has the same Radix primitives | [ui.shadcn.com](https://ui.shadcn.com) |

**Minimal set: add nothing.**

1. **`motion`** (installed): mascot pose swaps, the card entrance, and the list FLIP re-order.
2. **Radix Popover or Dialog** (installed): focus handling for the tour card.
3. **Our own `<Spotlight>`** (about 150 lines): the same approach as the mockup, one fixed element with a large box-shadow and 4 click blockers.

Take up driver.js (7.2 kB) only if the in-house spotlight turns up edge cases we don't want to own. `three` stays out unless the owner picks 3D.

## 4. Performance and resources

### Measured

- **Method.** Headless Chromium 151 over CDP, with the cache disabled on every run. Timings come from `Performance.getMetrics` and a `longtask` PerformanceObserver.
- **"4× CPU"** is CDP CPU throttling, used as a stand-in for a weak classroom PC.
- **WebGL** ran on SwiftShader, which is software, so the 3D numbers are a worst case with no GPU.
- **Not run.** Lighthouse: the chrome-devtools MCP was down and the Lighthouse CLI is not installed, and we did not install it. A trace file: we used the `getMetrics` totals instead.

| Scenario | Requests | Transfer | FCP | Main-thread task time | Long tasks | Script time |
|---|---|---|---|---|---|---|
| Mockup, first visit, 2D tour opens | 8 | 323 kB* | 396 ms | 368 ms | 0 | 14 ms |
| Same, 4× CPU | 7 | 322 kB* | 392 ms | 638 ms | 0 | 15 ms |
| Mockup, tour in **3D**, 4× CPU | 9 | 498 kB* | 2,288 ms | 2,352 ms | 5 (1,738 ms) | 273 ms |
| Mascot A/B screen (three.js plus 4 review PNGs) | 13 | 830 kB* | 136 ms | 645 ms | 1 (371 ms) | 104 ms |
| Same, 4× CPU; 3D frame rate | 13 | 829 kB* | — | 3,005 ms | 2 (454 ms) | 195 ms; **13.2 fps** (cap 30) |
| **Live app today**, `/exercise` (Vite dev server via tunnel) | **90** | **1,412 kB** (1,275 kB of it JS) | 2,276 ms | 420 ms | — | 224 ms |
| Live, 4× CPU | 90 | 1,397 kB | 1,688 ms | 649 ms | — | 189 ms |

\* The mockup figures are inflated by what only the mockup loads:

- 227 kB of Google Fonts stand-ins. Production self-hosts the licensed faces, and the live app already sends 93 kB of fonts.
- 77 kB of uncompressed HTML, because `http.server` does not gzip. It is 21 kB gzipped.
- 348 kB of review PNGs on the A/B screen.

**The tour's own cost is:**

- **2D:** the tour code plus about 70 kB of webp. The 5 poses are fetched one per step, so the first step needs only the 13 kB pose 1 and the 3.6 kB launcher face.
- **3D:** add 171 kB of three.js, 3.6 kB of model code, and about 1.7 s of main-thread shader and scene work on a slow CPU.

### What this means for the classroom (e2-medium VM, Cloudflare tunnel, about 30 laptops at once)

- **Rendering is client-side.** The VM only serves bytes and does dev-server transforms, so the mascot adds nothing to VM CPU after the first transform.
- **The bigger win is not the mascot.** Today's live entry makes **90 requests and moves 1.4 MB**, because the Vite dev server sends every module unbundled.
  - 30 laptops means about 2,700 requests and 42 MB, all transformed on a 2-vCPU box on a cold start.
  - `vite build` plus static serving (`vite preview`, or nginx/Caddy behind the same tunnel) turns that into a handful of hashed, cache-forever files that Cloudflare can cache at the edge. Source: [Vite, "Why Vite"](https://vite.dev/guide/why.html), on unbundled ESM costing extra round trips in production.
  - A local `vite build` of `legacy-frontend` is summarised in 4.1 below.
- **Under-5 s target on classroom Chrome.**
  - The 2D tour adds under 20 kB to the first screen and no long tasks, so it cannot be what pushes load past 5 s.
  - 3D adds about 1.7 s of main-thread work on a slow CPU with no GPU, so it needs the rules below.

### Rules for the build (both variants)

1. **Lazy-load.**
   - The tour chunk (`import()`) loads only when the first-visit check says to show it, or on **Tour**.
   - three.js and the model load only when the tour opens **and** the owner chose 3D.
   - Nothing mascot-related sits in the entry bundle.
2. **Fallbacks.** 3D falls back to the 2D pose when:
   - `WebGLRenderingContext` is missing, or context creation fails;
   - `navigator.hardwareConcurrency <= 2`;
   - the first frame takes more than 50 ms;
   - the user prefers reduced motion.

   The slot is never left blank. The mockup does this (`createMascot` → `create2D`).
3. **Asset weights.**
   - Ship the poses at 2× the display size (about 280×320) as webp at around 15 kB each, and the faces at about 4 kB.
   - Preload only pose 1.
   - The current crops are 262–286 px wide and slightly soft on HiDPI. Ask for 2× exports.
4. **FPS cap and pausing.**
   - Render at 30 fps (`mountMascot({ fps: 30 })`).
   - Use `powerPreference: 'low-power'`, with pixel ratio capped at 1.5.
   - Stop on `visibilitychange` when the tab is hidden, and dispose the GL context when the tour closes.
   - Reference: [Page Lifecycle API](https://developer.chrome.com/docs/web-platform/page-lifecycle-api).
5. **Reduced motion.**
   - Honour `prefers-reduced-motion` ([MDN](https://developer.mozilla.org/docs/Web/CSS/@media/prefers-reduced-motion)).
   - 2D: pose swaps become a 150 ms fade, with no bob, wave or hop.
   - 3D: renders one still frame and runs no loop.
   - Spotlight: jumps, no slide.
   - Star burst: stars fade in place.
   - Page change: instant.
   - Shimmer: a static gold wash.
6. **CSS motion only on `transform` and `opacity`.** The one exception is the spotlight box, which animates `left/top/width/height` on a single fixed element.

### 4.1 Production build

See "Vite build check" at the end of this file.

## 5. Tutorial architecture

```
src/app/pages/exercise/tour/
  steps.ts          // steps as data: { id, route, anchor, pose, title, text, placement, next? }
  TourProvider.tsx  // state machine: closed → open(step) → closed; persists seen-state
  Spotlight.tsx     // fixed hole + 4 blockers + ring; re-measures on scroll/resize via rAF
  TourCard.tsx      // Radix-based card: counter, dots, Back/Next, Skip, "Don't show again"
  Mascot2D.tsx      // pose <img> + motion variants; the 3D mascot is a lazy sibling
  useFirstVisit.ts  // reads/writes localStorage, per-team optional
```

- **Steps as data.** The 7 mockup steps map onto the real routes:

  | Step | Route | Anchor |
  |---|---|---|
  | 1 | `/exercise` | page title |
  | 2 | `/exercise` | team tiles |
  | 3 | `/exercise` | open button |
  | 4 | `/exercise/events` | round 1 card |
  | 5 | `/exercise/events/:eventKey` | weights card |
  | 6 | `/exercise/events/:eventKey` | the list |
  | 7 | `/exercise/events/:eventKey` | "Run results for this event" |

  - The copy uses the exercise's own words (ADR-0025 D8: no score, percentage or confidence) and follows DESIGN.md §9: plain words and no exclamation marks.
  - The title strings are new wording for Ann to see.
- **Anchors.**
  - Mark each target with `data-tour="teams"` and so on, never a CSS class. Tests can then assert that the anchors exist.
  - If an anchor is missing, the step is skipped rather than pointing at nothing.
  - A step on another route navigates first, then waits for its anchor for up to 2 s.
- **Seen-state.**
  - Key: `localStorage['smartmatch.exercise.tour.v1']`. It stores `{ done, reason: 'finished'|'skipped', dontShow, team, at }`.
  - Bumping `v1` re-shows the tour after a big UI change.
  - **Per-team option:** add the suffix `:team-4`, so a new team on a shared lab PC still sees it.
  - Every read and write sits in a try/catch; private mode just means the tour shows again.
- **First-visit trigger.**
  - On `/exercise`, 700 ms after the first paint, if there is no seen record and no `?tour=off`.
  - It never opens on the instructor route, or over a loading or error state.
- **Replay.** The **Tour** pill (bottom right, mascot face) reopens the tour at step 1. So does "How this works" in the exercise header, if we add one.
- **Skip.**
  - **Skip tutorial** or `Esc` closes the tour.
  - It shows a 5 s toast, "Tour closed. Find me under the Tour button…", with the chill pose.
  - Focus returns to the Tour button.
- **Keyboard and screen readers.**
  - The card is `role="dialog"` with `aria-modal="false"`, so the spotlit control stays reachable.
  - Focus moves to the step title on each step.
  - An `aria-live="polite"` region reads "Step 3 of 7. Title. Text."
  - `←`/`→` move between steps. `Esc` skips.
  - Targets are at least 44 px. The focus ring is 3 px in `--ce-primary`.
  - The mascot is decorative (`aria-hidden`).
- **Test safety.**
  - The provider renders nothing when `import.meta.env.MODE === 'test'` unless a test opts in with `<TourProvider forceOpen>`, so none of the 60-plus existing exercise tests change.
  - `desk/testMatchMedia.tsx` already covers the reduced-motion paths.
  - Add 4 tests:
    - (a) steps render in order;
    - (b) Skip writes seen-state;
    - (c) a missing anchor is skipped;
    - (d) reduced motion renders no animation.
  - Add a single Vitest check that every `anchor` in `steps.ts` exists on its page.
- **Extending to the CBA platform later.**
  - `steps.ts` becomes a registry keyed by product (`exercise`, `cba-student`, `cba-staff`).
  - The same provider and mascot take new step lists.
  - The seen key is namespaced per product (`smartmatch.cba.tour.v1`).
  - The CBA screens need their own `data-tour` anchors, and their copy goes through the same plain-words review.

## 6. Visual effects (in the mockup; each can be toggled and has a reduced-motion path)

| # | Effect | Real moment | Reduced motion | DESIGN.md fit |
|---|---|---|---|---|
| 1 | Paper-tint drift and pointer parallax behind the opening title | First screen of the exercise | Static, no parallax | **Conflict:** §10 says "no gradient background". It is kept to CPP tints at low contrast. Owner call. |
| 2 | Page-change crossfade and rise (View Transitions API) | Every route change (`ce-view` in §5) | Instant | Fits §5 `ce-view` |
| 3 | "On both lists" shimmer | Opening a comparison of two saved settings | Static gold wash | Fits `ce-overlap-pulse` in spirit; the sweep replaces the pulse |
| 4 | Star burst plus a celebrating mascot toast | Instructor opens results (`ce-unlock`) | Stars fade in place | **Conflict:** §4 and §10 rule out confetti ("a results run is evidence to discuss, not a win"). Stars fire on the *unlock*, not on the team's outcome, but this is an owner call. |
| 5 | Spotlight glide and gold ring pulse | The tour itself | Jumps, no pulse | New; uses gold as the one highlight on the screen |

Other DESIGN.md rules the mascot touches:

- §4 says "no people illustrations" and "spot art only in empty, locked and first-visit states". A mascot is a character, so this needs the owner's explicit OK.
- In the mockup the mascot appears only in the first-visit tour, the Tour pill, and the results-open toast.

## 7. Phased rollout

Hours are for one developer, with review included. Each phase ends in its own PR.

| Phase | Track | Hours |
|---|---|---|
| 0 | Owner picks: name, 2D/3D, effects 1 and 4, preview audience (open questions below) | 0.5 (owner) |
| 1 | `vite build` plus static serving for the exercise on the VM (compose service, tunnel target, cache headers). This is independent of the mascot and the largest load-time win. | 4–6 |
| 2 | Tour core: `steps.ts`, `TourProvider`, `Spotlight`, `TourCard`, seen-state, the Tour pill, and test-mode guard | 10–12 |
| 3 | 2D mascot: 2× pose exports, `Mascot2D` with `motion` variants, reduced-motion paths | 4–5 |
| 4 | Tests: 4 behaviour tests plus the anchor-existence check; axe pass on the card | 4 |
| 5 | Effects the owner keeps (2 and 3 are the cheapest; 1 and 4 only if approved) | 3–6 |
| 6 | Classroom check: 1 lab PC in Chrome, cold cache, and a 30-tab load against the VM | 2 |
| 7 (optional) | 3D variant: finish img2threejs passes 2–8, lazy chunk, WebGL fallback, 30 fps cap | 16–24 |
| 8 (later) | CBA extension: registry, CBA anchors and copy | 8–12 per surface |

Phases 1–6 total **27.5–35.5 hours**. Adding 3D makes it **43.5–59.5 hours**.

## 8. Open questions for the owner

1. **Name.** The mockup says "Bree", which is a placeholder. Cal Poly Pomona's mascot is Billy the Bronco, so do you want a Bronco-linked name, or a separate identity?
2. **2D or 3D?** The recommendation is 2D now. Is 3D worth 16–24 more hours and 171 kB for lab PCs?
3. **Preview.** Should Dr. Wang and Dr. Lin (and Ann) preview the mockup before we build, and do they approve the step wording (§5 of this plan)?
4. **DESIGN.md exceptions.** Do you approve:
   - the mascot as a character illustration (§4);
   - the entry background tint (§10);
   - the star burst on unlock (§4 and §10: no confetti)?
5. **Seen-state scope.** Per browser, or per team on shared lab PCs?
6. **Art.** Can the artist supply 2× exports and, if we keep 2D, a "pointing" pose? The current "explore" pose holds a magnifier, which works but does not point at the target.

---

## Vite build check (local, 2026-09-28)

**Command:** `vite build --outDir <scratchpad>`, run in `apps/web/legacy-frontend`. It took 1 min 53 s on `/mnt/c`, and nothing in `apps/` changed.

**Output:** 77 JS chunks, 1,579 kB minified in total, 458 kB gzipped. CSS is 27.6 kB gzipped.

`/exercise` served statically from that build (SPA fallback, no compression, no API behind it):

| | Requests | Transfer, uncompressed | Est. gzipped | FCP | Main-thread tasks |
|---|---|---|---|---|---|
| Built, 1× CPU | **16** | 1,234 kB (954 kB JS, 167 kB CSS) | about 330 kB | 188 ms | 224 ms |
| Built, 4× CPU | 16 | 1,234 kB | about 330 kB | 244 ms | 327 ms |
| Live dev server (from section 4) | 90 | 1,412 kB as sent | — | 2,276 ms | 420 ms |

The gzipped estimate uses the build's measured ratio of 0.29.

Findings:

1. The build cuts the entry from **90 to 16 requests** and takes dev-server transforms off the VM completely.
2. The entry also pulls `vendor-charts`: recharts, 104 kB gzipped. `/exercise` has no chart, so moving recharts behind the results route is a second, cheap win. It is worth doing before any mascot work.
3. For about 30 laptops, a cold start is 30 × about 330 kB, or about 10 MB, served as static cacheable files. Cloudflare can cache that at the edge, so the e2-medium mostly stops being a factor.

