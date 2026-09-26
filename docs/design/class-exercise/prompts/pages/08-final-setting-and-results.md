# Page 8 — final-setting pick, then locked or unlocked results

The team chooses one saved setting as its final one, then runs results once
the instructor has opened the event. Results show sign-ups and attendance,
and the room: "8 were already coming. Your invitations added 6. 46 seats
are still open."

- **Route:** `/exercise/events/:eventKey/results`. Code: `ExerciseResults.tsx`, `ResultPanels.tsx`, `ExerciseResultsChart.tsx`.
- **System:** [`DESIGN.md` 5.1, 6.13–6.17 and 7.8](../../DESIGN.md#78-results-round-one-exerciseeventseventkeyresults), motion `ce-seat-fill`, `ce-count-up`, `ce-unlock`.
- **Components:** [results reveal](../components/results-reveal.md), [empty and loading states](../components/empty-and-loading-states.md).
- **Assets:** [`invitation-envelope.svg`](../../assets/svg/invitation-envelope.svg) (locked), [`profile-card.svg`](../../assets/svg/profile-card.svg) (no saved setting).
- **Reference:** [`room/results-1280.png`](../../assets/mockups/room/results-1280.png), [`room/results-390.png`](../../assets/mockups/room/results-390.png), [`ledger/results-1280.png`](../../assets/mockups/ledger/results-1280.png), [`ledger/results-390.png`](../../assets/mockups/ledger/results-390.png).
- **Content:** round one results in [README section 7](../README.md#7-shared-fictional-data).
- **States:** no saved setting, locked, open and not chosen, open and chosen, running, first reveal, revisit, already run, rule not confirmed, unreachable.

## Google Stitch prompt

Screen A (locked):

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash ribbon. Title
"Results" (Archivo SemiExpanded 600, 48px) with a secondary button "Back to
your team's list" on the right; lead "What your team's list did, next to
what emailing all 300 would have done."

Section "Your team's final setting" (Source Serif 4 32px): three radio cards
in a row, each a saved setting with its four weights as small numbers:
"Major first" (selected: 3px CPP Green #005030 outline, filled radio),
"Interests first", "Balanced". Helper line: "Your team's invited list is
built from the setting you choose. Choose one to run results."

Below, a white card (14px corners, soft shadow) with, on the left, a line
envelope pictogram in CPP Green (96px), and on the right a pill chip with a
padlock "Results are closed", the sentence "The instructor has not opened
results for this event yet." in Figtree 20px #163229, and a secondary
button "Check again". The primary button "Run results for this event" is
shown disabled (45% opacity) under the card.
```

Screen B (results revealed):

```text
Same page after running. Replace the setting and lock sections with:

A two-column hero. Left: a white card "The room" with a "Front of the room"
bar and a 6x10 seating chart of small rounded squares: 8 filled warm brown
#8C6D62 (already coming), 6 filled CPP Green #005030 with a tiny white
check (your invitations), 46 outlined in #8F7A70 (still open); legend
"Already coming (8) · Your invitations (6) · Still open (46)". Right: a
three-line headline in Source Serif 4 semibold 40px with green numerals:
"8 were already coming. / Your invitations added 6. / 46 seats are still
open." Under it a ruled figures band (thin vertical rules, no cards): 60
"Seats in the room", 8 "Already coming", 46 "Still open", numerals in
Archivo bold 64px.

Then section "What happened for Northline Analytics": a grouped bar chart
with two groups, "Your team's list" (invited 30, signed up 6, attended 4)
and "If you emailed everyone" (invited 300, signed up 41, attended 27).
Bars: invited = pale green #D9EADF with a CPP Green outline; signed up =
CPP Gold #FFB81C with diagonal hatching and a #7A5200 outline; attended =
solid CPP Green. Every bar has its number on top. A text link "Show these
counts as a table".

Then section "The people on your team's list": three columns of name chips
under "Invited (30)", "Signed up (6)", "Attended (4)" — Signed up: Daniel
Okafor, Alexis Rivera, Marcus Chen, Grace Park, Brandon Cole, Emily Wang;
Attended: Daniel Okafor, Marcus Chen, Grace Park, Emily Wang; Invited shows
the first 8 then "and 22 more". A quiet line "Contacting all 300 is shown
as counts only."

Last: section "Ask the people your team invited" with a secondary button
"Go to asking for more". No confetti, no trophies, no percentages or rates.
```

**390 follow-up:** "At 390px: final-setting cards stack; locked card
stacks the envelope above the text. After the run: the room full width,
headline 28px, figures band three narrow columns, chart as horizontal bars,
name chips wrap."

## Claude Design prompt

```text
Build /exercise/events/northline/results for the Smart Match class exercise
with the preamble tokens, reusing the results-reveal and state components.

Page: h1 "Results"; aside secondary "Back to your team's list"; lead "What
your team's list did, next to what emailing all 300 would have done."

Before a run:
1. h2 "Your team's final setting": radio cards (role radiogroup) for the
   saved settings — name (serif 24px) + weights line. Nothing preselected.
   Helper (id used by the run button's aria-describedby): "Your team's
   invited list is built from the setting you choose. Choose one to run
   results."
2. Lock panel: locked → envelope SVG 96px, chip Lock "Results are closed",
   the server sentence "The instructor has not opened results for this
   event yet.", secondary "Check again" (ce-unlock plays if the check finds
   it open). Open → chip LockOpen "Results are open".
3. Primary "Run results for this event": disabled until a setting is chosen
   and results are open; "Running…" while pending.
4. Line "A team runs results once per event." under the button.

After a run: the results-reveal (seats 60, taken 8, added 6, open 46; the
reveal plays only on the first render after the run), then h2 "What
happened for Northline Analytics" with the Recharts grouped bars restyled
(series colours from DESIGN.md 3.3, hatch on signed up, direct value
labels 26px, no animation on bars), a <details> "Show these counts as a
table" containing the real <table>, then h2 "The people on your team's
list" with three chip lists (headings with counts; names from the ranked
list; unknown numbers shown as "Profile 212"), the line "Contacting all 300
is shown as counts only.", then h2 "Ask the people your team invited" and
a secondary link "Go to asking for more".

States for the switcher: No saved setting (profile-card.svg + "Your team has
not saved any settings for this event yet. Save one on your team's list
first, then choose it here as your final setting.") · Locked · Open, nothing
chosen · Open, "Major first" chosen · Running · First reveal · Revisit ·
Already run (calm notice "This team has already run results for this
event." with the results below) · Rule not confirmed (calm notice with the
server's sentence; illustrative "The course owner has not confirmed the
results rule yet.") · Unreachable · 390.

Never show a sign-up rate, conversion or percentage. Counts only.
```

## Review checklist

1. The run button explains why it is disabled.
2. Locked is calm (no red); already-run is a state, not an error.
3. Seat numbers come from the server; the sentence uses the exact pattern.
4. Chart and seats carry non-colour cues and a table fallback.
