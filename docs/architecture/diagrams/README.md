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

## How to use these diagrams

The 2026-10-09 sets were drawn with the
[diagram-design](https://github.com/cathrynlavery/diagram-design) Claude Code
plugin (v2.6.68). Each map is a self-contained `.html` page; most also have an
`.svg` export. Both are point-in-time: to show a newer state, draw a new dated
set rather than editing an old one.

**View**

1. On GitHub, click any `.svg` link: it renders in the browser.
2. Locally, open the `.html` file in a browser. From Windows, double-click it in
   `docs\architecture\diagrams\2026-10-09\` under the repository folder. The
   pages are single files with no server needed (fonts load from Google Fonts
   when online).

**Install the plugin (once, in Claude Code)**

1. `/plugin marketplace add cathrynlavery/diagram-design`
2. `/plugin install diagram-design@diagram-design`, then `/reload-plugins`
3. `/diagram-design:doctor` checks the environment. A WARN for a missing Python
   `playwright` package only blocks PNG export.

**Check a diagram** (no extra packages needed)

```bash
P=~/.claude/plugins/cache/diagram-design/diagram-design/<version>
python3 $P/skills/diagram-design/scripts/self_check.py docs/architecture/diagrams/2026-10-09/system/*.html
python3 $P/scripts/verify-geometry.py <file>.html   # overlap and bounds check
```

**Export**

1. SVG: `/diagram-design:export-diagram <file>.html --svg-only` in Claude Code,
   or `python3 $P/skills/diagram-design/scripts/export_svg.py <file>.html`. The
   script exports the first figure on a page only; extra figures stay in the HTML.
2. PNG: install Playwright first (`pip install playwright` and
   `python -m playwright install chromium`), then
   `/diagram-design:export-diagram <file>.html --png-only`.

**Draw a new or refreshed map**

1. In Claude Code, ask for it by type and scope, for example: "Use
   diagram-design to draw a sequence diagram of the command → outbox → worker
   flow on `origin/main`; save it under
   `docs/architecture/diagrams/<date>/system/`."
2. Verify every box and arrow against the code before committing: the
   diagram is only as true as the facts fed to it. Mark anything unconfirmed
   "unverified".
3. Run the self-check, export the SVG, add a caption to the folder's
   `README.md`, and add a row to this index.
4. Existing Mermaid, draw.io or Excalidraw drawings can be redrawn with
   `/diagram-design:import-mermaid`, `/diagram-design:import-drawio` or
   `/diagram-design:import-excalidraw`.
