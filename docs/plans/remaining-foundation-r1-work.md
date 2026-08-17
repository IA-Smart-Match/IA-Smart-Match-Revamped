# Remaining Foundation and R1 work

In dependency order. Each item names what blocks it and who owns the block, so
sequencing is visible rather than rediscovered.

---

## Blocked on decisions outside engineering

These cannot be started by engineering alone. They are listed first because
several downstream items wait on them, and the calendar cost of a late decision
is larger than the work itself.

| # | Item | Blocked on | Owner | Blocks |
|---|---|---|---|---|
| D1 | Approve the factor registry contents and golden case set | Gate G1 | Program owner | All matching work (R1) |
| D2 | Confirm ELI formula parameters (decay half-life, window, caps) | Open decision 2 | Program owner | R1 tuning; not R1 delivery |
| D3 | Route-matrix provider terms and per-run call budget | Open decision 6 | Procurement + engineering | `travel_burden` factor |
| D4 | Domain registration and DNS control | Open decision 8 | Institutional IT | All mail work (R4) |
| D5 | Retention periods per evidence table | Open decision 5 | Privacy / legal / records | R2 evidence tables |

**D1 is the critical path.** Everything in "Matching" below waits on it, and
matching is the product's reason for existing.

---

## Foundation completion

Work that finishes the scaffold itself. None is blocked on a decision.

| # | Item | Depends on | Notes |
|---|---|---|---|
| F1 | Pin dependencies to a lock file with hashes | — | Resolves security finding S-003; blocks F2 |
| F2 | Add dependency vulnerability, license, and SBOM scanning to CI | F1 | Scanning unpinned dependencies gives results that do not match what installs |
| F3 | Independent review of the four `ported_unverified` manifest entries | — | §6 of the orchestrator contract forbids self-approval; moves MM-001/003/004/005 to `verified` |
| F4 | Containerize API and worker; add image build to CI | F1 | Needed before any deployment; also unblocks container scanning |
| F5 | Flesh out Terraform environment skeletons | F4 | Still no deployment — configuration only, with the CI assertion that environments share no identifiers |
| F6 | Add ADRs for decisions made during scaffolding | — | Package boundaries, LTree type declaration, StrEnum adoption, scanner design |

---

## R1 — Matching foundation

### Blocked on D1

| # | Item | Depends on | Notes |
|---|---|---|---|
| M1 | Flip `REGISTRY_STATUS` to `approved` in a reviewed commit | D1 | Also lands the golden case set; `test_registry_is_not_yet_approved` changes here, deliberately |
| M2 | Implement `topic_relevance` | M1 | Embedding models may contribute feature inputs only with provenance and golden/shadow tests |
| M3 | Implement `role_fit` | M1 | The legacy's alias/fuzzy approach is a reasonable starting point; it needs golden cases, not a port |
| M4 | Implement `travel_burden` over the route matrix | M1, D3 | Interim: straight-line distance labeled "estimate quality: coarse". Never fabricate mileage. |
| M5 | Implement `repeat_penalty` | M1 | Feeds control-center view V6 (repeatedly selected vs underutilized) |
| M6 | Stage A eligibility filter | M1 | The four eligibility factors are declared in the registry and unimplemented |
| M7 | Stage B CP-SAT portfolio optimization | M2–M6 | OR-Tools. The LLM never solves the schedule. |
| M8 | Immutable `match_run` persistence with full version pinning | M7 | Input snapshot, eligibility policy, registry, weight set, optimizer version, route-estimate timestamp |
| M9 | Per-factor and per-penalty explanations | M7, M8 | Must separately show the ELI hard cap and soft penalty (v1.1 §1.3) |
| M10 | Scenario comparison | M8 | Six objectives per v1.1 §5.3 |

### Not blocked on D1

| # | Item | Depends on | Notes |
|---|---|---|---|
| J1 | Outbox dispatcher: lease, claim, create task, record evidence | — | Tables exist. Needs a lag metric, an alert, and crash recovery via lease expiry. |
| J2 | Command resource pattern with idempotency and 202 + job id | J1 | Explicit resources per v1.1 §1.11, not a generic job-type switch |
| J3 | SSE `GET /v1/jobs/{id}/events` with `Last-Event-ID` | J1 | Backed by `job_event.sequence`; this is why Redis is not required |
| J4 | Re-drive command with authorization and audit | J1 | Cloud Tasks has no native DLQ |
| J5 | Integration tests: crash between commit and task creation must not lose a job; duplicate delivery must not double-execute | J1 | Named explicitly in the v1.1 §4.1 gate list |
| J6 | Real OIDC task-identity verification in the worker | J1 | Resolves security finding S-001 |
| A1 | Google Identity Platform token verification in the API | — | Replaces the archived mock login |
| A2 | Wire `smartmatch_authz` into request handling as a dependency | A1 | The policy is written and tested; nothing calls it yet |
| A3 | PostgreSQL transactional rate limiter | A1 | Resolves security finding S-002. **Must ship with the first command endpoint, not after it.** |
| A4 | Authorization policy matrix with negative tests per operation | A2 | v1.1 §2.1 names this as a workstream |

---

## R1 — Frontend

Sequenced deliberately. Building components before the generated client exists
would recreate the hand-written-API coupling v1.1 §5.1 forbids.

| # | Item | Depends on | Notes |
|---|---|---|---|
| W1 | Scaffold `apps/web` — React 18, TypeScript, Vite | — | |
| W2 | Generate the TypeScript client from OpenAPI; add a drift check to CI | J2 (routes must exist) | Generated only, never hand-edited |
| W3 | Port presentational components (MM-F01) | W1, W2 | Confirm upstream shadcn/ui licensing first. Leave `mockData.ts` and `mockProfilePhotos.ts` behind. |
| W4 | Provenance and truthful-state components | W1 | Observed / inferred / heuristic / model output / synthetic labels; "travel estimate unavailable"; "partial discovery: 3 of 5". This component family is what kills the demo-mode ambiguity. |
| W5 | Matching control center — 13 views | M8, W2 | |
| W6 | Accessibility: WCAG 2.2 AA, plus a11y smoke tests in CI | W1 | |
| W7 | Add web gates to CI (npm ci, tsc, vitest, bundle budget, Playwright) | W1 | Listed as deferred in `.github/workflows/verify.yml` |

---

## Deferred beyond R1

Recorded so the sequencing is visible, not scheduled here.

- **R2** — self-service professional profiles (required by the ELI design: people
  must be able to see and correct the workload data used about them), coordinator
  intake, accept/decline, ICS delivery, attendance and QR (MM-F02), feedback,
  contact-confidence lifecycle in the API.
- **R3** — read-only Jarvis, research scout, quarantine and provenance,
  extraction, entity resolution, human verification queue, agent eval dataset.
  **Requires the crawler threat model before any crawl code is written.**
- **R4** — consent-origin workflows, suppression, versioned approval, crash-safe
  send, scheduling proposals. Gate G4 and G5.
- **R5** — conversational control center, exception triage, scenario analysis,
  failure explanation, forecasting. No new mutation authority.

---

## Suggested next three

If work resumes tomorrow, this is where it starts:

1. **F3** — get the four ported components independently reviewed. Cheap,
   unblocks the manifest, and needs no decisions.
2. **D1** — start the factor-registry approval conversation. It is the longest
   pole and the only thing blocking the product's core.
3. **J1 + A1** — the outbox dispatcher and real token verification. Both are
   unblocked, both are prerequisites for every command endpoint, and A3 must land
   alongside the first one.
