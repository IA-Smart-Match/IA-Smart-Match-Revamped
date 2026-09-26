# Handoff: class-exercise orchestrator, 2026-09-26

**This file is untracked. Never stage or commit it.** Its companion folder, `docs/plans/prompts/ce-handoff-2026-09-26-scratch/`, is untracked too.

Output style: follow ~/.claude/rules/common/subagent-output.md (i-have-adhd).
Every Agent prompt you write must include that line.

---

## 0. Your first 5 actions
1. Read this whole file. Then read `docs/decisions/class-exercise-decisions-2026-09-25.md`: Part 1 is plain words, Part 2 has D1–D16.
2. Run `git fetch origin && git log --oneline -3 origin/main`. Expect `de8bc66e` or later, and **no open exercise PRs**.
   - **Paths follow the docs consolidation** (branch `docs/consolidation-2026-09-26`). Check whether it has merged: `git ls-tree origin/main docs/archive/design/class-exercise`.
     - Non-empty: use the paths in this file as written.
     - Empty: the consolidation hasn't merged yet. Use the **pre-consolidation paths** in the §8 path table.
   - Read `docs/INDEX.md` (the canonical index) and `docs/archive/INDEX.md`. Archive files are dated and not canonical: read them, never edit them.
3. Run `ls /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/.venv/bin/ruff`. If it is missing, run `make setup` first.
4. Dispatch the **Stitch MCP subagent** (§5). The owner asked for it explicitly.
5. Ask the owner the 3 go-aheads in §4 that need a person: VM deploy, pilot-row cleanup, Ann messages.

---

## 1. What the product is (context)
- The repo serves 2 parallel tracks:
  - the **CBA platform**, which is never parked
  - the **class exercise**: a no-login classroom game for Dr. Ann Wang and Dr. Lin's Spring 2027 "AI in Marketing" course at Cal Poly Pomona, College of Business Administration.
- **How the class plays:**
  1. Student teams, numbered 1–6, set 4 weights: same major, went to similar events before, said they are interested, career goal fits this event.
  2. The app ranks 300 **fictional** profiles and invites the top 30 to Northline (E11, round 1), then Harbor (E12, round 2).
  3. Each team saves up to 3 settings, compares 2 with overlaps highlighted, then picks a final setting.
  4. The instructor unlocks results. The team runs once and sees sign-ups, attendance and seats. Outcomes are driven by hidden true interests the team never sees.
  5. The team "asks for more": ask nicely 30%, offer points 55%, or require it 80% with 15% who stop responding. Then round 2.
- **Wording rule (Ann, 2026-09-25):** describe the data only as "fictional profiles shaped by overall survey percentages". Never mention real students, respondents or individual responses. **The repo is PUBLIC.**
- **Authorities:**
  - requirements: `docs/product/class-exercise-requirements.md`
  - register: `docs/plans/open-questions/class-exercise-open-questions.md`
  - ADR-0025, plus its 2026-09-25 amendment
  - design spec: `docs/superpowers/specs/2026-09-16-class-exercise-design.md`
  - design package: `docs/design/class-exercise/`

## 2. Finished this session (all merged to main)
| PR | What |
|---|---|
| #227 | A results run requires a saved final setting (422 `exercise_final_setting_required`) |
| #228, #229 | Ann's real data file:<br>- xlsx upload (openpyxl + defusedxml, zip-bomb guard)<br>- migration **0042**: `hidden_true_career_goal`, `tiebreak_order`<br>- class-year rank<br>- role→topic table<br>- OQ-CE-01, OQ-CE-05 and OQ-CE-13 closed |
| #230 | Ann's answers:<br>- license line constant<br>- reason lines<br>- 30/55/80%, rounded half up<br>- profile card with 2 questions plus "confirm your major"<br>- points 1/1<br>- "fictional" banner<br>- OQ-CE-02/04/07/08/09/10/11/12 closed |
| #231 | Fixture xlsx stripped to the Profiles and Events tabs. Git history is kept, by owner decision. |
| #232 | Instructor-only events list and unlock panel (`GET /v1/exercise/instructor/events`) |
| #233 | Results rule. D7 coefficients:<br>- base 0.04<br>- true fit +0.40 (half interests, half goal)<br>- attended ≥1 event +0.10<br>- same major +0.04<br>- chance spread 0.20<br>- attend given signup 0.75<br><br>Undecided goal gets half credit on exploratory events, via migration **0043** `exercise_event.is_exploratory`.<br>Sample: `docs/archive/plans/open-questions/oq-ce-03-sample-result.md` |
| #234 | `make exercise-seed`, plus a guarded dev-only seed-on-start (6-condition allow-list; refuses on the VM) |
| #235 | "Ask them now" stays disabled until round-1 results exist. Unlock-panel L1–L3 fixes. |
| #236 | Decision record D1–D16 and the ADR-0025 amendment. OQ-CE-03, OQ-CE-15 and OQ-CE-16 closed. |
| #237 | Design package, direction **"The invitation desk"**.<br>Live in `docs/design/class-exercise/`:<br>- `DESIGN.md`<br>- `experiments.md`<br>- `assets/svg/`<br><br>Archived by the consolidation in `docs/archive/design/class-exercise/`:<br>- `prompts/` (19 prompt files + `README.md`)<br>- `assets/mockups/` (8 Fable PNGs)<br>- `assets/generated/claude-html/` (24 WebP renders)<br>- `generated.md` |
| #238 | D8 seat wording ("8 were already coming. Your invitations added 6. 46 seats are still open."). 6-team full-class integration test. Register IDs removed from the public OpenAPI. |
| #240 | Non-responders kept separate from card-completers (owner ruling). `undecided_goal_half` flag. Refresh counts on the asking GET. Plain all-zero-weights wording. Chart scroll box. |
| #239 | Teams panel auto-refresh. Table scroll on phones. Undecided chip. Saved counts rendered. Save disabled at 3/3. "Skipped N" reason. |

**Verification done:**
- M1 API full class: 271/273 checks passed, and the 2 misses were script errors.
  - Round 1 averaged 9.5 signed and 6.3 attended.
  - Refresh landed at 28.6%, 56% and 81%.
  - 0 leaks, 0 5xx.
- M2 browser walkthrough: the flow passes end to end. It found B1–B6, and all are fixed in #239 and #240.
- The full-class integration test now has 27 tests, and it runs in CI.

## 3. Owner and stakeholder decisions (don't re-ask)
- D1–D16 are in the decision record, with who decided and why.
- **Later rulings (2026-09-25/26):**
  - Non-responders are disjoint from card-completers (15% of all no-card profiles).
  - Data ribbon label: **"Fictional data"**.
  - Weights: a **slider 0–1, step 0.05, plus a number box**.
  - Asking choice: an **inline confirm**, about 5 s, no pop-up.
  - Visual refresh: **generate image mock-ups first**, then the owner decides whether to build.
- **Chau** approved: the D7 numbers, D8 "show both groups", D9 "P004 keep as built".
- Ann's answers are cited as "Ann Wang, email reply, 2026-09-25".

## 4. Unfinished work, in priority order
### Needs an owner go-ahead
1. **VM deploy** to `exercise.plated.blog`:
   - The compose command needs both `-f` files and `--build`. See memory "VM compose needs both -f files".
   - After deploy, **re-upload Ann's file**. Datasets from before 0043 read every event as not exploratory, so Undecided gets no credit.
   - Set the VM's own `SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE` (a 12-char minimum). Never reuse the local one, and never print it.
   - OQ-CE-06: the proxy rate-limit rule is still **not applied**. `exercise_rate_limit.py` is a PLACEHOLDER.
2. **Local DB cleanup.**
   - 3 pilot-tenant `cba_invitation_batch` rows block integration-test setup locally. I asked the owner "clear?" and got no answer yet.
   - The leftover DBs `smartmatch_m2`, `smartmatch_exverify` and the B26 `smartmatch_b26_*` / `smartmatch_*` scratch DBs can be dropped once the owner OKs it.
3. **Messages to Ann and Chau**, drafted by the owner. Nothing is sent by agents.
   - The sample result doc, as information.
   - Part 1 of the decision record.
   - The 25 new UI strings in `DESIGN.md` §11.1.
   - The results-chart question: the team's 30/6/4 bars sit on the same scale as the 300 bars, so they're slivers.

### Engineering: ready to dispatch
4. **Stitch mock-ups** (§5): the owner's explicit next step.
5. **After the owner reviews the mock-ups: build "The invitation desk" page by page.**
   - Follow `docs/design/class-exercise/DESIGN.md`: tokens in §3, motion in §5, components in §6, layouts in §7.
   - Libraries are already installed: `motion` 12.23, Radix (including slider), Recharts, lucide-react, Sonner.
   - The weights UI is **text inputs today**. The slider is new UI, whatever the library scout said.
   - Build it as a parallel set of per-page tracks in worktrees, with one owner per file.
6. **LOW follow-ups:**
   1. The Teams panel doesn't sign out on a 401 (`InstructorTeams.tsx`; pass `onSignedOut`).
   2. The Undecided label is copied client-side. Send it as a `factor_labels` entry from the server.
   3. Server and results-page wording says "refreshing" and should say "asking" (`ExerciseResults.tsx` and the server sentences).
   4. Split `tests/unit/test_exercise_results_router.py`, which is about 2,000 lines against an 800 cap.
   5. `exercise_dataset.license_line` is unused. It has a backlog row: retire it, or make it a per-file addendum.
   6. Other items:
      - names are lost if a setting is deleted after a run
      - every tab title is "IA West SmartMatch CRM"
      - the screen never shows which team you are
      - "email everyone" differs between teams
      - the invited-names list is not in rank order
      - a 404 on results before the first run shows as console noise

## 5. Stitch MCP subagent: brief to adapt and dispatch
Goal: connect Claude Code to **Google Stitch**. Then:
1. Generate Stitch versions of the prompts in `docs/archive/design/class-exercise/prompts/`.
2. Compare them with the HTML renders in `docs/archive/design/class-exercise/assets/generated/claude-html/`.
3. Record the results in a NEW live contact sheet. The archive is read-only.

Known state:
- The `stitch` skill exists in the skill list ("healthcheck, generate, integrate"), but it depends on a `google-stitch-frontend-mcp` skill and a Stitch MCP server. **Neither is configured**, so the healthcheck failed on 2026-09-26.
- Higgsfield's session expired. `hf auth login` is interactive and needs the owner.

Steps for the subagent:
1. Research the **official** Google Stitch MCP server and its install and auth steps (WebSearch or WebFetch). Only use a source that is Google's own, or that Google's docs link to. Report the exact `claude mcp add …` command and any API key or OAuth step.
2. **Do not edit settings or MCP config yourself, and do not paste secrets.** Hand the owner the exact command to run as `! <command>`, or for a separate terminal if it's interactive. Keys go in env or the OS keychain, never in the repo.
3. After the owner connects it, verify: invoke the `stitch` skill's healthcheck. If the skill still needs `google-stitch-frontend-mcp`, find its install path and report it the same way (owner runs it).
4. Generate the prompts, in this order:
   1. pages `08-final-setting-and-results`, `04-ranked-list-and-sliders`, `05-save-and-compare`, `09-asking-for-more`, at 1280 and 390
   2. the remaining pages at 1280
   3. the 8 components
   - Always prepend the shared style preamble from `docs/archive/design/class-exercise/prompts/README.md`, and use the shared fictional data.
   - Tokens and rules come from the live `docs/design/class-exercise/DESIGN.md`. If the archived prompts and DESIGN.md disagree, DESIGN.md wins. Note each disagreement.
5. Reject any output with:
   - wrong brand colours (CPP green `#005030`, gold `#ffb81c`, eggwhite page)
   - fake UI text
   - photos of people
   - per-person percentages or scores
   - any "real student" wording

   Regenerate a rejected output once, then keep the best version and note its flaw.
6. Save to the LIVE folder `docs/design/class-exercise/assets/stitch/<prompt>-<width>.webp`, about 30 images at most.
   - Write a new live contact sheet, `docs/design/class-exercise/stitch.md`. For each image give the prompt path (archived), the tool, and a one-line fidelity note, and compare it with the matching archived HTML render.
   - Do NOT edit anything under `docs/archive/`.
   - If Stitch can export HTML or Tailwind, save it under `docs/design/class-exercise/assets/stitch/code/` for reference only. Do not wire it into the app.
   - Add 1 line to `docs/INDEX.md` pointing at `stitch.md`, if INDEX lists design docs.
7. Open 1 docs PR on `design/ce-stitch-mockups`. Write the PR body to a unique scratch file.
8. Report back: the connection steps done, images per page, rejects, and the 3 strongest images.

## 6. Blockers and environment gotchas
| Blocker | Workaround |
|---|---|
| Stitch MCP not configured; Higgsfield session expired | §5, the owner runs the auth |
| chrome-devtools MCP is unusable (port 9222 is a Windows WebView) | Playwright headless: `/tmp/t6b4-pw` + `~/.cache/ms-playwright/chromium-1232`. If `/tmp` was wiped, reinstall Playwright into the scratchpad |
| The `/mnt/c` 9p mount can die with "Input/output error" | The owner runs `sudo umount -l /mnt/c && sudo mount -t drvfs 'C:\' /mnt/c -o uid=1000,gid=1000,symlinkroot=/mnt/` in a separate terminal. **Never `wsl --shutdown`**: it kills the session |
| Vitest on /mnt/c times out, and so does a node_modules symlink from another /mnt/c worktree | Run `npm ci` into the session scratchpad (Linux fs, about 30 s), symlink it, run `vitest run --pool=threads <file>`, then remove the symlink |
| Full test runs wedge on /mnt/c | Targeted files only, one pytest at a time. CI proves the suite (about 15–25 min) |
| Local DB pilot rows break integration conftest setup | Use a throwaway DB, then drop it |
| Codex is locked until 2026-09-28; Devin MCP returns Unauthorized | Opus review subagents are the review of record |
| GitHub can flag CONFLICTING even when a local merge is clean | Merge origin/main into the PR branch (never rebase) and push. That cleared #239 |
| The Artifact tool may be missing inside subagents | The orchestrator publishes |

## 7. Standing rules (each came from a failure)
1. Parallel agents run with `isolation: "worktree"`, `model: "opus"` for build and review, and the output-style line.
2. **Commit and push at every milestone.** Uncommitted work dies on rate limits and mount failures.
3. Branch from origin/main in a worktree. Never work in the parent checkout: on 2026-09-26 it sat on `docs/consolidation-2026-09-26` with a large staged docs move that belongs to the owner. Don't touch that branch or its index. Never rebase or force-push.
4. TDD: red→green commit pairs. Review: 1 Opus review round. **Any HIGH or MEDIUM fixed without re-review gets a round-2 verification review.**
5. A new migration updates the head pins AND `_REVISIONS_BETWEEN_HEAD_AND_THIS_CARD` in `tests/integration/test_cba_contact_schema.py`. Declare every new CHECK in `tests/integration/test_check_constraints.py`. `alembic_version` is `varchar(32)`.
6. The list-entry field set is pinned by `tests/unit/test_exercise_list_shape.py`. Adding a field there means updating that test in the same PR.
7. `hidden_true_*` must never reach a response, log, repr or CSV. No `OQ-CE-` string in user-facing text or OpenAPI; guard tests enforce this.
8. PR bodies go in a **uniquely named** scratch file, applied with `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/N -F body=@file`. `gh pr edit` fails silently. `gh pr checks N` takes no `--json`, and `gh api` takes no `-R`.
9. `ruff format` checks python fences inside .md files.
10. Keep files ≤ 800 lines. Put new tests in new files.
11. Agents don't merge and don't deploy. The owner merges. Relay each hand-back to the owner, verified against GitHub (`gh pr view N --json statusCheckRollup`).
12. `pgrep -f` matches its own shell. Use `ss -ltnp` to check ports.

## 8. Live resources

**Path table (docs consolidation, 2026-09-26).** Use the right column only if `docs/archive/design/class-exercise` is missing on origin/main.
| Thing | After consolidation (use this) | Before consolidation |
|---|---|---|
| Design spec (live) | `docs/design/class-exercise/DESIGN.md` | same |
| Experiments + library picks (live) | `docs/design/class-exercise/experiments.md` | same |
| SVG assets (live) | `docs/design/class-exercise/assets/svg/` | same |
| Image-gen prompts (19 + README) | `docs/archive/design/class-exercise/prompts/` | `docs/design/class-exercise/prompts/` |
| HTML-rendered mock-ups (24) | `docs/archive/design/class-exercise/assets/generated/claude-html/` | `docs/design/class-exercise/assets/generated/claude-html/` |
| Fable mock-ups (8) | `docs/archive/design/class-exercise/assets/mockups/` | `docs/design/class-exercise/assets/mockups/` |
| Mock-up contact sheet | `docs/archive/design/class-exercise/generated.md` | `docs/design/class-exercise/generated.md` |
| OQ-CE-03 sample result | `docs/archive/plans/open-questions/oq-ce-03-sample-result.md` | `docs/plans/open-questions/oq-ce-03-sample-result.md` |
| Earlier orchestrator handoffs | `docs/archive/plans/prompts/` | `docs/plans/prompts/` |
| New Stitch output (§5) | `docs/design/class-exercise/assets/stitch/` + `stitch.md` (live, new) | same |
| Unchanged | decision record `docs/decisions/…`, register `docs/plans/open-questions/class-exercise-open-questions.md`, `docs/plans/backlog.md`, requirements, design spec `docs/superpowers/specs/2026-09-16-class-exercise-design.md` | same |

The golden test `tests/golden/exercise/test_exercise_results_rule_sample_golden.py` parses the sample-result doc.
- On 2026-09-26 the consolidation's working tree already pointed that test, and `simulation.py:37`, at the archived path. Those edits were unstaged at the time.
- If CI fails with "file not found" on that doc after the merge, the test edit was left out. Point the test at the archived path. Never edit the archived doc.
- **The M2 browser stack is still running:** web http://127.0.0.1:5473/exercise and API :8390, on DB `smartmatch_m2`. Stop it with `pkill -f "port 8390"; pkill -f "vite --port 5473"` once the owner is done.
- **Local instructor passcode:** in the parent `.env` (gitignored). Never print it.
- **Claude Design canvas** (private, owner only): https://claude.ai/artifact/KQM1s4X8PDQzUPvhAAq3Uh
- **Status board:** https://claude.ai/artifact/TGdyx1KxenYn5VcF1uW8J3. It hasn't been updated for this wave; republish it if the owner wants.
- **Preserved scratch** from this session, in `docs/plans/prompts/ce-handoff-2026-09-26-scratch/` (untracked):
  - `ce-wave2-shared.md`: D1–D16 with reasoning, plus rules and file ownership
  - `libraries/`: the scout's picks, motion spec, SVGs and references
  - `proposals.md` and `image-gen-seeds.md`: Fable's 4 directions and adversarial review
  - `fable-mockups/`
  - `m1-latency.md`
- **Memory files to read:**
  - `ann-dataset-decisions-2026-09-24`
  - `ann-answers-2026-09-25`
  - `ce-wave2-2026-09-25`
  - `exercise-run-verification-2026-09-25`
  - `vitest-on-mnt-c`

## 9. Definition of done for the next session
1. Stitch is connected, and a Stitch mock-up PR is open with the images checked.
2. The owner has reviewed the mock-ups and made a build or no-build call on "The invitation desk".
3. If build: per-page build PRs, each at 10/10 with Opus approval, and the M2-style browser walkthrough re-run at 1280 and 390.
4. The VM deploy is done and Ann's file re-uploaded, with the owner's go-ahead. Otherwise that stays listed as pending.
5. LOW follow-ups are either done or ticketed in `docs/plans/backlog.md`.
