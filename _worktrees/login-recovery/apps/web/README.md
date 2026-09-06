# apps/web

**On hold. Blocked on [`DESIGN.md`](DESIGN.md).**

Nothing is built here until a standardized design system exists and has an owner.
`DESIGN.md` is a brief, not a design: Part 1 records the constraints already
settled by architecture v1.1, and Part 2 lists the eleven decisions the redesign
must make.

Read `DESIGN.md` before writing any code in this directory.

## Why the hold

1. **No design standard.** The legacy accumulated four portal experiences, two
   landing pages, a Streamlit UI, and 44 imported components with no shared
   decisions behind them. Rebuilding without a standard reproduces that.
2. **No generated client yet.** Architecture v1.1 §5.1 requires a *generated*
   TypeScript client. Building screens now means hand-writing API calls and
   rewriting them later — the coupling the contract forbids.
3. **Little that is truthful to show.** The control center depends on match runs,
   blocked on gate G1. A screen built early gets filled with placeholder content,
   and placeholder content that looks real is the habit this revamp exists to end.

The API it will consume is real and growing —
`contracts/openapi/smartmatch.json` currently describes health, unsubscribe, job
status, job event streaming, and the import command.

---

## Notice — development-only preview, synthetic data only

> **Any frontend present here is a development-only preview running on
> synthetic data only. It is not the product, it is not deployed, and it must
> never receive live student data.**
>
> **[`DESIGN.md`](DESIGN.md) is unresolved** and stays that way pending the UI
> team. Part 2's open decisions (D-1..D-11) are still open, and D-0 — assigning
> an owner — is still unassigned.
>
> **A preview here must not constrain backend contracts.** Where it disagrees
> with `contracts/openapi/smartmatch.json`, the contract is right and the
> preview is wrong. Nothing in this directory is evidence that an endpoint
> exists.

Screens carried over from the legacy repository are reference material, not a
design. They have not been through the provenance-labelling, truthful-state, or
accessibility constraints in Part 1 of `DESIGN.md`, and they do not close any of
the decisions in Part 2.

Related: [`../../docs/decisions/pilot-decisions.md`](../../docs/decisions/pilot-decisions.md)
(tentative pilot decisions, D-0 section) and
[`../../docs/ui/pilot-prototype-prompts.md`](../../docs/ui/pilot-prototype-prompts.md)
(a non-authoritative prompt pack for an **external** clickable prototype — no
generated UI code is merged here).
