# Infrastructure

**Nothing here has been applied. `terraform apply` has never been run against
any of it, and `ALLOW_CLOUD_DEPLOY` remains `false`.** What exists is the
configuration for one environment's topology and a registry of the names four
environments would claim. What does not exist is any way to turn that into
running infrastructure: there is no root module, no provider block, no state
backend, no credential, and no registry holding an image to deploy.

That is not an aspiration in a comment. `make infra-check` fails the build if a
provider block, a backend, a root module, a state file, a plan file, a
`.tfvars`, or a lock file appears anywhere in this tree — and the composition
module requires four inputs that name things nobody can supply today, so a
`terraform plan` cannot be produced at all, never mind an apply.

## Layout

```
infra/terraform/
  envs/{dev,staging,classroom,prod}/main.tf   registry of names — locals only
  modules/cloud_run_service/                  one Cloud Run v2 service
  modules/cloud_sql_postgres/                 PostgreSQL 16 instance + database
  modules/cloud_tasks_queue/                  the dispatcher's job queue
  modules/cloud_scheduler_job/                the scheduled dispatcher pass
  modules/secret_placeholders/                Secret Manager containers, no values
  modules/storage_buckets/                    evidence + artifact buckets
  modules/platform/                           composes the six, one per environment
```

The split matters. `envs/*/main.tf` contains **no resources and no module
blocks** — it is a list of names and settings, and the gate still refuses
anything applyable in it. The modules contain resources but **no names**: every
identifier arrives from the caller. Neither half can deploy anything on its own,
and that is the point.

## Environments

Four environments, each a **separate GCP project** (v1.1 §3.2):

| Environment | Data | Providers | Notes |
|---|---|---|---|
| `dev` | Synthetic | Fixtures | Scales to zero |
| `staging` | Synthetic | Fixtures until R4 | Production-shaped |
| `classroom` | Synthetic | **Fixtures only, always** | No provider credentials exist in this project |
| `prod` | Live pilot | Gated per release | Manual approval required |

Per the F5 deploy-target note (`docs/decisions/f5-deploy-target-note-2026-09-03.md`),
`classroom` is the intended first host for a stakeholder demo: synthetic data
only, no provider secret, and no promotion path to prod. That decision chooses a
target; it does not open a gate.

## What exists, service by service

| Service | Module | What it declares | What it deliberately omits |
|---|---|---|---|
| Cloud Run (API and worker) | `cloud_run_service`, instantiated twice | Service, revision scaling, runtime identity, health probes, database URL read from a Secret Manager placeholder | Ingress settings and invoker IAM — exposure is a per-environment decision nobody has made |
| Cloud SQL | `cloud_sql_postgres` | `POSTGRES_16` instance (pinned by a variable validation), one logical database, backups, PITR, no public address, deletion protection on | `google_sql_user` — a user resource carries a password, and a password in Terraform is a password in state |
| Cloud Tasks | `cloud_tasks_queue` | Queue with rate limits and a backoff retry policy matched to the worker's idempotent `POST /tasks/execute` | The OIDC enqueue identity — Finding S-001, still open |
| Cloud Scheduler | `cloud_scheduler_job` | HTTP job posting to `/operations/dispatch`, one attempt, scheduler-scoped OIDC token | The audience and the target URL. Both are inputs with no default and no committed value |
| Secret Manager | `secret_placeholders` | `google_secret_manager_secret` containers, user-managed replication, one per name the environment owns | **Every version.** No `google_secret_manager_secret_version` exists here and the gate fails if one appears |
| Cloud Storage | `storage_buckets` | Evidence and artifact buckets, uniform access, versioning on | Lifecycle rules — no retention decision has been recorded |

Bucket names are global across all of GCP, which makes them the sharpest case
for the disjointness rule below: two environments naming one bucket is not
merely a policy breach, it is a resource one project cannot create because
another already did.

## The rule that matters

Environment configurations **cannot share** a project, database, queue, bucket,
service name, service-account, or secret identifier. Architecture v1.1 §3.2
requires this be asserted by configuration validation in CI rather than left to
convention, because a shared identifier is invisible in a diagram and
catastrophic in practice.

There is no promotion path from `classroom` to `prod`. Classroom deploys only
from classroom-tagged releases.

### The assertion, not the sentence

The paragraph above is prose, and prose fails no build. The control is
`tools/env_isolation_check.py`, run by `make infra-check` and by the `isolation`
job in `.github/workflows/verify.yml`.

Over `envs/*/main.tf`:

| # | Assertion | Why it is there |
|---|---|---|
| 1 | No identifier value appears in two environments | The §3.2 rule itself |
| 2 | Every environment declares the *same* identifier keys | Otherwise assertion 1 is satisfied by deleting the duplicate |
| 3 | Every identifier carries its own environment's name and no other's | Catches a copied block at the line it was copied to, before it becomes a collision |
| 4 | Every identifier is a visible placeholder — the reserved `example` namespace, RFC 2606 domains | Nothing here is deployed, so no real project, bucket, account, or secret may be named |
| 5 | Only `terraform` and `locals` blocks exist; no backend | An environment file is a registry of names, not a deployment |
| 6 | Classroom is fixtures-only, holds no provider secret at all, and neither promotes nor is promoted from | The §3.3 classroom boundary |
| 7 | Only `prod` may hold non-synthetic data, and only with gated providers | Live data and ungated providers must not coexist |
| 8 | A key in neither `IDENTIFIER_KEYS` nor `SETTING_KEYS` fails | A new identifier nobody classified is a new identifier nobody checked |

Over `modules/**/*.tf`, added alongside the modules themselves — because a
registry of disjoint names proves nothing if a module can mint a name of its
own:

| # | Assertion | Why it is there |
|---|---|---|
| 9 | No variable that names a cloud object declares a `default` | A default is one value shared by every caller. It is the one door left through which dev and prod still collide after assertions 1–3 pass |
| 10 | No module writes a literal name into a resource attribute | The same failure spelled differently. Checked only on a block's own attributes, so `name` inside a Cloud Run `env` block is correctly left alone |
| 11 | `modules/platform` declares exactly the registry's identifiers, no more and no fewer | An unclassified input can be filled from somewhere nobody checks; an identifier no module consumes is one whose disjointness protects nothing |
| 12 | No `provider` or `backend` block, no `google_secret_manager_secret_version`, no `google_sql_user`, no `google_service_account_key` | The first two name a project and a credential; the rest put a value into state |
| 13 | The four deploy inputs — both images, the worker URL, the scheduler audience — declare no default | This is the apply gate. Each names something that has never been created, so a plan cannot be produced |
| 14 | No root module, no state, no plan, no `.tfvars`, no lock file; nothing beside `main.tf` in an environment directory | Each is produced by running something, and nothing here has been run. The stray-file rule closes the obvious way around assertion 5 |

The check parses a small subset of HCL rather than shelling out to `terraform`,
so it runs in CI and on a laptop with no Terraform installed and no network. A
value the subset cannot read — an interpolation, a variable reference — is a
parse error rather than a skipped line: a value it cannot resolve is a value
whose uniqueness it cannot assert.

It is itself self-tested in `tests/unit/test_env_isolation_check.py`, including
the cases that matter: two environments given the same project id, and a module
given a default for a name. Both must fail. A uniqueness assertion never shown
to fail is indistinguishable from `return 0`.

`modules/platform` also carries two `precondition` blocks restating the rule
where a plan would see it. They are **not** the assertion of record — they run
only if somebody runs a plan, and nobody has, and a plan sees one environment at
a time, so they cannot see a cross-environment collision at all.

### Running it

```bash
make infra-check                 # the gate; stdlib only, no Terraform needed
terraform fmt -check -recursive infra/terraform
```

`terraform validate` needs `terraform init` first, which downloads the Google
provider. Each module under `modules/` validates on its own with
`terraform init -backend=false`; that leaves a `.terraform/` directory and a lock
file behind, both of which are gitignored and both of which `make infra-check`
fails on if one is ever committed.

## What is deliberately absent

| Absent | Why | Closed by |
|---|---|---|
| A root module, a provider block, a state backend | Together they are what makes an apply possible. There is no deploy target and no credential | The program owner setting `ALLOW_CLOUD_DEPLOY=true`, which has not happened |
| Any container image reference | No registry is owned and nothing has been pushed; `.github/workflows/build.yml` pushes nowhere | A registry and a release policy |
| The scheduler's OIDC audience and the Cloud Tasks identity | Finding S-001 leaves both open, and the A1b identity-provider worksheet is unfilled. Writing a plausible value would be inventing one | S-001 plus a filled A1b worksheet |
| Every Secret Manager **value** | Containers are configuration; values are credentials. A value in Terraform is a value in state | Whoever holds the credential, out of band |
| Memorystore Redis, Pub/Sub, BigQuery, Calendar API | v1.1 §3.1 and the deferral table in §3.5. Each has an objective adoption trigger in `docs/migration/rejected-components.md` | Its trigger firing — adding one earlier is an architecture change, not a configuration detail |
| IAM bindings and project-level API enablement | They grant real access in a real project. Nothing here should grant anything | A deploy target existing |

## The standing constraints this tree is written under

`ALLOW_CLOUD_DEPLOY=false`, `ALLOW_LIVE_PROVIDERS=false`,
`ALLOW_LIVE_DATA=false`. Synthetic data only. Nothing in this directory is a
claim of production readiness, and nothing in it has been applied.
