# apps/web

**Not yet built.** This is R1 work, sequenced deliberately.

The frontend consumes a **generated** TypeScript client (v1.1 §5.1), and that
client is generated from the OpenAPI document, which currently describes only
health and the unsubscribe page. Building components now would mean writing API
calls by hand and rewriting them when the client arrives — recreating exactly the
hand-maintained coupling the contract forbids.

## Order of work

1. Scaffold React 18 + TypeScript + Vite (Foundation item W1)
2. Generate the client once feature routes exist; add a drift check to CI (W2)
3. Port presentational components from the legacy (MM-F01) — confirm upstream
   shadcn/ui licensing first, and leave `mockData.ts` and `mockProfilePhotos.ts`
   behind (W3)
4. Build the provenance and truthful-state components (W4) — these are what
   replace the legacy's demo-mode ambiguity, and they should exist before the
   screens that need them
5. Matching control center, 13 views (W5)

## Non-negotiables when it is built

- Route guards are **user experience only**. API authorization is authoritative.
- No hard-coded demo identity, and no fallback records that look live.
- Every data element carries a visible source label: observed, inferred,
  heuristic, model output, or synthetic.
- Failure states render truthfully — "travel estimate unavailable",
  "unsynchronized calendar", "partial discovery: 3 of 5 sources".
- WCAG 2.2 AA: keyboard, screen reader, contrast, focus.
