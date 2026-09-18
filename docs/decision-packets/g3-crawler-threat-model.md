# G3 — crawler/event pipeline: threat model, allowlist, eval set, cost controls, vocabulary growth

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Which of the conditions the signed G3 and R3 artifacts attached to themselves —
egress enforcement, the ADR-0015 monetary-spend amendment, the unverified LLM
price assumption, and the S6a evidence pass — must be satisfied before a first
live fetch, and who signs each off.

## Owner(s) of the decision

- **G3 owner of record: Danny Tran, Development Lead (@BrooklynD23)** —
  [`../decisions/g3-crawler-decision.md`](../decisions/g3-crawler-decision.md) §0.1, §11.
- **Vocabulary growth owner: Danny Tran, Development Lead** — same file, §6.3.
- **T-13 egress open-risk owner: Danny Tran, Development Lead** — same file, §8.
- **R3 signature authority: Danny Tran (@BrooklynD23), Development Lead** —
  [`../decisions/owner-roster.md`](../decisions/owner-roster.md) row 5; threat
  model signed 2026-09-03.
- The ADR-0015 amendment (§4.1) is recorded as a "**New work item**" with **no
  owner named** in the G3 decision. No owner named.

## Current safe default in force

**Two sources conflict. Both are quoted; this packet resolves neither.**

Source A —
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§2, row 2, classifies the crawler/event pipeline as **blocked-on-stakeholder**:

> G3, the crawler threat model, the tool allowlist/eval set/cost controls, and
> the vocabulary-growth owner are not approved.

and §5.2 states:

> **Do not build yet:** no crawler route, crawl worker, crawl UI, network call,
> or actual tag vocabulary before G3 and the threat-model review.

Source B —
[`../decisions/g3-crawler-decision.md`](../decisions/g3-crawler-decision.md):

> **Status:** **SIGNED** 2026-08-29 by Danny Tran, Development Lead. No required
> field is blank. This artifact passes P6's G3 stop-gate.

and [`../security/crawler-threat-model-draft.md`](../security/crawler-threat-model-draft.md):

> **Status:** **SIGNED — design requirements approved 2026-09-03.** Not
> implemented; live fetch gated on S6a evidence pass.

**Conflict flagged.** The plan's §2/§5.2 text names four things as unapproved
that the signed artifacts record as approved: the allowlist (§2, Cal Poly Pomona
only, global and read-only at runtime, "Absent, empty, or unparsable allowlist ⇒
**fetch nothing**. Fail closed."), the eval set (§7, must-pass invariants MP-1
through MP-5 with a whole-set floor ≥90%), the cost controls (§3, §4 — "50
pages/job · depth 2 · 5 MiB/response … 300 s wall time"; "**Cost ceiling L21 =
$2.00 per job.** Tenant ceilings: $25/day, $250/month, 5,000 fetches/day"), and
the twelve approved vocabulary terms with a named growth owner (§6.2, §6.3). The
plan has not been amended to record the signatures.

**What the signed artifacts themselves still hold open,** in their own words:

- §4 — "**A3 (LLM price per page) is unverified** and must be confirmed against
  the actual provider."
- §4.1 — "Decided 2026-08-29: **amend ADR-0015** … **New work item; must land
  before cost ceilings are implemented.**"
- §8 — "**T-13 (egress policy) accepted as an open risk.** … Condition of
  record: **egress enforcement is not required for fixture-based work, and is
  required before the first live fetch.**"
- §9 — "**Pointing the adapter at live hosts remains prohibited**".
- Threat model header — "live fetch gated on S6a evidence pass."

## Options

Neutral; each has consequences. This packet selects none.

1. **Record the signatures and enumerate the residual conditions as a gate.**
   Confirm G3 and R3 are signed, and publish the list of conditions (egress
   enforcement, ADR-0015 amendment, A3 verification, S6a evidence) as the
   remaining live-fetch gate with an owner per line. *Consequence:* fixture-based
   work continues under the signed scope; live fetch stays prohibited until each
   line is signed off; the remaining-engineering plan needs a dated supersession
   note.
2. **Record the signatures and hold live fetch under a single named sign-off.**
   Delegate the four conditions to one owner who states, once, when they are all
   met. *Consequence:* fewer artifacts; a single point of accountability, and no
   per-condition audit trail for whichever of them a later reviewer questions.
3. **Treat the plan's §2/§5.2 classification as governing and re-review.** Rule
   that the 2026-08-29/09-03 signatures do not discharge §2 row 2.
   *Consequence:* the allowlist, eval set, cost ceilings, and vocabulary return
   to unapproved status, and the fixture-based work already scoped by the
   31 August ratification (see
   [`../plans/2026-08-28-g3-events-s3-s5-plan.md`](../plans/2026-08-28-g3-events-s3-s5-plan.md)'s
   amendment header) would need its own restatement; this packet does not say
   what happens to work already landed under it.

## Evidence needed to close

From
[`../plans/2026-08-28-g3-events-s3-s5-plan.md`](../plans/2026-08-28-g3-events-s3-s5-plan.md)
(stop-gate), two committed artifacts are required:

1. a **G3 decision** containing non-blank "approved agent evaluation set and
   pass/fail criteria; allowed tools and domains (explicit allowlist);
   extraction limits (pages, depth, bytes, wall time); per-run/per-tenant rate
   and cost ceilings; human escalation behavior; the named owner and versioning
   process for the closed tag vocabulary, with the approved initial terms";
2. an **R3 threat-model sign-off** — "the threat model no longer marked draft,
   signed by a **named security reviewer**, covering SSRF, DNS rebinding,
   redirect chains, private/link-local addresses, egress policy, response
   limits, parser isolation, credential handling, and audit/provenance."

For the residual conditions, the artifacts name their own evidence: a verified
A3 price against the actual provider (§4); the landed ADR-0015 amendment
distinguishing counting quota from monetary spend (§4.1); egress enforcement at
the fetch boundary (§8); and the S6a evidence pass (threat-model header).

## What stays blocked until closure

- Per [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
  §5.2 under option 3: "no crawler route, crawl worker, crawl UI, network call,
  or actual tag vocabulary".
- Per [`../decisions/g3-crawler-decision.md`](../decisions/g3-crawler-decision.md)
  §9 under every option: "**Pointing the adapter at live hosts remains
  prohibited**".
- Per §4.1: cost-ceiling implementation, until the ADR-0015 amendment lands.
- Per the threat-model header: any live fetch, until the S6a evidence pass.

## Source links

- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md) — §2 row 2, §5.2
- [`../plans/2026-08-28-g3-events-s3-s5-plan.md`](../plans/2026-08-28-g3-events-s3-s5-plan.md) — 31 August scope amendment, stop-gate
- [`../decisions/g3-crawler-decision.md`](../decisions/g3-crawler-decision.md) — §0–§11
- [`../security/crawler-threat-model-draft.md`](../security/crawler-threat-model-draft.md) — revision 4, signed status
- [`../plans/prep/g3-allowlist-candidates.md`](../plans/prep/g3-allowlist-candidates.md), [`../plans/prep/g3-eval-and-vocabulary-candidates.md`](../plans/prep/g3-eval-and-vocabulary-candidates.md), [`../plans/prep/g3-limits-and-policy-options.md`](../plans/prep/g3-limits-and-policy-options.md) — preparation inputs
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — row 5, R3 signature authority
- [`../architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md`](../architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md), [`../architecture/decisions/ADR-0010-event-temporal-model.md`](../architecture/decisions/ADR-0010-event-temporal-model.md), [`../architecture/decisions/ADR-0015-charge-quota-before-refusal.md`](../architecture/decisions/ADR-0015-charge-quota-before-refusal.md)
