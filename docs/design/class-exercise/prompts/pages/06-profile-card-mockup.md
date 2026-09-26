# Page 6 — profile-card mock-up

One screen the instructor shows so the class can see what a profile would
be asked before arguing about how to ask. It is a mock-up and says so:
nothing is stored and every button is inert.

- **Route:** `/exercise/profile-card`. Code: `ProfileCardMockup.tsx`.
- **System:** [`DESIGN.md` 6.22 and 7.6](../../DESIGN.md#76-profile-card-mock-up-exerciseprofile-card).
- **Asset:** [`profile-card.svg`](../../assets/svg/profile-card.svg) (caption column only, 64px).
- **Content:** "Two quick questions"; confirm major; two questions (interests, career goal). OQ-CE-11: only interests and career goal are asked; major is confirmed, not asked; year and past events are not asked.
- **States:** default (inert), keyboard focus on an inert button, 390.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash ribbon on top reading, after a bold "Fictional data —",
"This is a mock-up of the card, shown to the class. It asks nobody
anything, keeps no answers, and is not connected to any list."

Left caption column (360px): title "What a profile would be asked"
(Archivo SemiExpanded 600, 40px) and a paragraph in Figtree 20px #59665F:
"Major and year are already on file, and past events are recorded when
someone attends. So the card asks only two things, and asks the person to
confirm their major." A small ID-card pictogram in CPP Green above the
title.

Centre: a phone-sized card, 360px wide, white, 18px corners, a deeper soft
shadow, sitting on the page like a card on a desk. In its top-right corner a
small pill chip "Mock-up only" (#F2EEE8 fill, #163229 text). Inside:
- Title "Two quick questions" (Source Serif 4 28px) and the line "Answering
  these would let us suggest events worth your evening." (#59665F).
- A section "Confirm your major": helper "This is the major already on file
  for you. Year and the events you have been to are on file too, so nothing
  else here asks for them." A dashed-outline box reading "Your major, as it
  is on file". A disabled grey button "Confirm — mock-up only, this button
  does nothing".
- Question 1 "What topics are you interested in?" with helper "Pick as many
  as you like, or add your own." and a dashed empty answer line.
- Question 2 "What kind of work do you want to end up doing?" with helper
  "A sentence is plenty." and a dashed empty answer line.
- A disabled grey button "Mock-up only — this button does nothing".

No real form fields, no names, no percentages.
```

**390 follow-up:** "At 390px: the caption above, the card full width (358px)
below it."

## Claude Design prompt

```text
Build /exercise/profile-card for the Smart Match class exercise with the
preamble tokens. This page uses the ribbon with the "Fictional data —" prefix and a different sentence: "This
is a mock-up of the card, shown to the class. It asks nobody anything,
keeps no answers, and is not connected to any list."

1280: grid 360px | 1fr. Left caption: ../../assets/svg/profile-card.svg
64px in --ce-primary (decorative), h1 "What a profile would be asked"
(--ce-font-display 600 40px), paragraph (body 20px --ce-ink-muted) as in the
Stitch prompt. Right: centred "phone card" 360px wide, --ce-surface,
--ce-radius-sheet (18px), --ce-elev-3, 24px padding, with a chip "Mock-up
only" top-right (--ce-surface-sunk, pill).

Card contents (use the exact strings):
h2 "Two quick questions" (serif 28px) + "Answering these would let us
suggest events worth your evening."
Section "Confirm your major" + helper + a dashed 2px --ce-line-strong box
"Your major, as it is on file" (aria-hidden) + disabled button "Confirm —
mock-up only, this button does nothing".
<ol> of two questions: "What topics are you interested in?" / "Pick as many
as you like, or add your own." and "What kind of work do you want to end up
doing?" / "A sentence is plenty." Each with a dashed answer line
(aria-hidden), not an input.
Final disabled button "Mock-up only — this button does nothing".

Inert buttons: --ce-surface-sunk fill, --ce-ink-muted text, 2px
--ce-line outline, cursor not-allowed, disabled + aria-disabled. They keep a
visible focus ring if focused programmatically.

No motion on this page beyond ce-fade-rise on first load (reduced: none).
States for the switcher: Default · 390.
```

## Review checklist

1. Only two questions; major is confirmed, not asked; no year or past-events question.
2. "Mock-up only" is visible on the card and on both buttons.
3. There are no real inputs.
