# Architecture Stage 2 — Fable 5.1 `/goal` card

**Created:** 2026-09-08 · **Author:** Stage 1 audit (Claude Opus)
**Stage 1 input:** PR #123, branch `docs/architecture-audit-stage-1`, commit `b19ca4b`
**Format:** house `/goal` XML per [`.cursor/skills/opus-goal-prompting`](../../../.cursor/skills/opus-goal-prompting/SKILL.md)

## Dispatch note — read before pasting

The Stage 1 audit is **not on `main` yet**. It lives on `docs/architecture-audit-stage-1` (PR #123).
Branch Stage 2 accordingly:

| If PR #123 is… | Fable branches from |
|---|---|
| **still open** | `origin/docs/architecture-audit-stage-1` ← use this, the `read_first` files only exist here |
| **merged** | `origin/main` |

The card below assumes **open**. Change one line in `<context>` if it has merged.

Standing env, as for every cloud agent on this repo:
`ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`, `ALLOW_CLOUD_DEPLOY=false`.

---

## The card — copy everything below this line

```text
/goal Convert the completed Stage 1 architecture audit into a target architecture, enforceable boundary rules, sequenced migration and implementation roadmaps, new ADRs, and coding-agent instructions. Documentation only — no production code, test, workflow, or config may change. Branch `docs/architecture-target-stage-2` from origin/docs/architecture-audit-stage-1. PR to main.

<role>
Stage 2 Architecture Planner for IA SmartMatch Revamped. Stage 1 (audit) is complete
and is your input, not your task. You are the architect who receives a finished
investigation and decides what the system should deliberately evolve toward.
</role>

<mission>
Given the system that actually exists, define the target architecture and the
increments that reach it — such that future coding agents can implement each one
without destabilising a running pilot deployment.
</mission>

<context>
Repository: IA-Smart-Match/IA-Smart-Match-Revamped
Base: origin/docs/architecture-audit-stage-1  (Stage 1 audit is NOT on main yet — PR #123)
Branch: docs/architecture-target-stage-2
PR base: main
Stage 1 commit: b19ca4b

Baseline facts to verify in tree, not to trust from this card. The audit is
pinned to c72dced; main has since moved to 5fca118 (PRs #126-#139), so BOTH
columns are given and NEITHER is authoritative -- read the tree:
                        audit (c72dced)   main (5fca118)
  alembic head               0033             0034_cba_meeting
  tables in schema.py          44               45  (cba_meeting)
  API router modules           26               27  (routers/meetings.py)
  OpenAPI paths / schemas   57 / 120         59 / 125
  3,807 test functions · 17 ADRs (next number is ADR-0018)
  import-linter root_packages = 4 (the python/ packages only) -- unchanged
The structural findings were re-checked against 5fca118 and hold; R-09 (the
frontend suite no workflow runs) is unchanged and still P0. See
CURRENT_ARCHITECTURE_AUDIT.md section 0 for the full drift table.

This is a RUNNING SYSTEM with a pilot VM deployment, not a greenfield design.
It calls itself "Foundation scaffold" in its own manifest. It is not one.
</context>

<assumptions treat_as_true>
- Stage 1's findings are correct unless the repository contradicts them. If you find a
  contradiction, say so explicitly in your output rather than silently working around it.
- Documentation-only slice. Nothing you write is implemented in this PR.
- Every increment you propose must be independently shippable and reversible.
- All gates are unblocked for PLANNING purposes; live secrets and institutional
  decisions remain deferred per the existing open-questions records.
</assumptions>

<read_first order="strict">
1.  docs/architecture/OPUS_AUDIT_HANDOFF.md          ← START HERE. Constraints, anti-goals, leverage.
2.  docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md  ← the authoritative report, 20 sections
3.  docs/architecture/risk-register.md               ← R-01…R-20, P0–P3, with evidence
4.  docs/architecture/dependency-analysis.md         ← which boundaries are real, which are folders
5.  docs/architecture/wip-analysis.md                ← unfinished work; §0 explains why grep TODO finds nothing
6.  docs/architecture/domain-model.md                ← domain as implemented; bounded contexts; terminology
7.  docs/architecture/data-architecture.md           ← 44 tables, ownership ambiguity, index gap
8.  docs/architecture/capability-inventory.md        ← per-capability status; §4 = five doc/code contradictions
9.  docs/architecture/current-system-topology.md     ← two deployment topologies, one executable
10. docs/architecture/repository-inventory.md        ← toolchain, CI gates, git-history caveat
11. pyproject.toml                                   ← [tool.importlinter] — the 4 working contracts are your pattern
12. .github/workflows/verify.yml                     ← every gate; note the deferred-gate list at the very bottom
13. services/api/smartmatch_api/main.py              ← module docstring + CAPABILITY_SCOPED_ROUTERS
14. services/worker/smartmatch_worker/handlers.py    ← default_registry() at ~line 1349; only 3 handlers
15. services/api/smartmatch_api/job_authz.py         ← the consolidation pattern AP-02 should follow
16. docs/architecture/decisions/README.md + ADR-0002, ADR-0005, ADR-0011  ← house ADR voice before you write ADR-0018+
</read_first>

<non_negotiables>
These are recorded decisions with argued reasoning. Overturning one requires an ADR that
argues against the existing ADR — a preference is not sufficient.

1.  Domain layer imports NO framework, storage, provider, IO, or env — including `os`
    and `pathlib`. (import-linter contract 1, ADR-0002)
2.  PostgreSQL is the only store. Redis / Pub-Sub / BigQuery are deferred with objective
    adoption triggers. It holds coordination state deliberately — that is what makes the
    transactional outbox sound. (v1.1 §2.4, ADR-0005)
3.  No request handler performs provider IO inline. (v1.1 §1.6, scan_forbidden.py:136)
4.  Identity is never caller-supplied. (scan_forbidden.py:61,166 — MM-A01)
5.  A score carries provenance or is null; null is never rendered as 0; no score is a
    percentage. (ADR-0011 — the product's defining commitment)
6.  Attendance is the only input to points. Registration never writes attendance. (ADR-0013)
7.  Quota is charged before refusal, so refusal is not a free probe. (ADR-0015)
8.  Schema is hand-written, not reflected — composite tenant-safe keys are the point. (ADR-0004)
9.  One transaction per migration. (ADR-0009)
10. No agents in Foundation. (ADR-0003)
11. Terraform environments share no identifier and nothing is applyable. (env_isolation_check.py)
12. A gated-off capability owns NO router — never an `if enabled:` branch. (main.py)
13. Never weaken an existing CI gate to make a migration easier.
</non_negotiables>

<deliverables>
Write each file. Every recommendation must cite the concrete problem it solves by risk ID
(R-01…R-20) or audit section. A recommendation with no cited problem does not belong.

[ ] docs/architecture/TARGET_ARCHITECTURE.md
    Per major component: responsibility · ownership · public interface · internal boundary ·
    permitted deps · forbidden deps · persistence ownership · failure behaviour · testing
    expectation · observability expectation.
    Mermaid: component topology · dependency direction · request/data flow · domain
    boundaries · persistence ownership · asynchronous command flow.

[ ] docs/architecture/ARCHITECTURE_PRINCIPLES.md
    Derived from THIS repository's findings. Not generic. Format per principle:
      AP-NN — <rule>
      Problem observed  (cite file:line + risk ID)
      Rule
      Why
      Exceptions        (legitimate ones — e.g. the two documented router→router imports)
      Enforcement       (a named import-linter contract, scanner rule, test, or review rule)
    The handoff already seeds: AP-02 shared-authorization ownership · AP-03 declared table
    ownership · AP-04 no provider IO in handlers (today only a docstring + a regex) ·
    AP-06 a gate's prose claim must be assertable against its constant. Develop these and
    add others the audit supports.

[ ] docs/architecture/MODULE_BOUNDARIES.md
    Per module: Purpose · Owns · Does not own · Public API · Allowed deps · Forbidden deps ·
    Persistence · Domain concepts · Tests · Operational concerns.
    For every CURRENT module state one of: remain · deepen · split · merge · move ·
    disappear · become an adapter. No cosmetic reorganisation.

[ ] docs/architecture/DEPENDENCY_RULES.md
    Expressed so it can be IMPLEMENTED as import-linter contracts — this repo already runs
    lint-imports in CI with four working contracts as the pattern. Include draft TOML.
    Must cover the currently ungoverned services/* layer (R-05, R-06).

[ ] docs/architecture/FUTURE_FEATURE_INTEGRATION.md
    For each future capability the audit identified — live email · live identity (A1b) ·
    live route matrix · live Cloud Tasks · GCP deployment · Calendar API (G5) · additional
    scoring factors · additional command types · retention/archival · a second client —
    state: where it belongs · owning module · which existing interface it extends · what new
    abstraction is ACTUALLY justified · which boundary must not be crossed · migration
    requirements · testing requirements.

[ ] docs/architecture/MIGRATION_ROADMAP.md
    Sequential increments. The audit sketches M0–M7; refine and extend as evidence supports.
    Per increment: Goal · Current problem (cited) · Target state · Files & modules affected ·
    Prerequisites · Implementation steps · Tests required · Migration & data concerns ·
    Compatibility concerns · Rollback strategy · Completion criteria · Follow-up unlocked.
    Order so that earlier increments make later ones cheaper.

[ ] docs/architecture/IMPLEMENTATION_ROADMAP.md
    Phase 0 (immediate correctness/security blockers) → Phase 6 (longer-term extensibility).
    RE-SEQUENCE if repository evidence supports a better order — and say so if you do.
    Per task: ID · scope · motivation · dependency · affected modules · risk · estimated
    complexity · required tests · completion criteria.

[ ] docs/architecture/decisions/ADR-BACKLOG.md
    The decisions needing durable ADRs, with the evidence each still needs.

[ ] ADRs numbered from ADR-0018, matching existing file naming and house voice.
    Write the ones you have sufficient evidence for NOW. Strong candidates:
      - service-layer import contract (R-05, R-06)
      - declared table ownership (R-20, data-architecture §8)
      - generated API client + drift gate (R-02)
      - the worker task-delivery contract — 200-on-duplicate / 503-on-race — that any live
        Cloud Tasks adapter must satisfy (R-01; source: worker/main.py docstring)
      - appliance-vs-GCP deployment topology statement (R-18)
    No ADRs for trivial implementation choices.

[ ] docs/agents/architecture-implementation-guide.md
    Optimised for future AI coding agents. Before-implementing checklist: read docs →
    identify owning module → trace existing behaviour → locate existing tests → justify any
    new abstraction → confirm dependency rules → write/update tests → minimum coherent
    change → validate constraints → update docs.
    Explicit rules ADAPTED TO THIS REPO, including:
      - WIP here is marked by ABSENCE, not TODOs. Never add a TODO.
      - Never register a command handler ahead of its gate.
      - Never mount a route for a gated-off capability.
      - Never introduce a parallel service abstraction without justification.
      - Never bypass the owning domain module; never duplicate a business rule.
      - Never leak provider semantics into the domain.
      - Never create generic abstractions for hypothetical future needs.
      - Never silently change persisted-state semantics.
      - Never remove a compatibility path before proving it unused.
      - Never infer a contract from type annotations alone where runtime validation exists.
      - Preserve transactional and concurrency invariants (lease + generation, SKIP LOCKED).
      - Never weaken a CI gate.

[ ] docs/agents/feature-implementation-template.md
    Sections: Feature · User/Business Requirement · Existing System Context · Owning Domain ·
    Owning Module · Existing Interfaces · Data Changes · API Changes · Security &
    Authorization · Consent & Privacy · Command-path vs synchronous decision · Observability ·
    Tests Required · Migration & Rollback · Documentation to Update · Completion Criteria.

[ ] docs/architecture/GLOSSARY.md  (if you agree with domain-model.md §4)
    "event" means four unrelated things in this schema; "review" two; four names overlap for
    the speaker concept. The audit recommends a glossary rather than renames. Agree or argue.
</deliverables>

<deferral_policy>
A decision only a human can make → record it in
docs/plans/open-questions/architecture-stage-2-deferred.md as OQ-### with:
  the question · why engineering cannot answer it · the safe default you assumed ·
  what changes if the answer differs.
Follow the existing house pattern in docs/plans/open-questions/*.md — every one of those
records carries a safe default that IS implemented, chosen so that being wrong degrades
into refusing rather than into doing the wrong thing.

Two audit UNKNOWNs are likely to become OQ items:
  U1 — which command type each of the eight submitting routers uses, and what executes it.
       RESOLVE THIS IN-TREE IF YOU CAN before designing anything asynchronous; it is
       answerable from the repository and R-04's proposed test answers it by construction.
  U6 — is the pilot VM live with real users? Not answerable from the repository. Defer it,
       and state which of your P1 sequencing decisions would change if the answer is yes.
</deferral_policy>

<anti_patterns>
Each of these is a specific failure this repository's evidence rules out — not a general caution.

- Repeating the audit. Stage 1 is done. Cite it; do not re-derive it.
- Proposing a rewrite, a big-bang migration, or any increment that is not independently
  shippable and reversible.
- Proposing a service split, event bus, CQRS, message broker, or microservice decomposition.
  Nothing in the repository exerts that pressure, and PostgreSQL-as-coordinator is a recorded
  decision with stated adoption triggers.
- Proposing to split schema.py on line count. Ownership first; the split is the optional
  consequence. (data-architecture §8)
- Proposing a snapshot scheme for the points ledger. Folding is correct at this scale and
  ADR-0011 reproducibility depends on the ledger remaining the source of truth.
- Proposing to rename database tables to fix terminology. Write a glossary.
- Designing for the speculative: multi-region, public third-party API, ML matching,
  websockets, event sourcing beyond the points ledger. ADR-0003 already excludes the nearest.
- Building the GCP path speculatively. Write down what each adapter must SATISFY; build when
  there is a reason.
- Weakening any gate — import-linter, scan_forbidden, terminology scan, env isolation,
  supply chain, secret scan — to make an increment easier.
- Generic principles. "Prefer composition over inheritance" is not a finding from this
  repository. Every AP must cite a file and a risk ID.
- Touching production code, tests, workflows, or configuration. DOCUMENTATION ONLY.
- Inventing certainty. Where evidence is thin, mark it UNKNOWN.
</anti_patterns>

<success_criteria>
Each item is objectively checkable.

1.  Branch `docs/architecture-target-stage-2` exists off origin/docs/architecture-audit-stage-1;
    PR opened against main.
2.  `git diff --stat origin/docs/architecture-audit-stage-1...HEAD` touches ONLY paths under
    docs/. Zero changes under python/, services/, apps/, tests/, db/, infra/, tools/, .github/.
3.  All ten deliverable files exist at the paths named above (GLOSSARY.md optional if argued).
4.  At least one ADR numbered ADR-0018 or higher exists in docs/architecture/decisions/,
    following the existing file-naming convention and section structure.
5.  Every AP in ARCHITECTURE_PRINCIPLES.md has all six fields, and its "Problem observed"
    cites a file path and a risk ID.
6.  DEPENDENCY_RULES.md contains draft TOML that could be pasted into
    pyproject.toml [tool.importlinter] — naming smartmatch_api and smartmatch_worker,
    which are absent from root_packages today.
7.  MIGRATION_ROADMAP.md increments each carry all twelve required fields, and the ordering
    argument for at least the first three is explicit.
8.  Every P0 and P1 risk in risk-register.md (R-09, R-01..R-06, R-08) is addressed by a named
    increment or task, or is explicitly deferred with a reason.
9.  TARGET_ARCHITECTURE.md contains at least four Mermaid diagrams that render.
10. `make check` still passes — it must, since no code changed. Run it to prove the fence held.
</success_criteria>

<output_format>
Report back exactly:
  PR URL
  files created (paths)
  principles written (AP number + one-line rule)
  ADRs written (number + title)
  phase sequencing, and whether you re-ordered it — with the reason if so
  OQ items raised (id + question)
  anything in the Stage 1 audit you disagreed with, and why
  known gaps
</output_format>
```

---

## Why this card is shaped the way it is

Notes for whoever maintains it — not part of the dispatch.

| Choice | Reason |
|---|---|
| Base branch is the audit branch, not `main` | The 10 `read_first` files exist only on `docs/architecture-audit-stage-1` until #123 merges. Branching from `main` gives Fable an empty `read_first` list and it will silently improvise. |
| `read_first` is 16 items and strictly ordered | The handoff is first because it carries the constraints and anti-goals; without it a planner reaches for a service split by reflex. Items 11–16 are code, so the plans name real contracts, real CI steps, and the real ADR voice. |
| Anti-patterns are specific, not general | House skill guidance: forbidden actions belong in `anti_patterns`, not scattered prose. Each entry here rules out a *plausible* move this evidence forbids — a generic "avoid over-engineering" would not have stopped any of them. |
| Success criterion 2 is a `git diff --stat` fence | "Documentation only" stated in prose is a wish. Stated as a diff scope it is checkable, and criterion 10 (`make check`) proves the fence held. |
| U1 is a resolve-in-tree instruction, not a deferral | It is answerable from the repository, and a Stage 2 plan that guesses at the command substrate's shape is worse than one that stops to look. |
| ADR numbering is pinned to 0018 | 17 ADRs exist. An agent that re-derives the next number from a partial listing collides. |
