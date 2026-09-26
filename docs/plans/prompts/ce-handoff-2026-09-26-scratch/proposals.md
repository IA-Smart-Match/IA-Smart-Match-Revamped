# SmartMatch class exercise — four visual directions (experimental / adversarial track)

Scope: proposals and static mock-ups only. No app code changed. Read against
`apps/web/legacy-frontend/src/app/pages/exercise/` on origin/main (ExerciseEntry,
ExerciseMatching + WeightsControls + RankedList + SavedSettingsPanel,
ExerciseResults + ResultPanels + ExerciseResultsChart, ExerciseAskingForMore).

What the current screens are: Tailwind slate, `text-xl` everywhere, 2 px grey
borders, a six-column `<table>`, three "Figure" tiles, number boxes for weights
(no sliders yet). It is honest and projector-legible, and it looks like an
admin tool. The stakeholders' word "industrialized" is fair.

Hard constraints carried into every direction (from the code's own comments):

- No score, percentage, bar or "match strength" next to a person (ADR-0025 D8).
  A slider shows the *team's input*; that is allowed. Nothing per-row is a
  number except rank and profile number.
- The reason line is the server's sentence, verbatim ("Same major; nothing else
  on file.", "Tied on major; ordered by year.").
- Factor labels, `max_settings`, invite limit, seat count and asking choices
  come from the server; the design must not hard-code them.
- Wording: "fictional profiles shaped by overall survey percentages". Never
  "real students", never "respondents".
- The results screen's commonest state is a calm refusal sentence (locked,
  already run, rule not confirmed). Every direction needs a good-looking
  "nothing yet" state, not only a good-looking reveal.

Verdict up front (detail in §5):

| Rank | Direction | One line | Mock-ups |
|---|---|---|---|
| 1 | **The Room** (seating chart) | Every screen shows the 60-seat room; the list reserves chairs, results show who actually sat down | yes |
| 2 | **The Ledger** (editorial broadsheet) | The exercise as a printed invitation ledger with a front-page verdict sentence | yes |
| 3 | **Corkboard** (index cards) | Profiles are index cards pinned under four dials; compare is two boards joined by red string | no |
| 4 | **The Reveal** (game-show board) | Dark stage, tile flips, seat counter — deliberately risky | no |

---

## 1. The Room — the seating chart is the spine

**Concept.** The employer talk has a room with 60 seats. Every screen shows
that room. Invitations *reserve* chairs; results show which chairs were
actually *sat in*; "46 seats are still open" is not a figure, it is empty
chairs you can count.

**Eight moments**

| Moment | Look | Motion |
|---|---|---|
| Opening | Cream page, one question: "Who should we invite?" Below it, the room as 6 rows x 10 chair glyphs, all empty; license line in small caps at the foot. | Chairs draw in row by row over 600 ms, once. |
| Team entry | Six round tokens, "Team 1"…"Team 6", each a coloured seat-back. Tapping one turns it solid: "Your saved work lives under this number." | Chosen token settles 2 px down. |
| Ranked list + sliders | Left column: four horizontal sliders, fat 28 px thumb, factor label in the server's words, value 0–1 as a small numeral. Right: the room, invited chairs in team colour, "30 of 60 reserved" under it. Below both: the list as rows (rank, name, major, year, "how much we know" as a 1-3 dot marker, reason verbatim). | Moving a slider re-fills chairs: leaving chairs fade to outline, arriving chairs fill. Rows re-order with a 200 ms translate. |
| Save + compare | "Keep these weights as…" name box under the sliders; saved settings appear as up to `max_settings` seat-back tags. Compare shows two rooms side by side; chairs reserved by both are amber; the two lists sit under their rooms with "on both lists" chips. | Rooms slide apart; shared chairs pulse once. |
| Final-setting pick | The saved tags become large radio cards; the chosen one gets a "Final" ribbon and its room is drawn full-width. Button: "Run this list." | Ribbon drops in. |
| Results reveal | The room. Invited chairs outlined; signed-up chairs half-filled; attended chairs solid. Below: the seat sentence set large, then the three-panel counts (team / everyone / round one) as the existing chart. Locked state: the room empty, one line "The instructor has not opened results for this event yet." | Fills happen row by row over ~1.5 s, skipped under reduced-motion. |
| Asking for more | Three tall cards in server order ("Promise better recommendations." / "A small reward." / "Required."). Picking one flips it to "Chosen." Refresh counts render in the seat-figure style. | Card flip, 300 ms. |
| Round-2 comparison | Two rooms side by side: round one and round two, same chair grammar. The seat sentence under each; the difference in open seats is the headline. | Rooms cross-fade in. |

**Typography / colour / motion.** Fraunces (display, optical size on) for the
page question and headline numbers; Inter for everything else. Paper `#FAF7F0`,
ink `#1A1A1A`, one team colour per team (six muted hues; Team 3 = teal
`#2F6F73`), amber `#F2B33D` only for "on both lists". Chair state is shape,
not hue: outline = invited, half = signed up, solid = attended. Motion is only
ever the room filling; everything else is instant.

**What it teaches better.** The empty chairs are the lesson. Round two is a
visibly fuller room, not a taller bar. The invited-vs-attended gap reads
without a legend.

**Risks.** Seat count is `event_seats` from the server; the 6x10 grid rule
needs a fallback for other counts (rows of 10 until done). Two panels push
the table down on a phone (~900 px). Colourblind viewers need the shape rule
enforced everywhere. A screen reader gets nothing from the room, so the counts
and table must remain the accessible content and the room `aria-hidden`.

---

## 2. The Ledger — editorial broadsheet

**Concept.** The exercise is a newspaper. Masthead "The Invitation Ledger",
the ranked list as a typeset numbered column, results as a front-page headline
with a big number, round two as a second edition.

**Eight moments**

| Moment | Look | Motion |
|---|---|---|
| Opening | Masthead in a display serif; dateline "AI in Marketing · College of Business"; deck "A short exercise about who gets invited." License line as the folio. | None. |
| Team entry | "Byline: Team __" with six large serif numerals in a row. | None. |
| Ranked list + sliders | A boxed "Editor's weights" strip: four sliders drawn as thin rules with square thumbs and small numerals. The list: numbered column with hanging numerals, name bold, major and year as a run-in, "how much we know" as a small-caps tag, reason in italic on a second line. Coverage notice as a pull-quote. | Rows re-sort with a fade. |
| Save + compare | Saved settings are "editions", named by the team. Compare is two columns under a shared rule with running heads; shared names get an amber marginal tick and "on both lists" in small caps. On a phone the chip goes inline. | None. |
| Final-setting pick | "Go to press with…" and the editions as large radio rows. | None. |
| Results reveal | Headline: "Your list filled 6 seats." Deck: the seat sentence. Then the three-panel counts as a ruled table, then names by section (Invited / Signed up / Attended). Locked state: the headline slot reads "Not yet unlocked by the instructor." | Headline fades in, 200 ms. |
| Asking for more | "Correction request": three boxed paragraphs; the chosen one gets a solid left rule. | None. |
| Round-2 comparison | "Second edition" — two headlines stacked, seat sentences side by side, the table gains a third column. | None. |

**Typography / colour / motion.** Newsreader (text and display) + Inter Tight
for numerals and tags. Paper `#F6F3EC`, ink `#161616`, rules `#B9B2A3`,
amber `#E0A425` for shared names only. Almost no motion.

**What it teaches better.** Reading from across a room. A projector shows one
screen at a time and a broadsheet is designed to be read at distance. The
headline sentence forces the "so what" into the UI. "Second edition" makes
round two feel like a revision, which it is.

**Risks.** Hairline rules and 400-weight serif vanish on a washed-out
projector. Risk of feeling precious or "designed to look old". Compare on a
phone becomes stacked columns and loses the side-by-side.

---

## 3. Corkboard — index cards under four dials

**Concept.** Profiles are 3x5 index cards. The four factors are rotary dials
on a strip above the board. Turning a dial re-pins the cards. Saving a setting
is a coloured pushpin. Compare is two boards with red string between shared
cards.

**Eight moments**

| Moment | Look | Motion |
|---|---|---|
| Opening | Cork (CSS gradient, no image), one card pinned centre: "Which team are you?" | Card sways 1 degree on load. |
| Team entry | Six cards with team numbers in marker style. | Chosen card lifts (shadow grows). |
| Ranked list + sliders | Strip of four SVG knobs, label in server words, value as knob angle plus numeral. Board: 30 cards in a 5x6 grid, rank in a corner circle, name, major, year, marker as a rubber stamp, reason in italic. | Cards re-pin: lift, slide, drop, 250 ms staggered. |
| Save + compare | Three coloured pins in a tray; tap a pin to save. Compare: two boards side by side, shared cards joined by an SVG red string. | String draws in 400 ms. |
| Final-setting pick | Tap a pin; a "FINAL" stamp lands on that board. | Stamp scale-in. |
| Results reveal | Cards flip; the back shows "Signed up" / "Attended" / blank. Seat sentence on a sticky note. | Staggered flips ~1.2 s. |
| Asking for more | Three sticky notes, chosen one gets a pin. | None. |
| Round-2 comparison | Two boards; cards new in round two get a folded corner. | None. |

**Typography / colour / motion.** Caveat only for the reason line; Public Sans
for everything else. Cork `#C9A26B` to `#B58A55`, card `#FFFDF6`, pins in six
team colours, red string `#C0392B`. Each animation under 300 ms.

**What it teaches better.** Compare. Red string between shared names is the
most literal "these two lists overlap here" you can draw. The marker as a
stamp makes information scarcity visible per person.

**Risks.** 30 cards in one phone column is a 6,000 px scroll. Cork texture
halves contrast. Handwriting reads as "for kids". String draws nothing when
boards stack. Dials are worse than sliders on touch.

---

## 4. The Reveal — game-show board (deliberately risky)

**Concept.** A dark stage. The list is a board of 30 lit tiles. The instructor
unlocking results is a live moment: tiles flip, a seat counter ticks, the
"seats still open" number lands last.

**Eight moments**

| Moment | Look | Motion |
|---|---|---|
| Opening | Black, one spotlit title: "Who gets the invite?" | Spotlight fades up. |
| Team entry | Six podium buttons that light when pressed. | Glow. |
| Ranked list + sliders | Four vertical faders with LED-style readouts; the board: 30 tiles, rank as a big numeral, name, small major/year; reason on tap. | Tiles reshuffle with a swap animation. |
| Save + compare | "Lock in" a setting to one of three slots; compare lights shared tiles gold on both boards. | Gold pulse. |
| Final-setting pick | "Final answer?" confirm. | Drum-roll bar. |
| Results reveal | Tiles flip one by one: grey (no reply), amber (signed up), green (attended). Counter under the board counts 8 to 14; "46 seats still open" drops in last. | ~4 s, skippable. |
| Asking for more | Three doors. | Door open. |
| Round-2 comparison | Round one dimmed behind round two. | Cross-fade. |

**Typography / colour / motion.** Archivo Black for numerals, Inter for text.
Stage `#0B0B10`, tile `#1E1E2A`, gold `#FFC857`, green `#3DDC97`, amber
`#FFA552`. Motion is the product.

**What it teaches better.** The reveal is memorable and the class watches it
together. The gap between 30 invited and 6 who came is felt as a let-down,
which is the lesson.

**Risks.** See the review.

---

## 5. Adversarial review

Three reviewers per direction. The instructor has 50 minutes and a projector
she has not tested in a lit room. The student is on a 390 px phone with one
bar of Wi-Fi, two minutes into a five-minute team huddle. The accessibility
reviewer runs VoiceOver, has reduced-motion on, and checks contrast.

### The Room

| Reviewer | Where it fails | Severity |
|---|---|---|
| Instructor | Teams will ask "is that the actual room?" Label it "60 seats, from the data file". The room takes vertical space above the list; on the projector the table may start below the fold. | medium |
| Student on phone | Room plus table means the table starts ~900 px down. Slider thumbs must be 44 px. The 10-column grid is fine at 390 px (about 30 px per chair). | medium |
| Accessibility | Signed-up vs attended must differ in shape, not hue. Room is `aria-hidden`; counts and table stay the accessible content. Row-by-row fill respects `prefers-reduced-motion`. | low once done |

Fails in a live class if the seat count is not 60 (grid rule) or the room
pushes the table below the fold on the projector. Both are layout rules.

### The Ledger

| Reviewer | Where it fails | Severity |
|---|---|---|
| Instructor | Hairline rules and 400-weight serif vanish on a 2,500-lumen projector in a lit room. Headline sentence is a win. "Editions" may confuse ("do I need three?"). | medium |
| Student on phone | Serif body at 16 px is fine; the two-column compare stacks and the marginal tick loses meaning; needs the chip inline. | medium |
| Accessibility | Best of the four: semantic table stays a table, no motion, high contrast. Small-caps tags need real text, not abbreviations. | low |

Fails in a live class if the projector washes out the rules. Fix: 2 px rules,
500-weight text; costs a little elegance.

### Corkboard

| Reviewer | Where it fails | Severity |
|---|---|---|
| Instructor | "It looks like a kids' app." Handwriting on a business-school projector is a credibility risk. Cork texture halves contrast. | high |
| Student on phone | 30 cards in one column is a 6,000 px scroll; nobody finds rank 28. Dials are worse than sliders on touch. Red string draws nothing when boards stack. | high |
| Accessibility | Grid of divs unless carefully built; string is purely visual; dials need a slider fallback; texture fails contrast. | high |

Fails in a live class on phones. It almost certainly fails on phones.

### The Reveal

| Reviewer | Where it fails | Severity |
|---|---|---|
| Instructor | A 4 s animation x 6 teams x 2 rounds is class time, and the reveal happens on 30 phones, not on the projector she can see. "Final answer?" is a joke that runs out on the second use. Dark UI in a lit room is unreadable. | high |
| Student on phone | Vertical faders are awkward on touch; the 30-tile board is a long scroll; the reason hidden behind a tap hides the lesson's "why". | high |
| Accessibility | Dark tiles with colour-coded state, motion as the product, a counting animation: three strikes. Reduced-motion turns off the concept. | high |

Fails in a live class if the projector is in a lit room (it will be). Even
with fixes, it spends its budget on the one moment the instructor cannot show
to everyone at once.

### Ranking and recommendation

1. **The Room** — recommended. Adds one picture and keeps the table; the
   picture *is* the lesson. Failures are layout rules with known fixes.
2. **The Ledger** — recommended as the typographic system even if the seat
   picture is adopted: a serif display face, a headline sentence on results,
   and rules instead of boxes fix "industrialized" on their own.
3. **Corkboard** — mine two details: the marker as a stamp, and a literal line
   between shared names in desktop compare.
4. **The Reveal** — do not ship. Keep one idea: results fill row by row, with
   a skip, only when reduced-motion is off.

**Recommended composite:** The Room's seating chart as the recurring element,
The Ledger's type and headline pattern, the Corkboard's stamp for "how much
we know". The two mock-up sets are kept pure so the prompt engineer can pick
parts.

---

## 6. Mock-ups

`mockups/room/` and `mockups/ledger/`, three moments each: `list.html`
(ranked list with sliders), `compare.html` (save and compare), `results.html`
(results reveal), with `-1280.png` and `-390.png` full-page screenshots.
Static HTML/CSS with inline SVG; Google Fonts is the only external request.

Content shape used: majors "Accounting", "International Business & Marketing",
"Marketing Management", "Finance, Real Estate & Law", "Computer Information
Systems"; years Sophomore to Senior; reasons "Same major; nothing else on
file." and "Tied on major; ordered by year."; markers "major only", "major
plus events attended", "completed card"; the seat sentence "8 were already
coming. Your invitations added 6. 46 seats are still open."; footer line
"Fictional profiles shaped by overall survey percentages."
