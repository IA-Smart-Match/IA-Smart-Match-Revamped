# Component — saved-setting card

A team may keep up to `max_settings` named weightings per event (3 today;
the number is the server's). Each is an index card the team can open,
compare, delete, and later choose as its final setting.

- **System:** [`DESIGN.md` 6.11](../../DESIGN.md#611-saved-setting-card-see-prompt), motion `ce-card-save`, `ce-lift`.
- **Reference:** [`room/compare-1280.png`](../../assets/mockups/room/compare-1280.png) (the three setting tags row), [`room/compare-390.png`](../../assets/mockups/room/compare-390.png).
- **Asset:** [`empty-state.svg`](../../assets/svg/empty-state.svg) for a free slot.
- **Content:** "Major first" (0.60, 0.15, 0.15, 0.10), "Interests first" (0.15, 0.45, 0.25, 0.15), "Balanced" (0.25 each).
- **States:** default, hover, focus, selected for compare, saving, empty slot, all empty, refusal on save, third compare toggle disabled, delete confirm.

## Google Stitch prompt

```text
A row of three index-card style panels for a desktop web app, each 352px
wide, on an eggwhite #F8F6F1 page. Above the row: a section title "Your
team's saved settings" (Source Serif 4, 32px, #163229), a line "Your team
may keep 3 for this event. You have 2." in #59665F, and a save form: a
labelled text field "Name these weights" (value "Balanced") and a secondary
button "Save these weights", with helper text "Saves the 4 numbers now on
screen."

Card 1 "Major first" and card 2 "Interests first": white, 14px corners,
soft shadow, no border, 24px padding. Title in Source Serif 4 24px. Under
it four rows, each a factor label in Figtree 16px #59665F on the left and
the value in tabular figures 20px bold #163229 on the right:
same major 0.60 / said they are interested in this topic 0.15 / career goal
fits this event 0.15 / went to similar events before 0.10 (card 2: 0.15 /
0.45 / 0.25 / 0.15). No bars, no percentages. Footer actions: secondary
button "Open this list", a checkbox-style toggle "Compare", and a quiet red
text button "Delete".

Card 1 is selected for comparison: 3px CPP Green #005030 outline and a small
green chip "Comparing" in the top-right corner.

Card 3 is an empty slot: dashed 2px #8F7A70 outline, no shadow, a simple
dashed-rectangle-with-plus pictogram in #8F7A70, and the text "Slot 3 of 3
is free. Save the weights on screen to fill it."
```

**390 follow-up:** "Stack the three cards full width (358px) with 16px gaps.
Put the save form above them with the button full width."

## Claude Design prompt

```text
Build the saved-setting card system for the Smart Match class exercise with
the preamble tokens. The number of slots comes from the server
(max_settings = 3); render slots in a 3-column grid at 1280 and stacked at
390.

Filled card: --ce-surface, --ce-radius-card, --ce-elev-1, 24px padding.
Title = the setting name (--ce-font-serif 600 24px). A <dl> of the four
factor labels (body 16px --ce-ink-muted, verbatim server words) and values
(body 700 20px tabular). Actions row: secondary "Open this list", a toggle
button "Compare" (aria-pressed), quiet "Delete" in --ce-danger text.
Delete opens an inline confirm in the card (no modal): "Delete Balanced? It
cannot be brought back." with a destructive button "Delete it" and a quiet
"Keep it".

Empty slot: 2px dashed --ce-line-strong outline, no shadow,
../../assets/svg/empty-state.svg at 64px in --ce-line-strong, text "Slot 3
of 3 is free. Save the weights on screen to fill it."

Above the grid: h2 "Your team's saved settings", line "Your team may keep 3
for this event. You have 2.", a save form: label "Name these weights", text
field, secondary button "Save these weights", helper "Saves the 4 numbers
now on screen."

Interactions: typing "Balanced" and saving plays ce-card-save (the empty
slot becomes a filled card: scale 0.96→1, opacity 0→1, 220ms --ce-ease-out;
reduced motion: 150ms opacity). The button reads "Saving…" for 600ms first.
Hover on a filled card: translateY(-2px) and --ce-elev-2 over 160ms
(reduced: shadow only). Ticking Compare on two cards outlines both in 3px
--ce-primary with a "Comparing" chip and reveals a primary button under the
grid "Show them side by side"; the third card's Compare toggle then
disables with the helper "Two are chosen. Untick one to swap."

States for the switcher: Two saved + one free (default) · All three saved ·
None saved (three free slots and "Save two settings to see them side by
side.") · Saving · Two chosen for compare · Delete confirm · Refusal on save
(a calm notice above the form with the server's sentence, e.g. "Give your
settings a short name.", and the typed name kept in the field) · Keyboard
focus on "Open this list".

Never draw the weights as bars, rings or percentages.
```

## Review checklist

1. The slot count and "You have 2" read as data, not hard-coded copy.
2. Weights appear only as numbers the team chose.
3. Delete confirms inline; there is no modal.
4. A refused save keeps the typed name.
