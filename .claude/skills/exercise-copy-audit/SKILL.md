---
name: exercise-copy-audit
description: Use when writing, changing or reviewing any sentence a student sees in the Smart Match class exercise (apps/web/legacy-frontend/src/app/pages/exercise), when Dr. Wang (Ann) sends wording feedback, when copy "sounds AI-generated", or when students lose track of which round they are in.
---

# Exercise copy audit

## Overview

Students read every sentence once, under time pressure, with no one to ask.
A sentence passes only if a first-year student can say **who does what, and
what to do next** after one read. Dr. Wang's exact wording always wins over
this rubric.

Files in this folder:

| File | What it is |
|---|---|
| `extract-copy.mjs` | Lists every student-facing string with `file:line`. Node stdlib, no install. |
| `glossary.md` | One word per thing. The audit checks every string against it. |
| `ann-verbatim.md` | Strings Ann specified. They must appear exactly. |

## Where the copy lives

- Student pages: `apps/web/legacy-frontend/src/app/pages/exercise/*.tsx` (+ `desk/`).
- Sentence builders: `*Wording.ts`, `listCoverageNotice.ts`, `askingChoices.ts`, `refusals.tsx`.
- Server sentences shown as-is: `services/api/smartmatch_api/routers/exercise_*.py`
  (refusal `detail` strings) and `python/smartmatch_domain/smartmatch_domain/exercise/` (reason lines).
- Not student copy: `Instructor*.tsx`, `*.test.tsx`, comments. The extractor skips them.

## Run it (Claude or Codex, from the repo root)

1. `node .claude/skills/exercise-copy-audit/extract-copy.mjs > /tmp/copy.md` — every string, `file:line | text`.
2. `node .claude/skills/exercise-copy-audit/extract-copy.mjs --banned` — internal words and "Step" (FAIL, exit 1) plus model-talk tells (warn).
3. `node .claude/skills/exercise-copy-audit/extract-copy.mjs --verbatim` — every Ann string present? (exit 1 if any missing).
4. Read the table from step 1 page by page against the rubric below. The script finds words; only reading finds semantic gaps.
5. For server sentences, `grep -rn 'detail=' services/api/smartmatch_api/routers/exercise_*.py` and read the reason builders.
6. Write the report in the shape under "Output".

## Rubric

Each rule comes from a correction Ann made in her 2026-10-16 feedback.

| # | Rule | Ann's example (before → after) |
|---|---|---|
| R1 | One term per thing, from `glossary.md`. "Round", never "Step". | "Name these weights" → "Give this setting a name" |
| R2 | Every sentence says who does what. Name the actor (you, your team, CBACH, your instructor). | "Saves the 4 numbers now on screen." → "Saves the four slider numbers at the top of this page under this name." |
| R3 | Numbers agree across screens and name their unit. Two numbers for one idea get two labels. | "added 4" and "added 7" → "Your list brought 7 extra sign-ups; 4 of them came." |
| R4 | No "this/it/that" without its noun on screen. | "Save the weights on screen to fill it." → "Save a setting to fill this slot." |
| R5 | No internal words: slot, workspace, factor, refresh, sequence, cap. | "Slot 1 of 3 is free." → "Empty. Save a setting to fill this slot." (Ann's own use of "slot" is the one exception) |
| R6 | Status text says where the team is and what to do next. | "Checked at 1:57" → "Your instructor has not opened results yet. … Press Check again once your instructor says results are open." |
| R7 | Instructions ≤ 20 words a sentence, grade-8 words. Explain the cost in plain words. | "Stopped responding" → say they stop opening messages and will not sign up. |
| R8 | A caption describes the chart actually drawn. | "Mass email alone beside your CBACH emails on top of it." → "Light bar: mass email alone. Dark bar: mass email plus your CBACH emails." |
| R9 | No model talk: "Note that", "simply", hedges, em-dash chains, a colon before every list, three-part rhythm, restating the heading. | — |
| R10 | Gaps get a sentence. If the screen shows a result students will ask "why?" about, say why. | Ties: "Explain what decides the fixed order, or order all ties by class year." |

Quick test per sentence: read it aloud as the TA. If you would add words to
explain it, those words belong on screen. If you would drop words, drop them.

## Output

Save as Markdown. Shape:

1. **Verdict line**: `PASS` or `FAIL — N must-fix, M later`, plus the three command exit codes.
2. **Findings table**: `| file:line | current text | rule | problem | proposed text | owner |`.
   One row per string. Proposed text is a full sentence ready to paste. Ann's verbatim text, where it exists, is the proposed text.
3. **Verbatim check**: the `--verbatim` output.
4. **Out of scope**: rows for files another person or track owns, so they can pick them up.

FAIL if any `--banned` FAIL row, any missing verbatim string, or any R2/R3/R6 finding remains.

## Common mistakes

| Mistake | Fix |
|---|---|
| Rewording Ann's text to fit the rubric | Her text is final. Add it to `ann-verbatim.md` and move on. |
| Hard-coding "30" or "60" in a sentence | Read the number from the response; the list size changed once already. |
| Fixing the string but not its test | `grep -rn '<old text>' apps/web/legacy-frontend/src apps/web/legacy-frontend/tests` and update every match. |
| Trusting the extractor's silence | It misses sentences split by JSX across lines. Read the page component too. |
