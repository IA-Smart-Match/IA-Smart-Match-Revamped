# AMP governance adapter — provider-port proposal (draft)

**Status:** **PROPOSAL — 2026-09-16. Closes nothing, authorizes nothing.** No
code, configuration, credential, or network path is created by this document.
Every section names an owner and a safe default; until a dated, attributed
decision lands, the safe default is in force — and every safe default here is
*no AMP call is made*.
**Scope:** documentation only. This file exists so the design can be reviewed
before any of it is plugged in.
**Subject system:** AMP (Agent Management Platform), `api.inquiryon.com` —
agent registration, governance policy, activity logging, `llm_trace`, HITL
workitems, and RLHF outcome reporting, per the AMP Agent Integration Playbook.

---

## 1. What AMP would be for, and what it would never be for

AMP offers four capabilities this platform could consume:

| AMP capability | What it is | Candidate use here |
|---|---|---|
| Agent lifecycle (`/api/agent/init`, `setState`) | An instance record with `initiated → active → wait → finished/abort` | Mirror a crawl job's lifecycle for external observability |
| Activity log + `llm_trace` | Journaled events; per-LLM-call prompt/answer/reasoning | Evidence for tier-3 extraction calls (MP-1's "cite field evidence" spirit) |
| HITL (`/api/hitl/request`, `get-decision`) | Policy-evaluated human workitems, human or auto resolution | An approval surface for first-seen events or autonomous dispatch |
| RLHF (`/api/rlhf/outcome`, `stage_tick`) | Outcome reporting that progressively raises agent autonomy | Long-term: graduated autonomy for low-risk agent decisions |

**What AMP would never be for:** the system of record for consent,
suppression, review, or approval. `smartmatch_domain.consent`,
`suppression_record`, `outreach_draft.approved_by`, and the review queues are
authoritative and stay so. An AMP "approve" is an input to an existing
in-platform decision route, never a write to `contact_channel`,
`outreach_draft`, or event publication. This is the same rule the codebase
already keeps elsewhere: one `suppression_record` list, one draft-approval
state machine, one answer to "has this person told us to stop."

**The autonomy ceiling.** AMP's RLHF progression toward Stage-2 auto-approval
collides with a standing rule of this repository: *gate owners sit outside
engineering and are never inferred from technical readiness.* An AMP
auto-decision can never substitute for OQ-001/002/003, G3's eval-set sign-off,
a coordinator's dispatch, or a named human's review. If AMP is adopted, its
autonomy is capped below every platform gate, permanently.

## 2. The three backlogged items, and where AMP fits each

### 2.1 R3 crawler / research agent — strongest fit

The G3 decision (`docs/decisions/g3-crawler-decision.md`, signed 2026-09-03)
already mandates the shape AMP models: a bounded agent run, per-call evidence,
and a human decision on every first-seen event.

- One AMP agent instance per crawl job; `setState` mirrors the job state
  machine (`smartmatch_domain.jobs.JobState`).
- One `llm_trace` per tier-3 extraction call — the prompt, the answer, and
  provider reasoning where exposed — which is exactly the evidence MP-1
  ("never fabricate; every prose-derived field carries a verbatim quoted span
  or is `unknown`") wants a reviewer to see.
- One HITL request per first-seen event, resolved by a human into the
  platform's own `discovery_review_item` flow — AMP records the decision; the
  platform's review queue remains the record that matters.

**This does not advance the actual blocker.** G3's open half is the agent eval
set (MP-1..MP-5, category floors, injection fixtures) and cost controls, not
orchestration. AMP is additive observability/governance, not a substitute for
the eval set.

### 2.2 Autonomous batch invite — partial fit

`routers/cba_invitations.py` is already built and deliberately human-driven:
a coordinator composes a batch (consent check 1), dispatches it (check 2), and
the worker re-checks at delivery (check 3). "Autonomous" means an agent
composing and dispatching without the human click — a policy decision, not
missing code.

If autonomy is ever authorized, AMP HITL is a reasonable gate: agent proposes
a batch → AMP workitem → human approves → `POST .../dispatch`. But note the
duplication: `outreach_draft` already carries an approval state machine
(`approved_by`/`approved_at` present iff `approved`). AMP adds a second
approval surface; adopting it means deciding *which* approval is authoritative
(the platform's — see §1) and whether a second portal earns its keep.

### 2.3 Outreach send — weakest fit

The send path's gate is the consent lifecycle, re-checked at delivery time by
the worker (`smartmatch_worker/outreach.py`). AMP adds nothing to that gate
and cannot — the blockers are OQ-001 (institutional From domain), OQ-002
(provider tenant/procurement), OQ-003 (reviewed copy), OQ-004 (production
contacts). At most, AMP logging could mirror `delivery_event` for external
audit, which is a want, not a need.

## 3. Proposed architecture — a provider port, not an integration

The shape is copied from `smartmatch_providers.resend.ResendEmailProvider`,
which is the repository's existing answer to "a real external service we are
not yet allowed to call":

- **`AmpGovernanceProvider` port** in `smartmatch_providers` — the interface
  the worker codes against: `start_instance`, `log`, `llm_trace`,
  `set_state`, `request_hitl`, `poll_decision`, `report_outcome`.
- **`FixtureAmpProvider`** — records calls in memory, returns scripted
  decisions. Lets the entire flow be exercised in tests and in the dev
  appliance with zero network.
- **No HTTP client in the module.** Like `resend.py`, the adapter composes
  requests and takes a caller-supplied transport. A test asserts the absent
  import; another walks call sites asserting nothing passes `transport=`.
  Live mode requires a credential *and* a permitted edition *and* a transport
  *and* (per §5) closed OQs — the same four-gate shape as live email.
- **Fail closed.** No `AMP_API_KEY` → fixture only. Classroom/dev editions
  refuse a live client at boot, naming the open question, exactly as
  `build_email_provider` refuses and names OQ-002.

### 3.1 Worker-side only — this is structural, not a preference

`tests/unit/test_no_external_calls_on_request_path.py` forbids any HTTP-client
import under `services/api/` and forbids `agent`, `llm`, `prompt`, `crawl`,
`discovery` path segments in the committed OpenAPI contract. Two consequences:

- All AMP traffic lives in `services/worker/` (or a provider adapter the
  worker calls). The API never learns AMP exists.
- **No AMP callback endpoint can exist on this API.** HITL resolution is by
  polling `GET /api/hitl/get-decision?caller_id=<job_id>` from the worker —
  which is also the only option while nothing is deployed and no reachable
  callback URL exists. The playbook's own polling sample is the model.

### 3.2 Concept mapping

| AMP | Platform | Direction |
|---|---|---|
| Agent instance (`init`) | `job` row | Platform → AMP (mirror) |
| `setState` | `JobState` transitions | Platform → AMP (mirror) |
| `llm_trace` | Extraction evidence for tier-3 calls | Platform → AMP (mirror) |
| HITL workitem | `discovery_review_item` / draft approval | AMP → platform, via existing review/decision routes only |
| RLHF outcome | Review decision records | Platform → AMP (report after the platform decision exists) |
| `decision_mode=auto` | Nothing authoritative | Logged; never writes |

The asymmetry is the design: everything authoritative flows platform → AMP as
a mirror; the only AMP → platform flow is a human's decision entering through
the same routes a human would use without AMP.

## 4. What this does not change

- No AMP SDK dependency; the port is plain HTTP shapes we define.
- No new env vars wired into `config.py` yet — `AMP_BACKEND_URL`,
  `AMP_API_KEY`, `AMP_ORG_ID`, `AGENT_NAME` are named here for review, not
  added.
- No callback endpoint, no new routes, no OpenAPI changes.
- No change to consent, suppression, review, draft approval, or gate
  authority.
- No RLHF auto-approval of anything the platform gates.

## 5. Open questions this proposal raises

Each is a decision a human has to make; each carries the safe default *no AMP
call is made*. Numbered in the R4 register's style for continuity.

### OQ-AMP-01 — AMP as a data processor

**Question.** Which AMP organization/account, under whose contract, with what
data-processing terms?

**Why engineering cannot answer it.** Same class as OQ-002: adopting a
third-party SaaS that receives prompts, metadata, and decision records is a
procurement and privacy decision. Prompts and `context` payloads can contain
contact details and event content — that is data egress to a named external
party.

**Safe default.** No credential exists; the fixture provider answers
everything.

### OQ-AMP-02 — credential storage and rotation

**Question.** Where do `AMP_API_KEY` / `AMP_ORG_ID` live, and what is the
rotation procedure?

**Why engineering cannot answer it.** Same class as OQ-005 — a
secrets-management decision tied to a deployment that does not exist.

**Safe default.** Absent secret ⇒ fixture provider; a live-mode boot without
the secret refuses and names this question.

### OQ-AMP-03 — what may leave the platform

**Question.** Which fields may appear in AMP `prompt`, `metadata`, `context`,
`action_fields`, and `llm_trace` payloads?

**Why engineering cannot answer it.** It is a PII-minimization and records
decision. It interlocks with T-14 (incidentally collected PII) and G2
(privacy/records approval for live data), neither of which is closed.

**Safe default.** The payload allowlist is empty; the adapter sends instance
ids and state names only — no recipient data, no page content, no extraction
text — until a field list is ratified.

### OQ-AMP-04 — is AMP's portal an approval surface or a mirror?

**Question.** Do humans approve inside AMP's portal (workitems resolved there,
outcomes reported back), or does AMP only record decisions made in the
platform's own review surfaces?

**Why engineering cannot answer it.** It decides whether AMP is a second UI
people are trained on — with its own accounts, roles, and audit story — or a
passive journal. The first is a product decision with a training and
support cost.

**Safe default.** Mirror only. AMP receives decisions after the platform
records them; no human is asked to work in a second portal.

## 6. Sequencing, if adopted

```
proposal review → OQ-AMP-01..04 closed → port + FixtureAmpProvider
→ worker-side wiring behind edition gate → R3 crawler pilot (after G3 eval set)
→ batch-invite HITL (only if autonomy is separately authorized)
→ outreach mirroring (only after OQ-001..004 close)
```

Each arrow is a separately reviewable change. The port landing first — with no
live client constructible — matches how `resend.py` shipped: the adapter
exists, is tested, and reaches no network.

## 7. Rejected alternatives

- **AMP as the review queue.** Rejected: a second authoritative answer to
  "what needs a human" is the two-sources-of-truth defect this codebase
  removes elsewhere.
- **AMP callbacks into the API.** Rejected structurally: no HTTP-client
  imports under `services/api/`, no `agent`/`llm`/`prompt` path segments in
  the contract, and nothing deployed to receive a callback anyway.
- **AMP Stage-2 auto-approval for sends or publishes.** Rejected outright:
  gate owners sit outside engineering; an RLHF auto-approve is not a person.
- **Blocking the backlog on AMP.** Rejected: none of the three items is
  blocked on orchestration. Outreach waits on institutional/legal decisions;
  the crawler waits on the G3 eval set; autonomous invites wait on a policy
  decision about who may authorize sends.

## References

- AMP Agent Integration Playbook (source document for the API shapes above)
- `docs/decisions/g3-crawler-decision.md` — signed G3 scope, limits, review policy
- `docs/security/r3-technical-review-findings.md` — T-11..T-15, egress, PII
- `docs/plans/open-questions/r4-outreach-deferred.md` — OQ-001..009, the register this file's OQ style follows
- `python/smartmatch_providers/smartmatch_providers/resend.py` — the port shape being copied
- `tests/unit/test_no_external_calls_on_request_path.py` — the structural constraint on §3.1
- `services/api/smartmatch_api/routers/cba_invitations.py` — the existing human-driven batch invite
- `services/worker/smartmatch_worker/outreach.py` — the delivery-time consent recheck
