# Matching engine expansion — decision brief

**Date:** 7 September 2026
**Status:** Proposal for the CBA product owner. **Nothing here is implemented.**
**Asks for:** one decision (the fusion fork), and a ruling on the score card.

---

## 1. What was asked

The owner asked three things:

1. What stops us building "semantic + lexical, similar to a hybrid RAG" recommendation?
2. How does the current engine compare to an open-source reference
   ([NextSteamGame](https://github.com/BakedSoups/NextSteamGame))?
3. Can the UI show a fit score with a plain-language reason — a card reading
   *"Job Fit Score 89%"* over *"Strong full-stack: React (5y), TypeScript (3y)…"*?

This brief answers (1) and (3) and states a recommendation. (2) is covered by the
companion research report, `docs/plans/research/2026-09-07-matching-expansion-options.md`.

---

## 2. The reframe that answers question 1

**Hybrid RAG is a retrieval architecture. CBA Stage B is a scoring architecture.**
They are not alternatives, and the question "should we switch to hybrid RAG" has no
answer as posed.

- Hybrid retrieval — BM25 plus dense vectors, fused by RRF or a weighted blend —
  consumes a query and emits a *ranked list*. It has no weighted rulebook, no
  per-factor provenance, no unknown propagation, and no approver.
- Stage B (`scoring.py:544`, `_compose_cba`) consumes four named factors and emits a
  *value in [0,1]* pinned to `registry_version`, `formula_version` and
  `applied_weights`.

Hybrid retrieval can enter this system in exactly two places, and they are different
projects with different costs:

| | Where | What it changes | Registry impact |
|---|---|---|---|
| **A** | Pool assembly (OQ-CBA-059) | *Who gets scored* — replaces "the caller names `candidate_subject_ids`" with "retrieve top-N for this request" | None |
| **B** | The Topic factor | *One of four numbers* — `cba_semantic_topic` becomes lexical+dense fused | Major bump |

**What it does not apply to is the composite.** You cannot fuse a rank into a weighted
sum. That is the fork this brief asks you to decide.

---

## 3. The real constraint, and it is not the technique

### 3.1 There is no relevance signal, and the pilot will not create one

A hybrid retriever still needs something telling it which results were good. Today:

- OQ-CBA-040 bars response-aware ranking; OQ-CBA-053 bars ratings as a scoring input.
  Both are **policy**, and the owner can reverse them.
- OQ-CBA-051: nothing in the schema records *this speaker appeared at this event*.
  `speaker_on_roster` is a documented stand-in for a fact the schema does not hold
  (`smartmatch_persistence/student_speaker_feedback.py:171`).
- `attendance_record` has a working writer — `AttendanceRepository` in
  `smartmatch_persistence/attendance.py`, with `{qr_scan, coordinator_entry, import}` —
  but its docstring states **"no route imports this repository, and none may."**
  `routers/pipeline.py:61` and `routers/cba_handoff.py:46` both say "No attendance
  writer". So this is one authorization decision away, not a schema migration away.

The pilot runs on synthetic data on a VM. **Synthetic data cannot supply relevance
judgements.** "Tune it after the pilot" is therefore not an available plan.

### 3.2 Retrieval is probably not the bottleneck

Hybrid RAG earns its keep selecting tens of results from millions. CBA selects a
shortlist of 2–3 from **tens** of consented contacts. The weakness is not recall.

### 3.3 The actual weakness is scoring resolution

Under `cba-physical-1`:

| Factor | Weight | Shape |
|---|---|---|
| `industry_match` | 0.30 | binary — 1.0 or 0.0 |
| `role_match` | 0.25 | binary — 1.0 or 0.0 |
| `proximity` | 0.30 | 3-band step — 1.00 / 0.60 / 0.20 |
| `cba_semantic_topic` | 0.15 | continuous, but fixture-backed today |

Two binary tests carry **0.55 combined**. With Topic effectively taking one of a few
values in practice, most candidates land on a small set of discrete composites.
This — not retrieval — is what makes shortlists feel arbitrary, and it is what any
expansion should attack first.

A live consequence is already registered as **OQ-CBA-061**: a speaker *with* topic text
that the fixture cannot score returns `unknown` and is excluded, while a speaker
*without* any topic text gets the 0.50 `policy_neutral` and is shortlisted. Absence
currently outranks presence.

**This is worse in practice than the register records.** The research found that
`FixtureSemanticTopicProvider` raises `TopicComparisonUnavailable` on any *unrecorded*
pair. Under the pilot's fixture provider, a speaker **with** topic text is therefore
unscorable and drops out of the shortlist, and only a speaker with **no** topic evidence
— who receives the 0.50 `policy_neutral` — reaches a number at all. **The Topic factor is
effectively inert outside the golden suite.** This will shape every match run the pilot
demonstrates, and it needs a decision on its own, independent of any expansion.

---

## 4. What is reachable without an outcome loop

More than expected. Retrieval and ranking quality have been evaluated against authored
relevance judgements since TREC, decades before click logs.

| Step | What | Blocked by | Reachable now? |
|---|---|---|---|
| 1 | Decide fork A vs B (§5) | OQ-CBA-059, OQ-CBA-060 | **Yes** — product decision |
| 2 | Real lexical scorer, honestly named | Registry bump + approver | **Yes** |
| 3 | Offline embeddings in-process | OQ-CBA-026 for the offline case | **Yes** |
| 4 | Fusion architecture | The §5 fork | **Yes** |
| 5 | Evaluation via authored gold shortlists | Owner's time | **Yes** |

Two notes that matter:

- **Step 2 is admissible today.** `factors/topic_relevance.py` already *is* a lexical
  set-overlap factor (required 0.75 / preferred 0.25), currently retired. OQ-CBA-026
  forbids shipping token overlap *under a semantic name*; it does not forbid lexical
  matching declared as lexical.
- **Step 3 is the highest-value unblock.** OQ-CBA-026's objection is a *vendor*
  objection — whose credentials, whose terms, whose retention, and may a named person's
  topic text leave the building. A local in-process model answers all four by removing
  the third party, and the `SemanticTopicProvider` Protocol seam already exists
  (`factors/cba_semantic_topic.py:183`), so this is an adapter, not surgery. It
  dissolves OQ-CBA-061 outright.

**Not reachable, and the pilot will not change it:** weight tuning from behaviour; any
decline-, acceptance- or rating-derived factor; anything attendance-derived; online A/B;
and **calibration** — see §6.

---

## 5. The fork, and the recommendation

Decide this **before** steps 2 and 3, because both are wasted effort if fusion
architecture is settled after them.

**Option 1 — fuse inside the Topic factor.** Lexical and dense scores combine into one
[0,1] value; the registry still sees one factor at 0.15.
*Cheapest, preserves every guard.* But the fusion weights become a second weight system
living outside `factor_registry` — precisely what "weights live only in the factor
registry" exists to prevent.

**Option 2 — two sibling factors.** `topic_lexical` and `topic_semantic` as separate
registry entries with their own weights. The registry performs the fusion by
construction and `normalize_weights` already handles it.
*Most honest.* Costs a major bump, re-approval, and a golden re-pin.

**Option 3 — fuse at pool assembly only.** Retrieval decides who is scored; Stage B is
untouched. *No registry change at all.*

### Recommendation (revised 7 Sep 2026, after the research report)

**Option 0 — grade the factors you already have — comes before all three.**

The companion research (`docs/plans/research/2026-09-07-matching-expansion-options.md`)
measured the distinct-composite count: **12 values under `cba-physical-1`, 4 under
`cba-virtual-1`**. It also established that retrieval buys nothing here — the pool is
caller-supplied and capped at `MAX_CANDIDATES = 200`, four orders of magnitude below the
scale at which retrieval earns its keep.

That undercuts the pool-assembly-first recommendation this brief originally made. The
first move is not retrieval at all:

**Grade `industry_match`, `role_match` and `proximity` from binary / step functions to
continuous scores.** This buys roughly an order of magnitude more distinct composite
values from data already in hand — no model, no vendor, no vector store, no new data
collection, and no privacy decision. It costs a `3.0.0` registry bump, new golden cases
and an approver, and nothing else.

Only after that does the retrieval question become worth asking. Then:

- **Option 3 first** because it is the only one that buys something immediately at zero
  registry risk, and it attacks OQ-CBA-059 — which must be answered anyway before any
  retriever is meaningful. It also fails safe: a bad retriever produces a worse candidate
  pool, which a Connector sees and overrides, rather than a wrong number pinned into an
  immutable `match_run` row.
- **Option 2 second** because if semantic matching is worth having, it is worth having
  *in the registry* where it is versioned, weighted and approved like everything else.
- **Not Option 1**, because a second weight system outside the registry is the exact
  failure the anti-deflation guard at `scoring.py:568` and the "no weight literals" rule
  were written to prevent. It would be cheap now and expensive forever.

**Sequencing:** answer OQ-CBA-059/060 → Option 3 → step 2 (lexical, honestly named) →
step 3 (offline embeddings) → Option 2 as a 3.0.0 bump, evaluated against gold shortlists
authored beforehand.

---

## 6. The "Job Fit Score — 89%" card

### It is not forbidden. It is deferred, and the trigger has now fired.

OQ-CBA-005 reads: *"Rank internally; show factor-level provenance and Topic reasoning;
do not show a prominent overall percentage… decide only if a later UI asks to expose the
aggregate."* A later UI has now asked. This is the owner's decision to make, not a rule
to override.

### The number and the sentence are separable, and only the number is contested

**The reason line is reachable now and conflicts with nothing.** `explanation.py` already
emits per-factor state, basis and provenance, and `cba_topic_explanation.py` exists. A
card reading *"Industry: manufacturing, matched · Role: engineering leadership, matched ·
25 miles from campus"* is buildable today and is closer to what the example actually
communicates.

One caveat worth checking before promising it: the example cites **quantified** evidence
("React 5y"). CBA's `basis` strings carry taxonomy versions and match/no-match reasoning,
not durations. The reason line will be honest and specific, but it will not look exactly
like the sample card.

### The recommendation on the number: **do not ship a percentage yet**

Three reasons, in order of weight:

1. **A percentage is a claim of calibration, and nothing here has ever observed a good
   fit.** "89%" reads as *89% likely to be a good match*. The engine has no outcome data
   and, per §3.1, no path to any during the pilot. That is not a presentation quibble;
   it is a claim the system cannot support.
2. **The precision is not there.** Over a composite built from two binary tests (0.55)
   and a 3-band step (0.30), 89% versus 86% is noise dressed as measurement.
3. **It has no value exactly where it is most needed.** Any `unknown` factor makes the
   composite `None` (ADR-0011) — so the card has no number to print for precisely the
   candidates a Connector most needs to understand.

**If the owner wants it anyway** — a legitimate call — the honest form is a **band, not a
percentage**: "Strong match / Possible match / Weak match / Not enough information", with
the fourth state carrying the same weight as the others rather than being hidden. That
satisfies the goal (a legible *why*, at a glance) without asserting precision the engine
does not have. Reversing OQ-CBA-005 for a percentage additionally requires changing
`explanation.py` and `tests/unit/test_frontend_match_run_contract.py`, both of which
currently enforce the prohibition — so the reversal would be visible and deliberate,
which is as it should be.

---

## 7. What this brief asks for

0. **Grade the existing factors** (§5, Option 0). This is now the primary
   recommendation and it depends on none of the others.
1. **Decide the fork** (§5) — *after* Option 0. Recommendation: Option 3, then Option 2.
2. **Rule on the score card** (§6). Recommendation: ship the reason line now, ship a
   band rather than a percentage, revisit the percentage only if calibration data ever
   exists.
3. **Answer OQ-CBA-059 and OQ-CBA-060**, which gate everything else.
4. **Note for later:** the attendance route is one authorization decision, not a
   migration. Worth knowing when an outcome loop is next discussed.

5. **Separately and urgently:** decide what the Topic factor does in the pilot (§3.3).
   As shipped, it excludes the speakers who have topic evidence and rewards those who do
   not.
6. **Note:** `feedback.py`, the only shadow-mode weight tuner in the tree, is imported by
   nothing but its own test and its `REASON_TO_FACTOR` map targets three factors absent
   from `PROPOSED_FACTORS`. It is a trap for whoever wires it up next.

Nothing in this brief is implemented, and nothing should be until items 0–3 are answered.
