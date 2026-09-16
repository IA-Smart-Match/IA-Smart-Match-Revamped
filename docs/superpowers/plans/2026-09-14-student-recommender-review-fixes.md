# Student Recommender — Adversarial Review Fixes Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Amend the four unshipped student-recommender documents so the seven adversarial-review findings (1×P1, 6×P2) are corrected before any V1 task is executed.

**Architecture:** Every finding is a defect in a *proposal*, not in shipped runtime. The fixes are document edits to the contracts, the V1 implementation plan, the decision record, the ADR, and the open-questions register. Each task edits the exact anchors quoted below, updates the tests the V1 plan carries so they would catch the regression, and ends with `make check`-equivalent doc tests green.

**Tech Stack:** Markdown docs; the ADR-index / plan-navigation pytest suite under `tests/`; no Python runtime code changes.

**Spec:** the review text reproduced per task below; the documents under amendment:
- `docs/architecture/student-recommender-contracts.md` (contracts)
- `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md` (V1 plan)
- `docs/decisions/student-recommender-decision-record.md` (decision record)
- `docs/architecture/decisions/ADR-0018-staged-student-event-recommender.md` (ADR-0018)
- `docs/plans/open-questions/student-engagement-deferred.md` (register)

## Global Constraints

- ADR-0018 stays `Proposed`; edits to it are wording corrections to D7 and D4 only, never a status change.
- No register row is closed by this plan. OQ-SC-11, OQ-SE-19, OQ-SE-01 stay OPEN.
- Constants stay domain constants (`STUDENT_FEED_MAX_PER_PRIMARY_TAG = 3`, `STUDENT_FEED_MAX_ITEMS = 5`, `STUDENT_FEED_WINDOW_DAYS = 7`, `STUDENT_FEED_WILDCARD_SLOTS = 1`).
- `FactorScore.value` stays bounded to `[0.0, 1.0]` (`python/smartmatch_domain/smartmatch_domain/factors/__init__.py:95`); the fix adapts the learned ranker, not the value object.
- Verification after every task: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q` must pass (the ADR-index and navigation suites the review reported green).
- Commit after every task with a `docs:` prefix.

---

### Task 1 (P1): Gate outcome training on OQ-SC-11 as well as OQ-SE-19

**Review text:** *"subject_id, event_id, exposure-time features, and exposed_at record exactly what was recommended to whom, which OQ-SC-11 currently prohibits storing. Even label 0 requires an exposure record."*

**Verified:** contracts §5.3 (lines 383–397) gates `training_example` on OQ-SE-19 only; the register row for OQ-SC-11 (register line 32) says "Do not store recommendation exposure rows"; decision record §4.6 (lines 118–131) never names OQ-SC-11.

**Files:**
- Modify: `docs/architecture/student-recommender-contracts.md:15` (intro), `:309` (§4 heading), `:383-397` (§5.3)
- Modify: `docs/decisions/student-recommender-decision-record.md:118-131` (§4.6)
- Modify: `docs/plans/open-questions/student-engagement-deferred.md:58` (OQ-SE-19 row)
- Modify: `docs/architecture/decisions/ADR-0018-staged-student-event-recommender.md:156` (D4 paragraph naming OQ-SE-19)

- [ ] **Step 1: Contracts §5.3 — rename the gate and add the prerequisite sentence**

Replace the heading `### 5.3 \`training_example\` (gated on OQ-SE-19; shape only)` with:

```
### 5.3 `training_example` (gated on OQ-SE-19 **and OQ-SC-11**; shape only)
```

Replace the trailing paragraph (`Not created until the register row closes; ...`) with:

```
Not created until **both** register rows close. Every row here — including a
label-`0` "shown, not acted on" row — is an exposure record: it says which
event was recommended to which student at which time. OQ-SC-11's current
default ("do not store what was recommended to whom") therefore forbids this
table outright. Closure of OQ-SE-19 alone does not admit it; either OQ-SC-11
closes first with a "store, for training, with these fields and retention"
decision, or the OQ-SE-19 decision explicitly resolves OQ-SC-11's scope for
`training_example` rows and the register records that cross-closure. Deletion
semantics are in §5.4.
```

- [ ] **Step 2: Contracts intro and §4 heading**

Line 15: replace `until OQ-SE-19/20` with `until OQ-SE-19/20 (and, for \`training_example\`, OQ-SC-11)`.
Line 309: replace `## 4. Feature registry (V2 — shape fixed now, empty until OQ-SE-19)` with `## 4. Feature registry (V2 — shape fixed now, empty until OQ-SE-19; real examples also need OQ-SC-11)`.

- [ ] **Step 3: Decision record §4.6 — add the prerequisite**

After the sentence ending `(subject_id, event_id, feature vector at exposure time)?` append a new paragraph:

```
**Prerequisite:** a training example *is* an exposure record. OQ-SC-11 (do not
store what was recommended to whom) must close, or be explicitly scoped by the
OQ-SE-19 decision, before a single real example is written. Gold sets and
synthetic pilot personas carry no exposure and are unaffected.
```

Extend `**Closure evidence:**` with `, and an OQ-SC-11 closure or an explicit OQ-SC-11 scope statement inside the OQ-SE-19 decision`.

- [ ] **Step 4: Register row OQ-SE-19**

In the OQ-SE-19 row's last column (`Field classification, retention/deletion decision, \`training_example\` schema, purge-on-profile-delete tests`) append `; OQ-SC-11 closed or scoped by this decision (an example row is an exposure record)`.

- [ ] **Step 5: ADR-0018 D4**

At line 156, after `**OQ-SE-19** decides` locate the end of that sentence and append: ` Because each example records an exposure, OQ-SC-11 must close or be scoped by that decision as well.`

- [ ] **Step 6: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/decisions/student-recommender-decision-record.md docs/plans/open-questions/student-engagement-deferred.md docs/architecture/decisions/ADR-0018-staged-student-event-recommender.md
git commit -m "docs: gate training_example on OQ-SC-11 exposure decision as well as OQ-SE-19"
```

---

### Task 2 (P2): Define purge on profile deletion, not only account deletion

**Review text:** *"this foreign key cascades only when user_account is deleted. The proposed student-owned profile DELETE leaves that account intact."*

**Verified:** contracts §5.3 FK is `(tenant_id, subject_id) → user_account, ON DELETE CASCADE`; W1 plan §3 names the profile table `student_profile` (1:1 with `user_account`, its own `id` UUID PK) and `DELETE /v1/units/{unit_id}/student/profile` hard-deletes that row while the account survives.

**Files:**
- Modify: `docs/architecture/student-recommender-contracts.md:383-397` (§5.3 schema + new §5.4)
- Modify: `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md` Task 9 "Interfaces" block (line ≈2519–2530): add the deletion note

- [ ] **Step 1: Change the FK in the §5.3 schema block**

Replace the line
```
  id UUID PK, tenant_id UUID, subject_id UUID,     -- FK (tenant_id, subject_id) → user_account, ON DELETE CASCADE
```
with
```
  id UUID PK, tenant_id UUID, subject_id UUID,     -- FK (tenant_id, subject_id) → user_account, ON DELETE CASCADE  (account removal)
  student_profile_id UUID NOT NULL,                -- FK → student_profile(id), ON DELETE CASCADE                 (profile removal — the W1 DELETE route)
```

- [ ] **Step 2: Add §5.4 deletion semantics**

Insert after §5.3's closing paragraph:

```
### 5.4 Deletion semantics for `training_example` (part of OQ-SE-19 closure evidence)

Two independent cascades, both required:

| Trigger | Mechanism | Test |
|---|---|---|
| `DELETE /v1/units/{unit_id}/student/profile` (W1; account intact) | `student_profile_id` FK `ON DELETE CASCADE` | `tests/integration/test_training_example_purge.py::test_profile_delete_purges_examples_and_keeps_account` — write two examples, call the W1 DELETE, assert zero rows for the subject **and** the `user_account` row still exists |
| account removal | `(tenant_id, subject_id)` FK `ON DELETE CASCADE` | `::test_account_delete_purges_examples` |
| profile re-created after deletion | new `student_profile.id`; old examples are already gone; no re-link | `::test_recreated_profile_starts_with_no_examples` |

A `PUT` that changes `profile_version` does **not** purge (examples pin the
feature vector at exposure time). The migration that creates this table ships
with these three tests; none exist until both gate rows close (§5.3).
```

- [ ] **Step 3: V1 plan Task 9 note**

In Task 9's **Interfaces** block append a bullet:
```
- Deletion: no table is created in this plan. When OQ-SE-19 + OQ-SC-11 close, the `training_example` migration carries a `student_profile_id` FK with `ON DELETE CASCADE` and the three purge tests in contracts §5.4; the account-level FK alone is insufficient because the W1 profile DELETE leaves `user_account` intact.
```

- [ ] **Step 4: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: training_example purges on profile deletion via student_profile FK, tested independently of account deletion"
```

---

### Task 3 (P2): Put candidate evidence into `inputs_hash`

**Review text:** *"Editing an eligible event's mapped tags can change its Jaccard score, ordering, and wildcard pool without changing any field in this tuple."*

**Verified:** contracts §1.4 lists `sorted(eligible_event_ids)`; V1 plan Task 5 `student_inputs_hash(... eligible_event_ids=(c.event_id for c in stage_a.eligible) ...)` (line ≈1706–1716). `StudentEventCandidate` (contracts line 136) already carries every field Stage B and Stage C consume: `is_virtual, starts_at, time_precision, publication_status, already_registered, tags{state, mapped_terms, quarantined_count, vocabulary_version}`.

**Files:**
- Modify: `docs/architecture/student-recommender-contracts.md:106-116` (§1.4)
- Modify: `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md` Task 5: `student_inputs_hash` definition, the `recommend()` call site (≈1706–1716), and `tests/unit/test_student_recommend.py` block

- [ ] **Step 1: Contracts §1.4 — replace the tuple**

Replace the tuple block with:

```
(unit_id, subject_id, profile_version, sorted(interest_terms), modality_preference,
 interest_vocabulary_version, feed_window.starts_at, feed_window.ends_at,
 sorted(candidate_evidence(c) for c in eligible), sorted(exclude_event_ids),
 registry_version, registry_hash, scoring_mode, scoring_mode_version, formula_version,
 model_artifact_hash, policy_version)

candidate_evidence(c) = (c.event_id, c.is_virtual, c.starts_at.isoformat(), c.time_precision,
                         c.publication_status, c.already_registered,
                         c.tags.state.value, sorted(c.tags.mapped_terms),
                         c.tags.quarantined_count, c.tags.vocabulary_version)
```

Add under it:

```
`candidate_evidence` is every candidate field any Stage B ranker or Stage C
policy may read (contracts §2 and §4 — the V2 `FeatureSpec`s consume the same
fields). Editing an eligible event's tags, modality, start time, or status
therefore changes `inputs_hash`; two responses with equal hashes were computed
from identical evidence. A future candidate field must be added here in the
same change that adds it to `StudentEventCandidate` (the wiring test in V1 plan
Task 5 asserts the dataclass fields and the evidence tuple agree).
```

- [ ] **Step 2: V1 plan Task 5 — new helper and signature**

In Task 5's `student_inputs_hash` definition, replace the parameter `eligible_event_ids: Iterable[str]` with `eligible: Iterable[StudentEventCandidate]`, and add above the function:

```python
def candidate_evidence(c: StudentEventCandidate) -> tuple:
    """Every candidate field a ranker or policy may read; folded into inputs_hash (contracts §1.4)."""
    return (
        c.event_id,
        c.is_virtual,
        None if c.starts_at is None else c.starts_at.isoformat(),
        c.time_precision,
        c.publication_status,
        c.already_registered,
        c.tags.state.value,
        sorted(c.tags.mapped_terms),
        c.tags.quarantined_count,
        c.tags.vocabulary_version,
    )
```

and inside the hash tuple replace `sorted(eligible_event_ids)` with `sorted(candidate_evidence(c) for c in eligible)`.

At the `recommend()` call site replace `eligible_event_ids=(c.event_id for c in stage_a.eligible),` with `eligible=stage_a.eligible,`.

- [ ] **Step 3: V1 plan Task 5 — add the tests**

Append to the `tests/unit/test_student_recommend.py` block:

```python
def test_changing_an_eligible_events_tags_changes_the_hash() -> None:
    catalog = _catalog(tags={"e1": {"finance"}, "e2": {"hackathon"}})
    edited = _catalog(tags={"e1": {"finance", "hackathon"}, "e2": {"hackathon"}})
    a = recommend(
        RUN,
        catalog,
        eligibility=DefaultEligibilityFilter(),
        ranker=_approved_ranker(),
        policy=DefaultFeedPolicy(),
    )
    b = recommend(
        RUN,
        edited,
        eligibility=DefaultEligibilityFilter(),
        ranker=_approved_ranker(),
        policy=DefaultFeedPolicy(),
    )
    assert a.inputs_hash != b.inputs_hash


def test_candidate_evidence_covers_every_candidate_field() -> None:
    from dataclasses import fields
    from smartmatch_domain.student_recommender.candidate import StudentEventCandidate
    from smartmatch_domain.student_recommender.recommend import candidate_evidence

    names = {f.name for f in fields(StudentEventCandidate)}
    assert names == {
        "event_id",
        "is_virtual",
        "starts_at",
        "time_precision",
        "publication_status",
        "already_registered",
        "tags",
    }
    assert len(candidate_evidence(_catalog(tags={"e1": {"finance"}})[0])) == 10
```

(`_catalog` and `_approved_ranker` are the helpers Task 5's test block already defines; if the names differ in the executed plan, use those names.)

Update the contracts §5.5 test table row for `test_student_recommend.py` to add `; editing an eligible event's tags changes the hash; evidence tuple covers every candidate field`.

- [ ] **Step 4: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: fold candidate evidence into inputs_hash so equal hashes mean equal inputs"
```

---

### Task 4 (P2): Derive primary tags inside `recommend()`; delete the test-only `TaggedPolicy`

**Review text:** *"recommend() never supplies primary_tag_by_event, and the route constructs an ordinary DefaultFeedPolicy, so every candidate receives the default missing tag and bypasses diversity handling."*

**Verified:** V1 plan Task 5 `feed = policy.select(run, ranked, inputs_hash)` (line ≈1725); Task 8 route builds `DefaultFeedPolicy()` and calls `recommend()` with no tags; Task 7 golden runner defines `class TaggedPolicy(DefaultFeedPolicy)` (line 2160) and `_primary_tags` (line 2137).

**Files:**
- Modify: `docs/architecture/student-recommender-contracts.md:186-192` (FeedPolicy Protocol) and the `recommend` composition paragraph (≈200–212)
- Modify: V1 plan Task 5 (`recommend()` body), Task 6 (Interfaces text at line 1752; add `primary_tag`), Task 7 (golden runner lines 2137–2165)

- [ ] **Step 1: Contracts §2 — `primary_tag` is domain, not router**

Under the `FeedPolicy` Protocol add:

```python
# student_recommender/policy.py
def primary_tag(interests: StudentInterestEvidence, tags: EventTagEvidence) -> str | None:
    """Alphabetically first interest the event's mapped tags match; None when nothing matches or either side is absent."""
```

Add to the composition paragraph: `recommend` computes `primary_tag_by_event = {c.event_id: primary_tag(run.interests, c.tags) for c in eligible}` and passes it to `policy.select`. No caller supplies tags; the router never sees them.

- [ ] **Step 2: V1 plan Task 5 — `recommend()` passes the mapping**

Replace `feed = policy.select(run, ranked, inputs_hash)` with:

```python
    primary_tag_by_event = {c.event_id: primary_tag(run.interests, c.tags) for c in stage_a.eligible}
    feed = policy.select(run, ranked, inputs_hash, primary_tag_by_event=primary_tag_by_event)
```

and add `from .policy import primary_tag` to the import list. Task 5's stub `policy.py` gains `primary_tag` alongside the Protocol:

```python
def primary_tag(interests: StudentInterestEvidence, tags: EventTagEvidence) -> str | None:
    if not interests.terms or tags.state.value != "tagged":
        return None
    matched = sorted(interests.terms & tags.mapped_terms)
    return matched[0] if matched else None
```

- [ ] **Step 3: V1 plan Task 6 — Interfaces text**

Replace the sentence beginning `the primary tag comes from \`candidate_primary_tags: Mapping[str, str | None]\` the router passes` with `the primary tag comes from \`primary_tag(run.interests, candidate.tags)\` computed inside \`recommend()\` (Task 5); no router involvement`.

- [ ] **Step 4: V1 plan Task 7 — remove the subclass**

Delete `_primary_tags` (lines 2137–2140) and the `class TaggedPolicy` block (2160–2163). Replace `policy=TaggedPolicy()` with `policy=DefaultFeedPolicy()`.

- [ ] **Step 5: V1 plan Task 5 — pipeline-level cap test**

Append to `tests/unit/test_student_recommend.py`:

```python
def test_diversity_cap_applies_through_recommend_without_caller_tags() -> None:
    catalog = _catalog(tags={f"f{i}": {"finance"} for i in range(1, 6)} | {"h1": {"hackathon"}})
    run = replace(
        RUN,
        interests=StudentInterestEvidence(
            terms=frozenset({"finance", "hackathon"}), vocabulary_version=VOCAB
        ),
    )
    out = recommend(
        run,
        catalog,
        eligibility=DefaultEligibilityFilter(),
        ranker=_approved_ranker(),
        policy=DefaultFeedPolicy(),
    )
    ids = [s.subject_id for s in out.feed.items]
    assert (
        ids[STUDENT_FEED_MAX_PER_PRIMARY_TAG] == "h1"
    )  # deferred behind the first three finance items (soft preference, Task 5)
    assert len(ids) == STUDENT_FEED_MAX_ITEMS
```

- [ ] **Step 6: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: recommend() derives primary tags for the diversity cap; drop test-only TaggedPolicy"
```

---

### Task 5 (P2): Make the diversity rule an explicit soft preference

**Review text:** *"appending deferred candidates before taking the first five violates ADR-0018 D7's maximum of three ranked items per primary tag... Keep over-cap candidates outside ranked slots, allowing a shorter feed, or obtain an explicit change from a hard cap to a soft diversity preference."*

**Verified:** V1 plan `_apply_diversity_cap` returns `kept + deferred` and `select` takes `ordered[:STUDENT_FEED_MAX_ITEMS]` (lines 1889–1926), which is a soft preference. ADR-0018 D7 (line 202–204) words it as "no more than 3 ranked items sharing the same primary tag", a hard cap. The two disagree; `test_diversity_cap_reorders_without_promoting_unscorables` asserts only `ids[:3]` and `ids[3] == "h1"`, so it does not pin either reading.

**Decision (program owner, 2026-09-14):** the rule is a **soft preference**, not a cap. Items past `STUDENT_FEED_MAX_PER_PRIMARY_TAG` are deferred behind every other scorable item and then fill the remaining ranked slots; the feed always fills to `STUDENT_FEED_MAX_ITEMS` when enough scorable items exist. The implementation stands; the ADR, the contracts, and the tests are corrected to say so. No new response field.

**Files:**
- Modify: ADR-0018 D7 (line 202–204) and the "Consequences" mention of the diversity cap (line ≈259)
- Modify: contracts §2 constants comment (line 198), §5.1 "minimum set" sentence (≈line 371–375), §5.5 test row for `test_student_feed_policy.py` (line 425)
- Modify: V1 plan Task 6 (`_apply_diversity_cap` docstring, `select`, tests at 1822–1830), Task 7 golden case list (line ≈2047 table) and the SE-GC case that exercises the rule

- [ ] **Step 1: ADR-0018 D7 wording**

Replace `(3) a **diversity cap** — no more than \`STUDENT_FEED_MAX_PER_PRIMARY_TAG = 3\`
ranked items sharing the same primary tag, stated as a constant, applied as a
stable re-order that never promotes an unscorable item;` with:

```
(3) a **diversity preference** — items beyond `STUDENT_FEED_MAX_PER_PRIMARY_TAG = 3`
sharing one primary tag are deferred behind every other scorable item and then
fill any ranked slots still open, so the feed stays full whenever enough
scorable items exist; stated as a constant, applied as a stable re-order that
never promotes an unscorable item and never shortens the feed;
```

At line ≈259 (Consequences) replace `the diversity cap` with `the diversity preference`. Leave the constant name unchanged (Global Constraints).

- [ ] **Step 2: Contracts wording**

Line 198: change the comment on `STUDENT_FEED_MAX_PER_PRIMARY_TAG` to `# soft preference: items past this per-tag count are deferred, then fill open slots (ADR-0018 D7)`. In §5.1 replace `one diversity-cap re-order` with `one diversity re-order where deferred same-tag items still fill the feed`. In §5.5 replace `diversity cap never promotes an unscorable` with `diversity preference defers past-3 same-tag items behind other tags, then fills to five; never promotes an unscorable`.

- [ ] **Step 3: V1 plan Task 6 — docstring and precise tests**

Change the `_apply_diversity_cap` docstring to `"""Soft preference (ADR-0018 D7): an item past the per-tag count is deferred behind every other scorable item, never dropped; the feed still fills."""`. Replace `test_diversity_cap_reorders_without_promoting_unscorables` with:

```python
def test_diversity_preference_defers_same_tag_items_but_still_fills_the_feed() -> None:
    ranked = _ranked(
        ("f1", 0.9), ("f2", 0.8), ("f3", 0.7), ("f4", 0.6), ("h1", 0.5), ("f5", 0.4), ("u", None)
    )
    tags = {
        "f1": "finance",
        "f2": "finance",
        "f3": "finance",
        "f4": "finance",
        "h1": "hackathon",
        "f5": "finance",
        "u": None,
    }
    feed = DefaultFeedPolicy().select(RUN, ranked, HASH, primary_tag_by_event=tags)
    assert [s.subject_id for s in feed.items] == ["f1", "f2", "f3", "h1", "f4"]
    assert feed.wildcard is not None and feed.wildcard.subject_id == "f5"
    assert feed.wildcard_pool_size == 1
    assert "u" not in [s.subject_id for s in feed.items]
    assert feed.withheld_unscorable == 1


def test_diversity_preference_never_shortens_the_feed() -> None:
    ranked = _ranked(("f1", 0.9), ("f2", 0.8), ("f3", 0.7), ("f4", 0.6), ("f5", 0.5))
    tags = {k: "finance" for k in ("f1", "f2", "f3", "f4", "f5")}
    feed = DefaultFeedPolicy().select(RUN, ranked, HASH, primary_tag_by_event=tags)
    assert [s.subject_id for s in feed.items] == ["f1", "f2", "f3", "f4", "f5"]
    assert feed.wildcard is None and feed.truncated is False
```

- [ ] **Step 4: V1 plan Task 7 — golden case pins the ordering**

In the golden case table, make the diversity case (the row whose expectation mentions the cap or re-order; add **SE-GC-011 — diversity preference** if none does) use inputs: interests `[finance, hackathon]`; events `f1..f4` tagged `[finance]` with descending scores, `h1` tagged `[hackathon]` scoring below `f4`; expected `order: [f1, f2, f3, h1, f4]`, `wildcard: null`, `withheld_unscorable: 0`, `withheld_untagged: 0`.

- [ ] **Step 5: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/decisions/ADR-0018-staged-student-event-recommender.md docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: diversity rule is an explicit soft preference; tests pin the deferred ordering"
```

---

### Task 6 (P2): Anchor the feed window so identical requests share a fingerprint

**Review text:** *"Every request creates new microsecond-resolution window bounds, which enter inputs_hash and therefore the wildcard seed."*

**Verified:** V1 plan Task 8 route: `now = datetime.now(tz=UTC); window = (now, now + timedelta(days=STUDENT_FEED_WINDOW_DAYS))` (lines 2433–2434); eligibility compares `start <= c.starts_at < end` (line 1223).

**Decision:** anchor `starts_at` to the top of the current UTC hour. Two requests within the same clock hour share a window; crossing an hour boundary is a legitimate input change. An event that started earlier in the current hour stays eligible for that hour (acceptable: it is still "this week"). Day-level anchoring was rejected because it would keep events that ended hours ago eligible until midnight.

**Files:**
- Modify: contracts §1.1 (the `feed_window` sentence near line 31) and §1.4 comment
- Modify: V1 plan Task 4 (`student_feed.py` constants block: add `feed_window_for`), Task 4 tests, Task 8 route (2433–2434) and HTTP tests

- [ ] **Step 1: Contracts — window anchor rule**

After the `exclude_event_ids` paragraph (line ≈31) add:

```
`feed_window` is anchored, not sampled: `starts_at` is the request clock
floored to the hour (UTC), `ends_at = starts_at + STUDENT_FEED_WINDOW_DAYS`.
Two requests in the same clock hour with the same profile, exclusions and
eligible catalog therefore return the same `inputs_hash` and the same wildcard.
The anchor is `student_feed.feed_window_for(now)`; the router never builds the
tuple itself.
```

- [ ] **Step 2: V1 plan Task 4 — domain function + test**

In `student_feed.py` add:

```python
STUDENT_FEED_WINDOW_ANCHOR: Final[str] = "hour"  # documented in contracts §1.1


def feed_window_for(now: datetime) -> tuple[datetime, datetime]:
    """Anchor the window to the top of the UTC hour so refreshes within an hour share an inputs_hash."""
    if now.tzinfo is None:
        raise ValueError("feed_window_for: now must be tz-aware")
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=STUDENT_FEED_WINDOW_DAYS)
```

Test in `tests/unit/test_student_feed_window.py`:

```python
from datetime import UTC, datetime, timedelta
import pytest
from smartmatch_domain.student_recommender.student_feed import (
    STUDENT_FEED_WINDOW_DAYS,
    feed_window_for,
)


def test_requests_in_the_same_hour_share_a_window() -> None:
    a = feed_window_for(datetime(2026, 10, 5, 14, 3, 7, 123456, tzinfo=UTC))
    b = feed_window_for(datetime(2026, 10, 5, 14, 59, 59, 999999, tzinfo=UTC))
    assert (
        a
        == b
        == (
            datetime(2026, 10, 5, 14, tzinfo=UTC),
            datetime(2026, 10, 5, 14, tzinfo=UTC) + timedelta(days=STUDENT_FEED_WINDOW_DAYS),
        )
    )


def test_crossing_the_hour_moves_the_window() -> None:
    assert feed_window_for(datetime(2026, 10, 5, 14, 59, tzinfo=UTC)) != feed_window_for(
        datetime(2026, 10, 5, 15, 0, tzinfo=UTC)
    )


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError):
        feed_window_for(datetime(2026, 10, 5, 14))
```

- [ ] **Step 3: V1 plan Task 8 — route uses the anchor and exposes a clock seam**

Replace the two `now`/`window` lines with:

```python
    window = feed_window_for(_now())
```

and add module-level `def _now() -> datetime: return datetime.now(tz=UTC)` (the test seam). Add to Task 8's HTTP tests:

```python
def test_two_requests_in_the_same_hour_share_inputs_hash_and_wildcard(
    client, approved_registry, seeded_catalog, monkeypatch
) -> None:
    import smartmatch_api.routers.student_recommendations as mod

    clock = iter(
        [datetime(2026, 10, 5, 14, 3, tzinfo=UTC), datetime(2026, 10, 5, 14, 41, tzinfo=UTC)]
    )
    monkeypatch.setattr(mod, "_now", lambda: next(clock))
    first = client.get(URL).json()
    second = client.get(URL).json()
    assert first["provenance"]["inputs_hash"] == second["provenance"]["inputs_hash"]
    assert first["wildcard"] == second["wildcard"]
    assert first["feed_window"] == second["feed_window"]
```

(`client`, `approved_registry`, `seeded_catalog`, `URL` are the fixtures Task 8's test block already defines.)

- [ ] **Step 4: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: anchor the feed window to the hour so identical requests share inputs_hash"
```

---

### Task 7 (P2): Bounded factor transforms for learned features

**Review text:** *"build_feature_vector() emits raw interest_count and event_tag_count, but FactorScore.__post_init__ rejects values outside [0,1]... LearnedRanker.rank() raise[s] instead of returning the promised StageBScore."*

**Verified:** V1 plan Task 9 `build_feature_vector` emits `float(len(run.interests.terms))` and `float(len(candidate.tags.mapped_terms))`; Task 10 `_score` builds `FactorScore(factor_key=k, value=vector.values[k], ...)` for every required feature; `FactorScore.__post_init__` rejects `value` outside `[0.0, 1.0]`. Tests in Task 10 only construct rankers, never call `rank()`.

**Decision:** `FeatureVector.values` stays raw (the model wants raw counts). `FeatureSpec` gains `factor_transform`, a registered bounded map used only when a raw value becomes a `FactorScore` for provenance. Every spec must declare one unless its raw range is already `[0,1]`.

**Files:**
- Modify: contracts §4 `FeatureSpec` block (≈line 312–330)
- Modify: V1 plan Task 9 (`FeatureSpec`, `STUDENT_FEATURES`, tests), Task 10 (`_score`, tests)

- [ ] **Step 1: Contracts §4 — `FeatureSpec.factor_transform`**

Add to the `FeatureSpec` field list: `factor_transform: Callable[[float], float] | None = None   # raw → [0,1] for FactorScore provenance; None ⇒ raw is already bounded and __post_init__ verifies the declared range`. Add the rule: "`FeatureVector.values` are raw model inputs. `StageBScore.factor_scores` are the same features rendered through `factor_transform`. A spec with an unbounded raw range and no transform fails at registry construction, not at rank time."

- [ ] **Step 2: V1 plan Task 9 — `FeatureSpec` and registry**

Add fields to `FeatureSpec`:

```python
factor_transform: Callable[[float], float] | None = None
raw_bounded: bool = False  # True when raw values are already in [0, 1]


def as_factor(self, raw: float) -> float:
    value = raw if self.factor_transform is None else self.factor_transform(raw)
    return min(1.0, max(0.0, value))
```

and extend `__post_init__`:

```python
        if self.factor_transform is None and not self.raw_bounded:
            raise ValueError(f"{self.key}: unbounded raw feature needs a factor_transform")
```

Add constants above `STUDENT_FEATURES`:

```python
STUDENT_INTEREST_VOCABULARY_SIZE: Final[int] = 12  # W1: the twelve G3 terms
STUDENT_MAX_TAGS_PER_EVENT: Final[int] = 12  # same vocabulary
```

Rewrite the registry rows:

```python
STUDENT_FEATURES: Final[tuple[FeatureSpec, ...]] = (
    FeatureSpec(
        "student_interest_overlap",
        FeatureSource.STUDENT_PROFILE,
        True,
        "OQ-SE-01",
        "Jaccard over the shared vocabulary.",
        raw_bounded=True,
    ),
    FeatureSpec(
        "interest_count",
        FeatureSource.STUDENT_PROFILE,
        True,
        "OQ-SE-01",
        "How many interests were declared.",
        factor_transform=lambda n: n / STUDENT_INTEREST_VOCABULARY_SIZE,
    ),
    FeatureSpec(
        "event_tag_count",
        FeatureSource.EVENT,
        True,
        "OQ-SE-01",
        "How many mapped tags the event carries.",
        factor_transform=lambda n: n / STUDENT_MAX_TAGS_PER_EVENT,
    ),
    FeatureSpec(
        "modality_match",
        FeatureSource.EVENT,
        True,
        "OQ-SE-01",
        "Preference and modality agree.",
        raw_bounded=True,
    ),
    FeatureSpec(
        "days_until_event",
        FeatureSource.EVENT,
        False,
        "OQ-SE-01",
        "Days from window start.",
        factor_transform=lambda d: d / STUDENT_FEED_WINDOW_DAYS,
    ),
)
```

Add tests to `tests/unit/test_feature_spec.py`:

```python
def test_unbounded_feature_without_transform_is_rejected() -> None:
    with pytest.raises(ValueError, match="factor_transform"):
        FeatureSpec("raw_count", FeatureSource.EVENT, True, "OQ-SE-01", "x")


@pytest.mark.parametrize(
    "key,raw,expected",
    [
        ("interest_count", 2.0, 2 / 12),
        ("event_tag_count", 12.0, 1.0),
        ("event_tag_count", 30.0, 1.0),
        ("days_until_event", 3.5, 0.5),
    ],
)
def test_as_factor_is_bounded(key: str, raw: float, expected: float) -> None:
    spec = next(f for f in STUDENT_FEATURES if f.key == key)
    assert spec.as_factor(raw) == pytest.approx(expected)
```

- [ ] **Step 3: V1 plan Task 10 — `_score` uses `as_factor`**

Replace the `factor_scores = tuple(...)` expression in `_score` with:

```python
        specs = {f.key: f for f in STUDENT_FEATURES}
        factor_scores = tuple(
            FactorScore(
                factor_key=k,
                value=None if vector.values[k] is None else specs[k].as_factor(vector.values[k]),
                basis=f"Feature {k} (raw {vector.values[k]}) from registry {vector.feature_registry_version}.",
            )
            for k in required
        )
```

- [ ] **Step 4: V1 plan Task 10 — a test that actually ranks**

Append to `tests/unit/test_student_learned_ranker.py`:

```python
def test_learned_ranker_ranks_multi_interest_multi_tag_candidates() -> None:
    run = replace(
        RUN,
        interests=StudentInterestEvidence(
            terms=frozenset({"finance", "hackathon"}), vocabulary_version=VOCAB
        ),
    )
    candidates = _catalog(tags={"e1": {"finance", "hackathon"}, "e2": {"finance"}, "e3": set()})
    ranker = LearnedRanker(predictor=_Constant(), model_artifact_hash=None)
    ranked = ranker.rank(run, candidates)
    assert [s.subject_id for s in ranked][:2] == [
        "e1",
        "e2",
    ]  # constant margin ⇒ event-id tie-break
    e1 = next(s for s in ranked if s.subject_id == "e1")
    assert e1.value is not None
    assert all(0.0 <= f.value <= 1.0 for f in e1.factor_scores if f.value is not None)
    assert next(
        f for f in e1.factor_scores if f.factor_key == "interest_count"
    ).value == pytest.approx(2 / 12)
    assert (
        next(s for s in ranked if s.subject_id == "e3").value is None
    )  # untagged ⇒ unscorable, not raised
```

(`RUN`, `VOCAB`, `_catalog`, `StudentInterestEvidence` are the fixtures Task 5's tests define; import them or duplicate the three-line helper.)

- [ ] **Step 5: Run the doc suites**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/student-recommender-contracts.md docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md
git commit -m "docs: bounded factor transforms so LearnedRanker.rank returns StageBScore for raw counts"
```

---

### Task 8: Close-out — consistency sweep and review pointer

**Files:**
- Modify: `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md` header (add a "Review amendments" line)
- Modify: `docs/plans/README.md` (row for this fixes plan, if the README lists superpowers plans)

- [ ] **Step 1: Grep for stale names**

```bash
grep -n "TaggedPolicy\|_primary_tags\|eligible_event_ids\|window = (now\|candidate_primary_tags" docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md docs/architecture/student-recommender-contracts.md
```
Expected: no output (each name was removed in Tasks 3, 4, 6).

- [ ] **Step 2: Header note in the V1 plan**

Under the plan header add: `**Review amendments (2026-09-14):** see \`docs/superpowers/plans/2026-09-14-student-recommender-review-fixes.md\` — soft diversity preference (owner decision), hour-anchored window, candidate evidence in \`inputs_hash\`, in-pipeline primary tags, bounded learned factors, and OQ-SC-11 as a training prerequisite.`

- [ ] **Step 3: Full doc suite**

Run: `.venv/bin/python -m pytest tests/unit/test_adr_index.py tests/unit/test_gate_decision_artifacts.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md docs/plans/README.md
git commit -m "docs: record review amendments on the student recommender V1 plan"
```
