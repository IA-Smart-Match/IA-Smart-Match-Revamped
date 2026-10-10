# Issue sweep tasklist — 2026-10-09

Source: all 78 issues on `IA-Smart-Match/IA-Smart-Match-Revamped`, explored by SWE-2 Max subagents
against the tree. Issue dumps with full bodies/comments: `.issue-explore/issues/<NNNN>.md`.

Legend: effort S (<~1 file or few lines) / M (multi-file or new tests) / L (new subsystem).
`agent` = an agent can ship it; `partial` = agent does prep/draft, human finishes;
`human` = owner/institutional call only; `external` = gated on outside systems/people.

> IMPORTANT: this checkout is on `Frontend-Experimental` (stale). All work must base on
> `origin/main` — sprint PRs #338–#346 already merged there. Migration head on main: 0046.

---

## Wave 1 — pure agent wins, small (do first, highest merge value)

### Bugs — one-file-ish fixes

- [ ] #272 — coordinator review queue prints raw role key — S — `CoordinatorReviewQueue.tsx:278` swap `{grant.role}` → `visibleRoleLabel(grant.role)` (precedent: `CoordinatorRedemptionQueue.tsx:120`)
- [ ] #280 — `ExactTime.__post_init__` wall-clock compare across DST fall-back — S — `events.py:264` → compare `astimezone(UTC)` instants (pattern at `eli.py:289`); add fold tests
- [ ] #282 — EAI non-ASCII login can't lift own unsubscribe — S — `suppression.py:178-188` ASCII-only check vs `login_accounts.py:155-157` NFC `.lower()` storage; add NFC-compare branch + test
- [ ] #281 — provider exception text leaks into `failure_reason` — S — `worker/outreach.py:494-510`; store fixed refusal sentence, keep exc in raised `ProviderFailure`/logs; check `/v1/jobs/{id}/events` too
- [ ] #279 — `eli.Engagement` allows cancelled+attended that migration 0040 CHECK forbids — S — `eli.py:249-265` add raise; DB already makes it unwritable
- [ ] #278 — `/v1/me/invitations` returns null `event_local_date`/`event_time_zone` — S — `persistence/cba_invitations.py:681-712` LEFT JOIN `event` on `batch.speaker_request_id` (0041 landed); update C3 comment
- [ ] #284 — dedupe /i/ token-page helpers (main.py vs token_pages.py) — S — delete private copies `main.py:852-985`, import from `token_pages`, `_read_answer_form` becomes thin Depends wrapper; fix stale `#213 unmerged` docstring
- [ ] #283 — volunteer drawer lacks `inert`; PagedList double live-region — S — port `SpeakerPortalLayout.tsx:93-146` inert/Escape pattern to `VolunteerPortalLayout.tsx:98-108`; collapse redundant aria-live at `PagedList.tsx:383` vs `SpeakerInvitations.tsx:231-237`

### Exercise UI — small

- [ ] #267 — per-screen tab titles — S — mirror `useSpeakerPageTitle` inside `ExerciseScreen` (`title` prop already exists)
- [ ] #268 — show which team the screen is working as — S — small `useTeamNumber()` hook + render "Team N" in existing `aside` slot
- [ ] #334 — event picker visible "Round one/two" label + Harbor "opens after round one" — S — `ExerciseEventPicker.tsx:127-135` (sr-only text → visible); DESIGN.md §11.1 copy
- [ ] #333 — compare view counts (both lists / only one / matched on major alone) — S — `MatchingCompareView.tsx:64-68`; `contributing_factor_keys == ["same_major"]` already in `ListEntryView`
- [ ] #270 — results 404 before first run → console noise — S-M — change contract to 200+null view (`exercise_results.py:302-311`, `ExerciseResults.tsx:98-107`); no OpenAPI regen (exercise routes not in contract)
- [ ] #332 — years in class order + mislabelled "years with nobody" row — S-M — seed `by_class_year` from `EXERCISE_CLASS_YEARS` (`markers.py:156-206`); skip `localeCompare` for `class_year` in `ListCompositionTable.tsx:132-134`; relabel `unlisted_class_years` row

### Ops/chore — small

- [ ] #274 — `scripts/vm/smartmatch.service` exercise containers don't survive reboot — S — replicate deploy.sh's conditional `-f docker-compose.exercise.yml` (gated on `SMARTMATCH_EXERCISE_WORKSPACE_SECRET` in `.env`) in ExecStart
- [ ] #263 — supersession banner on `owner-open-decisions-2026-09-19.md` — S — items 1–4 closed elsewhere; add dated banner at file top
- [ ] #262 — feature-implementation-template: fix `0034_<slug>` → `0044_<slug>` — S — `feature-implementation-template.md:86` (head line already correct)

## Wave 2 — agent-able, medium

- [ ] #287 — /i/ response tokens stored in Connector-visible draft bodies — M — add `cba.speaker_invitation.v1` to `SYSTEM_ONLY_TEMPLATES` AND re-scope worker `portal_body` gate (same PR — else invitation dispatch breaks); stop storing `/i/{token}` in `outreach_draft.body`, render at send time (mirror `/s/` portal precedent)
- [ ] #286 — T4 origin-flip: upsert must not rewrite `coordinator_entry` origin/provenance — M — guard `events.py:352-424` ON CONFLICT set_; then repair migration for NULL `speaker_request_id` batches (needs owner nod — expand-only)
- [ ] #285 — undo-cancellation + Connector wording for Speaker-wins 409s + "band changed since run" — M — three cards; undo needs owner ruling (0040 treats cancellation as durable fact — record un-cancel, don't erase); 409: never `str(exc)` when `response_channel == 'speaker_link'`; band: compare stored vs `current_speaker_load`
- [ ] #269 — invited-names list in rank order — S-M — order stored `invited` by `_invited_profile_nos` rank in `exercise_results_run.py` (pair with #327, same panel)
- [ ] #327 — "Email everyone (all 300)" four numbers beside "Your team's 30" + Harbor three-way — M — derive `seats_empty` at read in `results_repository.py`; tiles in `ResultPanels.tsx`; ship per-team seed as built, note #295
- [ ] #320 — one concise reason line per ranked profile — partial M — frontend half = drop `FactorNames` in `RankedList.tsx:253-270`; BUT Chau verified removing it does NOT surface Ann's phrases (tie lines win, `reasons.py:118`) — needs OQ-CE-12 amendment decision first. Ship frontend simplification only with that note.
- [ ] #306 — M7–M10 stale: CP-SAT + explanations already landed — M — correct stale status reports; residual = two-run scenario-compare read on match-runs surfaces (no gate)
- [ ] #304 — crawler: R3 threat model SIGNED 2026-09-03 (issue stale) — M-L — correct issue text; buildable piece = offline MP-1..5 eval corpus + harness in `tests/fixtures/crawl_sources/` (no network, same discipline as `event_sources`); live crawl stays gated (T-07/T-13)
- [ ] #308 — ADR backlog: B-11 exception-surface survey + B-07 seam test — M — B-11 is assigned to engineering ("survey every site that renders a DB exception"); B-07 asks for a test that no branch skips server-side load in `_subject_for_token` (`dependencies.py:99-198`)
- [ ] #310 — F-28/CP-V11 §4 leftover docstring/comment corrections — S — `eli.py:10` docstring, `ingest.py`/`feedback.py` F-copies, `defect-remediation.md` F-30 table, "F-1..F-27" count. Vendoring itself blocked (v1.1 doc not in tree)
- [ ] #290 — wip-analysis §0 skip-count refresh + skip-inventory audit — M — §0 table says 1, actual ~97 raw hits; refresh count + read-only audit vs `skip-site-inventory-2026-09-18.md`
- [ ] #264 — delete dead legacy-frontend code — M — 7 unrouted pages + orphan components (`AgenticOutreachPanel`, `FeedbackForm`, `OutreachWorkflowModal`, `CrawlerFeed`) + api.ts dead fns; partially stale (VolunteerAssignments/mockLogin already gone); update `test_frontend_zero_coercion_contract.py` — shares file with #260
- [ ] #336 — asking-choice verification harness — partial M — seeded driver per `AskingChoice`, pin ordering golden (reward/required > promise); fixture is `.accdb` not `.xlsx`
- [ ] #322 — residual of decided OQ-CE-14 supersession — partial M — most landed via #351; remaining: append dated supersession to OQ-CE-14, verify migration pins (post-#351 head is 0046), fix stale "OQ-CE-21 open" rows
- [ ] #299 — Justin's write-ups — partial — (a) draft one-page results-rule doc now (source: `simulation.py:1-38` docstring + `oq-ce-03-sample-result.md`); (b) row-by-row test list doc; exercise e2e harness doesn't exist (real build, defer or scope)
- [ ] #317 — wire exercise points counter — partial S — `ProfilePointsCounter.tsx` built but mounted nowhere; draft wire-up (`points` on `ListEntryView` + `RankedList` render) as proposal; mounting is product call
- [ ] #297 — pre-stage registry-3.0.0 flip — partial S — prep IA West review packet + unmerged flip diff (`CURRENT_CBA_REGISTRY = CBA_REGISTRY_3`, ADR-0027 → Accepted). DO NOT merge.
- [ ] #323 — Oct-16 reset: re-author `exercise-oct16-cleanup-runbook.md` + pre-flight scripts — partial M — execution gated on Danny's 4 answers + #326 deploy state

## Wave 3 — docs sweep (batch into 1–2 PRs)

- [ ] #258 — close stale OQ-CE rows (CE-03/04/16 say "not yet merged" but PR #238 merged) — S
- [ ] #259 — refresh `backlog.md` — mockup/barchart/coverage-notice built; points counter partial — S
- [ ] #260 — `frontend-broken-buttons.md` — B26 merged, count 41→42/42, `VolunteerAssignments.tsx` deleted — S (with #264)
- [ ] #261 — README capability table: add class-exercise rows; golden count is 19 not 11/13 — S

## Wave 4 — prep-only drafts (human finishes)

- [ ] #307 — draft decision packets for OQ-CBA-011/021/044/063/064/065/066 (register: `cba-phase-deferred.md`)
- [ ] #301/#302 — draft packets for uncovered OQ-SE/SC rows (SE-03 highest leverage)
- [ ] #314 — draft OQ-AMP-01…04 answers + FixtureAmpProvider sketch
- [ ] #311 — cross-NOTES.md comparison of mascot redesigns A/B/C
- [ ] #315 — stale (no ContentRanker/LearnedRanker in tree); draft Stage-A skeleton or correct issue
- [ ] #298 — options draft: pilot hostname candidates + per-table retention table (B-01)
- [ ] #294 — pre-draft 8-team diff (`EXERCISE_TEAM_NUMBERS` → 1..8, ~15 consumer files), hold unmerged
- [ ] #293 — draft Ann check-in note + two-branch memo (accept D9 vs change tie-break)
- [ ] #292 — draft dated confirmation row (SPEAKER_PORTAL verified False in all 3 scopes)
- [ ] #291 — draft reply-options memo re parallel tracks
- [ ] #296 — candidate roster-row draft only; naming is Danny's act
- [ ] #265/#266 — git chores: restore 19 stranded files from `wip/local-main-scratch-2026-09-26` (266 first), then prune merged branches; 9 unmerged need human keep/delete
- [ ] #288 — factor_registry.py split — parked until #297 flips

## Wave 5 — blocked / human-only (status comment only, do not touch)

- [ ] #316 Handshake+mobile+PWA — parked, all OQ rows open — comment status
- [ ] #313 img2threejs keep/delete — dir not in tree — owner local decision
- [ ] #312 career-goal-fit mockup — file absent from tree — owner supplies or drops
- [ ] #309 MM-A09 legacy PII — CANNOT CLOSE — comment re-affirming blocked-on-owner
- [ ] #305 cloud deploy — all repo-side criteria met; needs Supabase project + OQ-F5 answers
- [ ] #303 live outreach — code complete; all 9 OQ-R4 items external
- [ ] #300 A1b IdP — scaffold done; worksheet fields external by design
- [ ] #295 email-everyone seed — waiting on Ann (deadline passed; default A stands for Oct 16)
- [ ] #289 OQ-CE-17 factors — needs Ann's bucket answer (1 event = 0.5 or 1.0)
- [ ] #273 license_line — needs Ann + Danny answers; Option C (status quo) in force
- [ ] #275/#276 — Cloudflare dashboard rules — external (comment with §5 spec to replicate)

## Closed — verified merged (no action)

PRs #338–#346 + #344 all merged to main: #335(#338), #331(#344), #330+#329(#340), #328+#326+#319+#271(#345), #325+#318(#339), #321(#346).
Note: closures unverifiable from `Frontend-Experimental` checkout — verified via `gh pr list` merge state instead.
