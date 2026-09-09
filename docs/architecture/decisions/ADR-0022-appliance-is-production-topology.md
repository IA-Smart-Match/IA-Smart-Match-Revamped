# ADR-0022 — The Docker Compose appliance is the production topology

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §3.1–§3.3; Foundation F5
**Backlog:** Stage 2 migration increment M7
**Findings:** `docs/architecture/risk-register.md` R-18;
`docs/architecture/current-system-topology.md` §1;
`docs/plans/open-questions/f5-deploy-deferred.md` OQ-F5-001…004

## Context

Two deployment topologies are described in this repository and one of them runs.

**The appliance runs.** `docker-compose.yml` defines 12 services;
`docker-compose.vm.yml` is the VM overlay; `.github/workflows/build.yml` builds
the images and runs `compose smoke` and `pilot e2e` against them;
`.github/workflows/deploy.yml` deploys over IAP to a pilot VM and then probes the
public URL through Cloudflare Access. `smartmatch.sh` / `smartmatch.ps1` drive it
locally. The 26-step e2e walk runs against this, and only this.

**The GCP path is a design record.** Seven Terraform modules across four
environments. `infra/terraform/envs/dev/main.tf:1` states it in its own first
line — "dev environment — configuration only. NOTHING HERE IS APPLIED." — and
explains that there is no provider block, no backend block, and no resource,
module or data block, because "an environment skeleton that can be applied is not
a skeleton". `tools/env_isolation_check.py` fails the build if one appears, if
committed state or a plan or a `.tfvars` appears, or if a non-placeholder
identifier appears. Every identifier is in the reserved `example` namespace,
RFC 2606 for domains, and the check asserts that too.

The finding is not that either is wrong. Both are deliberate and both are
defended in their own files. The finding is that **the repository never says
which is current** (R-18). The consequence is asymmetric in a way that matters:
rollback, log destination, and deploy-time migration are all answered for the
appliance and unanswered for GCP. So the appliance — the thing that actually
serves the pilot — reads as interim scaffolding sitting beneath a real
architecture, and every planning conversation starts by re-deriving which one it
is talking about.

`f5-deploy-deferred.md` records what the GCP path is missing, and none of it is
engineering's to supply: which registry holds the images and what a tag resolves
to (OQ-F5-001, program owner and release policy); the deployed worker's base URL
(OQ-F5-002, assigned by the first apply and not knowable before); the OIDC
audience the scheduler's token is bound to and the invoker allowlist (OQ-F5-003,
security owner, via finding S-001); and where Terraform state lives and under
which credential (OQ-F5-004, program owner, at `ALLOW_CLOUD_DEPLOY=true`).

## Decision

**The Docker Compose appliance on a VM is the production topology of record. The
Terraform is a forward design record, non-applyable by design, and stays that way
until the F5 open questions close.**

Concretely:

1. **The appliance answers the operational questions.** Rollback is a redeploy of
   the previous image tags. Logs are the container's. Deploy-time migration is the
   `migrate` one-shot service. These are the answers of record; where a document
   asks "how does this deploy", it is answered for the appliance, not deferred to
   GCP.
2. **Non-applyability is a property to preserve, not a limitation to remove.**
   `tools/env_isolation_check.py` is a gate, and non-negotiable rule 13 — never
   weaken an existing gate — covers it. The Terraform is documentation that
   happens to be written in HCL, which is a better fidelity than prose because a
   reviewer can read the resource graph, and it stays that way.
3. **The Terraform is not deleted.** It is the record of what the GCP shape would
   be, and it is where the seams named in ADR-0021 point. Deleting it would
   discard design work and make the eventual decision start from nothing.
4. **Preconditions on any GCP work.** Before an environment becomes applyable:
   - ADR-0021's task-delivery contract suite exists and is green, so a live Cloud
     Tasks adapter is measured rather than improvised (R-01);
   - OQ-F5-001…004 are answered by their named owners, because each is a fact
     engineering cannot invent — a registry, a hostname assigned by the first
     apply, an audience bound by the security owner, a state backend and its
     credential;
   - `ALLOW_CLOUD_DEPLOY=true` is set deliberately by the program owner, which is
     the switch OQ-F5-004 already names.
5. **This is a statement of current fact, not a permanent architectural
   commitment.** If the pilot outgrows a single VM, this ADR is superseded by one
   that argues the case with the load evidence that motivated it — the same
   standard v1.1 §2.4 sets for Redis, Pub/Sub and BigQuery.

## Consequences

**Good.** The question "where does this run" acquires one answer, and every
document that needs it can cite this rather than re-deriving it from workflow
files. Rollback, logs and migration stop reading as unanswered — they were
answered, for the topology in use, and this says so. The Terraform stops looking
like an unfinished build and starts reading as what it is: a design record whose
non-applyability is enforced. And ADR-0021's contract gets a stated place in the
sequence rather than being optional preparation for work nobody has scheduled.

**Cost.** Naming the appliance as production makes its limits the system's
limits, on the record: one VM, one PostgreSQL container, no managed backup story
in this repository, and a scheduler that is a sidecar rather than Cloud
Scheduler. Those are true today and unstated; stating them invites the question
of what happens at the next scale, which is the right question to invite and not
a comfortable one. It also means someone reading the Terraform may reasonably ask
why it is maintained at all — answered above, but the maintenance cost is real.

**Enforcement.** `tools/env_isolation_check.py` in the `isolation` job already
enforces the second half — nothing applyable, no shared identifier between
environments — and `verify.yml`'s deferred list records that this is
configuration validation rather than the IaC scan, which needs real resources
there are none of. The first half is a documentation statement and is enforced by
being cited: `current-system-topology.md` §1 and any deployment document point
here.

## Alternatives considered

**Declare GCP Cloud Run the target architecture and the appliance an interim
step.** Rejected on the evidence. The appliance is what CI builds, probes and
deploys, and what the 26-step e2e walk exercises; the GCP path has never run and
four of its basic facts are unanswered by anyone in engineering. Calling the
running system interim would make the repository's own documentation false in the
other direction, and would license speculative GCP work that
`OPUS_AUDIT_HANDOFF.md` §7 rules out.

**Delete the Terraform.** Rejected: it is a genuine design record with an
enforced safety property, and deleting it would discard the resource-level
thinking that ADR-0021's adapter contract is written against. The problem R-18
identifies is ambiguity about status, not the existence of the files, and the fix
for ambiguity is a statement.

**Make one environment applyable so the path is proven.** Rejected: it weakens
`env_isolation_check.py`, which non-negotiable rule 13 forbids, and it would need
OQ-F5-001…004 answered first anyway — at which point the decision is a real one
made with the owner, not a test.

**Say nothing and let the workflows speak.** Rejected: that is the present state,
and R-18 exists because reading four workflow files and a Terraform header is
what it currently costs to learn which topology is real.
