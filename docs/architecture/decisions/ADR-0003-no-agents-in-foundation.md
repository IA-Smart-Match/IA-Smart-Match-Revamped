# ADR-0003 — No agent framework in the Foundation scaffold

**Status:** Accepted
**Date:** 17 August 2026
**Contract:** Architecture v1.1 §1.4, gate G3

## Context

The legacy repository contains agent orchestration (`src/coordinator/`), a
`nemoclaw_adapter`, an intent parser, and four agent tools. It would be natural to
carry a framework choice forward now so later work has somewhere to land.

## Decision

No agent framework, no agent code, and no agent dependency in Foundation.
Architecture v1.1 §1.4 states plainly: "no agents ship in the core pilot
(Foundation + R1)."

The framework decision itself — Google ADK inside the worker boundary — is
recorded in v1.1 as the intended direction, with LangGraph as the fallback if
model independence outweighs GCP integration and the Claude Agent SDK if research
becomes Anthropic-first. It is not implemented here, and confirming it is open
decision 7.

## Rationale

Adding a framework now would cost something and buy nothing. The dependency, its
transitive tree, and its vulnerability surface would exist for two releases before
anything used them. Worse, a scaffolded agent module invites feature work to route
through it before gate G3 has approved an eval set, tool allowlist, and cost
controls — which is precisely the sequence v1.1 §1.4 exists to prevent.

The legacy's agent code is rejected on its own terms regardless of framework: it
made provider calls in the browser request path and treated agent session state as
authoritative. v1.1 §1.6 requires every consequential action be persisted as a
command and dispatched through the outbox. That correction is architectural, not a
matter of which library runs the agent.

## Consequences

**Good.** No unused dependency. No premature commitment while open decision 7 is
open. The outbox and worker boundary — which agents will need — get built first
and for their own reasons, so agents arrive into infrastructure that already
works.

**Cost.** R3 starts with framework integration rather than feature work. This is
the correct place for that cost: by then the eval set exists, the tool allowlist
is approved, and the integration can be judged against real requirements instead
of guessed ones.
