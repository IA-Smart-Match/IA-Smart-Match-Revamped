# Student recommendation program — the prioritized workflow (2026-09-13)

**Status:** planning only. This document changes no source file, adds no route,
writes no migration, and closes no register row.

**Why this exists.** The 12 September stakeholder brief
([`2026-09-12-student-centric-prioritization-brief.md`](2026-09-12-student-centric-prioritization-brief.md))
established *what* to build and in what order of value. It did not give the team
a **workflow** — waves, gates, owners, and what unblocks what — and the owner's
report from the session was that the infrastructure is building out but the
prioritized sequence is missing. This is that sequence.

**Baseline.** Written against `feat/frontend-dev-resync` @ `915c43c`, the leading
head. Migration head `0036_host_organization`. The published contract carries
**83 operations**.

**This is new scope, and that is recorded rather than assumed.**
`docs/product/cba-smart-match-customer-requirements.md` contains **no
recommendation requirement and no notification requirement** — grepping it for
`recommend|notif|reminder|suggest` returns only incidental prose. Every wave below
is therefore work the customer document does not ask for, authorized by the
program owner from the 12 September session, in the shape
[`2026-09-07-remaining-pilot-gaps-plan.md`](2026-09-07-remaining-pilot-gaps-plan.md)
uses for work that goes beyond a committed artifact. No wave loosens an invariant:
no match percentage in the UI (OQ-CBA-005), weights only in `factor_registry` and
persisted settings, every `/v1` route deny-by-default, no fake success, unknown
never degrading to a default (ADR-0011 rule 1), `ALLOW_LIVE_PROVIDERS` and
`ALLOW_CLOUD_DEPLOY` stay false.

## Companion documents

| | |
|---|---|
| W1 — the student profile | [`2026-09-13-w1-student-interest-profile-plan.md`](2026-09-13-w1-student-interest-profile-plan.md) |
| W2 — ranking | [`2026-09-13-w2-student-event-ranking-plan.md`](2026-09-13-w2-student-event-ranking-plan.md) |
| W3 — delivery | [`2026-09-13-w3-recommendation-delivery-plan.md`](2026-09-13-w3-recommendation-delivery-plan.md) |
| W4 — aggregate demand | [`2026-09-13-w4-aggregate-demand-signal-plan.md`](2026-09-13-w4-aggregate-demand-signal-plan.md) |
| Feed research and the UI argument | [`research/2026-09-13-engagement-feed-research.md`](research/2026-09-13-engagement-feed-research.md) |
| The prototype's prompt and artifacts | [`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md) §Prompt 10 |

---

## 1. The waves

| Wave | Deliverable | Blocked by | Migration | Runs |
|---|---|---|---|---|
| **W0** | **Turn the points economy on.** Ratify D7; seed a funded catalog for the pilot unit | Ann + Yuka (OQ-SC-01) | none | **Now** |
| **W1a** | `smartmatch_domain/student_interests.py` — the vocabulary binding and nothing else | none | none | **Now** |
| **W1b** | `student_profile` + `student_profile_interest`, and the three student-owned routes | OQ-SC-02 | **`0037`** | On OQ-SC-02 |
| **W2a** | Parameterise `factor_registry` so two registries can coexist | none | none | **Now** |
| **W2b** | The student registry, the factors, the composition, golden cases, ADR-0018 | W1a + W2a | none | After W2a |
| **W3** | The weekly digest: student channel consent, then a durable command on the existing dispatch path | OQ-SC-03 | **`0038`** | Parallel |
| **W4** | The aggregate demand read | W1b | none | After W1b |
| **W5** | Naming a speaker on a student-facing card | OQ-CBA-064 **and** OQ-CBA-051 | — | **Not scheduled** |

```
  OQ-SC-01 ──► W0                                   (decision only; no code)

  W1a ─────────────┬──► W2b ──► [Gate 1: owner approves the student registry]
  W2a ─────────────┘              │
                                  ▼
  OQ-SC-02 ──► W1b ──┬───────► the feed is real
                     └──► W4 ──► the demand read

  OQ-SC-03 ──► W3                                   (digest drives registrations)

  OQ-CBA-064 + OQ-CBA-051 ──► W5                    (not scheduled)
```

**W1a and W2a start today.** Neither is blocked on a decision, and W2a is the
long-pole review because it edits an owner-approved file. Splitting the vocabulary
binding out of W1 is deliberate: it is the only W1 artifact W2 needs, so the
scoring work proceeds while the table and routes are still in review.

**Gate 1 — the owner approves the student registry.** W2b ships with
`STUDENT_REGISTRY_STATUS = "proposed"`, which makes `assert_registry_approved`
raise and the whole scoring path fail closed. The owner reviews ADR-0018 and the
golden cases, then flips one constant. **A one-constant-plus-tests pull request by
design** — which is the point of shipping with the gate shut rather than waiting.

**Migration budget: two revisions across the programme.** `0037` (W1b — both
tables and both indexes) and `0038` (W3). W2 and W4 are schema-free *by
construction*, which is a design property worth stating rather than an accident.
If W1b and W3 are in flight together, whichever merges first takes `0037` and the
other rebases — a revision number is a consequence of merge order, never reserved.

### Why W0 is first even though the session ranked matching first

The session ranked matching #1 and rewards #2. The sequencing inverts them for one
reason that is not a disagreement about value: **W0 contains no engineering.**
Earning, the ledger, the balance fold, the catalog, per-item progress, redemption
and the coordinator decision are all merged and reachable over HTTP. A
`reward_item` is listable only with a budget owner and `funded IS TRUE`, so Ann's
"points exist with nothing to spend on" is the schema enforcing an absent
decision, not a missing feature.

W0 converts a ratification into a working, student-visible reward loop in days,
during the weeks W1 is waiting on a privacy answer. Doing it second would leave
the platform's most complete capability switched off for no reason.

### Why W5 is listed but not scheduled

It is the single most valuable thing a recommendation card could carry — who is
speaking — and it is blocked twice over. `OQ-CBA-064` records that **no
student-authorized route returns a speaker id**, and `OQ-CBA-042` constrains the
shape any future one must take: it "must be assembled from confirmed or appeared
speakers and must **never** be reachable from invitation state." `OQ-CBA-051`
records that the appearance relation those words depend on **does not exist** —
nothing in the database records which speaker appeared at which event.

Listing it unscheduled is deliberate. A reader who notices the feed never names a
speaker should find the reason here rather than assume an oversight.

---

## 2. What each wave must not do

Stated per wave, because in each case the tempting shortcut is a specific one.

**W0** must not seed unfunded catalog rows to make the page look populated.
`WHERE funded IS TRUE` will hide them and the page will look broken rather than
honest. It also must not promote D7 by writing new numbers into
`smartmatch_domain.rewards` — those constants carry D7's tentative values
verbatim *because* D7 is tentative, and they move when the register says so.

**W1** must not store a column a decision has not authorized. An unanswered
question means the column is **absent**, not nullable-and-guessed — the argument
`OQ-E02` already makes for `disclosure_consent`, where writing the table before
the policy would invent the vocabulary the policy exists to choose.

**W2** must not add a factor to the CBA registry.
`assert_scoring_ready()` requires `implemented_scoring_keys() ==
APPROVED_SCORING_KEYS` exactly, and each current model's weights to sum to
1.0 ± 1e-9, so a fifth key would force re-approval of all four CBA weights and
silently re-interpret every speaker score already shown to a Connector. W2 gets
its own registry and its own version line — and it does so by **parameterising**
`factor_registry`, never by copying it. Two copies of `normalize_weights` is the
second source of truth that module's own docstring forbids, and duplication is how
the legacy deflation defect recurs.

W2 must also not invent a third and fourth scored factor to look thorough. Only
`student_interest_overlap` has data on both sides today; modality is an
*eligibility* filter precisely so `no_preference` never needs an invented value;
and availability and program affinity are declared `implemented=False` with
`proposed_weight = 0.0`, which is the registry's designed way to record an
intended shape without deflating anything.

**W3** must not widen `smartmatch_domain.consent`. That module governs contacting
an external professional whose address the research pipeline found;
`contact_channel` is scoped to `professional_id` and has no column for a student.
A student's own channel is a different consent posture and a different table —
the argument ADR-0014 makes for `disclosure_consent` not being
`smartmatch_domain.consent` widened.

**W4** must not divide an interest count by a registration count. Interests and
registrations are not nested sets, so a ratio between them is the "conversion above
100%" defect `speaker_pipeline` names — they are companion figures side by side.
It must also not transpose the `student_speaker_feedback` residual rule
unchanged: interests **overlap**, so the sum of per-term counts exceeds the number
of students and the residual has to be defined over *students*, not terms.

**W4** must not return a named student, and must not become a scoring input.
`OQ-CBA-053` is closed with "No": student feedback is an event outcome, not
evidence about who to invite next. `PROHIBITED_INPUTS` in `factor_registry.py`
names `unrelated_student_feedback` outright. W4 reports demand; it does not score
with it.

---

## 3. Decisions, owners, and what each one unblocks

Per the session's process note, **questions route through Ann and are put to Pia
and Lisa once as a group, never individually.** These carry the `OQ-SC-` prefix
proposed in the 12 September brief and are still **proposed, not registered** —
`cba-phase-deferred.md`'s last issued id is `OQ-CBA-064` and these are not CBA
questions.

| Id | Question | Owner | Unblocks | Safe default today |
|---|---|---|---|---|
| OQ-SC-01 | Is 100 / 300 / 600 / 1,000 at N = 3 the scheme, and what are the catalog rows? | Ann + Yuka, with Danny as D6 budget owner | **W0** | Catalog empty; `funded IS TRUE` holds it |
| OQ-SC-02 | What may a student be **asked**, and what may be **stored**? Is program of study an education record? | Privacy / records, with Ann — D8's neighbour | **W1**, then W2 and W4 | No profile table; no ranking |
| OQ-SC-03 | On what basis may SmartMatch **contact a student**, on which channels, revoked how? | Ann + records | **W3** | No student send path exists |
| OQ-SC-04 | **D8** — the disclosure-consent policy, and what "FERPA-aware" asserts | Privacy / legal / records (open as OQ-E01) | Check-in QR; any peer-visible surface | Counts only, no identifier in any response |
| OQ-SC-09 | Does a **skip** get stored? A recommender improves from negative signal; a stored "not interested" is also a record about a person | Ann + records, with OQ-SC-02 | W2's in-session re-ranking | **Session-only, never persisted** |
| OQ-SC-10 | Is a **weekly digest** the cadence, and who authors its copy? | Ann + Lisa | W3 | No digest |
| OQ-SC-11 | Is **what was recommended to whom** stored, so "what did we show this student on 3 October" is answerable? | Privacy / records | Nothing — but it decides whether W1's `DELETE` stays a hard delete or becomes a status flip | **Do not store.** The feed pins its inputs in the response instead |
| OQ-SC-12 | Is an event with **no mapped tag** worth a stated neutral value, and what value? | Program owner with Ann | Nothing; it changes how thin the feed looks | **No neutral.** Unknown, and the feed reports the count |
| OQ-SC-13 | May the **Event Host** (`volunteer`) read the aggregate demand figure, or Connectors only? | Ann, with D8 | Widens W4's role set | **Connectors only** (`{admin, coordinator}`) |

Four of these were raised by the design work rather than by the 12 September
brief, and two deserve a sentence each.

**OQ-SC-09** matters because the cheapest way to make a feed feel responsive is to
remember what a student rejected — and a stored rejection is a durable record of a
named person's stated disinterest. The safe default costs the recommender its
memory and discloses nothing, which is the correct direction to fail in.

**OQ-SC-12** is the largest product risk in the whole programme. An event with no
mapped tag is unscorable, so a thinly tagged pilot catalog produces a thin feed.
That is honest — it makes tag coverage *visible* rather than hidden — but it is
the thing most likely to make a demo disappointing, and it is worth deciding
before the demo rather than after. Answering it later costs a value, a `policy_id`
and a formula-version bump; it is not a redesign.

**OQ-SC-13 is a real reduction against what the session asked for**, and it is
listed rather than quietly applied. The session said the demand signal was
host-facing; `volunteer` is not in the engagement role set today, and `OQ-CBA-042`
already decided an Event Host does not learn who declined their own request. With
D8 open, deny-by-default says Connectors only. That should be the owner's call,
not an omission nobody noticed.

---

## 4. The success metric, fixed now

**Registrations per active student, and registration→attendance conversion.**

Not time in feed, not scroll depth, not session count. This is written down before
anything is built because the mechanics W2 borrows are the mechanics that optimize
for attention, and a team that ships them without naming the target will get
attention. The chapter does not want attention; it wants students in rooms.

`pipeline_record` already measures the second half of that — Attended cites a real
`attendance_record` or is refused — so the metric is answerable from evidence the
platform already keeps rather than from a new counter.

---

## 5. Sequencing constraints

The migration budget and the parallelism are stated in §1 with the wave table.
Three sequencing facts are worth repeating here because they are what let this
programme move while decisions are still open:

**W1a and W2a are unblocked today** and should start first. W2a in particular is
the long-pole review, because it edits an owner-approved file and its whole pin is
that `tests/unit/test_factor_registry.py` is not modified by a single line.

**W2b merges before Gate 1.** The route and the scoring path exist and *refuse*,
which is this repository's own idiom for a gated capability — the same shape as
the JWKS verifier that ships with no signature backend and the outreach path that
composes but cannot send. A closed gate is visible in a test; a checklist item is
not.

**W3 is independent of W1 and W2.** A digest of a student's *registered* agenda is
useful before any ranking exists, and shipping it early gives the reminder path a
production history before it ever carries a recommendation.

---

## 6. What this plan does not settle

- It does not ratify D7, and §3's OQ-SC-01 stays open until Ann and Yuka answer.
- It does not write `student_profile`'s columns. W1 describes a shape; OQ-SC-02
  decides the contents.
- It does not authorize a live send, a crawl, an upload, or a deployment.
- It does not close, reword, or promote any register row, and it does not enter
  the `OQ-SC-` questions in an existing register.
- It does not decide the visual design of anything. **D-0** stays partially closed
  for legacy-only work and **D-1..D-11** stay open; the prototype in
  [`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md) §Prompt 10
  is input to that conversation and closes none of it.
