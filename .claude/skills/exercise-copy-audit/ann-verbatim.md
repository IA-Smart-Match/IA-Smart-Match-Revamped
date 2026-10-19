# Dr. Wang's verbatim wording

Source: Ann's Word feedback of 2026-10-16 (`fb.docx`), "Event page", "Make round
one and round two clearly different" and "Smaller items". Her words are final
(owner rule): where she gave exact text, the screen uses it character for
character. Curly quotes and apostrophes are written as plain `'` here; the
checker treats `&apos;` and `\'` in source as `'`.

`node extract-copy.mjs --verbatim` checks that every line shaped `- "..."`
below appears in the exercise sources. Text in `{braces}` on screen is a live
number, so only the fixed parts are listed.

## Event page: saved settings (Ann's "Wording for item 1", all 9 rows)

| Part of the screen | Now (before) | Ann's text |
|---|---|---|
| Heading | Your team's saved settings | Save your weight settings |
| Line under heading | Your team may keep 3 for this event. You have 0. | Like a set of weights? Save it so you can compare it with others later. You can save up to 3 for this event. Saved so far: 0. |
| Box label | Name these weights | Give this setting a name |
| Grey hint in the box | (blank) | e.g., Major first, Interest first, Balanced |
| Note under the box | Saves the 4 numbers now on screen. | Saves the four slider numbers at the top of this page under this name. |
| Button | Save these weights | Save this setting |
| Empty slot | Slot 1 of 3 is free. Save the weights on screen to fill it. | Empty. Save a setting to fill this slot. |
| Line under slots | Save two settings to see them side by side. | Save two settings to compare the two lists side by side. |
| Bottom button | Go to results for this event | Choose one setting and see results (+ "You get one results run for this event.") |

- "Save your weight settings"
- "Like a set of weights? Save it so you can compare it with others later. You can save up to "
- "Saved so far: "
- "Give this setting a name"
- "e.g., Major first, Interest first, Balanced"
- "Saves the four slider numbers at the top of this page under this name."
- "Save this setting"
- "Empty. Save a setting to fill this slot."
- "Save two settings to compare the two lists side by side."
- "Choose one setting and see results"
- "You get one results run for this event."

## Event page: list notes

Ann gave these as examples ("e.g.", "such as"); the shape is fixed, the names
and numbers are live.

- "This setting is the same as "
- " of your list matched what you asked for. The other "
- " were added to fill the list."
- "same major; nothing else on file"

(The reason line is built in `python/.../exercise/reasons.py` as a lowercase phrase and
rendered "Same major; nothing else on file." The checker searches that package too.)

## Rounds

- "Round 1 of 2: Northline"
- "Round 2 of 2: Harbor"
- "Round 1 done. Next: Round 2, Harbor. Start by choosing how to ask students for more information."

## Owned by other tracks (listed for the audit; not checked by --verbatim)

Results screen (Track B), from Ann's results table. Prefixed `*` so the checker skips them.

* "Your list brought 7 extra sign-ups; 4 of them came."
* "11 people on your list signed up. 8 of them would have signed up from the mass email anyway, so your list added 3."
* "Light bar: mass email alone. Dark bar: mass email plus your CBACH emails."
* "Your instructor has not opened results yet. You can still pick your setting and review its list. Press Check again once your instructor says results are open."
* "You will send: [name]"
* "Send 'Balanced'? You get one results run for Northline."
* "Same event, same students, same luck. The only difference is what we knew about them."
