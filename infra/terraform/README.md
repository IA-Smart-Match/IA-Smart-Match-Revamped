# Infrastructure

**Nothing here is deployed, and nothing here should be applied.** These are
environment skeletons recording the topology decisions in architecture v1.1 §3.1
and the isolation boundaries in §3.2. Real module implementations are Foundation
item F5, after the services are containerized.

## Environments

Four environments, each a **separate GCP project** (v1.1 §3.2):

| Environment | Data | Providers | Notes |
|---|---|---|---|
| `dev` | Synthetic | Fixtures | Scales to zero |
| `staging` | Synthetic | Fixtures until R4 | Production-shaped |
| `classroom` | Synthetic | **Fixtures only, always** | No provider credentials exist in this project |
| `prod` | Live pilot | Gated per release | Manual approval required |

## The rule that matters

Environment configurations **cannot share** a project, database, queue, bucket,
service-account, or secret identifier. Architecture v1.1 §3.2 requires this be
asserted by configuration validation in CI rather than left to convention, because
a shared identifier is invisible in a diagram and catastrophic in practice.

There is no promotion path from `classroom` to `prod`. Classroom deploys only
from classroom-tagged releases.

## What is deliberately not here

Per v1.1 §3.1 and the deferral table in §3.5, the topology omits Memorystore
Redis, Pub/Sub, BigQuery, and any direct Calendar API integration. Each has an
objective adoption trigger recorded in `docs/migration/rejected-components.md`.
Adding one before its trigger fires would be a change to the accepted
architecture, not a configuration detail.
