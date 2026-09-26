# Generated mock-ups — contact sheet

**Round:** 2026-09-26, the owner's "generate image mock-ups first" request.
**Count:** 24 images (20 at 1280, 4 at 390), 1.9 MB of WebP, plus one
private Claude Design canvas with 4 interactive artboards.

These are mock-ups, not the build. Where an image and
[`DESIGN.md`](DESIGN.md) disagree, `DESIGN.md` wins.

## 1. How they were made

| Tool | Status | Output |
|---|---|---|
| Google Stitch | **Not run.** No Stitch MCP server is configured in this environment (no `stitch` entry in the Claude Code MCP config, and the `/stitch` command's `google-stitch-frontend-mcp` skill is not installed), so `stitch_healthcheck` could not run | 0 images |
| Higgsfield, GPT Image 2 (the agreed fallback) | **Not run.** `higgsfield account status` returns "Session expired"; `hf auth login` is interactive and must be run by a person | 0 images |
| Claude Design (Artifact "Design" canvas) | **Done.** Private canvas, owner-only: https://claude.ai/artifact/KQM1s4X8PDQzUPvhAAq3Uh | 4 interactive artboards: results reveal 1280 (replayable `ce-seat-fill`), results reveal 390, weight sliders with number boxes (live commit and "Rebuilding the list…"), opening and team entry |
| Claude-authored HTML, rendered in headless Chromium (`claude-html`) | **Done.** Each Claude Design prompt was built as static HTML using the shared preamble's tokens and the shared fictional data, then captured as WebP (quality 82) | 24 images in [`assets/generated/claude-html/`](assets/generated/claude-html/) |

Why `claude-html` and not an image model: with Stitch and Higgsfield both
unavailable, rendering real HTML was the only way to get images this round.
It also avoids the usual image-model flaws: every word is real UI text, and
there are no invented numbers and no people. The cost is that these images
are Claude's reading of the prompts, not an independent tool's.

Fonts are the mock-up stand-ins (Archivo, Source Serif 4, Figtree) loaded
from Google Fonts; production uses Transducer CPP, Proxima Sera and Usual.
The CPP logo is a labelled placeholder, never drawn.

## 2. Review against the brief's rejection rules

| Rule | Result |
|---|---|
| Wrong brand colours | 0 rejected. Only `--ce-*` values appear; gold is used only as a fill or highlight |
| Fake UI text | 0 rejected. Every string is the prompt's own copy or server sentence |
| Real-looking student photos | 0. No photos or people anywhere |
| Percentages per person | 0. The only per-person number is the rank |

Regenerated once: `weight-slider-1280` (the value bubble overlapped a
label), `empty-and-loading-states-1280` (spot SVGs collapsed to 40px), and
`04-ranked-list-and-sliders-390` (the sticky weights bar wrapped). All three
are fixed in the kept versions.

Flaws kept and noted (none breaks a rule):

1. **Results charts** (`08…-1280`, `08…-390`, `10…-1280`): on one shared
   axis the team's bars (30 / 6 / 4) are slivers beside "emailed everyone"
   (300). This is honest, and the direct labels carry the numbers. It is
   still a design question for Ann: small multiples, or a second axis per
   panel?
2. **Instructor team rows** (`11-instructor-1280`): the summary text wraps
   to three lines beside two actions. Move the actions under the text at
   ≤1280.
3. **Profile card** (`06-profile-card-mockup-1280`): the inert buttons'
   text is low contrast. They are disabled, which WCAG exempts, but a
   projector may wash them out.
4. **Component frames** use an `h1` as the frame's title so each image
   stands alone. In the product the component sits under the page's own `h1`.

## 3. Gallery

Fidelity scale: **High** = follows DESIGN.md tokens, type, layout and
states as written; **Medium** = follows the system with a noted gap.

### Components

| Image | Prompt | Tool | Fidelity |
|---|---|---|---|
| ![Weight slider](assets/generated/claude-html/weight-slider-1280.webp) | [`prompts/components/weight-slider.md`](prompts/components/weight-slider.md) | claude-html | High: slider with number box, drag bubble, focus ring, invalid entry, rebuilding line, 390 sticky bar |
| ![Ranked rows](assets/generated/claude-html/ranked-row-1280.webp) | [`prompts/components/ranked-row.md`](prompts/components/ranked-row.md) | claude-html | High: reason under name, icon+word markers, joined and on-both washes |
| ![Saved settings](assets/generated/claude-html/saved-setting-card-1280.webp) | [`prompts/components/saved-setting-card.md`](prompts/components/saved-setting-card.md) | claude-html | High: weights as numbers only, comparing outline, dashed free slot |
| ![Compare](assets/generated/claude-html/compare-view-1280.webp) | [`prompts/components/compare-view.md`](prompts/components/compare-view.md) | claude-html | High: summary sentence, 12 overlap chips, "Showing 10 of 30" |
| ![Results reveal](assets/generated/claude-html/results-reveal-1280.webp) | [`prompts/components/results-reveal.md`](prompts/components/results-reveal.md) | claude-html | High: 8 / 6 / 46 seats, three-line headline, ruled figures band (final state; motion is in the canvas) |
| ![Asking choices](assets/generated/claude-html/asking-choice-cards-1280.webp) | [`prompts/components/asking-choice-cards.md`](prompts/components/asking-choice-cards.md) | claude-html | High: the ruled 5-second inline confirm "Confirm: A small reward?"; no pop-up |
| ![Unlock panel](assets/generated/claude-html/instructor-unlock-panel-1280.webp) | [`prompts/components/instructor-unlock-panel.md`](prompts/components/instructor-unlock-panel.md) | claude-html | High: lock chips with icon and words, inline confirm |
| ![States](assets/generated/claude-html/empty-and-loading-states-1280.webp) | [`prompts/components/empty-and-loading-states.md`](prompts/components/empty-and-loading-states.md) | claude-html | High: eight states, server sentences verbatim, only the transport error red |

### Pages

| Image | Prompt | Tool | Fidelity |
|---|---|---|---|
| ![Opening](assets/generated/claude-html/01-opening-1280.webp) | [`prompts/pages/01-opening.md`](prompts/pages/01-opening.md) | claude-html | High: "Who should we invite?", license line, lecture-hall art; team zone below |
| ![Team entry](assets/generated/claude-html/02-team-entry-1280.webp) | [`prompts/pages/02-team-entry.md`](prompts/pages/02-team-entry.md) | claude-html | High: six place-card tiles, team 4 selected with gold notch, returning-browser line |
| ![Event picker](assets/generated/claude-html/03-event-picker-1280.webp) | [`prompts/pages/03-event-picker.md`](prompts/pages/03-event-picker.md) | claude-html | High: round seals inside cards (no eyebrow), past events not choosable |
| ![Matching 1280](assets/generated/claude-html/04-ranked-list-and-sliders-1280.webp) | [`prompts/pages/04-ranked-list-and-sliders.md`](prompts/pages/04-ranked-list-and-sliders.md) | claude-html | High: sticky sliders beside the list, coverage notice, 12 of 30 rows |
| ![Matching 390](assets/generated/claude-html/04-ranked-list-and-sliders-390.webp) | [`prompts/pages/04-ranked-list-and-sliders.md`](prompts/pages/04-ranked-list-and-sliders.md) | claude-html | High: compact weights bar, rows as stacked cards |
| ![Save and compare 1280](assets/generated/claude-html/05-save-and-compare-1280.webp) | [`prompts/pages/05-save-and-compare.md`](prompts/pages/05-save-and-compare.md) | claude-html | High: three settings, two comparing, one primary button |
| ![Compare 390](assets/generated/claude-html/05-save-and-compare-390.webp) | [`prompts/pages/05-save-and-compare.md`](prompts/pages/05-save-and-compare.md) | claude-html | High: segmented A / B control, one list at a time |
| ![Profile card](assets/generated/claude-html/06-profile-card-mockup-1280.webp) | [`prompts/pages/06-profile-card-mockup.md`](prompts/pages/06-profile-card-mockup.md) | claude-html | Medium: follows the spec; inert-button contrast is low (flaw 3) |
| ![Results locked](assets/generated/claude-html/08-final-setting-and-results-locked-1280.webp) | [`prompts/pages/08-final-setting-and-results.md`](prompts/pages/08-final-setting-and-results.md) | claude-html | High: final-setting radio cards, calm locked state, disabled run button with reason |
| ![Results 1280](assets/generated/claude-html/08-final-setting-and-results-1280.webp) | [`prompts/pages/08-final-setting-and-results.md`](prompts/pages/08-final-setting-and-results.md) | claude-html | Medium: seats, headline and people as specified; chart slivers (flaw 1) |
| ![Results 390](assets/generated/claude-html/08-final-setting-and-results-390.webp) | [`prompts/pages/08-final-setting-and-results.md`](prompts/pages/08-final-setting-and-results.md) | claude-html | Medium: phone room fits 10 per row; horizontal bars (flaw 1) |
| ![Asking 1280](assets/generated/claude-html/09-asking-for-more-1280.webp) | [`prompts/pages/09-asking-for-more.md`](prompts/pages/09-asking-for-more.md) | claude-html | High: chosen card with gold seal, others dimmed, refresh counts band |
| ![Asking 390](assets/generated/claude-html/09-asking-for-more-390.webp) | [`prompts/pages/09-asking-for-more.md`](prompts/pages/09-asking-for-more.md) | claude-html | High: inline confirm mid-countdown on a phone |
| ![Round two](assets/generated/claude-html/10-round-two-comparison-1280.webp) | [`prompts/pages/10-round-two-comparison.md`](prompts/pages/10-round-two-comparison.md) | claude-html | Medium: 8 / 11 / 41 room, round-one line, three-group chart (flaw 1) |
| ![Instructor](assets/generated/claude-html/11-instructor-1280.webp) | [`prompts/pages/11-instructor.md`](prompts/pages/11-instructor.md) | claude-html | Medium: unlock first, data files to the side, inline reset confirm; rows cramped (flaw 2) |
| ![Instructor sign-in](assets/generated/claude-html/11-instructor-passcode-1280.webp) | [`prompts/pages/11-instructor.md`](prompts/pages/11-instructor.md) | claude-html | High: passcode card with show toggle and "not your university login" helper |

Not generated: [`prompts/pages/07-points-counter.md`](prompts/pages/07-points-counter.md),
deferred by the 2026-09-26 ruling.

## 4. Re-running

- **Stitch:** configure the Stitch MCP server the `/stitch` command
  expects (tools `stitch_healthcheck`, `stitch_generate_frontend`), then
  run the prompts in [`prompts/README.md`](prompts/README.md) order.
  Save to `assets/generated/stitch/<prompt-name>-<width>.png`.
- **Higgsfield:** a person runs `hf auth login`, then GPT Image 2 with
  the Stitch preamble plus each prompt. Save to
  `assets/generated/higgsfield/<prompt-name>-<width>.png`.
- Add each new image to this sheet with its tool and a fidelity line.
