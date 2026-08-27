# Rejected legacy components

Every legacy component deliberately not carried into the target, with the reason
and the contract it conflicts with. Recorded so the decisions are reviewable and
so nobody re-adds one believing it was merely overlooked.

Legacy baseline: `BrooklynD23/Nebiux-Team-IA-West-SmartMatch` @ `bdce024`.

**Corrected 26 August 2026.** Four rows in the MM-005 and MM-004 tables below
asserted things the independent port review
(`docs/migration/port-verification.md`) disproved — findings F-21, F-22, F-12
and the description half of F-23. Corrections are marked inline and the
withdrawn claim is shown struck through rather than deleted, because a rejection
rationale that quietly changes its reason is not a record of a decision. The
corrections restate the review's published evidence; the legacy repository is
not present in this checkout, so nothing here was re-derived from `bdce024`.

---

## Rejected outright

| Component | Reason | Contract conflict | Replacement |
|---|---|---|---|
| `POST /auth/mock-login` (`portals.py:435`) | Caller-selected identity — any caller could choose their own role | v1.1 §1.11, §2.2 | Google Identity Platform token verification; tenant and actor derived server-side |
| `runtime_state.py`, `coordinator/result_bus.py` | Authoritative job state in module-level dicts; invisible across Cloud Run instances and lost on restart | v1.1 §1.6, §2.4 | `job`, `job_event`, `outbox_record` tables with leases and transactional counters |
| `demo_mode.py`, `cache/demo_fixtures/*.json` | Seed content served unlabeled so screens stayed populated | v1.1 §5.5, §3.6 N3 | Fixture providers returning visibly synthetic results; provenance labels on every data element |
| `data/demo.db`, `data/smartmatch.db`, `data/feedback/feedback-log.jsonl` | Business records in repository-local files | v1.1 §3.1, §2.2 | PostgreSQL as sole system of record; `.gitignore` and a CI check prevent recurrence |
| `src/app.py`, `src/ui/**` (20 modules) | Streamlit is not the target frontend | v1.1 §5.1 | React + TypeScript + Vite consuming a generated client (R1) |
| `src/voice/{stt,tts}.py` | Outside target scope; no accepted contract restores voice | v1.1 §1.1 | None planned |
| `src/coordinator/**` (agent orchestration, `nemoclaw_adapter`, in-request stream) | Provider calls in the browser request path; agent state treated as authoritative | v1.1 §1.4, §1.6, gate G3 | Bounded ADK agents inside the worker boundary, R3, behind an eval set and tool allowlist |
| `src/scraping/scraper.py` | Unreviewed crawl orchestration with unrestricted egress | v1.1 §1.5, gate G3 | R3 research pipeline with quarantine, provenance, and a crawler threat model |

## Rejected behaviors within components that were otherwise ported

These are the more instructive cases: the component was worth keeping, but a
specific behavior inside it was not.

### `ics_generator.py` → `smartmatch_domain.ics` (MM-001)

| Rejected | Why |
|---|---|
| `_parse_date` falling back to "30 days from now" | Fabricates a meeting slot nobody chose. v1.1 §3.6 N1 prohibits fabricating a slot. Most legacy events stored recurrence strings ("Every Tuesday"), so this path was the common case, not an edge case. |
| Naive datetimes formatted with a trailing `Z` | Asserts UTC for a value with no timezone, shifting the event by the local offset in every consuming calendar |
| Absence of RFC 5545 §3.1 line folding | Long SUMMARY/DESCRIPTION values produce documents strict parsers reject |

### `matching/factors.py` → `smartmatch_domain.eli` (MM-003)

| Rejected | Why |
|---|---|
| The "fatigue" framing and its labels ("Rest Recommended", "Needs Rest") | Implies a health assessment SmartMatch has no evidence to make. v1.1 §1.3 renames and re-scopes to operational workload only. |
| `days_since_last_assignment` derived from a pipeline `stage_order` column | Invents a number the data never contained, then displays it as fact |
| A single blended score with no separable cap | v1.1 §1.3 requires the hard cap (Stage A) and soft penalty (Stage B) be applied *and reported* separately |
| `geographic_proximity` returning `0.3` for unknown region pairs | A confident-looking default standing in for "unknown". Replaced by route-matrix estimates that report unavailability explicitly. |

### `feedback/acceptance.py` → `smartmatch_domain.feedback` (MM-005)

| Rejected | Why |
|---|---|
| Streamlit imports and `render_*` functions | Presentation inside a domain module |
| `st.session_state` as storage | Not authoritative, not durable, not multi-instance safe |
| `_persist_to_csv` | Business writes to a repository-local file |
| Demo-fixture fallback in `render_feedback_sidebar` (`acceptance.py:299-311`) | Served fabricated aggregates when `demo_mode` was set in session state. **Corrected 26 Aug 2026 (F-22):** this row previously named `aggregate_feedback`. That function (`acceptance.py:186-242`) returns an explicit all-zero dictionary on an empty log and never calls `load_fixture`; the fallback is in the presentation function beside it. The rejection stands; the attribution was wrong. |
| ~~Free-text decline reasons mapped to factors by substring match~~ — **withdrawn 26 Aug 2026 (F-21)** | ~~Unaggregatable, and the source of the noisiest weight suggestions~~ **This legacy defect does not reproduce.** Both legacy mappers use an exact dictionary lookup on a closed reason list — `acceptance.py:263` (`reason in REASON_TO_FACTOR`) and `service.py:213` (`DECLINE_REASON_TO_FACTOR.get(reason)`) — and an exhaustive search of the legacy `src/` tree for case-folding, `startswith`, `endswith` or containment tests against a reason or note field returns only those two lines. The one free-text field, `decline_notes`, is never mapped to a factor; it is stored and displayed only. The closed-enum design is still right, but its justification is elsewhere: the legacy held *two* reason-to-factor maps that disagree with each other on "Speaker already committed" (`historical_conversion` in `acceptance.py`, `volunteer_fatigue` in `service.py`), so there was no single mapping to carry forward. See MM-005 `behavior_replaced`. |
| No minimum decline count **per implicated factor** | The legacy would adjust weights from a single click. **Corrected 26 Aug 2026 (F-23):** this row previously said "minimum decision count", and so did the control — it counted *total decisions*, so four unrelated accepts plus one decline still moved a weight off one decline. `MIN_DECISIONS_FOR_PROPOSAL` is now `MIN_DECLINES_PER_FACTOR` (`8c47c2e`) and counts declines implicating each factor. Value unchanged at 5. |
| The per-factor clamp into a band around baseline, and the whole-vector renormalization, both in `service.py` | Dropped by the port. **Added 26 Aug 2026 (F-20/F-25):** an unrecorded loss until now. Whether dropping them is right is not settled — it is why the weight proposal is un-normalized, which is open finding F-25, sequenced to the M1/M8 consumer behind gate G1. |

### `data_loader.py` → `smartmatch_domain.ingest` (MM-004)

| Rejected | Why |
|---|---|
| `_try_read_csv`, encoding sniffing, `DATA_DIR` | Filesystem coupling; the domain does not read files |
| pandas DataFrame return type | Ties the domain to a specific data library |
| Returning a partial frame when required columns are missing | Let downstream scoring proceed on incomplete data. The import now fails closed. |
| Reporting a present-but-entirely-blank required column as **healthy for whitespace-only values** | As unusable as an absent column. **Corrected 26 Aug 2026 (F-12):** this row previously said the legacy reported *any* entirely-blank required column as healthy. It did not. The legacy had a nullability check (`if not col_spec["nullable"] and null_count > 0`) with the required columns declared `nullable: False`; re-executed under pandas 3.0.5 it raised a data-quality issue for empty CSV fields and for literal `nan` text, and reported healthy only for whitespace-only values. What the port adds is escalating that issue to a blocking error and catching the whitespace-only case — a good change, and a smaller one than this row claimed. Note also that the blank-marker rule is now caller-declared via `blank_sentinels` rather than built in (`8c47c2e`, F-16). |
| Per-column `null_counts`, per-column dtype validation (`str` / `int` / `datetime`), and the per-column `nullable` check | **Added 26 Aug 2026 (F-11):** an unrecorded loss. None of the three survives in `smartmatch_domain.ingest`, and no manifest field mentioned dropping them. Whether dropping the dtype validation was intended is recorded as an open decision on MM-004, not rationalized after the fact — there is currently no type gate anywhere between this module and the scoring path. |

---

## Deliberately not scaffolded

Not rejections of legacy code — architectural components v1.1 defers, with the
objective trigger that would introduce each (v1.1 §3.5).

| Component | Adoption trigger |
|---|---|
| Memorystore Redis | Measured PostgreSQL contention or limiter throughput that cannot meet SLO after tuning |
| Pub/Sub | One event genuinely needs multiple independent subscribers or replay fan-out |
| BigQuery | Analytics load interferes with operations, and a governed analytics owner exists |
| Direct Calendar API | Approved authorization model, owner, scopes, credential lifecycle, revocation, audit (gate G5) |
| Temporal | Many multi-day workflows with timers, signals, and compensation prove outbox + Cloud Tasks insufficient |
| Autonomous agents | Bounded use case with eval set, tool allowlist, cost controls, and human authorization (gate G3) |

**OpenClaw** was evaluated and rejected as a production foundation (v1.1 §1.4):
v0.1 scaffolds with minimal history. The one idea worth borrowing — canonical
hashable agent evidence — is already provided by the accountability trace design
in v1.1 §2.5.
