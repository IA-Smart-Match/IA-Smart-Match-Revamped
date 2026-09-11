# PR #154 closeout — session-death recovery and final state

**Date:** 2026-09-10 (late PDT) · **Branch:** `feat/frontend-dev-resync` · **Status at writing:** all five workstreams merged, CI green, dataset verified connected on the running `smartmatch_pr154` review stack.

This document records what the rate-limited session left behind, what the recovery pass found and finished, and what remains for the next session. It supersedes the ephemeral handoff at `/tmp/claude-1000/handoff-pr154/HANDOFF_PR154.md` for state questions (the handoff remains the authority for the locked decisions in its §3, recorded on the PR itself in [this comment](https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/154#issuecomment-5630450687) plus [this amendment](https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/154#issuecomment-5631324830)).

## What died and what survived

Five agents hit the session rate limit mid-flight (~21:40). Their committed work was already pushed — the commit-per-milestone rule held again. Recovery inventory:

| Workstream | Branch | What survived | What was missing |
|---|---|---|---|
| B1 identity+portals | `pr154/b1` | 3 commits — admin+coordinator one persona end to end (`portals.py`, `role_presentation.py`, `roles.ts`/`hasActiveRole`, seed logins holding both roles) | nothing — merged as found |
| B2 unified shell | `pr154/b2` | 2 commits — Connector shell w/ Option A nav, `legacyRedirects.ts`, routes rewrite | uncommitted `CoordinatorEvents` merge + contract test; match-run shortlist hole (`/ai-matching?run=` dropped the param); `VolunteerPortalLayout` stale nav/label; 6 stale test files; DESIGN.md role table |
| C1 host-org backend | `pr154/c1` | 1 commit — migration 0036 + schema + migration tests | uncommitted repository+router+wiring+policy cells; the HTTP contract test file named in the router's own docstrings; stamp-on-create tests |
| D dataset tooling | `pr154/d` | 3 commits — rewritten `verify_pilot_dataset.py` (19 counted tables, 12 surface floors, 20 cross-table checks that fail VACUOUS), engagement+feedback seeders, top-up target | uncommitted docs; the actual generate→top-up→verify run |
| S student repoint | `pr154/s` | 3 commits — student Home/History/Connect on `/v1` reads | 7 absolute links missing the `/student-portal/` prefix (would have routed students into the admin shell) |

Recovery completed each branch, then merged all five into `feat/frontend-dev-resync` (`a8836d99 → e6b17467`), resolving: `roles.ts` add/add (kept b1's), `openapi/smartmatch.json` (regenerated via `make openapi` — zero-diff verified), `INSTALL.md` (disjoint sections). Four merged-state test failures were fixed and flagged: admin's shared "Connector Dashboard" name, a seed-secret literal under the credential-scan threshold, ruff format on 3 files, and CHECK-constraint coverage for 0036's five new constraints.

## What was built after the merge

- **Event Host portal frontend** (`41ee877f`–`b0b30a34`): `VolunteerOrganization` (own org GET/PUT with honest 404/409 states), `VolunteerHome` as HostHome, `?request=` detail on both `VolunteerMyRequests` and `CoordinatorSpeakerRequests`, "Start a match" → `match-runs?request=`, link-guard + host-portal contract tests.
- **Dataset findings fixed** (`c2c87c28`, `f3ca3229`, `2bb23f82`): `seed_pilot_engagement`'s redemption leg is now re-runnable (check-then-skip; terminal redemptions never reopened; balance validation untouched), and `pipeline_record_names_an_event` was rescoped to referents that must resolve — synthetic fan-out journeys deliberately name derived opportunity ids, not events (no FK by design; `pipeline_provisioning.py:692`), so a new sibling check `synthetic_fanout_names_a_derived_opportunity` asserts their real contract. **A check's scope changed — flagged here per convention.**
- `5003b514`: audit-found UI nit — stale `?request=` miss banner now clears.

## Verified state (measured, not assumed)

- PR #154: OPEN, MERGEABLE, CI 10/10 green at `6bc875f2`. Post-writing commits: `bf517563` (feedback cohort — 12 speakers now publish ratings), `0706ca78` (dataset one-shot receives the embedding flag it reads), `d5240148`/`fd3fb128` (ruff format), `6bc875f2` (flag-plumbing test now derives reader services from tools/ mounts — dataset legitimately reads the flag for the verifier capability check).
- Local suite at merge: 5239 pytest (non-integration) + 106 frontend + tsc + vite build green; new integration tests green against a scratch DB.
- Review stack `smartmatch_pr154` (web :15173, api :18080) runs `2bb23f82`, DB at migration `0036`.
- `verify_pilot_dataset` exits **0**: all 19 counted tables populated; 13/13 portal surfaces above per-login floors; 21/21 cross-table checks OK. `top-up-pilot-dataset` run twice — second run changed nothing (the re-runnability fix, proven).
- Logins on the review stack: `admin@test.com`, `pilot@test.com`, `student@test.com`, `volunteer@test.com` (password `Testing123!!`).

## Remaining for the next session

1. **Browser walkthrough** — the owner's real acceptance bar: sign in as each of the four logins on http://127.0.0.1:15173 and click every portal page; confirm connected data reads coherently (Playwright/chromium over CDP per the handoff's tooling note; the magic MCP stays out of scope).
2. **Two product gaps need an owner decision** (contract-pinned as absent, not papered over): (a) no read model publishes which host/organization filed a speaker request — the Connector detail shows the org directory, not the filer; (b) no host-readable match/confirmation endpoint — hosts see request statuses only.
3. **Merge + promote**: on merge to `main`, `origin/deploy` promotes to the VM; confirm `origin/deploy` SHA == VM HEAD == `https://pilot.plated.blog/api/health` release, and that all four logins work through the public host with fixture tokens still 401.
4. **Known empties are deliberate**: 13 of 49 tables stay empty (`outreach_send`, `event_feedback_qr*`, spend/reservation, `suppression_record`, `delivery_event`, `redrive_record`, `resource_grant`, `concurrency_lease`) — all zero-writer non-demo surfaces.
5. **Minor**: `synthetic_fanout_names_a_derived_opportunity` fails VACUOUS on tenants with zero eventless journeys — fine for the generated dataset, surprising on a minimal one. Retained unmounted pages (`Dashboard`, `Pipeline`, `Opportunities`) still call `grantedPortal(…,"admin")` and would refuse if remounted without updating.
