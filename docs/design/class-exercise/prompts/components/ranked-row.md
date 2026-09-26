# Component — ranked row with reason line

One name on the ranked list: its position, who it is, and why it is there.
The reason line is the lesson's evidence, so it sits directly under the name.

- **System:** [`DESIGN.md` 6.7 and 6.8](../../DESIGN.md#67-ranked-row-with-reason-line-see-prompt), motion `ce-row-reorder`, `ce-row-join`, `ce-row-leave`.
- **Library:** `motion` 12.23 `layout` prop on each row for re-order (installed).
- **Reference:** [`room/list-1280.png`](../../assets/mockups/room/list-1280.png) (table rhythm; note it puts the reason in a separate "Why" column and uses dots for the marker — this system moves the reason under the name and uses icon plus words), [`room/list-390.png`](../../assets/mockups/room/list-390.png).
- **Content:** ranks 1–10 from [README section 7](../README.md#7-shared-fictional-data).
- **States:** default, hover (desktop), joined the list, on both lists, stale (after a refused change), loading skeleton, empty list.

## Google Stitch prompt

```text
A ranked list table for a desktop web app, full width 760px, inside a white
card with 14px corners and a soft shadow on an eggwhite #F8F6F1 page. Card
header: "The list" (Source Serif 4, 32px) and on the right a secondary
button "Download this list as a spreadsheet" with a download icon. Under the
header one line in #59665F: "Cut at 30 names, the limit set for this data
file."

Table columns (sentence case, Figtree 18px semibold, #59665F, on a #F2EEE8
header band): Rank · Name · Major · Year · How much we know.

Ten rows, 20px Figtree, generous 16px vertical padding, 1px #D9CBC4 dividers:
- Rank: big numeral in Archivo SemiExpanded bold 28px, CPP Green #005030.
- Name: Figtree 20px semibold #163229, and directly under it the reason
  line in Source Serif 4 18px #59665F, e.g. "What counted: same major; said
  they are interested in this topic; career goal fits this event."
- Major and Year as plain text.
- How much we know: a small pill chip with an icon and words — "major only"
  (hollow circle icon, #F2EEE8 fill), "major plus events attended" (dotted
  circle icon, #E8F2D8 fill), "completed card" (ID-card icon, #D9EADF fill,
  #003D24 text).

Rows:
1 Maya Tran · Computer Information Systems · Senior · completed card · "What counted: same major; said they are interested in this topic; career goal fits this event."
2 Daniel Okafor · International Business & Marketing · Senior · completed card · "What counted: same major; career goal fits this event."
3 Priya Patel · Computer Information Systems · Junior · major plus events attended · "What counted: same major; went to similar events before."
4 Jordan Kim · Computer Information Systems · Senior · major only · "Same major; nothing else on file."
5 Alexis Rivera · Computer Information Systems · Junior · major only · "Tied on major; ordered by year."
6 Ethan Nguyen · International Business & Marketing · Senior · major plus events attended · "What counted: same major; went to similar events before."
7 Sofia Morales · Technology & Operations Management · Senior · completed card · "What counted: said they are interested in this topic; career goal fits this event."
8 Marcus Chen · International Business & Marketing · Junior · major only · "Tied on major; ordered by year."
9 Hannah Lee · International Business & Marketing · Sophomore · major only · "Tied on major; ordered by year."
10 Diego Garcia · Accounting · Senior · major plus events attended · "What counted: went to similar events before."

Give row 6 a pale gold #FFF1CC background to show it just joined the list.
No scores, no percentages, no bars, no stars. Rank is only a position.
```

**390 follow-up:** "Turn each row into a stacked list item for a 358px
phone: rank numeral on the left (24px), then the name, then the reason line,
then one line with major · year, then the marker chip. 16px padding, 1px
dividers, no table header."

## Claude Design prompt

```text
Build the ranked-row component and a 10-row list for the Smart Match class
exercise, using the preamble tokens. Desktop (>=768px) is a real <table>
with <caption> "The names for Northline Analytics, in order." (visually
hidden); 390px is an <ol> of the same rows in the same content order.

Row anatomy (desktop): rank cell (--ce-font-display 700 28px,
--ce-primary, tabular); name cell containing the name (body 600 20px) and
the reason line beneath it (--ce-font-serif 18/28, --ce-ink-muted); major;
year; marker chip. Use the ten rows in README section 7 exactly, including
each reason sentence verbatim with its full stop.

Marker chip (pill, 16px body 500, 8px 12px padding, icon 16px + words):
"major only" = Lucide Circle on --ce-surface-sunk; "major plus events
attended" = CircleDot on --ce-avocado-tint; "completed card" = IdCard on
--ce-primary-tint with #003D24 text. Chips are not interactive.

Interactions to prototype:
1. A "Change weights" demo button outside the design that reorders the
   rows (swap ranks 3↔7, drop Hannah Lee, add "Chloe Brooks · Accounting ·
   Junior · major only · Same major; nothing else on file." at rank 9).
   Re-order uses layout animation, spring stiffness 500 damping 40
   (≈280ms). The new row gets ce-row-join: a --ce-gold-tint wash fading
   out over 900ms. The removed row fades and collapses in 140ms. With
   prefers-reduced-motion: rows jump, 150ms crossfade, and the gold wash
   is static for 900ms then removed.
2. While "rebuilding", the table dims to opacity 0.6 and a status line
   "Rebuilding the list…" appears in the card header (aria-live polite).

States for the switcher: Default · Row hover (desktop: row wash
--ce-surface-sunk) · Joined (gold wash on one row) · On both lists (rows 2,
4, 5, 8 keep a --ce-gold-tint wash and a chip "on both lists" with a Lucide
Link2 icon, --ce-gold fill, #17352A text) · Stale (table at 0.6 opacity and
the line "This is the list from before that change — it was refused, so
the list has not changed." in italic --ce-ink-muted above it) · Loading (8
skeleton rows: a 28px square for the rank, two bars for name and reason,
three short bars) · Empty (no table; --ce-surface card with
../../assets/svg/empty-state.svg at 96px in --ce-line-strong and the
sentence "Nobody is on this list. Nobody in this data file can be ranked
for this event with these weights.").

Do not add a score, percentage, "fit" bar or tooltip. Do not truncate the
reason line; let it wrap.
```

## Review checklist

1. Reason lines are verbatim, wrap, and sit under the name.
2. Marker chip carries an icon and the full words; no 1–3 dot scale.
3. Overlap is shown by a chip with text, not colour alone.
4. The 390 view is a list, not a squeezed table.
