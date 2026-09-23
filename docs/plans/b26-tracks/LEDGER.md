# B26 build ledger

Parent plan: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (§8).
Orchestrator: Opus 5.5. The owner merges; the orchestrator never merges.
Updated: 2026-09-23 15:10 PDT.

Status vocabulary: planned · plan-reviewed (Opus) · codex-approved · implementing · PR #N · CI · reviewed · ready.
**Review of record (owner ruling 2026-09-23 13:10):** Codex is locked until 2026-09-28, so **Opus replaces Codex** — Opus plan gate + Opus diff review (max 2 rounds). Codex's one partial finding (T1 DST) is fixed in #210.

## Migration chain (stacked branches; owner merges in this order)

`0037_exercise_tables` (main) → `0038` T2 (#212) → `0039` T6b-1 → `0040` T8a → `0041` T4 (`speaker_request_id` on invitation batches, owner ruling 2026-09-23).

| Wave | Track | Status | Branch | PR | CI | Open findings |
|---|---|---|---|---|---|---|
| 1 | T1 | reviewed; DST fix red→green | `feat/b26-t1` | #210 | 10/10 @2c89266b | — |
| 1 | T7 | reviewed (Opus APPROVE) | `feat/b26-t7` | #211 | 10/10 @4225d64d | — |
| 1 | T6a | reviewed (security APPROVE; access-log redaction moved to T6b-1 R4) | `feat/b26-t6a` | #213 | 10/10 @6e1857fb | — |
| 2 | T2 (`0038`) | reviewed (DB APPROVE); T1 fix merged | `feat/b26-t2` | #212 | re-running @1ca64299 | secret scan fails from T6b-1 branch (fix in progress) |
| 3 | T3 | PR; diff review running | `feat/b26-t3` | #215 | 8/9 (secret scan, same cause) | — |
| 3 | T8b | reviewed; review fixes red→green | `feat/b26-t8b` | #214 | 10/10 @55624cdd | — |
| 3 | T6b-1 (`0039`) | implementing; 0039 pushed incl. T6b-2/T6b-3/T6b-5 additions | `feat/b26-t6b-1` | — | — | gitleaks false positive in cf7f5f80 → owner-approved rewrite |
| 3 | T4 (`0041`) | plan final @2208de84; waits on T8a's 0040 | `feat/b26-t4` | — | — | — |
| 4 | T8a (`0040`) | implementing (stacked on T6b-1) | `feat/b26-t8a` | — | — | — |
| 4 | T5 | implementing (stacked on T3) | `feat/b26-t5` | — | — | — |
| 4 | T6b-2 | plan final @f30f85e9 | `feat/b26-t6b-2` | — | — | — |
| 4 | T6b-3 | plan final @78432e2f (stacks on T6b-2) | `feat/b26-t6b-3` | — | — | — |
| 5 | T6b-4 | plan final @1b4cf71b | `feat/b26-t6b-4` | — | — | — |
| 5 | T8c | plan final @0a6b458e (3.0.0 proposed, not current) | `feat/b26-t8c` | — | — | — |
| 6 | T6b-5 | plan final @3fc6f8da | `feat/b26-t6b-5` | — | — | — |
| 6 | T8d | plan gate APPROVE; MED fixes applying | `feat/b26-t8d` | — | — | — |

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
| Codex gate | Opus replaces Codex for B26 (Codex locked to 09-28). |
| T6b-3 | OQ-1 409 opt_in_unavailable; OQ-2 Connector suppress on opted-in → 409; OQ-3 unsubscribe lift only on login address; OQ-4 fix outreach_contacts.py:788. |
| T6b-5 Q1 | Existing-login binding: Event Host logins only. |
| gitleaks | Owner approved force-push rewrite of feat/b26-t6b-1 to remove a false positive. |

## Follow-up cards (not B26)

1. `/i/` response tokens visible in Connector-readable draft bodies.
2. Cloudflare rate-limit rule on `POST /i/*` and `POST /v1/speaker-invitations/respond`.
3. Mail-scanner auto-submit risk on `/i/` (OQ-CBA-044).
4. T8a FU-1: undo a cancellation.
5. `frontend-broken-buttons.md` stale lines 111, 112, 157 (owner).
6. Delete branch `feat/b26-t2-plan`.
7. `cba.speaker_invitation.v1` into SYSTEM_ONLY_TEMPLATES (with the /i/ card).
8. Extraction upsert can rewrite a Speaker Request's `origin` (near OQ-CBA-065).
9. `ExactTime.__post_init__` compares wall-clock across DST fall-back (events.py:264).
10. `DELETE …/availability` (return to "Not stated"); batched roster availability state.
11. Connector wording for the Speaker-wins 409s; Full re-check at compose; band "changed since run".
12. Split factor_registry.py after the 3.0.0 flip (B26-FU-REGISTRY-SPLIT).
13. Privacy owner: Connector self-invite risk (T6b-1 §11).

## Stakeholder gates (plan §10) — all open

1. Ann/Pia/Lisa on Speaker accounts → `SPEAKER_PORTAL` stays off.
2. Named privacy owner.
3. IA West review of D2 → registry 3.0.0 stays `proposed`; `current` = 2.0.0.
4. Pilot hostname → no `speaker_portal_invite` sends.
5. Retention periods (D5).
