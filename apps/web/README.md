# apps/web

**On hold. Blocked on [`DESIGN.md`](DESIGN.md).**

Nothing is built here until a standardized design system exists and has an owner.
`DESIGN.md` is a brief, not a design: Part 1 records the constraints already
settled by architecture v1.1, and Part 2 lists the eight decisions the redesign
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
