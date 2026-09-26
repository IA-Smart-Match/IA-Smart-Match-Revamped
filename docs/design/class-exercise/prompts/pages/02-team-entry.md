# Page 2 — team entry

A team enters its number (1–6). No name, no password, no account. The
numbers are a scope constant from the server.

- **Route:** `/exercise` (lower zone). Code: `ExerciseEntry.tsx` `EntryForm`.
- **System:** [`DESIGN.md` 6.4 and 7.2](../../DESIGN.md#72-team-entry-exercise-lower-zone), motion `ce-press`, `ce-lift`.
- **Asset:** [`team-badge.svg`](../../assets/svg/team-badge.svg) (32px, on the "already in team" line).
- **Content:** tiles 1–6; Team 4 selected; "This browser is already in team 4, working in Ann's file, 25 September."
- **States:** nothing selected, one selected, keyboard focus, submitting, returning browser, refusal, unreachable.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, continuing below the opening
hero. Section title "Which team are you?" (Source Serif 4, 32px, #163229)
and a line in Figtree 20px #59665F: "Pick your team's number. Your team's
saved work is kept under that number."

A row of six square tiles, 112x112px, 16px apart, like numbered place
cards: white, 14px corners, soft shadow, a big numeral in Archivo
SemiExpanded bold 44px #163229, numbers 1 to 6. Tile 4 is selected: filled
CPP Green #005030 with a white numeral and a small CPP Gold #FFB81C corner
notch at top-right.

Under the tiles, a line with a small shield-and-check pictogram in CPP
Green: "This browser is already in team 4, working in Ann's file, 25
September."

A primary button, CPP Green #005030, white text, 56px tall, 10px corners:
"Open this team's work".

At the very bottom, the license line in Figtree 18px #163229 on a #F2EEE8
panel: "For California State Polytechnic University, Pomona — College of
Business Administration instructional use only. All student profiles are
fictional."
```

**390 follow-up:** "At 390px: tiles 96x96 in a 3x2 grid, the button full
width and pinned to the bottom of the screen above the safe area, the
license panel above the button."

## Claude Design prompt

```text
Build the team-entry zone of /exercise for the Smart Match class exercise
with the preamble tokens. It sits under the opening hero (page 1).

Form: <fieldset> with <legend> rendered as the h2 "Which team are you?" and
the helper "Pick your team's number. Your team's saved work is kept under
that number." Six radio inputs, visually hidden, each inside a label styled
as a 112px tile (--ce-surface, --ce-elev-1, --ce-radius-card, numeral
--ce-font-display 700 44px). aria-label on each input: "Team 4" (not "4 Team
4"). Arrow keys move the selection (native radio behaviour).

Tile states: hover = ce-lift and numeral --ce-primary; focus-within = focus
ring on the tile; selected = --ce-primary fill, --ce-on-primary numeral,
8px --ce-gold triangle notch top-right; pressed = ce-press (scale 0.98,
100ms).

Returning browser line (only when the server reports a workspace):
../../assets/svg/team-badge.svg 32px in --ce-primary + "This browser is
already in team 4, working in Ann's file, 25 September." with the file label
in 600 weight.

Primary button "Open this team's work", disabled until a tile is chosen
(helper via aria-describedby: "Pick a team number first."). Pending:
"Opening your team's work…" with a 16px spinner, tiles at 60% opacity.

License panel at the foot of the page (same as page 1).

States for the switcher: Nothing selected · Team 4 selected · Keyboard focus
on tile 2 · Submitting · Returning browser (tile 4 preselected + line) ·
Refused (calm notice with the server sentence under the tiles, selection
kept) · Unreachable (problem notice + "Try again") · 390 (3x2 grid, sticky
full-width button over the safe area, --ce-elev-3).
```

## Review checklist

1. There is no name, email or password field.
2. The selected tile differs by fill and numeral colour, plus the notch.
3. The license line stays visible at 390.
