# R3 signing decisions — 2026-09-03

**Status:** **RATIFIED — SESSION POLICY** (engineering record; design requirements only).
**Ratifier:** Danny Tran (@dangt), Development Lead / Security Reviewer (authority 1a).
**Companion artifact:** `docs/security/crawler-threat-model-draft.md` (signed same date).

This record closes the human decision boxes required before the R3 signing pass.
It does **not** attest that controls are implemented; card S6a remains separate.

---

## Decisions

| ID | Choice | Recorded decision |
|---|---|---|
| **T-19** | A — accepted single-approver risk | Allowlist changes remain single-approver (Danny Tran) for pilot. Compensating controls: tamper-evident audit trail, reviewer revocation, anomaly detection on approval volume. G3 is **not** amended for a second approver in pilot scope. |
| **T-27** | A — per-tenant | `event_source_observation`, `event_provenance`, and `discovery_review_item` are tenant-scoped. Composite `(tenant_id, id)` keys and composite FKs required. |
| **T-28** | A — defer identity half to A1b | Anti-CSRF and server-side authorization at action time are requirements now. Reviewer identity, tenant, and org-unit authority follow A1b + membership model when live OIDC lands. |
| **T-04** | Aligned — 5 MiB compressed | Compressed-byte cap per response: **5 MiB** (matches decompressed cap per G3 §3). |
| **T-29** | Quantified (pilot) | DOM tree depth **32**; JSON nesting depth **16**; iCal recurrence expansion **365** occurrences max, **2-year** horizon; evidence spans **50** per page; DB rows created per job **200** (aligned with G3 artifacts/page). |
| **C-1 vs T-14** | A — hashes + logical form only | P9 Gate B closed 2026-09-02. Evidence stores payload hashes and normalized logical fields only — **no raw third-party prose** in persistence. |
| **T-13** | A — app runtime validating connector | Client-side validating connector is required; egress proxy is additive only. |
| **T-23** | Provider direction | Primary LLM provider: **Google Gemini** (pilot candidates: Gemini 2.0 Flash / 3.x Flash or GPT-4o mini as fallback). Training/retention: no customer data used for model training; region/terms to be recorded when ADR-0015 A3 procures credentials. |

---

## Stale dependency resolutions (doc sync)

| Prior outstanding item | Resolution |
|---|---|
| T-14 blocked on P9 Gate B | **Closed** — Gate B signed 2026-09-02 (`p9-gate-b-contact-fields-worksheet.md` §8). |
| T-19 vs signed G3 | **Closed for pilot** — single-approver risk accepted (table above). |
| T-27 / T-28 / T-29 / T-04 unquantified | **Closed** — values in table above. |
| C-1 vs T-14 | **Closed** — Option A (table above). |
| Reviewer authority | **Closed 2026-09-02 (1a)** — Danny Tran. |

## Remaining open (not blocking signature)

| ID | State |
|---|---|
| **T-07** | Tools/providers dimension — LLM named (T-23); full tool allowlist still engineering card work. |
| **T-13** | Enforcement point named (app connector); live egress proxy optional. |
| **ADR-0015 A3** | Live provider credentials and spend ceilings — procurement external. |
| **Implementation (S6a)** | No live fetch until implementation evidence pass. |

---

## Sign-off

- **Ratified by:** Danny Tran (@dangt), Development Lead / Security Reviewer
- **Date:** 2026-09-03
- **Scope:** Design requirements in `crawler-threat-model-draft.md` revision 4 + this record.
