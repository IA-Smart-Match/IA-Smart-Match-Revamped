# Class exercise — requirements for the Spring 2027 AI in Marketing module

**Last updated:** 2026-09-28
**Source:** Ann Wang, "Smart Match — Marketing Class Exercise and Minimum Build
Requirements", 15 September 2026; her "Background Note" for class
participants, same date; and her emails to the team
([`stakeholder-correspondence-2026-09.md`](../decisions/stakeholder-correspondence-2026-09.md)).
The two documents are proprietary and are held off-repo. This file paraphrases
them as structured requirements; short quotes are marked.
**Authority:** this document is the authority for the **class-exercise product
scope** (`ProductScope.CLASS_EXERCISE`, ADR-0025). It amends nothing in
[`cba-smart-match-customer-requirements.md`](cba-smart-match-customer-requirements.md),
which remains the authority for the CBA platform scope. The two scopes share
the domain matching mechanism and share no data, route, role, or table.
**Later rulings win:** where a decision record or a closed register row
changed the 15 September text, the table
[Changed since 15 September](#changed-since-15-september) points to it. That
record is the authority for the point; the text here is not restated.
**Parallel tracks:** Ann's document defers the "CBACH project" (real students
matched to real events) to a 20 November 2026 decision for *her* deliverable.
The CBA platform track (student engagement, retention, speaker-to-event
matching) is a separate stakeholder commitment and continues on its own plan.
This document does not pause it.

## Vocabulary

Ann's document avoids the bare word "students". This document keeps her terms:

- **The team** — Chau, Danny, Janice, Justin.
- **Class participants** — students in Dr. Lin's AI in Marketing course who use
  the app in Spring 2027.
- **The 300 profiles** — the made-up records inside the app: fictional
  profiles shaped by overall survey percentages.
- **Exercise events** — "Northline Analytics" (round one) and "Harbor Consumer
  Brands" (round two), a few weeks apart in the story.

## Purpose

This is the one thing the project must deliver this semester: a working class
exercise for a lower-division AI in Marketing course, built on the current app.
Every "required" item must be done.

## What class participants must be able to do

Act as the person promoting a campus career event with 60 seats, 8 sign-ups,
and time to personally invite only 30 people. Choose whom to invite with the
tool, see what happened, ask the profiles for more information, refresh, and
run a second event. Leave remembering one thing: AI helps a marketer use
customer information to decide whom to reach, but the marketer still decides
what information matters, what message fits, and who is being overlooked.

## How the matching is meant to work (the real-world design)

The made-up data stands in for this in the exercise; class participants never
fill in a profile card themselves.

1. **Day one, major only.** The only thing the app knows about every student is
   the major, so the first matching is broad and starts from major.
2. **Learned over time, two ways.** Students tell the app about themselves
   through a short profile card ("Want better event recommendations? Answer
   five quick questions." — now two questions, see OQ-CE-11), and attending an
   event tells the app the student cares about its topics.
3. **Show how much is known.** For every profile the app shows how much it
   knows, so the person matching can see who is matched on a full picture and
   who on major alone.

## The exercise in brief

| Item | Detail |
|---|---|
| Course | AI in Marketing (Dr. Lin), lower division, one exercise. Built and tested in fall 2026; runs in Spring 2027. |
| Length | Two 75-minute sessions (main plan), or one session plus homework (short version). |
| Class size | About 30 class participants in 6 teams of 5 (assumed; Dr. Lin to confirm — could be 5 or 8 teams). |
| Role | The person promoting two made-up career events a few weeks apart. |
| Main question | Which 30 people do we personally invite, what do we say, how do we know it worked, and what did we learn for the next event? |
| Constraints | 60 seats, 8 signed up, one week to go, 30 personal invitations per event. |
| Hand-in | A two-page team memo (due 48 hours after Session 2) and an individual record of how each person used AI. |
| Tool | The Smart Match demo site: no login, made-up data only. |

## What class participants should learn (three things, no more)

1. AI can only work with the information it has; better customer information
   leads to better targeting.
2. AI can help choose the audience and generative AI can help draft the
   message, but a marketer still decides whether the message fits the person.
3. Every targeting choice involves three trade-offs: many people or the right
   people; existing customers or new ones; the people the system knows or the
   people it overlooks.

## Reading before Session 1 (assigned one week ahead, about 20 minutes)

- **The case (one page, Ann writes it; read first).** Northline Analytics comes
  to campus in one week for a "Behind the Business" talk; Harbor Consumer
  Brands three weeks later. The organizer assumed analytics majors and posted in
  the usual places; 8 of 60 seats are taken. Five attachments: students by
  major and year; the 8 sign-ups by major and year; how many have a profile
  card and how many attended any past event; what was tried and the email open
  rate; both event descriptions.
- **The background note (Ann; already written).** Summarised below.

### What class participants are told (background note, in short)

- **The four factors, in plain words:** same major as the event's audience;
  said they are interested in the topic; career goal fits the event; went to
  similar events before.
- **You decide how much each one counts.** The note's example: if "said they
  are interested" counts *twice as much* as "same major", a marketing major who
  said she is interested in data careers ranks above an analytics major who
  never said anything. Change the weights and the list changes; the judgment
  about what matters is the participant's.
- **The tool matches only on what it knows.** On day one it knows major and
  year. Weight on "said they are interested" does nothing for someone who never
  said anything. Tools learn when people tell them (a card) and from behavior
  (attendance). Asking for more is a marketing decision with a price: ask too
  little and the tool stays blind, too much and people quit. The first round of
  a new tool is partly a learning round.
- **The three trade-offs:** reach or relevance; existing customers or new ones
  (heavy weight on past events re-invites people who would have come anyway);
  known or overlooked customers (complete profiles get invited again and again;
  the only defense is a person who asks who is missing).
- **Read results against "email everyone".** Outreach is a funnel (contacted →
  signed up → showed up). The rate says how well targeting worked; the total
  says whether the effort was enough. Never read your own result alone.
- **Two uses of AI, one human decision:** Smart Match helps choose the
  audience; a generative AI tool may help draft the invitation; the marketer
  decides whether the list and the message fit.
- **Bring to Session 1:** which of the four factors can the app really use
  now; who you think should be invited to Northline and why; what else, besides
  invitations, would make the second event easier to fill.

## Session plans

### Main plan: Session 1 — choosing whom to invite when you know little (75 min)

| Minutes | Activity | Who / notes |
|---|---|---|
| 0–8 | Open on the case: why the mass email failed, what the organizer assumed, how much the app knows about the 300 right now. | Board column 1: key facts |
| 8–12 | One slide: targeting by hand vs AI-assisted scoring and ranking. Same decision, faster. | Instructor |
| 12–18 | Before the tool, each team writes a card: who should be invited, and why. | Cards kept for later |
| 18–28 | Projector walkthrough: open Northline, run with default settings, show the top 30, the reason line, the "how much we know" marker, and the "who is on the list" table. | Instructor only |
| 28–48 | Teams at laptops (one tab per team, team number entered) try two named weight settings for Northline, save both top-30 lists, and note overlap and how many are matched on major alone. | Four factors in plain words |
| 48–65 | Discussion: tool vs card; weight on "said they are interested" for profiles that never said anything; who is missing from every list. | Board columns 2–3 |
| 65–75 | Homework brief: for one person on the list, a fill-in-the-blanks invitation and a personally written one, any AI tool allowed, every prompt and edit recorded. Submit the final Northline setting and both messages before Session 2. | Ann provides the forms |

### Main plan: Session 2 — results, asking for more, and the second event (75 min)

| Minutes | Activity | Who / notes |
|---|---|---|
| 0–10 | Message review: teams swap and score on four points (written for this person; tied to a reason the app gave; clear next step; no filler). | Scores do not change results |
| 10–22 | Round one: instructor unlocks results; each team runs its final Northline setting once. Screen shows invited / signed up / attended beside "email everyone" (all 300), and seats still empty. | One run per team per event |
| 22–34 | Asking for more: instructor shows the profile-card screen; discussion of why someone says yes or no and what the marketer gives back; each team picks better recommendations, a small reward, or required. | The choice has consequences |
| 34–40 | Per-team refresh: Northline attendees pick up its topics; a share of invited profiles without a card complete one; markers change. | Team presses its own button |
| 40–52 | Round two: Harbor Consumer Brands, invite 30. Results beside "email everyone" and the team's round-one result. | Side by side on the projector |
| 52–62 | Why results differed; then the reveal, framed as "this simulated market behaved this way" (true fit mattered, frequent attenders only a little more likely, major mattered less than assumed); real marketers would have to test this. | Board column 4 |
| 62–68 | Wrap-up: the three trade-offs and the one-sentence takeaway. | Instructor |
| 68–75 | Memo outline in teams; memo due in 48 hours. | Ann provides the memo form |

### Short version (one 75-minute session)

Reading as above. At home each team tries two Northline settings and submits
one final setting and a written prediction card. In class: 0–6 case; 6–9 one
slide; 9–17 walkthrough; 17–27 round one (unlocked in class), results side by
side; 27–37 asking for more; 37–41 refresh; 41–51 round two; 51–60 debrief and
reveal; 60–66 wrap-up; 66–75 memo outline. The two invitations and the memo are
homework due in 72 hours; message scoring happens online, with a ten-minute
review at the start of the next class.

## Grading (memo is team; AI record is individual)

| Component | Points of 100 |
|---|---|
| Recommendation for the next event: weight setting, the 30-person list, and whether the tool confirmed or changed the team's first instinct | 25 |
| Use of results from both rounds, including the "email everyone" comparison | 20 |
| How the team asked for more information, why, and what the marketer gave in return | 15 |
| The two invitations, and where the fill-in-the-blanks version stopped fitting | 15 |
| Who was left out (numbers from the "who is on the list" table) and how to reach them another way | 15 |
| Individual AI record: complete and honest, each suggestion marked used as is, changed, rejected, or set aside | 10 |

## Ann's stated keeps

From her email: "The matching engine, the saved settings, the dashboard, and
the back end you are rewriting are exactly what we build on. What changes is
who gets matched to what, not how." Keep: the matching engine with adjustable
weights, the ranked list with a reason next to each name, and the results
screen.

## Minimum build (transcribed from Ann's build table)

"Required" must work for the exercise to run. "If time allows" makes it better.
"Not now" is out of scope for this deliverable so nobody spends time on it.
Where a row's text was later changed, see
[Changed since 15 September](#changed-since-15-september).

| Area | Required | If time allows | Not now |
|---|---|---|---|
| Getting in | No login. A public web address. Each browser tab keeps its own work; a team enters its team number (1–6) so its saved runs are labeled. An instructor page behind a simple passcode can open any team's saved runs, unlock results, and set the invite limit. | — | Accounts and roles; the four user types; invitation-only speaker accounts. |
| Data | Load the made-up student body Ann provides as a spreadsheet, and let the instructor replace it from the instructor page. About 300 profiles and 12 events (10 past events for attendance history plus the 2 exercise events). Every profile has a made-up name, a major, and a year; about a third have attended one or more past events; about 70 have a completed profile card (stated interests and career goals), and of those a good share have interests that do not match Northline. Every profile also carries a hidden "true" set of interests that the app never shows and never uses for matching; only the results rule uses it. | — | Any connection to university records, Handshake, or real sign-ups; any real student data, even with names changed. |
| How much we know | Next to every profile, a simple marker: major only; major plus events attended; completed card. The "who is on the list" table also counts the list by these three groups. | — | — |
| Matching | Match profiles to one chosen event using four adjustable factors, labeled in plain words: same major; said they are interested in this topic; career goal fits this event; went to similar events before (topics of past events attended overlap this event's topics). Major is always available. The other three count only for profiles that have that information; for everyone else the reason line says so ("same major; nothing else on file"). Ties are broken in a fixed order: more information on file first, then year (seniors first), then a fixed random order that never changes; the reason line says "tied on major; ordered by year." Ranked list capped at the invite limit (30 by default). A team can save up to three named settings per event and view any two side by side with shared names highlighted. | — | Machine-learning matching; speaker-to-event matching; checking calendars. |
| Who is on the list | For the current list, a small table: count by major, by year, and by "how much we know" group, next to the same counts for all 300. | A one-line notice when a major or year that exists among the 300 has nobody on the list. | — |
| Download | Download the current list with reasons as a spreadsheet file. | — | Writing messages in the app; AI writing in the app; sending email. |
| Results lock | Results cannot be run until the instructor unlocks them for that event. Each team gets one results run per event. | — | — |
| Comparison | The results screen always shows the "email everyone" result (all 300 contacted) next to the team's result, and in round two the team's own round-one result as well, plus seats still empty. | — | — |
| Simulated results | A hidden rule that turns a list into results (invited, signed up, attended). It uses each profile's hidden true interests, not what the app has on file. (1) A profile is more likely to sign up when its true interests and career goal match the event. (2) Profiles that attended many past events are only a little more likely to sign up. (3) Same major alone gives only a small lift. (4) A small element of chance, fixed for each team so a repeated run gives the same result. (5) A reset per team that does not touch other teams. The rule is written in plain words in the code and shared with Ann and Dr. Lin before the practice run. Class participants hear it only as "how this simulated market behaved". | Results as a simple bar chart readable from the projector. | Real notifications or reminders; message quality changing results. |
| Asking for more | Before the refresh, a team picks one of three ways to ask the profiles it invited to complete a card. Each has a set outcome, written in the code and shared with Ann: promise better recommendations (about 30 percent of invited profiles without a card complete one); small reward (about 55 percent); required (about 80 percent, but about 15 percent of those without a card stop opening messages and never sign up in round two). Numbers are illustrative; Ann confirms them before the practice run. | A one-screen mock-up of the "five quick questions" card for the instructor to show. | Real profile cards for real people. |
| Profile refresh | A per-team button, available after the team has chosen how to ask: everyone who attended Northline picks up its topics as "went to similar events"; the chosen share of invited profiles complete a card copied from their hidden true interests; markers update. An instructor button runs every team's refresh at once. Each team's refresh changes only that team's copy of the 300 profiles. | — | Refresh from real behavior. |
| Points | Not required. | A points counter per profile that rises with attendance and card completion. | Reward catalog, redeeming points, faculty extra credit. |
| Hosting and backup | A stable web address that loads in under 5 seconds in Chrome on classroom computers. A spreadsheet backup for Session 1 (Ann builds it: the 300 rows, four weight cells, a score column, a sort). Session 2 depends on the site; there is no backup for the simulation. | — | Mobile app; more CPP colors and styling than already exist. |

## Weights: defaults and how they are shown

- **Default weights are 0.25 each.** Ann's 15 September document gives no
  numbers; it says only that the instructor runs the match "with the default
  settings". The equal default comes from Ann's email reply of 2026-09-25,
  which closed OQ-CE-02: "Equal is fine. Teams should decide for themselves
  which factors matter most." Code:
  `python/smartmatch_domain/smartmatch_domain/exercise/registry.py` (four named
  constants); record:
  [`class-exercise-decisions-2026-09-25.md`](../decisions/class-exercise-decisions-2026-09-25.md)
  and the [register](../plans/open-questions/class-exercise-open-questions.md).
- **The weights are relative and need not sum to 1.** The matcher divides by
  the total; only a total of zero is refused.
- **Weight display (owner ruling, 2026-09-28).** The matching screen shows the
  total of the four weights and this sentence: "What matters is how the weights
  compare: a factor set to 0.50 counts twice as much as one set to 0.25." It
  shows no percentages (ADR-0025 D8: no percentage, score, or confidence
  reaches a class participant), and it does not force the weights to sum to 1.
  This matches the background note's "twice as much" framing. Built on branch
  `feat/exercise-weight-total` (separate PR).

## Why the rule, the two rounds, and the choice of how to ask are built this way

- **The hidden rule turns a discussion into consequences.** It has to hold a
  real trade-off, or a team finds the one best answer in five minutes:
  - the 30-invite limit forces a choice;
  - frequent attenders get only a small lift, so the easy list does not win
    automatically;
  - major alone gives a small lift, so the organizer's assumption proves weak
    in a way teams can discover.
- **"Email everyone" shows what targeting is worth; "seats still empty" shows
  the cost of inviting too few.** With 52 empty seats and 30 invitations no
  team can fill the room by invitations alone, so the memo must say what else
  it would do.
- **The gap between what is on file and what is true is the point of two
  rounds.** In round one "said they are interested" reaches only the ~70 with
  cards, so most lists lean on major. Between rounds the team's own choice of
  how to ask — not an instructor button — changes round two: promising better
  recommendations learns least, a reward more, required the most but loses a
  few people. The causal story: round one, realise information is missing, ask
  for it, round two improves — by how much depends on how you asked.

## Who does what

Every item is either "required" in the build table or something Ann owes the
team. Anyone who finishes early helps whoever is furthest behind.

### Ann (instructor and project lead)

Owns everything class participants read or fill in, the made-up student body,
and the instructor-only decisions.

1. **Confirm the spring plan with Dr. Lin by Oct 2:** the spring week, one or
   two sessions, and roughly how many participants (the team plans for 6 team
   workspaces; it could be 5 or 8).
2. **Write the one-page case** with its five attachments (a Word document; the
   team builds none of it).
3. **The background note** — already written.
4. **Provide the data file:** one ~300-row spreadsheet (name, major, year, past
   events, stated interests and goals for ~70, hidden true interests). Built
   with Claude's help; mix follows the school's shape, every row fictional.
   20-row sample with final column names on Sept 18; full file on Sept 25.
   Delivered 2026-09-24 (see the correspondence record).
5. **Provide the four participant forms** (Word, not app features): prediction
   card, invitation form (both versions side by side), "how I used AI" record,
   memo template.
6. **Set the three "asking for more" percentages** — until then the team builds
   the placeholders and keeps them easy to change. Confirmed: OQ-CE-04.
7. **Attach the open license and upload to the course commons** by the Nov 20
   review (the case, note, forms, this document, and the plain-words rule
   write-up). The team's only part: show the same license line on the app's
   opening screen. Wording now fixed: OQ-CE-09 / D13.
8. **Build the Session 1 backup spreadsheet** from the data file.

### Chau (matching and results)

Owns who is on the list and what happens after it is sent.

1. **The four matching factors**, each with a team-adjustable weight; major is
   known for everyone, the other three count only where on file, and the reason
   line says so ("same major; nothing else on file").
2. **The tie-break:** more information on file, then year (seniors first), then
   a fixed random order; reason line "tied on major; ordered by year".
3. **The invite limit and saved settings:** list stops at the limit (30 unless
   the instructor changes it); up to three named settings per event; any two
   side by side with shared names highlighted.
4. **The results rule:** uses hidden true interests; true fit raises sign-up;
   frequent attenders only a little; major alone a small lift; chance fixed per
   team so the same list gives the same answer; per-team reset. Written in
   plain words (Justin edits) and shared with Ann and Dr. Lin before the
   November practice run.
5. **The "asking for more" outcomes:** a set share of invited profiles without a
   card get one (copied from hidden data); under "required" a share of those
   without a card stop responding in round two. Chau writes the rules; Danny
   builds the step that applies them.

### Danny (back end: storage, team workspaces, instructor controls, hosting)

Chau decides the rules; Danny builds the machinery that stores, runs and resets
them.

1. **No login, one workspace per team:** team number 1–6 labels saved settings
   (three per event), round-one and round-two lists, results and the "asking for
   more" choice; teams kept apart; survives reload.
2. **The instructor page** behind Ann's passcode: open any team's settings and
   results; unlock results per event; change the invite limit; replace the data
   file; one button to refresh every team.
3. **Loading the data file**, including an instructor re-upload, with a plain
   error when a column is missing.
4. **The results lock and the one-run-per-event rule.**
5. **The refresh between rounds**, per Chau's rules: Northline attendees pick up
   its topics; the chosen share get a card; under "required" the affected
   profiles stop responding; markers update. Each team's refresh uses its own
   round-one list and changes only its own copy of the 300. "Refresh all" runs
   every team's at once.
6. **Download and reset:** the list with reasons as a spreadsheet; a per-team
   reset that touches no other team (moved behind the instructor passcode by
   owner ruling, 2026-09-19).
7. **Hosting:** a stable address, under 5 seconds in Chrome on a classroom
   computer, up through the spring class. Address decided: OQ-CE-06.

### Janice (what people see)

Every screen, readable from the back of a classroom on a projector.

1. **The "how much we know" marker** — three states, understood without
   explanation.
2. **The "who is on the list" table** — counts by major, year and marker state
   beside the same counts for all 300.
3. **The side-by-side view** — two saved settings, shared names highlighted.
4. **The "asking for more" choice screen** — one plain sentence per option; if
   time, the profile-card mock-up.
5. **The results screen** — invited, signed up, attended, seats still empty;
   always beside "email everyone"; in round two also the team's round-one
   result; if time, a bar chart.

### Justin (testing, the written explanation, and support)

Once the test plan is written he helps whoever is furthest behind.

1. **Test against this document row by row**, including the easy-to-forget
   cases: two teams at once do not see each other's lists; reload keeps saved
   settings; the lock blocks a second run; reset clears one team only. Test
   profiles with known answers (Ann's concrete case is P004 — see
   [Changed since 15 September](#changed-since-15-september)). A short list of
   what was tested and what failed goes to the team before Ann's Oct 16
   run-through.
2. **The plain-words write-up:** one page, no code, of how the results rule
   decides who signs up, what each "asking for more" choice does, and how the
   refresh works. Ann and Dr. Lin read it before the practice run; the
   instructor uses it for the Session 2 reveal.

### Dr. Lin (course instructor)

Tells Ann the spring week, one or two sessions, and the expected class size;
joins one practice run with Ann in November.

## Timeline (Ann's planning markers; she will say which ones matter)

| Date | Milestone |
|---|---|
| Fri Sept 18 | Team confirms scope. Ann sends the 20-row sample with final column names and a one-line description of each. |
| Fri Sept 25 | Ann sends the full 300-row file. (Arrived 2026-09-24.) |
| Fri Oct 2 | Matching with the four factors, tie-break, cap, saved settings, markers, and the "who is on the list" table working **on the demo site** with the full data. Ann has confirmed the spring week and class size with Dr. Lin. |
| Fri Oct 16 | Results with lock, "email everyone" comparison, repeatable runs, reset, "asking for more", per-team refresh, round two, and download working. Ann runs both sessions start to finish and sends a problem list. |
| Fri Oct 30 | Problems fixed. Ann's case, background note, forms, and backup spreadsheet finished. |
| Week of Nov 9 | Practice run with Ann, Dr. Lin, and five or six volunteer students from Ann's fall classes going through both rounds. Hidden rule and the three percentages reviewed. |
| Fri Nov 20 | Fixes done. Team review. This version becomes the fall deliverable. Ann uploads the licensed materials to the course commons. Decision on the CBACH project. |
| Spring 2027 | Exercise runs in the agreed week. Small fixes only; no new features. |

Weekly check-in: Fridays 11 AM with Ann; tell her by Thursday to skip a week
(her reply, recorded in the correspondence file).

## What this means for the CBACH project (Ann's section, in short)

- **Not cancelled, not wasted.** Matching that starts from major and sharpens as
  profiles fill in, the markers, the profile card and the ways of asking for
  it, the refresh, the "who is on the list" table and the results screen are
  what a CBACH follow-on would build on.
- **Same staged approach if it goes ahead:** start broad (early real events
  match mostly on major and exist as much to learn as to fill seats); ask early
  (the card is the first thing a real student sees, and the college chooses how
  to ask knowing the trade-off); let behavior refine the profile; judge the app
  on improvement across events, not the first one.
- **The clean test for leadership (not the class):** for a real event,
  personally invite half of the students the app ranks as good fits, leave the
  other half to the usual channels, and compare sign-ups.
- **Decision:** Ann with the team at the Nov 20 review, based on whether the
  exercise was finished and tested on time and whether the team has room in
  spring. Her text: until then, no CBACH work beyond the optional
  five-questions mock-up. How that sentence sits beside the CBA platform track
  is an open item for the owner, not a change to the "Parallel tracks" note
  above; see the alignment section of the
  [correspondence record](../decisions/stakeholder-correspondence-2026-09.md#alignment-check-2026-09-28).

## Changed since 15 September

The decision named in each row is the authority. Do not build from the
15 September wording for these points.

| Topic | 15 September text | Now | Authority |
|---|---|---|---|
| Default weights | "the default settings" (no numbers) | 0.25 each | OQ-CE-02 (Ann, 2026-09-25) |
| Weight display | not specified | Total of the four weights plus the "counts twice as much" sentence; no percentages | Owner ruling 2026-09-28; ADR-0025 D8 |
| Profile card | "five quick questions" | Two questions (interests, career goal); major confirmed | OQ-CE-11; decision record D14 |
| License line | Ann to provide | Fixed wording on the opening screen | OQ-CE-09; D13 |
| Results-rule strengths | "only a little", "small lift", "small element of chance" | Ann's a lot / some / a little / some randomness, as numbers | OQ-CE-03; D7 |
| Undecided career goal | not specified | Half credit on broad (exploratory) events, in matching and results | OQ-CE-14; D2 |
| "Asking for more" percentages | 30 / 55 / 80 + 15, "illustrative" | Confirmed; halves round up; non-responders drawn only from those without a card | OQ-CE-04; D12 |
| Last tie-break step | "a fixed random order" | Ann's `tiebreak_order` column | D3; ADR-0025 amendment of 2026-09-25 |
| Copied card on refresh | copied from hidden true interests | Hidden true interests **and** hidden true career goal | OQ-CE-13; D6 |
| Test profile | an Accounting major interested in "product design" | Ann's P004 (interest in technology); kept as built | OQ-CE-15; D9 |
| Empty seats | "seats still empty" | Show the 8 already coming and the team's attendees separately | OQ-CE-16; D8 |
| Data file | "a spreadsheet file" | Ann's `.xlsx`, uploaded as sent | OQ-CE-05; D1 |
| Stable address | "a stable web address" | `exercise.plated.blog` (rate-limit half still open) | OQ-CE-06 |
| Passcode, two tabs per team | not specified | Env-set passcode; one shared workspace per team number | OQ-CE-07, OQ-CE-08 |
| Per-team reset | a team's own reset | Behind the instructor passcode | Owner ruling 2026-09-19 |
| How the data is described | "follows the real shape of the business school" | "Fictional profiles shaped by overall survey percentages." | D15 |

Decision records: [`class-exercise-decisions-2026-09-25.md`](../decisions/class-exercise-decisions-2026-09-25.md).
Register: [`class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md).

## Phase two (logged, not built for the exercise)

The team's proposed speaker workflow (Speaker Connector curates speakers;
speakers create accounts by invitation only; Event Host creates events and runs
matching over the speaker database) is, in Ann's words, "cleaner than what we
have" and "phase two". It is logged in [`../plans/backlog.md`](../plans/backlog.md).
On the CBA track, B26 track T6b has since built invitation-only speaker
accounts behind the `SPEAKER_PORTAL` capability, off by default; see the
correspondence record's alignment check.

## Where the rest lives

- Architecture: [ADR-0025](../architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md).
- Design spec: [`../superpowers/specs/2026-09-16-class-exercise-design.md`](../superpowers/specs/2026-09-16-class-exercise-design.md).
- Visual system and owner rulings: [`../design/class-exercise/DESIGN.md`](../design/class-exercise/DESIGN.md).
- Open questions for this scope: [`../plans/open-questions/class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md).
- Emails from Ann and the alignment check: [`../decisions/stakeholder-correspondence-2026-09.md`](../decisions/stakeholder-correspondence-2026-09.md).
