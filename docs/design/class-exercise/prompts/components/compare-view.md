# Component — compare view

Two saved settings' lists side by side, with the names on both lists
marked. The overlap is the point: those people were chosen either way, so
the weighting did not decide them.

- **System:** [`DESIGN.md` 6.12](../../DESIGN.md#612-compare-view-see-prompt), motion `ce-fade-rise`, `ce-overlap-pulse`.
- **Reference:** [`room/compare-1280.png`](../../assets/mockups/room/compare-1280.png), [`room/compare-390.png`](../../assets/mockups/room/compare-390.png) (overlap rows, "Showing 10 of 30. Show all 30"). This system drops the per-list seat grid from that mock-up: invitations are not seats (see [`experiments.md`](../../experiments.md)).
- **Content:** "Major first" vs "Interests first"; 12 names on both lists.
- **States:** default, overlap highlighted, nobody on both, loading, refusal, 390 segmented view, closed.

## Google Stitch prompt

```text
A comparison section for a desktop web app on an eggwhite #F8F6F1 page.
Section title "Two settings, side by side" (Source Serif 4, 32px) with a
secondary button on the right "Close this comparison". Under the title one
large line in Figtree 22px #163229: "12 names are on both lists,
highlighted in each." with a small gold chip icon (link symbol) before it.

Two equal white cards side by side (each 552px), 14px corners, soft shadow.
Card titles in Source Serif 4 24px: "Major first" and "Interests first",
each with its four weights as a small quiet line under the title: "same
major 0.60 · interested 0.15 · career goal 0.15 · similar events 0.10".

Each card holds a 10-row ranked list: CPP Green #005030 rank numeral
(Archivo SemiExpanded bold 24px), name in Figtree 18px semibold, reason
line under it in Source Serif 4 16px #59665F, and major · year in #59665F.
Rows that are on both lists have a #FFF1CC wash and a small pill chip "on
both lists" (CPP Gold #FFB81C fill, #17352A text, link icon).

Left list: Maya Tran, Daniel Okafor*, Priya Patel, Jordan Kim*, Alexis
Rivera*, Ethan Nguyen, Marcus Chen*, Hannah Lee, Diego Garcia*, Chloe
Brooks*. Right list: Sofia Morales, Daniel Okafor*, Leila Haddad, Alexis
Rivera*, Grace Park, Jordan Kim*, Chloe Brooks*, Marcus Chen*, Aisha Bello,
Diego Garcia*. (* = on both lists.)

Under each card: "Showing 10 of 30. Show all 30" as a text link. No
percentages, no Venn diagram, no scores.
```

**390 follow-up:** "On a 358px phone, keep the summary line at the top, then
a two-segment control 'Major first | Interests first' (first selected), then
only the selected list. Keep the gold 'on both lists' chips."

## Claude Design prompt

```text
Build the compare view for the Smart Match class exercise with the preamble
tokens. It appears under the saved-setting cards after a team picks two
settings.

Structure: <section aria-labelledby> with h2 "Two settings, side by side",
a secondary "Close this comparison" button, and a summary line (body 22px)
"12 names are on both lists, highlighted in each." (singular form: "1 name
is on both lists, highlighted in each."; zero: "Nobody is on both lists.").
Then two ranked lists (reuse the ranked-row component) in a 2-column grid at
1280. Each list has a caption with the setting name (--ce-font-serif 24px)
and its four weights in one quiet line.

Overlap rows: persistent --ce-gold-tint wash plus a chip "on both lists"
(Lucide Link2, --ce-gold fill, #17352A text). Use the two lists in the
Stitch prompt; starred names are on both.

Motion: section enters with ce-fade-rise (opacity 0→1, y 8→0, 240ms
--ce-ease-out). Then ce-overlap-pulse: each overlap row's wash goes from
--ce-gold-tint to --ce-gold at 35% and back, once, 600ms total, 30ms
stagger top to bottom across both lists. Reduced motion: no pulse, static
wash, 150ms fade.

Optional desktop-only variant (label it "Variant B" in the switcher): thin
1px --ce-gold-ink connector lines between the same name in the two lists,
drawn in the gutter, only for overlap rows. Keep it off by default; it is
an experiment from the Corkboard direction.

390: a segmented control (two radio buttons styled as segments,
--ce-radius-control) switching which list shows; the summary line stays
above. Each list shows 10 rows then "Showing 10 of 30. Show all 30".

States for the switcher: Default (12 on both) · Nobody on both · One on
both (singular copy) · Loading (two skeleton lists) · Refusal (calm notice
with the server sentence "Your team has no saved settings with that name."
and the lists absent) · Variant B connectors · 390 A · 390 B.
```

## Review checklist

1. The summary sentence handles 0, 1 and many correctly.
2. Overlap is marked by chip and wash, not colour alone.
3. No Venn diagram, overlap percentage or similarity score.
4. The 390 view never places two lists side by side.
