---
name: opus-goal-prompting
description: >-
  Author and execute /goal objectives for Opus 5.0 using Anthropic prompt-engineering
  patterns (XML structure, role, read-first, deferral defaults, verification gates).
  Use when the user invokes /goal, asks for Opus agent prompts, scaffold PRs, or
  continuation work after merged pilot slices.
---

# Opus 5.0 `/goal` prompting (Anthropic-style)

Teaches how to **write** and **run** durable `/goal` objectives for this repository.
Pair with Cursor `/goal` (CreateGoal → work → UpdateGoal complete).

## When to use

- User says `/goal …`, "Opus prompt for …", "scaffold PR for …", or "continue unfinished engineering"
- Post-merge continuation (check `goal-catalog-post-merge.md` first)
- Any multi-PR slice needing strict scope fences

## Anthropic techniques (apply to every goal body)

| Technique | How to apply here |
|-----------|-------------------|
| **Role + mission** | Open with `<role>` and one-sentence `<mission>` |
| **XML sections** | Use tagged blocks: `context`, `assumptions`, `non_negotiables`, `read_first`, `deliverables`, `deferral_policy`, `anti_patterns`, `success_criteria`, `output_format` |
| **Direct instructions** | State what to build; list forbidden actions in `anti_patterns`, not scattered prose |
| **Read-first discipline** | Ordered file list before coding; recon commit or plan doc first |
| **Examples** | Point to one shipped slice as pattern (`match_runs.py`, `rewards.py`, `outreach.py`) |
| **Chain-of-thought** | Allowed only in **Phase 0 recon** and plan doc — not in PR description fluff |
| **Deferral defaults** | Human blockers → `docs/plans/open-questions/<slice>-deferred.md` + safe refuse path |
| **Verification** | `success_criteria` must be objectively checkable (tests, migration head, OpenAPI paths) |
| **Critical context placement** | Repeat branch name + fence at top **and** in `success_criteria` |

## Scaffold posture (default for this repo)

Unless the user says otherwise:

- **Assume all gates are unblocked for engineering** (G1–G5, P2, D8, F5).
- **Live secrets / institutional decisions** → defer with OQ items; implement fixture/refuse path.
- **Never** fake success, never production-readiness claims, never `ALLOW_CLOUD_DEPLOY=true`.
- **Branch + PR required** unless user says "no PR".

## `/goal` execution protocol (agent)

1. **Parse** the objective; restate deliverables + evidence sources.
2. **CreateGoal** once with the full objective (not a shrunk version).
3. **Phase 0** — `git fetch && git switch -c <branch> origin/main`; read `read_first` files; write or update plan doc if slice lacks one.
4. **Implement** in dependency order (schema → domain → persistence → worker → API → contract → UI minimal).
5. **Verify** — `make check`; targeted pytest; note skipped integration if no DB.
6. **PR** — `git push -u origin HEAD`; `gh pr create --base main` with Summary + Test plan + OQ table.
7. **UpdateGoal** `complete` only when every `success_criteria` item has file/command evidence.

## Prompt skeleton (copy and fill)

```xml
<role>Lead implementation agent for [SLICE] on IA SmartMatch Revamped.</role>

<mission>[One sentence: what ships, wired or unwired.]</mission>

<context>
Repository: IA-Smart-Match-Revamped
Base: origin/main (fetch first)
Branch: [branch-name]
PR base: main
Post-merge baseline: migration head [NNNN], OpenAPI [N] ops — verify in tree.
</context>

<assumptions treat_as_true>
- All gates unblocked for engineering scaffold purposes.
- Fixture/synthetic defaults; live mode behind env + explicit refusal.
</assumptions>

<non_negotiables>
[List 5–10 repo invariants: domain purity, 202+job for sends, consent gates, etc.]
</non_negotiables>

<read_first order="strict">
1. [paths]
</read_first>

<deferral_policy>
Human decisions → docs/plans/open-questions/[slice]-deferred.md (OQ-###).
Safe default must fail closed or use .invalid / Fixture* providers.
</deferral_policy>

<deliverables>
[Checklist: plan doc, migration, domain, persistence, worker, API, OpenAPI, tests, README touch, PR]
</deliverables>

<anti_patterns>
[Explicit don'ts]
</anti_patterns>

<success_criteria>
[Measurable; each maps to a test or file path]
</success_criteria>

<output_format>
PR URL | migration head | new OpenAPI ops | OQ list | known gaps
</output_format>
```

## Model routing (suggested in goal text)

| Phase | Model |
|-------|-------|
| Orchestration + PR | Opus 5.0 medium |
| Plan / recon | Opus 5.0 high |
| Implementation cards | Sonnet 5.0 or Composer |
| Review | Opus 5.0 medium |

## Catalog

Ready-made `/goal` bodies for post–PR #36/#37 work:
[goal-catalog-post-merge.md](goal-catalog-post-merge.md)

Update that catalog when a goal merges; do not rewrite merged goals in place.

## Related skills

- `smartmatch-status-report` — pilot readiness snapshots
- `i-have-adhd` — stakeholder-facing output (optional per session)
