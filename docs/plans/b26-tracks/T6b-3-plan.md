# B26 T6b-3 — Self-service channel consent, the Speaker-wins rule, and `lifted_at` in every send-eligibility read

**Next action:** once the §10 start gate passes (`0039` carries §1.2 A and B, and T6b-2's `routers/speaker_self.py` is pushed), run milestone 0: merge `origin/feat/b26-t6b-2` into `feat/b26-t6b-3`.

**Revision 5, 2026-09-23.** T6b-3 stacks on T6b-2 and imports its authorizer; it writes no subject lookup of its own (orchestrator follow-up ruling, supersedes revision 4's "create it if first"). Revision 4 aligned §5.2 with T6b-2's order. Revision 3 applied the security plan gate (APPROVE, findings S1–S7): S1 §5.4 G2, S2 §6 and §7 race 10, S3 §10 gate, S4 §5.4 G3, S5 §5.4 and §6, S6 §5.1 W2, S7 §8 guard 1. Revision 2 recorded the owner rulings on OQ-1 to OQ-7 (§11). The §1.2 `0039` additions A and B went to the T6b-1 implementer, so the migration fallback is only a documented contingency (§10, contingency C). Revision 1 was the first plan. Docs only. No source file, route or migration is written by this document.

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2 (privacy and consent constraints), §3.2 (`suppression_record.lifted_at`, `lifted_by_user_id`, source `speaker_portal`), §4.4, §7 row 8, §8, §11 risk 1. ADR-0014 rule 2 (withdrawal is immediate and prospective). T6b-1 plan: `origin/feat/b26-t6b-1:docs/plans/b26-tracks/T6b-1-plan.md` (revision 3), boundary 3, §10 L2, Appendix A.

**Base and merge order.** The implementation is built on this branch, `feat/b26-t6b-3` (owner ruling: no separate `-impl` branches), stacked on **T6b-2** (`feat/b26-t6b-2`), because T6b-3 imports T6b-2's authorizer (§5.2). T6b-2 carries T8a (`feat/b26-t8a`) → T6b-1 (`feat/b26-t6b-1`) → T2 (`feat/b26-t2`, PR #212) → T1 (`feat/b26-t1`, PR #210), and T3 as T6b-2's dependency. Milestone 0 merges `origin/feat/b26-t6b-2` into this branch. The PR body says **"Merge #210, #212, then T6b-1, T8a, T3, T6b-2 PRs first"**. T6b-3 needs nothing from T4.

**Line numbers** are `main` @ `1909278f`. T6b-1 edits `routers/outreach.py` (`create_draft`, `send_draft`) and `worker/outreach.py` (the §6.2 gate), so re-grep those two files on the stacked base before editing.

## 0. Boundaries

1. **T6b-3 changes every send-eligibility read.** T6b-1 changes none (its boundary 3). §1 proves the split is safe.
2. **Suppression is still the only send gate.** The Speaker's choice log (§4.2) decides the Speaker-wins 409s only. No send path reads it.
3. **No frontend.** The Contact preferences page is T6b-4. The one exception is an optional `speaker_choice` field on the Connector channel type in `api.ts` (§5.4).
4. **No Connector un-suppress.** `suppressed: false` stays `400 outreach_unsuppress_not_supported` (OQ-009). Only the Speaker lifts, and only the sources the owner named.
5. **Routes are mounted only under `Capability.SPEAKER_PORTAL`** (off in every scope, T6b-1 C2). The Connector-side changes (§5.4) ship live, because they change nothing until a Speaker choice row exists, and none can exist while the capability is off.

## 1. Who changes which read — T6b-1 and T6b-3 made consistent

### 1.1 The split

| Source | Says |
|---|---|
| Parent §3.2 | "Every send-eligibility read changes to `lifted_at IS NULL` **in the same PR**" as the column. |
| Parent §8 | T6b-3 owns "`lifted_at` across every send-eligibility read". |
| T6b-1 boundary 3, §10 L2, Appendix A | `0039` adds the columns; no T6b-1 code sets them; every reader is unchanged; T6b-3 owns all of them. |

**Verdict: the split is safe, and T6b-3 changes all readers.** The parent's intent is that no reader ever sees a lifted row it does not understand. That holds because:

1. A row can be lifted only by code that writes `lifted_at`.
2. The only writer is `SuppressionRepository.lift` (§5.1), and it ships in T6b-3 in the same commit (milestone 2) as every reader change.
3. Between the T6b-1 merge and the T6b-3 merge, every row has `lifted_at IS NULL`, so "a row exists" and "an active row exists" are the same predicate.

T6b-3 pins the invariant with a source test: `lifted_at` is written only in `smartmatch_persistence/suppression.py` (§8, `test_suppression_single_reader.py`). Milestone 5 corrects the parent §3.2 sentence to "in T6b-3, the PR that adds the first writer".

T6b-1's Appendix A is accurate: its 4 readers and 5 callers match the code at `1909278f`. T6b-3 adds 3 items it does not list: the generic contact transition (`outreach_contacts.py:788`, which ignores suppression, OQ-4), the Speaker-wins guard on **both** Connector transition surfaces, and the coordinator suppress write (§5.4 G3).

### 1.2 What T6b-1 must change (two `0039` additions, schema only; sent to the T6b-1 implementer 2026-09-23)

Neither addition needs T6b-1 code. Both follow boundary 3's pattern: schema in `0039`, behaviour in T6b-3.

| # | Addition | Why it cannot wait |
|---|---|---|
| A | CHECK `ck_suppression_record_lift_source`: `lifted_at IS NULL OR source IN ('speaker_portal', 'unsubscribe_link', 'one_click')` | "Bounce and complaint are never lifted by either side" becomes structural, not a convention. A hand-written `UPDATE` or a future Connector lift route fails at the database. Coordinator suppressions are covered too (the owner's lift list excludes them). |
| B | Table `contact_channel_speaker_choice` (DDL in §4.2) | The Speaker-wins 409s need "the Speaker's latest action on this channel". The data at hand cannot answer it (§4.1). A table added later would be a fifth B26 migration after `0041` and would stack T6b-3 on T4 as well. |

T6b-1 test impact: 5 more CHECK keys in `tests/integration/test_check_constraints.py` (A, plus B's `_choice`, `_sequence`, `_lift` and `_lift_source`); `"contact_channel_speaker_choice"` in `tests/integration/conftest.py` `_TENANT_SCOPED_TABLES` after `"contact_channel_transition"`; the downgrade drops B first. T6b-1's R7 downgrade guard already covers B: a choice row needs a bound Speaker, and binding needs an accepted invitation.

**Contingency only.** A and B are being folded into `0039`. If `0039` nevertheless merges without them, contingency C (§10) adds them in `00NN_speaker_channel_choice` at current head plus one (parent header rule), and it goes on the T6b-2-based branch at that head.

## 2. Files

| Path | Change |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/suppression.py` | **New.** `SuppressionSource` (6 values), `LIFTABLE_BY_SPEAKER`, `NEVER_LIFTED`, `SOURCE_RANK`, `merge_suppression(...)`, `speaker_lift_verdict(...)`, `speaker_facing_reason(...)`. Pure. §3.1. |
| `python/smartmatch_domain/smartmatch_domain/speaker_channel_consent.py` | **New.** `SpeakerChoice` (`opt_in`, `opt_out`), `OPT_IN_START_STATES`, `opt_in_path(current)`, `connector_transition_conflict(latest, current, requested)`, `SELF_SERVICE_EVIDENCE`, `SELF_SERVICE_REASON`. Pure. §3.2. |
| `python/smartmatch_persistence/smartmatch_persistence/suppression.py` | **New.** The only module that reads or writes `suppression_record` outside `schema.py` and migrations. `active_suppression_exists(channel)`; `SuppressionRepository.record`, `.lift`, `.lock_for_address`, `.is_active`. Never commits. §5.1. |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_channel_choice.py` | **New.** `SpeakerChoiceRepository.append`, `.latest_for_channel`, `.latest_for_channels`, `.last_transition_at_for_channels`. Never commits. §4.2. |
| `python/smartmatch_persistence/smartmatch_persistence/contacts.py` | `_selectable()` (`:124-157`) uses `active_suppression_exists`. New `lock(session, *, tenant_id, contact_channel_id) -> bool`: `SELECT id FROM contact_channel WHERE tenant_id = :t AND id = :id FOR UPDATE`, its own statement with no join and no subquery (S5). Callers then re-read through the unchanged `get` (`:254`). New `list_for_speaker(tenant_id, professional_id, limit)`. Module docstring. |
| `python/smartmatch_persistence/smartmatch_persistence/outreach.py` | `load_recipient` (`:217-282`) uses `active_suppression_exists`. `suppress` (`:683-728`) and `is_suppressed` (`:730-740`) delegate to `SuppressionRepository`. `SuppressionOutcome` gains `write`. Module docstring and the "first suppression stands" paragraph. |
| `python/smartmatch_persistence/smartmatch_persistence/schema.py` | Comments only at `:1722` and on `suppression_record` (`:2076`). The DDL mirror is T6b-1's. |
| `services/api/smartmatch_api/routers/speaker_self.py` (T6b-2's module) | **Not edited. Imported.** `_authorize_speaker_self`, `_SPEAKER_SELF_ROLES`, `SpeakerPortalRepository` (for `find_bound_profile`) and `BoundSpeakerProfile`, all from `smartmatch_api.routers.speaker_self` (§5.2). |
| `python/smartmatch_persistence/smartmatch_persistence/speaker_portal.py` (T6b-1's module, where T6b-2 adds `find_bound_profile`) | T6b-3 adds two methods and no subject lookup: `lock_bound_profile_share(...)` and `login_address(...)` (§5.2). |
| `services/api/smartmatch_api/speaker_channel_consent.py` | **New.** `opt_in(...)` and `opt_out(...)`: one transaction each, the §7 lock order. Routes stay thin. |
| `services/api/smartmatch_api/routers/me_contact_channels.py` | **New.** `router = APIRouter(prefix="/v1/me/contact-channels", tags=["speaker-portal"])`, 3 routes. §5.3. |
| `services/api/smartmatch_api/main.py` | One row in `CAPABILITY_SCOPED_ROUTERS` (`:338`) under `Capability.SPEAKER_PORTAL`. |
| `services/api/smartmatch_api/routers/cba_contact_channels.py` | Transition (`:662`): lock the channel, Speaker-wins guard before `assert_transition` (`:718`). `_view` (`:319`): `speaker_choice`, `speaker_choice_at`. List (`:466`): one batched latest-choice read. §5.4. |
| `services/api/smartmatch_api/routers/outreach_contacts.py` | Transition (`:727`): lock and the same guard; pass `suppressed=` at `:788` (OQ-4). PATCH suppress (`:694`): lock the channel; Speaker-wins guard (OQ-2). §5.4. |
| `contracts/openapi/smartmatch.json` | `make openapi`: only the additive `speaker_choice` fields. The `/v1/me/contact-channels` paths are unmounted by default and stay out of the document. |
| `apps/web/legacy-frontend/src/lib/api.ts` | `SpeakerContactChannel` (`:3992`) gains optional `speaker_choice` and `speaker_choice_at`. No UI. |
| Docs (milestone 5) | `docs/plans/open-questions/r4-outreach-deferred.md` OQ-009 (`:236`): the Speaker's own lift is built; Connector un-suppress and the coordinator actor stay open. `docs/plans/open-questions/cba-phase-deferred.md` OQ-CBA-035 (`:47`): "built in T6b-3". Parent §3.2 sentence (§1.1). |
| Tests | §8 and §9. |

## 3. The rules as code (domain, pure)

### 3.1 `smartmatch_domain.suppression`

| Source | Rank | Speaker may lift | Speaker-facing reason |
|---|---|---|---|
| `bounce` | 3 | never | `delivery` |
| `complaint` | 3 | never | `delivery` |
| `coordinator` | 2 | no | `connector` |
| `unsubscribe_link` | 1 | only on the login address (OQ-3) | `unsubscribed` |
| `one_click` | 1 | only on the login address (OQ-3) | `unsubscribed` |
| `speaker_portal` | 0 | yes, on any of the Speaker's channels | `your_opt_out` |

`uq_suppression_record_address` (`schema.py:2096`) keeps **one row per address**. The row holds the highest-ranked source now standing:

`merge_suppression(existing, incoming_source, at, origin_send_id) -> SuppressionWrite`

| Existing row | Result |
|---|---|
| none | `INSERT` (`source`, `suppressed_at = at`, `origin_send_id`) |
| lifted | `REOPEN`: `source`, `suppressed_at = at`, `origin_send_id` are set; `lifted_at` and `lifted_by_user_id` are cleared |
| active, incoming rank higher | `ESCALATE`: `source` and `origin_send_id` are set; `suppressed_at` is kept ("when did they first ask us to stop") |
| active, rank equal or lower | `NOOP` |

`speaker_lift_verdict(existing, *, address_is_login: bool) -> LIFT | NOTHING_TO_LIFT | REFUSED(reason)` (OQ-3 ruling)

- None or lifted → `NOTHING_TO_LIFT`.
- Active `speaker_portal` → `LIFT` on any of the Speaker's channels (the Speaker made it).
- Active `unsubscribe_link` or `one_click` → `LIFT` only when `address_is_login`, otherwise `REFUSED("unverified_address")`.
- Active `coordinator` → `REFUSED("connector")`. Active `bounce` or `complaint` → `REFUSED("delivery")`.

`address_is_login` is `lower(btrim(channel.address)) = lower(btrim(login.email))`, where `login` is the `user_account` at `speaker_profile.account_user_id`. That is the address the invitation token proved (T6b-1 §5 step 10 stores it trimmed as the login email; T6b-5's existing-login mode binds only an account holding the invited address). No other address of the Speaker has a proof of control, so an unsubscribe made there may have come from whoever holds it now.

**Why one row loses no decision.** For either value of `address_is_login`, the liftable sources are exactly those ranked below a threshold: rank 0 on another address, ranks 0–1 on the login address. Escalation only goes up. So the row's source is non-liftable exactly when any non-liftable fact is standing, and a lift is all-or-nothing. That is why `speaker_portal` ranks **below** the unsubscribe sources after OQ-3: with the opposite order, a Speaker opt-out on top of an unsubscribe at another address would hide that unsubscribe, and a later opt-in would lift it. `test_single_row_merge_matches_the_per_source_model` proves the equivalence over every sequence of up to 4 events drawn from the 6 sources plus a Speaker lift, for both values of `address_is_login`: 2 × 7⁴ = 4,802 cases, compared with a model that keeps one row per source. What one row does lose is audit detail: a lower-ranked source's `origin_send_id`, and an earlier episode's timestamps after a re-open. §4.2's `lifted_source` and `lifted_suppressed_at` keep every lift's record, and OQ-5 records the trade-off.

### 3.2 `smartmatch_domain.speaker_channel_consent`

**Opt-in path** (`opt_in_path(current)`). Every move carries `consent_source = 'self_service'`.

| Current state | Moves | Result |
|---|---|---|
| `relationship_recorded` | → `consented` → `active_candidate` | 2 transitions |
| `consented` | → `active_candidate` | 1 transition. It rewrites `consent_source` to `self_service` and `consent_recorded_at` to now (OQ-6). |
| `active_candidate` | none | Lift only, if a suppression stands |
| `discovered`, `corroborated`, `reviewed`, `rejected`, `stale` | — | `409 speaker_contact_channel_opt_in_unavailable` (OQ-1) |

Every move is re-asked through `assert_transition` (`consent.py:191`). The graph (`STATE_TRANSITIONS`, `consent.py:86`) is unchanged.

**Connector conflict** (`connector_transition_conflict(latest_choice, current, requested) -> str | None`):

| Latest Speaker choice | Connector move | Code |
|---|---|---|
| `opt_out` | to `consented` or `active_candidate` | `speaker_contact_channel_speaker_opted_out` |
| `opt_in` | from `active_candidate` to any other state | `speaker_contact_channel_speaker_opted_in` |
| none, or any other move | — | `None`: today's rules apply unchanged |

Invariant (tested): latest choice `opt_in` implies `contact_state = 'active_candidate'`, because the opt-in ends there and the guard blocks every move away from it.

**Evidence and reason** are fixed server text with no address and no id: `"Speaker portal opt-in by the signed-in Speaker"` and `"Speaker opted in through the Speaker portal"`. The actor is on the row already.

## 4. Data

### 4.1 Why the choice needs its own record

- An opt-out writes only `suppression_record`, which has no actor column and one row per address. After an escalation, the row's source is no longer `speaker_portal`.
- `contact_channel_transition` cannot hold an opt-out: `ck_contact_channel_transition_moves` (`schema.py:1846`) forbids `from_state = to_state`, and an opt-out does not move the lifecycle.
- A Connector may record `consent_source = 'self_service'` itself (`ChannelTransitionRequest`, `cba_contact_channels.py:291`), so the source cannot tell a Speaker's opt-in from a Connector's.
- Matching the actor with `speaker_profile.account_user_id` breaks after a T6b-5 unbind.

### 4.2 `contact_channel_speaker_choice` (T6b-1 `0039`, addition B)

```sql
CREATE TABLE contact_channel_speaker_choice (
    id                    uuid        NOT NULL,
    tenant_id             uuid        NOT NULL,
    professional_id       uuid        NOT NULL,
    contact_channel_id    uuid        NOT NULL,
    sequence              integer     NOT NULL,
    choice                text        NOT NULL,
    decided_at            timestamptz NOT NULL,          -- no DEFAULT (T6b-1 R6)
    actor_user_id         uuid        NOT NULL,
    lifted_source         text        NULL,              -- what this opt-in lifted
    lifted_suppressed_at  timestamptz NULL,
    CONSTRAINT contact_channel_speaker_choice_pkey PRIMARY KEY (id),
    CONSTRAINT uq_contact_channel_speaker_choice_sequence
        UNIQUE (tenant_id, contact_channel_id, sequence),
    CONSTRAINT fk_contact_channel_speaker_choice_channel
        FOREIGN KEY (tenant_id, contact_channel_id)
        REFERENCES contact_channel (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_contact_channel_speaker_choice_profile
        FOREIGN KEY (tenant_id, professional_id)
        REFERENCES speaker_profile (tenant_id, professional_id) ON DELETE RESTRICT,
    CONSTRAINT fk_contact_channel_speaker_choice_actor
        FOREIGN KEY (tenant_id, actor_user_id)
        REFERENCES user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_contact_channel_speaker_choice_choice
        CHECK (choice IN ('opt_in', 'opt_out')),
    CONSTRAINT ck_contact_channel_speaker_choice_sequence
        CHECK (sequence >= 1),
    CONSTRAINT ck_contact_channel_speaker_choice_lift
        CHECK ((lifted_source IS NULL) = (lifted_suppressed_at IS NULL)
               AND (choice = 'opt_in' OR lifted_source IS NULL)),
    CONSTRAINT ck_contact_channel_speaker_choice_lift_source
        CHECK (lifted_source IS NULL
               OR lifted_source IN ('speaker_portal', 'unsubscribe_link', 'one_click'))
);
-- Append-only, the 0023 pattern (0023_contact_channel_transition.py:227-246):
-- contact_channel_speaker_choice_reject_mutation() + BEFORE UPDATE trigger
-- contact_channel_speaker_choice_is_append_only.
```

- **`sequence`**, not `decided_at`, orders the log. The writer computes `max(sequence) + 1` while it holds the channel's `FOR UPDATE` lock (§7), and the unique constraint catches any writer that skipped the lock. Two requests' clocks can disagree with their lock order. `schema.py` has no identity-column precedent, so there is none here.
- `uq_contact_channel_speaker_choice_sequence` also serves "latest per channel" (`ORDER BY sequence DESC LIMIT 1`, and `DISTINCT ON` for the batch read).
- `professional_id` must equal `contact_channel.professional_id`. No FK can say so (`contact_channel` has no unique on `(tenant_id, id, professional_id)`), so the service writes it from the locked channel row and a test pins it.
- The log does not depend on the account binding, so the Speaker-wins guard survives a T6b-5 unbind.

## 5. Readers, writers and routes

### 5.1 Every send-eligibility read (the §11 risk-1 inventory)

"Active" means `lifted_at IS NULL`. The one predicate is a correlated `EXISTS`:
`active_suppression_exists(channel) = EXISTS (SELECT 1 FROM suppression_record s WHERE s.tenant_id = channel.tenant_id AND s.address = channel.address AND s.lifted_at IS NULL)`.

**Why `EXISTS` and not the current `LEFT JOIN`.** If `lifted_at IS NULL` went in the `WHERE` of a `LEFT JOIN`, a channel whose only suppression is lifted would drop out of the result: `load_recipient` would answer "no such contact" and the worker would fail `outreach_contact_not_found`. Putting it in the `ON` clause is correct but easy to regress. `EXISTS` has neither failure mode.

**Readers (query changes):**

| # | Reader | Where | Change |
|---|---|---|---|
| R1 | `_selectable()` → `ContactChannelRow.suppressed` | `contacts.py:124-157` | `outerjoin` → `active_suppression_exists`. Feeds `get` `:254`, `list_for_unit` `:270`, `list_for_professional` `:302`, the `apply_transition` read-back `:446`, and the new `list_for_speaker`. |
| R2 | `OutreachRepository.load_recipient` → `RecipientFacts.suppressed` | `outreach.py:217-282` (join `:239-258`) | Same helper. |
| R3 | `OutreachRepository.is_suppressed` | `outreach.py:730-740` | Delegates to `SuppressionRepository.is_active`. |

**Writers:**

| # | Writer | Where | Change |
|---|---|---|---|
| W1 | `OutreachRepository.suppress` | `outreach.py:683-728` | Delegates to `SuppressionRepository.record`: `INSERT … ON CONFLICT ON CONSTRAINT uq_suppression_record_address DO NOTHING RETURNING id`, then `SELECT … FOR UPDATE`, then `merge_suppression`, then one `UPDATE` or none. `was_already_suppressed` = an active row existed before the call, so `test_outreach_persistence.py:677-737` stays green unchanged. |
| W2 | `SuppressionRepository.lift` | new | `lift(session, *, tenant_id, address, allowed_sources, lifted_at, lifted_by_user_id)`: `UPDATE … SET lifted_at = :lifted_at, lifted_by_user_id = :actor WHERE tenant_id = :t AND address = :a AND lifted_at IS NULL AND source IN (:allowed_sources)`. `allowed_sources` is the set the verdict allowed for **this** address: `{speaker_portal}`, or `{speaker_portal, unsubscribe_link, one_click}` on the login address (S6). It is never the fixed liftable list. Asserts that exactly 1 row changed, otherwise it raises and the transaction rolls back. CHECK A backs the widest set. |

**Consumers (unchanged code; each has a §8 contract test):**

| # | Consumer | Where | Reads through |
|---|---|---|---|
| C1 | Worker delivery-time gate | `worker/outreach.py:303` → `assert_send_allowed` `:351` (`_recipient` `:481`) | R2 |
| C2 | Generic compose | `routers/outreach.py:415` → `compose_draft` `:437-446` | R2 |
| C3 | Generic send | `routers/outreach.py:625` → `assert_send_eligible` `:643` | R2 |
| C4 | CBA batch creation | `routers/cba_invitations.py:839` → `choose_invitation_channel` (`cba_invitations.py:326`) → compose `:872` | R1 |
| C5 | CBA dispatch | `routers/cba_invitations.py:1092` → `classify_recipient` `:1105` (`cba_invitations.py:283`) | R2 |
| C6 | Connector channel list (`send_eligible`) | `cba_contact_channels.py:495` → `_view` `:319-345` | R1 |
| C7 | Connector channel register refusal | `cba_contact_channels.py:570` | R3 |
| C8 | Connector channel transition (suppression wins) | `cba_contact_channels.py:393` → `assert_transition(suppressed=)` `:722` | R1 |
| C9 | Generic contacts list, read, update read-back | `outreach_contacts.py:461`, `:358` (`_load_or_404` `:345`), `:704` → `_view` `:319-340` | R1 |
| C10 | T6b-1 portal invite eligibility, and its send | T6b-1 §3.2 step 5 (`ContactChannelRepository.get` + `is_send_eligible`), and C1 plus T6b-1's §6.2 gate | R1, R2 |
| C11 | `GET /v1/me/contact-channels` | new | R1 |

**Writers that call W1 (unchanged code):** unsubscribe `POST` (`routers/outreach.py:861`, `unsubscribe_link`); coordinator suppress (`outreach_contacts.py:694`, `coordinator`). No `bounce`, `complaint` or `one_click` writer exists (no provider webhook), so those rules are structural (CHECK A plus the rank table) and tested with rows inserted directly.

**Not a send-eligibility read:**

- `routers/outreach.py:566` `_address_for` (the address only).
- The `suppressed` fields in `student_speaker_feedback` (k-anonymity withholding, another concept).
- `tests/e2e/test_pilot_clickthrough.py:1839` (a raw `INSERT`; `lifted_at` defaults to `NULL`).
- `api.ts` never recomputes eligibility (`:3978`).

A repo-wide search for `suppression_record`, `suppress`, `is_send_eligible`, `assert_send_eligible`, `assert_send_allowed`, `classify_recipient` and `load_recipient` over `python/`, `services/` and `tools/` found no other reader, no view, and no raw SQL. The source guard (§8) keeps it that way.

### 5.2 Subject resolution — imported from T6b-2

**Orchestrator rulings (2026-09-23).** T6b-3 resolves the subject with T6b-2's authorizer and order (`origin/feat/b26-t6b-2:docs/plans/b26-tracks/T6b-2-plan.md` §2.1, §3.1). It **imports** it: there is no own lookup and no `speaker_subject.py`. That is why T6b-3 stacks on T6b-2.

```text
from smartmatch_api.routers.speaker_self import (
    BoundSpeakerProfile,
    SpeakerPortalRepository,   # for find_bound_profile, as T6b-2 imports it
    _SPEAKER_SELF_ROLES,
    _authorize_speaker_self,
)
```

| Name | Defined by | What it is |
|---|---|---|
| `BoundSpeakerProfile` | T6b-2 §1 | Frozen: `professional_id`, `owning_unit_id`, `owning_unit_path` |
| `SpeakerPortalRepository.find_bound_profile(session, *, tenant_id, account_user_id)` | T6b-2 §1 | `speaker_profile JOIN org_unit`, at most one row (`uq_speaker_profile_account`), no lock |
| `_SPEAKER_SELF_ROLES` | T6b-2 §1 | `frozenset({"speaker"})` |
| `_authorize_speaker_self(session, principal) -> BoundSpeakerProfile` | T6b-2 §3.1 | The two steps below |

**Order (T6b-2 §2.1), every route:**

1. `charge_quota` (commits, ADR-0015), so an unlinked caller pays too.
2. `bound = _authorize_speaker_self(session, principal)`:
   1. `find_bound_profile(tenant_id=principal.tenant_id, account_user_id=principal.user_id)`. None → `404 speaker_profile_not_linked`, **for any role**: `volunteer`, `coordinator`, `admin` and `student` without a bound profile all get this `404`. The lookup reads nothing from the request, so the `404` is no oracle.
   2. `assert_allowed` against the profile's unit (`owning_unit_path`) with `required_roles=_SPEAKER_SELF_ROLES` → `403 forbidden` (`no_grant`, `principal_suspended`, `explicit_resource_deny`) when the profile is bound but no active `speaker` membership covers its unit.
3. Route work, keyed by `bound.professional_id`, never by `principal.user_id` (they differ for a T6b-5 merged login).

`routers/me_contact_channels.py` calls `_authorize_speaker_self` by name (`test_the_route_calls_the_authorizer_the_matrix_names`). Its matrix rows set `authorizer_module="smartmatch_api.routers.speaker_self"` (§9).

**T6b-3's two added methods** on T6b-1's `SpeakerPortalRepository` (`smartmatch_persistence/speaker_portal.py`). Neither finds the subject; both take `bound` from the shared authorizer:

- `lock_bound_profile_share(session, *, tenant_id, professional_id, account_user_id) -> bool`: `SELECT 1 FROM speaker_profile WHERE tenant_id = :t AND professional_id = :p AND account_user_id = :u FOR SHARE`. Only the two write routes call it, right after `_authorize_speaker_self`. `False` means an unbind committed in between → `404 speaker_profile_not_linked` (§7 race 8). It is a lock and re-check. `find_bound_profile` stays lock-free, as T6b-2 wrote it.
- `login_address(session, *, tenant_id, account_user_id) -> str`: the bound login's `user_account.email`, for the OQ-3 `address_is_login` test (§3.1). Only opt-in calls it.

No path or body field names the subject (parent §2, MM-A01).

### 5.3 Routes (`/v1/me/contact-channels`, role `{speaker}`, `SPEAKER_PORTAL` only)

Quota is charged first; `charge_quota` commits (`dependencies.py:286-312`, ADR-0015). Rate limits: `RateLimit("me.contact_channels.read", 60, 1 min)` and `RateLimit("me.contact_channels.write", 10, 1 min)`, per principal. Auth is a bearer session, not a cookie, so there is no CSRF surface.

| Route | Request | Success | Errors |
|---|---|---|---|
| `GET /v1/me/contact-channels` | — | `200 { channels: [View], truncated }`: every channel in the tenant with `professional_id = bound.professional_id`, across units (OQ-7), ordered by `address, id`, capped at 50 by reading 51. | `429`; `404 speaker_profile_not_linked`; `403` (in that order, §5.2) |
| `POST /v1/me/contact-channels/{channel_id}/opt-in` | no body | `200 { channel: View, changed: bool }` | `429`; `404 speaker_profile_not_linked`; `403`; `404 speaker_contact_channel_not_found` (unknown, another Speaker's, another tenant: one code); `409 speaker_contact_channel_suppression_not_liftable` with `details.reason` of `connector` or `delivery`; `409 speaker_contact_channel_address_unverified` (an `unsubscribe_link` or `one_click` suppression on a channel that is not the login address; message: "This address was unsubscribed and is not the one you sign in with. Ask your Speaker Connector."); `409 speaker_contact_channel_opt_in_unavailable` with `details.contact_state`; `409 speaker_contact_channel_transition_conflict` (defence in depth, unreachable under the lock) |
| `POST /v1/me/contact-channels/{channel_id}/opt-out` | no body | `200 { channel: View, changed: bool }` | `429`; `404 speaker_profile_not_linked`; `403`; `404 speaker_contact_channel_not_found` |

`View`: `contact_channel_id`, `channel_kind`, `address`, `contact_state`, `send_eligible` (`is_send_eligible`, `consent.py:261`), `suppressed`, `suppression_reason` (`null`, `your_opt_out`, `unsubscribed`, `connector` or `delivery`), `speaker_choice` (`null`, `opt_in` or `opt_out`), `last_set_by` (`speaker` or `connector`), `can_opt_in`, `can_opt_out`, `updated_at`.

- `last_set_by = "speaker"` when a choice exists and its `decided_at >= max(contact_channel_transition.occurred_at)` for the channel. Otherwise `"connector"`. The Speaker's own opt-in moves share the choice's `now`, so they tie in the Speaker's favour.
- `can_opt_in` = the lift verdict (with `address_is_login`) is not `REFUSED`, the state is in `OPT_IN_START_STATES`, and the opt-in would change something.
- `can_opt_out` = not (latest choice is `opt_out` and the channel is suppressed).
- **Never returned:** `consent_evidence`, `consent_source`, any actor id, any unit id, `origin_send_id`. A key-set test pins this (parent §2 privacy).

**Idempotency.** When nothing would change, the response is `changed: false` and no row is written:

- Opt-in: already `active_candidate`, not suppressed, latest choice `opt_in`.
- Opt-out: latest choice `opt_out` and the merge is `NOOP`.

### 5.4 Connector surfaces (the Speaker-wins guard)

| # | Surface | Where | Change |
|---|---|---|---|
| G1 | CBA channel transition | `cba_contact_channels.py:662` | `_load_channel_or_404` first calls `contacts.lock(...)` in its own statement, then re-reads through `get()` (S5), so the suppression flag and state are read after the lock. Then `latest_for_channel`, then `connector_transition_conflict`, so a hit is a `409` with the §3.2 code. It runs **before** `_require_evidence` (`:711`) and `assert_transition` (`:718-736`), so the Speaker-specific code wins over the generic `speaker_contact_channel_transition_refused`. `occurred_at` is read after the lock. |
| G2 | Generic contact transition | `outreach_contacts.py:727` | Today's order is `_load_or_404` (`:757`) → `can_transition` (`:766`, `409 outreach_contact_transition_illegal`) → `_require_approved_consent` (`:779`) → `assert_transition` without `suppressed=` (`:788`), whose `except` maps **every** `ConsentViolationError` to `403 outreach_consent_source_not_approved`. New order (S1): (1) `contacts.lock` then `_load_or_404` re-read; (2) the Speaker-wins guard, `409 speaker_contact_channel_speaker_opted_out` / `…_opted_in`; (3) **new** check `row.suppressed and is_escalation(body.to_state)` → **`409 outreach_contact_suppressed`** (new code), "That address is suppressed: somebody at it has told us to stop."; (4) `can_transition`; (5) `_require_approved_consent`; (6) `assert_transition(..., suppressed=row.suppressed)` as defence in depth, its existing `403` mapping unchanged because step 3 already answered every suppressed escalation. **Shipped-behaviour change (OQ-4):** today a Connector can move a suppressed contact to `consented` (from `relationship_recorded`) or `active_candidate` (from `consented`) on this route and gets `201`; after milestone 3 both are `409 outreach_contact_suppressed`, and the suppressed code wins over a missing-evidence `400`. Moves to `stale` and `rejected` still succeed. The commit body and PR body list this change. |
| G3 | Contact PATCH: coordinator suppress **and** evidence correction | `outreach_contacts.py:621` (`update_evidence` `:685` → `contacts.py:338`; suppress `:694`) | After `_load_or_404` (`:651`) and the empty-request and un-suppress `400`s: `contacts.lock`, re-read, `latest_for_channel`. If the latest choice is `opt_in` and the request carries `suppressed: true` **or** `consent_evidence` → `409 speaker_contact_channel_speaker_opted_in` (OQ-2 ruling; orchestrator ruling S4 for evidence, because rewriting the evidence behind a Speaker's own consent is overriding it), nothing written. Otherwise both writes as today, W1 for the suppress. |
| V | Connector channel views | `cba_contact_channels.py:319`, `outreach_contacts.py:319` | Additive `speaker_choice` and `speaker_choice_at`, so a Connector sees why a 409 happened. The list reads all latest choices in one query. |

The guard sits in both transition routes because both move the same `contact_channel` rows. A guard on one route alone would leave the other as a way around it. A source test pins the set of `apply_transition(` call sites to G1, G2 and `speaker_channel_consent.opt_in`.

## 6. Transactions

**`now` is read once, after the channel lock and the suppression row lock are both held** (S2): `now = max(utc_now(), row.suppressed_at)` when a row exists, else `utc_now()`. That keeps `decided_at` and `occurred_at` in lock order, and keeps `lifted_at >= suppressed_at` (`ck_suppression_record_lifted`, T6b-1 §2) true even if an unsubscribe re-opened the row between the request's start and the lock (§7 race 10), or another API process's clock runs ahead. This differs deliberately from T6b-1 R6's "top of request", which has no lock to wait on.

**Opt-in** (`speaker_channel_consent.opt_in`), one transaction:

1. `charge_quota` (commits).
2. `bound = _authorize_speaker_self(session, principal)` (§5.2), then `lock_bound_profile_share(...)`: the profile row `FOR SHARE`; `False` → `404 speaker_profile_not_linked`.
3. `contacts.lock(channel_id)` (its own `FOR UPDATE` statement, S5), then `contacts.get(channel_id)`. If it is missing, or `professional_id` is not `bound.professional_id` → `404 speaker_contact_channel_not_found`.
4. `suppressions.lock_for_address(address)` (`FOR UPDATE`, may be none).
5. `now` as above (S2). Then `speaker_lift_verdict(address_is_login=…)`. `REFUSED("unverified_address")` → `409 speaker_contact_channel_address_unverified`; any other `REFUSED` → `409 …suppression_not_liftable`. Nothing is written. Suppression is checked before legality, the order `assert_transition` uses (`consent.py:217-219`).
6. `opt_in_path(current)`. Not allowed → `409 …opt_in_unavailable`.
7. Idempotent case → `200 changed: false`.
8. `LIFT` → `suppressions.lift(allowed_sources=<the verdict's set>, lifted_at=now, lifted_by_user_id=principal.user_id)`.
9. For each move: `assert_transition(prev, next, consent_source=SELF_SERVICE, suppressed=<after the lift>)`, then `apply_transition(expected_state=prev, to_state=next, consent_source="self_service", consent_evidence=SELF_SERVICE_EVIDENCE, reason=SELF_SERVICE_REASON, actor_user_id=principal.user_id, occurred_at=now)`. `None` → `409 …transition_conflict`.
10. `choices.append(choice="opt_in", sequence=max+1, decided_at=now, actor_user_id=principal.user_id, professional_id=channel.professional_id, lifted_source/lifted_suppressed_at when step 8 ran)`.
11. `commit`. Read back through R1 and build the view.

**Opt-out**, one transaction: steps 1–5 (without the verdict), then:

1. `suppressions.record(source="speaker_portal", at=now)` (W1's merge).
2. Idempotent case → `changed: false`. Otherwise `choices.append(choice="opt_out", …)`.
3. `commit`.

`contact_state` is not touched, so a later opt-in restores sending without research moves. Pausing invitations (T6b-2) stays separate from opting out (parent §2).

## 7. Lock order and races

**Global order:** `speaker_profile` → `contact_channel` → `suppression_record` → inserts (`contact_channel_transition`, `contact_channel_speaker_choice`). Every path takes a subsequence of it:

| Path | Locks, in order |
|---|---|
| Speaker opt-in / opt-out | profile `FOR SHARE` → channel `FOR UPDATE` → suppression row `FOR UPDATE` |
| T6b-1 invite | profile `FOR UPDATE` → invitation (reads the channel without a lock) |
| T6b-1 activation | profile → invitation → address advisory lock |
| G1, G2 Connector transition | channel `FOR UPDATE` (reads suppression and the choice log without a lock) |
| G3 contact PATCH | channel `FOR UPDATE` → suppression row (upsert, suppress only) |
| Unsubscribe `POST` | suppression row only (upsert) |
| Worker send, dispatch, compose | none (reads) |

No path takes a suppression row and then a channel, or a channel and then a profile, so no wait cycle exists.

| # | Race | Outcome |
|---|---|---|
| 1 | **Opt-out ∥ Connector → `consented`/`active_candidate`** | Both take the channel lock first. Opt-out first: the Connector re-reads after the lock, sees latest `opt_out`, and gets `409 …speaker_opted_out`. Connector first: the move commits, then the opt-out suppresses. Either way the address is not sendable after both commit, and the Speaker's later action stands. |
| 2 | Opt-in ∥ Connector → `stale` | Opt-in first: `409 …speaker_opted_in`. Connector first: the channel is `stale`, so the opt-in gets `409 …opt_in_unavailable` (OQ-1). |
| 3 | Opt-out ∥ opt-in (two tabs) | Serialized by the channel lock. The last one wins; both are in the log with consecutive `sequence`. |
| 4 | Opt-in ∥ coordinator suppress, or a directly written bounce/complaint | The suppression row lock serializes them. Suppress first: escalated to rank ≥ 2, so the opt-in gets `409 …not_liftable`. Opt-in first: lifted, then the upsert re-opens with the new source. Suppressed either way. |
| 5 | Opt-in ∥ an old unsubscribe link | Row lock. Unsubscribe after the lift re-opens (`unsubscribe_link`), which is the person's newer instruction. |
| 6 | Opt-out ∥ a worker send already past its delivery-time re-check (`worker/outreach.py:303-351`) | **Residual, documented.** That one message may still go. ADR-0014 rule 2: prospective. Every re-check that starts after the opt-out commits refuses. It is the same window an unsubscribe has today. No lock is held across the provider call. |
| 7 | Opt-out ∥ T6b-1 invite of the same channel | Profile lock (`FOR SHARE` against `FOR UPDATE`). Invite first: its job is refused at the worker re-check. |
| 8 | Opt-in ∥ T6b-5 unbind | Unbind commits before the share lock: `lock_bound_profile_share` re-checks `account_user_id` and returns `False` → `404 speaker_profile_not_linked`. After the share lock: the unbind's update waits until the opt-in commits. |
| 9 | Two first suppressions for one address | `ON CONFLICT DO NOTHING`, then `FOR UPDATE` on the surviving row, then the merge. |
| 10 | Opt-in whose request started before an unsubscribe re-opened the row (S2) | The unsubscribe commits a new `suppressed_at` while the opt-in waits on the channel or suppression lock. The opt-in reads `now` only after `lock_for_address`, and takes `max(utc_now(), suppressed_at)`, so the lift satisfies `ck_suppression_record_lifted` instead of failing with a `500`. The lift then applies to the re-opened `unsubscribe_link` row under the OQ-3 rule. |

## 8. A contract test per send path, and the reader guard

**Fixture:** `_seed_suppression_state(session, state, …)`, defined in `test_suppression_lift_send_paths.py` and copied verbatim into `test_outreach_handler.py` (the repo has no shared test-helper package), puts an `active_candidate`, `self_service`-consented channel into one of 4 states by direct SQL, so each test is red against today's readers once `0039` is applied:

| State | Rows | Expected `send_eligible` |
|---|---|---|
| `NONE` | no row | yes |
| `ACTIVE` | active `unsubscribe_link` row | no |
| `LIFTED` | that row lifted by the Speaker | **yes** |
| `REOPENED` | lifted, then re-suppressed through W1 | **no** |

| Path | Test (param over the 4 states) | Asserts |
|---|---|---|
| C1 worker | `tests/integration/test_outreach_handler.py::TestLiftedSuppression::test_delivery_recheck_honours_lifted_at` | `FixtureEmailProvider.sent` has 1 / 0 / 1 / 0 entries. Refusals are `BLOCKED` with a reason naming suppression. |
| C1 + opt-out | `…::test_opt_out_committed_before_the_recheck_blocks_the_send` | Job queued, opt-out committed, handler run: nothing sent. |
| C2 compose | `tests/contract/test_suppression_lift_send_paths.py::test_generic_compose` | `201` / today's refusal (as `test_outreach.py:328`) / `201` / refusal |
| C3 send | `…::test_generic_send` | `202` / refusal / `202` / refusal |
| C4 batch creation | `…::test_cba_batch_creation` | composed / skipped `suppressed` / composed / skipped |
| C5 dispatch | `…::test_cba_dispatch` | dispatched / not dispatched `suppressed` / dispatched / not dispatched |
| C6, C9 views | `…::test_connector_views_report_the_live_suppression` | `suppressed` and `send_eligible` on both list routes and the read route |
| C7 register | `…::test_register_refuses_only_an_active_suppression` | An address with a row but no channel: `201` for `LIFTED`, `409 speaker_contact_channel_suppressed` for `ACTIVE` and `REOPENED` |
| C8 transition | `…::test_escalation_is_refused_only_under_an_active_suppression` | `stale` → … → `consented`: `201` / `409` / `201` / `409` |
| C10 portal invite | `…::test_portal_invite_eligibility` (T6b-1's capability-on app stub) | `202` / `422 speaker_portal_channel_not_eligible` / `202` / `422` |
| C11 Speaker view | `tests/contract/test_me_contact_channels_api.py::test_view_reports_the_live_suppression` | `send_eligible` and `suppression_reason` |

`test_every_send_path_has_a_lifted_at_test` checks the `SEND_PATHS` registry in `test_suppression_lift_send_paths.py` against the §5.1 consumer table (C1–C11).

**Reader guard** — `tests/unit/test_suppression_single_reader.py` (AST over `python/`, `services/`, `tools/`; not tests or migrations):

1. `test_only_the_suppression_module_touches_the_table`: `schema.suppression_record` attribute access, or a non-docstring string literal holding `suppression_record` together with an **upper-case** SQL keyword (`SELECT`, `FROM`, `JOIN`, `INSERT`, `UPDATE`, `DELETE`; case-sensitive match), appears only in `persistence/suppression.py` and `persistence/schema.py`. Docstrings (the first expression statement of a module, class or function) are skipped, and keywords match case-sensitively, so prose such as `cba_contact_channels.py:191` ("a join against ``suppression_record``") and `outreach.py:16` ("computed from ``suppression_record``") does not trip it (S7). A failure names the file and line.
2. `test_lifted_at_is_written_only_by_the_suppression_module` (the §1.1 invariant).
3. `test_every_eligibility_consumer_is_known`: every call of `load_recipient`, `ContactChannelRepository.get`, `list_for_unit`, `list_for_professional`, `list_for_speaker`, `is_suppressed` and `is_active` is in `KNOWN_ELIGIBILITY_CONSUMERS` (file, function). A new caller fails until it is listed **and** has a `SEND_PATHS` entry.
4. `test_apply_transition_call_sites_are_guarded` (§5.4).

## 9. TDD list

Run one file at a time (env rule 3). DB tests use the private database `smartmatch_b26_t6b3` and drop it afterwards. Build token-shaped literals at runtime.

| File | Level | Tests |
|---|---|---|
| `tests/unit/test_suppression_rules.py` | unit | `test_source_vocabulary_matches_the_check` (schema CHECK text and CHECK A); `test_liftable_sources_are_a_rank_prefix_for_both_address_kinds`; `test_merge` (param: none / lifted / active × 6 incoming); `test_speaker_lift_verdict` (param: 6 sources × none / active / lifted × `address_is_login` true / false); `test_unsubscribe_sources_lift_only_on_the_login_address`; `test_single_row_merge_matches_the_per_source_model` (4,802 sequences); `test_speaker_opt_out_over_an_unsubscribe_elsewhere_does_not_hide_it` (regression for the rank order); `test_speaker_facing_reason_covers_every_source` |
| `tests/unit/test_speaker_channel_consent.py` | unit | `test_opt_in_path` (param: 8 states); `test_every_opt_in_move_is_a_legal_edge` (against `STATE_TRANSITIONS`); `test_connector_conflict` (param: 3 latest × every legal move); `test_evidence_and_reason_carry_no_address_or_id` |
| `tests/unit/test_suppression_single_reader.py` | unit | The 4 guards in §8 |
| `tests/integration/test_suppression_persistence.py` | integration | `record` insert / no-op / escalate / re-open; `was_already_suppressed`; `lift` sets both columns; `test_lift_only_touches_the_allowed_sources` (S6: `allowed_sources={speaker_portal}` against an `unsubscribe_link` row changes 0 rows and raises); `test_lift_at_suppressed_at_satisfies_the_check` (S2 boundary); `test_a_raw_lift_of_bounce_complaint_or_coordinator_is_refused_by_the_check` (CHECK A); `test_active_suppression_exists_ignores_a_lifted_row`; `test_lift_in_one_tenant_leaves_another_suppressed` |
| `tests/integration/test_outreach_persistence.py` | integration | `:677-737` unchanged and green. Add `test_load_recipient_reports_a_lifted_suppression_as_clear` and `test_a_reopened_suppression_is_reported_again`. |
| `tests/integration/test_contact_lifecycle.py` | integration | `test_contact_row_suppressed_flag_honours_lifted_at` (get, both lists, `list_for_speaker`) |
| `tests/integration/test_speaker_channel_choice.py` | integration | `test_sequence_is_dense_per_channel`, `test_duplicate_sequence_is_refused`, `test_update_is_refused_by_the_trigger`, `test_latest_and_batch_latest`, `test_professional_matches_the_channel` |
| `tests/integration/test_speaker_channel_consent_races.py` | integration | Two sessions with barriers, the T6b-1 `test_speaker_portal_activation.py` pattern: races 1, 2, 3, 4, 7, 9 and 10 of §7, each asserting the outcome column and no `DeadlockDetected` within a 10 s timeout |
| `tests/integration/test_outreach_handler.py` | integration | `TestLiftedSuppression` (§8) |
| `tests/contract/test_suppression_lift_send_paths.py` | contract (DB) | §8, C2–C10 |
| `tests/contract/test_me_contact_channels_api.py` | contract (DB, capability-on stub) | See the list below. |
| `tests/contract/test_contact_lifecycle_api.py` | contract (DB) | G1: `test_opted_out_channel_refuses_consented_and_active_candidate` (`409 …speaker_opted_out`, before the evidence `400`); `test_opted_in_channel_refuses_stale` (`409 …speaker_opted_in`); `test_after_opt_out_a_connector_may_mark_stale`; `test_no_choice_leaves_today_behaviour` (existing `:656-729` green); `test_view_carries_speaker_choice` |
| `tests/contract/test_outreach_contacts.py` | contract (DB) | G2: the same 2 codes. G3: `test_coordinator_suppress_on_an_opted_in_channel_is_409`. OQ-4 (S1): `test_generic_transition_refuses_escalating_a_suppressed_contact` (param: `relationship_recorded`→`consented` with evidence, `consented`→`active_candidate` → `409 outreach_contact_suppressed`, no transition row, state unchanged); `test_suppressed_code_wins_over_missing_evidence` (to `consented` with no evidence → `409 outreach_contact_suppressed`, not `400`); `test_speaker_wins_code_wins_over_suppressed_code` (opted-out channel → `409 …speaker_opted_out`); `test_generic_transition_still_allows_stale_and_rejected_when_suppressed`; `test_unsuppressed_illegal_edge_is_still_409_illegal` (today's `outreach_contact_transition_illegal` unchanged). G3 (S4): `test_coordinator_suppress_on_an_opted_in_channel_writes_nothing`; `test_evidence_patch_on_an_opted_in_channel_is_409` (evidence unchanged); `test_evidence_patch_after_opt_out_or_with_no_choice_succeeds`. `:443-467` stay green. |
| `tests/authz/test_route_roles.py` | authz | 3 literal rows with T6b-2's `_SPEAKER_SELF_ROLES` constant (one constant for all 8 `/v1/me` Speaker routes); `test_speaker_self_roles_match_the_live_constant` |
| `tests/authz/test_policy_matrix.py` | authz | 3 `Operation`s (`me.contact_channels.read`, `.opt_in`, `.opt_out`) with T6b-2's shared fields: `module="smartmatch_api.routers.me_contact_channels"`, `authorizer="_authorize_speaker_self"`, `authorizer_module="smartmatch_api.routers.speaker_self"`, `roles_constant="_SPEAKER_SELF_ROLES"`, `required_roles=frozenset({"speaker"})`, `resource_type="org_unit"`, `unit_scoped=True`. `speaker_at_owning_unit` → permit, every other shape → `deny("no_grant")`. T6b-1's `test_a_speaker_membership_reaches_no_operation` becomes `…_reaches_only_speaker_self_operations` against `SPEAKER_SELF_OPERATIONS`, which T6b-2 extends. |
| `tests/unit/test_speaker_portal_composition.py` (T6b-1's) | unit | The unmounted-path list gains the 3 paths; the OpenAPI document has none of them. |

`tests/contract/test_me_contact_channels_api.py`:

1. **Scope:** `test_lists_only_own_channels_across_units` (another Speaker's channel and another professional's channel are absent; the same professional's channel in a second unit is present). `test_response_never_carries_evidence_actor_or_unit` (key set).
2. **Opt-out:** `test_opt_out_writes_speaker_portal_suppression_and_choice`; `test_opt_out_is_immediate` (the next `GET` and C3 both refuse); `test_opt_out_is_idempotent` (`changed: false`, no second row); `test_opt_out_over_a_bounce_keeps_bounce_and_logs_the_choice`.
3. **Opt-in:** `test_opt_in_from` (param: `relationship_recorded` → 2 transitions, `consented` → 1, `active_candidate` → 0), each with `consent_source='self_service'`, actor = the Speaker's login and the fixed evidence. `test_opt_in_lifts_on_the_login_address` (param: `speaker_portal`, `unsubscribe_link`, `one_click`; asserts `lifted_by_user_id` and the choice's `lifted_source`). `test_opt_in_lifts_speaker_portal_on_another_address`. `test_opt_in_refuses_unsubscribe_on_another_address` (param: `unsubscribe_link`, `one_click` → `409 speaker_contact_channel_address_unverified`, message names the Connector, nothing written). `test_login_address_match_ignores_case_and_surrounding_space`. `test_view_can_opt_in_is_false_for_an_unverified_unsubscribe`. `test_opt_in_refuses_non_liftable` (param: `bounce` and `complaint` → `delivery`, `coordinator` → `connector`; nothing written: suppression, transitions and choices unchanged). `test_opt_in_unavailable` (param: 5 states). `test_opt_in_is_idempotent`.
4. **Refusals:** `test_not_mine_is_404` (param: another Speaker's, unknown, another tenant: identical bytes). `test_unlinked_caller_is_404_on_every_route` (T6b-2's shape; param: 3 routes × `volunteer`, `coordinator`, `admin`, `student` with no bound profile → `404 speaker_profile_not_linked`). `test_bound_without_active_speaker_membership_is_403` (param: `speaker` membership past `valid_until`, suspended account → `403 forbidden`). `test_unbind_between_authorize_and_share_lock_is_404`. `test_quota_is_charged_before_the_404`. `test_write_rate_limit_is_429_after_10`.
5. **Gate:** `test_capability_off_mounts_nothing`.

## 10. Commit milestones (red → green, one commit each)

Each milestone: tests first, run red locally (the red run is noted in the commit body), then code to green. Before each commit: `$VENV/bin/ruff format` + `ruff check` on touched files, and the milestone's test files one at a time. Every commit ends with the `Co-Authored-By` trailer.

**Start gate (S3, plus the T6b-2 stack).** All three must hit on `origin/feat/b26-t6b-2` before milestone 0. None is pushed yet (2026-09-23): A and B were sent to the T6b-1 implementer, and T6b-2 is plan-only (`f30f85e9`).

1. `git grep -n lift_source origin/feat/b26-t6b-2 -- db/migrations/versions/0039_speaker_portal.py`
2. `git grep -n contact_channel_speaker_choice origin/feat/b26-t6b-2 -- db/migrations/versions/0039_speaker_portal.py`
3. `git grep -n "def _authorize_speaker_self" origin/feat/b26-t6b-2 -- services/api/smartmatch_api/routers/speaker_self.py`

Until all three hit, do not merge and do not start milestone 1; report to the orchestrator.

0. `chore: merge feat/b26-t6b-2 into feat/b26-t6b-3`. `git merge origin/feat/b26-t6b-2`, which brings T8a, T6b-1, T2, T1 and T3. Resolve nothing by hand in T6b-2's files. Then run T6b-2's `tests/contract/test_speaker_self_api.py` once to prove the imported authorizer is green on this branch.

**Contingency C, not planned work — only if `0039` merges without §1.2 A and B:** `feat: speaker channel choice table and lift-source check` (migration at head plus one, mirror, CHECK-key table, conftest, head pins).
1. `feat: suppression and speaker channel consent rules in the domain`. §3, with `test_suppression_rules.py` and `test_speaker_channel_consent.py`.
2. `feat: one suppression module and lifted_at in every eligibility read`. **The risk-1 commit, atomic:** `persistence/suppression.py`, R1–R3, W1, W2, the reader guard, the persistence tests and every §8 send-path test (red with seeded `LIFTED` rows, then green).
3. `feat: speaker channel choice log and the Speaker-wins guard on connector transitions`. The choice repository, `contacts.lock`, G1–G3 (with the evidence guard), the OQ-4 fix (shipped-behaviour change, named in the commit body and PR body), the Connector view fields, `make openapi`, the `api.ts` type, and the lifecycle and outreach-contacts contract tests.
4. `feat: /v1/me/contact-channels with self-service opt-in and opt-out`. `_authorize_speaker_self` and friends imported from `smartmatch_api.routers.speaker_self` (§5.2), `lock_bound_profile_share`, `login_address`, the service, the router, the capability row, rate limits, the authz ledgers, the Speaker contract tests and the race tests.
5. `docs: T6b-3 notes on OQ-009, OQ-CBA-035 and the parent's lifted_at sentence`.

## 11. Owner rulings (2026-09-23)

All seven questions are ruled. None is open.

| # | Question | Ruling | Where it lands |
|---|---|---|---|
| OQ-1 | Opt-in from `discovered`, `corroborated`, `reviewed`, `rejected` or `stale` (no edge to `consented`) | **Refuse** with `409 speaker_contact_channel_opt_in_unavailable`. No state-graph change. Known cost: opt-out → Connector marks `stale` → the Speaker's opt-in is refused; the UI says "ask your Speaker Connector". | §3.2, §7 race 2, `test_opt_in_unavailable` |
| OQ-2 | Connector suppress on a Speaker-opted-in channel | **Refuse** with `409 speaker_contact_channel_speaker_opted_in`. Extended by the orchestrator (S4) to a Connector evidence correction on the same channel. | §5.4 G3, `test_coordinator_suppress_on_an_opted_in_channel_*` |
| OQ-3 | Which addresses an opt-in may lift an `unsubscribe_link` or `one_click` suppression on | **Only the Speaker's login address** (proven by the invitation; the bound account's email, read by `login_address`). On any other channel an opt-in lifts only `speaker_portal` suppressions; an unsubscribe there → `409 speaker_contact_channel_address_unverified`, "ask your Speaker Connector". | §3.1, §5.2, §5.3, §6 step 5, the OQ-3 tests in §9 |
| OQ-4 | `outreach_contacts.py:788` ignores suppression | **Fix in milestone 3** with a contract test. Shipped-behaviour change: escalating a suppressed contact on the generic route becomes `409 outreach_contact_suppressed` (new code, S1), checked after the Speaker-wins guard and before `can_transition` and `_require_approved_consent`. | §5.4 G2, §9, §10 milestone 3 |
| OQ-5 | One row per address loses some audit detail | **Accept.** No lift decision is lost (§3.1), and the choice log records every lift's source and time. The coordinator actor gap stays under OQ-009. | §3.1, §4.2 |
| OQ-6 | Opt-in from `consented` rewrites `consent_source` to `self_service` with a new date | **Yes.** The old consent stays in the trail. | §3.2 |
| OQ-7 | Channel scope for the Speaker | **Tenant-wide by `professional_id`**, across units. | §5.3 |

## 12. Risks

| Risk | Mitigation | Residual |
|---|---|---|
| **A send path ignores `lifted_at`** (parent §11 risk 1) | One predicate (`active_suppression_exists`); the 4-state contract test per path (C1–C11); the AST guard against a second reader; the known-consumer list; the delivery-time re-check stays. | A new raw-SQL reader added in a string the AST heuristic misses. The known-consumer list and review catch it. |
| A lift touches a delivery fact | CHECK A in the database; the rank rule; `speaker_lift_verdict`; the exhaustive model test. | — |
| A Connector bypasses the Speaker through the generic route | Guard on G1 and G2; `apply_transition` call-site pin. | — |
| Deadlock between Speaker, Connector and unsubscribe writers | One global lock order (§7); race tests assert no `DeadlockDetected`. | — |
| In-flight send after an opt-out | ADR-0014 rule 2 (prospective); test that every later re-check refuses. | One message already past its re-check (§7 race 6). |
| `0039` merges without §1.2 | Contingency C (§10). | The migration lands at head plus one on the T6b-2-based branch. |
| T6b-2 is late or changes `_authorize_speaker_self` | Start gate item 3; milestone 0 runs T6b-2's contract tests; the matrix names the imported authorizer, so a rename fails `test_policy_matrix.py`. | T6b-3 waits on T6b-2. |

## 13. Out of scope

1. The Contact preferences page and adapters (T6b-4), and the parent §7 row 13 e2e click-through.
2. A bounce, complaint or one-click writer (no provider webhook exists). The rules for them are structural and tested with direct rows.
3. Connector un-suppress and the coordinator actor column (OQ-009).
4. T6b-5's unbind semantics beyond §7 race 8. Choices persist after an unbind by design (§4.2).
5. Retention of choice rows (D5).

**Next action (under two minutes):** run the three §10 start-gate greps against `origin/feat/b26-t6b-2`; all must hit before milestone 0.
