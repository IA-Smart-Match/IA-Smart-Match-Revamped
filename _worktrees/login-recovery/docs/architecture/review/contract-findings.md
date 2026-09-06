# Architecture contract review — findings

**Contract reviewed:** SmartMatch Architecture v1.1, 17 August 2026
**Legacy baseline:** `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42` (verified present; HEAD of legacy `main`)
**Reviewed:** 17 August 2026
**Severity vocabulary:** `BLOCKER` · `REQUIRED_BEFORE_LIVE` · `DEFERRED_WITH_TRIGGER` · `DOCUMENTATION`

---

## Summary

The v1.1 contract set is internally consistent on every structural decision the
scaffold depends on — repository boundaries, data model, authentication,
authorization, and task execution. **No structural blocker prevents scaffolding.**

One blocker affects a single implementation slice (matching), and it originates
in the legacy code rather than in the contract. The contract already anticipates
it: gate G1 blocks R1 on factor-registry approval. This review quantifies the
defect that gate exists to catch.

| ID | Severity | Area | Finding |
|---|---|---|---|
| F-001 | `BLOCKER` (matching slice only) | Matching | Legacy factor registry declares 9 factors but computes 7; scores systematically deflated |
| F-002 | `DOCUMENTATION` | API surface | v1.1 route facts verified correct against the baseline |
| F-003 | `REQUIRED_BEFORE_LIVE` | ICS / Calendar | Legacy ICS fabricates dates, misreports timezones, omits line folding |
| F-004 | `REQUIRED_BEFORE_LIVE` | Consent | Legacy has no state machine preventing scraped contacts from becoming send-eligible |
| F-005 | `DEFERRED_WITH_TRIGGER` | Coordination | Legacy job state lives in process memory; incorrect on multi-instance Cloud Run |
| F-006 | `DOCUMENTATION` | Contract | Eight open decisions carry forward; none blocks Foundation |

---

## F-001 — Legacy factor registry declares nine factors and computes seven

**Severity:** `BLOCKER` for the matching slice. Does not block Foundation.
**Contract reference:** v1.1 §1.2, gate G1, Appendix C item 1.
**Owner:** program owner named in gate G1.

### What v1.1 says

> the factor registry stays versioned and canonical — the 6/8/9 factor
> contradiction must be resolved into **one** registry before any porting (R1 gate).

The contract flags this as a contradiction to resolve. It is more than that.

### Measured evidence

At `bdce024`:

| Source | Claim |
|---|---|
| `src/config.py:97` `FACTOR_REGISTRY` | **9** factors, `default_weight` summing to exactly 1.00 |
| `src/matching/engine.py:109` `compute_match_score` | computes **7** factor scores |
| `README.md:229` | describes "8-factor matching" |

The two declared-but-never-computed factors are `event_urgency` (0.05) and
`coverage_diversity` (0.05).

### Why this is a defect, not a naming inconsistency

`engine._normalize_weights` (line 53) normalizes across **all nine** `FACTOR_KEYS`:

```python
raw_weights = dict(weights) if weights is not None else get_effective_weights()
weight_sum = sum(raw_weights.values())
return {factor: raw_weights.get(factor, 0.0) / weight_sum for factor in FACTOR_KEYS}
```

`compute_match_score` then sums `weighted_factor_scores` over only the **seven**
factors it computed (line 140). The weight mass allocated to the two
unimplemented factors is simply lost.

**Consequence: the maximum attainable `total_score` is 0.90, not 1.00.** Every
match score the demo produced was deflated by up to 10%, and no relative ranking
guarantee survives either, because the deflation is uniform only when both
missing factors would have scored identically for every candidate.

### Required action

1. Program owner approves the canonical registry contents (gate G1).
2. A golden case set is agreed **before** any scoring port — characterization
   against the legacy is impossible here, because pinning the legacy's outputs
   would enshrine the defect.
3. Only then does MM-002 move off `blocked_contract`.

### What the target does in the meantime

`smartmatch_domain.factor_registry` records the resolved proposal with
`REGISTRY_STATUS = "proposed"`, and `assert_registry_approved()` raises until an
owner flips it in a reviewed commit. `normalize_weights()` ranges over exactly
the implemented scoring factors, so numerator and denominator agree and the sum
is 1.0 by construction — asserted by
`tests/unit/test_factor_registry.py::test_implemented_scoring_weights_sum_to_one`.

---

## F-002 — v1.1 route facts verified correct

**Severity:** `DOCUMENTATION`.
**Contract reference:** v1.1 §1.11.

v1.1 asserts specific baseline facts. The orchestrator contract requires these be
reconciled mechanically rather than trusted. They were, by counting route
decorators at `bdce024`:

| File | v1.1 claims | Measured |
|---|---|---|
| `portals.py` | 15 | 15 |
| `data.py` | 7 | 7 |
| `crawler.py` | 5 | 5 |
| `qr.py` | 5 | 5 |
| `outreach.py` | 4 | 4 |
| `matching.py` | 3 | 3 |
| `calendar.py` | 2 | 2 |
| `feedback.py` | 2 | 2 |
| `main.py` (`/api/health`) | 1 | 1 |
| **Total** | **44** | **44** |

`POST /auth/mock-login` is at `src/api/routers/portals.py:435`, exactly as v1.1
states.

**Conclusion:** the contract's evidence labels are trustworthy. This matters
beyond the count itself — it is the basis for treating v1.1's other observed
claims as reliable without re-deriving each one.

---

## F-003 — Legacy ICS generation fabricates dates and misreports timezones

**Severity:** `REQUIRED_BEFORE_LIVE`. Resolved in the port (MM-001).
**Contract reference:** v1.1 §3.1, §3.6 (N1), gate G5.

`src/outreach/ics_generator.py` at `bdce024`:

1. **Fabricated slots.** `_parse_date` returns `datetime.now(UTC) + timedelta(days=30)`
   for any unparseable input, including the recurrence strings the legacy stored
   for most events ("Every Tuesday", "Monthly"). The generated invite is
   confident and entirely invented. v1.1 §3.6 N1 prohibits fabricating a slot.
2. **False UTC.** Parsed dates are naive (`strptime` with no tzinfo), then
   formatted `"%Y%m%dT%H%M%SZ"`. A 09:00 Pacific event is emitted as `T090000Z`,
   moving it by seven or eight hours in every consuming calendar.
3. **No line folding.** RFC 5545 §3.1 caps content lines at 75 octets. Long
   SUMMARY or DESCRIPTION values produce documents strict parsers reject.

All three are fixed in `smartmatch_domain.ics` with golden tests that fail
against the legacy implementation. ICS remains the only supported calendar
artifact until gate G5 approves a Calendar authorization model.

---

## F-004 — No structural barrier between research evidence and send eligibility

**Severity:** `REQUIRED_BEFORE_LIVE`. Addressed by `smartmatch_domain.consent`.
**Contract reference:** v1.1 §2.3, §1.8.

The legacy has no contact-confidence lifecycle. A contact discovered by the
crawler and one who opted in are the same kind of record, distinguished only by
convention. Nothing prevents a scraped address reaching an outreach draft.

v1.1 §2.3 requires that no transition reach `recipient` except through
`consented`, and that `consented` require an approved consent source. The target
encodes this as a state machine with `ConsentSource.SCRAPED`, `PURCHASED`, and
`INFERRED` present in the enum specifically so their rejection is explicit and
testable. `tests/unit/test_consent.py` asserts the graph property directly: the
only predecessor of `ACTIVE_CANDIDATE` is `CONSENTED`.

This is a Resend acceptable-use-policy compliance requirement, not only a design
preference.

---

## F-005 — Legacy coordination state is process-local

**Severity:** `DEFERRED_WITH_TRIGGER` — the trigger has already fired (multi-instance Cloud Run is the target topology).
**Contract reference:** v1.1 §1.6, §2.4.

`src/runtime_state.py` and `src/coordinator/result_bus.py` hold job and result
state in module-level dictionaries. On a single Streamlit process this works. On
Cloud Run it does not: a job written by one instance is invisible to another, and
an instance recycle loses it.

v1.1 §2.4 replaces this with `job`, `job_event`, `outbox_record`, and
`redrive_record` in PostgreSQL, with `job_event.sequence` serving SSE reconnect
and transactional counters serving budget and concurrency. The Foundation schema
implements these tables; the dispatcher itself is R1 work.

---

## F-006 — Open decisions carried forward

**Severity:** `DOCUMENTATION`. None blocks Foundation.

v1.1 Appendix C lists eight open decisions. Their effect on the scaffold:

| # | Decision | Blocks | Foundation impact |
|---|---|---|---|
| 1 | Factor registry contents and approval authority | R1 | Registry committed as proposal; scoring fails closed |
| 2 | ELI formula parameters and default caps | R1 tuning | Proposed defaults documented as proposed in `eli.py` |
| 3 | Consent-origin policy and pilot recipient list | R4 | Lifecycle encoded; no send path exists |
| 4 | Calendar authorization model | direct Calendar API | ICS only; no Calendar adapter scaffolded |
| 5 | Retention periods per evidence table | R2 | No evidence tables in Foundation |
| 6 | Route-matrix provider terms and call budget | R1 travel factor | `travel_burden` proposed, unimplemented, zero active weight |
| 7 | Agent framework confirmation and R3 eval dataset | R3 | No agent code scaffolded |
| 8 | Domain registration and DNS control | all mail work | ICS UID uses a `.invalid` namespace rather than implying a real domain |

Two contract-internal points worth recording, neither blocking:

- **Retention numbers are placeholders.** v1.1 §2.5 correctly relabels the v1.0
  figures (3 years, 90-day redaction) as proposed defaults awaiting
  privacy/legal/records sign-off. Nothing should cite them as decided.
- **Rate limits are hypotheses.** v1.1 §3.4 says so explicitly ("still hypotheses
  to be tuned with recorded evidence"). The Foundation scaffold implements no
  limiter, so there is nothing to encode prematurely.

---

## Cross-document consistency checks

The orchestrator contract §5 names thirteen checks. Results:

| Check | Result |
|---|---|
| Topology vs sequence diagrams | Consistent — §3.1 removes Redis/Pub-Sub/BigQuery, and §1.6 correspondingly uses Postgres `job_event` for SSE cursors |
| Sequence diagrams vs state machines | Consistent — §1.6 dispatch sequence matches the §1.7 `queued → dispatched → running` path |
| ERD vs authorization scope | Consistent — §2.2 `MEMBERSHIP.granted_path` and `RESOURCE_GRANT` match the §2.1 combination semantics |
| ERD vs OpenAPI payloads | Not yet applicable — no feature routes in Foundation |
| API mutations vs idempotency | Consistent — §1.11 requires idempotency-key scope; `idempotency_record` implements per-tenant, per-command-type scoping |
| Job topology vs failure/re-drive | Consistent — §1.7 `redrive_pending` matches §1.6's "no native DLQ" reasoning |
| Outreach flow vs consent and provider policy | Consistent — §1.8's five gates and §2.3's lifecycle agree; both reject the circular opt-in |
| QR flow vs multi-use semantics | Consistent — §1.9 reusable token with idempotent unique constraint |
| Unsubscribe vs GET/POST semantics | Consistent — §1.10 fixes the v1.0 mutating GET |
| Classroom topology vs credential and egress controls | Consistent — §3.3 lists five mechanisms; the scaffold implements the configuration-validation one and asserts it in tests |
| Deployment rollback vs migration policy | Consistent — §4.2 expand/migrate/contract makes rollback independent of reversing a destructive step |
| Evidence immutability vs retention lifecycle | Consistent — §2.5 resolves the v1.0 tension by permitting a privileged, independently logged lifecycle process |
| Milestone plan vs prerequisites | Consistent — §4.3 gates G1–G5 each name a non-engineering owner |

**No contradiction found between accepted contracts.** F-001 is a
contract-versus-legacy conflict, which §4 of the orchestrator contract resolves
in the contract's favour.

---

## Scaffold gate

**Result: PASS.**

No unresolved architecture blocker affects repository boundaries, the data
model, authentication, authorization, task execution, or any ported domain
behavior. F-001 blocks exactly one implementation slice (matching), which is
recorded as `blocked_contract` in the migration manifest and excluded from the
port batch.
