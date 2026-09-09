# F5 deploy — open questions carried by the classroom root module

**Date:** 2026-09-04 · **Slice:** F5 infrastructure (classroom root module)

The classroom environment now has a root module —
`infra/terraform/envs/classroom/root.tf` — that composes
`infra/terraform/modules/platform`. It exists so `terraform validate` can be run
over a whole environment instead of one leaf module at a time. It is not a
deployment, and it cannot become one by accident: there is no `provider` block,
no `backend`, and every input it supplies is a reserved-namespace placeholder
guarded by a `validation` that rejects anything real.

That last part is what this file is about. Four values the module needs name
things that **do not exist**. Nobody on the engineering side can invent them,
because each is a decision about a registry, a deployment, or an identity
provider that a human has to make and record.

The pattern is the same one the R4 slice used: every item below has a **safe
default that is implemented**, and the default is chosen so that being wrong
about it degrades into *nothing deploys* rather than into *something deploys
somewhere unexpected*. A placeholder that cannot resolve fails at the point of
use, loudly. A plausible-looking invented value fails much later, quietly, and
possibly in somebody else's project.

`ALLOW_CLOUD_DEPLOY` remains `false`. Nothing in `infra/terraform` has been
initialized into a state backend, planned against a real project, or applied.

---

## Summary

| OQ | Question | Blocks | Safe default, implemented | Who decides |
|---|---|---|---|---|
| **OQ-F5-001** | Which registry holds the API and worker images, and what a tag resolves to | A real `terraform plan`; any deploy | `example.invalid/smartmatch/example-classroom-{api,worker}:example`, guarded by a validation requiring the `example` token | Program owner + release policy |
| **OQ-F5-002** | The deployed worker's base URL | The Cloud Scheduler target | `https://example-smartmatch-classroom-worker.example.invalid` — an RFC 2606 host that cannot resolve | Assigned by the first apply; not knowable before |
| **OQ-F5-003** | The OIDC audience the scheduler's token is bound to, and the invoker allowlist | Finding S-001 closing | The same unresolvable host plus `/operations/dispatch`, guarded the same way | Security owner, via Finding S-001 and the A1b worksheet |
| **OQ-F5-004** | Where classroom's Terraform state lives, and under which credential | `terraform init` with a backend; `apply` | No `backend` block at all; `terraform init -backend=false` only, local ephemeral state | Program owner, at `ALLOW_CLOUD_DEPLOY=true` |

---

## OQ-F5-001 — the container registry and the image tags

**Question.** Which registry (Artifact Registry project and repository, or
other) holds the API and worker images, who pays for it, and what does a
`classroom-v*` tag resolve to?

**Why engineering cannot answer it.** A registry is a billed resource in a
project somebody owns, and a tag policy is a release policy. Choosing a
reference means choosing what a classroom-tagged release deploys, which is a
program decision of the kind recorded in
`docs/decisions/f5-deploy-target-note-2026-09-03.md`, not an implementation
detail. `.github/workflows/build.yml` currently pushes nowhere, so there is no
image to name even if the question were settled.

**Safe default, implemented.** `var.api_container_image` and
`var.worker_container_image` in `root.tf` default to references under
`example.invalid`, a domain that resolves for nobody. Each carries a
`validation` requiring the `example` token, so a real reference cannot be
supplied on the command line with `-var` either — it fails at validate time with
a message naming this constraint. `modules/platform` itself still declares both
inputs with **no default**, and `tools/env_isolation_check.py` asserts that they
stay that way.

**What closing it looks like.** A registry exists, `build.yml` pushes to it, and
the placeholder plus its validation are removed in a diff, under review, at the
same time `ALLOW_CLOUD_DEPLOY` changes.

## OQ-F5-002 — the deployed worker's base URL

**Question.** What URL does the Cloud Scheduler job post `/operations/dispatch`
to?

**Why engineering cannot answer it.** A Cloud Run service URL is assigned by
Google at apply time. It is not a configuration choice; it is an output of a
deployment that has never happened. Writing a plausible one — guessing the
`run.app` hostname shape — would be inventing a fact.

**Safe default, implemented.** `var.worker_base_url` defaults to
`https://example-smartmatch-classroom-worker.example.invalid`. A scheduler job
planned against it targets a host that does not resolve, so a hypothetical
mis-apply produces a job that fails every invocation rather than one that
reaches something real.

**What closing it looks like.** The first apply produces the URL, and the value
then comes from `module.platform.worker_uri` rather than from a variable at all.
That refactor is deliberately not done now: wiring a module's output into its
own input only makes sense once the resources exist.

## OQ-F5-003 — the scheduler's OIDC audience and the invoker allowlist

**Question.** Which audience is the scheduler's OIDC token bound to, and which
service accounts may invoke the worker?

**Why engineering cannot answer it.** Finding S-001 leaves the Cloud Tasks
enqueue identity and the scheduler audience open, and the A1b identity-provider
worksheet (`docs/decisions/a1b-idp-configuration-worksheet.md`) is unfilled.
Both are authorization decisions: an audience is what a receiving service will
accept a token *for*, and getting it wrong either breaks every dispatch or
accepts tokens minted for something else.

**Safe default, implemented.** `var.scheduler_token_audience` defaults to the
unresolvable worker host plus `/operations/dispatch`, guarded by the same
`example` validation. Nothing would accept a token bound to it, which is the
correct failure: no dispatch rather than an unauthenticated one.

**What closing it looks like.** S-001 resolved, A1b Part 1 filled, and the
audience derived from the real worker URL alongside an explicit invoker IAM
binding — which this tree also deliberately does not contain (see the "What is
deliberately absent" table in `infra/terraform/README.md`).

## OQ-F5-004 — where classroom's Terraform state lives

**Question.** Which bucket holds classroom's state, under which credential, with
what locking and retention?

**Why engineering cannot answer it.** A state backend is a real bucket in a real
project reached with a real credential, and Terraform state contains every
resolved value in the configuration. Naming one is claiming a project exists and
that somebody is responsible for what leaks if that bucket is readable.

**Safe default, implemented.** There is **no `backend` block** anywhere in
`infra/terraform`, and `tools/env_isolation_check.py` fails the build if one
appears — in a module, in an environment registry, or in the root. The only
supported workflow is `terraform init -backend=false`, which keeps state local
and throwaway and is sufficient for `terraform validate`. `.tfstate`, `.tfplan`,
`.tfvars`, and `.terraform.lock.hcl` files are all failures if committed, so a
local init cannot leak into the repository unnoticed.

**What closing it looks like.** The program owner sets `ALLOW_CLOUD_DEPLOY=true`
having named a project, a state bucket, and a credential holder, and a human
adds the `provider` and `backend` blocks in a reviewed diff. Until then the root
module can be validated and nothing else.

---

## What is *not* an open question

- **Whether classroom may hold live data or a provider credential.** It may not,
  ever (architecture v1.1 §3.3). `provider_mode = "fixtures"` and
  `provider_secret_id = null` are asserted by the check, not chosen per release.
- **Whether classroom promotes to prod.** It does not, in either direction. The
  check asserts that too.
- **Whether the identifiers are unique.** They are, and
  `tools/env_isolation_check.py` proves it on every commit. The root module
  passes every identifier through from the registry in
  `envs/classroom/main.tf`; it mints none of its own, and a literal at the call
  site is a build failure.
