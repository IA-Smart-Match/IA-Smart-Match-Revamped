# B26 T8d — load band on Connector run views, the Connector availability panel and the Speaker's Availability page; engagements without an end time made visible

**Next action:** once T8c milestone 7 and T6b-4 milestone 8 are pushed, run milestone 0 (§10): merge
`origin/feat/b26-t8c`, then `origin/feat/b26-t6b-4`, into `feat/b26-t8d`.

**Revision 2, 2026-09-23.** Docs only: no source file, route or test is written by this document.

**Plan gate: APPROVE (orchestrator, 2026-09-23).** OQ-1…OQ-3 accepted as recommended; OQ-4 and OQ-5 become
follow-up cards. Findings MED 1–5 and the LOW batch applied (§14).

Parent: `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §2 (goal: the Speaker sees their
current load band), §4.1 ("after T8 it also carries `load`"), §5.2, §6 (T4/T8d row: a band word, never a
number, OQ-CBA-005), §8 T8d row, §11 risks 3 and 4.
Inputs (all final): T8c plan `origin/feat/b26-t8c` @ `0a6b458e`; T8b plan and code `origin/feat/b26-t8b`
@ `55624cdd`; T4 plan `origin/feat/b26-t4` @ `2208de84`; T6b-4 plan `origin/feat/b26-t6b-4` @ `86a8b65f`;
T6b-2 plan `origin/feat/b26-t6b-2` @ `f30f85e9`; T3 plan and code `origin/feat/b26-t3` @ `f086be2b`;
T5 plan `origin/feat/b26-t5` @ `f0c060e5`; T8a plan `origin/feat/b26-t8a` @ `09ca1455`.
Line numbers are `main` @ `1909278f` unless a branch is named. Frontend paths are relative to
`apps/web/legacy-frontend/`.

## 0. Decisions in one table

| # | Question | Decision |
|---|---|---|
| D1 | Where does the **current** band come from, for the Speaker and for the Connector? | A new `load` field on the shared `SpeakerAvailabilityResponse` (T3's model, reused by T6b-2's `/v1/me/availability`). Computed **at request time** on `GET` and `PATCH`, with T8c's `EngagementLoadRepository` and `assess_pool_loads` and T8b's `compute_eli`: the same code a 3.x run uses. Not from a run explanation: a Speaker has no run, and a run's band is a snapshot. |
| D2 | Registry `3.0.0` is proposed, not current. Is the current band computed anyway? | **Yes, independent of the flip.** Band table = the current registry's `load_bands` when it has one, else T8c's `Q7_REGISTERED_LOAD_BANDS` (the same Q7 table 3.0.0 declares). The response says whether matching uses it: `used_in_matching = current_cba_registry().load_bands is not None` (false today). **Flagged for the orchestrator** (OQ-1). |
| D3 | What does the wire carry? | Availability routes: **band word inputs only**: `band`, `reason`, `as_of`, `used_in_matching`, and the engagements without an end time. No hours, no utilization, no capacity echo in `load`. Run read: T8c's stored block (numbers kept for audit); the `api.ts` type declares only `band` and `reason`, so no page can render a number without editing the type (source scan F1). |
| D4 | How do Connectors see which engagements lack an end time (parent §11 risk 4)? | In the Connector availability panel (T5), from `load.engagements_without_end_time`: event title and date for events hosted by this unit, with a link to the Events page when the event is a Connector-entered one; "An engagement another unit recorded" otherwise (unit privacy). The run card says the gap exists and points to that panel. The run read gains **no** query (T4 test 17 pins its count). |
| D5 | Run views on 2.0.0 runs (every production run today)? | `MatchRunResponse.load_recorded` (from the run's own pin, like T4's `availability_recorded`). False → one header row "Workload: Not part of this run's matching" and nothing on the cards. True → a band word on every card, compose row and `load_full` exclusion. |

## 1. Branch, stack and start gate

**Stack.** T8d consumes T8c (backend load read, registry lineage, explanation `load`, `load_full`) and T6b-4
(the Speaker page and its `SLOT(T8d)`). T8c sits on T4 → T8a → T6b-1 → T2 → T1, plus T8b. T6b-4 sits on
T6b-2 (→ T8a → T6b-1 → T2 → T1, plus T3), T6b-3 and T5. Both chains share T8a → T6b-1 → T2 → T1.

On `feat/b26-t8d` (this plan commit, from `origin/main`), merge, not rebase, so the pushed plan commit stays
(the T5 / T6b-2 / T6b-4 pattern):

1. `git merge origin/feat/b26-t8c` (backend first).
2. `git merge origin/feat/b26-t6b-4`. Expected textual conflicts, all resolved as a union:
   - the parent plan (T4 §3.5 and §8 row, T8b line edits, T8c §5.2 re-wording vs T6b-x rows);
   - `src/lib/api.ts` (T4's match-run and batch types vs T6b-2 / T6b-3 / T6b-4 adapters: different regions);
   - `services/api/smartmatch_api/routers/cba_invitations.py` (T4 `_compose_one` and dispatch vs T6b-2 `_outcome_view`);
   - `tests/authz/test_policy_matrix.py`, `tests/authz/test_route_roles.py` (T6b-2 / T6b-3 rows only);
   - `README.md` head pin (T4 moves it to `0041`; keep `0041`);
   - `contracts/openapi/smartmatch.json`: never hand-merge. Take either side, then `make openapi VENV=$VENV`.
3. If a backend conflict needs more than a union, stop and escalate to the orchestrator.
4. PR against `main`, draft until T8c and T6b-4 merge. Body line 1: **"Merge the T8c and T6b-4 PRs (and their
   stacks) first."** After they land, merge `main` into `feat/b26-t8d` so the diff is T8d only.

T8d writes **no migration**.

**Start gate** (implementation, not this plan). All pushed on their branches:

| Track | Needed from it | Used in milestone |
|---|---|---|
| T8c | `EngagementLoadRepository.engagements_for`, `assess_pool_loads`, `AssessedLoad`, `Q7_REGISTERED_LOAD_BANDS`, `current_cba_registry()`, `registry_for_version`, `CandidateExplanation.load` (`LoadExplanation`), `ExcludedCandidateView.load`, `EXCLUSION_LOAD_FULL`, `tests/unit/registry_evaluation.py` | 1–6 |
| T8b | `LoadBand`, `LoadReason`, `LoadAssessment.unknown_hours_refs` (sorted `pipeline_record` ids as `str`) | 1–2 |
| T4 | `as_of_utc`, `MatchRunResponse.excluded`, `availability_recorded`, exported `MATCH_INELIGIBILITY_EXPLANATIONS`, the `AIMatching` excluded list, `AIMatching.test.tsx`, `CoordinatorInvitations.test.tsx`, `CoordinatorMatchRuns.test.tsx` | 5–8 |
| T3 | `SpeakerAvailabilityResponse`, `availability_response` (`speaker_availability_models.py:115`, `:182` on `feat/b26-t3`), both routes (`speaker_availability.py:90`, `:114`) | 3–4 |
| T6b-2 | `/v1/me/availability` `GET` / `PATCH` calling `availability_response` | 3–4 |
| T5 | `SpeakerAvailabilityPanel.tsx`, `SpeakerAvailabilityPanel.test.tsx` | 7–8 |
| T6b-4 | `SpeakerOwnAvailability.tsx` with `SLOT(T8d)`, its test file G, `test_frontend_speaker_portal_contract.py` item 5 | 7–8 |
| T8a | `CoordinatorBookings.tsx` cancel mutation | 8 |

If a built name differs from its plan, follow the built name and list the difference in the PR body.

## 2. Files

**Backend**

| # | Path | Change |
|---|---|---|
| 1 | `python/smartmatch_persistence/smartmatch_persistence/engagement_labels.py` | **New.** `EngagementLabel` (frozen) and `EngagementLabelRepository.labels_for` (§4.3). One statement; empty input issues none; never commits. T8c's `engagement_load.py` is not edited (the run hot path stays as T8c pinned it). |
| 2 | `services/api/smartmatch_api/speaker_load.py` | **New.** `current_speaker_load(...)` and the pure builder `speaker_load_view(...)` (§4.2). |
| 3 | `services/api/smartmatch_api/routers/speaker_availability_models.py` (T3's) | `EngagementWithoutEndTimeView`, `SpeakerLoadView` (§4.1); `SpeakerAvailabilityResponse.load: SpeakerLoadView` (required); `availability_response(professional_id, stored, *, load)`: `load` is a **required keyword**, so every call site must pass one. `__all__` gains both views. |
| 4 | `services/api/smartmatch_api/routers/speaker_availability.py` (T3's) | `GET` gains `now = utc_now()`; `GET` and `PATCH` compute `load` with `viewer_unit_id=owning_unit_id`; `PATCH` computes it before `session.commit()` (§4.2). |
| 5 | `services/api/smartmatch_api/routers/speaker_self.py` (T6b-2's) | `GET /v1/me/availability` gains `now = utc_now()`; `GET` and `PATCH` compute `load` with `viewer_unit_id=None`, `PATCH` before the commit (§4.2). No other handler changes. |
| 6 | `services/api/smartmatch_api/routers/match_runs.py` | `CandidateLoadBlockView` (subclass of T8c's `LoadBlockView`, §5); `CandidateExplanationView.load` (`:443`) and `_to_view` (`:652`) copy the stored block without `unknown_hours_refs`; `MatchRunResponse.load_recorded` (`:496`) from the run's own pin. T8c's `ExcludedCandidateView` untouched. No new query. |
| 7 | `contracts/openapi/smartmatch.json` | `make openapi VENV=$VENV` (the Connector availability response, `CandidateExplanationView`, `MatchRunResponse`). `/v1/me/*` stays out: `SPEAKER_PORTAL` is off (T6b-2 §5). |

**Frontend**

| # | Path | Change |
|---|---|---|
| 8 | `src/lib/api.ts` | Types `LoadBand`, `LoadReason`, `EngagementWithoutEndTime`, `SpeakerLoad`, `MatchLoad`; `SpeakerAvailability.load: SpeakerLoad`; `MatchCandidateExplanation.load?: MatchLoad \| null`; T4's excluded item `load?: MatchLoad \| null`; `MatchRunRead.load_recorded: boolean` (§6.1). |
| 9 | `src/lib/loadBandCopy.ts` | **New, pure.** Every string in §7; `loadBandWord`, `FULL_RUN_LABEL`, `runLoadDetail`, `currentLoadLines`, `gapItemText`. |
| 10 | `src/app/components/load/LoadBandSummary.tsx` | **New.** The current band for one Speaker: word, sentences, the no-end-time list. Props `{ load: SpeakerLoad; audience: "speaker" \| "connector"; headingLevel: 2 \| 4; idPrefix: string }`. |
| 11 | `src/app/components/load/RunLoadLine.tsx` | **New.** The stored band on a run: `<div><dt>Workload</dt><dd>{word}</dd></div>` plus the detail line (§7.1). |
| 12 | `src/app/pages/AIMatching.tsx` | Header `dl` (`:346-379`) gains the "Workload" row; `CandidateCard` (`:192`) gains a `dl` with `RunLoadLine` when `load_recorded`; T4's excluded list words `load_full` via the exported map plus a `full_by_known_hours` sentence. Used at `:381`, `:414`, `:429`: shortlist, unscorable and considered all get it (T8c records a load on unscorable scores too). |
| 13 | `src/app/pages/coordinator/CoordinatorMatchRuns.tsx` | `MATCH_INELIGIBILITY_EXPLANATIONS` (`:115`, exported by T4) gains `load_full` (§7.1). |
| 14 | `src/app/pages/coordinator/CoordinatorInvitations.tsx` | `Recipient` carries the candidate's `load` from the run read (`:348`); `RecipientRow` (`:188`) shows "Workload when matched: {word}" when `run.load_recorded`. |
| 15 | `src/app/pages/coordinator/SpeakerAvailabilityPanel.tsx` (T5's) | `LoadBandSummary audience="connector" headingLevel={4}` between the read states and the form, once `query.data` is defined. |
| 16 | `src/app/pages/speaker/SpeakerOwnAvailability.tsx` (T6b-4's) | Replace the `SLOT(T8d)` comment with `LoadBandSummary audience="speaker" headingLevel={2}`. |
| 17 | `src/app/pages/coordinator/CoordinatorBookings.tsx` (T8a's) | Cancel `onSuccess` also invalidates the prefix `[principalKey, "speaker-availability", unitId]`: a cancellation lowers the band. |
| 18 | `src/app/pages/coordinator/CoordinatorEvents.tsx` | `saveMutation.onSuccess` (`:363-368`), on an **edit** only, also invalidates `[principalKey, "speaker-availability", unitId]`: an end time added changes the band. |

**Tests** (§9): `tests/unit/test_speaker_load_view.py` (new), `tests/integration/test_engagement_label_read.py` (new),
`tests/contract/test_speaker_availability_api.py` (T3's), `tests/contract/test_speaker_self_api.py` (T6b-2's),
`tests/contract/test_match_runs_api.py`, `tests/unit/test_speaker_availability_models.py` (T3's),
`tests/unit/test_speaker_availability_openapi_contract.py` (T3's), `tests/unit/test_frontend_load_band_contract.py` (new),
`tests/unit/test_frontend_speaker_portal_contract.py` (T6b-4's item 5), the shared fixture
`src/test/speakerLoadFixture.ts` (new), and the Vitest files in §9.4.

**Docs:** parent plan sync (§10 milestone 9).

**Not touched:** `eli.py`, `load_bands.py`, `factor_registry.py`, `engagement_load.py`, `scoring.py`,
`explanation.py`, the worker, any migration, `schema.py`, `SpeakerAvailabilityForm.tsx`, `speakerAvailabilityDraft.ts`.

## 3. Facts this plan rests on (checked)

| # | Fact | Evidence |
|---|---|---|
| 1 | The shortlist renders in `AIMatching`, one `CandidateCard` per candidate, not in `CoordinatorMatchRuns`. | `AIMatching.tsx:192`, `:381`, `:414`, `:429`; T4 plan §1 AIMatching row. |
| 2 | T8c adds `load` to the domain explanation and to `ExcludedCandidateView`, **not** to `CandidateExplanationView`. `_to_view` copies field by field, so without T8d the read drops the shortlist's load. | T8c plan §2 row 10, §7; `match_runs.py:652-697`. |
| 3 | The explanation's factor rows come from `score.factor_scores`, and `engagement_load` is in no model's `scoring_keys`, so no "Engagement load · weight" row with a number appears on a card. | `explanation.py:509-520`; T8c §3.2 invariant 2. |
| 4 | T8b fills `unknown_hours_refs` with `pipeline_record` ids, sorted, even when capacity is not stated; the ref exists "so T8d can name what lacks hours". | T8b plan §2 `Engagement.ref`, §4 step 1. |
| 5 | A Connector can edit an event's time only when `event.host_org_unit_id = unit_id` and `origin = 'coordinator_entry'`. | `manual_events.py:189-199` (`_load_event_and_detail`), PATCH `:396`. |
| 6 | The Events page has no deep link to one event. | `CoordinatorEvents.tsx`: selection is local state (`:295`), no `useSearchParams`. |
| 7 | `speaker-availability` and `my-availability` queries have `staleTime: 30_000`. | `queryClient.ts:106`. |
| 8 | T5 and T6b-4 forbid `/\bavailable\b/i` on their availability surfaces. The parent's run label "Full (no override available)" contains it. | T5 §4.1; T6b-4 §5.4 and test G2; parent §11 risk 3. |
| 9 | T3's unit test and contract test pin the unstated response exactly. | `tests/unit/test_speaker_availability_models.py:243-258`, `tests/contract/test_speaker_availability_api.py:255-270` on `feat/b26-t3`. |
| 10 | T6b-4 test G7 stubs `load: { band: "moderate", utilization: 0.61 }`; test §9.3 item 5 pins `SLOT(T8d)` once. | T6b-4 plan §9.2 G7, §9.3 item 5. |

## 4. Current load on the availability responses (D1, D2, D3)

### 4.1 Wire shape

```python
class EngagementWithoutEndTimeView(BaseModel):
    """One counted engagement whose hours are unknown (T8b R4), labelled for this caller."""

    #: The pipeline_record id (T8b's ref). Null when shown == "other_unit": no other unit's
    #: record id reaches a Connector (plan-gate MED 1).
    engagement_id: uuid.UUID | None
    #: "event": title and date shown. "other_unit": Connector route, event hosted elsewhere.
    #: "event_missing": no event row (T8c OQ3).
    shown: Literal["event", "other_unit", "event_missing"]
    event_title: str | None  # set iff shown == "event"
    local_date: date | None  # event.resolved_date when shown == "event", else null
    time_precision: (
        Literal["exact", "date_only", "unresolved"] | None
    )  # null unless shown == "event"
    #: Connector route only: this unit hosts it and it is a coordinator_entry event.
    editable_here: bool


class SpeakerLoadView(BaseModel):
    """The Speaker's current load band. A band word's inputs only: no hours, no ratio (OQ-CBA-005)."""

    band: Literal["light", "moderate", "heavy", "full", "unknown"]
    reason: Literal["measured", "capacity_not_stated", "hours_unknown", "full_by_known_hours"]
    as_of: date  # the UTC date it was measured (T4 C7, T8b R2)
    used_in_matching: bool  # current_cba_registry().load_bands is not None
    engagements_without_end_time: list[EngagementWithoutEndTimeView]  # at most 20
    engagements_without_end_time_truncated: bool
```

- `load` is always present. `stated: false` gives `band "unknown"`, `reason "capacity_not_stated"`, and any
  counted engagement without an end time is still listed (T8b §4 step 1 fills the refs without capacity).
- **No `int` or `float` anywhere in `load`** (test U7 walks the JSON schema). `SpeakerAvailabilityResponse`
  already carries the capacity as a number (T3); `load` does not repeat it or add any other.
- Both routes share the model (T6b-2 §2.5), so both carry `load`.

### 4.2 Computation — `speaker_load.py`

```python
MAX_LISTED_WITHOUT_END_TIME: Final[int] = 20


def display_load_bands() -> RegisteredLoadBands:
    """The current registry's band table, else the Q7 table 3.0.0 declares (D2)."""
    bands = current_cba_registry().load_bands
    return Q7_REGISTERED_LOAD_BANDS if bands is None else bands


def current_speaker_load(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    capacity: Decimal | None,
    viewer_unit_id: uuid.UUID | None,
    now: datetime,
) -> SpeakerLoadView: ...


def speaker_load_view(
    assessed: AssessedLoad,
    labels: Sequence[EngagementLabel],
    *,
    has_more: bool,
    used_in_matching: bool,
    viewer_unit_id: uuid.UUID | None,
) -> SpeakerLoadView: ...
```

`current_speaker_load`, in order:

1. `as_of = as_of_utc(now)` (T4). `now` is the handler's one `utc_now()`, the same value T3 uses for "today".
2. `bands = display_load_bands()`; `used = current_cba_registry().load_bands is not None`.
3. `engagements = EngagementLoadRepository().engagements_for(session, tenant_id=…, professional_ids=[professional_id], as_of=as_of)`: T8c's read, tenant-wide (T8c OQ2), cancelled excluded, one query.
4. `assessed = assess_pool_loads([professional_id], capacities={professional_id: capacity}, engagements=engagements, as_of=as_of, bands=bands)[professional_id]`: the exact path a 3.x run takes, so the panel and the next run agree.
5. `refs = assessed.assessment.unknown_hours_refs`. Empty → no second query. Else
   `labels_for(..., record_ids=[UUID(r) for r in refs], limit=MAX_LISTED_WITHOUT_END_TIME + 1)`; `has_more = len(result) > 20`, keep 20.
6. `speaker_load_view(...)`.

`capacity` is `stored.statement.declared_capacity_hours_per_90_days` (T2: `Decimal | None`), or `None` when
there is no row. Never a default (Q6).

`speaker_load_view` label rule, per label:

| Label | `viewer_unit_id is None` (Speaker) | `viewer_unit_id` set (Connector) |
|---|---|---|
| no event row | `event_missing` | `event_missing` |
| event hosted by `viewer_unit_id` | `event`; `editable_here = origin == "coordinator_entry"` | same |
| event hosted by another unit | `event` (their own engagement; `/v1/me/engagements` already shows every unit's titles, T6b-2 §2.4); `editable_here = False` | `other_unit`; `engagement_id`, title, date and precision null; `editable_here = False` |

On the Speaker route `editable_here` is always `False`. `engagement_id` is set for `event` and
`event_missing` on the Speaker route. On the Connector route it is set only when the viewer's unit
owns the `pipeline_record` (review H1 on #225: an event-less booking or another unit's booking at
this unit's event carries no id), and it is always null for `other_unit`.

**Query cost per request:** T3 / T6b-2's reads **+ 1** (engagements), **+ 1 more** when any engagement lacks
an end time (labels): **2 at most**. Pinned by contract tests A9 and S4.

**Where it is called.** T3 `GET` and `PATCH` (`speaker_availability.py:106`, `:153`) and T6b-2 `GET` and
`PATCH /v1/me/availability`. The route handlers pass `load=` to `availability_response`.

| Handler | `now` | When `load` is computed |
|---|---|---|
| `GET` (both routes) | **New:** `now = utc_now()` at the top of the handler (T3's GET has none today, `speaker_availability.py:90-106`), passed to `current_speaker_load` | after the stored row is read |
| `PATCH` (both routes) | the handler's existing `now = utc_now()` (`speaker_availability.py:138`; T6b-2 §3.3 step 3) | after `write_statement` returns `result` (`:140`), **before** `session.commit()` (`:152`), with capacity from `result.statement` |

**Why before the commit (plan-gate MED 4).** If the load read fails after a commit, the client sees a 500 but
the row is already written at `version + 1`; a retry with the old `expected_version` then gets a false
`409 speaker_availability_stale`. Computed before the commit, a load-read failure rolls the whole request
back, so a retry succeeds. The engagements and labels reads touch only `pipeline_record` and `event`, never
the row just written, so reading them inside the write transaction changes nothing they return. Contract
test A13 pins it.

### 4.3 `EngagementLabelRepository.labels_for`

```sql
SELECT r.id AS record_id, e.id AS event_id, e.title, e.resolved_date, e.time_precision,
       e.host_org_unit_id, e.origin
FROM pipeline_record AS r
LEFT JOIN event AS e
  ON e.tenant_id = r.tenant_id AND e.id = r.opportunity_event_id
WHERE r.tenant_id = :tenant_id
  AND r.id = ANY(:record_ids)
ORDER BY e.resolved_date NULLS LAST, r.id
LIMIT :limit
```

- Served by `pipeline_record_pkey` and `uq_event_tenant_id`. No new index.
- Returns `tuple[EngagementLabel, ...]` in that order; empty input → `()` and no statement.
- Tenant-scoped: an id from another tenant returns nothing (test L3).

## 5. Stored load on the run read (D5)

`CandidateExplanationView` gains:

```python
load: CandidateLoadBlockView | None = Field(
    default=None,
    description=(
        "The engagement load recorded for this candidate at run time (registry 3.x only; "
        "null on 1.x and 2.x runs). Screens show the band word only (OQ-CBA-005)."
    ),
)
```

```python
class CandidateLoadBlockView(LoadBlockView):
    """T8c's excluded-candidate load block plus the two Stage B fields a scored candidate has."""

    multiplier: str  # the registry table's multiplier for this band, as a decimal string
    composite_before_load: float | None  # unrounded; null iff heuristic_score is null
```

- **A subclass, so T8c's schema stays as it is (plan-gate MED 5).** `LoadBlockView` is the model T8c built
  for `ExcludedCandidateView.load`; T8d does not edit it, and `ExcludedCandidateView.load` keeps its type.
  The OpenAPI component for T8c's block is byte-identical before and after T8d (test R7).
- **No `unknown_hours_refs` in the candidate block (plan-gate MED 2).** Those are `pipeline_record` ids from
  every unit (T8c OQ2: the load read is tenant-wide), and the Connector run wire must carry none of another
  unit's record ids. The run card never needs them: it points to the availability panel, which labels the
  gaps per unit (§4.2). Resolution rule at implementation, because Pydantic cannot drop an inherited field:
  - T8c's `LoadBlockView` has no `unknown_hours_refs` field → subclass exactly as above;
  - it has one (T8c §7 says the excluded block is "the same shape" as the payload block, which lists the
    refs) → `CandidateLoadBlockView` is a standalone model with `LoadBlockView`'s other fields plus the two
    above, and `ExcludedCandidateView.load` is still left untouched. Either way MED 5's goal (T8c's schema
    unchanged) and MED 2's (no refs on the candidate block) both hold. The PR body names which case applied.
- T8c's excluded block keeps whatever T8c ships. If it carries `unknown_hours_refs`, that is the same
  cross-unit exposure for Full Speakers: noted for the orchestrator in §12, not changed here.
- If T8c typed `ExcludedCandidateView.load` as a plain `dict`, T8d introduces `CandidateLoadBlockView`
  standalone with the T8c §7 keys minus `unknown_hours_refs`, and leaves the `dict` alone.
- `_to_view` copies `explanation.load` field for field, except `unknown_hours_refs`; decimals as `str`, no
  rounding (the `_to_view` docstring rule, `match_runs.py:652-660`).

`MatchRunResponse` gains:

```python
load_recorded: bool = Field(
    description=(
        "True when this run's registry pin applies engagement load (3.x), so every candidate "
        "carries a load block. False for 1.x and 2.x runs and for an unknown pin."
    )
)
```

Derived from the pin, never guessed from the data: `registry_for_version(run.registry_version).load_bands is
not None`; an unknown pin (T8c §8 read fallback) → `False`. No database read; T4's read query count holds
(test R4).

## 6. Frontend

### 6.1 Types (`api.ts`)

```ts
export type LoadBand = "light" | "moderate" | "heavy" | "full" | "unknown";
export type LoadReason = "measured" | "capacity_not_stated" | "hours_unknown" | "full_by_known_hours";
export interface EngagementWithoutEndTime {
  engagement_id: string | null; // null for "other_unit"
  shown: "event" | "other_unit" | "event_missing";
  event_title: string | null;
  local_date: string | null; // YYYY-MM-DD
  time_precision: "exact" | "date_only" | "unresolved" | null;
  editable_here: boolean;
}
export interface SpeakerLoad {
  band: LoadBand; reason: LoadReason; as_of: string; used_in_matching: boolean;
  engagements_without_end_time: EngagementWithoutEndTime[];
  engagements_without_end_time_truncated: boolean;
}
/**
 * A run's stored load, band fields only. The wire also carries hours and utilization for
 * audit; they are deliberately not typed here, so no page can render them (OQ-CBA-005).
 */
export interface MatchLoad { band: LoadBand; reason: LoadReason }
```

`SpeakerAvailability` gains `load: SpeakerLoad`. `MatchCandidateExplanation` and T4's excluded item gain
`load?: MatchLoad | null`. `MatchRunRead` gains `load_recorded: boolean`.

### 6.2 Where each surface reads it

| Surface | Source | Shown when |
|---|---|---|
| `CandidateCard` (shortlist, unscorable, considered) | `candidate.load` | `run.load_recorded` |
| Run header `dl` | `run.load_recorded` | always (one row) |
| `AIMatching` excluded list, token `load_full` | map text + `excluded.load?.reason` | the token is present |
| `CoordinatorMatchRuns` `202` state | `MATCH_INELIGIBILITY_EXPLANATIONS.load_full` | the token is present |
| `RecipientRow` (compose) | the run read's `candidate.load` | `run.load_recorded` |
| Connector availability panel (T5) | `data.load` | `query.data` defined |
| Speaker Availability page (T6b-4 slot) | `data.load` | `query.data` defined |

Rendering rules, all surfaces:

- Switch on `band` and `reason`, never on a missing value. `load_recorded` true with `candidate.load`
  null or absent → "Workload not recorded for this Speaker" (a defect made visible, never a default band;
  ADR-0011).
- No sort, no arithmetic, no `toFixed`, no `%`. Order is the server's.
- The load read state is the page's: no own spinner, no own error. `LoadBandSummary` renders only with data.
- No new query key, no new mutation. The band refreshes through the existing
  `speaker-availability` / `my-availability` reads: T5's and T6b-4's `setQueryData(saved)` after a save
  (the PATCH response carries the recomputed `load`), and the two invalidations in §2 rows 17–18.
- **Accepted staleness:** confirming a booking (the pipeline confirm action) raises the band but invalidates
  no `speaker-availability` key. The panel re-reads on open once the 30 s `staleTime` has passed
  (`queryClient.ts:106`), so a Connector may see the pre-confirmation band for up to 30 s. Accepted
  (orchestrator, plan gate); not fixed here.
- **List keys use the index** (`key={index}`), never `engagement_id`: it is null for `other_unit` items
  (plan-gate MED 1). The list is never reordered client-side, so an index key is stable.

### 6.3 Component tree

```text
SpeakerOwnAvailability                       h1#my-availability-heading "Your availability"
├─ read states (T6b-4)
├─ LoadBandSummary audience=speaker          section aria-labelledby → h2 "Your workload"
│  ├─ p: band word (strong) · "Measured <time>"
│  ├─ p: used_in_matching sentence
│  ├─ p: reason sentence
│  └─ ul: one li per engagement without an end time (title · <time> date)
└─ SpeakerAvailabilityForm (T5)

SpeakerAvailabilityPanel (T5)                section → h3 "Availability for {name}"
├─ read states (T5)
├─ LoadBandSummary audience=connector        div role="group" aria-labelledby → h4 "Workload"
│  └─ … same, each li: title · <time> · precision phrase · link "Add the end time on the Events page" when editable_here
└─ SpeakerAvailabilityForm (T5)

AIMatching
├─ header dl: … · "Workload" → "Recorded per Speaker below" | "Not part of this run's matching"
├─ CandidateCard: … · dl → RunLoadLine (dt "Workload", dd band word) · p detail
└─ excluded list (T4): li subject · reason words; load_full → "Full (no override available)" + detail
```

## 7. Copy

No digit appears in any string below; the only digits on screen are dates inside `<time>` (tests V-A3,
V-B6). Nothing on the availability surfaces contains "available" (T5 §4.1, T6b-4 G2).

### 7.1 Run views (Connector, stored at run time)

| `band` / `reason` | Word | Detail (card) |
|---|---|---|
| `light` / `measured` | Light | "Workload did not change the ranking." |
| `moderate` / `measured` | Moderate | "Ranked a little lower for workload." |
| `heavy` / `measured` | Heavy | "Ranked lower for workload." |
| `unknown` / `capacity_not_stated` | Load not measurable | "No capacity was stated, so workload did not change the ranking." |
| `unknown` / `hours_unknown` | Load not measurable | "Some confirmed engagements had no end time, so workload did not change the ranking. This Speaker's availability on Speaker contacts lists them." |
| excluded `load_full` (any reason) | **Full (no override available)** (verbatim, parent §11 risk 3; `FULL_RUN_LABEL`) | map text: "Full (no override available). Their confirmed and recent engagements exceed the hours they can give, so this run left them out." |
| excluded `load_full`, `load.reason = full_by_known_hours` | same | map text + "Some of their engagements also have no end time." |
| `load_recorded` false | header row only | "Not part of this run's matching" |
| `load_recorded` true, load missing | Workload not recorded for this Speaker | — |
| compose `RecipientRow` | "Workload when matched: {word}" | — |

### 7.2 Connector availability panel (current)

| Part | Text |
|---|---|
| Heading | "Workload" |
| Word + date | "{word}" · "Measured {as_of}" |
| Intro | "Recent and upcoming confirmed engagements, against the stated capacity." |
| `used_in_matching` false | "Matching does not use workload yet." |
| used, `light` | "Matching does not lower this Speaker's ranking for workload." |
| used, `moderate` | "Matching ranks this Speaker a little lower for workload." |
| used, `heavy` | "Matching ranks this Speaker lower for workload." |
| used, `full` | "New matching runs leave this Speaker out until the workload drops. There is no override yet." |
| used, `unknown` | "Matching does not change this Speaker's ranking until workload can be measured." |
| `capacity_not_stated` | "No capacity is stated. Add it below to measure workload." |
| `hours_unknown` | "These confirmed engagements have no end time, so their hours cannot be counted:" |
| `full_by_known_hours` | "The engagements with known hours already exceed the capacity. These others have no end time:" |
| item `event`, `exact` | "{title}" · `<time>` · "start time only" |
| item `event`, `date_only` | "{title}" · `<time>` · "date only, no times" |
| item `event`, `unresolved` | "{title}" · "date not set" |
| item link (`editable_here`) | visible "Add the end time on the Events page"; accessible name "Add the end time on the Events page for {title}" (review M1 on #225: the name starts with the whole visible text); `to="/coordinator-portal/events"` |
| item `event`, not editable here | "Recorded from an imported listing, so it cannot be edited here." when this unit hosts it; otherwise nothing extra |
| item `other_unit` | "An engagement another unit recorded. That unit's Speaker Connector can add the end time." |
| item `event_missing` | "An engagement whose event record is missing." |
| truncated | "More engagements also have no end time." |

### 7.3 Speaker page (current)

| Part | Text |
|---|---|
| Heading | "Your workload" |
| Word + date | "{word}" · "Measured {as_of}" |
| Intro | "Your recent and upcoming confirmed engagements, against the capacity you gave." |
| `used_in_matching` false | "Matching does not use your workload yet." |
| used, `light` | "Your workload does not lower your place in matching." |
| used, `moderate` | "Matching ranks you a little lower while your workload is Moderate." |
| used, `heavy` | "Matching ranks you lower while your workload is Heavy." |
| used, `full` | "You are not put forward for new events until your workload drops. Your Speaker Connector can tell you more." |
| used, `unknown` | "Your workload does not change matching until it can be measured." |
| `capacity_not_stated` | "You have not given a capacity. Add it below so your workload can be measured." |
| `hours_unknown` | "These engagements have no end time yet, so their hours cannot be counted. Your Speaker Connector can add them:" |
| `full_by_known_hours` | "Your engagements with known hours already exceed your capacity. These others have no end time yet:" |
| item `event` | "{title}" · `<time>` or "date not set" |
| item `event_missing` | "An engagement whose event details are no longer on file." |
| truncated | "More of your engagements also have no end time." |

## 8. Accessibility (WCAG 2.2 AA)

1. **Text, not colour.** The band is a word in text. Any chip styling is decorative; an icon, if used, is
   `aria-hidden="true"` (1.4.1).
2. **Headings.** Speaker page: `h1` "Your availability" → `h2` "Your workload" (sequential after T6b-4's
   outline). Connector panel: T5's `h3` → `h4` "Workload". Cards: no new heading; the band sits in a `dl`
   row (`dt` "Workload", `dd` word), so a screen reader reads "Workload, Moderate".
3. **Landmarks.** `LoadBandSummary` is a `section` with `aria-labelledby` on the Speaker page (`{idPrefix}-load-heading`),
   so it is a named region. Inside T5's panel section it is a `div role="group"` with `aria-labelledby`
   (a plain `div` would make the label meaningless; `group` names it without adding a second region).
4. **No new live region.** Pages keep T5 / T6b-4's one `role="status"`. The band is re-rendered text after a
   save; the save outcome is already announced (T5 §4, T6b-4 §8.2).
5. **Lists.** Engagements without an end time are a `ul` directly after the sentence that introduces them.
   Every date is a `<time dateTime="YYYY-MM-DD">` through T5's `formatCalendarDate` (UTC, never shifts a day).
6. **Links.** The Events link's accessible name starts with its visible text and adds the title (2.5.3).
   Inline links in running text are exempt from 2.5.8; the CPP focus ring applies (2.4.7).
7. **Reflow.** Rows stack below `sm`; long titles `break-words`. No horizontal overflow at 360 px. Browser
   check at 360, 768, 1024 and 1440 with `SPEAKER_PORTAL` flipped on locally (not committed).

## 9. Tests — written first (TDD)

Local rules (env): one pytest file at a time; DB tests on a private database `smartmatch_b26_t8d`, dropped
after; Vitest from a Linux-FS copy (`cp -r apps/web/legacy-frontend /tmp/t8d-web && (cd /tmp/t8d-web && npm ci)`
in the background, then `rsync -a --delete apps/web/legacy-frontend/src/ /tmp/t8d-web/src/` and
`npx vitest run --pool=threads <file>`); `npx tsc --noEmit -p .` in place. CI proves the suite. No
credential-shaped literals in tests.

### 9.1 Python unit

**`tests/unit/test_speaker_load_view.py`** (new, no DB; T8b `compute_eli` on hand-built `Engagement`s)

- U1 `test_each_band_and_reason_maps_to_the_view` (parametrized: light, moderate, heavy, full/measured, full/full_by_known_hours, unknown/capacity_not_stated, unknown/hours_unknown)
- U2 `test_display_bands_are_q7_while_current_is_2_0_0_and_the_registry_s_after_a_flip` (monkeypatch `factor_registry.CURRENT_CBA_REGISTRY` to `CBA_REGISTRY_3`; no `registry_evaluation` needed: no gate is called)
- U3 `test_used_in_matching_follows_the_current_registry` (false now; true when patched)
- U4 `test_speaker_viewer_sees_every_title_and_nothing_is_editable`
- U5 `test_connector_viewer_hides_other_units_titles_and_marks_only_own_coordinator_entry_events_editable` (own `coordinator_entry` → editable; own `extraction` → not; other unit → `other_unit` with `engagement_id`, title, date and precision all null; the Speaker viewer keeps `engagement_id` for every item)
- U6 `test_missing_event_is_event_missing`; `test_labels_keep_repository_order_and_truncate_at_20` (21 labels → 20 + truncated)
- U7 `test_the_load_schema_holds_no_number` (walk `SpeakerLoadView.model_json_schema()`: no `number` or `integer` type anywhere)
- U8 `test_capacity_none_is_never_defaulted` (`capacity_not_stated`, refs still listed)

**`tests/unit/test_speaker_availability_models.py`** (T3's, edited): `test_response_for_no_row_is_not_stated`
(`:243`) and `test_response_maps_sources_and_capacity_as_float` (`:258`) pass a `load=`; new
`test_availability_response_requires_a_load_keyword` (`TypeError` without it).

**`tests/unit/test_speaker_availability_openapi_contract.py`** (T3's, edited): O1
`test_response_carries_load_with_no_numeric_field`; O2 `test_load_is_required_in_the_response`.

### 9.2 Python integration

**`tests/integration/test_engagement_label_read.py`** (new, Postgres, private DB)

- L1 `test_labels_carry_title_date_precision_unit_and_origin`
- L2 `test_a_record_naming_no_event_returns_null_event_fields`
- L3 `test_another_tenants_records_are_invisible`
- L4 `test_order_is_date_then_id_with_unresolved_last`
- L5 `test_limit_is_applied_in_sql`
- L6 `test_empty_input_issues_no_statement` and `test_one_statement_for_twenty_one_ids` (`before_cursor_execute` count)

### 9.3 Python contract

**`tests/contract/test_speaker_availability_api.py`** (T3's; `:255-270` exact-JSON test gains the unstated
`load` block: `{"band": "unknown", "reason": "capacity_not_stated", "as_of": <utc today>, "used_in_matching": false, "engagements_without_end_time": [], "engagements_without_end_time_truncated": false}`)

- A1 `test_get_carries_load_on_every_response`
- A2 `test_capacity_and_exact_engagements_give_the_band_word` (attended 60 h at −10 against 100.0 → `moderate`)
- A3 `test_a_date_only_engagement_is_hours_unknown_and_listed`
- A4 `test_an_exact_event_without_end_is_listed_with_precision_exact`
- A5 `test_another_units_engagement_counts_but_shows_no_title_and_no_record_id` (`engagement_id` is null; the other unit's `pipeline_record` id appears nowhere in the response body)
- A6 `test_own_coordinator_entry_event_is_editable_and_extracted_is_not`
- A7 `test_a_cancelled_booking_is_not_counted` (T8a `cancel_booking`)
- A8 `test_patch_response_recomputes_the_band_from_the_new_capacity`
- A9 `test_load_costs_one_query_and_two_with_gaps` (`before_cursor_execute`, against T3's baseline)
- A10 `test_no_number_inside_load` (walk the JSON)
- A11 `test_band_equals_assess_pool_loads_on_the_same_inputs`
- A12 `test_used_in_matching_is_false_while_2_0_0_is_current_and_true_after_a_patched_flip` (patch `CURRENT_CBA_REGISTRY`; GET needs no gate)
- A13 `test_a_load_read_failure_on_patch_rolls_back_so_the_retry_is_not_stale` (monkeypatch `current_speaker_load` to raise once: the PATCH answers 500, the stored `version` is unchanged, and the same body with the same `expected_version` then answers 200, not `409 speaker_availability_stale`)
- A14 `test_get_measures_as_of_from_its_own_utc_now` (patch `utc_now` to 23:30 UTC on 5 Oct → `as_of` 5 Oct)

**`tests/contract/test_speaker_self_api.py`** (T6b-2's, capability-on app)

- S1 `test_my_availability_carries_load`
- S2 `test_the_speaker_sees_titles_from_every_unit_and_nothing_editable`
- S3 `test_my_patch_recomputes_the_band`
- S4 `test_my_load_costs_the_same_queries_as_the_connector_route`
- S5 `test_no_subject_is_taken_from_the_request` (the T6b-2 source guard stays green: `principal.user_id` is not passed to `current_speaker_load`)

**`tests/contract/test_match_runs_api.py`**

- R1 `test_a_2_0_0_run_reads_load_recorded_false_and_every_load_null`
- R2 `test_under_evaluation_a_3_0_0_run_reads_each_candidates_stored_band` (T8c `evaluate_registry_3`, modules `smartmatch_domain.scoring`, `smartmatch_domain.explanation`, `smartmatch_api.routers.match_runs`)
- R3 `test_the_candidate_load_block_is_copied_without_rounding_and_without_refs` (decimals as strings equal the payload's; no `unknown_hours_refs` key, even when the stored block lists refs)
- R4 `test_load_adds_no_query_to_the_run_read` (T4 test 17's count unchanged)
- R5 `test_an_unknown_pin_reads_load_recorded_false`
- R6 `test_excluded_load_full_keeps_its_load_block` (T8c C2's read, re-asserted after T8d's view change)
- R7 `test_t8cs_excluded_load_schema_is_unchanged` (the OpenAPI component for `ExcludedCandidateView.load` equals the one captured on the merged T8c base at milestone 5, key for key; `CandidateLoadBlockView` is a separate component)

### 9.4 Vitest (`src/**/*.test.tsx`; `fireEvent` only, no user-event, no jest-dom)

Harness: the `CoordinatorRedemptionQueue.test.tsx` pattern (T6b-4 §9.1): `vi.stubGlobal("fetch", …)` keyed
`"METHOD path"`, a fresh `QueryClient` per test, mocked `usePrincipalKey`, `cleanup()` and
`vi.unstubAllGlobals()` in `afterEach`, `vi.setSystemTime(new Date("2026-10-06T12:00:00Z"))`.

**Shared fixture (plan-gate MED 3).** Milestone 7 adds `src/test/speakerLoadFixture.ts` (not a `.test.tsx`,
so Vitest does not collect it): `speakerLoadFixture(overrides?: Partial<SpeakerLoad>): SpeakerLoad`,
defaulting to `band "light"`, `reason "measured"`, `as_of "2026-10-06"`, `used_in_matching false`, no
engagements, not truncated. In the same milestone, **every** `SpeakerAvailability` stub (GET and PATCH
responses) in T5's file C (`SpeakerAvailabilityPanel.test.tsx`) and T6b-4's file G
(`SpeakerOwnAvailability.test.tsx`) gains `load: speakerLoadFixture()`. Without it those stubs lack a
required field, and the pages would render `LoadBandSummary` from `undefined`. Any other test that stubs
an availability response (grep `declared_capacity_hours_per_90_days` under `src/`) gets the same line.

**Digit-free fixtures.** Every event title in V-B and V-C fixtures contains no digit (for example
"Corporate treasury guest lecture"), so the "no digit outside `<time>`" assertions test the load, not the
title.

**V-A `src/lib/loadBandCopy.test.tsx`** (pure)

1. `every band and reason has a word and a sentence for each audience` (`it.each`)
2. `the run Full label is exactly "Full (no override available)"`
3. `no string contains a digit or a percent sign`
4. `no speaker or connector-panel string contains the word available`

**V-B `src/app/components/load/LoadBandSummary.test.tsx`**

1. `renders the band word for each band` (`it.each`) · `Load not measurable for unknown`
2. `used_in_matching false shows the not-used sentence and no consequence sentence`
3. `used_in_matching true with full shows the no-override sentence (connector) and the not-put-forward sentence (speaker)`
4. `hours_unknown lists each engagement with its title and a time element` · `truncated adds the more sentence`
5. `other_unit and event_missing items have their sentences and no link`
6. `extra numeric fields on the wire render no digit outside time elements` (stub adds `utilization: 0.61`, `completed_hours: "50"`; titles digit-free)
10. `list items key by index, so two other_unit items with null ids both render`
7. `connector: only editable_here items have a link, named with the title` (`getByRole("link", { name: "Add the end time on the Events page for Corporate treasury guest lecture" })`)
8. `speaker: no link at all`
9. `heading level follows the prop; speaker: a section labelled by it; connector: a div with role=group labelled by it`

**V-C `src/app/pages/speaker/SpeakerOwnAvailability.test.tsx`** (T6b-4's file G, edited)

1. `the workload section sits between the read states and the form in DOM order`
2. `no workload section while the read is pending or failed`
3. G7 re-pointed: stub `speakerLoadFixture({ band: "moderate" })` plus `utilization: 0.61`, digit-free titles → "Moderate" shown, no digit outside `<time>`
4. `a save shows the band from the PATCH response` (setQueryData path; no extra GET)
5. G2 still holds with every band: no `/\bavailable\b/i` in `main`

**V-D `src/app/pages/coordinator/SpeakerAvailabilityPanel.test.tsx`** (T5's file, edited)

1. `the panel shows the workload section with the connector copy`
2. `no /\bavailable\b/i in the panel for any band`
3. `the Events link is present only for an editable item`

**V-E `src/app/pages/AIMatching.test.tsx`** (T4's file, edited)

1. `a 2.0.0 run shows Not part of this run's matching and no workload row on any card`
2. `a 3.x run shows the band word on shortlist, unscorable and considered cards`
3. `each run detail sentence follows band and reason` (`it.each`)
4. `excluded load_full reads Full (no override available); full_by_known_hours adds the end-time sentence`
5. `load_recorded true with a null load reads Workload not recorded for this Speaker`
6. `no % and no digit from the load block on the page` (stub carries T8c's numeric block)

**V-F `src/app/pages/coordinator/CoordinatorInvitations.test.tsx`** (T4's file, edited)

1. `RecipientRow shows Workload when matched for a 3.x run` · `nothing for a 2.0.0 run`

**V-G `src/app/pages/coordinator/CoordinatorMatchRuns.test.tsx`** (T4's file, edited)

1. `the 202 excluded list words load_full with the Full label`

**V-H `src/app/pages/coordinator/CoordinatorBookings.test.tsx`** (T8a's file, edited) and
**`src/app/pages/coordinator/CoordinatorEvents.test.tsx`** (new)

1. Bookings test 9 re-pointed: `success invalidates confirmed-speakers, the unit metrics key and the speaker-availability prefix, and nothing else`
2. `an event edit invalidates the unit's speaker-availability prefix; a new draft does not`

### 9.5 Python source scans (CI runs `pytest tests/`)

**`tests/unit/test_frontend_load_band_contract.py`** (new; `_code_only` from `test_frontend_invitation_compose_contract.py:53`)

- F1 `test_match_load_and_speaker_load_types_declare_no_number` (`api.ts`: the `MatchLoad`, `SpeakerLoad`, `EngagementWithoutEndTime` bodies contain no `number`)
- F2 `test_load_files_read_no_numeric_field` (`loadBandCopy.ts`, `components/load/*.tsx`: none of `utilization`, `completed_hours`, `confirmed_hours`, `capacity_hours`, `multiplier`, `composite_before_load`, `toFixed`, `%`)
- F3 `test_the_full_run_label_is_defined_once` (`"Full (no override available)"` only in `loadBandCopy.ts`)
- F4 `test_every_surface_uses_the_shared_copy` (`AIMatching.tsx`, `CoordinatorInvitations.tsx`, `SpeakerAvailabilityPanel.tsx`, `SpeakerOwnAvailability.tsx` import from `loadBandCopy` or `components/load/`, and none spells a band word literal)

**`tests/unit/test_frontend_speaker_portal_contract.py`** (T6b-4's item 5, edited):
`test_the_t6b5_slots_are_marked_and_t8d_filled_its_slot` — `SLOT(T6b-5)` twice in `SpeakerPortalLayout.tsx`;
`SLOT(T8d)` **absent** and `LoadBandSummary` imported in `SpeakerOwnAvailability.tsx`.

Unchanged and run one at a time: `test_frontend_matching_contract.py`, `test_frontend_match_run_contract.py`
(no `%`, no decimal literal in `CoordinatorMatchRuns.tsx`), `test_frontend_invitation_compose_contract.py`,
`test_frontend_zero_coercion_contract.py`, T3's `test_frontend_speaker_availability_contract.py`.

## 10. Commit milestones (red → green, one commit each, pushed)

Every commit ends with the `Co-Authored-By` trailer. Each red commit body quotes the red run (for example
"U 0/9 pass; ModuleNotFoundError: smartmatch_api.speaker_load"). `ruff check` + `ruff format` on every
touched Python file and this plan before each push.

| # | Commit | Tests green |
|---|---|---|
| 0 | `chore: merge origin/feat/b26-t8c into feat/b26-t8d`; `chore: merge origin/feat/b26-t6b-4 into feat/b26-t8d` (§1; `make openapi VENV=$VENV` if the JSON conflicted) | T8c's and T6b-4's own |
| 1 | `test: current speaker load view and engagement labels (red)` | — |
| 2 | `feat: current load band for a Speaker, computed at request time` (files 1–3) | U1–U8, L1–L6, T3 model tests |
| 3 | `test: availability responses carry the load band (red)` (incl. the T3 exact-JSON edit, O1–O2) | — |
| 4 | `feat: Connector and Speaker availability responses carry load` (files 4, 5, 7) | A1–A14, S1–S5, O1–O2 |
| 5 | `test: match run read carries stored load (red)` | — |
| 6 | `feat: match run read renders stored load and load_recorded` (files 6, 7) | R1–R7; T4's and T8c's contract tests unedited and green |
| 7 | `test: load band on run views, compose, panel and Speaker page (red)` (V-A…V-H, F1–F4, the T6b-4 scan edit; `src/test/speakerLoadFixture.ts` and `load: speakerLoadFixture()` on every availability stub in T5 file C and T6b-4 file G, §9.4) | — |
| 8 | `feat: load band on run views, compose, availability panel and Speaker page` (files 8–18) | V-A…V-H, F1–F4; `npx tsc --noEmit -p .` clean |
| 9 | `docs: parent plan sync for T8d` — §4.1 names the `load` shape (§4.1 here); §6 T4/T8d row names `AIMatching` and the availability panel; §8 T8d row: estimate 2.5 days, "Depends on T8c, T6b-4 (and T5, T8a through them)"; §11 risk 4 mitigation names the panel list. Then push and open the PR `feat: load band on run views and availability pages (B26 T8d)`, draft. | — |

PR body: line 1 from §1; the test plan (Python files one at a time, Vitest files, tsc, scans); the widths
checked; ends with the Claude Code line; edited with `gh api -X PATCH …/pulls/N -F body=@file` (env rule 9).

## 11. Contradictions found and how this plan handles them

| # | Found | Handling |
|---|---|---|
| X1 | Parent §6 puts the band on `CoordinatorMatchRuns` / `CoordinatorInvitations`. The shortlist renders in `AIMatching` (T4 found the same); `CoordinatorMatchRuns` shows only the `202`. | Band on `AIMatching` cards and excluded list, `RecipientRow`, and the `202` token map (§6.2). |
| X2 | Parent §11 risk 3's "Full (no override available)" contains "available", which T5 and T6b-4 forbid on availability surfaces. | Verbatim label on run views only; availability surfaces say "Full" plus "There is no override yet" (§7). |
| X3 | T8c adds `load` to `ExcludedCandidateView` but not `CandidateExplanationView`; the read would drop the shortlist's band. | T8d adds it (§5). |
| X4 | T8c puts hours and utilization on the run-read wire; the parent says "never a number". | The parent's rule is about screens: the TS type declares band fields only (F1), the availability routes carry none (U7, A10). OQ-3. |
| X5 | Parent §4.1 says the Connector response carries `load` "after T8", but 3.0.0 is proposed, not current. | Computed independent of the flip, with `used_in_matching` saying whether it counts yet (D2). OQ-1. |
| X6 | Parent §8 estimates T8d at 1 day. This scope (two response fields, one repository, four surfaces, two invalidations) is about 2.5. | Stated in the parent sync (milestone 9). |
| X7 | T8a's cancel says "nothing else is invalidated"; T6b-4 test G7 stubs a partial `load`; T6b-4 scan pins `SLOT(T8d)`; T3 tests pin the unstated JSON exactly. | Each edited in the milestone that changes it (§9). |

## 12. Open questions — decided (orchestrator, plan gate 2026-09-23)

OQ-1…OQ-3: accepted as recommended. OQ-4 and OQ-5: follow-up cards, not T8d.

| # | Question | Recommendation (ruling) |
|---|---|---|
| OQ-1 | **(orchestrator flag)** Compute and show the current band while registry 3.0.0 is proposed? | **Yes.** Compute from T8b / T8c code with the Q7 table, label it "Matching does not use workload yet" via `used_in_matching`. It lets Speakers and Connectors fix capacity and end times before the flip, and the flip needs no frontend change. |
| OQ-2 | Show a Speaker their band before IA West reviews the rule (parent §10 row 3)? | **Yes, with the not-used sentence.** Parent §2 lists "current load band" among the data a Speaker sees. Hiding it until `used_in_matching` is a one-line change in `LoadBandSummary` if the owner prefers. |
| OQ-3 | Keep hours and utilization on the run-read wire (T8c's excluded block, T8d's candidate block)? | **Keep.** The run read is a Connector-only audit record that already carries weights and `inputs_hash`; screens stay band-only by type (F1). Availability routes, which Speakers read, carry no numbers. |
| OQ-4 | Re-check Full at compose and dispatch, as T4 does for availability? | **Not in T8d.** Parent Q4 covers availability only, and Full is a run-time Stage A rule. Card it if the owner wants a Speaker who became Full after the run refused at compose. |
| OQ-5 | Add "changed since this run" for the band, and a deep link from the gap list to one event? | **Neither in T8d.** A load band drifts daily as the window slides (noisy) and would add a query to T4's pinned read; the Events page has no `?event=` link today. Two follow-up cards: `B26-FU-LOAD-CHANGED-SINCE`, `B26-FU-EVENT-DEEP-LINK`. |

**Noted for the orchestrator, not changed here:** if T8c's `ExcludedCandidateView.load` ships
`unknown_hours_refs` (T8c §7: "the same shape" as the payload block), a Full Speaker's exclusion carries other
units' `pipeline_record` ids on the Connector run wire, the exposure MED 2 removes from the candidate
block. Recommend T8c's implementer drop the refs from that view too; the stored payload keeps them.

## 13. Out of scope

- An override for Full (parent §5.2 item 7; follow-up card).
- The registry flip and its approval (T8c §13).
- Any change to T8c's load read, scoring, explanation payload or worker.
- Showing any load number, ratio, hours or multiplier on any screen.
- A batched roster-level band (T5 OQ-5).
- Turning `SPEAKER_PORTAL` on.

## 14. Plan-gate findings applied (2026-09-23)

| # | Sev | Finding | Where |
|---|---|---|---|
| 1 | MED | Connector route: `engagement_id` null for `other_unit`; React list keys use the index | §4.1, §4.2 label table, §6.1, §6.2, tests U5, A5, V-B10 |
| 2 | MED | No `unknown_hours_refs` in the candidate view's load block (no cross-unit record ids on the run wire) | §5, test R3; excluded-block note in §12 |
| 3 | MED | Milestone 7 adds a shared `speakerLoadFixture()` to every availability stub in T5 file C and T6b-4 file G | §9.4, §10 row 7 |
| 4 | MED | `PATCH` computes `load` before the commit, from `result`'s capacity (no false 409 on retry) | §4.2, §2 rows 4–5, test A13 |
| 5 | MED | `CandidateLoadBlockView(LoadBlockView)` adds `multiplier` and `composite_before_load`; T8c's excluded schema unchanged | §5, §2 row 6, test R7 |
| 6 | LOW | Connector summary is a `div role="group"` with `aria-labelledby` | §6.3, §8 item 3, test V-B9 |
| 7 | LOW | Digit-free event titles in V-B and V-C fixtures | §9.4, tests V-B6, V-B7, V-C3 |
| 8 | LOW | `now = utc_now()` added to both `GET` handlers | §4.2, §2 rows 4–5, test A14 |
| 9 | LOW | Query cost wording: +1, +1 more with gaps, 2 at most | §4.2 |
| 10 | LOW | Staleness after a booking is confirmed accepted (30 s `staleTime`) | §6.2 |

---

**Next action (under two minutes):** run `git log --oneline -3 origin/feat/b26-t8c origin/feat/b26-t6b-4` to see whether either implementation has started.
