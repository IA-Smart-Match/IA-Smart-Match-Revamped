# Security policy

**Scope:** this repository as committed. It is not a policy for a running
system, because there is not one.

---

## Deployment status

**Nothing here is deployed, no live provider has been called, and no live data
has been imported.** That is the README's statement of the same fact, and the
scaffold security review is explicit that it reviewed "the target repository as
committed. Not a review of a deployed system — nothing is deployed."

Concretely:

- `infra/terraform/` holds four environment skeletons, one comment line each.
  Nothing has been applied.
- No container image is published anywhere: `.github/workflows/build.yml`
  authenticates to nothing, tags for no registry, and pushes nowhere.
- The API and worker run against fixture providers. A live provider adapter
  cannot be constructed, and a `classroom` edition carrying any provider
  credential fails to boot rather than failing closed later.
- The worker's task endpoint refuses every delivery: real OIDC verification
  ships with no signature backend, so it answers `401` without a credential and
  `501` with one (finding S-001).

So a report against this repository is a report about code, configuration, or
documentation — not about an exploitable production service.

## Reporting a vulnerability

Use **GitHub private vulnerability reporting** on this repository: the
repository's **Security** tab → **Report a vulnerability**. Do not open a public
issue, a pull request, or a discussion describing the problem.

Two honest caveats, because an instruction that does not work is worse than no
instruction:

1. **Private vulnerability reporting has to be enabled in repository settings
   before that button exists.** Whether it is enabled here has not been
   verified — it is a repository setting, not a file, so nothing in this
   checkout can prove it either way. If the Security tab offers no reporting
   option, the setting is off.
2. As of this writing the repository is **private** (checked against the GitHub
   API, 25 August 2026). While that is true, the reachable audience is the
   people who already have access to it.

**There is no security contact email address, and this file will not invent
one.** If private reporting is unavailable to you, contact a repository
administrator through GitHub — the only identity confirmed to exist for this
repository is the GitHub user `BrooklynD23`, who merged pull request #1 — and
send no vulnerability detail through a public channel.

**No response-time commitment is made.** There is no on-call rotation, no
triage roster, and no published SLA; claiming one would be exactly the kind of
documentation-that-is-not-a-control this project treats as a defect.

## Out of scope

- **The legacy repository** (`BrooklynD23/Nebiux-Team-IA-West-SmartMatch`).
  Findings against it have an owner outside this migration; see S-005 in the
  scaffold security review, and MM-A09 in the migration manifest for the one
  severity-1 item, which is a decision rather than an engineering task and is
  unremediated. No write to the legacy repository has been made or is
  authorized.
- **Known and recorded gaps.** Anything already written down is not a new
  report: the scaffold security review's findings S-001 through S-008, the
  README's "Proposed, scaffolded, or deliberately absent" table, and the
  backlog in `docs/plans/remaining-foundation-r1-work.md`. Check those first —
  and if a recorded gap is *worse* than recorded, that is a report worth making.

## What runs on every change

These are controls, not intentions; each is a step in `.github/workflows/verify.yml`:

| Control | Mechanism |
|---|---|
| Secret scanning over full history | gitleaks, in the `secrets` job |
| Dependency vulnerabilities | `pip-audit --strict` against the hash-pinned `requirements/runtime.txt`, so the result describes exactly what gets installed |
| Hard-coded credentials in source **and in documentation** | `tools/scan_forbidden.py`; its credential rule declares no file-type restriction, so committed Markdown is covered too |
| No tracked `.env` file | An explicit check in the `isolation` job; `.gitignore` also blocks `.env`, `*.pem`, `*.key`, and service-account JSON patterns |
| No tracked local databases or archives | An explicit check in the same job |
| Dependency integrity | `--require-hashes` installs in both `make setup` and CI (S-003) |
| Workflow supply chain | Every action pinned to an immutable commit SHA, never a tag |

## What is deliberately not here

Listed rather than omitted, so the matrix is honest about what is not run:
CodeQL, Trivy, and SBOM generation are deferred to the before-live (R1+) stage;
container image scanning, signing, and provenance attestation to before-scale
(R3+). `.github/workflows/verify.yml` carries that deferral list at the bottom
of the file, with the release that introduces each gate.

There is no bug bounty and no advisory publication process.
