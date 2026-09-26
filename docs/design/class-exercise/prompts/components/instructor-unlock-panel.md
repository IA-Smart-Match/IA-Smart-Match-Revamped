# Component — instructor unlock panel

The instructor opens results for one event at a time. Until then, a team's
"Run results" is refused with a calm sentence. Opening is one-way for the
session, so the control is a deliberate button, not a toggle.

- **System:** [`DESIGN.md` 6.24](../../DESIGN.md#624-instructor-components), motion `ce-unlock`, `ce-notice-in`.
- **Content:** data file "Ann's file, 25 September". Events: "Northline Analytics" (open), "Harbor Consumer Brands" (closed).
- **States:** loading, both closed, one open, opening, refusal, no events in file, session expired.

## Google Stitch prompt

```text
An instructor panel for a desktop web app on an eggwhite #F8F6F1 page. A
white card (760px, 14px corners, soft shadow, 24px padding) titled "Open
results for an event" (Source Serif 4, 32px). Under the title in #59665F:
"For Ann's file, 25 September. Teams can run results only for an event
that is open."

Two rows separated by a 1px #D9CBC4 divider, each 72px tall:
Row 1: event name "Northline Analytics" in Figtree 20px semibold; a pill
chip "Results are open" with an open-padlock icon (fill #E8F2D8, text
#163229); no button.
Row 2: "Harbor Consumer Brands"; a pill chip "Results are closed" with a
padlock icon (fill #F2EEE8, text #163229); on the right a secondary button
"Open results" (white, 2px #8F7A70 outline, 10px corners).

Under the rows a quiet text button "Check again" with a refresh icon.
No toggle switches. No red.
```

**390 follow-up:** "At 358px, put the chip under the event name and make
'Open results' full width under it."

## Claude Design prompt

```text
Build the instructor unlock panel for the Smart Match class exercise with
the preamble tokens. It lives on /exercise/instructor, first in the left
column after sign-in.

Card: h2 "Open results for an event", a meta line "For Ann's file, 25
September. Teams can run results only for an event that is open." Then a
<ul> of events (server order). Each row: event name (body 600 20px), a
status chip, and an action.
- Closed: chip Lucide Lock + "Results are closed" on --ce-surface-sunk;
  secondary button "Open results".
- Open: chip Lucide LockOpen + "Results are open" on --ce-avocado-tint;
  no button (it cannot be closed from here).

Clicking "Open results" opens an inline confirm in that row: "Open results
for Harbor Consumer Brands? Every team can then run results once for this
event." with primary "Open results now" and quiet "Not yet". Confirm →
"Opening…" (aria-disabled) for 600ms → ce-unlock: the lock icon's shackle
lifts 4px and swaps to LockOpen, the chip crossfades from sunk to
avocado-tint over 300ms --ce-ease-out, the button leaves. A status line
(role="status") under the list: "Results are open for Harbor Consumer
Brands." Reduced motion: icon swap and colour change with no movement.

Below the list: quiet button "Check again" (Lucide RotateCw).

States for the switcher: Loading (two row skeletons) · Both closed · One
open (default) · Confirm pending · Opening · Refusal (calm notice with the
server's sentence, row unchanged, illustrative text "That event is not in
the current data file.") · No events ("Ann's file, 25 September has no
events for the teams to run." and "Check again") · Session expired (notice
"Enter the passcode again to continue." and the panel replaced by the
passcode form) · 390 frame.
```

## Review checklist

1. Opening needs a confirm; there is no toggle that looks reversible.
2. Locked and open differ by icon and words, not colour alone.
3. Refusals are calm cards, never red.
