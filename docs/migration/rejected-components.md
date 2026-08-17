# Rejected legacy components

Every legacy component deliberately not carried into the target, with the reason
and the contract it conflicts with. Recorded so the decisions are reviewable and
so nobody re-adds one believing it was merely overlooked.

Legacy baseline: `BrooklynD23/Nebiux-Team-IA-West-SmartMatch` @ `bdce024`.

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
| Demo-fixture fallback in `aggregate_feedback` | Returned fabricated aggregates when no feedback existed |
| Free-text decline reasons mapped to factors by substring match | Unaggregatable, and the source of the noisiest weight suggestions |
| No minimum decision count | The legacy would adjust weights from a single click |

### `data_loader.py` → `smartmatch_domain.ingest` (MM-004)

| Rejected | Why |
|---|---|
| `_try_read_csv`, encoding sniffing, `DATA_DIR` | Filesystem coupling; the domain does not read files |
| pandas DataFrame return type | Ties the domain to a specific data library |
| Returning a partial frame when required columns are missing | Let downstream scoring proceed on incomplete data. The import now fails closed. |
| Reporting a present-but-entirely-blank required column as healthy | As unusable as an absent column |

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
