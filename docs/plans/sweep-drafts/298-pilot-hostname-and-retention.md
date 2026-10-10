> DRAFT — needs Danny (BrooklynD23) and the IA West privacy owner decision. Nothing here is decided.

# #298 — Pilot hostname candidates and per-table retention (B-01)

## Context and sources

| Fact | Source |
|---|---|
| Speaker-portal invite links are built from `outreach_public_base_url`; the stable address is open (row 4) | `docs/plans/2026-09-22-b26-self-service-availability-plan.md` section 10 (line 632) |
| The setting, env var `SMARTMATCH_OUTREACH_PUBLIC_BASE_URL`, defaults to `http://localhost:8080` | `services/api/smartmatch_api/config.py:98,113-116` (prefix `SMARTMATCH_` at `:38`) |
| API builds the link as `<base>/i/<token>` | `services/api/smartmatch_api/routers/cba_invitations.py:566` |
| Worker reads the same value | `services/worker/smartmatch_worker/main.py:492`, `services/worker/smartmatch_worker/config.py:428` |
| Invite template id `cba.speaker_portal_invite.v1` | `python/smartmatch_domain/smartmatch_domain/speaker_portal.py:72` |
| Owner's earlier ask: "pick the pilot VM hostname"; reply template `The exercise runs at <hostname>, exercise scope only` | `docs/archive/plans/owner-open-decisions-2026-09-19.md:13,91` |
| D5: retention periods per evidence table deferred; "No retention class is enforced in code today"; needs a privacy/records owner | `docs/decisions/pilot-decisions.md:118` |
| B-01: five append-only tables; institution (records policy) and product owner (match-run reproducibility) own it | `docs/architecture/decisions/adr-backlog.md:24-44` |
| Risk R-13 and the growth note | `docs/architecture/risk-register.md:35`, `docs/architecture/data-architecture.md:158` |
| No named privacy owner exists | B26 plan section 10 row 2 (line 630) |

## (a) Hostname candidates

Docs already name two hosts: `pilot.plated.blog` as the corroborated pilot VM hostname (`docs/operations/classroom-vm-cloudflare-tunnel.md:370`, `docs/architecture/CURRENT_ARCHITECTURE_AUDIT.md:89`) and `exercise.plated.blog` for the class-exercise scope (`docs/operations/exercise-oct16-cleanup-runbook.md:4`). No other domain is named in the repo docs. Candidate 4 below is therefore a placeholder, not a real name.

Config key for every option: `SMARTMATCH_OUTREACH_PUBLIC_BASE_URL` (`config.py:98`), set on both api and worker (`main.py:492` in the worker). It must be an origin with scheme; the API strips a trailing slash (`cba_invitations.py:566`).

| Option | Value | For | Against / to check |
|---|---|---|---|
| 1 | `https://pilot.plated.blog` | Already corroborated in docs as the pilot VM; no new DNS or tunnel work | Personal-domain look on emails to Speakers; ties invites to the current VM and tunnel |
| 2 | `https://exercise.plated.blog` | Live today for Ann's exercise | Wrong scope: the exercise host serves exercise scope only, no CBA routers (`owner-open-decisions-2026-09-19.md:91`); would need that to change. Likely unsuitable |
| 3 | A separate subdomain of the same domain, name chosen by owner (for example a speaker-facing label) | Keeps invites apart from the pilot admin host; can move without renaming the pilot | New tunnel route and DNS; one more host to run |
| 4 | An institution-owned domain (placeholder; none named in docs) | Strongest trust signal to Speakers; survives a change of VM | Needs the institution to grant it; lead time unknown; D5/D8 privacy owner not yet named |

Cross-cutting questions: links already sent under an old base are not rewritten by changing the setting (the token URL is built at send time, `cba_invitations.py:566`; confirm in the worker path); the default `http://localhost:8080` must never reach a real send (`config.py:111-112` comment says it only changes fixture text).

## (b) Retention table: candidate options, no values chosen

Append-only and migration evidence: `job_event` 0001; `match_run` 0018 (immutability trigger `match_run_is_immutable`, 0018:291); `pilot_login_attempt` 0020; `delivery_event` 0021; `contact_channel_transition` 0023 (trigger `contact_channel_transition_is_append_only`, 0023:240); `contact_channel_speaker_choice` 0039 (append-only trigger, 0039:296). Migration directory: `db/migrations/versions/`. For `job_event` and `pilot_login_attempt` the "append-only" label comes from B-01 and R-13, not a trigger I confirmed; check before relying on it.

| Table | What it holds | Append-only? | Period options (not chosen) | Driver to confirm |
|---|---|---|---|---|
| `job_event` | Per-job progress events streamed to the client | Yes per B-01/data-architecture:158 (trigger unconfirmed) | keep as long as the job; fixed window after job end; aggregate then drop | Institution records policy; whether events are evidence or telemetry |
| `delivery_event` | Outreach delivery outcomes per send | Yes, trigger (migration 0021) | fixed window after send; keep for dispute window; aggregate counts then drop | Records policy for outreach; contact-rule and dispute needs |
| `contact_channel_transition` | Opt-in/opt-out history of a contact channel | Yes, trigger (0023:240) | keep while the contact is active; keep as long as consent proof is needed; fixed window after last transition | Consent-proof obligation (D8 disclosure-consent); privacy owner |
| `contact_channel_speaker_choice` | Speaker's own opt-in/out per channel | Yes, trigger (0039:296) | same options as the row above | D8; privacy owner. Not in B-01's list of five: confirm whether it belongs in B-01 |
| `pilot_login_attempt` | Login attempts for pilot accounts | Yes per B-01 (trigger unconfirmed) | short window for abuse detection; longer window for audit; aggregate then drop | Security/audit policy; records policy for login logs |
| `match_run` | Immutable snapshot of each matching run | Yes, trigger `match_run_is_immutable` | keep all (reproducibility commitment); keep latest N per unit; export then drop after a window | Product owner: ADR-0011 reproducibility; "dropped, aggregated, or exported first" (adr-backlog.md:28-32) |
| `speaker_portal_invitation` (0039) | Invitation records with expiry | Not stated append-only | prune after expiry; keep while booking exists; fixed window after expiry | B26 plan section 10 row 5 lists "expired invitations" as waiting on D5 |

Also waiting on D5 per the B26 plan (line 633): ended availability windows and cancelled bookings. They have no table named in this draft; add rows once the tables are confirmed from the B26 migrations.

What "deleted" means is a per-table choice: dropped, aggregated, or exported first (adr-backlog.md:28-30). Because the tables are protected by update/delete-refusing triggers, any prune needs a deliberate, recorded path around them; that is an engineering question once the period is set.

## Open questions

1. Which hostname option, and who owns DNS/tunnel for it? Danny.
2. Is the institution willing to supply a domain (option 4), and by when? Danny with the IA West contact.
3. Who is the named privacy/records owner (none named today)? Danny and IA West.
4. Period per table, chosen from the options above. IA West privacy owner for the records tables; product owner (Danny) for `match_run`.
5. For each table, what does "deleted" mean: drop, aggregate, or export first? Privacy owner with Danny.
6. Does `contact_channel_speaker_choice` join B-01's list? Danny.
7. Is legal review required before external or live-data use (D5 says it is a later gate)? Privacy owner.
8. Do already-sent invitations keep working after a hostname change? Engineering check, then Danny.
