# W4 — the aggregate student demand signal (2026-09-13)

**Status:** planning only. No source file changes, no route, no migration.

**Parent:** [`2026-09-13-student-recommendation-program-plan.md`](2026-09-13-student-recommendation-program-plan.md).
**Depends on:** W1 only. Fully parallel with W2.
**Migration:** none.

---

## 1. What this is for, and what it refuses to be

The stakeholder framing was that the platform serves **both** the student and the
Event Host: student demand should help identify the right speaker. This wave
delivers the honest half — a Connector can see **what their unit's students
actually want**, in aggregate, and choose a topic accordingly.

It does not make demand a scoring input. `OQ-CBA-053` is closed with "No", and
`PROHIBITED_INPUTS` names `unrelated_student_feedback`. The judgement stays with
the human filing the Speaker Request; W4 gives them a number they do not have
today. §6 makes that separation executable rather than documentary.

## 2. Build it as a sibling of `speaker_pipeline`

The capability merged in PR #156 is the template, and five of its rules transfer.

**It derives nothing new.** Its docstring: every number "was already measured by
exactly one owning query"; the module adds only "which of those numbers form a
cohort funnel, which ratios between them are legitimate, and which sentences a
coordinator is shown." That is ADR-0011 rule 4 applied to ratios — "a conversion
rate is a published number too, and a second copy of it in JSX is a second
definition."

**Unknown propagates.** A ratio with an unknown side is `None` plus an
`unavailable_reason` naming which side was missing — "never `inf`, never `nan`,
never a silent `0%`."

**Illegitimate ratios are refused**, because "a 'conversion' above 100% is the
visible symptom of dividing two independent aggregates."

**This bites W4 hard, and it is the wave's central design fact.** Declared
interests and registrations are **not** nested sets — a student may declare
`hackathon` and register for nothing, or register having declared nothing. So
*interest count* and *registration count* are **companion figures presented side
by side, never a funnel and never a conversion between them.** §6 pins that a
future "conversion" between the two fails a test rather than shipping.

**Prose is bounded and server-authored** — `MAX_INSIGHTS`,
`MINIMUM_BASELINE_FOR_INSIGHTS`, `INSUFFICIENT_ACTIVITY_MESSAGE`.

**One request, one session**, reusing the metrics surface's own
`_authorize_aggregate_read` rather than inventing an authorization.

## 3. Route, roles, and the role decision that is not mine

**`GET /v1/units/{unit_id}/engagement/interest-demand`**, added to
`routers/engagement.py` — same persona, same authorizer shape, same "counts, never
a roster" discipline. Putting it elsewhere would invite a second discipline.

**Roles: `{admin, coordinator}`**, as its own literal constant
`_INTEREST_DEMAND_ROLES`.

The session's framing said "host-facing", and `volunteer` — the stored role behind
the Event Host presentation name — is **not** in the engagement set today.
`OQ-CBA-042` decided that an Event Host does not even learn who declined their own
request; with D8 open, the narrower reading on deny-by-default is the safe one.
**W4 therefore excludes the Event Host and registers the widening as its own
question.** This is put to the owner rather than decided here: it is a real
reduction in what the session asked for, and it should be a choice rather than an
omission.

## 4. Response

```
InterestDemandResponse:
  unit_id, generated_at, vocabulary_version
  population_basis: str          # states exactly who was counted
  total_profiles: int | null
  total_suppressed: bool
  by_term: [ { term, student_count: int | null, suppressed: bool } ]   # ALL TWELVE, always
  caption: str                   # words whenever anything is withheld
```

The cell's `__post_init__` makes the leak **unrepresentable** —
`SpeakerFeedbackAggregate`'s device: a suppressed cell carrying a number, or an
unsuppressed cell carrying none, raises.

A term nobody picked is a **measured 0**, not a suppression and not an absent
key — the claim `AttendanceSummaryResponse.by_method` already makes ("a mechanism
with no rows is a measured 0, not an absent key"). Twelve keys, always.

## 5. Suppression, transposed carefully

New domain module `smartmatch_domain/student_interest_demand.py` with **its own**
`MIN_PROFILES_FOR_AGGREGATE = 3` — deliberately the same value as
`MIN_RESPONSES_FOR_AGGREGATE`, deliberately **not an import of it**: a different
population and a different decision, and a shared import would let a relaxation of
one silently relax the other. *Within* the module it is one constant used by both
conditions, which is the feedback module's own rule ("a second constant would let
one of them be relaxed without the other, which is how a differencing guard
rots").

Four exposures, each closed:

**1. Small cells.** A term with 1 or 2 students publishes nothing — and withholds
the **count as well as** any derived figure, because "a suppression that still
publishes n has suppressed only the harmless half."

**2. Differencing against the total — and the feedback residual does not transpose
directly.** Interests **overlap**, so the sum of term counts exceeds the number of
students and the per-speaker residual identity is simply false here. Define the
residual over **students**, which is computable in SQL:

```
residual = total_profiles − count(distinct students appearing in at least one published term)
publish total_profiles iff total_profiles >= 3 and (residual == 0 or residual >= 3)
```

This closes "there are 5 profiles and 3 are accounted for by published terms, so
2 students' entire interest sets live in the suppressed terms."

**3. Co-occurrence — the genuinely dangerous one, and no per-term threshold
catches it.** "The student interested in *capstone showcase* is also interested in
*judge*" re-identifies at a granularity this response must never reach.
**Cross-tabulation is prohibited outright:** no pair counts, no per-student
vectors, no filter parameters that could be composed into one (**no `?term=`, no
`?filter_by=`**), and no breakdown crossing interest with attendance,
registration, event, or time. Stated in the module docstring and pinned in the
response model's shape.

**4. Differencing across time.** **Not defended against, and the plan says so**
rather than claiming otherwise — `OQ-CBA-003` already accepted the same limitation
for the per-speaker read.

## 6. Persistence, and the population problem W1 creates

Repository method `interest_counts_for_unit(...)` doing
`count(distinct student_profile.user_id)` grouped by term **inside the
database** — `engagement.py`'s precedent: it "aggregates with `count(distinct ...)`
inside the database and never selects the identifier." The returned dataclass
carries counts and no ids, so the guarantee is **structural**, not a filter the
router remembers to apply.

**W1 gives `student_profile` no `owning_unit_id`** (a profile is a fact about a
person, tenant-scoped), so **"students in this unit" needs an explicit
definition.** Two candidates:

- **(a)** accounts holding a `membership` row with role `student` on the unit's
  path;
- **(b)** accounts with at least one `event_registration` or `attendance_record`
  in the unit.

**Recommend (a)** if the pilot actually grants per-unit student memberships — the
implementer verifies against `principals.py` and the dev-principal composition —
falling back to **(b)** if it does not. Whichever is chosen, the response states
it in `population_basis`, **because a count whose population is undefined is not a
fact**, and a test pins that string against the query that produced it.

## 7. What a Connector may and may not see

**May:** how many students in the stated population declared each of the twelve
terms, subject to suppression; the total number of profiles, subject to the
residual rule; the vocabulary version; the population basis; the generation
instant; a worded caption whenever anything is withheld.

**May not:** any student id, email, external subject, or name; any list of
anything; any cell below threshold; the total when the residual rule fails; any
co-occurrence, pair count, or per-student vector; any crossing of interest with
attendance, registration, program, graduation term, or a specific event; any
per-event "how many students want this"; and any path by which these numbers reach
a scoring factor.

## 8. Tests

| Level | Asserts |
|---|---|
| unit | Below threshold everything is `None`; a suppressed cell carrying a number raises at construction; the **student-based** residual rule in both directions (`residual == 0` publishes, `2` suppresses, `3` publishes); all twelve terms always present; an unpicked term is a measured 0 |
| unit | **Interest and registration counts are never divided by each other** — a pin naming both figures, so a future "conversion" between them fails rather than ships |
| contract | **Identifier-free by schema walk**: no property named `*_id` except `unit_id`; no `email`, `name` or `subject` anywhere in the response tree; `population_basis` present and non-empty; the route's parameter list is **exactly** `{unit_id}` — no filter or cross-tab parameter exists; a student token is `403`; a cross-tenant unit is `404` |
| integration | The repository's return type carries no identifiers (structural, and better than asserting on SQL text); counts correct for a seeded population with **overlapping** interests |
| structural | `test_demand_not_a_factor_wiring.py` — import reachability: `student_interest_demand` is **not reachable** from `smartmatch_domain.scoring` or any module in `smartmatch_domain.factors`. The owner's "no demand-weighted scoring" decision, executable |

## 9. Where it appears

A `components/studentDemand/` family with `lib/studentDemand.ts` and
`tests/studentDemand.test.ts`, mirroring `speakerPipeline` file for file. It
belongs beside the **Speaker Request form**, where the number changes a decision:
whoever chooses a topic sees what the unit's students asked for before they type
it.

Subject to **D-0** — new product UI stays blocked until D-1..D-11 are ratified, so
the section is designed here and rendered in the external prototype, not merged.

## 10. What W4 does not do

- No named student, at any threshold.
- No scoring input; no factor reads these figures.
- No cross-unit or tenant-wide view.
- No demand figure on a **student-facing** surface. A student does not need to
  know how many peers share an interest, and telling them is a disclosure with no
  purpose behind it.
