---
schema: agent-memory/record/v1
entry_id: 5c1d8a44-3f92-4e18-8b70-2a6f9c0d5e31
project_id: smartmatch
repository_id: f943437b-6a8f-47fe-9c0d-478988b70d9a
status: approved
authority: observation
privacy_class: repo-public
claim: The forbidden-behaviour scanner walks every file in the tree, not only Python, so committed Markdown is already covered by the credential gate.
sources:
  - tools/scan_forbidden.py@830fd4db983118af77dc3f389b2fca56b5f259c0
produced_by_tool: claude-code
produced_by_session: 57e35539-b0e2-4365-9a0f-3f8d01a25be9
produced_by_commit: ba5f9df
reviewed_by: dangtran1022@gmail.com
approved_at: 2026-08-24T00:00:00Z
expires_at: null
supersedes: null
superseded_by: null
conflicts_with:
content_hash: sha256:3720030ffe9f144ffb0eb9ef332ddff54104c20f028a458bcd4ab4c2b662768e
---

Rules without an applies_to tuple match every extension, and the credential
rule has none. Two consequences follow. Documentation that quotes a token shape
fails the gate, which is the intended behaviour rather than a false positive.
And this ledger inherits a mandatory pre-merge secret check simply by being
committed, which is the reason the design keeps records as files rather than
rows in a service. Adding docs/agent-memory/ to EXCLUDED_PREFIXES would discard
that control entirely.
