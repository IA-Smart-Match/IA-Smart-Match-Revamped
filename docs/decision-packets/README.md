# Workshop decision packets

> **Decision packets — docs only. They authorize no implementation. Every
> register row named in them remains OPEN.**

**Created:** 2026-09-18.

Each packet frames one gated item so that the named humans can decide it. A
packet states the decision, names the owners **as the source documents name
them** (or records "No owner named"), quotes the safe default currently in
force, lays out options neutrally with their consequences, lists the closure
evidence the register or plan already requires, and says what stays blocked.

## What a packet is not

- A packet **does not recommend** an option, a weight, a threshold, a value of
  N, or a role list. It frames; humans decide.
- A packet **closes no register row and changes no status.** Closure requires
  what the registers require: "an attributed, dated decision artifact plus the
  evidence named in the row"
  ([`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md)).
- A packet is not closure evidence. Per the same register: "A plan, prototype,
  feature flag, or unwired implementation is not closure evidence."
- A packet makes no production-readiness claim.

## Index

| Packet | Decision framed | Register rows / gates |
|---|---|---|
| [`g1-factors-weights.md`](g1-factors-weights.md) | D1/G1 matching registry — factors, weights, golden cases, program owner, weight governance | `remaining-engineering-implementation-plan.md` §2 row 1, §5.1; P5 stop-gate |
| [`g3-crawler-threat-model.md`](g3-crawler-threat-model.md) | G3 crawler/event pipeline — threat model, tool/domain allowlist, eval set, cost controls, vocabulary-growth owner | §2 row 2, §5.2; P6 stop-gate; R3 |
| [`d6-d7-rewards.md`](d6-d7-rewards.md) | D6 budget owners and funding; D7 calibration N (ADR-0013) | OQ-SC-01; §2 row 3, §5.3; P7 stop-gate |
| [`metrics-authz.md`](metrics-authz.md) | Metrics role-gating under ADR-0014 — aggregate versus drill-down roles | OQ-SE-08, OQ-SC-13, OQ-CBA-042; §2 row 4, §5.4 |
| [`a1b-idp.md`](a1b-idp.md) | A1b live identity-provider wiring | OQ-A1b-001 to -006; P2 stop-gate |
| [`oq-se-01-02-student-ranking.md`](oq-se-01-02-student-ranking.md) | Student scoring registry and the wildcard contract | OQ-SE-01, OQ-SE-02 |

## Conflicts these packets surface

Four packets record a disagreement between
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
(dated 2026-08-28 in its planning baseline) and later decision artifacts. The
packets show both sides and resolve none of them:

- **G1** — the plan classifies matching as blocked-on-stakeholder;
  [`../plans/workshops/g1-workshop-output-worksheet.md`](../plans/workshops/g1-workshop-output-worksheet.md)
  records "RATIFIED — 2026-09-03. Gate G1 / D1 closed."
- **G3** — the plan says the allowlist, eval set, cost controls, and
  vocabulary-growth owner "are not approved";
  [`../decisions/g3-crawler-decision.md`](../decisions/g3-crawler-decision.md)
  is signed 2026-08-29 and
  [`../security/crawler-threat-model-draft.md`](../security/crawler-threat-model-draft.md)
  signed 2026-09-03, each with residual conditions of its own.
- **Metrics** — the plan says "current intentional ungating remains until the
  explicit product/security decision";
  [`../decisions/metrics-authorization-decision-draft.md`](../decisions/metrics-authorization-decision-draft.md)
  is "CLOSED — 2026-09-02", and the code implements it.
- **A1b** — the plan sequences replacing the unavailable-login state with
  institutional sign-in;
  [`../decisions/pilot-login-decision-2026-09-04.md`](../decisions/pilot-login-decision-2026-09-04.md)
  substitutes a pilot database-credential login and defers production SSO.

**Updated 2026-09-18.** All four conflicts above now carry dated supersession
notes inside the plan itself — at §2 and at §5.1 (G1), §5.2 (G3), §5.4
(metrics) and Wave C item 4 (A1b) of
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md).
Those notes quote each later artifact's own status words, leave the original
plan text intact, and end with what is still open. They resolve nothing: the
reconciliation remains the owners' decision.

Reconciling the plan text with these artifacts is itself a decision for the
owners, and each affected packet lists it under evidence needed to close.
[`../plans/README.md`](../plans/README.md) states the discipline: "When a dated
plan is superseded or its implementation state changes, preserve the original
evidence and add a dated supersession/current-state note pointing to the new
authority."

## Related registers and indexes

- [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md) — canonical OQ-SC / OQ-SE register
- [`../plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md) — OQ-CBA register
- [`../plans/open-questions/a1b-live-idp-deferred.md`](../plans/open-questions/a1b-live-idp-deferred.md) — OQ-A1b register
- [`../plans/README.md`](../plans/README.md) — planning navigation authority
- [`../architecture/decisions/README.md`](../architecture/decisions/README.md) — ADR index
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — named owners
