> DRAFT — needs Danny decision. Nothing here is decided.

# AMP governance adapter: candidate answers to OQ-AMP-01..04 (draft)

Refs #314. Source: `docs/plans/2026-09-16-amp-governance-adapter-proposal.md` (proposal status: "Closes nothing, authorizes nothing", line 3). Backlog row says "Proposal only... No owner named" (`docs/plans/backlog.md:22`).

**Read first.** The proposal states AMP "does not advance the actual blocker": G3's open half is the agent eval set (MP-1..MP-5, category floors, injection fixtures) and cost controls, not orchestration (`2026-09-16-amp-governance-adapter-proposal.md:61-64`). Answering these OQs does not unblock G3. Sequencing puts the port after the OQs close and the crawler pilot after the eval set (`:207-215`).

Every option below keeps the safe default in force: no AMP call is made.

## Candidate answers (options, not picks)

### OQ-AMP-01 — AMP as a data processor (`proposal:155`)
- A. No account. Keep fixture only. Question stays open until a pilot needs it.
- B. Name one AMP org under an institution-approved contract, data-processing terms reviewed first.
- C. Decline AMP as a vendor; close the OQ as "not adopted".

### OQ-AMP-02 — credential storage and rotation (`proposal:169`)
- A. No credential exists; fixture provider only (the default).
- B. Credential in the same secret store chosen for OQ-005; rotation set by whoever owns that decision.
- C. Credential per environment, never in dev/classroom editions; live-mode boot without it refuses and names the OQ.

### OQ-AMP-03 — what may leave the platform (`proposal:180`)
- A. Allowlist stays empty: instance ids and state names only (default).
- B. Add job-level fields only (job id, state, counts), no recipient data, no page content.
- C. Add extraction evidence fields after T-14 and G2 close (`proposal:180-191`).

### OQ-AMP-04 — approval surface or mirror (`proposal:193`)
- A. Mirror only: AMP receives decisions after the platform records them (default).
- B. Approval inside AMP's portal, with its own accounts and roles; the platform route stays authoritative (`proposal:23-30`).

## Park vs adopt

| | Park | Adopt |
|---|---|---|
| What happens | Leave proposal as is; close #314 as "parked until G3 eval set exists" | Close the four OQs, then land port plus `FixtureAmpProvider` only (`proposal:207-215`) |
| Cost | None | A reviewable change; no network path, no live client |
| Unblocks G3 eval set? | No | No (`proposal:61`) |
| Risk | Design drifts stale | A second approval surface if OQ-AMP-04 = B |

## FixtureAmpProvider sketch (not code to merge)

Pattern to mirror: `FixtureEmailProvider` records calls in a list and returns a `fixture-` prefixed result (`python/smartmatch_providers/smartmatch_providers/fixtures.py:26-45`), against a `@runtime_checkable` `Protocol` with a `name` attribute (`python/smartmatch_providers/smartmatch_providers/base.py:116-128`). The method list is the proposal's (`proposal:97-99`).

```python
@runtime_checkable
class AmpGovernanceProvider(Protocol):
    name: str

    def start_instance(self, job_id: str) -> str: ...  # returns instance id
    def log(self, instance_id: str, event: str) -> None: ...
    def llm_trace(self, instance_id: str, prompt: str, answer: str) -> None: ...
    def set_state(self, instance_id: str, state: str) -> None: ...
    def request_hitl(self, instance_id: str, caller_id: str) -> str: ...  # workitem id
    def poll_decision(self, caller_id: str) -> str | None: ...  # None = pending
    def report_outcome(self, instance_id: str, outcome: str) -> None: ...


class FixtureAmpProvider:
    name = "fixture-amp"

    def __init__(self, decisions: dict[str, str] | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []  # recorded, never sent
        self._decisions = decisions or {}  # scripted answers

    # each method appends to self.calls; ids are "fixture-<job_id>"
```

Sketch signatures are mine, not the proposal's. `prompt` and `answer` parameters touch OQ-AMP-03: under the default allowlist the real adapter sends ids and states only. No HTTP client, per `proposal:100-104`.

## Open questions

1. Park or adopt? Danny.
2. OQ-AMP-01 and 02: does the institution have any appetite for AMP as a vendor? Danny, then institution procurement (same class as OQ-002).
3. OQ-AMP-03: field list. Danny with the privacy/records owner (G2).
4. OQ-AMP-04: mirror or approval surface. Danny.
5. Who owns this item at all? The backlog row names no owner (`backlog.md:22`). Danny.
