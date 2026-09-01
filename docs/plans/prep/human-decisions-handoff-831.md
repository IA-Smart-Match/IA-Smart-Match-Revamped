# What needs a human — decision handoff, 2026-08-31

**Status:** **HANDOFF ONLY.** This document approves nothing, ratifies nothing,
signs nothing, and fills no owner field. **Changes no code.**
**Forward link:** the working decisions recorded below were formally
ratified, to the extent each was implementable, in
`docs/decisions/2026-08-31-session-ratification.md`. That record — not this
one — is the signed, dated authority trail; this document remains input
evidence only and must never be relabeled as a signed decision artifact.
**Baseline:** branch `friday-deliverable-828` at `9bd87d4`; working tree clean.
**Audience:** the humans who can supply what engineering cannot.

> **Why this document exists.** Engineering has run out of work it is permitted
> to do. Every remaining item in the P1–P9 portfolio is blocked on a decision, a
> name, a signature, or a purchase — none of which an agent may supply. This is
> not a status report (see `status-report-830.md`) and not a per-plan register
> (see `blocked-work-register-830.md`). It is the shortest possible list of
> things a person must do, ordered by how cheap they are to do.

---

## 0. How to read this

Each item states the **question**, **who can answer it**, **what it unlocks**,
and **what it costs to keep waiting**. Nothing here is a recommendation about
*which way* to decide — where a prepared worksheet already carries a
recommendation, that is noted and the worksheet is cited, but the choice
remains open.

**Three things that are true of every item below and worth stating once:**

- Nothing is silently broken while these stay open. Each blocked capability
  fails closed and is pinned by a test (cited per item). The cost of waiting is
  schedule, not correctness.
- A prepared worksheet is not a passed gate. Several items have complete
  paperwork waiting on a single signature.
- Four of these are not decisions at all — they are *names*. See §1.

---

## 1. The cheapest four: name a role (≈ four sentences, one sitting)

Four documents reference a role as though it already exists. Each was written
as a dependency by someone who assumed someone else had named it. **No workshop
is required; no analysis is required. Each is one sentence naming one person.**

| Role | Referenced in | Unlocks |
|---|---|---|
| **Privacy owner of record** | P9 Gate B worksheet §0.2 — "no such role is named anywhere in this repository" | P9 Gate B, R3 finding T-14, MP-4 scope |
| **Program owner (D1/G1)** | `docs/plans/workshops/g1-factor-registry-workshop-packet.md` — "Blocking owner: program owner (name TBD)" | All of P5 — the longest pole in the portfolio |
| **Rewards budget owner (D6)** | `docs/decisions/pilot-decisions.md` D6 — names no budget holder, and no budget exists | All of P7 |
| **Product owner (opportunities)** | P8 stop-gate — no artifact exists under `docs/decisions/` at all | All of P8 |

**Cost of waiting:** P5, P7, P8 and P9 Gate B are all queued behind a name
rather than behind a decision. P5's workshop packet is already complete and
could run the day a program owner is named.

**Note on the rewards budget owner:** naming the role and funding it are
separate acts. D6 records that no budget exists; a named owner with no budget
still unblocks the *design* conversation, but not S8/S9 delivery.

---

## 2. P9 Gate B — the cheapest open gate (three choices + one signature)

**Question:** for the pilot, does the system collect each of these event contact
fields — (a) Public URL, (b) Point(s) of Contact, (c) Contact Email/Phone?

**Decision direction for this handoff:** the system should collect the Public URL,
Point of Contact, and contact information if available. This allows the IA West
Coordinator to reach out to agents as a follow-up when needed. The decision
still requires the formal human sign-off recorded in the worksheet; the text
above is the working choice being carried forward for review.

- **Where:** `docs/decisions/p9-gate-b-contact-fields-worksheet.md`. Every
  decision field and the §8 signature are `_(blank)_`.
- **Who can answer:** Dr. Wang **and** the privacy owner (§1) — the plan names
  both (`2026-08-28-pilot-columns-plan.md` §Gate B). **Except** that a "drop all
  three" outcome requires no privacy owner at all and closes the gate cleanly.
- **Prepared:** the worksheet carries a per-field recommendation (collect the
  URL; drop the other two for the pilot). It remains a recommendation.
- **Unlocks:** P9 Gate B branch selection; R3 finding T-14; MP-4's final scope;
  the Stage 0 §4 schema review.
- **Cost of waiting:** this is the highest-leverage-per-minute item in the
  portfolio. It also transitively holds the R3 threat model, which holds P6.
- **Coupling to watch:** if any contact field *is* collected, P1 gains a new
  dependent (minimum-disclosure roles for contact data). "Drop" keeps P1
  uncoupled.

---

## 3. R3 — the reviewer-authority question (a fact about the org, not the repo)

**Question:** is the Development Lead the same role as the "named security
reviewer" the R3 stop-gate requires?

**Current human fact for this handoff:** Yes — Git: `dt110202@gmail.com`.
The Development Lead is the named security reviewer for this project unless
someone explicitly designates a different authority. This is an org-level fact,
not a repository-level recommendation.

- **Where:** `docs/security/crawler-threat-model-draft.md` signature block —
  reviewer name and date both blank; revision 4, unsigned. Pinned by
  `test_g3_threat_model_remains_unsigned_draft`.
- **Two honest resolutions:** (1a) the Development Lead *is* the reviewing
  authority, and the signature block should say so explicitly; or (1b) a
  separate reviewer is required and the field stays blank until one is named.
- **Who can answer:** whoever defines role authority for this project at IA
  West. An agent cannot choose, because the answer is a fact about the
  organization.
- **Why it matters:** signing under the wrong role produces an artifact that
  *looks* like it cleared the gate. Answering 1b is not a failure outcome —
  it is a correct outcome that costs a name.
- **Unlocks:** everything in P6 past the R3 gate. The G3 half of that gate is
  already signed (2026-08-29).

**Four technical dimensions inside R3 also await human facts**, and no
signature should be read as covering them until they are filled. These are not
paperwork chores; they are the remaining substantive security facts the threat
model still lacks. For this handoff, the working decisions are:

- **T-07:** model-agnostic policy. The platform will allow OpenRouter and Groq
  as viable model entry points, with all tools permitted within the pilot scope.
  Data retention is not a blocker for this pilot because the data stays within the
  student/user scope and does not include coordinator outreach data outside the
  program's follow-up workflow.
- **T-13:** the agent runs behind a guardrail and the platform will implement a
  project-specific harness for all model calls; the preferred enforcement point is
  at app runtime before outbound call dispatch.
- **T-19:** approver is `dt110202@gmail.com`; proposer is the same human plus
  Chau / Starey Night (Janice) and each of our respective agents as delegated
  proposal actors.
- **T-23:** model-agnostic is the goal. The project will choose the cheapest
  capable model(s) by task and latency profile, with a balance between speed,
  performance, and cost; data-retention terms are not material to the pilot scope
  for IA West.

| Finding | Missing fact |
|---|---|
| **T-07** | model-agnostic tooling decision is in place, with OpenRouter and Groq allowed; all tools remain permitted within the pilot scope |
| **T-13** | the egress enforcement point is the project guardrail/harness, enforced at app runtime before outbound dispatch |
| **T-19** | approver is `dt110202@gmail.com`; proposer is the same human plus Chau / Starey Night (Janice) and the relevant agents |
| **T-23** | model choice remains task- and latency-based; provider-retention terms are not material to the IA West pilot scope |

T-27, T-28 and T-29 are deliberately labelled **CANNOT CLOSE** rather than
signed as requirements they do not meet. That labelling is correct and should
survive any future signing pass.

---

## 4. ADR-0015 Amendment A1 — ratification

**Question:** ratify or reject Amendment A1 (quota-counting vs. monetary-spend
reservation semantics).

**Summary of the proposal:** Amendment A1 says quota counting and monetary spend
reservation are not the same control. The practical rule is that a command route
must charge quota before it refuses the request, so cheap, rejected requests do
not slip through unmetered while successful work is counted. In other words, the
system treats a denied request as a real cost to the caller rather than a free
probe. This is the policy choice that makes the limiter honest and prevents a
caller from exhausting the system by spraying cheap refusals.

- **Where:** `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`,
  §Amendment A1. Status is **PROPOSED**; the approver line is deliberately blank.
- **Who can answer:** the ADR approver of record.
- **Unlocks:** T-08's conservative-reclaim direction in the threat model depends
  on this amendment landing.
- **Note:** the ADR's own `**Status:**` line correctly still reads a bare
  `Accepted`, and the README index's Amended column correctly still reads `—`,
  because ratification has not happened. Both are coupled to
  `test_an_amended_adr_is_marked_amended_in_the_index`. Do not "tidy" either
  before ratification — the test is the guard, not a nuisance.

---

## 5. P1 — metrics authorization (a workshop, four bounded questions)

**Question:** what are the aggregate-vs-row-level read rules for metrics?

**Decision direction for this handoff:** choose **Option 1 — allow aggregates only
to unit members**. Under this model, a student sees their own class or unit
summary, a school coordinator sees only the school summary, and the IA West
Coordinator sees cross-unit portfolio metrics. Row payloads remain restricted and
are not exposed to all active unit members.

This is not a code bug; it is a policy decision. The current system intentionally
allows any active unit member to read aggregates and drill-down rows with no
separate rule on row-level sensitivity. The issue is whether imported row payloads
are considered as open as a summary metric, or whether aggregate access should stay
broader than row-level disclosure. The working decision here is the lower-risk,
role-scoped aggregate path: summary metrics remain visible by unit membership, while
row-level disclosure stays behind an operational role boundary.

- **Where:** `docs/decisions/metrics-authorization-decision-draft.md` poses four
  questions and answers none.
- **Who can answer:** product **and** security, together — this one genuinely
  needs the meeting.
- **Cost of waiting:** current behavior is intentionally ungated and pinned by
  `tests/authz/test_policy_matrix.py::INTENTIONALLY_UNGATED_OPERATIONS`. Nothing
  is silently wrong, but nothing can be tightened either.
- **Leverage:** the portfolio index already flags this as high leverage per unit
  of decision spent.

---

## 6. P2 — not a decision at all: this is procurement

**This item is on the list to correct how it has been filed.** A1b institutional
sign-in has been queued as though a decision artifact were pending. It is not.

- **Where:** `docs/decisions/a1b-idp-configuration-worksheet.md` — "**Status:**
  UNFILLED — this is a blank worksheet". Every field is blank because **no IdP
  tenant exists yet**.
- **What is actually needed:** the IdP is being set up on Google Cloud. Once the
  tenant exists (development/test tenant acceptable and expected; live production
  SSO is out of scope), the issuer URL, audience, JWKS approach, key-rotation
  policy, and the full PKCE client-flow contract can be recorded.
- **Decision for this session:** **in scope; proceed**. The work is approved to
  continue once the IdP tenant is provisioned and the worksheet is filled.
- **Who can act:** whoever can provision the Google Cloud IdP tenant and record
  its final configuration.
- **Cost of waiting:** cards A1–A4 have been repeatedly queued behind a workshop
  that cannot produce an issuer URL. Card A0 (audit + worksheet) is already
  landed and was the only card runnable without the tenant.

---

## 7. Remaining, as their owners become available

For each of these, the available human choice is either to confirm the current
holding position, to define a new policy, or to reject the work as out of scope.
The operative question is not whether the code is broken; it is whether the owner
wants the work accepted, clarified, or renounced.

- **P9 Gate A (`board_role`)** — decision recorded: `board_role` is
  relationship-scoped, not a single intrinsic attribute. It varies by context and
  role experience, such as a person serving on a board for one program while
  appearing only as a guest speaker in another. The system should therefore treat
  `board_role` as contextual and time/relationship dependent rather than a single
  universal label. `columns.yaml` remains the current holding position until the
  final relationship model is recorded, but the session decision is to treat it as
  context-bound and not globally fixed.
- **P8 opportunities definition** — decision recorded: the opportunities model is
  a list of programmatic engagement opportunities, including hackathons,
  datathons, competitions, guest lecturer events, and school events. These are
  the opportunities our coordinator can send connections or volunteers to
  represent the institution. This defines the canonical opportunity set the
  system is expected to support.
- **P7 D6/D7 rewards** — needs both the owner from §1 *and* a funding decision.
  Working direction: owner is `dt110202@gmail.com`; rewards should be capped at a
  maximum reward amount and managed under a defined budget. The budget is treated
  as IA West Coordinator-controlled, with a working placeholder ceiling of
  $5,000 while the final funding model is confirmed.
- **P6 Stage 0 scope confirmation** — decision recorded: **in scope; proceed**.
  The iCal and JSON-LD parser work is approved to continue from the fixture-only
  stage to the in-scope implementation path. The P6 owner has confirmed the
  work is in scope for the current effort. The parsers are exported from nothing
  and imported by nothing outside their own tests, so the exposure remains a
  process gap only until the broader implementation lands.

---

## 8. Outside this repository

- **CP-PII — legacy PII remediation.** Six paths of real people's data live in
  `BrooklynD23/Nebiux-Team-IA-West-SmartMatch`, a different repository. Per
  `docs/plans/critical-path-legacy-pii.md`, it **has no owner.** Nothing in this
  repository can close it, and no work here reduces it. Raised because it is the
  only item on this list involving real personal data.

  **Current disposition for this handoff:** the source repo is archived and
  private, and the Vercel shutdown has been directed by the Development Lead
  (`Git: dt110202@gmail.com`). Access is removed from everyone, and this issue
  is held as out of scope for the active delivery path and should not block
  current work in this repository.

---

## 9. One clarification that is not a request

`docs/decisions/pilot-decisions.md` records "Interim owner: DangT … **This is a
self-assignment**", unratified and pending IA West confirmation. It is listed
here only so it is not mistaken for institutional authority when reading any of
the items above — several of which would otherwise appear to have an owner
available.

---

## 10. Sources

Read directly from the working tree at `9bd87d4` on 2026-08-31:

- `docs/plans/status-report-830.md` §§2, 5, 6
- `docs/plans/prep/blocked-work-register-830.md` §§0–3
- `docs/plans/2026-08-28-plan-portfolio-index.md`
- `docs/decisions/{p9-gate-b-contact-fields-worksheet,a1b-idp-configuration-worksheet,metrics-authorization-decision-draft,pilot-decisions,g3-crawler-decision}.md`
- `docs/security/{crawler-threat-model-draft,r3-technical-review-findings}.md`
- `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`
- `docs/plans/workshops/g1-factor-registry-workshop-packet.md`
- `docs/plans/critical-path-legacy-pii.md`
