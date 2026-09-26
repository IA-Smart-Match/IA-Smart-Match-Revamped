# Page 5 — save up to 3 settings and compare 2

The lower zone of the matching screen. The team names the weights on
screen, keeps up to `max_settings` of them, and compares two with the
shared names highlighted.

- **Route:** `/exercise/events/:eventKey` (lower zone). Code: `SavedSettingsPanel.tsx`, `ExerciseMatching.tsx` `ComparisonView`.
- **System:** [`DESIGN.md` 6.11, 6.12 and 7.5](../../DESIGN.md#75-saved-settings-and-compare-same-route-lower-zone), motion `ce-card-save`, `ce-fade-rise`, `ce-overlap-pulse`.
- **Components:** [saved-setting card](../components/saved-setting-card.md), [compare view](../components/compare-view.md).
- **Reference:** [`room/compare-1280.png`](../../assets/mockups/room/compare-1280.png), [`room/compare-390.png`](../../assets/mockups/room/compare-390.png).
- **Content:** "Major first", "Interests first", "Balanced"; comparing the first two; 12 names on both lists.
- **States:** none saved, one saved, three saved, saving, two chosen, comparison open, nobody on both, refusal.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page. This is the lower half of the
"Northline Analytics" list screen; show the bottom of the ranked list card
at the top edge, then:

Section "Your team's saved settings" (Source Serif 4 32px) and the line
"Your team may keep 3 for this event. You have 3." A save form: label "Name
these weights", text field, secondary button "Save these weights", helper
"Saves the 4 numbers now on screen."

Three index-card panels in a row (white, 14px corners, soft shadow): "Major
first" (same major 0.60 · said they are interested in this topic 0.15 ·
career goal fits this event 0.15 · went to similar events before 0.10),
"Interests first" (0.15 · 0.45 · 0.25 · 0.15) and "Balanced" (0.25 each).
Values in bold tabular figures, labels in small grey text. Each card has
"Open this list", a "Compare" toggle and a quiet red "Delete". Cards 1 and 2
are chosen for comparison: 3px CPP Green #005030 outline and a small green
"Comparing" chip. Under the row a primary CPP Green button "Show them side
by side".

Below: section "Two settings, side by side" with "Close this comparison" on
the right, and the line "12 names are on both lists, highlighted in each."
Two white cards side by side, "Major first" and "Interests first", each a
ranked list of 10 names (CPP Green rank numerals, bold names, grey reason
line). Shared names (Daniel Okafor, Jordan Kim, Alexis Rivera, Marcus Chen,
Diego Garcia, Chloe Brooks) have a pale gold #FFF1CC row and a CPP Gold
#FFB81C chip "on both lists" with a link icon. Under each list: "Showing 10
of 30. Show all 30".

At the bottom, a primary CPP Green button "Go to results for this event".
No Venn diagrams, no overlap percentage.
```

**390 follow-up:** "At 390px: cards stack; the comparison becomes a
two-segment control 'Major first | Interests first' above one list; the
summary line stays above the control."

## Claude Design prompt

```text
Build the lower zone of /exercise/events/northline for the Smart Match
class exercise with the preamble tokens, reusing your saved-setting card
and compare-view components.

Order:
1. h2 "Your team's saved settings", count line (from max_settings and the
   list length), save form (label "Name these weights", field, secondary
   "Save these weights", helper "Saves the 4 numbers now on screen.").
2. Grid of max_settings slots (3 columns at 1280, stacked at 390).
3. Compare controls: "Compare" toggles on the cards; once two are chosen, a
   primary "Show them side by side" appears under the grid. With fewer than
   two saved: "Save two settings to see them side by side."
4. Compare view (when open), entering with ce-fade-rise, then
   ce-overlap-pulse on the 12 shared rows.
5. Primary "Go to results for this event" (the only primary once compare is
   closed; while compare is open, "Show them side by side" is hidden).

Interactions: save "Balanced" into the free slot (ce-card-save); choose
cards 1 and 2; open comparison; close it (ce-fade-rise reversed at 140ms).

States for the switcher: None saved · One saved · Three saved · Saving ·
Two chosen · Comparison open (12 on both) · Nobody on both · Refusal on save
(calm notice with "Give your settings a short name.", typed text kept) ·
Delete confirm (inline) · 390 comparison, segment A · 390 comparison,
segment B.

Keep exactly one primary button visible per region.
```

## Review checklist

1. The cap sentence reads from data; a save over an existing name is not blocked.
2. Overlap marked with chip plus wash; summary sentence handles 0, 1, many.
3. One primary per region.
