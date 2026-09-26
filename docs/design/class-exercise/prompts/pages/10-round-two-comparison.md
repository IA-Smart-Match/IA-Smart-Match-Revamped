# Page 10 — round-two comparison

The results screen for the second event. It adds the team's own round-one
result as a third panel, so the class sees whether asking for more and
re-weighting changed anything.

- **Route:** `/exercise/events/:eventKey/results` for the round-two event. Code: `ResultPanels.tsx` (`round_one` branch), `ExerciseResultsChart.tsx`.
- **System:** [`DESIGN.md` 6.15, 6.16 and 7.10](../../DESIGN.md#710-round-two-comparison-results-for-the-second-event), motion `ce-seat-fill`, `ce-count-up`.
- **Component:** [results reveal](../components/results-reveal.md).
- **Asset:** [`round-journey.svg`](../../assets/svg/round-journey.svg).
- **Reference:** [`room/results-1280.png`](../../assets/mockups/room/results-1280.png) for the hero; Fable's proposals describe two rooms side by side for round two — this system keeps one room (round two) plus the round-one line, to keep the projector view to one picture.
- **Content:** round two results and the round-one panel in [README section 7](../README.md#7-shared-fictional-data).
- **States:** first reveal, revisit, round one built without a saved setting, a panel with a missing count, 390.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash ribbon. Title
"Results" (Archivo SemiExpanded 600, 48px), secondary button "Back to your
team's list"; lead "What your team's list did, next to what emailing all
300 would have done, and next to your team's first round."

A slim strip under the lead: a small geometric pictogram of circle "1",
dotted arrow, filled circle "2" in CPP Green #005030 (120px wide), then
"Round 2 · Harbor Consumer Brands" in Figtree 20px.

Hero, two columns: left, a white card "The room" with a 6x10 seating chart:
8 warm-brown #8C6D62 seats (already coming), 11 CPP Green seats with a tiny
white check (your invitations), 41 outlined #8F7A70 seats (still open),
legend with counts. Right: headline in Source Serif 4 semibold 40px with
green numerals: "8 were already coming. / Your invitations added 11. / 41
seats are still open." Under it a quiet line in #59665F: "In round one your
team's list left 46 seats empty." Then a ruled figures band: 60 "Seats in
the room", 8 "Already coming", 41 "Still open".

Section "What happened for Harbor Consumer Brands": grouped bars with three
groups: "Your team's list" (30 / 11 / 8), "If you emailed everyone" (300 /
44 / 29), "Your team, round one" (30 / 6 / 4). Series: invited = pale green
#D9EADF with CPP Green outline; signed up = CPP Gold #FFB81C hatched with a
#7A5200 outline; attended = solid CPP Green. Numbers on every bar. Caption:
"Your team's list, contacting all 300, and your team's first round."

Section "Your team's first round": "Built from your team's setting “Major
first”. It left 46 seats empty."

No arrows up or down, no "+83%", no "improved" badges, no percentages.
```

**390 follow-up:** "At 390px: stack everything; the chart becomes three
horizontal bar groups; keep the round strip at the top."

## Claude Design prompt

```text
Build the round-two results screen for the Smart Match class exercise with
the preamble tokens, reusing the results-reveal component.

Differences from page 8:
- Lead: "What your team's list did, next to what emailing all 300 would have
  done, and next to your team's first round."
- A round strip: ../../assets/svg/round-journey.svg (120px, --ce-primary,
  aria-hidden) + "Round 2 · Harbor Consumer Brands" (body 20px).
- Reveal props: seats 60, taken 8, added 11, open 41; plus a quiet line
  under the headline "In round one your team's list left 46 seats empty."
  (from round_one.seats_empty; singular "1 seat").
- Chart: three groups in this order — "Your team's list", "If you emailed
  everyone", "Your team, round one" — same series styling as page 8. The
  <details> table gains the third row.
- h2 "Your team's first round": "Built from your team's setting “Major
  first”. It left 46 seats empty." If round one used no saved setting:
  "Built without a saved setting."
- People chips for round two's list, as on page 8.

Do not compute or display a difference ("+5 seats", arrows, "improved").
The class draws the comparison; the screen lays the numbers side by side.

States for the switcher: First reveal · Revisit · Round one without a saved
setting · A missing count (one bar absent, the table cell and a line read
"Your team, round one: attended not available") · 390.
```

## Review checklist

1. Three panels in the fixed order; round one never computed from round two.
2. No deltas, arrows, or "improved" language.
3. "not available" is words, never a zero bar.
