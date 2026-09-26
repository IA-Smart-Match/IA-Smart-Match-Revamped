# Component — asking-for-more choice cards

Before the refresh, a team picks one of three ways to ask the people it
invited to fill in a card. A team picks once, so the choice needs weight and
a confirm step.

- **System:** [`DESIGN.md` 6.18](../../DESIGN.md#618-asking-choice-card-see-prompt), motion `ce-choice-commit`, `ce-lift`.
- **Asset:** [`partly-known-card.svg`](../../assets/svg/partly-known-card.svg) for the section header.
- **Content:** the choices are the server's `choices`, worded by `askingChoices.ts`: "Promise better recommendations.", "A small reward.", "Required." No percentages (the illustrative shares are not shown to participants).
- **States:** nothing chosen, one focused, confirm pending, saving, chosen (fixed), refusal, loading.

The inline confirm is a proposed change (today one click commits); see
[`DESIGN.md` section 11](../../DESIGN.md#11-open-items-for-the-owner).

## Google Stitch prompt

```text
A choice section for a desktop web app on an eggwhite #F8F6F1 page. Section
title "How will your team ask?" (Source Serif 4, 32px, #163229). A line
under it in #59665F 20px: "Pick one way to ask the people your team invited
to fill in a card. Your team picks once."

Three equal tall white cards in a row (360px each, 14px corners, soft
shadow, 24px padding). Each card: a round radio marker top-left, a title in
Source Serif 4 24px, and one supporting line in Figtree 18px #59665F:
1. "Promise better recommendations." — "Tell them a card helps us suggest
   events worth their evening."
2. "A small reward." — "Offer something small for a completed card."
3. "Required." — "Make the card a condition of hearing about events."

Show card 2 as chosen: filled with #D9EADF, a 3px CPP Green #005030
outline, a round gold #FFB81C seal with a check in the top-right corner, and
the line "Your team chose this." at the bottom in CPP Green. Cards 1 and 3
are faded to 55% opacity. Under the row: "A team picks once, so these are
now fixed." in #59665F.

No percentages, no predicted outcomes, no icons of gifts or money.
```

**390 follow-up:** "Stack the three cards full width at 358px with 12px
gaps; keep the chosen state on card 2."

## Claude Design prompt

```text
Supporting lines under each title are proposed copy; the owner approves them before build.

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

Flow:
1. Selecting a card (click, Space) marks it with a 3px --ce-primary outline
   and reveals an inline confirm under the row: "Choose \"A small
   reward.\"? Your team picks once." with a primary button "Choose this way"
   and a quiet "Pick again".
2. Confirm → button reads "Saving…" (aria-disabled) for 600ms.
3. Chosen: ce-choice-commit — chosen card fills --ce-primary-tint and a
   gold seal (32px circle, --ce-gold, Lucide Check in #17352A) scales in at
   its top-right; the other two fade to 0.55 opacity and become
   aria-disabled; line "Your team chose this." on the chosen card; line "A
   team picks once, so these are now fixed." under the row. 240ms
   --ce-ease-out; reduced motion: same end state, 150ms opacity, no scale.

States for the switcher: Nothing chosen · Keyboard focus on card 1 ·
Confirm pending (card 2) · Saving · Chosen (fixed) · Refusal (calm notice
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
4. Keyboard: arrows move, Space selects, the confirm button is reachable.
