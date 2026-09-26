# Component — results reveal and seat figures

The flow's one authored moment. The room has 60 seats; 8 were taken before
the team did anything; the team's invitations added 6; 46 are still open.
The seats fill in that order, once, and then the screen rests.

- **System:** [`DESIGN.md` 5.1 and 6.15](../../DESIGN.md#51-the-focal-moment-ce-seat-fill), motion `ce-seat-fill`, `ce-count-up`.
- **Library:** `motion` 12.23 (`animate()` for counters, variants with `staggerChildren` for seats).
- **Reference:** [`room/results-1280.png`](../../assets/mockups/room/results-1280.png) (seat grid beside a large seat sentence), [`ledger/results-1280.png`](../../assets/mockups/ledger/results-1280.png) (ruled figures band instead of cards), and both 390 versions: [`room/results-390.png`](../../assets/mockups/room/results-390.png), [`ledger/results-390.png`](../../assets/mockups/ledger/results-390.png).
- **Content:** seats 60, already coming 8, added 6 (the server's `team.signed_up_count`), still open 46.
- **States:** first reveal (animated), revisit (final state), reduced motion, one seat singulars, a room that is not 60, nothing added.

Seat semantics (differs from the Room mock-up on purpose): a seat is a
sign-up, not an invitation. Invited-but-not-coming people are not seats.
Attendance is shown in the chart below, not in the room.

## Google Stitch prompt

```text
A results hero section for a desktop web app on an eggwhite #F8F6F1 page,
1152px wide, two columns.

Left column (560px): a white card, 14px corners, soft shadow, titled "The
room" (Source Serif 4 24px). A thin #F2EEE8 bar labelled "Front of the
room" in small #59665F text at the top. Under it a seating chart of 60
small rounded squares (26px, 4px corners, 8px gaps) in 6 rows of 10:
- 8 squares filled warm brown #8C6D62 ("already coming"), placed in the
  front row, left side.
- 6 squares filled CPP Green #005030 with a tiny white check stroke inside
  ("your invitations"), next to them.
- 46 squares as outlines only, 2px #8F7A70 ("still open").
A legend below with the three swatches and labels "Already coming (8)",
"Your invitations (6)", "Still open (46)".

Right column: a large three-line headline in Source Serif 4 semibold 40px
#163229, with the numbers in CPP Green:
"8 were already coming.
Your invitations added 6.
46 seats are still open."

Under it a ruled figures band (not cards): three columns separated by thin
vertical #8F7A70 rules, each a big Archivo SemiExpanded bold 64px number
over a Figtree 18px label: "60 Seats in the room", "8 Already coming", "46
Still open".

No confetti, no trophies, no percentages, no "great job".
```

**390 follow-up:** "Stack for a 358px phone: the room card full width with
seats at 26px (10 per row still fits), then the three-line headline at
28px, then the figures band as three narrow columns with 40px numbers."

## Claude Design prompt

```text
Build the results reveal for the Smart Match class exercise with the
preamble tokens. Props (fake them in the prototype): event_seats=60,
existing_signups=8, team_signed_up_count=6, seats_empty=46. Never compute
one from the others in the UI; all four come from the server.

Layout 1280: two columns 6/6. Left: card "The room" containing a "Front of
the room" bar (--ce-surface-sunk, 8px tall, caption --ce-type-meta) and a
seat grid: event_seats squares, 10 per row, 26px, --ce-radius-seat 4px, 8px
gap. Seat types: taken = --ce-seat-taken fill; yours = --ce-primary fill
with a 2px --ce-on-primary check path inside; open = transparent with 2px
--ce-line-strong outline. Fill order: taken seats first (front row from the
left), then yours, then open. The grid is aria-hidden="true". Legend under
it with the three swatches and counts.
Right: the headline as three lines, --ce-font-serif 600 40/48, numerals in
--ce-primary: "8 were already coming." / "Your invitations added 6." / "46
seats are still open." Singulars: "1 was already coming.", "1 seat is still
open." This block is the aria-live="polite" region. Under it a ruled
figures band: three columns divided by 1px --ce-line-strong, numerals
--ce-font-display 700 72px tabular, labels body 18px: "Seats in the room",
"Already coming", "Still open".

Motion — ce-seat-fill, first render after a run only:
0–240ms grid fades in, all seats open outlines.
240–600ms 8 taken seats fill, 12ms stagger; line 1 fades in.
700–1300ms 6 yours fill, 60ms stagger, each scale 1→1.08→1 (--ce-ease-out);
line 2 fades in.
1400–1800ms open seats' outlines brighten once; line 3 fades in; figures
count up from 0 over 700ms (ce-count-up, tabular so nothing shifts).
Add a small quiet "Skip" text button top-right of the card during the
sequence that jumps to the final state. With prefers-reduced-motion: final
state at once, text fades in 150ms, no count-up, no Skip.

States for the switcher: First reveal (plays) · Revisit (final state, no
animation) · Reduced motion · Singulars (seats 60, taken 1, yours 1, open
58) · Nothing added (yours 0; line 2 reads "Your invitations added 0.") ·
Room of 45 (rows of 10, last row of 5) · 390 frame.

No confetti, sound, trophy, rating or percentage. The screen is evidence for
a discussion, not a win.
```

## Review checklist

1. The four numbers are server values; nothing is subtracted in the UI.
2. Seat types differ by fill, mark and outline, and the legend names them.
3. The seat grid is hidden from screen readers; the sentences are announced once.
4. Revisits show the final state without replaying the animation.
