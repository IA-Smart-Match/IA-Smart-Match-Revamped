# TODO / FIXME disposition register

**Status:** point-in-time survey, 2026-09-18. Base commit: `origin/main`.

**This document recommends; it authorizes nothing.** It changes no marker, no
code and no test. It closes no open-question row, opens no gate, and does not
make any dated plan active. Every "needs-track" line below is a *proposal* for
someone else to accept or reject. Nothing here is a production-readiness claim.

**Scope:** every `TODO` / `FIXME` (and the neighbouring `XXX` / `HACK`) marker
in the repository's **tracked** files. Untracked paths — including
`node_modules/`, `.venv/`, build output and local `.env` — are out of scope by
virtue of being untracked, so no exclusion pattern was needed for them.

---

## 1. Headline finding

**The repository contains zero actionable `TODO`, `FIXME`, `HACK` or `XXX`
markers in code.** Every textual match is either documentation *asserting* that
absence, a branch name, a dictionary word, or test prose describing markers
that used to exist in an earlier revision.

This is not an accident, and it is documented as a deliberate house rule:

> **Rule.** No `TODO`, `FIXME`, `HACK`, `XXX`, or `NotImplementedError` in …
> — `docs/agents/architecture-implementation-guide.md:176`

> WIP in this repository is not marked in code. It is tracked in a parallel
> documentation system — named gates (G1–G5, A1b, F5, R2, R4, S12),
> `docs/plans/open-questions/*-deferred.md` records, and an agent-memory ledger
> with a CI gate.
> — `docs/architecture/wip-analysis.md` §0

So a TODO sweep is the *wrong instrument* for this codebase: unfinished work is
expressed as absence (an unmounted route, an unregistered command type, a
constructor that refuses), which a grep for markers cannot see. `wip-analysis.md`
§0 exists to pay exactly that cost and remains the correct place to look.

---

## 2. Reconciling the "84 markers" figure

The orchestration brief states there are **"84 TODO/FIXME markers, concentrated
in `tests/integration` and `tests/unit`."** No marker definition reproduces that
number. Every command below was run from the worktree root against tracked
files only; the count is the number of **matching lines**.

| # | Command | Count |
|---|---|---:|
| A | `git grep -nE "TODO\|FIXME" -- .` | 22 |
| B | `git grep -nE "\b(TODO\|FIXME\|XXX\|HACK)\b" -- .` | 23 |
| C | `git grep -niE "\b(TODO\|FIXME\|XXX\|HACK)\b" -- .` | **26** |
| D | `git grep -niE "\b(TODO\|FIXME\|XXX\|HACK)\b" -- . ':!docs/'` | 3 |
| E | `git grep -niE "\b(TODO\|FIXME)\b" -- .` | 21 |
| F | `git grep -niE "\b(TODO\|FIXME)\b" -- . ':!docs/'` | 2 |
| G | `git grep -ni "todo" -- .` (substring, not word-bounded) | 29 |
| H | `git grep -ni "fixme" -- .` (substring) | 9 |
| I | `git grep -n "NotImplementedError" -- .` | 10 |

**Definition adopted: C** — case-insensitive, word-bounded, across all tracked
files including `docs/`. It is the widest definition that still only matches
marker-shaped tokens, so it cannot be accused of hiding anything; `docs/` is
included precisely so the reader can see that the docs matches are the bulk of
the result. Row G is reported but not adopted, because unbounded `todo`
matches the branch name `claude/pr1-blockers-todos-er5heu` seven times.

**No reasonable definition yields 84, and the register does not pad or trim to
reach it.** The maximum over any marker definition is 29, and the maximum
restricted to non-documentation files is 3 — of which **zero** are actionable.

### 2.1 Where 84 probably came from

The nearest reproducible neighbour to 84 is the count of **pytest skip / xfail
call sites**, which *are* concentrated in `tests/`:

```
git grep -nE "pytest\.(mark\.)?(skip|skipif|xfail)" -- .        →  83
git grep -nE "pytest\.(mark\.)?(skip|skipif|xfail)" -- tests/   →  75
```

83 is one off 84, and a `pytest -ra` run would report a slightly different
number again (one call site can skip several parametrised cases, and one
`skipif` can skip zero). This is offered as the most likely origin of the
figure, **not** as a claim that the brief meant it.

Two caveats, both material:

1. **The directory attribution in the brief is wrong even for this reading.**
   The skips cluster in `tests/e2e` (35) and `tests/contract` (30), not in
   `tests/integration` (6) and `tests/unit` (4).
2. **These are not WIP markers.** Every sampled call site is an
   *environment-conditional* skip — no PostgreSQL reachable
   (`tests/contract/test_me.py:54`, `tests/integration/test_rewards_api.py:202`),
   or an e2e step whose predecessor did not produce the state it needs
   (`tests/e2e/test_pilot_clickthrough.py:552`, `:664`, `:712`, `:754`). The
   `Makefile:97` comment documents this as intentional: each skip names its
   reason and `-ra` prints every one. Dispositioning them as TODOs would be a
   category error, so this register does not do so.

If the sponsor of the "84" figure wants the skip inventory audited, that is a
**separate track** — see §6, `track: skip-inventory-audit`.

---

## 3. Dispositions

Every line matched by the adopted definition (C), in file order. Marker text is
verbatim from the source line.

### 3.1 `docs/` — documentation of the no-TODO rule

| File:line | Verbatim text | Disposition |
|---|---|---|
| `docs/agents/architecture-implementation-guide.md:27` | ``zero `TODO`, zero `FIXME`, zero `HACK`, zero `XXX`, zero`` | **not-a-defect** |
| `docs/agents/architecture-implementation-guide.md:174` | ``### 3.1 WIP is marked by absence — never add a `TODO` `` | **not-a-defect** |
| `docs/agents/architecture-implementation-guide.md:176` | ``**Rule.** No `TODO`, `FIXME`, `HACK`, `XXX`, or `NotImplementedError` in`` | **not-a-defect** |
| `docs/agents/architecture-implementation-guide.md:188` | ``**How to check.** `grep -rn "TODO\|FIXME\|HACK\|NotImplementedError" python/`` | **not-a-defect** |
| `docs/agents/architecture-implementation-guide.md:652` | ``- [ ] No `TODO`/`FIXME`/`HACK`/`NotImplementedError` added; no `if enabled:` inside`` | **not-a-defect** |
| `docs/agents/feature-implementation-template.md:13` | ``- Do not write a `TODO`, `FIXME`, `HACK`, or `NotImplementedError` anywhere in`` | **not-a-defect** |
| `docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md:168` | ``**The pattern worth naming.** This codebase does not mark WIP with `TODO`.`` | **not-a-defect** |
| `docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md:169` | ``There are zero `TODO`, `FIXME`, `HACK`, `XXX` markers and zero`` | **not-a-defect** |
| `docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md:485` | ``Zero `TODO`/`FIXME`/`HACK`/`XXX`/`NotImplementedError` in the codebase. WIP is`` | **not-a-defect** |
| `docs/architecture/GLOSSARY.md:154` | ``## 4. Gates — the WIP vocabulary that replaces `TODO` `` | **not-a-defect** |
| `docs/architecture/GLOSSARY.md:156` | ``There are **zero** `TODO`, `FIXME`, `HACK`, `XXX` markers and zero`` | **not-a-defect** |
| `docs/architecture/OPUS_AUDIT_HANDOFF.md:24` | ``… §0 explains why the usual `TODO` search returns nothing here`` | **not-a-defect** |
| `docs/architecture/OPUS_AUDIT_HANDOFF.md:40` | ``**2. There are no `TODO`s — zero, repository-wide — and that is not because`` | **not-a-defect** |
| `docs/architecture/OPUS_AUDIT_HANDOFF.md:45` | ``discipline than TODO comments and you should preserve it. Its one cost is that`` | **not-a-defect** |
| `docs/architecture/wip-analysis.md:15` | ``\| `TODO` \| **0** \|`` | **not-a-defect** |
| `docs/architecture/wip-analysis.md:16` | ``\| `FIXME` \| **0** \|`` | **not-a-defect** |
| `docs/architecture/wip-analysis.md:17` | ``\| `HACK` \| **0** \|`` | **not-a-defect** |
| `docs/architecture/wip-analysis.md:18` | ``\| `XXX` \| **0** \|`` | **not-a-defect** |
| `docs/architecture/wip-analysis.md:29` | ``This is a genuinely better discipline than TODO comments, because an unmounted`` | **not-a-defect** |

**Why not-a-defect (all 19).** Each is prose stating or enforcing the house
rule that markers must not exist. Verified by reading each surrounding section:
`architecture-implementation-guide.md` §3.1 and its checklist are authoring
rules; `CURRENT_ARCHITECTURE_AUDIT.md` §168–170 and §485, `GLOSSARY.md` §4 and
`wip-analysis.md` §0 are audit findings recording the zero count. Removing any
of them would delete the documentation of the convention, not a marker.

**Consistency note (no action authorized).** `wip-analysis.md` §0 records
"skipped/xfail tests — **1**". The current tree has 83 skip/xfail call sites
(§2.1). The audit is dated to commit `c72dced` and is explicitly a point-in-time
record, so this is drift, not an error in the audit — but a reader who takes §0
as current will be misled. Flagged under §6 `track: wip-analysis-refresh`.

### 3.2 `tests/` — prose describing removed markers

| File:line | Verbatim text | Disposition |
|---|---|---|
| `tests/unit/test_frontend_paged_list_contract.py:56` | ``# component existed. Each left a `TODO(integrator)` asking to be wired up`` | **done-elsewhere** |
| `tests/unit/test_frontend_paged_list_contract.py:328` | ``lists behind a satisfied-looking `TODO(integrator)`, so they get the`` | **done-elsewhere** |

**Verification (read, not inferred).** Both lines are comments/docstrings
*about* markers that existed in three coordinator pages authored in parallel
worktrees before `PagedList.tsx` landed. The work those markers asked for is
done and is now *enforced*: the three pages
(`coordinator/CoordinatorEvents.tsx`, `CoordinatorMeetings.tsx`,
`CoordinatorReviewQueue.tsx`) are pinned in the `PAGED_SURFACES` map
(lines 46–66) and again in `LATE_WIRED_SURFACES`, where the test asserts both
that the whole array reaches `items={…}` and that the page's own array name
never appears in a `.map(`. A `git grep -ni "todo" -- apps/` returns nothing, so
no `TODO(integrator)` survives in the frontend source.

**Recommended follow-up:** none. Unlike a stale code marker, this prose is the
*reason the assertion exists* and should stay. Deleting it would leave a strict
test with no explanation of what it defends against.

### 3.3 Dispositions not used

No marker was dispositioned **tracked-by-OQ** or **needs-track**, because no
actionable marker exists. This is a real result, not an omission: the gates and
registers listed in `docs/plans/open-questions/` own this repository's WIP
directly, without a marker intermediary, exactly as `wip-analysis.md` §0
describes.

---

## 4. Counts

### Per disposition

| Disposition | Count |
|---|---:|
| not-a-defect | 19 |
| done-elsewhere | 2 |
| tracked-by-OQ | 0 |
| needs-track | 0 |
| **Total dispositioned** | **21** |
| Excluded (Appendix A) | 5 |
| **Total matched by definition C** | **26** |

### Per top-level directory

| Directory | Dispositioned | Excluded | Total |
|---|---:|---:|---:|
| `docs/` | 19 | 4 | 23 |
| `tests/` | 2 | 0 | 2 |
| `python/` | 0 | 1 | 1 |
| `apps/`, `services/`, `db/`, `infra/`, `tools/`, `scripts/`, `contracts/`, root | 0 | 0 | 0 |

The count in `docs/plans/prompts/` (2, both excluded) includes no match from
this register's own task prompt: `docs/plans/prompts/*` is excluded wholesale
per Appendix A.

---

## 5. Actionable-marker density

| Tree | Actionable markers |
|---|---:|
| `python/` | 0 |
| `services/` | 0 |
| `apps/` | 0 |
| `tests/` | 0 |
| `db/`, `infra/`, `tools/`, `scripts/` | 0 |

---

## 6. "needs-track" list, ordered by risk

No track is required to remove or resolve a marker. Two are proposed for the
*discrepancies this survey uncovered*; both are documentation-only and neither
is gated.

| Risk | Proposed track | Gated? | Why |
|---|---|---|---|
| Medium | `docs: wip-analysis skip-count refresh` | No | `docs/architecture/wip-analysis.md` §0 states 1 skipped/xfail test; the tree has 83 call sites. A reader treating §0 as current gets a materially wrong picture of how much of the suite is environment-conditional. Documentation-only; touches no test. |
| Medium | `test: skip-inventory audit` | No | 83 skip/xfail call sites, 35 in `tests/e2e` and 30 in `tests/contract`, were sampled but not exhaustively read. Sampling suggests all are environment- or predecessor-conditional, but "suggests" is not "verified", and a skip that silently never runs in CI is indistinguishable from a passing test in a summary line. Read-only audit; proposes no test change. |

Lower-risk observation, not proposed as a track: the brief's "84 markers in
`tests/integration` and `tests/unit`" should be corrected at source, since
downstream planning that budgets for 84 marker removals is budgeting for work
that does not exist.

---

## Appendix A — exclusions

Matched by definition C, excluded from disposition, with the reason.

| File:line | Text | Reason excluded |
|---|---|---|
| `python/smartmatch_providers/smartmatch_providers/data/glove_vocab.txt:12894` | `xxx` | Not a marker. A GloVe embedding vocabulary word in a generated data file, one token per line, between `ballpark` and `uphold`. Case-insensitive `\bXXX\b` cannot distinguish it; reading the file makes it unambiguous. |
| `docs/plans/prep/g3-eval-and-vocabulary-candidates.md:68` | ``approves `"Case Competition"`, `"Guest Lecture"`, or `"Hack-a-thon"` produces a`` | Not a marker. Product vocabulary — an event-type term under G3 evaluation. `Hack-a-thon` matches `\bHACK\b` only by hyphen splitting. |
| `docs/plans/prep/g3-eval-and-vocabulary-candidates.md:78` | ``term set. Approving `hackathon` does **not** map `hack a thon`, `hackfest`, or`` | Not a marker. Same G3 vocabulary discussion; `hack a thon` is an example of a *non*-matching spelling. |
| `docs/plans/prompts/architecture-stage-2-fable-goal.md:80` | ``5.  docs/architecture/wip-analysis.md  ← unfinished work; §0 explains why grep TODO finds nothing`` | Agent prompt. `docs/plans/prompts/*` is excluded wholesale: these are instructions to agents, not repository state. |
| `docs/plans/prompts/architecture-stage-2-fable-goal.md:192` | ``- WIP here is marked by ABSENCE, not TODOs. Never add a TODO.`` | Agent prompt; same reason. |

Also excluded without individual listing, because they are matched only by the
**non-adopted** substring definition (row G) and are not marker-shaped: eleven
lines across `docs/migration/port-verification.md`,
`docs/plans/critical-path-*.md`, `docs/plans/pr1-blockers-handoff.md`,
`docs/plans/pr3-verification-evidence.md` and
`docs/plans/status-report-830.md` that contain the git branch name
`claude/pr1-blockers-todos-er5heu`.

## Appendix B — reproducing this survey

Run from the repository root. Counts are as of `origin/main`, 2026-09-18.

```
git grep -niE "\b(TODO|FIXME|XXX|HACK)\b" -- .                     # 26 (adopted)
git grep -niE "\b(TODO|FIXME|XXX|HACK)\b" -- . ':!docs/'           #  3
git grep -nE  "pytest\.(mark\.)?(skip|skipif|xfail)" -- .          # 83
git grep -cE  "pytest\.(mark\.)?(skip|skipif|xfail)" -- tests/     # per-file histogram
```

A count that differs from the table above means the tree moved, not that the
survey was wrong — re-run rather than reconcile by hand.
