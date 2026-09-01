# P9 Gate B — published contact fields: decision worksheet

**Status:** **WORKSHEET — PREPARATION ONLY. This document does not approve
anything and is not a decision artifact until a human completes and signs it.**
**Ratification status (31 August 2026):** **RECORDED — GATE INCOMPLETE.**
Session approver Danny Tran (`dt110202@gmail.com`) recorded a **working
direction** — see §0.5 below and
`docs/decisions/2026-08-31-session-ratification.md`. It is preserved as
recorded direction, **not** as an ingestion branch or implementable behavior:
the §8 signature and every field it requires remain blank, and the
Gate B decision matrix in §0 is unchanged by it.
**Gate:** P9 Gate B (`docs/plans/2026-08-28-pilot-columns-plan.md` §Stop-gates).
**Prepared:** 2026-08-30, by an agent, from the sources in §7.
**Deciders required:** Dr. Wang (program owner) **and** a named privacy owner.
**Changes no code.**

> An agent assembled the options and recommendations below. **Every decision
> field is blank and must stay blank until the named humans fill it.** An agent
> filling a field here would be inventing an approval, which is the
> `fallbackFatigue` defect one abstraction level up.

---

## 0. Blocking blanks — UNRESOLVED

These four fields are the gate. None may be filled by an agent.

- **§0.1 Program owner of record** — _(blank)_
- **§0.2 Privacy owner of record** — _(blank)_ · **no such role is named
  anywhere in the repository today.** See §6.
- **§0.3 Per-field collect/drop decisions** — _(blank; three fields, §2)_
- **§0.4 Signature** — _(blank; §8)_

## 0.5 Session-recorded working direction (31 August 2026) — RECORDED — GATE INCOMPLETE

**This section records a direction. It does not fill §0 or §8.**

The session recorded that, for the pilot, the system should collect the
Public URL, Point(s) of Contact, and contact information (email/phone) when
available, so the IA West Coordinator can reach out to agents as a follow-up
when needed. The decision still requires the formal human sign-off recorded
below in §8; this paragraph is the working choice carried forward for
review, not a substitute for it.

**Unresolved fields — none of which this record fills:**

- Named privacy owner and the collection purpose (§0.2, §8).
- Minimization and retention rules (§8).
- Correction and deletion paths (§8).
- Named viewer and exporter roles (§8).
- The per-field collect/drop decisions themselves (§0.3, §2) and the §0.4/§8
  signature.

**Permitted implementation boundary, restated from the design:** static
HTTPS URL-shape validation only (the four rules in §V2 of
`docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`).
Raw URL persistence remains blocked unless a separately approved host/path
projection exists. Published contact names, email addresses, and phone
numbers **may not be collected, persisted, quarantined, copied into a
finding, sent to a model, exported, or rendered** until Gate B records every
item listed above with the required signatures. This direction does **not**
become an ingestion branch or implementable contact-collection behavior by
being recorded here.

## 1. Why this gate is worth clearing first

Gate B is the cheapest open gate in the portfolio: **two questions, both of
which the program owner is likely to already hold the answers to.** It is also
disproportionately load-bearing. Three separate pieces of work are stopped
behind it:

| Blocked item | Where | What it is waiting for |
|---|---|---|
| **T-14 — incidental PII** | `docs/security/crawler-threat-model-draft.md` | R3's own text says T-14 **cannot close** until Gate B decides collect-or-drop per published contact field with a privacy owner. T-14 not closing is one of the adversarial review's stated reasons not to sign R3. |
| **MP-4 — never emit personal contact data** | `docs/decisions/g3-crawler-decision.md` §7 | MP-4 is currently an **absolute** prohibition scoped explicitly to "while P9's contact-field decision is open". Gate B decides whether it stays absolute or acquires a permitted set. |
| **Stage 0 §4 schema review** | `docs/plans/prep/campus-event-discovery-capability.md` §7 | Stage 0 lists "get the contact-field group decided" as one of its four buildable-now items. It is the only one of the four still open. |

Note the shape of the coupling: **Gate B does not need to say "collect" to
unblock anything.** A decision of "drop all three" closes T-14, makes MP-4
permanent rather than provisional, and finishes the Stage 0 schema review — at
lower cost than any collect option. The gate is blocking because it is
*undecided*, not because it is *restrictive*.

## 2. The three fields — decide each SEPARATELY

`columns.yaml` currently carries all three under `events.optional` with no
fixtures and no ingest wiring. `smartmatch_worker.handlers` calls
`validate_columns(..., required=(), optional=())`, so the ratified contract does
not constrain imports today; wiring it is card W1 and is deliberately separate.

### 2.1 `Public URL`

A link to a public event page. **Not personal data.**

| Option | What it means | Consequence |
|---|---|---|
| **B1a — Collect** *(recommended)* | Ratify as an optional events column; add valid/invalid fixtures and URL validation. | Requires the validation rules in §3. `Opportunities.tsx` already reads this field on the legacy path, so dropping it removes a value the UI reads today. |
| B1b — Drop | Remove from `columns.yaml` optional; update README and fixtures. | The legacy `Opportunities.tsx` read becomes dead; the event-discovery pipeline loses its natural canonical-URL column and would need another home for `event_source_observation.canonical_url`. |

**Recommendation: B1a — collect.** It is the only one of the three that is not
personal data, it is already consumed by existing UI, and the discovery design
needs a canonical URL column regardless. The privacy question here is not
"whether", it is the §3 validation rules — which are a security matter, not a
disclosure one.

> **Caveat the decider should see:** a URL is not automatically non-personal.
> A link of the form `.../people/jane-doe` or a private calendar subscription
> URL with an embedded token is both. R3's **T-06** requires provenance URLs be
> redacted or tokenized *on write* for exactly this reason. Choosing B1a should
> be read as "collect public event-page URLs", not "collect any URL".

### 2.2 `Point(s) of Contact (published)`

A named human contact. **Personal data**, even when the name is published.

| Option | What it means | Consequence |
|---|---|---|
| **B2a — Drop** *(recommended)* | Remove the column. No named contacts ingested. | MP-4 stays absolute. T-14's minimization control becomes trivially satisfiable and testable. Costs: a coordinator wanting to reach an event organizer has no field for it. |
| B2b — Collect, organizational names only | Permit **office/unit names** (`Campus Programs Office`) and forbid individual persons. | Captures most of the operational value with much less personal data. **But** "is this string a person or an office?" is not machine-decidable, so the control is a human review rule, not a validation rule — it will leak individuals. See §5. |
| B2c — Collect, individuals permitted | Full collection with purpose, minimization, retention, correction path, and named viewers recorded per plan P9. | Requires all five ADR-0014 fields answered, plus a subject correction path that does not exist today. Highest cost, and it is the option that most complicates R3 T-14 and the discovery review UI. |

**Recommendation: B2a — drop, for the pilot.** Reversible in one direction only
in practice: adding the field later is a schema addition; removing it after
collection means deleting real personal data from real exports. Dropping now
costs the least and forecloses the least.

> If B2b is chosen, the decider should know it is **not enforceable by
> validation** and should be recorded as a review rule with an expected leak
> rate, in the same spirit as G3 §6.1's "quarantine volume is measurement, not
> failure".

### 2.3 `Contact Email / Phone (published)`

Direct contact details. **Personal data, and the highest-risk of the three.**

| Option | What it means | Consequence |
|---|---|---|
| **B3a — Drop** *(strongly recommended)* | Remove the column. | MP-4 stays absolute; T-14 minimization is satisfied at the schema level rather than by a runtime rule. |
| B3b — Collect, role addresses only | Permit `programs@example.edu`; forbid personal addresses. | Same non-decidability problem as B2b, and worse: `j.doe@example.edu` is a role address at some institutions and a personal one at others. |
| B3c — Collect, unrestricted | Requires the full ADR-0014 set plus a documented outreach boundary. | ADR-0014 is explicit that **"published" provenance is not consent** for platform disclosure or outreach. Collecting here does not authorize using it. |

**Recommendation: B3a — drop.** Three independent reasons converge:

1. **ADR-0014** already separates disclosure consent from contact consent; a
   published address is provenance, not consent.
2. **The prompt-injection assessment §2.5** documents that the *legacy* system
   wrote a model-supplied `contact_email` straight into a display field labelled
   "Contact Email / Phone (published)" — **this exact column**. That is a
   demonstrated injected-content-to-human-trust path, not a hypothetical one.
3. The discovery pipeline is crawler-fed. A collected contact column plus an LLM
   extractor is the shape that produced the legacy defect.

## 3. Validation rules — required only if any field is collected

Carried from the prep document and extended with what R3 has since found:

- **URL:** require HTTPS; reject `javascript:`, `data:`, and internal schemes;
  reject userinfo (`https://user:pass@host/`); apply T-06's on-write redaction so
  a token-bearing subscription URL is never persisted raw.
- **All contact fields:** never merged into event title, tags, or metric
  drill-down. Note that R3's revision-3 work corrects a false claim here — the
  domain does **not** structurally prevent text from reaching a title;
  `normalize_title` accepts any non-blank string. This must be an adapter or
  persistence validation, not an assumed property.
- **Extractor output may never populate a contact field.** Human/import origin
  only, per T-11 control C-4.
- **Redaction rules for exports and minimum-disclosure roles** must tie to the
  metrics-authz decision (P1), which is itself still blocked. If any contact
  field is collected, **Gate B acquires a dependency on P1** that it does not
  have under the drop options.

## 4. What the decision unblocks, per outcome

| Outcome | T-14 | MP-4 | Stage 0 §4 | New dependencies |
|---|---|---|---|---|
| Drop all three | Closes at schema level | Becomes permanent | Complete | None |
| Collect `Public URL` only *(recommended set: B1a + B2a + B3a)* | Closes; URL handled under T-06 | Stays absolute for contact data | Complete | None |
| Any contact field collected | Needs retention, purge, viewer, and export rules before it can close | Must be narrowed, not dropped | Complete | **P1** (minimum-disclosure roles); a subject correction path |

## 5. The question behind the question

Both B2b and B3b ("organizational only") are attractive and **neither is
machine-enforceable**. Whether `programs@example.edu` or `Campus Programs
Office` denotes a person is a judgment about the world, not a property of the
string. If the owner wants them, the honest form is:

> collect, with a human review rule, an explicit acceptance that individuals
> will sometimes be captured, and a purge path for when they are

— not a validation rule that will be believed to be doing more than it does.
That is the same failure shape as the legacy `_sanitize_for_prompt` docstring
(`prompt-injection-assessment.md` §2.1): a control whose stated scope exceeds
its actual scope stops reviewers from looking.

## 6. The privacy owner does not exist yet

P9 Gate B requires "Dr. Wang **+ privacy owner**". **No privacy owner is named
anywhere in this repository.** A term search across `docs/` finds the role
referenced as a requirement and never as a filled field.

This is a second, smaller blocking blank, and it is worth surfacing separately
because it has a cheap resolution the other blanks do not: **if all three fields
are dropped, no privacy owner is needed to close this gate** — there is no
personal data to own. Only the collect options require the role to be filled
first.

**Do not read this as a reason to prefer dropping.** It is a note that the two
questions are not equally expensive to answer, and the decider should know which
one drags a vacant role in behind it.

## 7. Sources

- `docs/plans/2026-08-28-pilot-columns-plan.md` — Gate B text, branches, card W1
- `docs/pilot-data/event-contact-fields-decision-prep.md` — field table, synthetic samples
- `docs/pilot-data/columns.yaml` — `open_questions`, second item
- `docs/architecture/decisions/ADR-0014-disclosure-consent.md` — disclosure ≠ contact consent
- `docs/decisions/g3-crawler-decision.md` §7 — MP-4
- `docs/security/r3-technical-review-findings.md` — T-14 and its Gate B dependency
- `docs/security/prompt-injection-assessment.md` §2.5, §3 A6 — the legacy contact-field path
- `docs/plans/prep/campus-event-discovery-capability.md` §7 — Stage 0 schema review

## 8. Decision record — TO BE COMPLETED BY THE NAMED HUMANS

```
Program owner (name, role):        ____________________
Privacy owner (name, role):        ____________________
                                   (required only if any field below is "collect")
Date:                              __________

Public URL                          [ ] collect   [ ] drop
Point(s) of Contact (published)     [ ] collect   [ ] drop
Contact Email / Phone (published)   [ ] collect   [ ] drop

If any field is "collect", the following are ALSO required and this artifact is
incomplete without them:
  Purpose:            ____________________
  Minimization rule:  ____________________
  Retention/purge:    ____________________
  Correction path:    ____________________
  Who may view:       ____________________
  Who may export:     ____________________

This decision closes P9 Gate B. It does NOT close P9 Gate A (board_role), which
is decided independently.
```

**No agent may fill any field in §8.**
