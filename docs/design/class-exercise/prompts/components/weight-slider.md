# Component — weight slider

The four controls a team uses to say how much each thing counts. The lesson
turns on them, so they are the most-touched element in the flow.

- **System:** [`DESIGN.md` 6.6](../../DESIGN.md#66-weight-slider-see-prompt), motion `ce-slider-settle`, `ce-list-rebuilding`.
- **Library:** `@radix-ui/react-slider` 1.2.3 (installed; not yet used by `WeightsControls.tsx`, which ships text boxes today).
- **Reference:** [`room/list-1280.png`](../../assets/mockups/room/list-1280.png) (left card: slider layout and value pill), [`room/list-390.png`](../../assets/mockups/room/list-390.png).
- **Content:** labels are the server's `factor_labels`, verbatim: "same major", "said they are interested in this topic", "career goal fits this event", "went to similar events before". Values 0.40, 0.25, 0.25, 0.10.
- **States:** default, hover, focus (keyboard), dragging, committed-and-rebuilding, invalid field entry, server refusal, disabled.

Behaviour the mock-up must show: the numeric field beside each slider holds
the exact value; dragging updates the field live; the list is rebuilt only
when the thumb is released, Enter is pressed, or the field loses focus.

## Google Stitch prompt

```text
A single white card titled "How much each thing counts" (Source Serif 4,
32px, #163229), 360px wide, for a desktop web app. Inside, four stacked
weight controls separated by 24px:

Each control: a label on top in Figtree 18px semibold #163229 ("same major",
"said they are interested in this topic", "career goal fits this event",
"went to similar events before" — lowercase exactly as written). Under it a
horizontal slider and, to its right, an 88px-wide rounded input box showing
the value in tabular figures ("0.40", "0.25", "0.25", "0.10").

Slider look: 6px track in #F2EEE8 with a 2px #8F7A70 outline; the filled
part from the left is CPP Green #005030; a 28px white round thumb with a 2px
#005030 ring and a soft shadow. Slider range 0 to 1.

Under the four controls, one line in #59665F 16px: "The list is rebuilt when
you let go of a slider or press Enter."

Show the second control ("said they are interested in this topic") in a
dragging state: thumb 32px, a small dark-green value bubble "0.25" above the
thumb. Show the fourth control's input with a red outline and the message
"\"1,5\" is not a plain number. Use digits and one decimal point, like 0.5."
in #BA1A1A under it.

Card: white, 14px corners, soft shadow, no border, 24px padding, on an
eggwhite #F8F6F1 page. No percentages anywhere. No icons beside the title.
```

**390 follow-up:** "Make this a 358px-wide mobile card. Keep the label above
each slider; put the value box on the same line as the label, right-aligned.
Add a compact sticky bar at the top of the screen reading 'Weights 0.40 ·
0.25 · 0.25 · 0.10' with a text button 'Edit weights'."

## Claude Design prompt

```text
Build the weight-slider component for the Smart Match class exercise, as an
interactive prototype using the preamble's tokens. Use Radix Slider
semantics (role="slider", aria-valuemin 0, aria-valuemax 1, aria-valuenow,
aria-valuetext "0.40"). Render four instances inside a card titled "How much
each thing counts" (h2, --ce-font-serif).

Anatomy per instance:
- <label> in body 600 18px with the server's words, verbatim and lowercase:
  "same major" / "said they are interested in this topic" / "career goal
  fits this event" / "went to similar events before".
- Track: 6px, fill --ce-surface-sunk, 2px --ce-line-strong outline; range
  fill --ce-primary. Thumb: 28px drawn, 44px hit area, white, 2px
  --ce-primary ring, --ce-elev-1.
- Paired text field, 88px, inputmode="decimal", tabular numerals, value to
  two decimals. Typing is free; commit on Enter or blur. Reject anything
  that is not a plain decimal with the message: "\"1,5\" is not a plain
  number. Use digits and one decimal point, like 0.5." (role="alert", under
  the field, --ce-danger text, field outline --ce-danger).
- Slider step 0.05; arrow keys ±0.05, PageUp/PageDown ±0.25, Home/End.

Starting values: 0.40, 0.25, 0.25, 0.10.

Behaviour: dragging updates the field live but does not "commit". Commit
happens on pointerup, Enter, or field blur. On commit, show a 16px spinner
next to that label and a status line under the card "Rebuilding the list…"
(aria-live polite) for 700ms, then clear. Controls stay usable while
rebuilding. If the user commits another slider during that time, queue it
and show "1 change waiting" in the status line.

States for the switcher: Default · Hover (thumb 32px, --ce-elev-2) ·
Keyboard focus (focus ring on thumb, value in field bolds) · Dragging (value
bubble above thumb in --ce-primary with white text) · Rebuilding · Invalid
field · Server refusal (a calm notice above the card with the sentence
"Those weights were not accepted." followed by the server's reason (render it verbatim; illustrative here) and the fields reverting to the last
accepted values) · Disabled (45% opacity; note in the prototype that the
real screen never disables them during a refetch).

Motion: ce-slider-settle — clicking the track glides the thumb 180ms with
--ce-ease-out; reduced motion jumps. No other animation.

Frames: 1280 (card 360px wide in a left column) and 390 (card full width,
value field on the label's line). On 390 also show the sticky compact bar
"Weights 0.40 · 0.25 · 0.25 · 0.10  Edit weights" at --ce-elev-3.

Do not show any percentage, "total must equal 1", or a sum. Weights are
independent numbers the team chose.
```

## Review checklist

1. Labels are the four server phrases, lowercase, verbatim.
2. No sum, no percentage, no "match strength" anywhere near the sliders.
3. Keyboard focus is visible on the thumb; the field is reachable by Tab.
4. The list is not described as updating on every drag tick.
