# Critical path: legacy identity exposure (MM-A09)

**ID:** CP-PII
**Parent:** [critical-path-plans.md](critical-path-plans.md)

The only severity-1 item in the stakeholder test log. It is **not closable from
this repository**. It currently has **no owner**.

Planning only. No writes to the legacy repository are authorized.

## Ratification status (31 August 2026) — CANNOT CLOSE

Session approver Danny Tran (`dt110202@gmail.com`) recorded this item as
**CANNOT CLOSE** — see `docs/decisions/2026-08-31-session-ratification.md`
and `docs/plans/prep/human-decisions-handoff-831.md` §8. **Legacy PII
remediation owner and outcome remain unnamed and unresolved**; this
ratification does not name one and does not claim remediation.

**Current disposition recorded for this handoff:** the source repository
(`BrooklynD23/Nebiux-Team-IA-West-SmartMatch`) is archived and private, and
the Vercel shutdown of that deployment has been directed by the Development
Lead (`dt110202@gmail.com`). Access is removed from everyone. This item is
held as **out of scope for the active delivery path** in *this* repository
and does **not** block current private-repository engineering — but it
remains open for D9/licensing/open-source purposes (see `pilot-decisions.md`
D9), and no work recorded anywhere in this repository is remediation of the
archived legacy repository or reduces its exposure. The "(b) Current status"
table below is otherwise unchanged by this note.

---

## (a) What this is

Six paths tracked in `BrooklynD23/Nebiux-Team-IA-West-SmartMatch` at
`bdce024` contain named real people. Verified by header and row count;
contents are deliberately not reproduced here.

| Path (under the Category 3 CRM tree unless noted) | What it is |
|---|---|
| `data/data_speaker_profiles.csv` | 18 rows; names, roles, companies |
| `data/data_cpp_events_contacts.csv` | 15 rows; published contacts including email/phone |
| `data/poc_contacts.json` | Named people with `@cpp.edu` addresses **and** `comm_history` — a communications log, not a contact list |
| `data/pipeline_sample_data.csv` | 58 rows pairing `speaker_name` with `match_score` / rank / stage |
| `archived/.../data_speaker_profiles.csv` | Byte-identical duplicate of the first |
| `archived/.../data_cpp_events_contacts.csv` | Byte-identical duplicate of the second |

A remediation that deletes four paths leaves two intact.

This is **Fix #1** in Dr. Ann Wang's 19–20 August 2026 test log. MM-A04 covers
only `demo.db` / `smartmatch.db` / `feedback-log.jsonl` — none of the six.
S-005 in `docs/security/scaffold-security-review.md` flagged the local DBs
without inspecting them; MM-A09 is the identity finding that audit did not
enumerate.

Taking the Vercel deployment down, or deleting the files at HEAD, **does not
remove them from git history**.

Sources:

- `docs/migration/migration-manifest.yaml` MM-A09 (`blocking_owner: unassigned`)
- `docs/plans/stakeholder-audit-integration.md` §2.5, §8, §9 Q1, §10
- `docs/architecture/review/stakeholder-test-log-audit.md` Fix #1
- `docs/plans/remaining-foundation-r1-work.md` D9 (gated by MM-A09)
- Orchestrator contract: legacy is read-only evidence; no write without
  authorization (`docs/plans/orchestrator-handoff.md`)

Related but smaller: whether the **stakeholder test log itself** should be
vendored here. It names real people, which is the subject of this finding.
Default remains external citation with author+dates pinned (`stakeholder-audit-integration.md`
§9 Q7).

---

## (b) Current status

| Claim | State |
|---|---|
| Target repository ports any of the six | No. Disposition `archived`. |
| Exposure in *this* git history | None of the six is in this repo. |
| Exposure in legacy git history | Yes, at the pinned SHA and in clones/forks/backups of it. |
| Owner | **Unassigned** |
| D9 (open-source / LICENSE) | Blocked |
| F13 `LICENSE` | Blocked; PR1 shipped `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS` without it |
| Kickoff Q11 | Blocked on Q1 (this document's Q1, not "which factors") |

---

## (c) Execution plan

### 1. Assign an owner (this week)

Put a person on `MM-A09.blocking_owner` and on `stakeholder-audit-integration.md`
§9 Q1. Engineering cannot pick the legal remedy. Until this line has a name,
every later LICENSE/open-source discussion is theatre.

Likely owners to choose among (not chosen here): privacy / legal / records,
legacy repository owner, program owner. The security review assigned S-005 to
"legacy repository owner / privacy".

### 2. Inventory reach, without copying PII into *this* repo

The owner (or a designated counsel) should establish, outside this tree:

- Which remotes and forks still have `bdce024` (GitHub, Vercel build cache,
  agent checkouts, USB copies named in the stakeholder-audit CRLF clone note).
- Whether the Vercel deployment's build SHA equals `bdce024` (audit assumption
  §8.2: if not, screen behaviour may differ; the files still exist at that
  commit).
- Whether `poc_contacts.json` comm_history is the worst disclosure (it is).

Do **not** commit extracts, names, or emails here. Pointers only. Agent-memory
must not record this finding as a ledger row whose `sources` are legacy paths
(pointer rule; audit §9 Q8 explicitly excluded it).

### 3. Choose a remedy (Q1)

Two families; neither is an engineering task in this repo:

**A. History rewrite of the legacy repository** (filter-repo / BFG, force-push,
  rotate any leaked credentials, notify clones). High operational cost;
  incomplete if forks are not followed.

**B. Repository replacement** — new empty canonical remote; old remote
  archived private / deleted per institutional policy; document the SHA as
  historical evidence accessible under access control.

A hybrid (rewrite + restrict the old remote) is a variant of A.

**Deleting files in a new commit on `main` is not a third option.** It is
hygiene for HEAD and leaves history.

### 4. Only then answer D9 / kickoff Q11

May this *target* repository be open-sourced? It does not contain the six
paths. Publishing **legacy** history would broaden exposure. The target
`LICENSE` can in principle land once Q1 is decided even if the answer is
"legacy stays private, target is X". Do not write `LICENSE` by guessing X.

F13 remaining file: `LICENSE` at repo root. `SECURITY.md` /
`CONTRIBUTING.md` / `CODEOWNERS` are on the PR1 branch.

### 5. What engineering does after the decision

- Update MM-A09 `notes` with the decision, date, and owner — still no
  reproduced contents.
- If the legacy SHA used as evidence moves (rewrite), update
  `legacy_sha` / `legacy_sha_verified` **only** with a recorded deviation:
  CP-REREVIEW and every `contract_refs` walk today pin `bdce024`. A rewrite
  that changes that SHA is a migration-evidence incident, not a silent
  `git pull`.
- Scanner / CI: no change unless someone proposes vendoring redacted fixtures;
  those must be synthetic (MM-A03 discipline).

---

## (d) Dependencies

Blocked on a named human. Blocks D9, F13 `LICENSE`, honest open-source
answers, and any plan to publish the legacy tree.

Does not block CP-PR1, A5, G1 conversation, or F9 re-review of *target* code.
Re-review still needs **read** access to `bdce024`; if Q1's remedy destroys
that access without a controlled archive, F-12 / F-21 become unfalsifiable
(`defect-remediation.md` §10 assumption 2). **Coordinate Q1 with CP-REREVIEW:**
keep a sealed evidence copy of `bdce024` even if the public legacy remote
goes away.

---

## (e) Acceptance

- [ ] `blocking_owner` on MM-A09 is a named role or person, not `unassigned`.
- [ ] Written decision: rewrite vs replace vs hybrid, with who executes it on
      the legacy remote.
- [ ] Explicit statement that HEAD deletion is not the remedy.
- [ ] D9 either unblocked with a LICENSE choice, or still blocked with a
      remaining condition (e.g. "wait until rewrite is confirmed on GitHub").
- [ ] Evidence copy of `bdce024` for migration review is accounted for
      (location, access control) if the public repo will be rewritten or
      removed.
- [ ] No PII from the six paths appears in this repository, the agent-memory
      ledger, or new ADRs.

---

## (f) Priority

**First human-assignment**, parallel with CP-PR1. The PR1 handoff repeats:
it is the only severity-1 item and it still gates D9.

Do not order it ahead of GRANT/A5 in an *engineering* sprint. Do not bury it
under S-series product work either — those are not severity 1.

---

## Out of scope (stated so it is not "forgotten")

- Writing to the legacy repository from an agent session.
- Vendoring the stakeholder test log without a Q7 decision.
- Inspecting `data/demo.db` / `data/smartmatch.db` contents (S-005) unless the
  same owner expands the brief — those are MM-A04, not MM-A09.
- Classroom-reset tooling (diagram 3) — needs a scope and an ID; not PII.
