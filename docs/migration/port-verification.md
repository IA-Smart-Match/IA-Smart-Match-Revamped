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

## Amendment notice — 26 August 2026, and how it is applied

This document has been amended, and **the amendment is additive: not one
observation below has been rewritten.** Superseded transcripts carry a
`> **Superseded …**` block underneath them; the original text and numbers are
left exactly as they were.

**Why annotation rather than rewriting.** A review is not a description of the
current tree — it is a dated record of what a named reviewer observed at a named
commit, and its value comes entirely from being that. Rewriting the `18 cases`
transcript to say `22` would make this document assert that A4 observed 22 cases
on 18 August 2026, which A4 did not, because there were 18. That is the same act
as the defects this review exists to name: F-5 and F-14 are counts written from
memory instead of measurement, and F-21 is a claimed observation that never
happened. A review that repaired itself by editing its own evidence would be
disqualifying itself while correcting a manifest for exactly that. The review's
own integrity statement makes the argument in the other direction — the reviewer
declined to correct the manifest in place, because "a manifest edited by its own
reviewer stops being evidence" — and the same rule applied symmetrically means a
review edited by the party it criticised stops being evidence too. So: annotate,
never overwrite, everywhere, including where overwriting would have been tidier.

**One exception, and it is a different kind of change.** Finding **F-30** below
is not staleness. It is a defect in this review's own reasoning, wrong at the
moment it was written, and it is recorded as a finding rather than as an
annotation — which is how this document handles every other claim that turned
out not to be so.

**What changed underneath this review.** Two engineering commits on
`claude/pr1-blockers-todos-er5heu` fixed the code findings: `654e89f` (F-1, F-2,
F-3, F-6, F-7, F-8, F-9, F-10 — `ics.py`, `eli.py`) and `8c47c2e` (F-15, F-16,
F-17, F-23, F-24, F-26, F-27 — `ingest.py`, `feedback.py`; F-25 deliberately
left open). The migration-owner findings were then corrected in
`docs/migration/migration-manifest.yaml`,
`docs/migration/rejected-components.md` and
`docs/testing/scaffold-verification.md` on 26 August 2026. **No entry's `status`
was changed by that correction**, per §6 of the orchestrator contract; see
*What a re-reviewer must now check* at the foot of this document.

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
| The four entries' tests | 62 passed (15 + 18 + 13 + 16) — *superseded; see below* |
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

> **Superseded 26 Aug 2026 — the four entries' test counts.** The figures in the
> table above were correct on 18 Aug 2026. Measured at `6a2f0ec` with
> `.venv/bin/pytest <file> --collect-only -q`: `test_ics_golden.py` **17**,
> `test_eli.py` **22**, `test_ingest.py` **21**, `test_feedback.py` **21** — 81
> in total, against 62 here. The whole non-integration suite reports 565 passed,
> 1 skipped, 359 deselected. The four files were not re-executed against the
> legacy for this amendment: the legacy repository is not present in this
> checkout, so nothing in this document's legacy-side evidence has been
> re-derived. That limit is stated again under *What a re-reviewer must now
> check*.

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

> **Superseded 26 Aug 2026 — the counts, and F-2.** The counts above were
> correct on 18 Aug 2026 and matched the manifest then. Measured at `6a2f0ec`:
> **7 preserved-behavior + 10 corrected-behavior = 17**, and the manifest now
> says 17. The two added cases are
> `test_no_itip_method_is_asserted_without_an_organizer_and_attendee` (F-1) and
> `test_dtstamp_is_required_and_never_read_from_the_clock` (F-3).
>
> **F-2 is closed.** `654e89f` rewrote the defect-1 golden test as
> `test_no_start_time_is_ever_fabricated`, and the commit reports it was proven
> by mutant rather than by revert: reintroducing the legacy's "30 days from now"
> fabrication leaves the old assertion passing and fails the new one. That is
> the right shape of proof for an evidence defect — the code was already
> correct, so nothing could be shown by reverting it.

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

> **Superseded 26 Aug 2026 — F-3 closed, both halves.** The transcript above was
> accurate; the default branch no longer exists. `654e89f` made `generated_at` a
> required keyword-only parameter, so the claim in `dependencies_removed` is now
> literally true where it previously was not. Re-measured at `6a2f0ec`:
>
> ```
> $ grep -n 'datetime.now' python/smartmatch_domain/smartmatch_domain/ics.py
> 199:            ``datetime.now(UTC)``, which left one implicit clock read in a
> ```
>
> — the sole remaining match is the docstring sentence explaining the change.
> And the branch is not merely untested but absent:
>
> ```
> >>> generate_ics(invite)
> TypeError: generate_ics() missing 1 required keyword-only argument: 'generated_at'
> ```
>
> **This is a breaking API change**, and the manifest now records it under
> MM-001 `behavior_introduced` rather than leaving it implied by a
> `dependencies_removed` entry. A caller that relied on the default gets a
> `TypeError`, not a document stamped with the current time — which is the
> intended direction, but it is a change to the signature and not only to an
> internal.

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

> **Superseded 26 Aug 2026 — F-1 closed, by removal rather than completion.**
> The document dump above no longer describes the module's output: `654e89f`
> deleted the `METHOD:REQUEST` line. It did not add `ORGANIZER` and `ATTENDEE`,
> and the reasoning is worth keeping visible, because it is the same reasoning
> that rejected legacy defect 1 — completing the METHOD means inventing a mail
> address, there is no organizer identity to draw one from while mail-domain
> registration is open decision 8 (which is why the UID namespace is
> `.invalid`), and asserting what the data does not support is the defect class
> this port exists to end. `docs/plans/defect-remediation.md` §4.2 argued for
> this against the manifest's own plan to defer F-1 to R2, and the manifest's
> MM-001 `notes` now record that the deferral was superseded.
> `test_no_itip_method_is_asserted_without_an_organizer_and_attendee` states the
> RFC 5546 §3.2.2 invariant conditionally, so it stays correct if `METHOD`
> returns with a real organizer behind it.
>
> **The last paragraph above is not superseded.** `STATUS:CONFIRMED` is still
> emitted unconditionally, `PRODID` still differs from the legacy's, and
> `test_document_structure_matches_legacy_shape` still says the envelope is
> "unchanged from the legacy output". Only the `METHOD` half of that sentence
> has gone away. The remaining half is for the re-reviewer.

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

> **Corrected in the manifest, 26 Aug 2026 — F-4, both halves.** MM-003's
> `behavior_retained` no longer claims event cadence; it now reads "recent
> assignment pressure and travel burden combined into a single bounded score",
> with the withdrawn claim and the reason recorded beside it. The softer half
> was answered by adding a `behavior_introduced` field to the manifest schema —
> the schema had `behavior_retained` and `behavior_rejected` and no third box,
> which is *why* a genuine improvement got filed as retention. Time-based decay
> now sits there.
>
> **The false claim also ships inside the package and has not been fixed.**
> `python/smartmatch_domain/smartmatch_domain/eli.py:10` still reads "recent
> assignment pressure, travel burden, and event cadence combined into a bounded
> score". Correcting a manifest and leaving the same sentence in the module it
> describes leaves the falsehood shipped, which is the seam
> `docs/plans/defect-remediation.md` §1 exists to make visible. `eli.py` was
> outside the authority of the 26 Aug documentation correction; the edit is
> reported to the F9 coordinator for routing to engineering and **remains open**.

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

> **Superseded 26 Aug 2026 — F-5 closed, with a correction to the finding's own
> arithmetic.** The observation of 18 was right; the manifest's 20 was not
> merely stale, it **was never right at any commit** — the file has been 18 and
> is now 22, and no revision of it had 20. Measured at `6a2f0ec`:
>
> ```
> $ .venv/bin/pytest tests/unit/test_eli.py --collect-only -q | tail -3
> tests/unit/test_eli.py: 22
> ```
>
> `654e89f` added four: the unrounded-cap boundary (F-6), duplicate modifiers
> counted once (F-8), future-dated engagements rejected (F-9), and the
> prohibited-input enforcement the docstring had promised (F-10). The manifest
> now states 22 and says how it was measured.

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

> **Superseded 26 Aug 2026 — F-6 closed.** `654e89f` stores `utilization`
> unrounded and `evaluate_cap` decides on it; `round(utilization, 4)` is gone
> from `compute_eli` (`grep -n 'round(' eli.py` at `6a2f0ec` matches only the
> `score` / `decayed_hours` / `raw_hours` display rounding and the penalty).
> The fix follows `docs/plans/defect-remediation.md` §4.3, which replaced this
> finding's reasoning rather than its severity: the defect is the *coupling*,
> not the width of the window — 0.005 % of a 40-hour capacity is about seven
> seconds, and nobody is protected by seven seconds. Accordingly the test that
> landed is not "40.002 h is over cap" but
> `test_stage_a_cap_is_decided_on_the_unrounded_utilization`, which asserts the
> decision is *insensitive to display precision* by checking that every
> plausible rendering (0–4 dp) of the offending value still reads ≤ 1.0 while
> the cap decision is `OVER_CAP`. No constant moved and exactly 40.0 h is still
> `WITHIN_CAP`.

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

> **Superseded 26 Aug 2026 — F-7 closed, and one clause of this finding was
> wrong when written.** `654e89f` excludes `MANUAL_BLACKOUT` from
> `modifier_points` while keeping it in `snapshot.modifiers`, so the explanation
> still shows the blackout and the score no longer counts it.
> `test_manual_blackout_wins_over_spare_capacity` was extended to assert
> `score == 0.0` and `load_penalty(snapshot) == 0.0`, which is exactly the
> quantity this finding noted went unasserted.
>
> The correction, from `docs/plans/defect-remediation.md` §4.4 and repeated in
> the commit: **"a non-zero Stage B utility penalty" does not hold.**
> `evaluate_cap` checks `MANUAL_BLACKOUT` first and returns `BLACKED_OUT`, so a
> blacked-out professional never reaches Stage B in that snapshot; the 0.0016
> penalty is computable but unreachable, and the effect on the matching outcome
> was nil rather than small. That moves the defect into a worse category, not a
> milder one — the damage was to the *persisted* `EliSnapshot`, which asserted
> 4.0 of measured workload for someone who had done no work, in the record v1.1
> §5.1 gives the professional a right to correct. There was nothing there to
> correct.

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

> **Superseded 26 Aug 2026 — F-8 closed, at Low rather than Medium.**
> `654e89f` normalizes to a `frozenset` once and uses that one value for both
> the score and the snapshot, covered by
> `test_duplicate_modifiers_are_counted_once_not_per_element`.
> `docs/plans/defect-remediation.md` §4.7 lowered the severity — `mypy --strict`
> runs over these packages in CI and `LoadInputs.modifiers` is annotated
> `frozenset[LoadModifier]`, so any in-repo caller passing a list fails the
> build; the residual exposure is untyped boundaries, and none exists for this
> module yet. The severity moved; the priority did not, and the fix is one line
> that removes the class rather than the instance.
>
> **The consequence for `security_review` stands and has been acted on.** The
> manifest's MM-003 line now says the structure closes the field **set**, not
> the field **types**, and cites
> `tests/unit/test_eli.py::test_prohibited_inputs_cannot_reach_the_computation`
> as what enforces it.

**F-9 (low) — future-dated engagements are silently dropped.**
`EngagementRecord` is documented as "one completed **or committed**
engagement," but `compute_eli` skips `record.occurred_on > inputs.as_of`. A
commitment for next week contributes nothing to the load that is meant to
prevent over-commitment. No test covers the branch.

> **Superseded 26 Aug 2026 — F-9 closed, and the decision behind it recorded.**
> `docs/plans/defect-remediation.md` §4.8 called this "a decision before a fix",
> owned by the migration owner. The decision, now in MM-003
> `behavior_introduced`: **`EngagementRecord` means *completed*.** A record
> dated after `as_of` is refused at construction (`ValueError: ... must not be
> dated after as_of`) rather than counted or silently dropped; a record dated
> exactly on `as_of` has occurred and still counts. Covered by
> `test_future_dated_engagements_are_rejected_not_silently_dropped`, which
> asserts both the rejection and the boundary.
>
> **What is deliberately *not* decided:** whether committed load should
> contribute to ELI at all. That stays open under decision **D2**. Counting
> future commitments needs a forward horizon and a forward weighting rule — the
> recency curve only decays backwards — and both are formula parameters owned by
> the program owner. The silent drop was the defect; making it loud is not an
> answer to the semantic question, and the manifest says so rather than
> implying the question is settled.

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

> **Superseded 26 Aug 2026 — F-10 closed by making the claim true, not by
> weakening it.** The transcript above was accurate. `654e89f` added
> `test_prohibited_inputs_cannot_reach_the_computation`, which for every name in
> `PROHIBITED_INPUTS` asserts it is absent from the `LoadInputs` and
> `EngagementRecord` field sets, that the constructor rejects it as a keyword,
> and that `slots=True` / `frozen=True` leave no route to attach it afterwards.
> The commit's reasoning is the point: *documentation is not a control*, so the
> test was written rather than the docstring softened.
>
> Note this closes only the second half of the docstring's claim. "Enforced by
> the registry schema" is still not demonstrated — no registry schema validates
> `LoadInputs` — and the manifest's corrected `data_provenance` now attributes
> the enforcement to the closed dataclass field set plus this test, rather than
> to a schema. **The `eli.py:19` docstring itself has not been re-read against
> that distinction and is for the re-reviewer.**
>
> The `security_review` paragraph above is also superseded: see the F-8
> annotation, and MM-003's rewritten `security_review` line in the manifest.

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

> **Corrected in the manifest, 26 Aug 2026 — F-11 recorded, not resolved.** All
> three losses are now listed in MM-004 `behavior_rejected` and in
> `docs/migration/rejected-components.md`. Per
> `docs/plans/defect-remediation.md` §3.1 MM-004 condition 3, recording the loss
> is only half of what this finding asks: it also asks whether dropping **dtype
> validation** was intended. That is written into the entry as an **open
> decision with both arguments stated**, not as a settled one — the target
> performs no type checking on imported cells at all, and nothing downstream
> performs it either, so there is currently no type gate anywhere between this
> module and the scoring path. Owner: migration owner, with the adapter that
> will call `validate_columns`. Nothing depends on the answer today, because no
> caller exists.

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

> **Corrected in the manifest, 26 Aug 2026 — F-12, plus a change of substance
> since.** The added-behavior claim has been rewritten to exactly what this
> finding establishes and moved out of `behavior_rejected` into the new
> `behavior_introduced` field — filing an addition under "rejected" is what
> produced the inaccuracy in the first place. The same claim is corrected in
> `docs/migration/rejected-components.md`.
>
> **The behavior itself has also changed, so the rewritten claim is not simply
> the old one made accurate.** `8c47c2e` removed the built-in list of literal
> null markers (`null` / `none` / `nan`) in favour of a caller-declared
> `blank_sentinels` argument, empty by default (finding F-16). So the rule is
> now: `None` and whitespace-only text are blank on their own; a literal `nan`
> or `NULL` is blank **only if the caller declared it**. The manifest's
> `behavior_introduced` says that the null-sentinel rule is caller-declared
> rather than built in, because otherwise the corrected claim would be accurate
> about the legacy and stale about the target on the same line.
>
> Consequence for F-13's remedy: the three legacy outcomes in the transcript
> above are still exactly what a characterization case would encode, but a case
> covering the literal-`nan` row must now pass `blank_sentinels=("nan",)` to
> reproduce it.

### 3. Do the target tests test what they claim?

**F-13.** `characterization_tests: tests/unit/test_ingest.py (column-validation
parity cases)`. There are no parity cases. Nothing in the file references the
legacy, compares against a legacy output, or pins a legacy behavior; every
assertion is written against the target's own design. A characterization test
establishes what the legacy did so a port can be shown not to have changed it,
and none exists. This claim is repeated in
`docs/testing/scaffold-verification.md`, which records "Every reused behavior has
characterization and target tests — **PASS** … MM-004, MM-005."

> **Corrected 26 Aug 2026 — F-13, both copies, by route (b).** MM-004's
> `characterization_tests` is now `n/a` with the reason, and the
> `scaffold-verification.md` row now reads `PASS for MM-001 only` with the
> untrue `PASS` removed and an explicit instruction not to restore it until
> cases exist.
>
> **Route (b) is the weaker of the two answers `docs/plans/defect-remediation.md`
> §3.1 offers, and it was chosen for a reason that is not a judgement about
> characterization.** Route (a) — writing real parity cases from the F-12
> transcript — is available, is cheap, and is the better answer; the agent
> making this correction was not authorized to write tests. Recorded in the
> entry as provisional rather than settled, so nobody reads `n/a` as "parity is
> not applicable here". It is applicable, and expressible, unlike MM-005's.

**F-14.** The manifest says 14 cases. There are 13.

```
tests/unit/test_ingest.py: 13
```

The tests that do exist are sound — none is tautological, none asserts on a
mock, and each would fail against an empty implementation.

> **Superseded 26 Aug 2026 — F-14 closed.** 13 was right on 18 Aug 2026.
> Measured at `6a2f0ec`:
>
> ```
> $ .venv/bin/pytest tests/unit/test_ingest.py --collect-only -q | tail -3
> tests/unit/test_ingest.py: 21
> ```
>
> `8c47c2e` added eight, covering row-order independence (F-15), ragged required
> and optional columns, header collisions on required and non-required columns
> (F-17), caller-declared sentinels and the `Null`/`None`-are-values case
> (F-16), and the duplicate-declaration `ValueError`. The manifest now states 21
> and how it was measured.

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

> **Superseded 26 Aug 2026 — F-15 closed, at High rather than Medium.**
> `docs/plans/defect-remediation.md` §4.1 raised the severity above every other
> code finding here, on three compounding grounds: it fails *open* rather than
> closed, in a control whose docstring says the import fails closed; the
> triggering condition is row order, which is whatever the exporter emitted and
> which no operator discipline avoids; and it is a **regression against the
> legacy** in an `ADAPT` entry, which is the precise category this manifest
> exists to detect and which it did not detect.
>
> `8c47c2e` derives the present set as the union across all rows *and* adds a
> `ragged_rows` finding naming the coordinator's own header and the count of
> rows missing it — ERROR when the ragged column is required, WARNING otherwise.
> The union alone would have hidden the raggedness rather than reporting it.
> Covered by `test_verdict_does_not_depend_on_row_order`,
> `test_required_column_absent_from_some_rows_fails_closed`, and
> `test_ragged_optional_column_warns_but_does_not_block`.

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

> **Superseded 26 Aug 2026 — F-16 closed, by the third of the three options.**
> `docs/plans/defect-remediation.md` §4.8 offered a per-column opt-out,
> restricting the rule to non-name columns, or accepting it and documenting the
> trade. `8c47c2e` took none of those: it **removed the built-in list entirely**
> in favour of a caller-declared `blank_sentinels` argument, empty by default.
> The reasoning is this module's own `data_provenance` — it is handed
> already-parsed rows and knows nothing of their source, so it cannot tell a
> marker from a value, and the adapter that parsed the export can. Default-off
> is the fail-safe direction when the alternative is discarding a name. Covered
> by `test_declared_null_sentinels_count_as_blank` and
> `test_null_and_none_are_values_unless_the_caller_declares_otherwise`. This is
> an API change and is recorded in MM-004 `behavior_introduced`.

**F-17 (low) — findings report normalized names, not the coordinator's headers.**

```
  source header 'Internal Note!' reported as: ('internal_note',)
```

The message reads "columns present but not part of the import contract" and then
names a string that does not appear in the file being fixed. Related: two headers
that normalize to the same column (`Full Name` and `full_name` in one row) are
accepted silently with one shadowing the other, and duplicate entries in the
`required` argument collapse without notice.

> **Superseded 26 Aug 2026 — F-17 closed, all three parts.** `8c47c2e` makes
> findings quote the coordinator's own source header; adds a
> `colliding_headers` finding rather than letting one header shadow another —
> ERROR when the column is required, since which value survived is not
> verifiable; and raises `ValueError` when the caller's own `required` /
> `optional` declaration names the same column twice after normalization, on the
> ground that a caller contract error is not coordinator data. The review was
> right that the shadowing is a data-loss path and not a cosmetic one, and it is
> now a finding of its own. Covered by
> `test_findings_quote_the_coordinators_own_header`,
> `test_headers_colliding_on_a_required_column_fail_closed`,
> `test_headers_colliding_outside_the_required_set_warn`, and
> `test_duplicate_declared_columns_are_a_caller_error`. The `ValueError` is an
> API change and is recorded in MM-004 `behavior_introduced`.

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

> **Corrected in the manifest, 26 Aug 2026 — F-18 and F-19.** MM-005's
> `behavior_retained` no longer claims either. A `behavior_replaced` field was
> added to the schema — a vocabulary and a mapping that were redesigned are
> neither retained nor rejected, and filing a replacement as retention is
> precisely what these two findings are — and both are recorded there with the
> full before/after lists above.
>
> **The sentence beginning "Also worth recording" is the most important
> correction of the four**, and per `docs/plans/defect-remediation.md` §3.1
> MM-005 condition 1 it is now in the manifest as the *justification* for the
> replacement, not merely as a note. The legacy held two maps that contradict
> each other; retaining a mapping that disagrees with itself was never an
> option, and picking one silently would have been worse than replacing both in
> the open. That fact was previously nowhere in the manifest, which is why the
> entry had to reach for "retained" to describe a decision it had not recorded.
>
> **Both false claims also ship inside the package and have not been fixed.**
> `python/smartmatch_domain/smartmatch_domain/feedback.py:6` still reads
> "Retained: the decline-reason vocabulary, the reason-to-factor mapping".
> `feedback.py` was outside the authority of the 26 Aug documentation
> correction; reported to the F9 coordinator and **open**.

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

> **Corrected in the manifest, 26 Aug 2026 — F-20, both halves.** MM-005's
> `legacy_path` and `legacy_symbol` now name `src/feedback/service.py` and
> `src/config.py:125-129` alongside `acceptance.py`, with a `legacy_path_note`
> recording *why* the original attribution was wrong — `acceptance.py` used a
> hard-coded `weight_bump: float = 0.05` and no maximum at all, so the constants
> this entry claims to carry forward cannot have come from the only file it
> named.
>
> The second half — the two `service.py` steps the port drops, the per-factor
> clamp into a band around baseline and the vector renormalization — is now
> recorded in `behavior_rejected` and in
> `docs/migration/rejected-components.md`, and it is explicitly *not* presented
> as a settled decision. It is the substance of F-25, which remains open.

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

> **Corrected 26 Aug 2026 — F-21, two of three copies.** The claim is withdrawn
> from MM-005's `behavior_rejected` and struck through in
> `docs/migration/rejected-components.md`, in both cases with the evidence above
> quoted rather than the row silently deleted: a rejection rationale that changes
> its reason without saying so is not a record of a decision. The closed-enum
> design is untouched and still right — it now rests on the reason that is true
> (the legacy's two mappings contradict each other) rather than on one that is
> not.
>
> **The third copy ships inside the package and has not been fixed.**
> `python/smartmatch_domain/smartmatch_domain/feedback.py:70` — the
> `DeclineReason` docstring — still says "the legacy's attempt to map free text
> to factors by substring matching was the source of its noisiest weight
> suggestions". Reported to the F9 coordinator and **open**.
>
> One limit on this correction, stated because it matters more here than
> anywhere else in this document: the legacy repository is **not present** in
> the checkout where the correction was made, so the withdrawal restates this
> review's search rather than repeating it. A claim that a defect does not exist
> is exactly the kind that must not be accepted on agreement — the only
> acceptable evidence is a fresh search of `bdce024`.

**F-22 — the demo-fixture fallback is misattributed.** The claim is that it lived
"in `aggregate_feedback`, which returned fabricated aggregates when no real
feedback existed." `aggregate_feedback` (`src/feedback/acceptance.py:186-242`)
returns an explicit all-zero dictionary on an empty log and never calls
`load_fixture`. The fixture fallback is in `render_feedback_sidebar`
(`acceptance.py:299-311`), a presentation function, and it fires only when
`demo_mode` is set in session state. The defect is real and rejecting it is
right; the manifest names the wrong function, and
`docs/migration/rejected-components.md` repeats the error.

> **Corrected 26 Aug 2026 — F-22, two of three copies.** Both the manifest and
> `docs/migration/rejected-components.md` now attribute the fallback to
> `render_feedback_sidebar` (`acceptance.py:299-311`) and record that it fires
> only under `demo_mode`. **The third copy is in the package and has not been
> fixed:** `feedback.py:14` still says "the demo-fixture fallback in
> `aggregate_feedback`". Reported to the F9 coordinator and **open**.

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

> **Superseded 26 Aug 2026 — F-23 closed by changing the control, not the
> rationale.** `docs/plans/defect-remediation.md` §3.1 MM-005 condition 6
> allowed either; §4.8 recommended counting declines as the stricter reading and
> the one that matches "the legacy would learn from a single click".
> `8c47c2e` took that route: `MIN_DECISIONS_FOR_PROPOSAL` is now
> `MIN_DECLINES_PER_FACTOR`, counting declines that implicate each factor,
> **per factor** — because a floor met in aggregate would still move an
> individual weight off a single decline. The value is unchanged at 5. Covered
> by `test_no_proposal_below_the_minimum_decline_count`,
> `test_accepts_do_not_unlock_a_movement_driven_by_one_decline` (the exact case
> this finding's truth table exposed), and
> `test_the_floor_is_per_factor_not_per_proposal`. The manifest and
> `docs/migration/rejected-components.md` both now say "minimum decline floor
> (5) per implicated factor".

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

> **Superseded 26 Aug 2026 — the count, F-24, and the characterization claim.**
> 16 was right on 18 Aug 2026 and matched the manifest. Measured at `6a2f0ec`:
>
> ```
> $ .venv/bin/pytest tests/unit/test_feedback.py --collect-only -q | tail -3
> tests/unit/test_feedback.py: 21
> ```
>
> **F-24 is closed.** `8c47c2e` replaced the tautological assertion with probes
> that attempt to defeat the control — assignment to the property, assignment to
> a *field*, `object.__setattr__`, the constructor, `dataclasses.replace`, and
> `WeightProposal.requires_approval.fset is None` — verified against three
> separate mutations. The field-assignment probe is the one that matters most
> and is the one this review did not perform; see **F-30**.
>
> `characterization_tests` is now `n/a` with the reason. The reason recorded is
> this finding's: parity is not merely absent, it is **inexpressible**, because
> five prose reasons became seven enum codes with three having no legacy
> antecedent and two of six factor names surviving — there is no legacy
> input/output pair a target case could be written against. That distinguishes
> it from MM-004, whose `n/a` is provisional.

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

> **Still open, 26 Aug 2026 — F-25 is NOT fixed, deliberately, and it is the
> only finding in this review left in that state.** `8c47c2e` reversed an
> earlier attempt on this branch to bound the sum. The reasoning is
> `docs/plans/defect-remediation.md` §4.5, which raised the finding from Low to
> Medium *and* asked that no sum bound be picked now — the two are consistent
> because the defect is not that 0.48 is large. It is that **the number a human
> approves is not the number that gets applied**: weights are normalized
> somewhere (`factor_registry.normalize_weights` exists), so after
> normalization a proposed +0.08 on one factor is not a +0.08 change in
> effective weight, and the more factors move together the further apart the two
> numbers get. The whole safety argument for this module is that a human
> approves the change, and an approval control whose displayed quantities do not
> correspond to the effect of approving is weak in the direction hardest to
> notice: everything renders plausibly.
>
> Choosing the application semantics — normalize on apply, bound the sum at
> proposal time, or both — belongs with the consumer that applies weights, which
> arrives with weight sets in **M1/M8, behind gate G1**. Picking a bound now
> would manufacture a number with no more provenance than the one it replaces.
>
> What has changed is that the state is now recorded and pinned rather than
> merely present. MM-005 carries an `open_findings` field saying in the
> manifest's own voice that **the proposal is un-normalized and its application
> semantics are unspecified**, and the behavior is pinned by
> `tests/unit/test_feedback.py::test_aggregate_movement_is_deliberately_unbounded`,
> which asserts six deltas of exactly `MAX_FACTOR_DELTA` summing to 0.48 — so
> whichever semantics is chosen has to change a failing test rather than slide
> in beside a silent assumption.

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

> **Superseded 26 Aug 2026 — F-26 closed.** `8c47c2e` refuses a blank
> `match_run_id` at construction, alongside the invariants beside it. Covered by
> `test_feedback_must_be_attributed_to_a_match_run`. MM-005's `data_provenance`
> now says the attribution is enforced rather than merely claimed, which is what
> this finding's second half was about.

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

> **F-30 (Medium) — a defect in this review's own reasoning, not staleness.
> Recorded 26 Aug 2026; it was wrong when written.**
>
> The first row of the probe table above is annotated `TypeError (frozen
> dataclass)`, and `docs/plans/defect-remediation.md` §4.6 tabulates the same
> row under "What it proves: `frozen=True`", concluding that the four probes
> "each fail if someone removes `frozen=True`". **They do not, and the first row
> proves nothing about `frozen`.** `requires_approval` is a property with no
> setter, so assigning to it raises whether or not the dataclass is frozen.
> Measured against the real `WeightProposal` and against a mutant of it with
> `frozen=True` removed and nothing else changed:
>
> ```
> frozen=True   (as shipped)
>   p.requires_approval = False  -> TypeError: super(type, obj): obj must be an instance or subtype of type
>   p.deltas = {}                -> FrozenInstanceError: cannot assign to field 'deltas'
> frozen removed (mutant)
>   p.requires_approval = False  -> AttributeError: property 'requires_approval' of 'WeightProposal' object has no setter
>   p.deltas = {}                -> NO ERROR
> ```
>
> The assignment fails either way; only the *exception type* changes, and it
> changes for a reason unconnected to the guarantee — with `frozen=True` the
> dataclass `__setattr__` runs first and trips over the read-only property,
> which is why the shipped behavior is the confusing `TypeError` rather than the
> honest `AttributeError` the mutant gives. A probe spelled
> `pytest.raises((AttributeError, TypeError))` — the natural spelling once a
> maintainer has seen both — passes unchanged against the mutant. A probe
> spelled `pytest.raises(TypeError)` fails against it, but for the wrong reason
> and with a message that points at the property rather than at the missing
> `frozen`, which any maintainer would reasonably widen.
>
> **The frozen guarantee is observable only through assignment to a *field*** —
> `p.deltas = {}` → `FrozenInstanceError`, and no error at all once `frozen` is
> gone. This review did not probe that, so the table's coverage claim was
> hollow exactly where it said it was strongest: a test suite built from these
> five rows verbatim would have had a hole precisely where the table promised
> protection.
>
> Not a hypothetical. §4.6 named this table as the specification for F-24's
> replacement test and §5 called porting the review's transcripts into the suite
> "the single highest-value item in this whole plan" — so the defect was on a
> direct path into CI, where it would have become a passing test asserting a
> guarantee it did not check. `8c47c2e` avoided it:
> `test_proposal_always_requires_human_approval` includes
> `with pytest.raises(dataclasses.FrozenInstanceError): proposal.deltas = {}`
> alongside the widened `(AttributeError, TypeError)` on the property, and the
> commit reports the suite was verified against three separate mutations rather
> than trusted.
>
> **Owner: this document and `docs/plans/defect-remediation.md` §4.6.** The §4.6
> table still carries the wrong attribution and the "each fails if someone
> removes `frozen=True`" sentence; `docs/plans/` was outside the authority of
> the 26 Aug documentation correction, so that copy is reported to the F9
> coordinator and **remains open**. The lesson generalizes past this table:
> *a probe's exception is evidence for a mechanism only if the probe has been
> run against a mutant with that mechanism removed.* Five of the six probes here
> were run against the shipped class only.

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

> **Superseded 26 Aug 2026 — F-27 closed, and closed at runtime rather than only
> under a type checker.** `8c47c2e` added `@typing.final` *and* an
> `__init_subclass__` that refuses the subclass outright. `@final` closes the
> type-checked route; the runtime refusal closes the untyped one, which is the
> route that actually matters for a control that is structural everywhere else —
> `mypy` does not run on a caller outside this repository. Covered by
> `test_the_approval_control_cannot_be_subclassed_away`. MM-005's
> `security_review` line has been rewritten accordingly and no longer says "no
> caller can" without saying what makes that so.

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

| # | Severity | Finding | Owner | Status — 26 Aug 2026 |
|---|---|---|---|---|
| F-1 | Medium | MM-001 emits `METHOD:REQUEST` with no `ORGANIZER` and no `ATTENDEE`, violating RFC 5546 §3.2.2. New in the port; the legacy emitted no `METHOD`. | engineering | **Fixed** `654e89f` — `METHOD` dropped rather than completed; see the MM-001 q5 annotation. The manifest's plan to defer it to R2 is superseded. |
| F-2 | Low | MM-001's defect-1 golden test asserts a type rejection, not a parsing behavior; it would pass against any type-checking implementation. | engineering | **Fixed** `654e89f` — golden test rewritten to test parsing behavior, proven by mutant. |
| F-3 | Low | MM-001 lists "implicit clock reads" as removed; `generate_ics` still calls `datetime.now(UTC)` when `generated_at` is omitted, and no test covers that branch. | migration owner | **Fixed** — code in `654e89f` (`generated_at` now required; breaking API change), description in the manifest 26 Aug 2026. |
| F-4 | **High** | MM-003 claims "event cadence" as retained behavior. No cadence input exists; ELI has no access to the event under consideration. | migration owner | **Manifest corrected** 26 Aug 2026 (`behavior_retained` rewritten; `behavior_introduced` added for the decay). **The `eli.py:10` copy is OPEN** and is outside that correction's file set. |
| F-5 | Low | MM-003 claims 20 test cases; `tests/unit/test_eli.py` has 18. | migration owner | **Corrected** 26 Aug 2026 — measured **22**. The claim of 20 was never right at any commit; there were 18 at review time. |
| F-6 | Medium | MM-003's Stage A hard cap tests a value rounded to 4 dp, so 100.000–100.005 % of declared capacity reports `WITHIN_CAP`. | engineering | **Fixed** `654e89f` — cap decides on the unrounded value; the test asserts insensitivity to display precision, per remediation §4.3. |
| F-7 | Medium | MM-003 counts `MANUAL_BLACKOUT` in `modifier_points`, giving an idle professional a load score of 4.0 and a non-zero Stage B penalty for a scheduling instruction. | engineering | **Fixed** `654e89f`. One clause of this finding was wrong: the Stage B penalty is unreachable, which makes it a defect in the persisted record rather than in the outcome (remediation §4.4). |
| F-8 | Medium | MM-003 scores `len(inputs.modifiers)` on the raw sequence but reports `frozenset(...)`; a list with duplicates yields a score of 20 beside an explanation naming one modifier. Also weakens the "closed input structure" security claim. | engineering | **Fixed** `654e89f` — normalized once. Lowered to Low by remediation §4.7; the `security_review` consequence is corrected in the manifest. |
| F-9 | Low | MM-003 silently drops future-dated engagements although `EngagementRecord` documents "completed **or committed**". | engineering | **Fixed** `654e89f` — now a rejection, not a drop. Decision recorded: `EngagementRecord` means *completed*. **Whether committed load should count stays open under D2.** |
| F-10 | Low | `eli.py`'s module docstring claims the prohibited-input list is enforced by `tests/unit/test_eli.py`, which contains no such assertion. | engineering | **Fixed** `654e89f` — the promised test was written rather than the docstring weakened. The docstring's separate "registry schema" claim is for the re-reviewer. |
| F-11 | Medium | MM-004 drops the legacy's per-column null counts, dtype validation, and nullability checks without recording the loss anywhere in the manifest. | migration owner | **Recorded** in the manifest 26 Aug 2026. **The dtype-validation decision it asks for is OPEN**, with both arguments stated rather than resolved. |
| F-12 | Medium | MM-004's added-behavior claim is inaccurate: the legacy flagged an entirely-blank required column as a data-quality issue for empty and `nan` values; only whitespace-only values passed as healthy. | migration owner | **Corrected** 26 Aug 2026 in the manifest and `rejected-components.md`, and updated for the caller-declared sentinels (F-16). **The `ingest.py:196` copy is OPEN.** |
| F-13 | **High** | MM-004's `characterization_tests` names "column-validation parity cases" that do not exist. No test in the file references legacy behavior. Repeated in `docs/testing/scaffold-verification.md`. | migration owner | **Corrected** 26 Aug 2026 in both documents, via route (b) — `characterization_tests: n/a` with the reason. **Route (a), writing real parity cases, is OPEN and is the better answer.** |
| F-14 | Low | MM-004 claims 14 test cases; `tests/unit/test_ingest.py` has 13. | migration owner | **Corrected** 26 Aug 2026 — measured **21**. |
| F-15 | Medium | MM-004 derives the column set from `rows[0]` alone; identical ragged data in different row order yields opposite `is_usable` verdicts. Untested. | engineering | **Fixed** `8c47c2e` — union across rows plus a `ragged_rows` finding. Raised to High by remediation §4.1: a fail-closed gate that failed open, and a regression against the legacy in an `ADAPT` entry. |
| F-16 | Low | MM-004 treats literal `null` / `none` / `nan` as blank in every column regardless of semantics; `Null` and `None` are real names. | engineering | **Fixed** `8c47c2e` — the built-in marker list removed in favour of a caller-declared `blank_sentinels`; default off. |
| F-17 | Low | MM-004 reports normalized column names back to the coordinator; headers colliding after normalization shadow silently. | engineering | **Fixed** `8c47c2e` — source headers quoted, `colliding_headers` added, duplicate declarations raise `ValueError`. |
| F-18 | **High** | MM-005 claims the decline-reason vocabulary is retained. It was replaced: 5 prose strings → 7 different enum codes, 3 with no legacy antecedent. | migration owner | **Manifest corrected** 26 Aug 2026 — recorded as replaced, in a new `behavior_replaced` field. **The `feedback.py:6` copy is OPEN.** |
| F-19 | **High** | MM-005 claims the reason-to-factor mapping is retained. 2 of 6 factor names survive, and the legacy contained two mappings that disagree with each other. | migration owner | **Manifest corrected** 26 Aug 2026, with the two-contradictory-mappings fact recorded as the justification. **The `feedback.py:6` copy is OPEN.** |
| F-20 | Medium | MM-005's `legacy_path`/`legacy_symbol` omit `src/feedback/service.py` and `src/config.py`, which are the actual source of the ported constants and of the ported delta expression. | migration owner | **Corrected** 26 Aug 2026 — `legacy_path`/`legacy_symbol` extended with a note on why the original attribution could not have been right; the dropped clamp and renormalization recorded. |
| F-21 | **High** | MM-005's claimed legacy defect "free-text decline reasons mapped to factors by substring matching" does not reproduce. Both legacy mappers use exact dictionary lookup; `decline_notes` is never mapped to a factor. | migration owner | **Withdrawn** 26 Aug 2026 from the manifest and struck through in `rejected-components.md`. **The `feedback.py:70` copy is OPEN.** Re-derivation from `bdce024` is still owed — see the annotation. |
| F-22 | Medium | MM-005 attributes the demo-fixture fallback to `aggregate_feedback`, which returns zeros. It is in `render_feedback_sidebar`. Repeated in `docs/migration/rejected-components.md`. | migration owner | **Corrected** 26 Aug 2026 in both documents. **The `feedback.py:14` copy is OPEN.** |
| F-23 | Medium | MM-005's minimum-decision floor counts total decisions, not declines; 4 accepts plus 1 decline produces a weight movement from a single decline, contradicting the stated rationale. | engineering | **Fixed** `8c47c2e` — the control changed rather than the rationale: `MIN_DECLINES_PER_FACTOR`, counted per factor. Documents updated 26 Aug 2026. |
| F-24 | Medium | `test_proposal_always_requires_human_approval` asserts a hard-coded `return True` and never attempts to change the value. It is the only test for the control the `security_review` line rests on. | engineering | **Fixed** `8c47c2e` — replaced with probes verified against three mutations. **See F-30: the probe table in this document was not a correct specification for it.** |
| F-25 | Low | MM-005 bounds each delta but not their sum; six factors may be proposed to move +0.08 each (+0.48 total) with no normalization, which the legacy performed. | engineering | **OPEN, deliberately.** Raised to Medium by remediation §4.5, which asks that no sum bound be chosen now. Recorded in MM-005 `open_findings` and pinned by `test_aggregate_movement_is_deliberately_unbounded`. Sequenced to the M1/M8 consumer behind gate G1. |
| F-26 | Low | `FeedbackEntry.match_run_id` accepts an empty string although `data_provenance` makes the attribution load-bearing. | engineering | **Fixed** `8c47c2e`. |
| F-27 | Low | `WeightProposal` is not `@final`; a subclass can override `requires_approval` and still satisfy `isinstance`. | engineering | **Fixed** `8c47c2e` — `@final` plus a runtime `__init_subclass__` refusal. |
| F-28 | Low | The v1.1 architecture contract is not present in the target repository, so no `contract_refs` value on any entry can be checked. See below. | migration owner | **OPEN, and it caps every verdict.** No correction can close it: it needs a decision by the program owner — place v1.1 in the repository, or redefine `contract_refs` as author-asserted. Recorded per entry as `contract_refs_status: UNVERIFIABLE`. |
| F-29 | Low | 5 pre-existing failures in `tests/integration/test_outbox_dispatcher.py` against a stated baseline of 295 passed / 1 skipped. Outside this review's scope (concurrently-edited area); recorded so it is not mistaken for a consequence of these ports. | engineering | **Superseded** — see below. |
| **F-30** | Medium | **A defect in this review, not in the manifest or the target.** The F-24 probe table attributes `p.requires_approval = False` → `TypeError` to `frozen=True`. It proves nothing about `frozen`: `requires_approval` is a property with no setter, so the assignment raises either way. The frozen guarantee is observable only through assignment to a *field* (`p.deltas = {}` → `FrozenInstanceError`), which was not probed — so the table's coverage claim was hollow exactly where it said it was strongest. Recorded 26 Aug 2026. | this document; `docs/plans/defect-remediation.md` §4.6 | **Verified against a mutant and recorded here** (see the MM-005 q6 annotation). `8c47c2e` avoided the hole in the test it shipped. **The §4.6 copy of the table is OPEN** — `docs/plans/` was outside the correcting agent's file set. |

Findings F-4, F-13, F-18, F-19, and F-21 are the ones that decide the verdicts.
Each is a case of the manifest asserting something that is not so — and the
manifest's only value is as evidence.

### F-29 — superseded, 26 August 2026

Recorded here rather than deleted, because a finding that turned out to be an
artifact is itself worth leaving on the record, marked. The instruction not to
drop it silently is `docs/plans/defect-remediation.md` §3.4.

F-29 recorded 5 pre-existing failures in
`tests/integration/test_outbox_dispatcher.py` against a stated baseline of 295
passed / 1 skipped, and put them explicitly outside this review's scope as a
concurrently-edited area. Both of those judgements were right, and the finding
was accurate about what was observed. **It no longer describes anything.** Two
things happened to it:

1. `docs/plans/orchestrator-handoff.md` records that the failures were an
   artifact of reading the file while another agent was mid-edit, and that the
   suite was green (26 dispatcher tests) once the edit settled. Backlog **J13**
   supplies a second and better-evidenced explanation for intermittent failures
   in that file: `claim_batch`'s `UPDATE … RETURNING` returned rows in heap
   order rather than the FIFO order its docstring, `oldest_pending_age` and
   ADR-0005 all assumed, and the resulting test failed about one run in thirty
   at module scope. Fixed in `bfb1a0e`.
2. The area has since been substantially rewritten — **J12**
   (`_stranded_predicate` and `reclaim_stranded`, plus three follow-on defects),
   **J13**, and **J17** (`outbox_record.lease_token`, migration `0004`). The 5
   failures cannot be re-run in any meaningful sense, because neither the tests
   nor the code they exercised is the same.

**Not re-measured for this amendment, and deliberately so.** The integration
lane requires `SMARTMATCH_DATABASE_URL` and a live PostgreSQL, and this
amendment was made under an instruction not to set it or run integration tests.
What was observed: the file now collects **44** tests
(`pytest tests/integration/test_outbox_dispatcher.py --collect-only -q`),
against the 26 the handoff cites — so even the handoff note's count is stale.
Collection is not execution and no pass/fail claim is made here. A re-reviewer
who wants F-29 fully *closed* rather than superseded should run the integration
lane and say so.

---

## What could not be verified

This section is not empty, and a review claiming otherwise would itself be a
finding.

> **Still true, 26 Aug 2026, with one item worse.** Item 1 (F-28) is unchanged
> and uncloseable by any correction — see the note appended to it. Items 2, 3, 4
> and 5 are unchanged. **Item 6 is now worse for anyone re-checking this
> document: the legacy repository is no longer present in the checkout at all**
> (`/home/user/Nebiux-Team-IA-West-SmartMatch` does not exist), so the 26 Aug
> corrections to legacy-side claims — F-11, F-12, F-18, F-19, F-20, F-21, F-22 —
> restate this review's transcripts rather than repeat its searches. That is
> exactly the dependency `docs/plans/defect-remediation.md` §5 measure 3 forbids
> a re-review from resting on.

1. **Every `contract_refs` value on all four entries.** The architecture contract
   v1.1 is not in this repository. `docs/architecture/` contains `decisions/`,
   `review/`, and an empty `traceability/`. Sections cited across the four
   entries — §1.2, §1.3, §1.5, §2.2, §3.1, §3.6, §5.1, §5.5, Appendix B — could
   not be read, so I cannot confirm that §3.6 N1 says what the ICS module says it
   says, that §1.3 requires the two-stage cap the ELI module implements, or that
   Appendix B requires shadow mode. Every architectural justification in this
   review is reported as *what the code and manifest assert*, never as *what the
   contract requires*. This is F-28.

   *26 Aug 2026: unchanged, and no correction can change it.* Each of the four
   entries now carries `contract_refs_status: UNVERIFIABLE` saying so in the
   manifest's own voice, which is the most a correction can do. Per
   `docs/plans/defect-remediation.md` §5, **even with every correction and every
   fix, the best honest verdict available is "verified except `contract_refs`"**
   — and reaching a clean `verified` needs a decision that is not
   engineering's: place v1.1 (or a pinned, hash-referenced copy) in the
   repository, or redefine `contract_refs` as author-asserted and stop reading
   it as evidence. The first is recommended. **That decision should be made
   before the re-review is requested rather than discovered inside it**, or the
   re-review returns F-28 again and the cycle repeats.

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

## Amendment — what a re-reviewer must now check

*Added 26 August 2026 by the F9 documentation agent. Not part of the 18 August
review, and written by a different party: everything above this heading is A4's,
everything under a `> **Superseded …**` or `> **Corrected …**` marker is this
amendment's. The two are kept typographically distinct on purpose.*

### The one thing this amendment did not do

**No entry's `status` was changed.** MM-003, MM-004 and MM-005 remain
`ported_unverified`; MM-001 remains `verified`. §6 of the orchestrator contract
forbids an agent approving its own port, and `docs/plans/defect-remediation.md`
§5 extends the principle to exactly this situation: *the corrections were
written by the same party whose original claims failed.* A review that confirms
a corrected manifest now matches the code establishes nothing a careful reader
could not have established by reading the code — the manifest would be
internally consistent and evidentially empty, **which is a worse state than the
rejection it replaced, because it looks settled.** Promotion is the
re-reviewer's decision and nobody else's.

### What is genuinely closed, and therefore cheap to check

Fifteen code findings landed with tests, and the commits state the reasoning
per finding. `654e89f`: F-1, F-2, F-3, F-6, F-7, F-8, F-9, F-10. `8c47c2e`:
F-15, F-16, F-17, F-23, F-24, F-26, F-27. Two of those needed a *mutant* rather
than a revert to prove the test bites (F-2, F-24), because the defect was in the
evidence rather than in the code — that distinction is worth checking, because a
test added for an evidence defect is trivially satisfiable if nobody checked it
fails against something.

### What must be re-derived rather than agreed with

**This is the load-bearing part.** Every correction to a claim about *legacy*
behavior — F-11, F-12, F-18, F-19, F-20, F-21, F-22 — restates this review's
published transcripts. The legacy repository is **not present** in the checkout
where the corrections were made, so nothing was re-searched. Per
`docs/plans/defect-remediation.md` §5 measure 3: re-derive each from the legacy
source at `bdce024` **before** reading the corrected text, then compare. Two
reviews reaching the same conclusion from the same source is worth something; a
second review reading the first is worth much less.

**F-21 is the sharpest case.** It is a claim that a defect does *not* exist, and
the manifest now rests a withdrawal on it. The only acceptable evidence is a
fresh search of the legacy `src/` tree for case-folding, `startswith`,
`endswith` and containment tests against a reason or note field — not agreement
with either document.

### The tail that lands outside the manifest, and is still open

`docs/plans/defect-remediation.md` §1 records that six of the false claims were
copied into the module docstrings of the code they describe. **The 26 August
correction could not touch `python/`, so every one of those copies is still
shipped.** A re-review that reads only the manifest will pass an entry whose
module still says the false thing:

| File | Claim still asserted there | Finding |
|---|---|---|
| `smartmatch_domain/eli.py:10` | "recent assignment pressure, travel burden, and **event cadence**" | F-4 (High) |
| `smartmatch_domain/eli.py:19` | prohibited list "enforced by the **registry schema** and by `tests/unit/test_eli.py`" | F-10 — the test half is now true; the schema half is not |
| `smartmatch_domain/ingest.py:196` | "the legacy loader reported it as present and healthy" | F-12 |
| `smartmatch_domain/feedback.py:6` | "Retained: the decline-reason vocabulary, the reason-to-factor mapping" | F-18, F-19 (High) |
| `smartmatch_domain/feedback.py:14` | "the demo-fixture fallback in `aggregate_feedback`" | F-22 |
| `smartmatch_domain/feedback.py:70` | "map free text to factors by substring matching" | F-21 (High) |

Line numbers are as at `6a2f0ec`; `ingest.py`'s moved from 172 to 196 in
`8c47c2e`. **The re-review scope has to include these docstrings.**

Also still open outside the manifest: the F-24 probe table in
`docs/plans/defect-remediation.md` §4.6 carries the wrong mechanism attribution
and the claim that its probes "fail if someone removes `frozen=True`" — see
**F-30**. §4.6 nominates that table as the specification for a test suite, so
the error is on a path into CI.

### Per entry

**MM-003.** Check that `behavior_retained` no longer claims what the module
cannot do, and that time-based decay reads as introduced rather than retained.
Check the F-9 decision on its merits — `EngagementRecord` now means *completed*,
future-dated records are refused rather than counted or dropped, and whether
committed load should contribute is left open under **D2**; that is a decision
recorded, not a defect fixed, and a re-reviewer may disagree with it. Check the
rewritten `security_review`: it now claims the structure closes the field
**set** and not the field **types**, which is narrower than what it replaced and
should be checked for being narrow *enough*. `eli.py:10` is still wrong.

**MM-004.** `characterization_tests` is `n/a` by route (b) only because the
correcting agent could not write tests. Route (a) is available, cheap, and
better — the F-12 transcript is a ready-made specification, with the caveat that
a literal-`nan` case must now declare `blank_sentinels=("nan",)`. **Decide which
route this entry ships with before promoting it.** Two open decisions are
recorded rather than resolved: whether dropping the legacy's dtype validation
was intended (there is now no type gate anywhere), and that "the import fails
closed" is still a caller obligation with no caller to honour it.
`ingest.py:196` is still wrong.

**MM-005.** **F-25 is open by design and the entry must not be promoted on the
assumption it was overlooked.** The manifest states in its own voice that the
proposal is un-normalized and its application semantics unspecified, and pins
the behavior with a test whose name states the deferral. Check that the
recorded reason for replacing the vocabulary and mapping — the legacy's two
mutually contradictory maps — is one you can reproduce, since it is now the
justification the redesign rests on. Three docstring copies in `feedback.py` are
still wrong.

**MM-001.** Already `verified`; not revisited. Two loose ends the review left
and this amendment did not close: `STATUS:CONFIRMED` is emitted unconditionally
and derived from nothing, and `test_document_structure_matches_legacy_shape`
still says the envelope is "unchanged from the legacy output" while `PRODID` and
`STATUS` did change. Note also that `generate_ics` now has a **breaking
signature**: `generated_at` is required.

### The ceiling, restated

F-28 caps every verdict available. Architecture contract v1.1 is still not in
this repository, so no `contract_refs` value on any entry can be checked —
including the §1.3 reference justifying ELI's two-stage cap and the Appendix B
reference justifying shadow mode. **The best honest verdict reachable today is
"verified except `contract_refs`".** A clean `verified` needs the program owner
to either place v1.1 in the repository or redefine the field as author-asserted,
and that decision should precede the re-review rather than be discovered inside
it.

### And the durable answer, which is none of the above

`docs/plans/defect-remediation.md` §4.6 and §5 make the argument better than it
can be restated here: **the strongest guarantee against self-approval is not a
person, it is a mechanism.** This review executed probes for F-6, F-7, F-8,
F-12, F-15, F-23 and F-25 and published transcripts for each; they are
executable evidence sitting in a Markdown file. Most have since been ported into
the suite by the two fix commits. The one check that has *not* been written, and
that would have caught F-13 — a High finding — on the day it was written, is the
manifest-path existence check: a test that reads the manifest and asserts every
path named in `characterization_tests` and `target_tests` exists, and that
stated counts match `pytest --collect-only`. It is recommended in the manifest's
own `schema_note` and in §3.3. Until it exists, every count in that file is a
number someone has to re-measure by hand — which is what F-5 and F-14 are two
instances of, and what this amendment had to do by hand a third time.

---

## Integrity statement

> **Amendment integrity, 26 August 2026.** The paragraph below headed "Target
> repository" describes A4's run and is unchanged. For this amendment: four
> documentation files were written — `docs/migration/port-verification.md`
> (this file, annotations only; no prior observation altered),
> `docs/migration/migration-manifest.yaml`,
> `docs/migration/rejected-components.md`, and
> `docs/testing/scaffold-verification.md`. No code, no test, and no file under
> `python/`, `services/`, `tests/`, `db/`, `infra/`, `.github/`, `tools/`,
> `docs/plans/`, `docs/architecture/` was modified. No entry `status` was
> changed. Nothing was committed or pushed; the work is left in the working
> tree. No legacy repository was read, because none is present. The integration
> lane was not run and `SMARTMATCH_DATABASE_URL` was not set. Verification run
> after the edits: `tools/scan_forbidden.py` clean, `tools/agent_memory_check.py`
> clean, the manifest parses under `yaml.safe_load`, and
> `pytest tests/ -m "not integration"` reports 565 passed / 1 skipped /
> 359 deselected — unchanged from before the edits, as documentation-only
> changes should leave it.

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
