# B26 build ledger

Parent plan: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (§8).
Orchestrator: Opus 5.5. The owner merges; the orchestrator never merges.
Updated: 2026-09-23 10:55 PDT.

Status vocabulary: planned · plan-reviewed (Opus) · codex-approved · implementing · PR #N · CI · reviewed · ready.
**Codex:** usage-limited until 2026-09-23 12:10 PDT. Owner ruling: Opus stands in as the plan gate; Codex re-reviews every plan AND diff before a PR is called ready.

## Migration chain (stacked branches; owner merges in this order)

`0037_exercise_tables` (main) → `0038` T2 (#212) → `0039` T6b-1 → `0040` T8a → `0041` T4 (`speaker_request_id` on invitation batches, owner ruling 2026-09-23).

| Wave | Track | Status | Branch | PR | CI | Open findings |
|---|---|---|---|---|---|---|
| 1 | T1 | PR, Opus APPROVE; Codex pending | `feat/b26-t1` | #210 | 10/10 green @a4e2bbce | — |
| 1 | T7 | PR, Opus APPROVE; Codex pending | `feat/b26-t7` | #211 | 10/10 green @4225d64d | — |
| 1 | T6a | PR; Opus security review running | `feat/b26-t6a` | #213 | 10/10 green @6e1857fb | — |
| 2 | T2 (`0038`) | PR (stacked on #210); Opus DB+Python review running | `feat/b26-t2` | #212 | 10/10 green @358da818 | — |
| 3 | T3 | plan final-pass (C1 = UTC); stacks on T2 | `feat/b26-t3` | — | — | — |
| 3 | T4 (`0041`) | plan revising (C1 migration, C2 Q8 in-track, C3 b, C7 UTC) | `feat/b26-t4` | — | — | — |
| 3 | T8b | plan revising (owner rulings C1–C3, 90-day window) | `feat/b26-t8b` | — | — | — |
| 3 | T6b-1 (`0039`) | plan revising (review R1–R11; owner R8 = deny speaker on aggregate reads) | `feat/b26-t6b-1` | — | — | — |
| 4 | T8a (`0040`) | plan final @09ca1455, orchestrator-verified; stacks on T6b-1 | `feat/b26-t8a` | — | — | — |
| 4 | T5 | not started (needs T3 plan) | — | — | — | — |
| 4 | T6b-2 | not started (needs T3, T6b-1, T8a) | — | — | — | — |
| 4 | T6b-3 | not started (needs T6b-1) | — | — | — | — |
| 5 | T6b-4 | not started | — | — | — | — |
| 5 | T8c | not started (registry 3.0.0 ships `proposed`, not current) | — | — | — | — |
| 6 | T6b-5 | not started | — | — | — | — |
| 6 | T8d | not started | — | — | — | — |

## Owner rulings during the build

| Track | Ruling |
|---|---|
| T6a | `^/i/` Vite proxy in server + preview. |
| T8a C1 | Cancelled bookings leave `list_confirmed_speakers` and `pipeline_confirmed` (ADR-0011 register); replay → 409 `pipeline_record_cancelled`. |
| T8a C3 | New `/coordinator-portal/bookings` page (Coordinate group, `CalendarCheck`). |
| T6b-1 token | HMAC of invitation id under `SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET`; worker fills link; DB stores SHA-256. |
| T6b-1 R8 | Deny `speaker` in `_authorize_aggregate_read`; `speaker_at_owning_unit` matrix shape. |
| T8b | Same-day attended counts as upcoming; window exactly 90 days: [as_of−45, as_of) + [as_of, as_of+44]. |
| T4 C1 | Add `speaker_request_id` to invitation batches now (`0041`). |

## Follow-up cards (not B26)

1. `/i/` response tokens visible in Connector-readable draft bodies.
2. Cloudflare rate-limit rule on `POST /i/*` and `POST /v1/speaker-invitations/respond`.
3. Mail-scanner auto-submit risk on `/i/` (OQ-CBA-044).
4. T8a FU-1: undo a cancellation.
5. `frontend-broken-buttons.md` stale lines 111, 112, 157 (owner).
6. Delete branch `feat/b26-t2-plan`.

## Stakeholder gates (plan §10) — all open

1. Ann/Pia/Lisa on Speaker accounts → `SPEAKER_PORTAL` stays off.
2. Named privacy owner.
3. IA West review of D2 → registry 3.0.0 stays `proposed`; `current` = 2.0.0.
4. Pilot hostname → no `speaker_portal_invite` sends.
5. Retention periods (D5).
