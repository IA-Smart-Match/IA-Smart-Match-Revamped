# Stakeholder correspondence, September 2026

**Status:** record. Holds three emails verbatim, as supplied by Danny (owner) on
2026-09-27, plus what each one settles and an alignment check against the repo.
This file decides nothing new. Where an email answered a register row, the
register row is the authority.
**Recorded:** 2026-09-28.
**Scope:** `ProductScope.CLASS_EXERCISE`, plus the speaker-workflow proposal
(CBA platform track).
**Requirements authority:** [`../product/class-exercise-requirements.md`](../product/class-exercise-requirements.md).
**Register:** [`../plans/open-questions/class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md).

**Attachments are held off-repo.** Ann's two Word documents of 2026-09-15
("Class Exercise and Build Requirements", "Background Note") are proprietary;
they are not committed and `test_data/*.docx` is git-ignored. Their content is
paraphrased in the requirements file. Ann's two data workbooks are held off-repo
in their original form; copies with the Read Me and Benchmark tabs removed are
committed as test fixtures under decision D4
([`class-exercise-decisions-2026-09-25.md`](class-exercise-decisions-2026-09-25.md)).

---

## A. Janice's question to Ann Wang

- **From:** Janice (the team)
- **To:** Ann Wang
- **Date:** undated; sent before B, about mid-September 2026
- **Attachments:** none

> We had a few questions regarding the direction we are to lead SmartMatch in.
>
> If we pivot the direction of the app to be focused on connecting students with the right events, how will that affect the teaching module that you discussed at the beginning of the year?
> Which part of our project do you want to keep for the marketing class? We heard that you enjoy the idea of AI matching and AI ranks and would like to keep them for students to see how AI may be applied in marketing; however, if we pivot to prioritize student matching, would this still be similar to what you envisioned?
> Do we focus on building whatever that can help you with the classroom modules first? Or should we listen to Dr. Sandeep's request to match students to events first?
>
> We were hoping on seeking some clarification on the roles as well when it came to matching our volunteers to events.
>
> We thought that the current pipeline involved too much reliance on back-n-forth communication that may impede the benefits of AI matching. For example:
> Speaker Connector reaches out to speakers externally and logs who can come to a certain event.
> Then after garnering a list, the Connector can send the list of speakers to the event host.
> The event host then picks the best speaker from a ranked list of pre-approved speakers
> The event host then sends the request back to the Speaker Connector to approve.
>
> Instead of this approach, we ask that instead we could have:
> Speaker Connector can curate a list of speakers, and the speakers make their account from INVITE-ONLY (to remove any outside, external, untrusted possibilities)
> Event Host can make new events & run the AI matching to find the best speaker out of all the speakers found in the database.
>
> Let us know what you think, and are we still meeting on Friday?
> I may not be available due to a meeting.

### What this settles

Nothing on its own; it is the question list B answers. It is the origin of the
invite-only speaker proposal.

---

## B. Ann Wang's reply

- **From:** Ann Wang
- **To:** Janice and the team
- **Date:** undated; about 2026-09-15 (the two files it refers to are dated
  2026-09-15)
- **Attachments:** "Class Exercise and Build Requirements" and "Background
  Note", both 2026-09-15 — held off-repo (see above)

> Thank you for the questions. I know there have been some twists and turns since August, and I want to say clearly: none of your work is wasted. The matching engine, the saved settings, the dashboard, and the back end you are rewriting are exactly what we build on. What changes is who gets matched to what, not how.
> Right now it makes more sense to focus on the student end: matching students to events, and helping a marketer see what the app knows about each student and who is being left out. I have put together two files for you as references. The first, "Class Exercise and Build Requirements," describes the class exercise Dr. Lin's AI in Marketing course will run in spring, what the app must do for it, and who does what on the team. Please read the build table and your own section under "Who does what" first; the rest is context. The second, "Background Note," is what the class participants will read before the exercise. It is not for you to build anything from; it shows you what they will understand about the tool when they sit down to use it.
> To your three questions. The pivot to student-to-event matching does not hurt the class module; it is the class module. The parts I want kept for the class are the matching engine with its adjustable weights, the ranked list with a reason next to each name, and the results screen; all three are in the requirements file. And there is one direction, not two: build what the requirements file describes. That is what serves the college and what I will teach with. Please do not build anything for the classroom that the college would not use.
> On the speaker workflow you proposed: it is cleaner than what we have, and I like invite-only for trust. It is also phase two. Please log it in the backlog; I will bring it to Pia and Lisa with the other consolidated questions when we get there.
> On meetings: let us keep the Friday 11 AM slot as our weekly check-in. If there is nothing new to show in a given week, tell me by Thursday and we skip it. The dates in the requirements file are my planning markers; I will tell you which ones matter as we get close. If you need to meet sooner, including tomorrow, say so and we will find a time.
> Yes, we meet this Friday. Janice, if your other meeting runs over, send me your questions beforehand and I will circulate notes.

### What this settles

1. **Keep for the class:** the matching engine with adjustable weights, the
   ranked list with a reason per name, and the results screen.
2. **Build what the requirements file describes** — it is the class-exercise
   scope authority ([`class-exercise-requirements.md`](../product/class-exercise-requirements.md)).
   Her "one direction, not two" sentence is an open item for the owner; see
   [Owner decisions needed](#owner-decisions-needed).
3. **Invite-only speaker workflow = phase two.** Logged in
   [`../plans/backlog.md`](../plans/backlog.md); Ann takes it to Pia and Lisa.
   No Pia/Lisa answer is recorded yet.
4. **Weekly check-in: Fridays 11 AM.** Tell Ann by Thursday to skip a week with
   nothing to show. The repo has no other meeting-cadence record, so this file
   is where the rule lives.
5. **The requirements dates are planning markers**; Ann says which ones matter
   as they approach.

---

## C. Ann Wang, dataset email

- **From:** Ann Wang
- **To:** the team
- **Date:** about 2026-09-24 (the register records the cover email and the Read
  Me on 2026-09-24; the 300-row file arrived 2026-09-24/25)
- **Attachments:** `SmartMatch_Student_Body_Sample_20.xlsx`,
  `SmartMatch_Student_Body_300.xlsx` — originals held off-repo; stripped copies
  are test fixtures (D4)

> Dear Team,
>
> Attached are two files of made-up students for the class exercise:
> SmartMatch_Student_Body_Sample_20.xlsx: 20 rows to start testing
> SmartMatch_Student_Body_300.xlsx: the full 300 rows, plus the 12 events
> The column names are final, and the "Read Me" sheet explains each column. A few things to know:
> Every row is fictional. No real student is in either file (however, I did borrow the distribution of the recent student survey of 1,370 students)
> Pink columns are hidden. The app must never show them or use them for matching. They are used only by the results rule and the profile refresh.
> The sample is part of the full file, with the same IDs and values, so anything you build on the sample will work on the full file.
> Test case: P004 is an Accounting major whose profile card states an interest in technology. For the Northline event, it should rank above a plain Accounting major when "said they are interested" is turned up, and not when it's turned off.
> The mix of majors, interests, and event attendance is based on this fall's Career Readiness Survey, adjusted for the majors in our college.
> For questions, quick ones on Teams are fine. Anything that changes the plan or the dates, please send by email so we have a record.
> Best,

### What this settles

1. **Column names are final** — OQ-CE-01 closed 2026-09-24.
2. **Hidden (pink) columns never shown, never matched on**; read only by the
   results rule and the refresh — ADR-0025 D6 and its 2026-09-25 amendment;
   OQ-CE-13 / D6.
3. **Sample ⊂ full file** with the same IDs — both are fixtures (D4).
4. **P004 test case** — OQ-CE-15 / D9: the first half holds; the second half
   ("and not when it's turned off") does not, as built. Chau approved keeping
   it; Ann may revisit.
5. **Process:** quick questions on Teams; anything that changes the plan or the
   dates goes by email so there is a record. The data description stays D15's
   sentence.

---

## Alignment check (2026-09-28)

Emails A–C and the 15 September requirements against `origin/main` at
`19b110eb`. Paths are shortened:

- `domain/` = `python/smartmatch_domain/smartmatch_domain/`
- `api/` = `services/api/smartmatch_api/routers/`
- `web/` = `apps/web/legacy-frontend/src/app/pages/exercise/`

Status: **built**, **partly**, **missing**, **conflicts**. Conflicts and missing
items come first.

| # | Requirement or statement | Status | Evidence | Action |
|---|---|---|---|---|
| 1 | Ann (B): "one direction, not two … do not build anything for the classroom that the college would not use"; requirements: "no work on the CBACH scope beyond the optional five-questions mock-up" until 20 Nov | **conflicts** (wording) with the owner's standing ruling that the CBA track and the exercise run in parallel | `docs/product/class-exercise-requirements.md` "Parallel tracks"; ADR-0026 (Proposed) blockquote: "Both stakeholder tracks proceed"; B26 plan and T6b work on main (row 2). ADR-0018 is the import-linter ADR and has no bearing. | **Owner decision.** No ADR, status or paragraph changed here. |
| 2 | Ann (B) and build table "Not now": invite-only speaker accounts are phase two, pending Pia and Lisa | **conflicts** — already built on the CBA track, capability off | `python/smartmatch_domain/smartmatch_domain/product_scope.py:245` `SPEAKER_PORTAL`, `:284`/`:313`/`:349` default `False`; `api/speaker_portal.py`; `db/migrations/versions/0039_speaker_portal.py`; B26 plan track T6b; decisions INDEX open gate 3 | **Owner decision:** keep `SPEAKER_PORTAL` off until Pia/Lisa answer. Backlog row updated. The event-host "match over the whole speaker database" half is the existing CBA matcher. |
| 3 | Hosting: stable address, under 5 s in Chrome; Oct 2 needs matching "working on the demo site with the full data" | **missing** — not deployed | `docs/plans/backlog.md` row "Class-exercise VM deploy" (blocked 2026-09-26: no `deploy` branch, env secrets, DNS, rate-limit rule); PR #253 open (`fix/vm-deploy-keeps-exercise`); load time never measured | Owner steps in `docs/operations/exercise-hosting.md` §9 before **Fri Oct 2** (4 days). |
| 4 | No-login routes rate-limited (hosting half of OQ-CE-06) | **missing** | `services/api/smartmatch_api/exercise_rate_limit.py` `PLACEHOLDER (OQ-CE-06)`; register row OPEN | Apply the proxy rule at deploy. |
| 5 | P004 (C): above a plain Accounting major with the interest factor up, **not** above with it off; requirements example says "product design" | **conflicts** (accepted deviation) | `tests/golden/exercise/test_exercise_ann_dataset_golden.py:157` (card names "Technology / information systems"), `:161` up → above, `:178` off → still above on career goal, `:188` information tie-break; OQ-CE-15 / D9. "Product design" is not one of the 13 topics (`domain/exercise/vocabulary.py:119`), so the email's case replaces the doc's example. | Tell Ann at a Friday check-in that the second half does not hold and why (D9); she may revisit. |
| 6 | Team numbers 1–6; class size "could be 5 or 8" (Ann confirms by Oct 2) | **partly** | `domain/exercise/__init__.py:37` `EXERCISE_TEAM_NUMBERS = (1, 2, 3, 4, 5, 6)` | If Dr. Lin says 8 teams, change the tuple (and its tests) before Oct 16. |
| 7 | Justin: one-page, no-code write-up of the results rule, the three choices and the refresh, before the Nov practice run | **partly** | Rule in words in `domain/exercise/simulation.py:1` docstring; numbers in `docs/archive/plans/open-questions/oq-ce-03-sample-result.md`; no single one-page write-up found | Justin writes it before the week of Nov 9. |
| 8 | Weight display: total of the four weights plus "counts twice as much" sentence; no percentages; no forced sum of 1 | **partly** | Not on main; branch `feat/exercise-weight-total`. Weights are relative today (`domain/weight_settings.py:33` divides by the total); ADR-0025 D8 forbids percentages | Merge the separate PR. |
| 9 | If time: per-profile points counter | **partly** | `web/ProfilePointsCounter.tsx:78` exists, not routed; `domain/exercise_points.py`; DESIGN.md §11 item 4 "Deferred" | None for Oct; backlog row stands. |
| 10 | "Asking for more": 30 / 55 / 80 percent, 15 percent stop responding under "required" | **built** | `domain/exercise/asking.py:82-84` shares, `:92` `REQUIRED_NON_RESPONDING_SHARE = 0.15`, `:191` half-up count; OQ-CE-04 (Ann: "All good") | None. |
| 11 | Results rule: true fit matters most; frequent attenders "only a little"; major a small lift; chance fixed per team | **built** (numbers per Ann's later words) | `domain/exercise/simulation.py:471` `EXERCISE_SIMULATION_COEFFICIENTS`; OQ-CE-03 / D7 (a lot +0.40, some +0.10 for ≥1 past event, a little +0.04) | None. Ann's 9-25 "some" supersedes the doc's "only a little". |
| 12 | Default weights (doc: "the default settings") | **built** | `domain/exercise/registry.py:133-136` 0.25 each; OQ-CE-02 (Ann, 2026-09-25) | None. |
| 13 | Getting in: no login, team number, per-team workspace surviving reload; instructor page behind passcode | **built** | `api/exercise_workspace.py:202` enter, `:177` httpOnly session cookie; `api/exercise_instructor_session.py:124` login; OQ-CE-07, OQ-CE-08 | None. |
| 14 | Data: load Ann's file, instructor re-upload, plain error on a missing column | **built** | `api/exercise_instructor.py:189` upload; `domain/exercise/ingest.py:171`, `:201` missing-column refusal; `domain/exercise/workbook.py` (xlsx, D1) | None. |
| 15 | "How much we know" marker and "who is on the list" table (+ if-time empty-group notice) | **built** | `domain/exercise/markers.py:60` `InformationMarker`, `:156` `list_composition`; `web/ListCompositionTable.tsx:48`, `web/ListCoverageNotice.tsx:33` | None. |
| 16 | Matching: four factors, reason lines, tie-break, cap 30, three saved settings, side by side | **built** | `domain/exercise/matching.py:186` score, `:297` tie-break; `python/smartmatch_persistence/smartmatch_persistence/exercise/schema.py:130` `invite_limit` default 30; `.../settings_repository.py:73` `MAX_SAVED_SETTINGS_PER_EVENT = 3`; `api/exercise_matching.py:503` compare; `web/MatchingCompareView.tsx:38` | None (Oct 2 code items done; site item is row 3). |
| 17 | Download the list with reasons | **built** | `api/exercise_matching.py:428` `download_ranked_list` (`list.csv`) | None. |
| 18 | Results lock, one run per team per event | **built** | `api/exercise_instructor.py:405` unlock; `api/exercise_results_run.py:332` `already_run` | None. |
| 19 | Comparison: "email everyone", round-one result in round two, seats still empty (+ if-time bar chart) | **built** | `domain/exercise/simulation.py:647` `run_email_everyone`, `:676` seats; `api/exercise_results.py:150` round one; `web/ResultPanels.tsx:41`, `:101` chart | None. |
| 20 | Asking-for-more choice, per-team refresh, instructor refresh-all, per-team reset (+ if-time card mock-up) | **built** | `api/exercise_results.py:371` choose, `:430` refresh; `api/exercise_instructor_refresh.py:96`; `api/exercise_instructor.py:538` reset (instructor-only, owner ruling 2026-09-19); `web/ProfileCardMockup.tsx` (two questions, OQ-CE-11) | None (Oct 16 code items done; Ann's run-through needs row 3). |

### Milestones against the build

| Date | Code on main | Blocker |
|---|---|---|
| Fri Oct 2 | Rows 12–17 built | Row 3: not on the demo site. Ann owes spring week and class size (row 6). |
| Fri Oct 16 | Rows 10, 11, 18–20 built | Row 3: Ann cannot run both sessions without the site. Row 4 should be applied first. |

## Owner decisions needed

1. **"One direction, not two" (row 1).** Ann's sentence and her "no CBACH work
   until 20 Nov" line read against the standing parallel-tracks ruling. Decide
   whether to answer Ann, and how. This record changes no ADR and no status.
2. **Speaker portal ahead of phase two (row 2).** Confirm `SPEAKER_PORTAL` stays
   off, and no real Speaker is invited, until Pia and Lisa answer.
3. **Deploy before Oct 2 (rows 3–4).** Owner steps in `exercise-hosting.md` §9;
   passcode and secrets are the owner's to set.
4. **P004 (row 5).** Whether to tell Ann that the "turned off" half does not
   hold as built.
