# Infrastructure

**Nothing here is deployed, and nothing here should be applied.** These are
environment skeletons recording the topology decisions in architecture v1.1 §3.1
and the isolation boundaries in §3.2. There are no modules, no resources, no
provider blocks, no state backend, and no credentials — and `make infra-check`
fails the build if any of them appear, because a skeleton that can be applied is
not a skeleton. Real module implementations wait on a deployment target, which
does not exist yet.

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

### The assertion, not the sentence

The paragraph above is prose, and prose fails no build. The control is
`tools/env_isolation_check.py`, run by `make infra-check` and by the `isolation`
job in `.github/workflows/verify.yml`. Over `envs/*/main.tf` it asserts:

| # | Assertion | Why it is there |
|---|---|---|
| 1 | No identifier value appears in two environments | The §3.2 rule itself |
| 2 | Every environment declares the *same* identifier keys | Otherwise assertion 1 is satisfied by deleting the duplicate |
| 3 | Every identifier carries its own environment's name and no other's | Catches a copied block at the line it was copied to, before it becomes a collision |
| 4 | Every identifier is a visible placeholder — the reserved `example` namespace, RFC 2606 domains | Nothing here is deployed, so no real project, bucket, account, or secret may be named |
| 5 | Only `terraform` and `locals` blocks exist; no backend | Nothing here may be applied |
| 6 | Classroom is fixtures-only, holds no provider secret at all, and neither promotes nor is promoted from | The §3.3 classroom boundary |
| 7 | Only `prod` may hold non-synthetic data, and only with gated providers | Live data and ungated providers must not coexist |
| 8 | A key in neither `IDENTIFIER_KEYS` nor `SETTING_KEYS` fails | A new identifier nobody classified is a new identifier nobody checked |

It parses a small subset of HCL rather than shelling out to `terraform`, so it
runs in CI and on a laptop with no Terraform installed and no network. A value
the subset cannot read — an interpolation, a variable reference — is a parse
error rather than a skipped line: a value it cannot resolve is a value whose
uniqueness it cannot assert. The check is itself self-tested in
`tests/unit/test_env_isolation_check.py`, including the case that matters — two
environments given the same project id, and the check must fail.

## What is deliberately not here

Per v1.1 §3.1 and the deferral table in §3.5, the topology omits Memorystore
Redis, Pub/Sub, BigQuery, and any direct Calendar API integration. Each has an
objective adoption trigger recorded in `docs/migration/rejected-components.md`.
Adding one before its trigger fires would be a change to the accepted
architecture, not a configuration detail.
