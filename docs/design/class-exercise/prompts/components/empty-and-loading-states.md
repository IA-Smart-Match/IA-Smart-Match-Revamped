# Component — empty, loading and refusal states

The exercise's commonest screens are "not yet" screens: results locked,
nothing saved, the list loading, the connection dropped. They must look as
considered as the reveal.

- **System:** [`DESIGN.md` 6.20 and 6.21](../../DESIGN.md#620-notice), motion `ce-skeleton`, `ce-notice-in`.
- **Assets:** [`empty-state.svg`](../../assets/svg/empty-state.svg), [`invitation-envelope.svg`](../../assets/svg/invitation-envelope.svg), [`profile-card.svg`](../../assets/svg/profile-card.svg).
- **Content:** real server sentences where they exist (listed below).
- **States:** a board of eight panels, one per state.

Server sentences used here (verbatim from the API):

- "The instructor has not opened results for this event yet."
- "This team has already run results for this event."
- "Choose one of your saved settings as your final setting before running results."
- "The instructor has not loaded the student body yet."
- "Your team has already asked the people it invited."

## Google Stitch prompt

```text
A state board for a desktop web app on an eggwhite #F8F6F1 page: a 2x4 grid
of white cards (560px wide each, 14px corners, soft shadow, 24px padding),
each labelled above in small #59665F text with the state name.

1 "Loading the list": skeleton blocks in #F2EEE8 — a title bar, then 5 rows
each with a small square (rank), a long bar (name) and a shorter bar
(reason). Caption under it: "Loading the list…".
2 "Results locked": a line-drawn envelope pictogram in CPP Green #005030
(96px), a pill chip with a padlock "Results are closed", the sentence "The
instructor has not opened results for this event yet." in 20px #163229,
and a secondary button "Check again".
3 "Nothing saved yet": a dashed rounded rectangle with a plus, in #8F7A70,
and "Your team has not saved any settings for this event yet. Save two to
see them side by side."
4 "Choose a final setting first": an ID-card pictogram in #005030 and
"Choose one of your saved settings as your final setting before running
results."
5 "Already run": an info icon in #005030 and "This team has already run
results for this event."
6 "No data file": "The instructor has not loaded the student body yet."
7 "Connection problem": the only card with a 2px red #BA1A1A outline, a
warning-triangle icon in #BA1A1A, "The exercise could not be reached. Check
the connection and try again." and a primary CPP Green button "Try again".
8 "Empty list": the dashed rectangle and "Nobody is on this list. Nobody in
this data file can be ranked for this event with these weights."

All text sentence case. Only card 7 uses red. No sad faces, no emoji.
```

**390 follow-up:** "Show the same eight cards stacked at 358px width."

## Claude Design prompt

```text
Build a state board for the Smart Match class exercise with the preamble
tokens: a page of eight panels, each the real component in that state.

Shared notice component:
- Calm: --ce-surface, --ce-elev-1, --ce-radius-card, 24px padding, Lucide
  Info 24px in --ce-primary, the sentence at body 20/30, optional one
  action. role="status". Enters with ce-notice-in (opacity + y 4→0, 200ms
  --ce-ease-out; reduced: opacity 150ms).
- Problem: same card with a 2px --ce-danger outline, Lucide TriangleAlert
  in --ce-danger, and a primary "Try again". Only for transport failures.
- No left-border stripes, no red for refusals, no toasts for refusals.

Panels:
1 Loading the list — skeleton matching the ranked table (rank square 28px,
  name bar 40%, reason bar 70%, three short cells), ce-skeleton opacity
  breathing 0.55↔1 over 1.6s (reduced: static 0.75), and a visually hidden
  role="status" "Loading the list…".
2 Results locked — ../../assets/svg/invitation-envelope.svg 96px in
  --ce-primary, chip Lucide Lock "Results are closed", sentence "The
  instructor has not opened results for this event yet.", secondary "Check
  again".
3 Nothing saved yet — ../../assets/svg/empty-state.svg 96px in
  --ce-line-strong, "Your team has not saved any settings for this event
  yet. Save two to see them side by side."
4 Choose a final setting first — ../../assets/svg/profile-card.svg 80px,
  "Choose one of your saved settings as your final setting before running
  results." with a quiet link "Go to your team's list".
5 Already run — calm notice "This team has already run results for this
  event."
6 No data file — calm notice "The instructor has not loaded the student
  body yet."
7 Connection problem — problem notice "The exercise could not be reached.
  Check the connection and try again." + primary "Try again" that shows
  "Trying again…" for 800ms.
8 Empty list — empty-state.svg and "Nobody is on this list. Nobody in this
  data file can be ranked for this event with these weights."

Render at 1280 (2 columns) and 390 (1 column). A spot SVG appears at most
once per panel and never beside a heading.
```

## Review checklist

1. Only the transport failure is red.
2. Server sentences are verbatim with full stops.
3. Every skeleton has a spoken loading status.
4. No spinner sits in the middle of content for more than 300ms.
