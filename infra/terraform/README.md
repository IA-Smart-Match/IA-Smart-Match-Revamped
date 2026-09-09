# Infrastructure

**Nothing here has been applied. `terraform apply` has never been run against
any of it, and `ALLOW_CLOUD_DEPLOY` remains `false`.** What exists is the
configuration for one environment's topology, a registry of the names four
environments would claim, and — for `classroom` alone — a **plan-only root
module** that composes the two, so `terraform validate` has something whole to
read. What still does not exist is any way to turn that into running
infrastructure: no provider block, no state backend, no credential, and no
registry holding an image to deploy.

That is not an aspiration in a comment. `make infra-check` fails the build if a
provider block, a backend, a state file, a plan file, a `.tfvars`, or a lock
file appears anywhere in this tree; if a root module appears in an environment
nobody listed; or if the root's four deploy inputs hold anything but a
reserved-namespace placeholder. A `terraform plan` run here would plan a
deployment of images that do not exist, into a project nothing is authenticated
against — and an `apply` cannot begin at all, because there is nothing to
authenticate as.

## Layout

```
infra/terraform/
  envs/{dev,staging,classroom,prod}/main.tf   registry of names — locals only
  envs/classroom/root.tf                      the one root module — plan-only
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

`envs/classroom/root.tf` is the third piece, and it is deliberately the thinnest
one: a `terraform` block, four `variable` blocks holding placeholders, and one
`module "platform"` call that passes every identifier straight through from
`main.tf`. It mints no name of its own, declares no resource, configures no
provider, and names no backend. What it buys is real — the composition
type-checks as a whole rather than one leaf module at a time — and what it costs
is bounded by the assertions below.

### Why classroom, and only classroom

`classroom` holds no provider credential at all (v1.1 §3.3), so a root module
there cannot be one secret away from an apply. `ROOT_MODULE_ENVIRONMENTS` in
`tools/env_isolation_check.py` is that decision written down; a `root.tf`
appearing in `dev`, `staging`, or `prod` fails the build twice over — once as an
unlisted root module, once as a stray file in an environment directory.

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
| Cloud Scheduler | `cloud_scheduler_job` | HTTP job posting to `/operations/dispatch`, one attempt, scheduler-scoped OIDC token | The audience and the target URL. Both are module inputs with no default; the classroom root supplies unresolvable `example.invalid` placeholders, guarded so a real value cannot replace them |
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
| 13 | The four deploy inputs — both images, the worker URL, the scheduler audience — declare no default *in the module* | A default in the module is one value every environment inherits. The placeholders live at the call site instead, where a fake value is obviously fake and review sees it |
| 14 | No state, no plan, no `.tfvars`, no lock file; nothing in an environment directory beside `main.tf` and a permitted `root.tf` | Each is produced by running something, and nothing here has been applied. The stray-file rule closes the obvious way around assertion 5 |

Over `envs/<env>/root.tf`, where one exists — because a caller is the thing that
makes an apply *conceivable*, and the whole value of the file depends on it
staying unable to do one:

| # | Assertion | Why it is there |
|---|---|---|
| 15 | Only an environment listed in `ROOT_MODULE_ENVIRONMENTS` may have a `root.tf` | Which environments may hold a root module is a decision, not a default. Today the list is `classroom`, the one project with no provider credential |
| 16 | Only `terraform`, `variable`, `module`, and `output` blocks; no `provider`, no `backend`, no `resource`, no `data`, no `locals` | A provider names the credential an apply would use; a resource or data block reaches a live project directly; a `locals` block would mint a name the registry never saw |
| 17 | Exactly one `module` call, labelled `platform`, sourced from the local path `../../modules/platform` | A remote or registry source fetches code nobody here reviewed. One call means one environment's topology, reviewed as a whole |
| 18 | Every input `modules/platform` declares is passed, none that it does not, and every value is a `local.*` or `var.*` reference — never a literal | A literal at the call site is a name the registry never saw and disjointness cannot read. An omitted input is one Terraform prompts for, or fills from somewhere nobody checked |
| 19 | Only the four deploy inputs may be declared as root `variable`s | Identifiers come from the registry in `main.tf`, where uniqueness is asserted. A root variable holding one would route around that |
| 20 | Each deploy input has a placeholder default carrying the `example` token, on a reserved domain, **and** a `validation` requiring that token | The default alone is only a suggestion — `-var` overrides it silently. The validation is what makes passing a real image reference fail loudly, so a real value cannot arrive without deleting an assertion in a reviewed diff |

The check parses a small subset of HCL rather than shelling out to `terraform`,
so it runs in CI and on a laptop with no Terraform installed and no network. A
value the subset cannot read — an interpolation, a variable reference — is a
parse error rather than a skipped line: a value it cannot resolve is a value
whose uniqueness it cannot assert.

It is itself self-tested in `tests/unit/test_env_isolation_check.py`, including
the cases that matter: two environments given the same project id, a module
given a default for a name, a `provider` block added to the root, and a real
`us-west1-docker.pkg.dev/...` image reference passed to a deploy input. Each
must fail. A uniqueness assertion never shown to fail is indistinguishable from
`return 0`, and a root-module gate never shown to fail is worse — it is the one
file that could deploy something.

`modules/platform` also carries two `precondition` blocks restating the rule
where a plan would see it. They are **not** the assertion of record — they run
only if somebody runs a plan, and nobody has, and a plan sees one environment at
a time, so they cannot see a cross-environment collision at all.

### Running it

```bash
make infra-check                 # the gate; stdlib only, no Terraform needed
terraform fmt -check -recursive infra/terraform
```

`make infra-check` is the assertion of record and needs no Terraform at all.
Validating the configuration does need it:

```bash
cd infra/terraform/envs/classroom
terraform init -backend=false    # downloads the Google provider; no state, no backend
terraform validate               # "Success! The configuration is valid."
```

`-backend=false` is not a convenience flag here, it is the point: there is no
`backend` block to initialize, so state would be a local file that nobody should
keep. `init` leaves a `.terraform/` directory and a `.terraform.lock.hcl` behind
— both gitignored, and both a `make infra-check` failure if one is ever
committed, so **delete them when you are done**:

```bash
rm -rf infra/terraform/envs/classroom/.terraform infra/terraform/envs/classroom/.terraform.lock.hcl
```

Each module under `modules/` still validates on its own the same way.

**What you cannot do from here.** `terraform apply` — and any `plan` that would
be worth reading — needs a configured provider, and there is no `provider` block
in this tree. Adding one means naming a project and a credential, which is the
program owner's `ALLOW_CLOUD_DEPLOY=true` decision and has not happened. Even
with a provider added, the four deploy inputs would still refuse a real image
reference or a real URL: their `validation` blocks require the `example` token,
so the values would have to be changed in a reviewed diff too. Two separate,
visible acts by a human, neither of which this repository can perform on its
own.

## What is deliberately absent

| Absent | Why | Closed by |
|---|---|---|
| A provider block and a state backend | Together with a credential they are what makes an apply possible. There is no deploy target and no credential | The program owner setting `ALLOW_CLOUD_DEPLOY=true`, which has not happened (OQ-F5-004) |
| A root module in `dev`, `staging`, or `prod` | Those projects would hold a provider credential; classroom holds none, which is why it is the only one permitted a caller | A deploy target existing for that environment, decided the same way |
| Any real container image reference | No registry is owned and nothing has been pushed; `.github/workflows/build.yml` pushes nowhere. The root supplies an `example.invalid` placeholder its own validation refuses to let you replace | A registry and a release policy (OQ-F5-001) |
| The scheduler's OIDC audience and the Cloud Tasks identity | Finding S-001 leaves both open, and the A1b identity-provider worksheet is unfilled. Writing a plausible value would be inventing one | S-001 plus a filled A1b worksheet (OQ-F5-003) |
| Every Secret Manager **value** | Containers are configuration; values are credentials. A value in Terraform is a value in state | Whoever holds the credential, out of band |
| Memorystore Redis, Pub/Sub, BigQuery, Calendar API | v1.1 §3.1 and the deferral table in §3.5. Each has an objective adoption trigger in `docs/migration/rejected-components.md` | Its trigger firing — adding one earlier is an architecture change, not a configuration detail |
| IAM bindings and project-level API enablement | They grant real access in a real project. Nothing here should grant anything | A deploy target existing |

## The standing constraints this tree is written under

`ALLOW_CLOUD_DEPLOY=false`, `ALLOW_LIVE_PROVIDERS=false`,
`ALLOW_LIVE_DATA=false`. Synthetic data only. Nothing in this directory is a
claim of production readiness, and nothing in it has been applied.

The four values the classroom root supplies as placeholders are open questions
with named owners, not oversights:
`docs/plans/open-questions/f5-deploy-deferred.md` (OQ-F5-001 through
OQ-F5-004).
