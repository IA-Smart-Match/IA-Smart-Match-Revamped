# B26 build ledger

Parent plan: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (§8).
Orchestrator: Opus 5.5. The owner merges; the orchestrator never merges.
Updated: 2026-09-24 07:45 PDT.

Status vocabulary: planned · plan-reviewed (Opus) · codex-approved · implementing · PR #N · CI · reviewed · ready.
**Review of record (owner ruling 2026-09-23 13:10):** Codex is locked until 2026-09-28, so **Opus replaces Codex** — Opus plan gate + Opus diff review (max 2 rounds). Codex's one partial finding (T1 DST) is fixed in #210.

## Migration chain (stacked branches; owner merges in this order)

`0037_exercise_tables` (main) → `0038` T2 (#212) → `0039` T6b-1 → `0040` T8a → `0041` T4 (`speaker_request_id` on invitation batches, owner ruling 2026-09-23).

| Wave | Track | Status | Branch | PR | CI | Open findings |
|---|---|---|---|---|---|---|
| 1 | T1 | reviewed | `feat/b26-t1` | #210 | 10/10 @2c89266b | — |
| 1 | T7 | reviewed | `feat/b26-t7` | #211 | 10/10 @4225d64d | — |
| 1 | T6a | reviewed | `feat/b26-t6a` | #213 | 10/10 @6e1857fb | — |
| 2 | T2 (`0038`) | reviewed | `feat/b26-t2` | #212 | 10/10 @1ca64299 | — |
| 3 | T3 | reviewed | `feat/b26-t3` | #215 | 10/10 @8aacf50e | — |
| 3 | T8b | reviewed | `feat/b26-t8b` | #214 | 10/10 @55624cdd | — |
| 3 | T6b-1 (`0039`) | reviewed (security) | `feat/b26-t6b-1` | #217 | 10/10 @d5a39b48 | — |
| 4 | T5 | reviewed | `feat/b26-t5` | #216 | 10/10 @cc2ac502 | owner browser pass |
| 4 | T8a (`0040_booking_cancellation`) | reviewed | `feat/b26-t8a` | #218 | 10/10 @a622fb10 | — |
| 4 | T4 (`0041_batch_speaker_request`) | reviewed; verifying fixes | `feat/b26-t4` | #220 | 10/10 @0237b79b | — |
| 4 | T6b-2 | reviewed; LOW fixes in | `feat/b26-t6b-2` | #219 | 9/10 (python) @ee1c0fd6 | fixing CI |
| 5 | T6b-3 | review fixes in progress | `feat/b26-t6b-3` | #222 | 10/10 @270cb113 | delta security review |
| 5 | T8c | CI fix + review | `feat/b26-t8c` | #221 | 9/10 (python) @80cbdaba | review pending |
| 5 | T6b-4 | built, PR opening | `feat/b26-t6b-4` | — | — | a11y review |
| 6 | T6b-5 | mid-merge (switcher) | `feat/b26-t6b-5` | — | — | — |
| 6 | T8d | plan final @6f8de7ac | `feat/b26-t8d` | — | — | after T8c + T6b-4 |

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
