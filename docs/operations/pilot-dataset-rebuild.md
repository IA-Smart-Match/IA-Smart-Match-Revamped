# Rebuilding the synthetic pilot dataset

**Audience:** whoever has to make the pilot appliance show numbers, on a
machine where it currently shows empty screens.

**Posture:** this is the *repair and rebuild* companion to
[`local-dev-walkthrough.md`](local-dev-walkthrough.md). That guide brings the
appliance up for the first time and walks its steps by hand, one shell at a
time. This one is for the state that guide's step 6 leaves you in when it goes
wrong, and for getting back to a known dataset in one command afterwards.
Where the two disagree on a port or a variable, the walkthrough is the
tiebreaker for the by-hand path and this file is the tiebreaker for
`scripts/reset_pilot_dataset.sh`.

**What this file has been executed against.** Unlike the walkthrough, the
sequence below was run end to end on a WSL machine with native PostgreSQL, and
the row counts in [§6](#6-what-a-good-run-looks-like) are that run's actual
output rather than an estimate. The one number that is *not* from a run is
`reward_item`, and §7 explains why it cannot be.

---

## 1. The failure this exists for

An appliance was found in this state:

```
professional_unit_relationship      250
event                                60
job                                   0  EMPTY
import_batch                          0  EMPTY
review_item                           0  EMPTY
speaker_profile                       0  EMPTY
pipeline_record                     180
attendance_record                   258
point_ledger_entry                  182
speaker_request_classification        0  EMPTY
match_run                             0  EMPTY
cba_invitation_batch                  0  EMPTY
cba_invitation                        0  EMPTY
student_speaker_feedback              0  EMPTY
```

Every full table is written by `tools/generate_pilot_dataset.py`'s **Phase B**,
which goes through repositories. Every empty one is written by **Phase A**,
which goes through the HTTP API. Nothing in the stack complained, because the
generator's report describes what the *tool* believed it did.

The consequence is worse than it looks on a table. `speaker_profile` **is** the
§13 roster, so with it empty the coordinator roster, every match run, every
invitation and every speaker-feedback surface are empty too — not *unknown*,
which would be ADR-0011 working correctly, but genuinely absent. From a screen
those look identical.

### Why Phase A produced nothing

Phase A needs **three** processes, and the walkthrough's step 5 starts two:

| Process | What it does | How to run it on a host |
|---|---|---|
| API | Accepts `POST /v1/units/{id}/imports`, answers `202` | `make run-api` (port 8000) |
| Worker | Executes the command the queue delivers | `make run-worker` (port 8001) |
| **Dispatch driver** | Moves a queued job to the worker | **no Makefile target exists** |

Under `docker compose` the third is the `scheduler` sidecar, which POSTs the
worker's own `/operations/dispatch` every two seconds. It cannot be reused
here: its target is the hard-coded constant
`smartmatch_worker.local_scheduler.DISPATCH_URL` — `http://worker:8080/...`, a
compose service name — and that module's docstring is explicit that a sidecar
whose destination could be repointed by an environment variable would be a more
capable forwarder than the job needs. So a host-run appliance has nothing
driving dispatch, every import sits `queued` forever, and
`wait_for_review_items` times out.

The worker also needs its loopback task queue switched on
(`SMARTMATCH_LOCAL_TASK_QUEUE_ENABLED`, `SMARTMATCH_LOCAL_TASK_TARGET_URL`) and
its two *different* dev tokens; the config validator refuses to boot if the
task-scoped and dispatch-scoped credentials are the same string.

`scripts/reset_pilot_dataset.sh` runs all three and drives dispatch itself.

---

## 2. The one command

```bash
scripts/reset_pilot_dataset.sh
```

From a git worktree, which has no virtualenv of its own:

```bash
VENV=/path/to/main/checkout/.venv scripts/reset_pilot_dataset.sh
```

**It drops and recreates the `smartmatch` database.** That destroys *every*
tenant in it, not only `pilot`. On a machine where more than one piece of work
shares one local database — several agent worktrees, say — check with somebody
before running it, or point `DATABASE` at a database of your own.

### What it does, in order

1. **Preflight** — interpreter, `psql`, a live PostgreSQL.
2. **Computes the dev-principal map** *before starting anything*. `Settings`
   reads `SMARTMATCH_DEV_PRINCIPALS` once at process start, so a token added
   after the API is up authenticates as nobody and answers `401`. The map is
   the coordinator's token plus one per feedback student, derived from
   `pilot_dataset_plan.feedback_dev_principals()`.
3. **Drop, recreate,** and `make migrate`.
4. **`make seed-pilot`**, **`make seed-pilot-principals`**,
   **`make seed-pilot-logins`** — the existing targets, reused rather than
   restated. Step 1 dropped `pilot_credential` along with everything else, so
   the logins step is **not optional**: it sources the four owner-supplied
   `SMARTMATCH_PILOT_*_EMAIL`/`_PASSWORD` pairs from `SMARTMATCH_ENV_FILE`
   (defaulting to this repository's `.env`, falling back to the main checkout's
   when run from a worktree, which has none of its own) into a subshell that
   lives for exactly that one command, and then **gates on
   `pilot_credential` being non-zero**. A full database nobody can sign in to
   is a failed rebuild. No password is defaulted and no value is ever printed.
5. **Starts API, worker and the dispatch driver**, waits for both health
   endpoints, and sends one dispatch pass eagerly so a misconfigured dispatch
   path fails *here*, with a message about dispatch, rather than ninety seconds
   later as "the queued import never reached review".
6. **Runs the generator** with `--seed 42`.
7. **Gates on the database.** `job = 0` fails the run loudly. A silent zero is
   exactly how the appliance reached §1's state.
8. **Rewards** — only if the operator supplied a worksheet row (§7).
9. **`make verify-pilot-dataset`** — counts every table again and exits
   non-zero on any empty one.

Knobs are environment variables with stated defaults; the script's header lists
them. `KEEP_RUNNING=1` leaves the API and worker up to click through.

---

## 3. Verifying without rebuilding

```bash
make verify-pilot-dataset
```

Read-only. It counts every table a demo reads from for the pilot tenant, prints
them aligned so a *block* of zeros in the middle is visible, names the writer
that should have filled each, and exits non-zero on any empty one.

Run it before assuming a screen is broken, and after any manual seeding.

It counts **rows**, never measurements. An empty `review_item` table is a
broken import path and reporting it as zero is correct. A speaker whose topic
relevance is unknown, or a student whose balance is unknown, is not counted here
at all and must never render as `0` — that is ADR-0011 rule 1, and a deliberate
fraction of every generated run is in exactly that state on purpose.

---

## 4. What one run now produces that it did not before

Three changes to the generator, all of which the rebuild exercises.

**Several speaker requests, not one.** The invitations page composes against a
*recorded shortlist*, so one run meant one reachable shortlist and one batch.
The generator now files `SPEAKER_REQUEST_COUNT` requests, each naming a
different in-list engagement category and a different slice of the roster's
ranked §7/§8 codes, submits a run per request, and composes a batch per
completed run.

**An invitation batch per run**, through the real
`POST /v1/units/{id}/speaker-invitations/batches` with the `Idempotency-Key`
that route requires — because on this surface a retry without one is a second
batch, and a second batch is a second message to everybody in the first.

**Phase D: contact channels**, recorded and then separately activated through
`routers/cba_contact_channels.py`, so a batch has somebody it can actually
address. Sequenced before composition, because a batch resolves each
recipient's channel as it composes.

**Phase C: student speaker feedback**, through the student's own route. Each
rating is a `POST` made with that student's own bearer token, because
`routers/student_speaker_feedback.py` takes `student_id` from the verified
principal and there is no request field that could carry another. A generator
writing those rows through a repository would exercise none of the checks the
surface exists for — not attendance, not the roster, not the edit window.

---

## 5. The feedback arithmetic, and why it is not arbitrary

`smartmatch_domain.student_speaker_feedback` publishes a per-speaker aggregate
only at `MIN_RESPONSES_FOR_AGGREGATE` (3) or above, and publishes the *unit*
aggregate only when the pool clears the same threshold **and** its residual
does:

```
residual = n_unit − Σ n_s over speakers whose own aggregate published
publish iff n_unit ≥ 3 and (residual == 0 or residual ≥ 3)
```

The residual rule closes a subtraction: one speaker published at `n=3` beside a
unit at `n=5` leaks two other ratings as a mean over two students.

`FEEDBACK_SPEAKER_RESPONSE_SHAPE = (5, 4, 2, 1)` is chosen to show **both**
outcomes at once:

| Speaker | Ratings | Own aggregate |
|---|---:|---|
| 1 | 5 | published |
| 2 | 4 | published |
| 3 | 2 | **suppressed** |
| 4 | 1 | **suppressed** |
| **unit** | **12** | **published**, residual `12 − 9 = 3` |

Change any entry and re-check. `(5, 4, 2)` leaves a residual of 2 and silently
suppresses the unit aggregate — the demo then shows nothing where it meant to
show something, and looks broken rather than careful.
`tests/unit/test_pilot_dataset_plan.py` asserts this against the shipped
`aggregate_unit_feedback`, so the plan's restatement of the rule cannot drift.

### The feedback window is the thing that will bite you

`feedback_anchor` derives the anchor from the event's own ADR-0010 triple — the
stated end or else the start for an exact event, and **midnight at the end of
the day, in UTC** for a date-only one — and the window is seven days wide. The
generated calendar spreads six months *backwards* from the fixed literal
`CALENDAR_ANCHOR = 2026-09-28`, so most of it is already closed. The generator
selects only events whose window is genuinely `OPEN` and **raises loudly** when
none is, naming the anchor as the cause. Once `CALENDAR_ANCHOR` is more than a
week in the past, Phase C cannot write a row until that literal moves. Do not
widen the window instead — it is a ratified decision.

Unresolved events are writable (no anchor, so `permits_change` is true) and are
deliberately **not** used: that is the case OQ-CBA-052 is open on, and a
generator writing rows into an open question would be answering it in code.

---

## 6. What a good run looks like

The actual output of `make verify-pilot-dataset` after
`scripts/reset_pilot_dataset.sh` on the machine this was written on. See §7 for
`reward_item`.

```
verify-pilot-dataset: tenant 9a47555f-… (slug 'pilot'), unit 27691431-…
  professional_unit_relationship      250         generator Phase B
  event                                63         generator Phase B
  job                                   7         generator Phase A (HTTP import)
  import_batch                          4         generator Phase A (HTTP import)
  review_item                         192         generator Phase A (worker -> review)
  speaker_profile                     100         generator Phase A (review accept)
  pipeline_record                     280         generator Phase B
  attendance_record                   290         generator Phase B
  point_ledger_entry                  187         generator Phase B
  speaker_request_classification       12         generator Phase A (request)
  match_run                             3         generator Phase A (match runs)
  cba_invitation_batch                  3         generator Phase A (invitations)
  cba_invitation                        9         generator Phase A (invitations)
  student_speaker_feedback             12         generator Phase C
  reward_item                           0  EMPTY  make seed-pilot-rewards (owner-supplied)
```

Compare that against §1: every table that was empty there is populated here
except `reward_item`, which §7 explains. `event` is 63 rather than 60 because
the fan-out import adds two and each Speaker Request is itself an `event` row.

Alongside it, `pilot_credential` holds **4** rows — one login per role
(`coordinator`, `student`, `admin`, `volunteer`). Step 5 gates on that count
being non-zero, because a full database nobody can sign in to is a failed
rebuild.

`contact_channel` holds **75**, every one `active_candidate` with source
`institutional_relationship` — recorded and then separately activated by
Phase D. The other 25 roster members hold no channel at all, deliberately, and
that is what produces the invitation split:

```
cba_invitation   pending                          6
                 skipped / no_contact_channel     3
```

Six composed and three skipped across three batches (2/1, 3/0, 1/2) — a real
mix rather than uniformly one outcome. Nothing is dispatched.

Student feedback, from the same run: 8 students, 12 ratings posted, 4
deliberately withheld, 2 per-speaker aggregates published, 2 suppressed, unit
residual 3, unit aggregate publishes.

Each of the three match runs, on the fixture path:

```
  request 1 (Hackathon)      scoring mode cba-virtual-1
    candidates named        100
    scored candidates         6
    unscorable candidates    56   (reported, never zeroed)
    excluded candidates      38   (never evaluated)
    portfolio status     optimal
    shortlist                 3 speakers
    invitations composed      0
    recipients skipped        3
    dispatched            False   (G4-gated; composed, not sent)
```

Requests 2 and 3 are identical in these counts and differ in their targets and
in which speakers they shortlist — scorability is decided by §9 and §19, which
the targets do not move, so the same six candidates are scorable in all three
and the ranking among them differs.

The generator's own report is longer and is the thing to read when a number
looks wrong: it prints, per speaker request, the scored / unscorable / excluded
counts and the exclusion reasons, and it prints every fraction it left
deliberately unmeasured.

---

## 7. What the run deliberately leaves unmeasured

This is the section to read before concluding something is broken. Every item
below is a *true* state that a run reproduces on purpose. None of them may be
"fixed" by writing a value.

### Fractions the plan withholds by design

Named in `tools/pilot_dataset_plan.py` beside each other, so the whole set is
one screen:

| Constant | Share | What has no evidence |
|---|---:|---|
| `UNKNOWN_TOPIC_SHARE` | 0.12 | professionals with no expertise record at all — `topics is None`, which is not `()` |
| `UNKNOWN_LOCATION_SHARE` | 0.10 | professionals with no coordinates, so travel burden is unknown |
| `UNCLASSIFIED_INDUSTRY_SHARE` | 0.15 | exports stating no customer §7 sector |
| `UNCLASSIFIED_ROLE_SHARE` | 0.08 | exports stating no §8 role category |
| `UNRESOLVED_EVENT_SHARE` | 0.08 | events with no resolvable date (ADR-0010) |
| `QUARANTINED_TAG_SHARE` | 0.15 | events carrying an off-vocabulary tag |
| `OUT_OF_LIST_CATEGORY_SHARE` | 0.15 | events under a category the counting rule excludes |
| `FEEDBACK_WITHHELD_SHARE` | 0.25 | students who attended, could rate a speaker, and did not |
| `CONTACT_CHANNEL_SHARE` | 0.75 *covered* | the remaining quarter of the roster holds no channel, so cannot be invited |

Two more are arithmetic rather than constants. Roughly one roster member in
five is left **unreviewed** on §19 (`reviews_classification`), so the run
reports somebody as `industry_classification_awaiting_review` rather than
ranking them last — "nobody has checked this record" and "we checked and they
scored badly" call for different actions and must stay distinguishable. And
about one attending student in twelve is left **uncredited**, which is the
narrow case `routers/rewards.py::_fold_balance_for` answers with an *unknown*
balance rather than a zero.

### The rewards catalog is empty, and this is not a bug

`reward_item` holds nothing after a plain run. Every value — display name,
points cost, fulfilment cost, budget owner, funded — is owner-supplied;
`docs/pilot-data/rewards-catalog-worksheet.md` says engineering "must not
invent owners, funding, or point costs", and **that worksheet's item table has
no completed row in it**. So the rebuild seeds none and says so, and no
redemption is openable.

To fill it, complete a worksheet row and pass it through:

```bash
SEED_PILOT_REWARD_ARGS="--name '<row>' --points-cost <n> --fulfilment-cost <n> \
  --budget-owner-id <uuid> --funded" scripts/reset_pilot_dataset.sh
```

The attendance-derived balances are real regardless. `verify-pilot-dataset`
will keep reporting `reward_item` as empty, and should — an operator who *did*
supply a row and got nothing needs that failure.

### A quarter of the roster can never be invited, on purpose

A batch invites somebody only if they hold a `contact_channel` that is
`active_candidate`, carries an approved consent source, and is unsuppressed.
Nothing in the import path writes such a row — `pipeline_provisioning` says so
itself — so Phase D records them, through the consent surface's own acts: a
create at `consented` naming an approved source and its evidence, then a
**separate** transition to `active_candidate`. A create may never assert that
state; a row born sendable makes "who activated this person" unanswerable.

`CONTACT_CHANNEL_SHARE` covers three quarters of the roster and leaves the rest
with nothing, so `no_contact_channel` stays a visible skip. A roster where
everybody is reachable asserts a consent coverage no real programme has.

**The consent evidence invents nothing.** It says in words that the address is
generated fixture data on the reserved `.invalid` domain and that no permission
is asserted and no form submission is cited. A fabricated submission id would
be manufacturing precisely the evidence gate G4 requires, and an auditor
following the trail would find a citation to nothing.

### Nothing is dispatched

Composing writes the batch and its outcomes as rows a Connector can read back.
*Sending* is a separate operation behind gate G4 — consent-origin policy,
supervised recipient policy, deliverability review — and
`smartmatch_providers.registry` refuses to construct a transport until it
opens. `dispatched: False` is recorded as a fact on every batch rather than
omitted, so a reader cannot assume messages went out.

### Most match-run candidates are unscorable

The generator calls the fixture semantic-topic provider, which holds no
recordings, so a candidate carrying expertise text scores `unknown` on customer
§9, ADR-0011 rule 1 makes their composite `None`, and they are reported
**unscorable** rather than shortlisted. The shortlist is drawn from the minority
who filed no expertise text at all. ADR-0017 approved an offline in-process
embedding model that removes the cause, reachable only with
`SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=true` on the **API** process:

```bash
SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=true scripts/reset_pilot_dataset.sh
```

Running it once each way is a real before/after — the per-request block of the
generator's report prints `scoring_mode` and the scored/unscorable/excluded
counts both times. Stripping topic text from the seed to make the demo look
fuller is the workaround this repository will not take: it was one of the two
alternatives ADR-0017 rejected.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `something is already listening on port 8000` | a `make run-api` from another session holds the port | stop it, or `API_PORT=8010 WORKER_PORT=8011 scripts/reset_pilot_dataset.sh`. Do **not** ignore it: this script's uvicorn would fail to bind, the health check would pass against the *other* process, and the run would proceed with no dev principals and no task queue — which is how §1's half-written dataset happens |
| `seeding produced ZERO logins` | no env file, or a pair with only one half filled in | `SMARTMATCH_ENV_FILE=/path/to/.env`; a missing pair creates nothing and no password is defaulted |
| `Phase A produced ZERO job rows` | dispatch never ran | read `.pilot-reset-logs/dispatch.log` and `worker.log`; a `401`/`403` means the scheduler token disagrees with the worker's, a `501` means the worker has no task queue configured |
| `POST /operations/dispatch was refused` | same, caught early | as above |
| generator `401` on a feedback student | the token is not in the API's `SMARTMATCH_DEV_PRINCIPALS` | the API reads it once at startup; restart it — the rebuild script sets it before booting |
| generator `403 student_feedback_not_eligible` | the student has no attendance record at that event | `write_feedback_students` records it; check the event ids agree |
| `no generated event still has an open feedback window` | `CALENDAR_ANCHOR` has aged more than seven days into the past | move that literal in `tools/pilot_dataset_plan.py`; do **not** widen `FEEDBACK_EDIT_WINDOW_DAYS` |
| match run answers `422` | fewer candidates could be scored than the shortlist needs | expected on the fixture path — see §7's last item; the run records it per variant and carries on |
| match run answers `503 registry_not_ready` | this appliance's factor registry is not approved or not fully implemented | a deployment fact, recorded per variant, not a dataset defect |
| `make` cannot find the interpreter in a worktree | worktrees have no `.venv` | `VENV=/path/to/main/checkout/.venv` |

---

## 9. References

- `scripts/reset_pilot_dataset.sh` — the rebuild, with its reasoning in the header
- `tools/verify_pilot_dataset.py` — the read-only counter
- `tools/generate_pilot_dataset.py` — the generator; its module docstring is the
  argument for the Phase A / Phase B / Phase C split
- `tools/pilot_dataset_plan.py` — every deliberately-unmeasured fraction
- `tests/unit/test_pilot_dataset_plan.py` — the pure assertions over that plan
- [`local-dev-walkthrough.md`](local-dev-walkthrough.md) — the by-hand path
- [`hosted-synthetic-pilot-guide.md`](hosted-synthetic-pilot-guide.md) — the
  `docker compose` path, where the `scheduler` sidecar drives dispatch for you
- `docs/pilot-data/rewards-catalog-worksheet.md` — the owner-supplied catalog
