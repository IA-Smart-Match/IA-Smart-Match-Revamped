# Architecture diagram index

Point-in-time diagrams describe the repository state on their stated date. They decide nothing and do not imply deployment or production readiness.

| Date | Diagram set | Scope |
|---|---|---|
| 2026-09-04 | [System Process & Architecture Diagrams](../../archive/architecture/diagrams/2026-09-04-system-process-architecture-diagrams.md) | Grand system map, data lineage, release gates, eight activity workflows, four persona interactions, local/cloud topology, and component status matrix. |

## 2026-10-09 — System

System and backend maps at commit `d0b05adc`, drawn with the diagram-design plugin. Each is an HTML page with an `.svg` export. Captions, reference tables and unverified items: [2026-10-09/system/README.md](2026-10-09/system/README.md).

| Diagram | Files | Shows |
|---|---|---|
| System architecture | [HTML](2026-10-09/system/system-architecture.html) · [SVG](2026-10-09/system/system-architecture.svg) | Browser → Cloudflare → Vite → CBA api or exercise api → PostgreSQL ← worker; fixture providers; dormant adapters |
| Package dependencies | [HTML](2026-10-09/system/package-dependencies.html) · [SVG](2026-10-09/system/package-dependencies.svg) | The six workspace packages, real imports vs `pyproject.toml`, 7 import-linter contracts |
| CBA platform data model | [HTML](2026-10-09/system/er-cba-platform.html) · [SVG](2026-10-09/system/er-cba-platform.svg) | 54 tables in 8 clusters, with representative foreign keys |
| Class exercise data model | [HTML](2026-10-09/system/er-class-exercise.html) · [SVG](2026-10-09/system/er-class-exercise.svg) | The 8 `exercise_*` tables and their keys |
| Command, outbox and worker flow | [HTML](2026-10-09/system/worker-job-flow.html) · [SVG](2026-10-09/system/worker-job-flow.svg) | `submit_command` → outbox → dispatcher (`SKIP LOCKED`) → task queue → executor |
| Deployment topology | [HTML](2026-10-09/system/deployment-topology.html) · [SVG](2026-10-09/system/deployment-topology.svg) | GitHub Actions → IAP SSH → pilot VM compose stack; ports; Cloudflare tunnel; terraform (never applied) |

