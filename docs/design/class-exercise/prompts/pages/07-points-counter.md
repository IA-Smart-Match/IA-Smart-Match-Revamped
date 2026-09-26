# Page 7 — points counter (deferred)

> **Deferred, 2026-09-26 (orchestrator call).** Not generated this round.
> The page waits until an endpoint returns `ProfilePoints`. The prompts
> below stay so the later round starts from them; do not run them yet.

A per-profile counter that rises with attendance and card completion. It is
a nice-to-have in Ann's build table and is **not routed today**:
`ProfilePointsCounter.tsx` exists, but no endpoint returns `ProfilePoints`
to a page yet. Generate it as a component frame, not a screen, until the
owner confirms where it lives (see [`DESIGN.md` section 11](../../DESIGN.md#11-open-items-for-the-owner)).

- **Code:** `ProfilePointsCounter.tsx`.
- **System:** [`DESIGN.md` 6.23 and 7.7](../../DESIGN.md#77-points-counter-component-frame-not-routed), motion `ce-count-up`.
- **Content:** three fictional profiles: Daniel Okafor (total 7; attending 5; card 2; "Card completed"); Jordan Kim (total 3; attending 3; card 0; "Card not completed"); Hannah Lee (total not available; attending not available; card not available; "Card not asked yet").
- **States:** numbers present, zero, not available, card states (not asked yet / not completed / completed).
- **Rules:** points are whole counts; no progress bar to a threshold, no "top 10%", no rewards catalogue, no redeeming (Ann's "not now").

## Google Stitch prompt

```text
Desktop web, 1280px, eggwhite #F8F6F1 page. Section title "Points for three
profiles" (Source Serif 4 32px) and the line "Points rise when a profile
attends an event or completes a card." in #59665F.

Three ticket-stub cards in a row (340px each): white, 14px corners, soft
shadow, with a dashed vertical perforation line 72px from the right edge
and two small semicircle notches on the top and bottom edges at the
perforation, like a ticket.
Left part: profile name in Source Serif 4 24px; the total as a big numeral
in Archivo SemiExpanded bold 72px CPP Green #005030 followed by "points" in
Figtree 22px; two rows in Figtree 18px: "From attending events 5", "From
completing a card 2". Right stub: a small pill chip with an icon: "Card
completed" (ID-card icon, #D9EADF fill).

Card 1 Daniel Okafor: 7 points (5 and 2), "Card completed".
Card 2 Jordan Kim: 3 points (3 and 0), "Card not completed".
Card 3 Hannah Lee: the total reads "not available" in Figtree 30px
#59665F instead of a number, both rows read "not available", chip "Card
not asked yet".

No progress bars, no rankings, no rewards, no percentages.
```

**390 follow-up:** "Stack the three tickets full width; keep the
perforation and stub on the right."

## Claude Design prompt

```text
Build the points-counter component for the Smart Match class exercise with
the preamble tokens, as a component frame (not a routed page).

Anatomy: <section aria-label="Points for Daniel Okafor">. Ticket card
(--ce-surface, --ce-elev-1, --ce-radius-card) with a dashed 2px --ce-line
perforation 72px from the right and two 12px semicircle notches cut with a
CSS mask (not overlapping circles). Left: h3 name (--ce-font-serif 600
24px); total (--ce-font-display 700 72px, --ce-primary, tabular) + "points"
(body 22px); <ul> of "From attending events N" and "From completing a card
N" (body 18px). Stub: card-state chip — "Card completed" (Lucide IdCard,
--ce-primary-tint), "Card not completed" (Lucide CircleSlash,
--ce-surface-sunk), "Card not asked yet" (Lucide CircleDashed,
--ce-surface-sunk).

Rules: a null figure renders the words "not available" (body 30px
--ce-ink-muted for the total); zero renders "0". Never infer a total in the
UI.

Motion: ce-count-up on the total, 0 → value over 700ms --ce-ease-out, once
per mount; reduced motion: final number at once. No count-up for "not
available".

States for the switcher: Three profiles (7/3/not available) · All zero ·
All not available · 390 (stacked).
```

## Review checklist

1. "not available" is never shown as 0, and 0 is never shown as "not available".
2. No progress bar, threshold, ranking or reward.
3. Marked as a component frame, not a routed screen.
