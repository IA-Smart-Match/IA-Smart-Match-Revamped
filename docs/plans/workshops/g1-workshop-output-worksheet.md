# G1 workshop output worksheet — UNFILLED TEMPLATE

**Status: DRAFT / UNFILLED. No decision recorded here has been made.**
This worksheet is the *output* side of
[`g1-factor-registry-workshop-packet.md`](g1-factor-registry-workshop-packet.md).
The packet says what must be decided; this worksheet is where the decisions get
written down during the session so that closing gate G1 is a signature, not a
work session.

**Ratifier required:** **Danny Tran (@dangt)** — program owner named 2026-09-02
(packet line 7). Nobody else may fill the decision columns.

**Gate state at authoring:** `REGISTRY_STATUS = "proposed"`;
`assert_registry_approved()` raises `RegistryNotApprovedError`;
`tests/unit/test_factor_registry.py::test_registry_is_not_yet_approved` passes.
**Nothing in this worksheet changes that.** Engineering must not flip the status
until this worksheet is filled, signed, and committed.

## Prepared artifacts to review in-session

| Artifact | What it is | State |
|---|---|---|
| `tests/golden/matching/g1-draft-factor-set.proposed.json` | Machine-readable draft of the factor list, proposed weights, and the open questions, each tagged with its packet source line | DRAFT — every `workshop_decision` is `PENDING`, every `answer` is `null` |
| `tests/golden/matching/symptoms/G1-GC-001..003` | The three required stakeholder-symptom fixtures (pre-existing, placeholder inputs) | Unchanged by this preparation |
| `tests/golden/matching/symptoms/G1-GC-004` | Draft reproducing inputs for the exact-tie symptom | DRAFT — inputs proposed, tie-break rule **not** proposed |
| `tests/golden/matching/symptoms/G1-GC-005` / `G1-GC-006` | ADR-0011 discriminating pair for "Topic Relevance 0%": topics **absent** vs topics **present but disjoint** | DRAFT — `zero_classification` deliberately absent from both |
| `tests/golden/matching/symptoms/G1-GC-007` / `G1-GC-008` | ADR-0011 discriminating pair for "Match Depth 0": history **absent** vs history **recorded empty** | DRAFT — `zero_classification` deliberately absent from both |

All fixture data is synthetic. No expected scores appear in any fixture; the
schema forbids them until G1 closes
(`tests/golden/matching/golden_case.schema.json`, `properties.expected.not`).

## Agenda item 1 — factor list and final weights

Proposal carried forward verbatim from the packet inventory (packet lines
42–50). The right-hand columns are the workshop's to fill.

| Key | Stage | Proposed weight | Implemented | Survives? (Y/N) | Final weight | Notes |
|---|---|---|---|---|---|---|
| `topic_relevance` | B suitability | 0.30 | no | | | |
| `role_fit` | B suitability | 0.25 | no | | | |
| `travel_burden` | B penalty | 0.20 | no | | | D3: no provider contracted |
| `engagement_load` | B penalty | 0.15 | **yes** | | | only implemented scoring factor |
| `repeat_penalty` | B penalty | 0.10 | no | | | |
| `availability` | A eligibility | 0 | no | | 0 (fixed) | legacy `calendar_fit` maps here (packet lines 52–53) |
| `credential_check` | A eligibility | 0 | no | | 0 (fixed) | |
| `contact_status` | A eligibility | 0 | no | | 0 (fixed) | |
| `declared_cap` | A eligibility | 0 | no | | 0 (fixed) | |

Two invariants the final column must satisfy, both machine-checked:

1. Stage B weights sum to **1.0** across scoring factors
   (`test_proposed_scoring_weights_sum_to_one`).
2. Normalized weights over **implemented** scoring factors sum to **1.0**
   (`test_implemented_scoring_weights_sum_to_one`). Today that set is
   `{engagement_load}` alone, so normalization is degenerate and returns 1.0 —
   this is the corrected form of the legacy 0.90 deflation defect, not a bug.

Eligibility factors carry no Stage B weight by construction; `FactorSpec`
raises on any attempt to give one a weight.

## Agenda item 2 — Q6

| Legacy factor | Packet position | Decision (return / drop / rename into) | Rationale |
|---|---|---|---|
| `historical_conversion` | no proposed target (packet line 61) | | |
| `student_interest` | no proposed target (packet line 62) | | |

The packet is explicit that silence is the current defect: one of the three
answers must be written, for each.

## Agenda item 3 — golden cases and ADR-0011 classification

| Fixture | Symptom | `zero_classification` (measured_zero / unknown) | Presentation when unknown |
|---|---|---|---|
| `G1-GC-002` | Topic Relevance 0% (original placeholder) | | |
| `G1-GC-005` | Topic relevance — expertise topics **absent** | | |
| `G1-GC-006` | Topic relevance — topics present, **disjoint** | | |
| `G1-GC-003` | Match Depth 0 (original placeholder) | | |
| `G1-GC-007` | Depth — engagement history **absent** | | |
| `G1-GC-008` | Depth — history **recorded empty** | | |

Tie case `G1-GC-001` / `G1-GC-004`:

- Reproducing inputs — accept the `G1-GC-004` draft, or replace: ____________
- **Tie-break rule** (not determined by the packet, packet line 74): ____________

Also undecided and worth naming: `match_depth` is **not** a key in
`PROPOSED_FACTORS`. Whether it is a factor, a derived display quantity, or a
renaming of an existing factor is open.

## Agenda item 4 — weight governance

1. Who may change approved weights after G1 closes (packet line 87): ____________
2. Does shadow-mode evaluation (MM-005) gate weight changes (packet line 88): ____________
3. Registry version pinning for `match_run` snapshots, M8 (packet line 89): ____________

## Sign-off block — UNSIGNED

- [ ] Surviving factor keys and final weights recorded, both sum invariants hold.
- [ ] Q6 answered for `historical_conversion` and `student_interest`.
- [ ] `zero_classification` recorded for every symptom zero above.
- [ ] Tie-break rule recorded.
- [ ] Named program owner for ongoing weight governance recorded.

**Ratified by:** ____________________  (must be Danny Tran, @dangt)
**Date:** ____________
**Commit recording ratification:** ____________

Only once every box above is ticked and this block is signed does the M1
sequence in the packet (flip `REGISTRY_STATUS`, invert
`test_registry_is_not_yet_approved`, land scored golden cases) become
authorized. Preparing this worksheet does not authorize it.
