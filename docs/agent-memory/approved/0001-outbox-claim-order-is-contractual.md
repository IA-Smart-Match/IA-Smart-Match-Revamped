---
schema: agent-memory/record/v1
entry_id: 0f6a1c02-4d1e-4b7a-9f21-5c8d3e7a1b40
project_id: smartmatch
repository_id: f943437b-6a8f-47fe-9c0d-478988b70d9a
status: approved
authority: observation
privacy_class: repo-public
claim: The outbox claim order is a contract obligation stated in ADR-0005, not an emergent property of the query plan.
sources:
  - docs/architecture/decisions/ADR-0005-transactional-outbox-and-cte-claim.md@c39f4c24dfae7769ee86bd6a266f6731aa2da00c
  - python/smartmatch_persistence/smartmatch_persistence/outbox.py@8c289b265b0616a3dc83dfbd4d74f3786fa5ebf9
produced_by_tool: claude-code
produced_by_session: 57e35539-b0e2-4365-9a0f-3f8d01a25be9
produced_by_commit: 4e35430
reviewed_by: dangtran1022@gmail.com
approved_at: 2026-08-24T00:00:00Z
expires_at: null
supersedes: null
superseded_by: null
conflicts_with:
content_hash: sha256:b4037c1f3afb62873393b02211a283658082433f673398496b00f47d47d80cf1
---

FIFO ordering here is something the contract promises, so it cannot be traded
away for a faster plan without changing the contract first. ADR-0005 states the
obligation directly. Commit bfb1a0e exists because the ordering was once treated
as incidental, and the claim query stopped honouring it.
