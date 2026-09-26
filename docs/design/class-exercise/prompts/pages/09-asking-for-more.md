# Page 9 — asking for more

After round one, a team picks one of three ways to ask the people it
invited to fill in a card, then asks once. The refresh reports three counts.

- **Route:** `/exercise/asking`. Code: `ExerciseAskingForMore.tsx`, `askingChoices.ts`.
- **System:** [`DESIGN.md` 6.18, 6.19 and 7.9](../../DESIGN.md#79-asking-for-more-exerciseasking), motion `ce-choice-commit`, `ce-count-up`.
- **Component:** [asking choice cards](../components/asking-choice-cards.md).
- **Asset:** [`partly-known-card.svg`](../../assets/svg/partly-known-card.svg).
- **Content:** Team 4 chose "A small reward."; counts 9 / 0 / 34.
- **States:** nothing chosen, confirm pending, chosen and not asked, asking, asked (counts shown), already asked (counts not re-shown), before round one run (refusal), unreachable.

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page, gold-wash ribbon. Title
"Asking for more" (Archivo SemiExpanded 600, 48px) with a secondary button
"Back to the events" on the right. Lead Figtree 22px #59665F: "Pick one way
to ask the people your team invited to fill in a card. Your team picks
once." To the right of the lead, a simple geometric pictogram of a card
half filled in (left half solid, right half dashed) in CPP Green, 96px.

Section "How will your team ask?" (Source Serif 4 32px): three tall white
cards in a row — "Promise better recommendations.", "A small reward.",
"Required." — each with one grey supporting line. Card 2 is chosen: #D9EADF
fill, 3px CPP Green outline, a gold #FFB81C round seal with a check at the
top-right, "Your team chose this." at the bottom. Cards 1 and 3 faded.
Under the row: "A team picks once, so these are now fixed."

Section "Ask the people your team invited" (Source Serif 4 32px) with the
line "This happens once. Everyone who attended the first event picks up its
topics, and some of the people your team invited fill in a card." A
primary CPP Green button "Ask them now".

Then a ruled figures band (thin vertical rules, no cards) with big Archivo
bold numerals: 9 "Cards filled in", 0 "Stopped opening messages", 34
"Topics added from the first event".

No percentages, no predicted rates, no gift or money icons.
```

**390 follow-up:** "At 390px: cards stack; the pictogram hides; the button is
full width; the figures band keeps three narrow columns."

## Claude Design prompt

```text
Build /exercise/asking for the Smart Match class exercise with the preamble
tokens, reusing the asking-choice-cards component.

Order: h1 "Asking for more"; aside secondary "Back to the events"; lead;
partly-known-card.svg 96px beside the lead at 1280 (decorative, hidden at
390). Section 1: the choice cards (radiogroup, inline confirm, once-only).
Section 2: h2 "Ask the people your team invited", explanation line, primary
"Ask them now" — disabled until a way is chosen (helper "Pick a way of
asking first."), "Asking…" while pending, then replaced by the line "Your
team has already asked." Section 3 (after asking): a ruled figures band
(<dl>, three columns, 1px --ce-line-strong dividers, --ce-font-display 700
64px numerals) "Cards filled in 9", "Stopped opening messages 0", "Topics
added from the first event 34", with ce-count-up once (reduced: final
numbers). The counts come back from the one request and are kept on screen;
a later visit shows "Your team has already asked." without them.

States for the switcher: Nothing chosen · Confirm pending · Chosen, not
asked · Asking · Asked (counts) · Revisit after asking (no counts, the line
only) · Refused before round one (calm notice with the server's sentence;
illustrative "Run results for the first event before asking.") · Already
asked refusal ("Your team has already asked the people it invited.") ·
Loading · Unreachable · 390.

No percentages, completion rates or predicted outcomes.
```

## Review checklist

1. Choice wording verbatim; no percentages.
2. The once-only nature is said before and after the action.
3. Counts are shown once and not faked on revisit.
