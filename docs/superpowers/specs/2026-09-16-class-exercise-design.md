# Class exercise design

**Date:** 2026-09-16
**Status:** Approved for implementation, with placeholders that close when Ann's
20-row sample arrives (Fri Sept 18). Every placeholder is marked
`PLACEHOLDER until 9/18`.
**Scope:** `ProductScope.CLASS_EXERCISE` only. The CBA platform track continues
unchanged; this spec touches shared code in exactly two places (§4.1, §4.2).
**Requirements:** [`docs/product/class-exercise-requirements.md`](../../product/class-exercise-requirements.md)
**Architecture:** [ADR-0025](../../architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md)
**Register:** [`class-exercise-open-questions.md`](../../plans/open-questions/class-exercise-open-questions.md)

## 0. Scope, non-goals, not-now

Build every "Required" row of Ann's build table. "If time allows" rows are in
the backlog. "Not now" rows are not built: accounts and roles, the four user
types, invitation-only speaker accounts, real data, Handshake, machine-learning
matching, speaker-to-event matching in this scope, calendars, in-app message
writing, AI writing, email, notifications, reward catalog, mobile.

Naming: the word in code is **exercise**. `tools/scan_forbidden.py` rejects
`demo_mode`, `DEMO_MODE`, `if demo`, and `load_fixture(`. It also rejects
`to_csv`; the download in §8 uses `csv.writer`.

## 1. Product scope and isolation

- `smartmatch_domain/product_scope.py`: add `ProductScope.CLASS_EXERCISE =
  "class_exercise"` and `Capability.CLASS_EXERCISE = "class_exercise"`,
  granted only in that scope. `DEFAULT_PRODUCT_SCOPE` stays `CBA`, so a
  deployment with no scope variable cannot serve exercise routes.
- `services/api/smartmatch_api/main.py`: register
  `exercise_public.router` (`/v1/exercise`, no principal) and
  `exercise_instructor.router` (`/v1/exercise/instructor`, passcode session)
  under `Capability.CLASS_EXERCISE`, in the same declaration table as
  `outreach.public_router` (line 434 today), so the no-principal exception is
  visible where the others are.
- In the `CLASS_EXERCISE` scope the authenticated CBA routers are not
  registered. Tests: exercise routes answer 404 under `ProductScope.CBA`; CBA
  authenticated routes are absent from the app's route table under
  `CLASS_EXERCISE`.
- Boundary rule in the `make imports` check: modules matching
  `services/api/smartmatch_api/routers/exercise_*` and
  `smartmatch_persistence/exercise/*` may import `smartmatch_domain` and may
  not import `smartmatch_authz` or any tenant-scoped repository.

## 2. Data model

All tables prefixed `exercise_`; no `tenant_id`, no `owning_unit_id`, no
foreign key to `user_account`. One Alembic migration at head-plus-one at merge
readiness.

| Table | Columns (key ones) | Notes |
|---|---|---|
| `exercise_dataset` | id, label, source_filename, uploaded_at, row_count, checksum, invite_limit (default 30), license_line (nullable) | One row per uploaded data file. The instructor's "replace the data file" creates a new row and points active workspaces at it after validation. |
| `exercise_profile` | dataset_id, profile_no, display_name, major, class_year, past_event_keys[], stated_interests[] (G3 terms), career_goal, **hidden_true_interests[]** | The 300. `hidden_true_interests` is in `EXERCISE_WITHHELD_FIELDS`. |
| `exercise_event` | dataset_id, event_key, name, topic_tags[] (G3 terms), target_majors[], is_exercise_event, sequence | 12 rows: 10 past, then Northline (round 1) and Harbor (round 2). |
| `exercise_team_workspace` | dataset_id, team_number (1–6), workspace_token_hash, seed, created_at, asking_choice (nullable), refreshed_at (nullable) | One per team per dataset. `seed` drives §11's chance element. |
| `exercise_profile_overlay` | workspace_id, profile_no, added_event_topics[], card_interests[] (nullable), card_career_goal (nullable), non_responding (bool) | Per-team mutations only. A team's view of a profile is base row ⟕ overlay. "Reset team" deletes this team's overlay, runs, and settings. Cheaper than six copies of 300 rows and makes isolation a key, not a discipline. |
| `exercise_saved_setting` | workspace_id, event_key, name, weights (jsonb, four keys), created_at | UNIQUE (workspace_id, event_key, name); at most three per (workspace, event), enforced in the repository and by a partial check. |
| `exercise_result_run` | workspace_id, event_key, round, setting_name, invited_profile_nos[], signed_up_profile_nos[], attended_profile_nos[], email_everyone (jsonb), seats_empty, created_at | UNIQUE (workspace_id, event_key) — the one-run rule as a constraint, not a check in code. |
| `exercise_result_unlock` | dataset_id, event_key, unlocked_at | Instructor action. Absent row = locked. |

**PLACEHOLDER until 9/18:** the mapping from Ann's column names to
`exercise_profile` and `exercise_event`; the `class_year` vocabulary; whether
past events are named by key or by title; whether career goal is a G3 term or
a small fixed list.

## 3. Spreadsheet ingest

- Route: `POST /v1/exercise/instructor/datasets` (multipart, one file),
  synchronous. The instructor needs an answer on the spot, so the job and
  review pipeline behind `routers/imports.py` is not used.
- Format: **CSV** read with `csv.DictReader` (stdlib). If Ann's file is XLSX
  (OQ-CE-05), ask for a CSV export first; `openpyxl` is the fallback and is a
  new runtime dependency.
- Validation, in order, each producing one plain sentence on failure:
  required columns present ("The file is missing the column `major`."); row
  count within 50–1000; every `class_year` in the vocabulary; every interest
  term mapped to G3, with the count of unmapped terms reported and the rows
  kept (ADR-0011: counted, never silently dropped); exactly two rows flagged
  as exercise events; no duplicate `profile_no`.
- On success: dataset row, profile rows, event rows, checksum. Existing
  workspaces keep pointing at their old dataset until the instructor
  re-points them; a re-point resets every team.

**PLACEHOLDER until 9/18:** the required-column list.

**As shipped (PR #184, 2026-09-19) — owner decision pending.** The route is not
multipart. FastAPI's multipart parsing needs `python-multipart`, which this
repository does not have, and adding it is a new runtime dependency plus a
re-lock of hash-pinned requirements for one route. It shipped instead as a raw
`text/csv` request body with `label` and `source_filename` as query parameters;
the ingest core takes bytes either way, so switching back is a change to one
handler's signature. This paragraph records what runs today, **not** a decision
— see PR #184 "owner decision 2", still open.

## 4. Factors, weights, tie-break, reasons

### 4.1 Shared: the `FactorRegistry` parameterisation (ADR-0024 D2)

Executed once, first, exactly as Task 1 of
`docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md`: a frozen
`FactorRegistry` value object threaded through `assert_registry_approved`,
`assert_scoring_ready`, `factor_keys`, `implemented_scoring_keys`,
`resolve_scoring_model`, `normalize_weights`, `scoring._FACTOR_KIND`, and
`explanation._SPECS_BY_KEY`; every existing constant bound to `CBA_REGISTRY`;
`tests/unit/test_factor_registry.py` untouched.

### 4.2 Shared: `smartmatch_domain/student_factors/`

Four pure functions over `(ProfileEvidence, EventEvidence)`, each returning a
`FactorScore` whose value is `unknown` when the profile lacks the input:

| Function | Value | Unknown when |
|---|---|---|
| `same_major` | 1.0 if profile major ∈ event target majors else 0.0 | never (major is always on file) |
| `stated_interest_overlap` | Jaccard of card interests and event topic tags | no card |
| `career_goal_fit` | 1.0 if career goal maps to a topic tag of the event, else 0.0 | no card |
| `past_event_topic_overlap` | Jaccard of the union of attended events' topics and this event's topics | no past events |

Both `STUDENT_REGISTRY` (CBA track) and `EXERCISE_REGISTRY` import these.

### 4.3 Exercise-only: `EXERCISE_REGISTRY` and `score_exercise_pair`

`EXERCISE_REGISTRY` version `0.1.0`, `status = "approved"`, approver "Ann
Wang, class-exercise requirements 2026-09-15", four `FactorSpec`s with Ann's
plain-words labels, all `implemented=True`. `score_exercise_pair(profile,
event, *, weights)` composes them with `normalize_weights(registry=...)`:
an unknown factor contributes nothing and its weight is **not** re-spread
(ADR-0016). A profile with only major on file gets exactly the major
contribution.

**PLACEHOLDER until 9/18:** default weights (OQ-CE-02; placeholder equal).

### 4.4 Exercise-only: `_exercise_ranked`

Key tuple, ascending: `(value is None, -value, -info_rank, -year_rank,
permutation[profile_no])` where `info_rank` is 2 for completed card, 1 for
major plus events, 0 for major only; `year_rank` puts seniors first; and
`permutation` is a fixed shuffle of profile numbers seeded from the dataset
checksum, so it never changes between runs, teams, or processes. The list is
cut at the dataset's `invite_limit`.

### 4.5 Reasons

One sentence per name, from an explanation spec table in the exercise module,
through `assert_one_sentence`. The two sentences Ann specifies verbatim:
"same major; nothing else on file" (major-only profile) and "tied on major;
ordered by year" (a tie resolved by §4.4). Other cases name the factors that
contributed, in Ann's words.

### 4.6 No numeric score on any screen (ADR-0025 D8)

The response carries `rank`, `reason`, `marker`, and the factor keys that
contributed. No number named like a score.

## 5. Invite limit

`exercise_dataset.invite_limit`, default 30. Instructor route
`PATCH /v1/exercise/instructor/datasets/{id}` changes it. The ranked list and
the simulation both read it.

## 6. Saved settings and side by side

- `PUT /v1/exercise/workspaces/{token}/events/{event_key}/settings/{name}`
  stores the four weights; a fourth name is refused with a sentence.
- `GET .../settings/compare?a=&b=` returns both ranked lists and the set of
  profile numbers on both, which the screen highlights.
- Reuse `smartmatch_domain/weight_settings.validate_weight_overrides` for
  range and key checks; the persistence is the new table, not
  `match_weight_setting`.

## 7. "Who is on the list" table

For the current list: counts by major, by class year, and by marker (major
only / major plus events / completed card), each beside the same count over
all 300. Marker derivation follows the three-state pattern in
`smartmatch_domain/match_depth.py`: absent information is `unknown`, an empty
card is not the same as no card. Empty-group notice is backlog.

## 8. Download

`GET .../events/{event_key}/list.csv`: the current ranked list with rank,
name, major, year, marker, and reason. `csv.writer` into a `StringIO`, served
as a `StreamingResponse` with `text/csv`; never written to disk, never via
pandas.

## 9. Results lock and the one-run rule

`POST .../events/{event_key}/results` refuses with a sentence unless
`exercise_result_unlock` has a row for the dataset and event; a second run
hits the UNIQUE constraint and is refused with "This team has already run
results for this event." Instructor: `POST /v1/exercise/instructor/events/{event_key}/unlock`.

## 10. Comparison view

The results response always carries three panels: the team's list (invited,
signed up, attended), "email everyone" (all 300 run through §11 with the same
seed), and, for round two, the team's stored round-one result. `seats_empty =
60 - 8 - attended`, with 60 and 8 as named constants from the case.

## 11. Simulated results rule

Module `smartmatch_domain/exercise/simulation.py`. Its docstring is the
plain-words statement Ann and Dr. Lin receive; the paragraph below is the
draft of that docstring.

> For each invited profile the app decides whether the person signs up, then
> whether they attend. A person is much more likely to sign up when the
> event's topics match what they truly care about and their career goal fits
> the event. Someone who has been to many past events is only a little more
> likely to sign up than someone who has not. Being in the same major as the
> event's audience gives only a small lift on its own. A small amount of chance
> is added, and that chance is fixed for each team, so running the same list
> twice gives the same answer. Most people who sign up attend. The app uses
> each profile's true interests for this, not what the profile has told the
> app, which is why a list built on what the app knows can miss people.

Coefficients as named constants: `TRUE_FIT_LIFT`, `FREQUENT_ATTENDER_LIFT`,
`SAME_MAJOR_LIFT`, `CHANCE_SPREAD`, `ATTEND_GIVEN_SIGNUP`. The chance draw is
`random.Random(workspace.seed ^ hash(event_key))`. A team's reset deletes its
overlay, runs, and settings and regenerates its seed.

**PLACEHOLDER:** the four coefficient values (OQ-CE-03).

**As shipped (PR #186, 2026-09-19) — who may reset.** Owner ruling of
2026-09-19: the per-team reset is an **instructor action only**. The
team-facing route `POST /v1/exercise/workspaces/current/reset` is removed and
answers 404; `POST /v1/exercise/instructor/workspaces/{team_number}/reset`,
behind the instructor passcode session, is the only reset. *What* a reset
deletes is unchanged — the instructor handler runs the same
`ExerciseWorkspaceRepository.reset_team`, so the paragraph above and §2's
overlay note still hold word for word. The ruling removes the destructive
consequence of the shared-per-team number (OQ-CE-08), not the default itself;
that row stays open.

## 12. Asking for more

`POST .../asking-choice` with one of `better_recommendations`,
`small_reward`, `required`. Outcomes as named constants:
`CARD_COMPLETION_SHARE = {better_recommendations: 0.30, small_reward: 0.55,
required: 0.80}` and `REQUIRED_NON_RESPONDING_SHARE = 0.15`. The choice is
stored on the workspace and unlocks §13.

## 13. Profile refresh

`POST .../refresh`, allowed once after the asking choice. For this team's
overlay only: every profile in the round-one attended set gains Northline's
topics under `added_event_topics`; of the invited profiles with no card, a
share chosen by the asking choice (selected by the team seed) gets a card
copied from `hidden_true_interests`; under `required`, a further share is
marked `non_responding` and is excluded from sign-up in §11 for round two;
markers recompute from base ⟕ overlay. Instructor `POST
/v1/exercise/instructor/refresh-all` runs it for every workspace that has
chosen and not yet refreshed.

## 14. Instructor page

One passcode from the environment (`SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE`).
Verify with the PBKDF2-HMAC-SHA256 primitive and mint an opaque session token
with `new_session_token` from `smartmatch_domain/pilot_credentials.py`; do
**not** use `routers/auth.py` login, which resolves a `user_account` and mints
a principal. Session in an httpOnly cookie; rate-limited like
`LOGIN_RATE_LIMIT`. Powers: list workspaces and open any team's saved settings
and results; unlock results per event; set the invite limit; upload a data
file; refresh all; reset one team.

**As shipped (PR #184, 2026-09-19) — the session is signed, not stored; owner
decision pending.** There is no server-side session row: a session table is a
migration and that track shipped none. The cookie is
`"<expiry>.<opaque nonce>.<HMAC>"`, the nonce is `new_session_token`, and the
expiry is covered by the signature, so editing it invalidates rather than
extends. The consequence, stated rather than hidden: **there is no revocation
before expiry** — a minted session stays usable for its twelve hours
(`INSTRUCTOR_SESSION_TTL`), and `logout` clears the browser's copy, not a row.
The two levers that do work are that lifetime and rotating
`SMARTMATCH_EXERCISE_WORKSPACE_SECRET`. The session key and the team workspace
token are labelled derivations of that one secret, so a participant's workspace
cookie can never verify as the instructor's session. Whether to buy real
revocation with a migration is PR #184 "owner decision 1", **still open**.

The cookie is named `exercise_instructor` and scoped
`Path=/v1/exercise/instructor` — narrower than the workspace cookie's
`/v1/exercise` — and it is **`Secure` by default**, turned off only by
`SMARTMATCH_EXERCISE_COOKIE_SECURE=false`. Local development over plain `http`
must set that, or the browser will not store it.

**As shipped (PR #184, 2026-09-19) — the rate limit is a marked placeholder
(OQ-CE-06, still open).** "Rate-limited like `LOGIN_RATE_LIMIT`" could not be
built from this repository's limiter, which needs a principal or
`smartmatch_persistence`, and an exercise router may import neither. What runs
is `exercise_rate_limit.py`, a persistence-free **in-process** fixed-window
limiter marked `PLACEHOLDER OQ-CE-06`: 10 attempts per client per 5 minutes
(copied from `routers/auth.py`'s `LOGIN_RATE_LIMIT`, not invented) plus a
60-attempt global bound. The per-client window is charged **first**, and the
global one is refunded when the passcode turns out to be correct, so one caller
cannot lock the instructor out. It is per process, per process lifetime, fixed
rather than sliding windows, and parses no `X-Forwarded-For`. OQ-CE-06 stays
open.

**As shipped (PR #184 + #186, 2026-09-19) — the routes.** Under
`/v1/exercise/instructor`: `POST /login`, `POST /logout`, `GET /datasets`,
`POST /datasets`, `PATCH /datasets/{dataset_id}`,
`POST /datasets/{dataset_id}/repoint`, `POST /events/{event_key}/unlock`,
`GET /workspaces`, `GET /workspaces/{team_number}`,
`POST /workspaces/{team_number}/reset`, and `POST /refresh-all` — the last a
stub that refuses with a sentence until the results track lands. `unlock`,
team detail and per-team reset resolve against **the data file the teams are
actually on**, not the newest upload: an explicit `dataset_id` is honoured and
refused if no team is in it, a single file in use resolves to it, several in
use is refused with a sentence asking which, and a file with no teams in it is
never targeted.

## 15. Team workspace identity

Entry screen asks for a team number 1–6. The server creates or returns the
workspace for `(active dataset, team_number)` and sets an opaque workspace
token in an httpOnly cookie, mirrored to `localStorage` so a reload restores
it. The server row is the truth; the cookie is a pointer. Two tabs on one
team share the workspace (OQ-CE-08, confirm on 9/18).

**As shipped (PR #186, 2026-09-19) — an existing workspace wins over the newest
data file.** Owner ruling of 2026-09-19. The pair is no longer
`(active dataset, team_number)`: entry used to go straight to the most recently
uploaded file, so the moment the instructor uploaded one, a team that pressed
reload was handed a second, empty workspace and its work appeared to be gone —
while §3 says in as many words that uploading moves nobody. Only an instructor
re-point moves a team. `ExerciseWorkspaceRepository.entry_dataset_for` states
the rule in one place, in three branches:

1. **The team already has a workspace** — on any data file — and that
   workspace's file is the answer.
2. **A legacy team with workspaces on more than one file** (nothing creates
   that state any more) lands on its **most recently created workspace row**,
   `created_at DESC` then `id DESC` so a tie has one answer for every reader.
3. **A brand-new team** joins the file the other teams are on, by that same
   ordering. With no workspace anywhere the method answers `None` and the route
   falls back to `active_dataset`, so the first team of a lesson joins the
   newest upload.

The decision and the insert happen under **one transaction-level advisory
lock** — `lock_workspace_membership` on `WORKSPACE_MEMBERSHIP_LOCK_KEY`, taken
as `entry_dataset_for`'s first statement and held continuously to the commit —
so a re-point committing mid-entry cannot leave a team holding two workspaces.
A re-entered or moved workspace keeps its id and therefore its cookie. The
consequence for §16: an entry screen showing `dataset_label` may legitimately
show an older file's label after an upload. That is the ruling, not a bug.

## 16. Frontend

New pages under `apps/web/legacy-frontend/src/app/pages/exercise/`: entry,
event picker, matching (weights in plain words, ranked list, marker, list
table, saved settings, compare), asking-for-more, results, and the instructor
page. Reuse `AIMatching.tsx` `CandidateCard` and `FactorRow`,
`components/MetricCard.tsx`, and `components/provenance/SyntheticDataMarker.tsx`
on every screen. Type sizes chosen for a projector at classroom distance. No
CBA portal shell, no `SessionGate`.

## 17. Hosting

A stable address on the pilot VM path (`docker-compose.vm.yml`,
`docs/operations/vm-deploy.md`) running with `SMARTMATCH_PRODUCT_SCOPE=
class_exercise`. Budget: under 5 seconds to first interactive in Chrome on a
classroom machine, measured on the deployed address, not locally.

## 18. Acceptance

Justin's checklist is Ann's build table, one line per "Required" cell, plus
the four things she calls easy to forget: two teams at once do not see each
other's lists; reload keeps saved settings; the lock blocks a second run; a
reset clears one team and nothing else. Automated: `make check`, `make scan`,
`make imports`, `make openapi-check`, `tests/golden/exercise/`.
