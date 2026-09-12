# Smart Match web application

The active frontend is in [`legacy-frontend`](legacy-frontend). The directory name is historical; it is the current React 18, TypeScript, and Vite application.

Read [`DESIGN.md`](DESIGN.md) before changing frontend UI or API integration. It is the authoritative standard for CPP branding, product language, layouts, accessible states, data truthfulness, and frontend-to-backend wiring. [`AGENTS.md`](AGENTS.md) makes that requirement explicit for coding agents working in this directory.

The canonical backend contract is [`../../contracts/openapi/smartmatch.json`](../../contracts/openapi/smartmatch.json). Existing fixture-backed signed-in screens must keep their visible synthetic-data disclosures until they are wired to verified live endpoints.

## Local verification

From `apps/web/legacy-frontend`:

```powershell
npm test
npm run typecheck
npm run build
```
