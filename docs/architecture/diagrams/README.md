# Architecture diagram index

Point-in-time diagrams describe the repository state on their stated date. They decide nothing and do not imply deployment or production readiness.

| Date | Diagram set | Scope |
|---|---|---|
| 2026-09-04 | [System Process & Architecture Diagrams](../../archive/architecture/diagrams/2026-09-04-system-process-architecture-diagrams.md) | Grand system map, data lineage, release gates, eight activity workflows, four persona interactions, local/cloud topology, and component status matrix. |

## 2026-10-09 — Product

Drawn from `origin/main` @ `d0b05adc` with the diagram-design plugin (HTML + SVG). Captions and sources: [`2026-10-09/product/README.md`](2026-10-09/product/README.md).

| Diagram | Scope |
|---|---|
| [CBA platform surface](2026-10-09/product/platform-surface.html) | Persona → portal page → API router → capability, with on/off per product scope; dormant speaker portal and class exercise. |
| [Class exercise flow](2026-10-09/product/class-exercise-swimlane.html) | Team, instructor and system lanes from team entry to round two (Harbor). |
| [Results lock states](2026-10-09/product/results-lock-state.html) | Never opened → open → closed again, and what a team run gets in each. |
| [Frontend page map](2026-10-09/product/frontend-map.html) | Route shells, the two API clients, 11 dormant page files. |
| [Documentation map](2026-10-09/product/docs-map.html) | Which index points where, and where each kind of document lives. |
| [CI and release pipeline](2026-10-09/product/ci-release.html) | Workflows, merge gate, promote → deploy → VM. |

