# F5 deploy target — classroom vs dev (stakeholder pilot)

**Status:** Decision note — program owner direction 2026-09-03.
**Ratifier:** Danny Tran (@dangt).

---

## Comparison

| Dimension | `dev` | `classroom` |
|---|---|---|
| **Purpose** | Engineer sandbox; scales to zero | Stakeholder demos; production-shaped but isolated |
| **Data** | Synthetic fixtures | **Synthetic fixtures only — always** (per `infra/terraform/README.md`) |
| **Provider credentials** | Fixtures | **None** — no live API keys in project |
| **Institutional sign-in** | Not required for sandbox | **Same as dev for pilot** — IdP (A1b) is orthogonal; classroom does not mandate SSO by itself |
| **Pain score (setup)** | Lower — fewer isolation rules | Medium — separate GCP project, stricter CI isolation assertions |
| **Stakeholder suitability** | Poor (looks like internal tooling) | **Better** — named “classroom” environment, no prod coupling |
| **Promotion to prod** | None | **Explicitly none** — no promotion path to prod |

---

## Recommendation for stakeholder click-through pilot

1. **Primary demo path:** `docker compose up` locally (fastest for Fri 2026-09-04 target).
2. **Hosted stakeholder demo:** **`classroom`** GCP project when F5 Terraform lands — not because it requires institutional SSO, but because it is the architecture’s designated **synthetic demo** environment with no provider secrets and no path to prod.
3. **`dev` project:** Continue for engineer iteration; not the stakeholder-facing label.

**Institutional sign-in (A1b)** adds login realism when worksheet Part 1 is filled; it is required for **role-based login** (program action item) but is **not** a prerequisite to choosing classroom over dev for hosting.

---

## Decision

- **First cloud target for stakeholder hosting:** `classroom` (synthetic only).
- **`ALLOW_CLOUD_DEPLOY`:** remains `false` until Terraform modules and runbook gates are satisfied.
- **Fri 2026-09-04 target:** compose/local first; cloud classroom follows F5 implementation.
