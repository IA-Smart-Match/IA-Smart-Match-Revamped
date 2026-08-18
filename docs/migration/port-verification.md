# Port verification review — MM-001, MM-003, MM-004, MM-005

**Review date:** 18 August 2026
**Reviewer:** A4 (independent review agent)
**Target:** `BrooklynD23/IA-Smart-Match-Revamped` @ `claude/smart-match-v1-migration-sp1t49`
**Legacy baseline:** `bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42` (read-only; unmodified — see the integrity statement)

This review exists because §6 of the migration orchestrator contract forbids an
agent from approving its own port. The four entries below were written by
another agent and had `reviewer: pending`. Nothing here was taken from the
manifest's description of itself: every claim was checked against the legacy
source and the target source side by side, and the load-bearing ones were
executed.

**Outcome: one of four entries reaches `verified`.**

| Entry | Component | Verdict | Manifest status set |
|---|---|---|---|
| MM-001 | `ics_generator.py` → `smartmatch_domain.ics` | **verified with findings** | `verified` |
| MM-003 | `matching/factors.py` → `smartmatch_domain.eli` | **rejected** | `ported_unverified` |
| MM-004 | `data_loader.py` → `smartmatch_domain.ingest` | **rejected** | `ported_unverified` |
| MM-005 | `feedback/acceptance.py` → `smartmatch_domain.feedback` | **rejected** | `ported_unverified` |

"Rejected" here means *this review does not approve the entry as verified*. It
is not a recommendation to discard the port. In every case the ported code is
substantially better than the legacy it replaces; what fails is the accuracy of
the manifest entry that describes it, and in MM-003's case a defect in a safety
control. The remedy for all three is a manifest correction and a small number of
code fixes, not a rewrite.

---

## Scope and method

**What this is.** A review of source as committed on the named branch. Nothing
is deployed; no runtime, no database contents, and no provider behavior were
examined, because none exist to examine.

**What was compared.** For each entry, the legacy file named in `legacy_path`
was read in full alongside the target module and the target test file. Where the
manifest named a symbol, the symbol was located and read. Where the manifest
made a claim about legacy behavior, the legacy behavior was executed rather than
inferred wherever it was possible to execute it.

**What was executed.**

| Action | Detail |
|---|---|
| Full target suite | `.venv/bin/pytest tests/ -p no:warnings` |
| The four entries' tests | 62 passed (15 + 18 + 13 + 16) |
| Legacy ICS reproduction | Legacy `ics_generator.py` copied to `/tmp` and driven with the target's golden cases |
| ICS fold fuzz | 4 000 random Unicode payloads plus exhaustive 4-byte-codepoint boundary offsets |
| ELI boundary probes | Window edges, cap rounding, blackout, modifier typing, degenerate capacity |
| Feedback control probes | Four separate attempts to defeat `WeightProposal.requires_approval`; decision-floor truth table |
| Ingest rule probes | Blank forms, ragged rows, header collisions |
| Legacy blank-column comparison | Legacy `_validate_columns` null logic re-executed under pandas 3.0.5 in a throwaway `/tmp` virtualenv |
| Dependency greps | pandas, streamlit, numpy, pathlib, `open(`, clock reads, module-level mutable state across all four modules |
| Import boundary | `lint-imports` — 4 contracts kept, 0 broken |

Nothing was written into either repository except this file and the four
manifest fields the reviewer is permitted to set. No defect found here was
fixed; all are reported.

---

## MM-001 — `smartmatch_domain.ics` · **verified with findings**

### 1. Are the `behavior_retained` claims true of the target code?

Yes, all seven, each with a corresponding test that fails if the behavior is
removed.

| Claim | Where it lives | Test |
|---|---|---|
| Pure string building, no external library | `ics.py` imports only `hashlib`, `dataclasses`, `datetime`, `typing` | import-linter contract |
| VCALENDAR / VEVENT envelope | `generate_ics` line list | `test_document_structure_matches_legacy_shape` |
| Deterministic UID | `_derive_uid` — SHA-256 over name + start instant | `test_uid_is_deterministic_for_identical_input`, `..._differs_for_different_events` |
| CRLF endings | `"".join(f"{...}\r\n" ...)` | `test_crlf_line_endings_preserved` |
| TEXT escaping of `\`, `;`, `,`, newline | `_escape_text`, backslash first | `test_text_escaping_matches_rfc5545` |
| Optional fields omitted when absent | `if invite.location is not None:` | `test_optional_fields_omitted_when_absent` |
| One-hour default duration | `invite.starts_at + timedelta(hours=1)` | `test_default_duration_is_one_hour` |

The port also fixes a fourth defect the manifest does not claim: the legacy
`_escape_ics_text` did not handle carriage returns, leaving a bare CR inside a
TEXT value and breaking the line structure. Observed directly:

```
legacy _escape_ics_text('a\r\nb') -> 'a\r\\nb'      <- bare CR survives into the document
target _escape_text('a\r\nb')     -> 'a\\nb'
```

### 2. Do the three claimed legacy defects reproduce?

This is the strongest claim in the manifest, so it was tested directly rather
than read. The legacy module was copied to `/tmp` (byte-compilation disabled so
the legacy tree could not be touched) and driven with the behavior the target's
golden cases encode.

```
### DEFECT 1: unparseable date fabricates a slot
Could not parse date 'Every Tuesday', using 30-day default
  legacy generate_ics('Talk', 'Every Tuesday') -> DTSTART:20260917T134527Z
  today is 20260818 -> fabricated ~30d out; NO exception raised

### DEFECT 2: naive datetime formatted with trailing Z (false UTC claim)
  legacy: DTSTART:20260915T170000Z
  legacy: DTEND:20260915T180000Z
  _parse_date('2026-09-15T17:00:00') tzinfo = None
  -> a tz-NAIVE value emitted as ...Z  [REPRODUCED]

### DEFECT 2b: non-UTC input is relabeled, not converted
  legacy generate_ics('Careers Panel', '2026-09-15') -> DTSTART:20260915T000000Z

### DEFECT 3: no RFC 5545 line folding
  lines exceeding 75 octets: [('SUMMARY:AAAAAAAAAAAA...', 208)]
  utf-8 summary line octets: 208 (unfolded)
```

All three reproduce. The manifest's claim is substantiated.

`docs/migration/rejected-components.md` makes a stronger sub-claim about defect
1 — that the fabrication path "was the common case, not an edge case." That was
also checked. `src/ui/match_engine_page.py:216` falls back to the
`Recurrence (typical)` column for `date_str`, and every value in that column of
the legacy events dataset is an unparseable recurrence string:

```
  date_str='Annual'                         -> DTSTART:20260917T134906Z
  date_str='Ongoing series + pitch events'  -> DTSTART:20260917T134906Z
  date_str='Recurring each term/year'       -> DTSTART:20260917T134906Z
  date_str='Annual (often spring)'          -> DTSTART:20260917T134906Z
  date_str='2026-04-16'                     -> DTSTART:20260416T000000Z
```

Distinct values of that column, whole file: `Annual` ×6, `Ongoing series + pitch
events` ×2, `Ongoing` ×2, `Recurring each term/year`, `Recurring (varies by
year)`, `Recurring`, `Annual (often summer)`, `Annual (often spring)`. Not one
is parseable. The sub-claim holds.

### 3. Do the target tests test what they claim?

Counts match the manifest exactly: 7 preserved-behavior cases, 8
corrected-behavior cases, 15 total. All pass.

One weak test, recorded as **F-2**: `test_unparseable_date_raises_instead_of_
fabricating_a_slot` passes the string `"Every Tuesday"` into the `starts_at`
field and asserts a type rejection. It exercises no date-parsing logic, because
the target has none — the fabrication is impossible by construction rather than
prevented by a check. The test is not wrong, and the property it stands for is
real and stronger than a runtime check, but the test would pass against any
implementation that type-checks its input and proves nothing about parsing.

The folding tests were checked for adequacy by independent fuzzing rather than
trusted:

```
### fold fuzz: 4000 random unicode payloads, octet bound + exact round-trip
  violations: 0
### 4-byte codepoint straddling the boundary exactly
  pad=0..7: roundtrip+bound ok=True   (all eight offsets)
```

`_fold_line` is correct. It walks back off UTF-8 continuation bytes before
cutting, charges the continuation line's leading space against the 75-octet
budget (`limit = _MAX_LINE_OCTETS - 1`), and unfolds to exactly the input. It
does not split multi-byte codepoints, including 4-byte ones landing on the
boundary from every offset.

### 4. Are the `dependencies_removed` genuinely gone?

Module-level logger: gone. Implicit clock reads: **partly** — recorded as
**F-3**. `generate_ics` still reads the clock when `generated_at` is omitted:

```
'datetime.now(UTC)' present in generate_ics body: True
DTSTAMP with generated_at omitted: DTSTAMP:20260818T134552Z
```

The read is now injectable and every test injects, which is the substance of the
improvement. But `dependencies_removed: ["implicit clock reads"]` describes a
removal that did not happen, and no test covers the default branch.

### 5. Does the target introduce a new defect?

Yes, one — **F-1**, the most significant finding in this review.

```
BEGIN:VCALENDAR | VERSION:2.0 | PRODID:-//IA West SmartMatch//Event Invite//EN |
CALSCALE:GREGORIAN | METHOD:REQUEST | BEGIN:VEVENT | UID:...@smartmatch.invalid |
DTSTAMP:... | DTSTART:... | DTEND:... | SUMMARY:Careers Panel | STATUS:CONFIRMED |
END:VEVENT | END:VCALENDAR
  has METHOD:REQUEST : True
  has ORGANIZER      : False
  has ATTENDEE       : False
```

The port adds `METHOD:REQUEST`, which the legacy did not emit. RFC 5546 §3.2.2
makes `ORGANIZER` and at least one `ATTENDEE` mandatory properties of a VEVENT
carried under the REQUEST method. The document has neither. This is a
conformance defect in the same family as the one defect 3 exists to fix, and it
is new: the legacy, having no `METHOD`, could not have it.

RFC 5545 alone — which is what the module's docstring claims — is still
satisfied; `METHOD` is a valid VCALENDAR property and 5545 does not require an
organizer. The practical exposure is iTIP-aware clients, principally
Exchange/Outlook, which route a REQUEST as a meeting invitation and have no
organizer to attribute it to.

No test catches this. `test_document_structure_matches_legacy_shape` asserts the
envelope is "unchanged from the legacy output" but checks only
`BEGIN:VCALENDAR`, `VERSION`, `CALSCALE`, `BEGIN:VEVENT`, `END:VEVENT`,
`END:VCALENDAR` — so the added `METHOD`, the added `STATUS`, and the changed
`PRODID` all pass under a test whose docstring says they did not change.

### 6. Is the `security_review` line defensible?

Yes. No IO, no network, no secrets — confirmed by grep and by the import-linter
contract "Domain is pure — no frameworks, storage, providers, IO, or env"
(KEPT). The UID namespace is `smartmatch.invalid`, an RFC 2606 reserved TLD, as
claimed.

### 7. Are `contract_refs` and `data_provenance` consistent?

`data_provenance: no data; pure string generation` — accurate. `contract_refs`
could not be verified; see *What could not be verified*.

### Verdict

**Verified with findings.** Every claim the manifest makes about MM-001 is true,
and the strongest of them was demonstrated by execution rather than accepted.
F-1 is a real defect and should be fixed, but it falsifies no manifest claim and
is a one-property change. This was a judgement call at the boundary — an
orchestrator that reads "fixes three defects, introduces one" as automatically
disqualifying should downgrade this entry to `ported_unverified`; the evidence
for doing so is F-1 above.

---

## MM-003 — `smartmatch_domain.eli` · **rejected**

### 1. `behavior_retained`

The claim is: "recent assignment pressure, travel burden, and event cadence
combined into a bounded score, with recency weighting."

| Element | In the target? |
|---|---|
| Recent assignment pressure | Yes — engagements inside the 90-day window |
| Travel burden | Yes — `EngagementRecord.travel_hours` |
| Bounded score | Yes — `min(100.0, ...)` |
| Recency weighting | Yes — `_decay_weight`, 45-day half-life |
| **Event cadence** | **No** |

**F-4.** There is no event-cadence input. ELI is computed per professional from
that professional's own engagement history; the function has no parameter
carrying the event under consideration and therefore no way to express its
cadence. The legacy's `_recurrence_pressure` mapped a recurrence string to a
pressure value and weighted it at 0.20 of the blend; nothing corresponds to it.
The `CONSECUTIVE_WEEKENDS` / `BACK_TO_BACK` / `AT_DECLARED_FREQUENCY` modifiers
are cadence-*flavored*, but they are caller-supplied booleans, not a computed
cadence, and the manifest lists them nowhere. A claimed retained behavior that
is not implemented is a failed verification.

A second, softer inaccuracy: "with recency weighting" is presented as retained
*shape*. The legacy's `recency_pressure` was `min(deepest_stage / 4.0, 1.0)`,
derived from a pipeline `stage_order` column — it was not a function of time at
all. Genuine time-based recency decay is something the port **introduced**, and
it deserves credit under a heading other than "retained."

### 2. `behavior_rejected`

All four claims check out against the legacy source, and all four are absent
from the target.

| Claimed legacy defect | Confirmed at |
|---|---|
| Health framing and its labels | `_recovery_status_from_fatigue` returns `"Rest Recommended"` / `"Needs Rest"` / `"Available"` |
| `stage_order` → `days_since_last_assignment` | `days_since_last_assignment = int(round((1.0 - recency_pressure) * 30))`, where `recency_pressure` comes from the `stage_order` column — a pipeline stage number rendered as a count of days |
| Single blended score with no separable cap | `fatigue_pressure = 0.30*a + 0.30*b + 0.20*c + 0.20*d`, one number, no cap |
| pandas DataFrame coupling | `_coerce_pipeline_rows` returns `pd.DataFrame`; the signature takes `ia_event_calendar: pd.DataFrame` |

Target: `evaluate_cap` (Stage A) and `load_penalty` (Stage B) are separate
functions returning separate values; no health vocabulary anywhere; no pandas.
This half of the entry is accurate.

### 3. Do the target tests test what they claim?

**F-5.** The manifest says `tests/unit/test_eli.py (20 cases)`. There are 18.

```
tests/unit/test_eli.py: 18
```

More substantively, `test_manual_blackout_wins_over_spare_capacity` asserts
`snapshot.utilization == 0.0` and the cap decision — deliberately checking the
quantity that is unaffected, while the quantity that *is* affected goes
unasserted. See F-7.

### 4. `dependencies_removed`

Genuinely gone: pandas, `src.config` constants, `geographic_proximity`. `eli.py`
imports only `math`, `dataclasses`, `datetime`, `enum`, `typing`. No filesystem
access, no module-level mutable state, no clock read (`as_of` is a required
input — this module gets the injection right where `ics.py` does not). This
claim is fully satisfied.

### 5. New defects

**F-6 — the Stage A hard cap boundary is decided by a display rounding.**
`compute_eli` stores `utilization=round(utilization, 4)`; `evaluate_cap` then
tests the *rounded* value with `> 1.0`.

```
    40.0000h/40h -> utilization stored=1.0      evaluate_cap=within_cap
    40.0001h/40h -> utilization stored=1.0      evaluate_cap=within_cap
    40.0020h/40h -> utilization stored=1.0001   evaluate_cap=over_cap
    40.0100h/40h -> utilization stored=1.0002   evaluate_cap=over_cap
    41.0000h/40h -> utilization stored=1.025    evaluate_cap=over_cap
```

A professional between 100.000 % and 100.005 % of their declared capacity is
reported `WITHIN_CAP`. The window is narrow, but this is an eligibility
constraint that architecture v1.1 §1.3 describes as hard and overridable only
with an authorized, expiring override, and its threshold is currently set by a
rounding applied for readability. The unrounded value should decide, or the
rounding should be applied at render time only.

**F-7 — `MANUAL_BLACKOUT` inflates the measured load score.** A blackout is
documented in `CapDecision` as "the professional's or coordinator's explicit
instruction," and the test name says it is "an instruction, not a load
judgement." It is nevertheless counted in `modifier_points`:

```
  idle professional with only a blackout: score = 4.0  utilization = 0.0  penalty = 0.0016
```

An idle professional acquires four points of *measured workload* and a non-zero
Stage B utility penalty because someone marked them unavailable. Both numbers
feed the coordinator-facing explanation.

**F-8 — `LoadInputs` performs no type coercion, and the modifier count is taken
from the raw sequence.**

```
  modifiers=[BACK_TO_BACK]*6 (a list) -> score = 20.0  snapshot.modifiers = {LoadModifier.BACK_TO_BACK}
```

`compute_eli` scores `len(inputs.modifiers)` but the snapshot reports
`frozenset(inputs.modifiers)`. A caller passing a list — which the dataclass
accepts silently, `frozenset` being only a type annotation — gets a score of 20
alongside an explanation naming one modifier. The explanation contradicts the
score it explains. This also bears directly on the `security_review` claim; see
question 6.

**F-9 (low) — future-dated engagements are silently dropped.**
`EngagementRecord` is documented as "one completed **or committed**
engagement," but `compute_eli` skips `record.occurred_on > inputs.as_of`. A
commitment for next week contributes nothing to the load that is meant to
prevent over-commitment. No test covers the branch.

Also noted, not raised as findings: the rolling window includes day 90 exactly
(`occurred_on < window_start` is the exclusion test), so the window is 91 days
inclusive against a constant named `_ROLLING_WINDOW_DAYS = 90`; and
`declared_capacity_hours=1e-9` passes validation and yields
`utilization = 1000000000.0`. Empty input, zero-hour engagements, and
division-by-zero surfaces are all handled correctly — `declared_capacity_hours
<= 0.0` is rejected at construction with a good message.

### 6. `security_review`

"Closed input structure (LoadInputs) means a prohibited field cannot reach the
computation." Structurally true: `LoadInputs` has fixed fields, no `**kwargs`,
and `compute_eli` reads no attribute dynamically. But F-8 shows the structure
enforces *shape*, not *type* — it validates `declared_capacity_hours` and
nothing else. "Closed" is doing more work in that sentence than the code does.

"Prohibited-input list asserted in `tests/unit/test_factor_registry.py`" — that
file does assert `PROHIBITED_INPUTS` contains `age`, `health_inference`, and
`protected_characteristic`, and that no factor key collides with the set. It
asserts nothing about ELI's inputs. The claim is literally true and materially
thinner than it reads.

**F-10.** `eli.py`'s own module docstring makes a stronger and false version of
the same claim: the prohibited-input list is "enforced by the registry schema
and by `tests/unit/test_eli.py`, not by convention." `tests/unit/test_eli.py`
contains zero references to prohibited inputs:

```
0 matches for PROHIBITED in tests/unit/test_eli.py
```

### 7. `contract_refs` and `data_provenance`

`data_provenance: operational workload facts only` is consistent with
`LoadInputs`. "prohibited-input list enforced by schema" overstates, per F-10.
`contract_refs` could not be verified.

### Verdict

**Rejected.** A `behavior_retained` element that is not implemented (F-4), a
test count that does not match (F-5), and a defect in the arithmetic of a hard
eligibility control (F-6) together exceed what "verified" should cover. The
module is a clear improvement on what it replaces and the `behavior_rejected`
half of the entry is entirely accurate; it needs a corrected manifest entry and
three small code fixes.

---

## MM-004 — `smartmatch_domain.ingest` · **rejected**

### 1. `behavior_retained`

Accurate. Column validation against a required set: `validate_columns`.
Accumulating rather than stopping at the first problem: `findings` is appended to
through the function and returned whole — verified by
`test_all_missing_columns_are_reported_at_once` and
`test_findings_accumulate_across_categories`. Quality reported separately from
the data: `DatasetQuality` carries no rows.

**F-11 (unclaimed loss).** The legacy `_validate_columns` also produced
per-column `null_counts`, per-column dtype validation (`str` / `int` /
`datetime`), and a per-column `nullable` check. None of this survives, and the
manifest's `behavior_rejected` does not mention dropping any of it. Behavior can
legitimately be dropped, but it has to be recorded — an unlisted loss is exactly
what the manifest exists to prevent.

### 2. `behavior_rejected`

The filesystem claims are all true and all satisfied: `_try_read_csv`, encoding
sniffing, `DATA_DIR`, and the DataFrame return type are confirmed present in the
legacy and confirmed absent from the target, which imports only
`collections.abc`, `dataclasses`, and `enum`.

"Returning a partially-populated frame when required columns were missing and
letting downstream scoring proceed" is true of the legacy: `load_speakers`
returns `(df, quality)` unconditionally and nothing consults `quality`.

**F-12.** The added-behavior claim is inaccurate: *"a required column present but
blank in every row is an error, which the legacy reported as healthy."* The
legacy had a nullability check —
`if not col_spec["nullable"] and null_count > 0` — and the required columns are
declared `nullable: False`. Re-executed under pandas 3.0.5:

```
  empty CSV fields (a real export of a null column)    -> legacy issues: ["Column 'Metro Region' has 2 null(s) but is marked non-nullable"]
  whitespace-only fields                               -> legacy issues: NONE (reported healthy)
  literal 'nan' text                                   -> legacy issues: ["Column 'Metro Region' has 2 null(s) but is marked non-nullable"]
```

The legacy reported it as healthy only for whitespace-only values. For empty
fields — what a CSV export of a null column actually contains — and for literal
`nan` text, it raised a data-quality issue. What the port genuinely adds is
*escalating that issue to a blocking error* and *catching the whitespace-only
case*. That is a good change, and a materially smaller one than the manifest
describes.

### 3. Do the target tests test what they claim?

**F-13.** `characterization_tests: tests/unit/test_ingest.py (column-validation
parity cases)`. There are no parity cases. Nothing in the file references the
legacy, compares against a legacy output, or pins a legacy behavior; every
assertion is written against the target's own design. A characterization test
establishes what the legacy did so a port can be shown not to have changed it,
and none exists. This claim is repeated in
`docs/testing/scaffold-verification.md`, which records "Every reused behavior has
characterization and target tests — **PASS** … MM-004, MM-005."

**F-14.** The manifest says 14 cases. There are 13.

```
tests/unit/test_ingest.py: 13
```

The tests that do exist are sound — none is tautological, none asserts on a
mock, and each would fail against an empty implementation.

### 4. `dependencies_removed`

Fully satisfied. No pandas, no pathlib, no `src.config`, no streamlit caching, no
`open(`, no module-level mutable state. Confirmed by grep and by the
import-linter purity contract.

### 5. New defects

**F-15 — the column set is read from `rows[0]` only, so the verdict depends on
row order.**

```
  row0 lacks metro_region, row1 has it -> ['missing_required_columns'] usable: False
  row0 has it, row1 lacks it           -> clean                        usable: True
```

Two datasets containing identical rows in different order receive opposite
`is_usable` verdicts. Ragged rows are ordinary in real imports (a JSON-lines
export, a spreadsheet where trailing empty cells are dropped, a partial
re-export). The legacy's DataFrame took the union of keys and did not have this
behavior. No test covers it.

**F-16 (low) — `_is_blank` treats the literal strings `null`, `none`, and `nan`
as blank regardless of column semantics.**

```
  metro_region='Null'   -> ['required_column_entirely_blank']
  metro_region='None'   -> ['required_column_entirely_blank']
  metro_region='0'      -> clean
```

`Null` and `None` are real surnames and real place names. A small import whose
only value in a required text column is one of them is rejected as entirely
blank. The rule is centralized and documented, which is the right instinct; it
is applied without regard to what the column holds.

**F-17 (low) — findings report normalized names, not the coordinator's headers.**

```
  source header 'Internal Note!' reported as: ('internal_note',)
```

The message reads "columns present but not part of the import contract" and then
names a string that does not appear in the file being fixed. Related: two headers
that normalize to the same column (`Full Name` and `full_name` in one row) are
accepted silently with one shadowing the other, and duplicate entries in the
`required` argument collapse without notice.

### 6. `security_review`

"no IO; no path handling; cannot be induced to read a file" — defensible and
verified. No filesystem primitive is imported or reachable, and the import-linter
purity contract holds.

One nuance worth recording: "the import now fails closed" describes a *caller*
obligation. `is_usable` is a read-only property; nothing in the module prevents a
caller from ignoring it, and there is presently no caller anywhere in the target
to honour it. The property is the right shape; the guarantee is not yet enforced
by anything.

### 7. `contract_refs` and `data_provenance`

`data_provenance: operates on already-parsed rows; knows nothing of their source`
— accurate and demonstrably so. `contract_refs` could not be verified.

### Verdict

**Rejected.** A `characterization_tests` claim asserting evidence that does not
exist (F-13), an inaccurate description of the added behavior (F-12), an
unrecorded loss of legacy validation (F-11), a count discrepancy (F-14), and an
order-dependence defect (F-15). The module itself is clean, well-tested for what
it does, and a genuine improvement.

---

## MM-005 — `smartmatch_domain.feedback` · **rejected**

### 1. `behavior_retained`

Two of the four claims are false.

**F-18 — "the decline-reason vocabulary" is not retained.** The legacy
`DECLINE_REASONS` is five prose strings. The target is a seven-member enum of
snake_case codes.

```
  legacy acceptance.py reasons (5): ['Too far (geographic distance)', 'Schedule conflict',
                                     'Topic mismatch', 'Speaker already committed', 'Other']
  target reasons (7):               ['wrong_topic', 'wrong_role', 'too_far', 'unavailable',
                                     'overcommitted', 'recently_engaged', 'other']
```

`wrong_role`, `unavailable`, and `recently_engaged` have no legacy antecedent;
`Schedule conflict` and `Speaker already committed` have no target equivalent.
Redesigning the vocabulary is defensible — a closed machine-readable enum is
better than prose — but it is a replacement, and describing it as retained hides
the decision.

**F-19 — "the reason-to-factor mapping" is not retained.**

```
  legacy acceptance.py mapping targets: ['calendar_fit', 'geographic_proximity',
                                         'historical_conversion', 'topic_relevance']
  legacy service.py    mapping targets: ['calendar_fit', 'geographic_proximity', 'role_fit',
                                         'topic_relevance', 'volunteer_fatigue']
  target mapping targets:               ['availability', 'engagement_load', 'repeat_penalty',
                                         'role_fit', 'topic_relevance', 'travel_burden']
  overlap with EITHER legacy mapping:   ['role_fit', 'topic_relevance']
```

Two names of six survive. Also worth recording: the legacy contains *two*
conflicting reason-to-factor maps that disagree on `Speaker already committed`
(`historical_conversion` in `acceptance.py`, `volunteer_fatigue` in
`service.py`). There was no single legacy mapping to carry forward.

**F-20 — provenance gap.** `MAX_FACTOR_DELTA 0.08` and `PER_REASON_BUMP 0.03`
are correctly carried forward, but not from the file the entry names. They are
`src/config.py:125-129`, consumed at `src/feedback/service.py:216` as
`min(OPTIMIZER_MAX_FACTOR_DELTA, OPTIMIZER_REASON_WEIGHT_BUMP * count)` — which
is the exact expression the target reimplements. `src/feedback/acceptance.py`,
the only file the entry's `legacy_path` names, uses a hard-coded
`weight_bump: float = 0.05` and no maximum at all. The port's real legacy source
is a file the manifest does not mention. `src/feedback/service.py` also contained
the parts of this component with the highest review value — file-backed
persistence, weight-history writing, and a re-normalization step the port drops
— and none of it appears in the inventory.

### 2. `behavior_rejected`

The Streamlit, `st.session_state`, and CSV-append claims are all confirmed
against the legacy and all confirmed absent from the target, which imports only
`collections`, `collections.abc`, `dataclasses`, `enum`, `types`, `typing`.
Those three are accurate.

**F-21 — the free-text substring-matching defect does not reproduce.** The
manifest and `docs/migration/rejected-components.md` both name "free-text decline
reasons mapped to factors by substring match" as "the source of the noisiest
weight suggestions." Both legacy mappers use an exact dictionary lookup on a
closed reason list:

- `src/feedback/acceptance.py:263` — `if count >= min_declines_for_suggestion and reason in REASON_TO_FACTOR:`
- `src/feedback/service.py:213` — `factor = DECLINE_REASON_TO_FACTOR.get(reason)`

An exhaustive search of the legacy `src/` tree for case-folding, `startswith`,
`endswith`, or containment tests against a reason or note field returns only
those two exact-lookup lines. The free-text field that does exist,
`decline_notes`, is never mapped to a factor anywhere — it is stored and
displayed only. A claimed legacy defect that does not reproduce is a significant
finding, because it is offered as justification for a design change.

**F-22 — the demo-fixture fallback is misattributed.** The claim is that it lived
"in `aggregate_feedback`, which returned fabricated aggregates when no real
feedback existed." `aggregate_feedback` (`src/feedback/acceptance.py:186-242`)
returns an explicit all-zero dictionary on an empty log and never calls
`load_fixture`. The fixture fallback is in `render_feedback_sidebar`
(`acceptance.py:299-311`), a presentation function, and it fires only when
`demo_mode` is set in session state. The defect is real and rejecting it is
right; the manifest names the wrong function, and
`docs/migration/rejected-components.md` repeats the error.

The `acceptance_rate` claim is accurate. Legacy returns `0.0` for an empty log;
the target returns `None`, and a genuine `0.0` remains distinguishable:

```
  aggregate([]).acceptance_rate      = None
  aggregate(all declines).acceptance = 0.0
```

**F-23 — the minimum-decision floor does not enforce its stated rationale.** The
claim is "a minimum decision floor (5), because the legacy would learn from a
single click." The floor counts *total* decisions, not declines:

```
    0 accepts +  1 decline(s)  total=  1 -> None (no proposal)
    4 accepts +  1 decline(s)  total=  5 -> PROPOSAL {'travel_burden': 0.03}
    0 accepts +  4 decline(s)  total=  4 -> None (no proposal)
    9 accepts +  1 decline(s)  total= 10 -> PROPOSAL {'travel_burden': 0.03}
   99 accepts +  1 decline(s)  total=100 -> PROPOSAL {'travel_burden': 0.03}
```

Four unrelated accepts are enough to unlock a weight movement driven by exactly
one decline. The control is real and worth having; the rationale written beside
it is not what it enforces. No test covers a mixed accept/decline set below the
floor's intent.

### 3. Do the target tests test what they claim?

16 cases, matching the manifest. All pass. Most are good — the immutability test,
the clamping test, and the `OTHER`-maps-to-nothing test all assert real behavior.

**F-24 — one tautological test.** `test_proposal_always_requires_human_approval`
asserts `proposal.requires_approval is True` against a property whose entire body
is `return True`. It would pass against an empty implementation. It is the only
test covering the control the `security_review` line rests on, and it does not
test that control: it never attempts to change the value.

`characterization_tests: tests/unit/test_feedback.py (reason-mapping parity
cases)` — there are none, and per F-18/F-19 there could not be: the target's
vocabulary and mapping do not overlap the legacy's enough for parity to be
expressible.

### 4. `dependencies_removed`

Fully satisfied: no streamlit, no pandas, no pathlib, no json, no `src.demo_mode`,
no filesystem access, no module-level mutable state, no clock read.

### 5. New defects

**F-25 (low) — the per-factor bound does not bound aggregate movement.**

```
  deltas: {'engagement_load': 0.08, 'repeat_penalty': 0.08, 'travel_burden': 0.08,
           'availability': 0.08, 'role_fit': 0.08, 'topic_relevance': 0.08}
  SUM of proposed deltas: 0.48
```

Each delta respects `MAX_FACTOR_DELTA`, which is what the manifest claims and
what `test_every_delta_respects_the_bound` asserts. But weights that must sum to
1 can be asked to move by 0.48 in aggregate, all in the same direction, and the
proposal carries no normalization. The legacy `service.py` clamped each factor
into a band around its baseline and then re-normalized the whole vector; the port
drops both steps. No test asserts anything about the sum.

**F-26 (low) — `match_run_id` is not validated.**

```
  FeedbackEntry(match_run_id='') accepted -> '' - no non-blank check
```

`data_provenance` says decisions are "attributed to a versioned match_run," and
`FeedbackEntry`'s docstring calls the attribution the mechanism by which "a
weight proposal can be traced to the exact model that produced the proposals
being judged." An empty attribution is accepted silently, while the adjacent
`event_name`-equivalent invariants (reason required on decline, forbidden on
accept) are enforced properly.

### 6. Is the `security_review` line defensible?

Mostly yes, and it was tested rather than accepted. The claim is that
`requires_approval` is "a property returning `True`, not a settable field, so no
caller can mark a proposal auto-applicable." Four attempts:

```
  p.requires_approval = False                          -> TypeError (frozen dataclass)
  object.__setattr__(p,'requires_approval',False)      -> AttributeError: property ... has no setter
  WeightProposal(..., requires_approval=False)         -> TypeError: unexpected keyword argument
  dataclasses.replace(p, requires_approval=False)      -> TypeError: unexpected keyword argument
  __slots__: ('deltas','based_on','rationale')   has __dict__: False
```

The control holds against every direct route. `frozen=True` blocks assignment,
`slots=True` removes the `__dict__` that would otherwise absorb it, the property
has no setter, and it is not a constructor field. This is a genuinely structural
control and better than the manifest's one-line description suggests.

**F-27 (low) — it is not final.** A subclass overriding the property produces an
object that satisfies `isinstance(x, WeightProposal)` and reports
`requires_approval == False`:

```
  subclass overriding the property -> requires_approval = False
```

Any consumer typed on `WeightProposal` accepts it. `@typing.final` on the class,
or having consumers check the concrete type, would close this. It is a low-
severity gap — it needs code written to defeat the control on purpose, not an
accident — but "no caller can" is stated more strongly than the code supports.

### 7. `contract_refs` and `data_provenance`

`data_provenance: coordinator decisions only, attributed to a versioned
match_run` — the first half is accurate, the second is weakened by F-26.
`contract_refs` could not be verified.

### Verdict

**Rejected.** Two `behavior_retained` claims are false (F-18, F-19), one claimed
legacy defect does not reproduce (F-21), one is attributed to the wrong function
(F-22), the added control does not enforce its stated rationale (F-23), a
significant legacy source file is missing from the inventory (F-20), and the
`characterization_tests` claim describes evidence that does not and cannot exist.
The module itself is good code with good tests and a real structural control; the
manifest entry describing it is the least accurate of the four.

---

## Findings

Severity is about the manifest's reliability as evidence and about defects in the
target, not about production risk — nothing here is in production.

| # | Severity | Finding | Owner |
|---|---|---|---|
| F-1 | Medium | MM-001 emits `METHOD:REQUEST` with no `ORGANIZER` and no `ATTENDEE`, violating RFC 5546 §3.2.2. New in the port; the legacy emitted no `METHOD`. | engineering |
| F-2 | Low | MM-001's defect-1 golden test asserts a type rejection, not a parsing behavior; it would pass against any type-checking implementation. | engineering |
| F-3 | Low | MM-001 lists "implicit clock reads" as removed; `generate_ics` still calls `datetime.now(UTC)` when `generated_at` is omitted, and no test covers that branch. | migration owner |
| F-4 | **High** | MM-003 claims "event cadence" as retained behavior. No cadence input exists; ELI has no access to the event under consideration. | migration owner |
| F-5 | Low | MM-003 claims 20 test cases; `tests/unit/test_eli.py` has 18. | migration owner |
| F-6 | Medium | MM-003's Stage A hard cap tests a value rounded to 4 dp, so 100.000–100.005 % of declared capacity reports `WITHIN_CAP`. | engineering |
| F-7 | Medium | MM-003 counts `MANUAL_BLACKOUT` in `modifier_points`, giving an idle professional a load score of 4.0 and a non-zero Stage B penalty for a scheduling instruction. | engineering |
| F-8 | Medium | MM-003 scores `len(inputs.modifiers)` on the raw sequence but reports `frozenset(...)`; a list with duplicates yields a score of 20 beside an explanation naming one modifier. Also weakens the "closed input structure" security claim. | engineering |
| F-9 | Low | MM-003 silently drops future-dated engagements although `EngagementRecord` documents "completed **or committed**". | engineering |
| F-10 | Low | `eli.py`'s module docstring claims the prohibited-input list is enforced by `tests/unit/test_eli.py`, which contains no such assertion. | engineering |
| F-11 | Medium | MM-004 drops the legacy's per-column null counts, dtype validation, and nullability checks without recording the loss anywhere in the manifest. | migration owner |
| F-12 | Medium | MM-004's added-behavior claim is inaccurate: the legacy flagged an entirely-blank required column as a data-quality issue for empty and `nan` values; only whitespace-only values passed as healthy. | migration owner |
| F-13 | **High** | MM-004's `characterization_tests` names "column-validation parity cases" that do not exist. No test in the file references legacy behavior. Repeated in `docs/testing/scaffold-verification.md`. | migration owner |
| F-14 | Low | MM-004 claims 14 test cases; `tests/unit/test_ingest.py` has 13. | migration owner |
| F-15 | Medium | MM-004 derives the column set from `rows[0]` alone; identical ragged data in different row order yields opposite `is_usable` verdicts. Untested. | engineering |
| F-16 | Low | MM-004 treats literal `null` / `none` / `nan` as blank in every column regardless of semantics; `Null` and `None` are real names. | engineering |
| F-17 | Low | MM-004 reports normalized column names back to the coordinator; headers colliding after normalization shadow silently. | engineering |
| F-18 | **High** | MM-005 claims the decline-reason vocabulary is retained. It was replaced: 5 prose strings → 7 different enum codes, 3 with no legacy antecedent. | migration owner |
| F-19 | **High** | MM-005 claims the reason-to-factor mapping is retained. 2 of 6 factor names survive, and the legacy contained two mappings that disagree with each other. | migration owner |
| F-20 | Medium | MM-005's `legacy_path`/`legacy_symbol` omit `src/feedback/service.py` and `src/config.py`, which are the actual source of the ported constants and of the ported delta expression. | migration owner |
| F-21 | **High** | MM-005's claimed legacy defect "free-text decline reasons mapped to factors by substring matching" does not reproduce. Both legacy mappers use exact dictionary lookup; `decline_notes` is never mapped to a factor. | migration owner |
| F-22 | Medium | MM-005 attributes the demo-fixture fallback to `aggregate_feedback`, which returns zeros. It is in `render_feedback_sidebar`. Repeated in `docs/migration/rejected-components.md`. | migration owner |
| F-23 | Medium | MM-005's minimum-decision floor counts total decisions, not declines; 4 accepts plus 1 decline produces a weight movement from a single decline, contradicting the stated rationale. | engineering |
| F-24 | Medium | `test_proposal_always_requires_human_approval` asserts a hard-coded `return True` and never attempts to change the value. It is the only test for the control the `security_review` line rests on. | engineering |
| F-25 | Low | MM-005 bounds each delta but not their sum; six factors may be proposed to move +0.08 each (+0.48 total) with no normalization, which the legacy performed. | engineering |
| F-26 | Low | `FeedbackEntry.match_run_id` accepts an empty string although `data_provenance` makes the attribution load-bearing. | engineering |
| F-27 | Low | `WeightProposal` is not `@final`; a subclass can override `requires_approval` and still satisfy `isinstance`. | engineering |
| F-28 | Low | The v1.1 architecture contract is not present in the target repository, so no `contract_refs` value on any entry can be checked. See below. | migration owner |
| F-29 | Low | 5 pre-existing failures in `tests/integration/test_outbox_dispatcher.py` against a stated baseline of 295 passed / 1 skipped. Outside this review's scope (concurrently-edited area); recorded so it is not mistaken for a consequence of these ports. | engineering |

Findings F-4, F-13, F-18, F-19, and F-21 are the ones that decide the verdicts.
Each is a case of the manifest asserting something that is not so — and the
manifest's only value is as evidence.

---

## What could not be verified

This section is not empty, and a review claiming otherwise would itself be a
finding.

1. **Every `contract_refs` value on all four entries.** The architecture contract
   v1.1 is not in this repository. `docs/architecture/` contains `decisions/`,
   `review/`, and an empty `traceability/`. Sections cited across the four
   entries — §1.2, §1.3, §1.5, §2.2, §3.1, §3.6, §5.1, §5.5, Appendix B — could
   not be read, so I cannot confirm that §3.6 N1 says what the ICS module says it
   says, that §1.3 requires the two-stage cap the ELI module implements, or that
   Appendix B requires shadow mode. Every architectural justification in this
   review is reported as *what the code and manifest assert*, never as *what the
   contract requires*. This is F-28.

2. **Whether the ports behave correctly in use.** None of the four modules has a
   production caller. The only reference anywhere outside the package and its
   tests is a docstring mention of `smartmatch_domain.eli` in
   `factor_registry.py`. Consequently: MM-004's "the import now fails closed" is
   a property of a caller that does not exist; MM-001's contribution to §3.6's
   "visible as unsynchronized rather than silently substituted" cannot be
   observed, because nothing renders an invite; and MM-005's shadow-mode
   guarantee is untested end to end because nothing consumes a `WeightProposal`.
   What was verified is that each module *permits* the correct behavior and does
   not permit the incorrect one.

3. **Golden tests run literally against the legacy.** The manifest says each
   MM-001 corrected-behavior case "fails against the legacy." The signatures are
   incompatible — `generate_ics(event_name, date_str, ...)` against
   `generate_ics(CalendarInvite, *, generated_at)` — so the test bodies cannot be
   executed against the legacy module. What I did instead was execute the legacy
   with the inputs each test encodes and confirm it produces the wrong answer.
   That establishes the claim's substance. It does not establish the literal
   statement, and the difference is worth stating plainly.

4. **MM-003 against legacy outputs.** MM-003 is a `REPLACE` and the manifest says
   characterization does not apply, which is correct. I therefore verified the
   legacy defects and the target's independent correctness, but there is no
   sense in which the target's ELI numbers were checked against anything. The
   parameters (45-day half-life, 90-day window, 4 points per modifier capped at
   20, quadratic penalty) are unvalidated proposals. The manifest says so under
   open decision 2; I am recording that I did not and could not check them.

5. **The `completion_commit` claims.** `7b5ab9f` exists and is the commit that
   introduced all four modules. I did not audit whether the commit's contents
   match the manifest's per-entry description of what shipped.

6. **Runtime, deployment, and data.** No deployed system, no database, no live
   provider, no real dataset. The legacy CSVs under `data/` were read to check
   one factual claim about the recurrence column; nothing was loaded, imported,
   or processed.

7. **MM-002 and the archived entries.** Out of scope for this review. I read
   MM-002's entry for context and formed no view on it.

---

## Integrity statement

**Accessed.** The target repository at `/home/user/IA-Smart-Match-Revamped` on
branch `claude/smart-match-v1-migration-sp1t49`: the four target modules, their
four test files, `tests/unit/test_factor_registry.py`, the migration manifest,
`docs/migration/rejected-components.md`, `docs/security/scaffold-security-review.md`,
`docs/testing/scaffold-verification.md`, `tools/scan_forbidden.py`, and
`pyproject.toml`. The legacy repository at
`/home/user/Nebiux-Team-IA-West-SmartMatch` at `bdce024`: `src/outreach/ics_generator.py`,
`src/matching/factors.py`, `src/data_loader.py`, `src/feedback/acceptance.py`,
`src/feedback/service.py`, `src/config.py`, several `src/ui/` and `src/api/`
callers, and the CSVs under `data/`.

**Legacy repository.** Read only. Nothing was written to it, no branch or commit
was checked out, and no Python byte-compilation was allowed to touch it — the one
legacy module that needed executing was copied to `/tmp` first, with
`sys.dont_write_bytecode` set. Verified clean and at the pinned SHA on
completion:

```
$ cd /home/user/Nebiux-Team-IA-West-SmartMatch && git status --porcelain
$ git rev-parse HEAD
bdce024de1a9bf488c6bd9a7c24a3c87e03ffa42
```

**Target repository.** Two files written, both within this reviewer's ownership:
this document, and the `reviewer` / `status` / `verification_notes` fields of
entries MM-001, MM-003, MM-004, MM-005 in `docs/migration/migration-manifest.yaml`.
No code, no test, and no other document was modified. Several manifest
descriptions were found to be wrong and were **not** corrected in place — they
are recorded above as findings instead, because a manifest edited by its own
reviewer stops being evidence. Nothing was committed and nothing was pushed.

**Live systems.** No provider was called. No live data was read, imported, or
written. No cloud resource was created, modified, or inspected. No credential was
read or required. One throwaway virtualenv was created under `/tmp` to install
pandas, solely to re-execute the legacy null-handling logic for F-12; it lives
outside both repositories.

**Production readiness.** Not claimed, and not assessed.

---

*A4 (independent review agent)*
