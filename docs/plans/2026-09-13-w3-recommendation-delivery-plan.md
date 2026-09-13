# W3 — delivering recommendations to students (2026-09-13)

**Status:** planning only. No source file changes, no route, no migration, no
provider authorized.

**Parent:** [`2026-09-13-student-recommendation-program-plan.md`](2026-09-13-student-recommendation-program-plan.md).
**Blocked on:** **OQ-SC-03** — on what basis may SmartMatch contact a student.
**Migration:** `0038`. One revision.
**Independent of W1 and W2** — a digest of a student's own registered agenda is
useful before any ranking exists.

---

## 1. What exists, and what does not

Grepping `python/`, `services/` and `apps/` for `push`, `reminder`, `fcm`, `apns`
and `web push` returns **nothing**. There is no notification subsystem.

What does exist, and what W3 rides on:

| | |
|---|---|
| A durable job state machine + transactional outbox + dispatcher, parking a job at attempt exhaustion | `smartmatch_worker.dispatcher`, `outbox_record` |
| An external clock calling `POST /operations/dispatch` | `smartmatch_worker.local_scheduler` (dev appliance; Cloud Scheduler in a real deployment, still open F5) |
| A working precedent for a consent-gated durable send | `outreach.send`, its `outreach_draft` / `outreach_send` / `delivery_event` chain, and the gate **re-checked by the worker at delivery time, not only at compose time** |

So a reminder is **a scheduled durable command dispatched through the path that
already exists** — not a new subsystem. That framing is the main content of this
plan.

## 2. Why the existing consent model cannot be reused

`contact_channel` is scoped to `professional_id`. Its columns are
`professional_id, channel_kind, address, contact_state, consent_source,
consent_recorded_at, consent_evidence` — there is no column for a student and no
nullable path to one.

That is not an oversight to patch. `smartmatch_domain.consent` governs contacting
**an external professional whose address the research pipeline found**, where the
question is whether this system may write to a stranger at all. A student has an
institutional relationship with the chapter and an account in the system; the
question is different, the evidence is different, and the revocation surface is
different. Widening `consent` to cover both would make one module answer two
questions, which is the argument ADR-0014 already makes for `disclosure_consent`
not being `smartmatch_domain.consent` widened.

**`student_contact_preference` is its own table**, migration `0038`.

## 3. The table

| Column | Notes |
|---|---|
| `id`, `tenant_id`, `owning_unit_id` | ADR-0004 composite discipline |
| `subject_id` | Composite FK to `user_account`, `ON DELETE RESTRICT` |
| `channel_kind` | CHECK-pinned. **`in_app` and `email` only** at this revision. `push` is not in the vocabulary — see §5 |
| `state` | `opted_in` / `opted_out`. **Revocation is a state, not a delete** — ADR-0014's rule, and the reason the `disclosure_consent` design says so explicitly |
| `decided_at`, `decided_by_user_id` | Who chose, and when |
| `created_at`, `updated_at`, `version` | |

`uq_student_contact_preference_channel` on `(tenant_id, subject_id, channel_kind)`.

**The default is off.** A row's absence means no consent, and the digest command
skips a student with no `opted_in` row rather than treating absence as
permission. A wrong refusal costs a student a reminder; a wrong send is a message
to a student who never asked for one, and no later decision undoes it.

## 4. The digest

**One command, `student-digest.send`**, submitted per unit on a schedule, not per
student on a timer.

- The worker handler assembles each opted-in student's digest **at delivery time**
  and re-checks the preference then — the `outreach.send` discipline, because a
  student who opted out on Tuesday must not receive Wednesday's queued message.
- Content is the student's own agenda plus, once W2 exists, their top few
  recommendations. Nothing about another student.
- Two triggers only, and both are about something the student already did or could
  do: *you are registered and it is tomorrow*, and *this week's events are up*.
  No re-engagement nagging, no "you haven't opened the app".
- Copy is authored by a human and versioned. Every shipped outreach template is
  `content_status: synthetic` and refused in live mode; a student template starts
  the same way and is promoted only when someone has reviewed the words —
  **OQ-SC-10** names the owner.

## 5. Channel order: in-app, then email, then push

**In-app first.** A read surface on the student portal — no consent question
beyond being signed in, no credential, no deliverability, no store. It is also the
only channel that can ship while mobile is deferred.

**Email second.** Reuses the existing send machinery, and inherits its three
institutional blockers (OQ-001 From domain, OQ-002 provider tenant, OQ-003
reviewed copy). Those are not W3's to close, and W3 must not pretend otherwise:
until they are, an email digest is composable and undeliverable, which the job
should report as such rather than as a success.

**Push last, and not in this revision.** Push needs a client (deferred), a
credential, a store presence, and a platform decision — and the session deferred
mobile. `channel_kind`'s CHECK constraint therefore does not contain `push`. A
later migration adds it *with* the decision that authorizes it, so the vocabulary
never lists a channel nothing can deliver.

**The domain is channel-agnostic.** `smartmatch_domain/student_digest.py` decides
*what* a digest says and *whether* a student may receive one; a channel adapter
decides how it travels. Push then becomes an adapter and a CHECK value, not a
rewrite.

## 6. Tests

| Level | Asserts |
|---|---|
| unit | Absence of a preference row is refusal, not permission; `opted_out` refuses; the digest for a student with an empty agenda is *not generated* rather than generated empty |
| unit | The digest module imports no provider, no channel client, and no environment variable — the import-purity contract |
| contract | The preference routes are `{student}`-only; identity from the token; a body naming another `subject_id` changes nothing |
| integration | The command runs to a terminal state; a preference flipped between compose and delivery is honoured at delivery |
| structural | A pin asserting `push` is absent from the channel vocabulary and that no module names FCM, APNS or a web-push key — the shape `test_calendar_invite_wiring.py` uses to keep Google Calendar out, so acquiring the capability fails a test citing the gate rather than passing as a diff |

## 7. What W3 does not do

- No live send. The email path stays behind OQ-001/002/003.
- No push, no service worker, no device token.
- No message to anyone who is not the account holder.
- No engagement-driven cadence. Two triggers, both anchored to a real event.
