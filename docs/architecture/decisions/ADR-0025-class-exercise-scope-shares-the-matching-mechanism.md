# ADR-0025 — The class exercise is a second product scope that shares the matching mechanism

**Status:** Accepted
**Date:** 16 September 2026
**Owner of record:** Ann Wang (class-exercise scope), with the team (Chau, Danny, Janice, Justin)
**Decides:** how the Spring 2027 class exercise is built on this platform without touching the CBA platform scope: a second `ProductScope`, its own tables and routers, one shared domain matching mechanism, and one shared student-factor module that both `STUDENT_REGISTRY` (ADR-0024) and the new `EXERCISE_REGISTRY` compose from.
**Requirements:** `docs/product/class-exercise-requirements.md`
**Design:** `docs/superpowers/specs/2026-09-16-class-exercise-design.md`
**Register:** `docs/plans/open-questions/class-exercise-open-questions.md`
**Relates to:** ADR-0016 (CBA scoring policy), ADR-0024 (staged student→event recommender). Amends neither.

> **Accepted.** This ADR adds a scope; it removes, pauses, or re-decides
> nothing. The CBA platform track — student engagement, retention,
> speaker-to-event matching, ADR-0024's recommender — continues on its own plan
> for its own stakeholder. What this ADR fixes is that the class exercise and
> the CBA track run on **one matching mechanism with two rulebooks in two
> processes**, never as a second scoring system and never in the same process
> as real data.

## Context

On 15 September 2026 Ann Wang delivered the requirements for a class exercise
in Dr. Lin's Spring 2027 AI in Marketing course: a no-login site over about
300 made-up profiles, matched to one chosen event with four adjustable factors
in plain words, a ranked list capped at an invite limit with a reason next to
each name, saved settings, a results screen driven by a hidden simulated rule,
and a per-team refresh between two rounds. Her direction to the team: "What
changes is who gets matched to what, not how." Keep the matching engine with
adjustable weights, the ranked list with reasons, and the results screen.

The platform already has the "how": a registry of weighted factors
(`smartmatch_domain.factor_registry`, ADR-0016), a composition that keeps
`unknown` distinct from `0` (ADR-0011), a spec-driven explanation module, and
ADR-0024's decision D2 that the registry mechanism is parameterised into a
`FactorRegistry` value object so a second registry can sit beside
`CBA_REGISTRY`. What the platform does not have is any of the exercise's
"who": no profile with a major, year, interests, or career goal; no
unauthenticated surface; no per-team workspace; no spreadsheet ingest; no
simulation.

The two audiences are different people with different data. The CBA track
serves real students and real events under tenancy, principals, and the
student-engagement register's privacy rows. The exercise serves six teams of
class participants over fictional rows, with no account and no consent
question. The exercise also ranks in the opposite direction: ADR-0024 ranks
events for one student; Ann ranks profiles for one event.

## Decision

### D1. A second product scope, never the same process as real data

`ProductScope.CLASS_EXERCISE` and `Capability.CLASS_EXERCISE` are added to
`smartmatch_domain.product_scope`. The capability is granted only in that
scope. `services/api/smartmatch_api/main.py` registers the exercise routers
under it, following the existing pattern for a router that takes no principal
(`outreach.public_router`). In the exercise scope the authenticated CBA
routers are **not registered**, so `get_current_principal` is unreachable
rather than bypassed; in the CBA scope the exercise routers are not
registered. A test asserts both absences.

### D2. Own tables, keyed by exercise and team, with no tenancy

The exercise stores its data in tables prefixed `exercise_` keyed by
`(exercise_dataset_id, team_number)`. They carry no `tenant_id`, no
`owning_unit_id`, and no foreign key to `user_account`. A team is not a
tenant, and a made-up profile is not an account. Modelling the class as an
`org_unit` under the CBA tenant was rejected: it would mint about 1,800 fake
principals and put synthetic rows one join from real ones. A rule in the
package-boundary check (`make imports`) forbids the exercise routers from
importing `smartmatch_authz` or any tenant-scoped repository.

### D3. One student-factor module, two registries

The four factors Ann names are implemented once, as pure functions over a
`(profile, event)` pair in `smartmatch_domain/student_factors/`:

| Function | Ann's words | ADR-0024 name |
|---|---|---|
| `same_major` | same major | `student_program_affinity` (declared, unbuilt at 0.0) |
| `stated_interest_overlap` | said they are interested in this topic | `student_interest_overlap` (Jaccard over the G3 vocabulary) |
| `career_goal_fit` | career goal fits this event | — |
| `past_event_topic_overlap` | went to similar events before | — |

Two registries compose them, each a `FactorRegistry` from ADR-0024 D2:

- **`EXERCISE_REGISTRY`** (this ADR): the four functions with Ann's labels,
  team-adjustable weights, `status = "approved"` on the authority of the
  requirements document. No owner gate: the exercise has no privacy question
  to wait on.
- **`STUDENT_REGISTRY`** (ADR-0024): the same functions under the
  student-engagement owners' governance, `status = "proposed"`, failing closed
  until OQ-SE-01. ADR-0024's decisions about it are unchanged; what changes is
  only that its factor implementations are imported from `student_factors/`
  rather than written a second time.

`CBA_REGISTRY` and every speaker-side constant stay bit-identical.
`tests/unit/test_factor_registry.py` is not edited. `PROHIBITED_INPUTS` is
imported, never redefined.

### D4. Two rankers over the same functions

`rank_profiles_for_event(event, profiles, ...)` is built for the exercise and
returns `StageBScore` with `subject_id` holding the profile id. ADR-0024's
`rank_events_for_student` is built on the CBA track's own schedule and holds
the event id in the same field, as its contracts already document. Neither
ranker imports the other. Unavailable information is `unknown`, never `0`
(ADR-0011), and weights are never re-spread per candidate (ADR-0016).

### D5. The exercise tie-break is its own function

`smartmatch_domain.scoring._ranked` (known first, value descending, subject id
ascending) is untouched. The exercise adds `_exercise_ranked`, which extends
the same key: more information on file first, then year with seniors first,
then a fixed permutation seeded from the dataset checksum alone, so the order
never changes between runs, teams, or processes. The reason line names the case:
"tied on major; ordered by year."

> **Correction, 19 September 2026.** This paragraph read "seeded from the
> dataset id alone". The seed is the dataset **checksum**, as the design spec
> §4.4 and `rank_profiles_for_event(..., dataset_checksum=...)` in
> `smartmatch_domain/exercise/matching.py` have both always said. A factual
> correction of a detail, not a re-decision: the decision — that the exercise
> has its own tie-break, ending in a fixed permutation seeded from the dataset
> — is unchanged, so the status and date above stand and this is not an
> amendment.

### D6. Hidden true interests are stored and never leave the server

The data file's hidden "true interests" column is stored on the profile row,
is a member of `EXERCISE_WITHHELD_FIELDS`, appears on no response model, and
is read by no factor function. Only the simulated-results rule reads it. A
schema-walking test asserts the field name appears in no exercise response and
in the exported OpenAPI document nowhere.

### D7. The simulated-results rule is deterministic per team and written in words

The rule that turns a list into invited / signed up / attended lives in one
module whose docstring states it in plain words, copied into the design spec
and sent to Ann and Dr. Lin before the practice run. Its coefficients are named
constants. Its chance element is seeded per team, so the same list twice gives
the same answer, and a team's reset touches only that team's rows.

### D8. No numeric score reaches a class participant

Carried over from ADR-0024 D8 because it costs nothing and keeps the two
scopes' surfaces alike: the exercise shows rank, the four weights the team
set, and one reason per name. It shows no percentage, score, or confidence.

### D9. Rejected

- **A standalone exercise scorer** that never touches `factor_registry.py`.
  Cleanest separation, but a second scoring system beside the first, which
  ADR-0016 and ADR-0024 D1 forbid.
- **Per-route bypass of `get_current_principal`** inside the CBA scope.
  Smallest diff, but puts a no-auth route in the same process as real data.
- **A separate repository.** Would vendor `smartmatch_domain`, turning the
  shared mechanism into a copy, and double the CI and deploy surface for a
  four-person team.
- **Any code identifier containing "demo".** `tools/scan_forbidden.py`
  rejects `demo_mode`, `DEMO_MODE`, and `if demo`; the scope is called
  *exercise* throughout.

## Consequences

**Good.** Ann's "none of your work is wasted" holds literally: the weight
registry, composition, explanation, and determinism machinery serve both
scopes. The exercise's four factors are the CBA track's student factors,
built and tested once. Nothing in the CBA track moves, and no real datum can
be served by the exercise process.

**Bad, accepted.** The same four people carry two tracks; the shared work is
the D2 parameterisation and the factor module, and everything else is
additive. The exercise adds a table set, a migration, a CSV path, and a
hosting target that exist for one course.

**Verification.** ADR-0024 D2's parameterisation lands with
`test_factor_registry.py` untouched; `make imports` enforces D2's boundary;
`make scan` enforces D9's naming; the scope-absence tests enforce D1; the
schema walk enforces D6; golden cases under `tests/golden/exercise/` cover
every factor known and unknown, every tie-break branch, and the simulation's
per-team determinism.

## Amendment discipline

A later change to which factors the two registries share, to the tie-break
order, or to the isolation model amends this ADR. Changing a coefficient, a
percentage, or a default weight is a register row in
`class-exercise-open-questions.md`, not an amendment.
