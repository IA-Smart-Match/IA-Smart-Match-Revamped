# Page 4 — ranked top 30 with reason lines and four sliders

The screen the lesson turns on. The team sets four weights; the list of 30
re-sorts; each name says why it is there; a table shows who the list leaves
out.

- **Route:** `/exercise/events/:eventKey`. Code: `ExerciseMatching.tsx`, `WeightsControls.tsx`, `RankedList.tsx`, `ListCompositionTable.tsx`, `ListCoverageNotice.tsx`.
- **System:** [`DESIGN.md` 6.6–6.10 and 7.4](../../DESIGN.md#74-matching-exerciseeventseventkey), motion `ce-row-reorder`, `ce-row-join`, `ce-row-leave`, `ce-list-rebuilding`.
- **Components:** [weight slider](../components/weight-slider.md), [ranked row](../components/ranked-row.md).
- **Library:** Radix Slider; `motion` `layout` for rows.
- **Reference:** [`room/list-1280.png`](../../assets/mockups/room/list-1280.png), [`room/list-390.png`](../../assets/mockups/room/list-390.png). Take the two-column top and the list rhythm; leave out its "30 of 60 chairs reserved" room (invitations are not seats).
- **Content:** Northline Analytics, Team 4 weights 0.40/0.25/0.25/0.10, ranks 1–30 from [README section 7](../README.md#7-shared-fictional-data), coverage notice.
- **States:** ready, rebuilding, refused change (stale list), loading, empty list, no workspace, unreachable.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash fictional-data ribbon
at the top. Header row: title "Northline Analytics" (Archivo SemiExpanded
600, 48px, #163229); right side quiet text "Team 4" and a secondary button
"Choose a different event". Lead line Figtree 22px #59665F: "Decide how much
each thing counts, then see who that puts on the list — and who it leaves
off."

Two columns below (360px left, rest right, 24px gap):

Left, sticky: white card "How much each thing counts" (Source Serif 4 24px)
with four sliders, each labelled in lowercase exactly: "same major" 0.40,
"said they are interested in this topic" 0.25, "career goal fits this
event" 0.25, "went to similar events before" 0.10. Slider: 6px beige track
#F2EEE8 with 2px #8F7A70 outline, CPP Green #005030 fill, 28px white thumb
with a green ring; an 88px value box at the right of each label with
tabular figures. A small note: "The list is rebuilt when you let go of a
slider or press Enter."

Right: white card "The list" (Source Serif 4 32px) with a secondary button
"Download this list as a spreadsheet" (download icon) on the right and a
line "Cut at 30 names, the limit set for this data file." Then a one-line
notice with a people icon on #FFF1CC: "Nobody on this list is a Freshman or
a Finance, Real Estate & Law major." Then the ranked table: columns Rank ·
Name · Major · Year · How much we know. Rank in CPP Green Archivo bold 28px;
name Figtree 20px semibold with the reason line under it in Source Serif 4
18px #59665F; marker as a pill chip with icon and words. Rows 1–10:
Maya Tran (Computer Information Systems, Senior, completed card, "What
counted: same major; said they are interested in this topic; career goal
fits this event."), Daniel Okafor (International Business & Marketing,
Senior, completed card, "What counted: same major; career goal fits this
event."), Priya Patel (Computer Information Systems, Junior, major plus
events attended, "What counted: same major; went to similar events
before."), Jordan Kim (Computer Information Systems, Senior, major only,
"Same major; nothing else on file."), Alexis Rivera (Computer Information
Systems, Junior, major only, "Tied on major; ordered by year."), Ethan
Nguyen, Sofia Morales, Marcus Chen, Hannah Lee, Diego Garcia (mixed majors
and years, reasons like the ones above). Fade the table out after row 10
with "20 more names below".

No percentages, no scores, no match bars. The only per-person number is the
rank.
```

**390 follow-up:** "At 390px: the sliders card first and full width; a
compact sticky bar at the top once scrolled, 'Weights 0.40 · 0.25 · 0.25 ·
0.10 — Edit weights'; the list as stacked rows (rank left, then name,
reason line, 'major · year', marker chip)."

## Claude Design prompt

```text
Build /exercise/events/northline for the Smart Match class exercise with
the preamble tokens. Reuse the weight-slider and ranked-row components you
built earlier in this project.

Layout 1280: header (h1 "Northline Analytics", aside "Team 4" + secondary
"Choose a different event", lead). Grid 360px | 1fr, 24px gap.
- Left column: sticky (top 24px) card with the four sliders (values 0.40,
  0.25, 0.25, 0.10).
- Right column: card "The list" (h2) with header actions: status slot
  (aria-live polite) and secondary "Download this list as a spreadsheet"
  (Lucide Download; a plain link to a CSV). Meta line "Cut at 30 names, the
  limit set for this data file." Coverage notice (Lucide UsersRound,
  --ce-gold-tint, body 20px): "Nobody on this list is a Freshman or a
  Finance, Real Estate & Law major." Then the full 30-row ranked table
  (README section 7).
Below the grid, full width:
- h2 "Who is on the list": three small tables side by side (By major, By
  year, By how much we know), columns "On this list" and "In the whole data
  file", tabular right-aligned numerals, zero shown as 0 in ink. Under them:
  "Everyone in this data file could be ranked for this event." and "Every
  year in this data file has somebody on the list." Invent plausible counts
  that sum to 30 and 300.
- Then a placeholder for the saved-settings section (page 5) and a primary
  button "Go to results for this event".

Interaction: moving a slider and releasing it triggers "Rebuilding the
list…" (table at 0.6 opacity, 600ms), then the rows re-order with
ce-row-reorder, one name leaves (ce-row-leave) and one joins (ce-row-join
gold wash). Reduced motion: instant re-order with a 150ms crossfade; static
gold wash for 900ms.

States for the switcher: Ready · Rebuilding · Refused change (calm notice
above the list with the server's sentence, illustrative "Those weights were
not accepted."; list at 0.6 with the stale line "This is the list from
before that change — it was refused, so the list has not changed.") ·
Loading (slider card renders; list shows 8 skeleton rows) · Empty list
(empty-state card) · No workspace (calm notice + "Enter your team number") ·
Unreachable · 390.

390: slider card first; when it scrolls out, a sticky compact bar
(--ce-elev-3) "Weights 0.40 · 0.25 · 0.25 · 0.10" + quiet "Edit weights"
that scrolls back and focuses the first slider. Ranked rows as an <ol> of
stacked items. The three composition tables become three <details>
disclosures ("By major", "By year", "By how much we know").
```

## Review checklist

1. Reason lines verbatim under each name; factor labels verbatim on sliders.
2. No room/seat picture on this screen; no per-person number other than rank.
3. The list header reports the limit from data ("Cut at 30 names…").
4. At 390 the weights stay reachable while reading the list.
