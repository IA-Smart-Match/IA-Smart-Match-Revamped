# B26 build ledger

Parent plan: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` (§8).
Orchestrator: Opus 5.5. The owner merges; the orchestrator never merges.
Updated: 2026-09-24 (final).

Status vocabulary: planned · plan-reviewed (Opus) · implementing · PR #N · CI · reviewed · ready · merged.
**Review of record (owner ruling 2026-09-23 13:10):** Codex is locked until 2026-09-28, so **Opus replaces Codex** — Opus plan gate + Opus diff review (max 2 rounds). Codex's one partial finding (T1 DST) is fixed in #210.

## Migration chain

`0037_exercise_tables` → `0038_speaker_availability` (T2, merged) → `0039_speaker_portal` (T6b-1) → `0040_booking_cancellation` (T8a) → `0041_batch_speaker_request` (T4). Alembic revision ids ≤ 32 chars. No other migration.

## Tracks

`main` @ee017ec1 (#210–#216 and #226 merged). Every open branch contains `main` and all of its stack parents.

| Merge step | Track | PR | Status | Head | CI | Review of record |
|---|---|---|---|---|---|---|
| — | T1 | #210 | merged | 2c89266b | 10/10 | Opus APPROVE |
| — | T7 | #211 | merged | 4225d64d | 10/10 | Opus APPROVE |
| — | T2 (`0038`) | #212 | merged | 1ca64299 | 10/10 | Opus APPROVE |
| — | T6a | #213 | merged | 6e1857fb | 10/10 | Opus APPROVE (security) |
| — | T8b | #214 | merged | 55624cdd | 10/10 | Opus APPROVE |
| — | T3 | #215 | merged | 8aacf50e | 10/10 | Opus APPROVE |
| — | T5 | #216 | merged | cc2ac502 | 10/10 | Opus APPROVE |
| — | ci: python timeout 15→25 (R-D) | #226 | merged | a065f583 | 10/10 | Opus APPROVE, 2 LOW |
| 1 | T6b-1 (`0039`) | #217 | ready | 528c9940 | 10/10 | Opus APPROVE (security), main-sync delta 1 round |
| 2 | T8a (`0040`) | #218 | ready | e5567a26 | 10/10 | Opus APPROVE, main-sync delta 1 round |
| 3 | T4 (`0041`) | #220 | ready | 866c8614 | 10/10 | Opus APPROVE, main-sync delta 1 round |
| 4 | T6b-2 | #219 | ready | d877d280 | 10/10 | Opus APPROVE (security), T4-sync delta 2 rounds |
| 5 | T6b-3 | #222 | ready | d17f74e8 | 10/10 | Opus APPROVE (security), T4-sync delta 2 rounds |
| 6 | T6b-4 | #223 | ready | d7cb91ba | 10/10 | Opus APPROVE (security), sync delta 1 round |
| 7 | T6b-5 | #224 | ready | 2f63199a | 10/10 | Opus APPROVE (security), R-B/R-C + allow-list delta 3 rounds |
| 8 | T8c | #221 | ready | 43e1459e | 10/10 | Opus APPROVE, R-A delta 1 round |
| 9 | T8d | #225 | ready | 98009078 | 10/10 | Opus APPROVE, R-A delta 1 round |

### 2026-09-24 red → green evidence

| PR | Change | Red | Green |
|---|---|---|---|
| #219 | T4 helper port (`a006fe3a`) | 18c86a9c (19 of 50 fail, 422 `speaker_invitation_request_required`) | 78bd932a (50 pass) |
| #222 | T4 helper port | b2ddfba4 (8 of 33 fail) | b9ba3053 (33 pass) |
| #221 | R-A: load numbers off the wire | ca397674 | 4f36dfab |
| #225 | R-A: T8d views, availability `load`, api.ts | 9bb691dc | c116bb1f |
| #224 | R-C backend / frontend | 3ea1f345 / 52c8fdf0 | 76cd6370 / b8137704 |
| #224 | R-B seed merge | 33682868 | e040d013 |
| #224 | T4 helper port after T6b-4 merge | 655d3ff1 (2 fail) | 89cffce8 (54 pass) |
| #224 | R-C true allow-list (owner, row 10) | bbac8631 (9 of 145 fail) | 1e0c94fb (145 pass) |
| #217/#218/#220/#223 | merges only | — | pass counts in merge commit bodies |
| #226 | CI config | #224 python run cancelled at 15 min, all tests passing | #226 python 9m52s under 25 |

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
| R-A (09-24) | No load numbers on the API wire: `completed_hours`, `confirmed_hours`, `capacity_hours`, `utilization` only in the stored run payload. Owner confirmed: `measurable`, `as_of`, `eli_formula_version`, `multiplier`, `composite_before_load` stay; `declared_capacity_hours_per_90_days` (Speaker's own input) is out of scope. |
| R-B (09-24) | Seed merge onto a foreign login only for `volunteer` entries when holder roles ⊆ {speaker, volunteer} ({} included); else `SeedConflictError`. |
| R-C (09-24) | Existing-login binding is a true allow-list: active roles minus `speaker` must equal {volunteer}. No role / other role → generic 400 at activation, 409 `speaker_portal_address_not_host_login` at invite. |
| R-D (09-24) | Python CI job `timeout-minutes` 15 → 25 (#226). |

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
14. Provider exception text reaching `failure_reason` on portal sends.
15. T4 origin-flip backfill gap.
16. EAI (non-ASCII) login address can't lift own unsubscribe (T6b-3 LOW-5).
17. Volunteer drawer lacks `inert` (T6b-5 LOW); `PagedList` double live-region (T6b-4 LOW).
18. T6b-2 C3: `/v1/me/invitations` returns null `event_local_date` / `event_time_zone`; fill from `speaker_request_id` (T4 makes it possible).
19. R-B then unbind: unbinding a Speaker whose portal-created login later gained `volunteer` via the seed retires the shared credential (`login_shared=false`). Documented in `vm-deploy.md`. The retired account keeps `volunteer`, so re-activation revives it (red test in #224).
20. Duplicate `/i/` token-page helpers in `main.py` vs `token_pages.py`; stale "#213 unmerged" docstring.
21. `eli.Engagement` accepts cancelled + attended together; 0040's CHECK forbids it.
22. Small doc drift: `api.ts` orphan JSDoc above `MatchAvailability`; README "11 golden cases" (now 13); T8c/T8d plan text stale after R-A.

## Stakeholder gates (plan §10) — all open

1. Ann/Pia/Lisa on Speaker accounts → `SPEAKER_PORTAL` stays off.
2. Named privacy owner (also covers the Connector self-invite risk).
3. IA West review of D2 → registry 3.0.0 stays `proposed`; `current` = 2.0.0.
4. Pilot hostname → no `speaker_portal_invite` sends.
5. Retention periods (D5).
