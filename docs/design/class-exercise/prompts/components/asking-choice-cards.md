# Component — asking-for-more choice cards

Before the refresh, a team picks one of three ways to ask the people it
invited to fill in a card. A team picks once, so the choice needs weight and
a confirm step.

- **System:** [`DESIGN.md` 6.18](../../DESIGN.md#618-asking-choice-card-see-prompt), motion `ce-confirm-window`, `ce-choice-commit`, `ce-lift`.
- **Asset:** [`partly-known-card.svg`](../../assets/svg/partly-known-card.svg) for the section header.
- **Content:** the choices are the server's `choices`, worded by `askingChoices.ts`: "Promise better recommendations.", "A small reward.", "Required." No percentages (the illustrative shares are not shown to participants).
- **States:** nothing chosen, one focused, confirm pending, saving, chosen (fixed), refusal, loading.

**Owner ruling, 2026-09-26:** an inline confirm. Each card's button "Choose
this way" turns into "Confirm: A small reward?" for about 5 seconds; a
second press commits. No pop-up, no modal. See
[`DESIGN.md` section 11](../../DESIGN.md#11-open-items-for-the-owner).

## Google Stitch prompt

```text
A choice section for a desktop web app on an eggwhite #F8F6F1 page. Section
title "How will your team ask?" (Source Serif 4, 32px, #163229). A line
under it in #59665F 20px: "Pick one way to ask the people your team invited
to fill in a card. Your team picks once."

Three equal tall white cards in a row (360px each, 14px corners, soft
shadow, 24px padding). Each card: a round radio marker top-left, a title in
Source Serif 4 24px, one supporting line in Figtree 18px #59665F, and a
secondary button "Choose this way" at the bottom:
1. "Promise better recommendations." — "Tell them a card helps us suggest
   events worth their evening."
2. "A small reward." — "Offer something small for a completed card."
3. "Required." — "Make the card a condition of hearing about events."

Show this as the confirm moment: card 2 has a 3px CPP Green #005030
outline and its button has turned into a solid CPP Green button reading
"Confirm: A small reward?" with a thin light underline bar under the label
(a 5-second countdown, about half gone), and the small grey line "Press
again within 5 seconds. Your team picks once." under the button. Cards 1
and 3 keep their "Choose this way" buttons.

(Second screen, same layout) Show card 2 as chosen: filled with #D9EADF, a 3px CPP Green #005030
outline, a round gold #FFB81C seal with a check in the top-right corner, and
the line "Your team chose this." at the bottom in CPP Green. Cards 1 and 3
are faded to 55% opacity. Under the row: "A team picks once, so these are
now fixed." in #59665F.

No percentages, no predicted outcomes, no icons of gifts or money.
```

**390 follow-up:** "Stack the three cards full width at 358px with 12px
gaps; show card 2 in the confirm moment, its button full width."

## Claude Design prompt

```text
Supporting lines under each title are approved as drafted (2026-09-26).

Build the asking-for-more choice cards for the Smart Match class exercise
with the preamble tokens. Semantics: role="radiogroup" labelled by the h2
"How will your team ask?"; each card is role="radio" with aria-checked;
arrow keys move between cards. Map over a `choices` array (server order);
an unknown value renders as its raw string in the same card.

Card: --ce-surface, --ce-elev-1, --ce-radius-card, min-height 200px at
1280. Title --ce-font-serif 600 24px with the exact wording
"Promise better recommendations." / "A small reward." / "Required." (full
stops included). One supporting line, body 18px --ce-ink-muted (use the
lines from the Stitch prompt).

Each card has a secondary button "Choose this way" (44px min height).

Flow (owner ruling: inline confirm, no pop-up):
1. First press on a card's button (click, Enter, Space) marks the card with
   a 3px --ce-primary outline and turns that same button into a primary
   button "Confirm: A small reward?" (the choice label without its final
   full stop). ce-confirm-window: the label swaps in 150ms and a 2px
   --ce-on-primary underline under the label shrinks linearly from full
   width to 0 over 5000ms. A helper under the button reads "Press again
   within 5 seconds. Your team picks once." and an aria-live="polite"
   region says "Press again to confirm A small reward. Your team picks
   once." Focus stays on the button.
2. The window lapses, Escape is pressed, or another card is chosen → the
   button reverts to "Choose this way" and the outline clears.
3. Second press inside the window → button reads "Saving…"
   (aria-disabled) for 600ms.
3. Chosen: ce-choice-commit — chosen card fills --ce-primary-tint and a
   gold seal (32px circle, --ce-gold, Lucide Check in #17352A) scales in at
   its top-right; the other two fade to 0.55 opacity and become
   aria-disabled; line "Your team chose this." on the chosen card; line "A
   team picks once, so these are now fixed." under the row. 240ms
   --ce-ease-out; reduced motion: same end state, 150ms opacity, no scale.
Reduced motion for the confirm: no underline animation; the label swap and
the static helper "Press again within 5 seconds." carry it.

States for the switcher: Nothing chosen · Keyboard focus on card 1 ·
Confirm window (card 2, underline half gone) · Confirm lapsed (back to
"Choose this way") · Saving · Chosen (fixed) · Refusal (calm notice
with the server sentence "Your team has already chosen how to ask." and the
chosen card shown) · Loading (three card skeletons) · 390 frame.

Header: to the right of the h2 at 1280, ../../assets/svg/partly-known-card.svg
at 96px in --ce-primary (hidden at 390). No percentages or predicted
completion rates anywhere.
```

## Review checklist

1. Wording is exactly the three phrases with their full stops.
2. No percentage, rate or predicted outcome is shown.
3. The chosen state stays visible after choosing; the other cards do not vanish.
4. Keyboard: arrows move between cards; the same button confirms; Escape cancels.
5. No pop-up or modal appears at any point.
