# Page 3 — event picker

Two events are rounds a team builds a list for; ten past events exist only
as attendance history. Both kinds are shown, named for what they are.

- **Route:** `/exercise/events`. Code: `ExerciseEventPicker.tsx`.
- **System:** [`DESIGN.md` 6.5 and 7.3](../../DESIGN.md#73-event-picker-exerciseevents), motion `ce-lift`, `ce-fade-rise`.
- **Asset:** round seal geometry from [`round-journey.svg`](../../assets/svg/round-journey.svg) (draw the circles in-card; do not place the SVG beside the heading).
- **Content:** the two rounds and ten past events in [README section 7](../README.md#7-shared-fictional-data).
- **States:** ready, loading, no exercise events, no past events, refused (no workspace), unreachable.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page with the gold-wash fictional-data
ribbon at the top. A header row: page title "Choose an event" (Archivo
SemiExpanded 600, 48px, #163229) and on the right, quiet text "Team 4" with
a small people icon.

Lead line, Figtree 22px #59665F: "Build your team's list for one of the two
events in the exercise."

Section "The two events you can work on" (Source Serif 4 32px). Two wide
white cards stacked, full width, 14px corners, soft shadow, 24px padding,
each clickable with a chevron on the right:
Card 1: a 48px round seal with "1" (outline CPP Green #005030), the event
name "Northline Analytics" in Source Serif 4 32px, then two lines in
Figtree 20px #163229: "Topics: Technology / information systems; Marketing
/ advertising / public relations" and "Aimed at: Computer Information
Systems; International Business & Marketing".
Card 2: seal "2" filled CPP Green with a white numeral, "Harbor Consumer
Brands", "Topics: Retail / consumer goods; Marketing / advertising / public
relations", "Aimed at: International Business & Marketing; Management &
Human Resources".

Section "Past events, for attendance history" (Source Serif 4 32px) with a
line in #59665F: "These are not events you build a list for. They are what
“went to similar events before” reads." Then a quiet two-column list of ten
names with a small calendar icon each: Fall Career Fair; Resume Lab
Workshop; Consulting Industry Panel; Accounting Firms Night; Startup Pitch
Night; Supply Chain Info Session; Data Analytics Workshop; Nonprofit
Networking Mixer; Retail Leadership Panel; Case Competition Kickoff.
```

**390 follow-up:** "At 390px: cards stack full width, seal 40px, event name
26px; the past events collapse behind a disclosure 'Show the 10 past
events'."

## Claude Design prompt

```text
Build /exercise/events for the Smart Match class exercise with the preamble
tokens.

- h1 "Choose an event"; aside "Team 4" (Lucide Users 20px, body 18px
  --ce-ink-muted); lead "Build your team's list for one of the two events in
  the exercise."
- h2 "The two events you can work on", then a <ul> of two round cards, each
  a single <a> (whole card clickable): seal (48px circle; round 1 outline
  2px --ce-primary with --ce-primary numeral, round 2 filled --ce-primary
  with --ce-on-primary numeral, --ce-font-display 700 22px), event name
  (h3, --ce-font-serif 600 32px), "Topics: …" and "Aimed at: …" lines (body
  20px), Lucide ChevronRight at the right. Round order comes from
  `sequence`, never from the name.
- h2 "Past events, for attendance history", helper line, and a two-column
  <ul> (Lucide CalendarDays 20px + name, body 18px). Not links.

Motion: hover on a round card = ce-lift and the chevron translates 4px
right (160ms). Page content enters with ce-fade-rise, the two cards 60ms
apart. Reduced motion: shadow change only; 150ms opacity.

States for the switcher: Ready · Loading (two card skeletons + five line
skeletons; hidden status "Loading the events…") · No exercise events (calm
notice "This data file has no exercise events in it yet. The instructor can
upload a file that does.") · No past events ("This data file carries no past
events.") · No workspace (calm notice with the server sentence and a
secondary link "Enter your team number") · Unreachable (problem notice +
"Try again") · 390 (stacked; past events inside a <details> "Show the 10
past events").
```

## Review checklist

1. No eyebrow "Round 1" above the event name; the round is a seal inside the card.
2. Past events are clearly not choosable.
3. Topic and major strings render as sent.
