# Pilot decisions — tentative, not ratified

**Status: TENTATIVE. None of the decisions below is organizationally ratified.**

Every entry in this file is a **development decision** recorded so that work can
proceed against something written down instead of against an assumption. Each is
held by the project's **current interim owner** and is **subject to IA West
review**, which has not happened. IA West may change, reverse, or reject any of
them, and nothing here should be quoted as an institutional position.

**Interim owner: DangT (`dangtran1022@gmail.com`).** This is a self-assignment
by the person doing the work, not an appointment by IA West — it records who to
ask about any decision below, and nothing more. It confers no institutional
authority, and IA West may replace the holder without reference to this file.

No interim-owner assignment existed anywhere in this repository before this
entry; the only other identity recorded for it is `@BrooklynD23` (see
`CODEOWNERS`, which states plainly that even that routing is unverified). That
`CODEOWNERS` entry is still unverified and this entry does not fix it.

**What "tentative" means here, precisely:**

- It is enough to unblock development and to stop the same question being
  re-litigated in every session.
- It is **not** enough to ship to real students, to publish, or to represent to
  an institution.
- Where a decision touches privacy, licensing, or identity, the tentative
  decision is deliberately the *conservative* one — the choice that is cheapest
  to reverse if IA West decides otherwise.

These decisions correspond to the items listed as blocked in
[`../plans/pr1-blockers-handoff.md`](../plans/pr1-blockers-handoff.md) §3.3 and
in [`../plans/remaining-foundation-r1-work.md`](../plans/remaining-foundation-r1-work.md).
Those documents remain the record of *why* each item was blocked; this one
records the interim position taken while the block stands.

---

## Q1 — CLOSED (handling decided; nothing erased)

**Decision: the archived legacy repository stays read-only reference material.**

- It is **not modified**.
- It is **not deleted**.
- Its **history is not rewritten**.

Q1 was the unassigned remediation owner for the six legacy paths carrying named
real people (recorded as **MM-A09** in
[`../migration/migration-manifest.yaml`](../migration/migration-manifest.yaml)).
It was the only severity-1 item, and it gates D9.

**Closing Q1 does not erase anything, and this document must not be read as if
it did.** The six paths naming real people **remain in that archive's git
history**. Deleting them at HEAD never removed them, and rewriting history was
rejected as a remedy rather than performed. What is decided is **how the archive
is handled** — read-only, unpublished, untouched — not that the exposure is
gone.

Consequences that follow directly:

- The archive is evidence for porting decisions, and nothing more. The existing
  rule in `README.md` ("Do not copy files") is unchanged.
- Because the history still contains those paths, **publishing the history would
  broaden the exposure**. That is the direct link to D9 below.
- If IA West later requires actual remediation of the archive, this decision is
  the thing to reopen. It was chosen because it is reversible; a history rewrite
  is not.

---

## D1–D9 — tentative, interim-owned, pending IA West review

| # | Item | Interim position | Still required from IA West |
|---|---|---|---|
| **D1** | Factor registry contents and golden case set (gate G1) | **Program owner named 2026-09-02:** Danny Tran (@dangt). G1 workshop may run. No substantive registry approved until workshop outputs are committed. Scoring continues fail-closed. | Approval of registry contents and golden cases in workshop. **Longest remaining product pole.** |
| **D2** | ELI formula parameters (decay half-life, window, caps) | The parameters implemented today stand as the tentative values. The open sub-question — whether committed future engagements count toward load — stays open; current behaviour refuses them explicitly rather than dropping them silently. | Confirmation or replacement of the parameters. |
| **D3** | Route-matrix provider terms and per-run call budget | Deferred with the rest of production procurement. No provider is contracted, so `travel_burden` has no live provider. | A procurement decision, once there is a deployment to procure for. |
| **D4** | Domain registration and DNS control | Deferred. See "Standing assumptions" — custom domains, DNS, and production Google Workspace are explicitly out of scope for the pilot. | Institutional IT ownership of a domain and its DNS. |
| **D5** | Retention periods per evidence table | Deferred to the retention implementation phase listed below. No retention class is enforced in code today. | A privacy / legal / records decision on periods per table. |
| **D6** | Rewards budget owner | **Named 2026-09-02:** Danny Tran (@dangt) as institutional budget owner; IA West Coordinator operational administrator; **$5,000** placeholder ceiling (pending institutional funding confirmation). D6 gate **closed** for pilot scope. | Currency confirmation; funded balance; catalog seeding when plan authorizes. |
| **D7** | Points-economy calibration | Decided tentatively, in full, below. | Review of the earn rate, the bands, and N. |
| **D8** | Disclosure-consent policy, and what "FERPA-aware" asserts | Decided tentatively, in full, below: minimum-disclosure handling, and **no claim of FERPA compliance**. | Formal institutional privacy review. Recorded below as an unmet adoption gate. |
| **D9** | Licensing / whether the repository may be open-sourced | Decided tentatively, in full, below: **private pilot, no open-source license, no `LICENSE` file**. **31 Aug 2026 ratification status: CANNOT CLOSE** (see `docs/decisions/2026-08-31-session-ratification.md`) — stays open for D9/licensing/open-source purposes, and is explicitly **non-blocking** for current private-repository engineering. | A licensing decision, which stays gated by the Q1 archive-history exposure above. |

---

## D6 — session-recorded working direction (31 August 2026)

**Ratification status:** **CLOSED — 2026-09-02 (pilot scope).** Danny Tran
(@dangt) named as institutional budget owner. $5,000 placeholder ceiling
ratified pending institutional funding confirmation. IA West Coordinator
remains operational administrator. D7 remains tentative.

**Fields this direction does not resolve** (blocked pending a formal design):
currency; institutional budget ownership; funded balance; budget lifecycle
and effective versions; concurrency; release/refund semantics; overlap
rules; item names, costs, and content; earn policy and calibration N;
fulfilment commitments; and read/redemption roles.

**Permitted implementation boundary:** the formal D6 record above, and
verification of already-authorized existing-schema/append-only guarantees
(e.g. `budget_owner_id NOT NULL`, `test_reward_item_rejects_a_null_budget_owner`)
only. If a database append-only guard is found absent, that gap is reported
rather than added under this session. **No new budget envelope, commitment,
reservation, redemption, earning, catalog, route, or UI behavior is
authorized by this record.** The $5,000 placeholder and the tentative D7
values below are not promoted to ratified figures.

## D7 — points and rewards (tentative)

### The numbers

| | Tentative value |
|---|---|
| Earning rate | **100 points per verified attendance** |
| Initial reward bands | **300 / 600 / 1,000 points** |
| Calibration N | **3** — the cheapest reward is reachable in three events |

The calibration property from
[`../architecture/engagement-model.md`](../architecture/engagement-model.md) §3
is `min(points_cost over listed items) ≤ N × points_per_event`. It holds here by
construction: **3 × 100 = 300**, which is the cheapest band exactly.

"Attendance alone" is the basis, deliberately. Streaks, logins, and referrals do
not earn points, so the property does not depend on a student's history and can
be evaluated identically for every student.

These numbers replace the legacy arithmetic (25 points per event against a
2,500-point cheapest reward — 100 events) that the 19–20 August 2026 stakeholder
test log identified as a catalog making a promise the program could not keep.

### Governance of availability and rules

Reward availability and point rules are **coordinator-managed**, with:

- **Versioning.** Every reward-catalog change and every point-rule change
  produces a new version rather than overwriting the old one.
- **Effective dates.** A rule version states when it takes effect. Points are
  earned under the rule version in effect at the time of the attendance.
- **Audit reasons.** Every change carries a stated reason and the identity of
  the coordinator who made it.
- **No silent balance editing.** A coordinator cannot set a student's balance.
  Corrections are made as **audited ledger adjustments** — an appended entry
  with a reason, visible to the student — so a balance is always the sum of
  entries that each explain themselves.

Two consequences that must survive into any implementation:

- **Existing redemptions retain their point-cost snapshot.** Repricing a reward
  does not reprice a redemption already requested against the old price.
- **A deactivated reward blocks new requests but stays visible on existing
  tickets.** Deactivation is not deletion; an in-flight fulfilment ticket must
  still be able to say what it is for.

**None of this exists in code.** There is no points ledger, no reward catalog,
and no attendance record in this repository today.

---

## D8 — disclosure and consent (tentative)

**Decision: minimum-disclosure handling.** Every disclosure surface discloses
the least data that makes the feature work, and discloses it only to the party
that needs it, only for as long as it is needed, and only with the subject's
consent where the subject is a student.

Concretely, as a tentative policy:

- QR check-in collects only what verifies attendance. It does not collect
  contact information as a side effect.
- A "people met" list is constrained by consent, and says so when consent limits
  what it can show, rather than silently returning a shorter list.
- A student's LinkedIn or contact visibility is **self-supplied** and
  **revocable immediately**. Nothing is scraped, inferred, or carried over from
  a third party.
- Mentor contact is **coordinator-mediated**. Students and professionals are not
  handed each other's contact details as a consequence of matching.

**This is explicitly NOT a claim of FERPA compliance.** This project does not
assert FERPA compliance, and no document in this repository should. What is
claimed is narrower and checkable: the handling described above is **aligned
with minimum-disclosure principles**. Whether that is sufficient under FERPA, or
under IA West's own records policy, is a legal and institutional question that
nobody here is qualified to answer.

**Unmet adoption gate:** *formal institutional privacy and records review has
not been performed.* It is a prerequisite for handling any real student data,
and it is not satisfied by this decision, by the code, or by anyone's good
intentions. Until it is done, the pilot runs on synthetic data only.

---

## D9 — licensing (tentative)

**Decision: private pilot. No open-source license. Deliberately no `LICENSE`
file.**

- A short, clearly-marked notice goes in `README.md` stating that this is a
  private pilot and is not open-source licensed.
- **No `LICENSE` file is added.** Its absence is a decision, not an oversight —
  the same position `CONTRIBUTING.md` already records, now with an interim
  decision behind it instead of an open block.
- The notice is a statement of intent, **not legal language**, and was not
  drafted or reviewed by anyone qualified to write licensing terms.

The reasoning is the Q1 link above: the legacy archive's git history still
contains paths naming real people, and publishing history that includes those
paths would broaden that exposure. Open-sourcing therefore stays gated on
remediation that has not happened, regardless of anyone's appetite to publish.

If IA West wants this repository public, the sequence is: institutional
licensing decision → archive-history remediation → then a `LICENSE` file. Not
the reverse.

---

## D-0 and the frontend decisions D-1..D-11 — deferred

**D-0 (assign a `DESIGN.md` owner) is deferred, not decided.**
[`../../apps/web/DESIGN.md`](../../apps/web/DESIGN.md) **stays unresolved** —
Part 2's eleven open decisions (D-1..D-11) remain open, and this document does
not answer any of them. They wait on the UI team.

Nothing in this file, and nothing in
[`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md), closes
D-0 or any of D-1..D-11. The prompt pack is input for that conversation; it is
not a design decision and it is not authoritative.

**The copied legacy frontend is development-only.** Its standing is:

- **Development-only.** Not deployed, and not demonstrated as the product.
- **Synthetic-data-only.** It must never receive live student data, under any
  circumstances, at any point before the privacy gate in D8 is satisfied.
- **Non-binding on the backend.** It must not constrain backend contracts. Where
  the copied frontend disagrees with `contracts/openapi/smartmatch.json`, the
  contract wins and the frontend is wrong.

The W-series sequencing in
[`../plans/remaining-foundation-r1-work.md`](../plans/remaining-foundation-r1-work.md)
is unchanged: W1 → W2 → W4 (provenance and truthful-state components) before W3
and W5.

---

## Follow-up implementation phases — explicitly NOT PR #3 code

The following are recorded as **future phases**. None of them is in PR #3, and
none of them exists in this repository today. Listing them here is scope
control, not a commitment to a date.

| Phase | What it covers | State in code |
|---|---|---|
| Dynamic matching | Match runs, ranked results, factor explanations, scenario comparison | Not implemented. Blocked on D1 / gate G1. |
| Rewards | Catalog, point ledger, redemption, fulfilment tickets | Not implemented. |
| Consent | Disclosure records, consent recheck, revocation | Not implemented. |
| Gmail / Calendar | Outreach send, delivery status, meeting proposals, calendar sync | Not implemented. No provider is connected. |
| Routing | Travel burden, route matrix, provider health | Not implemented. Blocked on D3. |
| Retention | Retention classes and enforced periods | Not implemented. Blocked on D5. |
| Research Scout | Source discovery, extraction, quarantine, entity resolution | Not implemented. Future concept. |
| Jarvis | Typed-intent accelerator over ordinary workflows | Not implemented. Future concept. |

What **is** implemented is the durable command path — unit-scoped import
submission, `202` plus a job id, job status, a resumable SSE event stream, and
re-drive / abandon for parked work. That is the whole of the live surface, and
`contracts/openapi/smartmatch.json` describes it in seven operations.

---

## Standing assumptions

These are assumptions the work proceeds on. They are true today, and each one
stops being an assumption the moment someone deploys anything.

- **There is no production deployment.** Nothing is hosted, and nothing is
  reachable by a student, professional, coordinator, or administrator.
- **There is no production data.** Every record anywhere in this project is
  synthetic. No live student data has ever been present, and none may be
  introduced before the D8 privacy gate is satisfied.
- **There is no rolling-migration compatibility requirement.** Because no
  deployment exists, migrations are not constrained to be compatible with a
  running previous version. **This assumption expires at the first deployment**
  and should be revisited then, not silently carried forward.
- **Custom domains and DNS are deferred.** See D4.
- **Production Google Workspace setup is deferred.** No Workspace tenant, no
  OAuth client, and no Gmail or Calendar authorization exists. Gate G5 (the
  Calendar authorization model) is untouched.

---

## How to change anything in this file

An entry here is superseded by an IA West decision, not by an engineering
preference. When IA West decides one of these, record the decision, say who made
it and when, and mark the entry **RATIFIED** or **SUPERSEDED** rather than
editing the tentative text away — the tentative position is the record of what
the code was built against in the meantime.
