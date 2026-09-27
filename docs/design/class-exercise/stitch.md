# Stitch mock-ups: "The invitation desk"

**Status:** reference only. The owner chose to build. The build is the PR stack
#245 and #247–#251, plus #252 for the negative-weight refusal. The images are
kept for a later rebuild or reference; nothing here is wired into `apps/web`.
Each gallery row's **Built as** note says where the build differs from the image.
**Section citations** (§) point at [`DESIGN.md`](DESIGN.md) as amended by that stack.
**Round:** 2026-09-26. 24 images (20 desktop, 4 mobile), all WebP and each 19–227 KB,
plus 24 HTML/Tailwind exports kept for reference in [`assets/stitch/code/`](assets/stitch/code).
**Rules:** [`DESIGN.md`](DESIGN.md) wins over any image, and over the archived prompts.

## 1. How they were made

| Item | Value |
|---|---|
| Tool | Google Stitch remote MCP server (`https://stitch.googleapis.com/mcp`), called over JSON-RPC. The key lives in the user-scope MCP config, never in this repo |
| Model | `GEMINI_3_8_FLASH` (Stitch "Gemini 3.8 Flash", `PRO_AGENT`) for every screen |
| Device types | `DESKTOP` (the archived "1280") and `MOBILE` (the archived "390") |
| Stitch project | Private, owner-only: `projects/4736179568401651070` |
| Design system | Built once from live `DESIGN.md` with `upload_design_md` and `create_design_system_from_design_md` (asset `a4870f122d954bdb8346183743ba5466`). Every screen used it |
| Prompt per screen | The Stitch style preamble and the shared fictional data from the [archived prompt README](../../archive/design/class-exercise/prompts/README.md), then the page's archived Stitch prompt, then the `DESIGN.md` overrides in section 4, then fixed guard rules (no nav bar, photos or people; no invented copy; exact ribbon text; no per-person numbers; data wording) |
| Post-processing | Screenshot scaled to 1280 px wide (desktop) or 780 px, which is 390 at 2x (mobile), saved as WebP q82. HTML saved as-is after a scan for keys and trackers |

**Did the design-system ingest help?** Partly.

1. **What it did well:** every screen used the eggwhite page, white cards, CPP Green actions, the gold-wash ribbon, the Bay-brown control outlines and the 4 px spacing scale. No screen needed a colour fix.
2. **What it got wrong:** it turned the tokens into a Material palette (`primary #00371f`, `background #f8faf5`), so the prompts still had to state each hex.
3. **Fonts:** it recorded the licensed families (Transducer CPP, Proxima Sera, Usual), which a browser cannot load. When a screen did not also load the stand-ins, text fell back to system fonts. See flaws F1 and F2.

**HTML exports:** 0 API keys and 0 trackers (re-checked 2026-09-27). The only remote hosts are `cdn.tailwindcss.com` (23 of 24 files; `09-…-mobile` uses plain CSS), `unpkg.com/lucide@latest` (14 files, unpinned) and Google Fonts (24 files). Inline scripts only set the Tailwind config, call `lucide.createIcons()`, or toggle local demo state (the passcode eye and the unlock button). None loads remote images. They are reference only; do not serve them.

## 2. Gallery

Fidelity scale, as in the archived sheet: **High** means the screen follows `DESIGN.md` tokens, type, layout and the prompt's states. **Medium** means it follows the system with a gap, which the note names.
"Archived" is the Claude-authored HTML render of the same prompt, in
[`../../archive/design/class-exercise/assets/generated/claude-html/`](../../archive/design/class-exercise/assets/generated/claude-html).
Every row's tool is **Stitch · `GEMINI_3_8_FLASH`**.

### 2.1 Priority pages (desktop and mobile)

| Image | Device | Prompt | Fidelity | Compared with the archived render | Built as |
|---|---|---|---|---|---|
| ![Results](assets/stitch/08-final-setting-and-results-desktop.webp) | DESKTOP | [`pages/08-final-setting-and-results.md`](../../archive/design/class-exercise/prompts/pages/08-final-setting-and-results.md) (screen B) | High. Seats show 8 / 6 / 46, the three-line serif headline has green numerals, and the ruled figures band is present. Regenerated once (R1) | [`08-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/08-final-setting-and-results-1280.webp): same structure. Stitch draws larger seats and a two-row legend, and adds each panel's counts as a caption. It keeps the same shared-axis "sliver" bars (archived flaw 1). It drops the CPP logo placeholder and adds the license line as a footer | Added = `team.attended_count` (§6.15); every invited name shows, no "and 22 more"; "Ask them now" stays, not "Go to asking for more"; no "60 seats" caption or license footer; the chart keeps one shared axis (§6.16) |
| ![Results 390](assets/stitch/08-final-setting-and-results-mobile.webp) | MOBILE | same | Medium. It has the room, the horizontal bars and the chips. Flaws F1 and F3 remain (R2) | [`08-…-390`](../../archive/design/class-exercise/assets/generated/claude-html/08-final-setting-and-results-390.webp): the Stitch horizontal bars read better than the archived slivers. The archived version keeps the serif headline, which Stitch lost | The chart stays vertical in its own scroll box; 390 horizontal bars are deferred (§7.8, §6.16). The 3 invented sub-lines (F3) are not built |
| ![Results locked](assets/stitch/08-final-setting-and-results-locked-desktop.webp) | DESKTOP | same (screen A) | High. The radio cards show weights only, the locked panel is calm, and the disabled run button carries its reason underneath. Regenerated once (R3) | [`08-…-locked-1280`](../../archive/design/class-exercise/assets/generated/claude-html/08-final-setting-and-results-locked-1280.webp): near-identical layout. Stitch repeats the helper line under the button, which matches `aria-describedby` intent | No "Check again": it re-sent the one-time run, so the panel has no action and Run stays the only retry (§6.14). The panel sits above the picker (§7.8) |
| ![Matching](assets/stitch/04-ranked-list-and-sliders-desktop.webp) | DESKTOP | [`pages/04-ranked-list-and-sliders.md`](../../archive/design/class-exercise/prompts/pages/04-ranked-list-and-sliders.md) | High. Sliders sit beside the list with number boxes, and the markers use icon plus words. Side margins are 24 px, not 64 px | [`04-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/04-ranked-list-and-sliders-1280.webp): the Stitch name column is wider, so reason lines wrap to 3–6 lines against the archived 6–12. Stitch fades row 10 as the prompt asked. The archived version shows 12 rows | Weights sit beside the list only at 1280 and up, stacked below (§7.4); all 30 rows, no fade; no "Team 4" aside; a weights refusal shows once, under its slider (§6.6) |
| ![Matching 390](assets/stitch/04-ranked-list-and-sliders-mobile.webp) | MOBILE | same | High. It has the compact "Weights 0.40 · 0.25 · 0.25 · 0.10 · Edit weights" bar, stacked rows, and the next-step button | [`04-…-390`](../../archive/design/class-exercise/assets/generated/claude-html/04-ranked-list-and-sliders-390.webp): same content order. Stitch put the sticky bar above the title rather than pinned. The screen was cropped from a desktop-width canvas (F4) | The compact bar pins once the weights card scrolls out; "Edit weights" scrolls back and focuses the first slider (§7.4) |
| ![Save and compare](assets/stitch/05-save-and-compare-desktop.webp) | DESKTOP | [`pages/05-save-and-compare.md`](../../archive/design/class-exercise/prompts/pages/05-save-and-compare.md) | High. Three cards, 2 marked "Comparing", Delete in quiet green (the `DESIGN.md` override), and gold overlap rows. It adds small labels "List A" / "List B" and an input placeholder (F5) | [`05-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/05-save-and-compare-1280.webp): equivalent. Stitch adds each setting's weights under the list title, which helps comparison | Compare is two stacked full-width tables, each in its own scroll box, not side by side (§6.12, §7.5); no "List A" / "List B"; Delete asks first (§6.11, §11.1) |
| ![Compare 390](assets/stitch/05-save-and-compare-mobile.webp) | MOBILE | same | Medium. It has the segmented "Major first \| Interests first" control and the summary above it. The overlap rows carry a left gold stripe, which §6.20 forbids | [`05-…-390`](../../archive/design/class-exercise/assets/generated/claude-html/05-save-and-compare-390.webp): the archived render shows only the compare zone. Stitch shows the whole lower zone (save form, cards, compare) | Below 768 compare is tabs plus cards, 10 rows then "Show all 30" (§6.12); overlap rows get wash plus chip, no stripe (§6.20) |
| ![Asking](assets/stitch/09-asking-for-more-desktop.webp) | DESKTOP | [`pages/09-asking-for-more.md`](../../archive/design/class-exercise/prompts/pages/09-asking-for-more.md) | High. The chosen card has the gold seal and the others fade. It has the pictogram beside the lead and the ruled 9 / 0 / 34 band | [`09-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/09-asking-for-more-1280.webp): same. Stitch adds the half-filled card pictogram that the archived render left out | The third figure reads "Picked up the first event's topics" and counts people (§6.19); the art sits beside the "How will your team ask?" `h2`, not the lead (§7.9) |
| ![Asking 390](assets/stitch/09-asking-for-more-mobile.webp) | MOBILE | same, plus the §6.18 inline confirm | High. It shows the "Confirm: A small reward?" button, a half-spent countdown underline, and "Press again within 5 seconds." No pop-up | [`09-…-390`](../../archive/design/class-exercise/assets/generated/claude-html/09-asking-for-more-390.webp): same moment, rendered as tidily. Cropped from a desktop-width canvas (F4) | The helper is the §11.1 hint "Press again to confirm A small reward. Your team picks once.", not "within 5 seconds"; 300 ms double-click guard, key repeat ignored, blur does not disarm (§6.18) |

### 2.2 Remaining pages (desktop)

| Image | Device | Prompt | Fidelity | Compared with the archived render | Built as |
|---|---|---|---|---|---|
| ![Opening](assets/stitch/01-opening-desktop.webp) | DESKTOP | [`pages/01-opening.md`](../../archive/design/class-exercise/prompts/pages/01-opening.md) | High. It has "Who should we invite?", the license line in a sunk card, and the lecture-hall pictogram. "Which team are you?" fell back to sans (F2) | [`01-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/01-opening-1280.webp): same. The Stitch pictogram is simpler | The real CPP logo, on an eggwhite plate in dark mode (§6.1; the plate is in `exercise.css`, not yet in DESIGN.md); the art shows at 1024 and up only (§7.1) |
| ![Team entry](assets/stitch/02-team-entry-desktop.webp) | DESKTOP | [`pages/02-team-entry.md`](../../archive/design/class-exercise/prompts/pages/02-team-entry.md) | High. Six place-card tiles, team 4 in green with the gold notch, and the badge line | [`02-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/02-team-entry-1280.webp): equivalent | The license card stays in the top zone, not the page foot (§7.1); the button is right-aligned under the tiles (§7.2); the "Team number" legend is screen-reader only |
| ![Event picker](assets/stitch/03-event-picker-desktop.webp) | DESKTOP | [`pages/03-event-picker.md`](../../archive/design/class-exercise/prompts/pages/03-event-picker.md) | Medium. Layout, seals and the past-events list are right, but the title, lead and meta lines render in a Times-like fallback (F1, R4) | [`03-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/03-event-picker-1280.webp): the archived render has the correct type roles | Built in the §3.4 type roles; no "Team 4" aside (the events read has no team); "Round 1/2" is screen-reader text beside the seal; 390 disclosure "Show the {n} past events" (§11.1) |
| ![Profile card](assets/stitch/06-profile-card-mockup-desktop.webp) | DESKTOP | [`pages/06-profile-card-mockup.md`](../../archive/design/class-exercise/prompts/pages/06-profile-card-mockup.md) | High. Standard ribbon, the mock-up sentence moved to the caption, 48 px title and no pictogram, all per the `DESIGN.md` overrides | [`06-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/06-profile-card-mockup-1280.webp): Stitch's inert buttons have a sunk fill, which fixes archived flaw 3 (low contrast) | The `h1` sits in the shell header above the caption column, not inside it (§7.6); the card chip reads "Mock-up only" (§11.1) |
| ![Round two](assets/stitch/10-round-two-comparison-desktop.webp) | DESKTOP | [`pages/10-round-two-comparison.md`](../../archive/design/class-exercise/prompts/pages/10-round-two-comparison.md) | Medium. It has the 8 / 11 / 41 room, the round strip and the round-one line. The figures band sits in a card, and the chart panels are cards inside a card (§10) | [`10-…-1280`](../../archive/design/class-exercise/assets/generated/claude-html/10-round-two-comparison-1280.webp): Stitch splits the chart into three panels, so the team's bars are less of a sliver than in the archived render | The chart keeps one shared axis, not three panels (§6.16); the "In round one … 46 seats empty." line is not built, "Your team's first round" says it (§7.10); added = attended (§6.15) |
| ![Instructor](assets/stitch/11-instructor-desktop.webp) | DESKTOP | [`pages/11-instructor.md`](../../archive/design/class-exercise/prompts/pages/11-instructor.md) (screen B) | Medium. Unlock comes first, data files sit on the right, and the team 2 inline confirm is the only red. Team rows wrap to 3–4 lines | [`11-instructor-1280`](../../archive/design/class-exercise/assets/generated/claude-html/11-instructor-1280.webp): same cramped team rows as archived flaw 2. Stitch's "Clear team N's work" follows the green-quiet override | The right column is not sticky (§7.11); "Open results" asks first inline, "Open results now" / "Not yet" (§11.1); no "For Ann's file…" meta line; the upload shows one "Uploading and checking the file…", no stages (§6.24) |
| ![Instructor sign-in](assets/stitch/11-instructor-passcode-desktop.webp) | DESKTOP | same (screen A) | High. Centred 480 px card, key icon, show/hide toggle, and the "not your university login" helper | [`11-instructor-passcode-1280`](../../archive/design/class-exercise/assets/generated/claude-html/11-instructor-passcode-1280.webp): equivalent. Stitch's ribbon runs full-bleed without the card radius | The toggle has one fixed name, "Show what is typed", and `aria-pressed` carries the state (§11.1) |

Not generated: [`pages/07-points-counter.md`](../../archive/design/class-exercise/prompts/pages/07-points-counter.md), deferred by `DESIGN.md` §6.23.

### 2.3 Components (desktop)

| Image | Device | Prompt | Fidelity | Compared with the archived render | Built as |
|---|---|---|---|---|---|
| ![Weight slider](assets/stitch/weight-slider-desktop.webp) | DESKTOP | [`components/weight-slider.md`](../../archive/design/class-exercise/prompts/components/weight-slider.md) | Medium. Slider plus number box (the owner ruling), the drag bubble and the red invalid field. The bubble clips its "0.25", and the card title is sans, not serif | [`weight-slider-1280`](../../archive/design/class-exercise/assets/generated/claude-html/weight-slider-1280.webp): the archived render shows more states (focus, rebuilding, 390 bar) | Typed values are sent unclamped; only the thumb clamps. A refusal shows once, under the slider, and box and thumb revert; a negative reads "A weight cannot be below 0." (§6.6, #252) |
| ![Ranked rows](assets/stitch/ranked-row-desktop.webp) | DESKTOP | [`components/ranked-row.md`](../../archive/design/class-exercise/prompts/components/ranked-row.md) | High. The reason sits under the name, markers use icon plus words, and row 6 has the gold "joined" wash. Marker chips wrap in the narrow last column. Regenerated once (R5) | [`ranked-row-1280`](../../archive/design/class-exercise/assets/generated/claude-html/ranked-row-1280.webp): equivalent after the column fix | Measured 1280 columns (Year 7.75rem, Major 20%, marker 27%), so chips wrap to 2 lines at most (§6.7) |
| ![Saved settings](assets/stitch/saved-setting-card-desktop.webp) | DESKTOP | [`components/saved-setting-card.md`](../../archive/design/class-exercise/prompts/components/saved-setting-card.md) | High. Weights as numbers only, the "Comparing" outline and chip, a dashed free slot, and Delete in quiet green | [`saved-setting-card-1280`](../../archive/design/class-exercise/assets/generated/claude-html/saved-setting-card-1280.webp): equivalent | "Open this list" is secondary; Delete opens "Delete Balanced? It cannot be brought back." / "Delete it" / "Keep it"; save shows "Saving…" (§6.11, §11.1) |
| ![Compare](assets/stitch/compare-view-desktop.webp) | DESKTOP | [`components/compare-view.md`](../../archive/design/class-exercise/prompts/components/compare-view.md) | Medium. It has the summary sentence, gold overlap rows and "Showing 10 of 30". The "on both lists" chip collides with the major text on wrapped names | [`compare-view-1280`](../../archive/design/class-exercise/assets/generated/claude-html/compare-view-1280.webp): the archived render was rated High with no layout flaw noted | Two stacked tables at 768 and up, each in its own scroll box, with its weights under the title (§6.12, §7.5) |
| ![Results reveal](assets/stitch/results-reveal-desktop.webp) | DESKTOP | [`components/results-reveal.md`](../../archive/design/class-exercise/prompts/components/results-reveal.md) | High. 8 / 6 / 46 seats, a serif headline with green numerals, and a ruled band at display size | [`results-reveal-1280`](../../archive/design/class-exercise/assets/generated/claude-html/results-reveal-1280.webp): equivalent final state. Neither shows motion | Green seats and the added figure are `team.attended_count`; open = 60 − 8 − attended (§6.15). The README's round-one data (attended 4) would draw 4 and 48: see drift D1 |
| ![Asking choices](assets/stitch/asking-choice-cards-desktop.webp) | DESKTOP | [`components/asking-choice-cards.md`](../../archive/design/class-exercise/prompts/components/asking-choice-cards.md) (confirm screen only) | High. The inline "Confirm: A small reward?" with a gold countdown underline and the 5-second helper. No modal | [`asking-choice-cards-1280`](../../archive/design/class-exercise/assets/generated/claude-html/asking-choice-cards-1280.webp): the archived render also shows the chosen state. Stitch shows the confirm moment only | Same helper change as `09-…-mobile`; no "Saving…" label, a spinner keeps "Confirm: …" while pending (§6.18) |
| ![Unlock panel](assets/stitch/instructor-unlock-panel-desktop.webp) | DESKTOP | [`components/instructor-unlock-panel.md`](../../archive/design/class-exercise/prompts/components/instructor-unlock-panel.md) | Medium. The chips carry icon and words, and nothing is red. The "Results are open" chip uses a closed padlock, where §4 wants `LockOpen` | [`instructor-unlock-panel-1280`](../../archive/design/class-exercise/assets/generated/claude-html/instructor-unlock-panel-1280.webp): the archived render uses the right icons and shows the inline confirm | The open chip uses `LockOpen` (§4); "Open results" opens the inline confirm (§11.1); no meta line and no "Results are open for …" status line; focus moves to the event name |
| ![States](assets/stitch/empty-and-loading-states-desktop.webp) | DESKTOP | [`components/empty-and-loading-states.md`](../../archive/design/class-exercise/prompts/components/empty-and-loading-states.md) | High. Eight states, server sentences verbatim, and only the connection card is red. It adds a "State board" frame title, as the archived render did | [`empty-and-loading-states-1280`](../../archive/design/class-exercise/assets/generated/claude-html/empty-and-loading-states-1280.webp): equivalent | The locked card has no "Check again" (§6.14); the empty compare line reads "Save two settings to see them side by side." (§6.11) |

### 2.4 Flaws kept (none breaks a rejection rule)

| # | Flaw | Where |
|---|---|---|
| F1 | Stand-in fonts did not load; text fell back to Times or Arial | `03-…-desktop`, `08-…-mobile` |
| F2 | One heading in sans where Source Serif 4 was asked for | `01-…-desktop`, `weight-slider-desktop` |
| F3 | Invented sub-lines under 3 headings ("Comparison between your team's invitations and reaching the entire pool.", "Fictional profiles selected using the final setting \"Major first\".", "Offer an incentive or question to learn more before the next event.") and an uppercase "FRONT OF THE ROOM" | `08-…-mobile` |
| F4 | Stitch drew the `MOBILE` screen centred on a 1280-wide canvas; the 390 column was cropped out | `04-…-mobile`, `09-…-mobile` |
| F5 | Small invented labels: "List A" / "List B", "The list (first 30 of 300 fictional profiles)", "Showing ranks 9 and 10 of 30", an input placeholder | `05-…-desktop`, `05-…-mobile` |

## 3. Rejected / regenerated

29 Stitch generations produced 24 kept images. Each image was regenerated at most once, and there was no rate-limit or quota error.

| # | Image | First attempt's fault | Second attempt | Kept |
|---|---|---|---|---|
| R1 | `08-final-setting-and-results-desktop` | Invented 3 sub-lines under section heads (text not in `DESIGN.md`) | Clean | 2nd |
| R2 | `08-final-setting-and-results-mobile` | The same 3 invented lines, uppercase "FRONT OF THE ROOM", sans headline | Worse: dropped the seating chart, put "The room" over an invented line, duplicated "Go to asking for more" | 1st (flaws F1 and F3) |
| R3 | `08-final-setting-and-results-locked-desktop` | Invented card text: "Active choice", "Select setting", "30 invited" | Clean | 2nd |
| R4 | `03-event-picker-desktop` | Title, lead and meta in a Times-like fallback | Same fault, same pixels | 1st (flaw F1) |
| R5 | `ranked-row-desktop` | Name column about 110 px, so reason lines broke one word per line | Readable columns; chips wrap | 2nd |

Checks on all 24 kept images:

- 0 wrong brand colours
- 0 photos or people
- 0 per-person percentages or scores
- 0 "real student", "respondent" or survey-response wording
- Every ribbon reads "Fictional data — All student profiles are fictional, shaped by overall survey percentages."

## 4. `DESIGN.md` vs archived prompt disagreements

12 found before the build. The first 7 were sent to Stitch as overrides, where `DESIGN.md` wins. The last 5 were noted and not applied, because the `DESIGN.md` side is a schematic wireframe or an example rather than a rule. The **Build** column says what the build (#245, #247–#251) shipped. Drift found after the build is in [section 5](#5-prompt-drift-archived-prompts-vs-final-designmd); this table is not repeated there.

| # | Archived prompt says | `DESIGN.md` says | Applied? | Build |
|---|---|---|---|---|
| 1 | Figures-band numerals 64 px (`pages/08`, `pages/10`, `components/results-reveal`) | `--ce-type-display` 72/76 (§3.4, §6.15); 40 px on 390 (§7.8) | Yes | As `DESIGN.md`: display 72/76, 40 on 390 |
| 2 | "Delete" is a quiet **red** text button (`pages/05`, `components/saved-setting-card`) | A quiet button is primary-colour text. Red appears only on the destructive confirm inside an inline confirm (§6.3, §6.11) | Yes | As `DESIGN.md`: quiet green, then "Delete it" / "Keep it" inline (#251) |
| 3 | "Clear team N's work" is quiet **red** text (`pages/11`) | Same rule, §6.3 | Yes | As `DESIGN.md`: quiet green, then "Yes, clear team N" in red (#250) |
| 4 | `pages/06` swaps the ribbon sentence for a mock-up disclaimer | The ribbon text is a fixed constant and never changes (§6.2) | Yes: the disclaimer moved to the caption | As `DESIGN.md`: the shell's ribbon; the sentence sits in the caption column (#249) |
| 5 | `pages/06` puts an ID-card pictogram above the title | No icon or illustration beside a page title (§4, §10) | Yes | As `DESIGN.md`: no pictogram |
| 6 | `pages/06` title 40 px; phone card 18 px corners | `h1` 48/56 (§3.4); card radius 14 px, and 18 px is for mobile sheets only (§3.6) | Yes | As `DESIGN.md`: the shell's 48/56 `h1` (#249) |
| 7 | `pages/09` shows only the chosen state | The owner-ruled inline confirm (§6.18, §11 item 3) | Yes: `09-…-mobile` shows the confirm moment | As `DESIGN.md`, plus the guard, key-repeat and blur rules (§6.18, #249) |
| 8 | Back button "Back to your team's list" (`pages/08`, `pages/10`) | §7.8 wireframe: "← Back to your list" | No (wireframes are schematic, §7) | Kept the prompt: "Back to your team's list" (#247) |
| 9 | Header: secondary button "Choose a different event" (`pages/04`) | §7.4 wireframe: "Team 4 · Choose another →" | No (schematic) | Kept the prompt: "Choose a different event"; no "Team 4" (#251) |
| 10 | Coverage notice: "…a Freshman or a Finance, Real Estate & Law major." | §6.10 example: "…a Senior or an Accounting major." | No: §9 says to use the README's shared data | n/a: the server writes the notice |
| 11 | Empty compare: "Save two to see them side by side." (`components/empty-and-loading-states`) | §6.11: "Save two settings to see them side by side." | No: rendered as archived. Fix it in the build | As `DESIGN.md`: "Save two settings to see them side by side." (#251) |
| 12 | Invalid-weight message: "\"1,5\" is not a plain number. Use digits and one decimal point, like 0.5." | §6.6: "Type a number for this weight." or the server's refusal sentence | No: read as the server's refusal | Both: "Type a number for this weight." for an empty box, the prompt's sentence for text that is not a plain number; server refusals verbatim, under the slider (#251, #252) |

## 5. Prompt drift: archived prompts vs final `DESIGN.md`

The archived prompts under
[`docs/archive/design/class-exercise/prompts/`](../../archive/design/class-exercise/prompts/README.md)
are read-only. A rebuild applies these corrections on top of them, and on top of
the 12 rows in [section 4](#4-designmd-vs-archived-prompt-disagreements), which
are not repeated here. 26 items. D1, D2 and D8 would mislead a rebuild most.

| # | Where (archived prompt) | The prompt says | The build does (`DESIGN.md` §) |
|---|---|---|---|
| D1 | README §7 round one and round two; `pages/08`; `pages/10`; `components/results-reveal` | "Your invitations added 6" is the team's **signed-up** count (`team.signed_up_count`, prop `team_signed_up_count=6`), while the team attended 4. Round two: added 11, attended 8 | Added and the green seats are `team.attended_count`; the server stores `seats_empty = 60 − 8 − attended` (§6.15). The README data would show 8 / 4 / 48 and 8 / 8 / 44. For a rebuild, keep 8 / 6 / 46 and 8 / 11 / 41 and set the team's attended to 6 and 11 |
| D2 | `pages/08` screen A (both tools); `components/empty-and-loading-states` panel 2 | The locked panel has a secondary "Check again", and `ce-unlock` plays if the check finds results open | No action. Teams cannot read the lock, so any check is the one-time run itself; the Run button is the only retry (§6.14) |
| D3 | `pages/08` screen A and Claude Design steps 2–3 | Run is disabled while locked; an open event shows the chip "Results are open" | Run stays live once a setting is chosen. No open chip before a run; the locked panel appears only after a refused run, above the picker (§6.14, §7.8) |
| D4 | `pages/08` Claude Design step 4 | "A team runs results once per event." under the Run button | "Your team has not run results for this event yet. A team runs them once." above the picker. The §6.14 already-run line is not rendered |
| D5 | `pages/08` screen B | Invited chips show the first 8, then "and 22 more"; the last section's button is "Go to asking for more" | Every invited name shows. The last section keeps "Ask them now" (or "Pick one first" when no way is picked) and "Your team may ask once." |
| D6 | `pages/08` and `pages/10` 390 follow-ups | The chart becomes horizontal bars at 390 | Deferred until Ann answers the shared-scale question: one shared-axis chart in its own scroll box (§6.16). §7.8 still says horizontal bars |
| D7 | `pages/10` (both tools) | A quiet line under the headline: "In round one your team's list left 46 seats empty." | Not built. The "Your team's first round" section says the same numbers. §7.10 still lists the line |
| D8 | `pages/05`; `components/compare-view` (and its Variant B); README file table | Two lists side by side: 552 px cards in a 2-column grid; optional gutter connectors | Two tables stacked full width, each in its own scroll box, at 768 and up; tabs plus cards below 768; no connectors (§6.12, §7.5) |
| D9 | `components/results-reveal` Claude Design | A quiet "Skip" button during the seat fill | No Skip. The fill runs once, in 1.8 s at most; reduced motion shows the final state (§5.1) |
| D10 | `pages/09`; `components/asking-choice-cards` | Visible helper "Press again within 5 seconds. Your team picks once." | The visible helper and the live region both read "Press again to confirm A small reward. Your team picks once." (§6.18, §11.1) |
| D11 | `components/asking-choice-cards` flow | Any second press in the window commits; "Saving…" shows for 600 ms; blur and key repeat are not covered | A press within 300 ms of arming is ignored; a held Enter or Space never confirms; blur does not disarm; no "Saving…" label, a spinner keeps "Confirm: …" (§6.18) |
| D12 | README §7; `pages/09` | Third figure "Topics added from the first event" (34) | "Picked up the first event's topics". It counts people (`len(gainers)`), not topics (§6.19) |
| D13 | `pages/09` (both tools) | The half-filled card pictogram sits right of the lead | Beside the "How will your team ask?" `h2`, 96 px; the shell has no slot beside the lead (§7.9) |
| D14 | `pages/09` Claude Design | "Ask them now" is disabled until a way is chosen, helper "Pick a way of asking first." | Shut until a way is chosen **and** round-one results exist; the reason line reads "Run your team's results for … before asking." |
| D15 | `pages/11` screen B and Claude Design | The right column is sticky | It scrolls with the page. At 1280 it is 1615–2411 px tall, so a sticky column hid "Move every team" and "Sign out" (§7.11) |
| D16 | `pages/11` screen B (Stitch); `components/instructor-unlock-panel` (Stitch) | "Open results" is a plain button | The first press opens an inline confirm: "Open results for {event}? Every team can then run results once for this event." / "Open results now" ("Opening…") / "Not yet". Escape cancels (§6.24, §11.1). The Claude Design prompts already had it |
| D17 | `pages/11`; `components/instructor-unlock-panel` | Meta line "For Ann's file, 25 September. Teams can run results only for an event that is open."; status line "Results are open for Harbor Consumer Brands." | Neither is built (neither is in §11.1). Focus moves to the event's name when the unlock lands |
| D18 | `pages/11` Claude Design | The upload shows three stages ("Reading the file" → "Checking the columns" → "Saved") and a determinate bar | One label, "Uploading and checking the file…": the client sends one request and has no stages. §6.24's loading row still names stages |
| D19 | `pages/11` Claude Design | A show/hide toggle with `Eye`/`EyeOff`; its name is not given | One fixed name, "Show what is typed"; `aria-pressed` carries the state (§11.1) |
| D20 | `components/weight-slider` Claude Design | A server refusal is a calm notice above the card, and the fields revert | The refusal shows once, under the slider, and box and thumb revert (§6.6, owner ruling 2026-09-27). Typed values go out unclamped; a negative is refused as "A weight cannot be below 0." (#252) |
| D21 | `pages/03`; `pages/04` | Header aside "Team 4" | No team indicator: neither read returns the team (backlog row "The screen never shows which team you are") |
| D22 | `pages/04` Stitch | The table fades after row 10 with "20 more names below" | All 30 rows render |
| D23 | `pages/02` (both tools) | The license panel sits at the page foot (390: above the button) | One license card, in the top zone under the lead (§7.1) |
| D24 | `pages/02` Claude Design | The `<legend>` renders as the `h2` | A visible `h2` "Which team are you?"; the legend "Team number" is screen-reader only |
| D25 | `pages/06` Claude Design | The `h1` sits inside the left caption column | The `h1` is in the shell header above both columns; the caption column holds the §11.1 caption and the mock-up sentence (§7.6) |
| D26 | README §4–§5 preambles; `pages/01` | A grey logo placeholder; the dark tokens have no logo rule | Dark mode sets the unchanged CPP logo on an eggwhite plate (`exercise.css`; not yet in `DESIGN.md`) |

## 6. How to regenerate

1. **Connect Stitch at user scope.** Use Google's remote MCP server
   `https://stitch.googleapis.com/mcp`, with the API key sent as the
   `X-Goog-Api-Key` header. The key stays in the user-scope MCP config, never
   in this repo:

   ```bash
   claude mcp add --scope user --transport http stitch https://stitch.googleapis.com/mcp \
     --header "X-Goog-Api-Key: $STITCH_API_KEY"
   ```

   The local `/stitch` command wraps a third-party npm package. Do not use it.
2. **Build the design system from the final `DESIGN.md`** with
   `upload_design_md`, then `create_design_system_from_design_md`. Still state
   each hex in the prompt: the ingest maps the tokens to a Material palette
   (section 1).
3. **Assemble each prompt in this order:**
   1. the [Stitch style preamble](../../archive/design/class-exercise/prompts/README.md#4-stitch-style-preamble) and the
      [shared fictional data](../../archive/design/class-exercise/prompts/README.md#7-shared-fictional-data), with D1's
      numbers fixed
   2. the page's archived Stitch prompt, unedited
   3. the section 4 overrides and the section 5 drift items for that file
   4. the guard rules: no nav bar, photos or people; no invented copy; the
      exact ribbon text; no per-person numbers; the data wording
4. **`DESIGN.md` wins** over the prompts and over every image here. Three
   `DESIGN.md` lines still lag the build (D6, D7, D18); follow the build there.
5. **Use device types, not pixel widths.** `DESKTOP` stands for the archived
   "1280", and `MOBILE` for "390".
6. **Check each screen for the known Stitch flaws** before keeping it:
   - **Font fallback (F1, F2):** the licensed faces cannot load. Name the
     stand-ins (Archivo SemiExpanded, Source Serif 4, Figtree) and check that
     the export loads them from Google Fonts.
   - **Mobile on a desktop canvas (F4):** a `MOBILE` screen can come back
     centred on a 1280-wide canvas. Crop to the 390 column, or regenerate.
   - **Invented copy (F3, F5):** regenerate once, then keep the better attempt
     and log the flaw.
7. **Post-process:** desktop 1280 px wide, mobile 780 px (390 at 2x), WebP
   q82. Scan each HTML export before committing: no keys, no trackers, no
   scripts beyond the Tailwind CDN, Lucide and Google Fonts. Then update the
   gallery and its Built as column.

## 7. Top 3

1. [`assets/stitch/08-final-setting-and-results-desktop.webp`](assets/stitch/08-final-setting-and-results-desktop.webp): the lesson's payoff reads at a glance. The room fills 8 / 6 / 46, the serif headline states the same numbers, and the ruled band repeats them. It is counts only, with no invented copy after the regeneration. Best evidence for the build.
2. [`assets/stitch/05-save-and-compare-desktop.webp`](assets/stitch/05-save-and-compare-desktop.webp): the whole save-and-compare loop fits on one screen. Stitch added each setting's weights under the list title, and the quiet green Delete follows `DESIGN.md`. Gold is used for exactly one job.
3. [`assets/stitch/09-asking-for-more-mobile.webp`](assets/stitch/09-asking-for-more-mobile.webp): the clearest picture of the owner's inline-confirm ruling on a phone. The same button becomes "Confirm: A small reward?" with a half-spent countdown and no pop-up.
