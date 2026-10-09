# Product repo maps — 2026-10-09

Drawn from `origin/main` at `d0b05adc` on 2026-10-09. They are point-in-time maps:
they decide nothing and say nothing about production readiness. Each `.html`
opens in a browser and carries its sources and unverified items under the
diagram. Each `.svg` is the first diagram on that page, exported with the
diagram-design plugin. No PNGs: the Playwright Python package is not installed
on the machine that drew them.

| Map | Files | What it shows |
|---|---|---|
| CBA platform surface | [`platform-surface.html`](platform-surface.html), [`.svg`](platform-surface.svg) | Five personas (Student, Event Host, Speaker Connector, Speaker, exercise team) against the 15 product capabilities. Each cell names the portal pages that persona uses, and each row names the API routers the capability mounts and whether it is on in the `cba`, `ia_west_legacy` and `class_exercise` scopes. The speaker portal and the class exercise are built but dormant in the CBA pilot. A second figure (HTML only) shows that one process runs one scope, and that the frontend carries a hard-coded copy of the CBA policy. |
| Class exercise flow | [`class-exercise-swimlane.html`](class-exercise-swimlane.html), [`.svg`](class-exercise-swimlane.svg) | One class session in three lanes: the team enters, matches with default weights 3/3/2/2 and saves settings, and runs round one (Northline) once the instructor unlocks it. Then it chooses a way of asking, refreshes, and runs round two (Harbor). Each run passes the server's run guard. Clear-team and switch-file are in the table below the diagram; switching the file deletes every team's work. |
| Results lock states | [`results-lock-state.html`](results-lock-state.html), [`.svg`](results-lock-state.svg) | One event's results go from never opened to open to closed again, and can be reopened. It shows what a team's run gets in each state. Unlocking or locking twice does nothing new, and closing deletes no stored run. |
| Frontend page map | [`frontend-map.html`](frontend-map.html), [`.svg`](frontend-map.svg) | Route shells in `apps/web/legacy-frontend` and the two API clients. Exercise pages use the cookie-based `exerciseClient.ts`; everything else uses the bearer-token `lib/api.ts`. 11 page files have no route and are listed as dormant, not dead. |
| Documentation map | [`docs-map.html`](docs-map.html), [`.svg`](docs-map.svg) | Which index file points where: root README, `docs/INDEX.md`, the planning index, the decision spine, the ADR index, the open-question registers and this diagram index. The table below it says where each kind of document lives. The two links added on 2026-10-09 are highlighted. |
| CI and release pipeline | [`ci-release.html`](ci-release.html), [`.svg`](ci-release.svg) | Branch → reviewed PR → `main` → manual `promote.yml` → `deploy` branch → `deploy.yml` → VM `deploy.sh` → `pilot.plated.blog`, with the optional exercise overlay. A merge to `main` needs one review and a code-owner review, but **no status check is required**. On 2026-10-09, GitHub has no `deploy` branch on origin. |

The system architecture, package dependency, data model, worker and deployment
maps for the same date are drawn separately (the "System" section of the
[diagram index](../../README.md)).
