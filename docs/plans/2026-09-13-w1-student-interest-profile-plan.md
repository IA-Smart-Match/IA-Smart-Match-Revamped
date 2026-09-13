# W1 — the student interest profile (2026-09-13)

**Status:** planning only. No source file changes, no route, no migration written
by this document.

**Parent:** [`2026-09-13-student-recommendation-program-plan.md`](2026-09-13-student-recommendation-program-plan.md).
**Blocked on:** **OQ-SC-02** — what a student may be asked, and what may be stored.
**Migration:** `0037_student_profile`, `down_revision = "0036_host_organization"`.
One revision, and the **only** revision in the whole programme.

---

## 1. The problem in one paragraph

`user_account` is `id, tenant_id, external_subject, email, suspended, created_at,
version`. There is no major, no interest, no availability, no preference — nothing
declared about a student anywhere in the schema. The only student signals are
behavioural: `event_registration`, `attendance_record`, `student_speaker_feedback`.
Meanwhile every published event carries `tags` mapped into a closed vocabulary.
**The join has one side.** W1 builds the other, and nothing downstream starts
until it exists.

## 2. The vocabulary: bind to G3, do not re-type it, do not partition it

New module `smartmatch_domain/student_interests.py` that **declares no terms of
its own**:

```
STUDENT_INTEREST_VOCABULARY         = G3_VOCABULARY          # referenced, never re-typed
STUDENT_INTEREST_VOCABULARY_VERSION = VOCABULARY_VERSION     # "g3-2026-08-29"
STUDENT_INTEREST_BINDING_VERSION    = "1.0.0-proposed-oq-sc-02"
```

Two version constants doing different jobs. The first is stamped on every stored
interest and is what the W2 factor compares against an event tag's version — a set
overlap must never cross vocabulary versions, the refusal `industry_match`
already makes for `NAICS_TAXONOMY_VERSION`. The second records **when a human
agreed these twelve terms are also a legitimate *student-interest* vocabulary**,
which is a separate decision from G3's own approval and must not borrow its date.
Until an owner signs it the string carries `-proposed-`.

### The constraint that decides this, and the caveat it forces

`event_vocabulary.py` records that §6.1 **declined** splitting event-type terms
from speaker-role terms, and that `TERM_CONCEPTS` is "present for a reader, never
for a resolver: partitioning tags by this mapping would quietly implement the
design that was not adopted."

So **"students pick from the seven type terms" is not available to an executor.**
It is either all twelve or a new owner-approved vocabulary. W1 takes all twelve,
and `student_interests.py` **must not import `TERM_CONCEPTS`** — pinned by a test
that reads the module source.

**The honest caveat, to be stated in the UI copy rather than papered over:** a
student ticking `mentor` or `judge` is saying *"show me events tagged that way"*,
which is well defined because the tag is on the event. That reading is what the
single-namespace decision forces.

### Rejected, each for its own reason

| Candidate | Why not |
|---|---|
| The 7 "type" terms | Requires partitioning by `TERM_CONCEPTS` — the declined design |
| The 5 manual-event categories | A **router** Pydantic validator (`manual_events_models._CATEGORIES`), not a domain vocabulary: no version constant, no CHECK, and present only on manually filed events, so a crawled event has no category and the overlap denominator is undefined for most of the catalog. `hackathon` is in both sets with no stated relationship |
| NAICS sectors | An employer taxonomy for someone with no employer; no event carries a NAICS code |
| CBA role categories | Speaker-side by construction; a student surface built on it walks toward OQ-CBA-064 |
| A fresh student vocabulary | Correct eventually, an invention now. Kept cheap: it is **one constant**, so the day an owner approves a distinct list exactly one binding changes and the factor's cross-version refusal catches every stale stored row |

## 3. Two tables, not an array column

### `student_profile` — 1:1 with `user_account`, tenant-scoped

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `tenant_id` | UUID NOT NULL |
| `user_id` | Composite FK `(tenant_id, user_id)` → `user_account(tenant_id, id)`, **ON DELETE CASCADE** |
| `modality_preference` | Text NOT NULL, **no server default** |
| `created_at`, `updated_at` | timestamptz NOT NULL |
| `version` | Integer NOT NULL DEFAULT 1 — optimistic lock (`event_manual_detail`'s precedent; a student editing on two devices is that race) and the input pin W2's response returns |

Constraints: `uq_student_profile_tenant_id (tenant_id, id)` — ADR-0004, and the
target the child's composite FK points at; `uq_student_profile_user
(tenant_id, user_id)` — one profile per account, and the `ON CONFLICT` target that
makes `PUT` an upsert; `ck_student_profile_modality` over
`in_person | virtual | no_preference`; `version >= 1`.

**CASCADE here, against the RESTRICTs elsewhere.** A profile is a *statement by*
an account; when the account goes there is nobody whose statement it was.
`attendance_record` and `redemption` RESTRICT because they are records *about*
someone, and evidence outlives convenience.

**No `owning_unit_id`.** A profile is a fact about a person, tenant-scoped like
`user_account`, not about an event in a unit like `attendance_record`.
`routers/rewards.py` states the precedent: "`{unit_id}` in the path is the
*authorization* scope — the strictest this API can express — not a claim that the
resource belongs to the unit." **One consequence W4 must absorb:** "students in
this unit" then needs an explicit definition, which W4 states in its response.

### `student_profile_interest` — shaped like `event_tag` so the two intersect in SQL

`id`, `tenant_id`, composite FK `(tenant_id, profile_id)` → `student_profile`
**CASCADE** (an interest cannot outlive the profile that declared it —
`event_tag`'s reason), `term` **NOT NULL**, `vocabulary_version` NOT NULL,
`created_at`. `uq_student_profile_interest_term (profile_id, term)`, mirroring
`uq_event_tag_term`.

**No quarantine arm — the deliberate difference from `event_tag`.** That table
carries `resolution IN ('mapped','quarantined')` with a nullable `term` because it
ingests strings from the wild. This table's only writer is a student choosing from
a list the server just served them, so an unmappable value is a client bug and
must be a `400`, never a stored row. Hence `term NOT NULL`, no `raw_value`, no
resolution CHECK. **Say this in the migration docstring** — an absent column with
a stated reason is the artifact.

**A child table rather than JSONB** (unlike `event_manual_detail.speaker_topics`):
the overlap wants a set intersection against `event_tag` in SQL; each interest
needs its own `vocabulary_version` stamp, which a JSONB array of strings cannot
carry per member; and W4's per-term aggregate is a `GROUP BY` on a column.

**Both indexes land in `0037`, not later:** `ix_student_profile_interest_term` on
`(tenant_id, term)` for W4's `GROUP BY`, and `ix_student_profile_interest_profile`
on `(tenant_id, profile_id)` for the feed read. Spending a second revision on an
index whose query is already written wastes the one-per-PR budget.

## 4. The non-interest fields

The rule — an unanswered decision means the column is **absent**, not
nullable-and-guessed — resolves every one of these.

**`modality_preference` — INCLUDE.** The only one that earns its place. It is not
an education record under any reading, so it does not wait on OQ-SC-02's hard
half; it compares to `event.is_virtual`, which migration `0024` made `NOT NULL`
*precisely* to avoid a third "nobody said" state; and W2 expresses it as a Stage A
filter, so it never needs an invented neutral. NOT NULL with **no server
default** — `student_speaker_feedback.status`' reasoning, that a row's initial
state is a decision the insert makes. `no_preference` is a **stated** indifference
and is a different fact from having no profile at all; that distinction is
load-bearing in W2.

**`program_of_study` — ABSENT.** OQ-SC-02 asks it by name. No factor could consume
it today — no event field describes a target program, and
`event_manual_detail.audience` is free text — so it would be personal data stored
with no reader, the least defensible category.

**`graduation_term` — ABSENT.** Same register row, no comparable event field, and
quasi-identifying in combination with program and unit — exactly the differencing
surface W4 has to defend.

**`preferred_region` — ABSENT.** Two independent blockers: the event side's
`region` is unvalidated free text ≤200 chars with no vocabulary and no CHECK, so
the comparison has no closed domain on *either* side; and a student's home region
is a location datum OQ-SC-02 has not admitted. Do **not** add it as free text "for
later" — a free-text column is where a vocabulary decision gets made silently.

**Channel or disclosure consent — ABSENT.** W3's table, and ADR-0014's argument
that a consent flag hung on another table is a widening.

**What to actually ask the owner:** approve a **two-field profile** — closed
vocabulary interests plus modality. That is a far easier yes than a five-field
one, and it is the whole of what W2 can consume.

## 5. Routes

New module `routers/student_profile.py` — not appended to `student_events.py`,
which is already ~1,160 lines against the repo's 800-line ceiling.

```
GET    /v1/units/{unit_id}/student/profile
PUT    /v1/units/{unit_id}/student/profile
DELETE /v1/units/{unit_id}/student/profile
```

Identity is `principal.user_id` in the `WHERE` clause, never in a body — MM-A01,
as `routers/rewards.py` does it. **No request model carries a `user_id`,
`student_id` or `subject_id` field**, and that absence is pinned structurally.

`GET` returns `200` with an explicit absence, never `404`:

```
unit_id, profile (nullable), profile_state: "declared" | "absent",
interest_vocabulary: [all twelve terms], interest_vocabulary_version
```

Serving the vocabulary *in the read* makes a client structurally unable to invent
a term. A `404` on your own profile reads as "this route does not exist";
`profile_state` says which fact it is.

`PUT` replaces the declared set whole, idempotent, creating on first call, and
**re-reads and returns the stored row** rather than acknowledging —
`StudentRegistrationResponse`'s no-toast-only-success rule. It **refuses an empty
interest list** with a worded `400`: a profile declaring nothing is not a weaker
profile, it is a row whose only effect is to turn an honest UNKNOWN into a
subtler one. No `PATCH` — a set is replaced, not patched.

`DELETE` hard-deletes and cascades. Nothing anchors to a profile — *provided* W2
writes no durable recommendation rows. If **OQ-SC-11** is ever answered "store
impressions", this becomes a status flip instead.

Two **separate** literal role constants and two **separate** authorizer functions,
both `frozenset({"student"})` — `test_route_roles.py`'s stated rule that two role
sets agreeing today is no reason a widening of one should widen the other, and
`student_events.py`'s defence of splitting read from write so the policy matrix's
`authorizer` column says something true. `load_unit_or_404` first, authorize
against that row's path. `charge_quota` on `PUT` and `DELETE`, not on `GET`.

## 6. Tests

| Level | Asserts |
|---|---|
| unit `test_student_interest_vocabulary.py` | The term set **is** `G3_VOCABULARY.terms` (equality against the imported object, never a re-typed literal); both version constants exist and differ; **structural pin — the module source does not reference `TERM_CONCEPTS`** |
| unit `test_student_profile_models.py` | **Structural pin:** iterate `model_fields` on every request model and fail on any of `{user_id, student_id, subject_id, external_subject, email}`. MM-A01 made mechanical. Plus `extra="forbid"`, off-vocabulary term rejected, empty list rejected, unknown modality rejected |
| integration | `0037` up and down; both composite FKs targeting the named unique constraints; both CASCADEs; three unique constraints by name; both indexes |
| integration | Extend `test_check_constraints.py` — pin the exact `ck_student_profile_modality` expression text, **both directions** |
| contract | `GET` absent → `200` + `"absent"`, not `404`; the twelve terms served; `PUT` idempotent and re-read; off-vocabulary → `422`; `DELETE` then `GET` says absent; coordinator → `403`; no parameter exists by which one student reaches another's row |
| authz | Rows in `test_policy_matrix.py` (**mandatory** — it fails if an authenticated route has no row, and it compares the named authorizer and role constant against the live objects), `test_route_roles.py`, negatives in `test_policy_negatives.py` |

OpenAPI regenerated in the same commit.

## 7. What W1 does not do

- No coordinator, host, or admin read of any individual profile. W4 is the
  aggregate and it is the only other reader.
- **No inference.** A student who registers for three hackathons does not thereby
  acquire a `hackathon` interest. Declared and observed stay separate, because a
  profile that edits itself is one a student cannot correct.
- No free-text field of any kind.
- No ranking. Until W2 lands the profile is stored and unread.
