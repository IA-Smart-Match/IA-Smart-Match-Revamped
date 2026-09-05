# R4 outreach — open questions carried by the G4 slice

**Date:** 2026-09-04 · **Slice:** R4 outreach infrastructure (G4)

Every item here is a decision a human has to make that engineering could not
make for them. None of them stopped the slice: each carries a **safe default**
that is implemented, and the default is chosen so that being wrong about it
degrades into *not sending* rather than into *sending something nobody
approved*.

That asymmetry is the whole policy. A deferral that fails toward inaction costs
a coordinator a message; a deferral that fails toward action costs a real
person an email they never agreed to receive, which is the harm the consent
lifecycle exists to prevent and which no later decision can undo.

Nothing here is a placeholder that *reports success*. Where a decision is
missing, the code refuses, and it says which decision it is waiting on.

---

## OQ-001 — the institutional From address (blocks D4)

**Question.** Which mailbox does outreach come from, who owns it, and which
domain carries its SPF, DKIM, and DMARC records?

**Why engineering cannot answer it.** A From address is an institutional
identity claim. Choosing one is choosing who the recipient will reply to, who
answers a complaint, and whose domain reputation absorbs a bounce rate.

**Safe default, implemented.** `SMARTMATCH_OUTREACH_FROM_ADDRESS` is unset by
default and the fixture path uses `noreply@example.invalid` — an RFC 2606
reserved domain that cannot resolve, so a misconfigured deployment that somehow
reached a real transport would fail to send rather than send as somebody. Live
mode requires the variable to be set explicitly; there is no fallback that
guesses a domain from the tenant.

## OQ-002 — the live email provider tenant (blocks F5)

**Question.** Which Resend (or equivalent) account, on which verified domain,
under whose contract?

**Why engineering cannot answer it.** It is a procurement and data-processing
decision, and the acceptable-use terms it comes with are the terms
`consent.py` was written against.

**Safe default, implemented.** `build_email_provider` returns
`FixtureEmailProvider` unless a credential is present *and* the edition permits
a live client. The live adapter is a named refusal, not a silent no-op: asking
for one without the decision raises `ProviderConfigurationError` naming this
question. The classroom edition can never construct one at all.

## OQ-003 — template legal copy

**Question.** What must every outbound message say — postal address, the
institution's identity, the wording of the unsubscribe line, any jurisdiction
specific notice?

**Why engineering cannot answer it.** It is legal copy for a named
institution.

**Safe default, implemented.** The shipped templates carry
`content_status = "synthetic"`. A template so marked composes and stores
normally, and the send handler refuses it in live mode — so the pilot exercises
the entire path end to end against the fixture provider without anyone being
able to put unreviewed copy in front of a real recipient.

## OQ-004 — production contact records

**Question.** Which real contacts, on what consent evidence, get loaded into
`contact_channel`?

**Why engineering cannot answer it.** Every row asserts that a specific person
agreed to be contacted. That assertion is made by whoever recorded the consent,
not by a migration.

**Safe default, implemented.** The migration creates the table and seeds
nothing. Synthetic contacts use `.invalid` addresses. `consent_source` is `NOT
NULL` with no default and the approved-source vocabulary is a CHECK constraint,
so there is no way to store a contact whose permission nobody can name.

### Update — the operational half is now implemented (branch `feat/outreach-contact-admin-api`)

The question above is unchanged and still open: *which real contacts get
loaded* is a decision for whoever holds the consent, and nothing here answers
it. What has changed is that there is now a way for that person to say so.

`routers/outreach_contacts.py` lets a coordinator register a contact channel,
correct the evidence behind it, suppress it, and drive it through the
`consent.py` lifecycle — and migration `0022` records every one of those moves
in `contact_channel_transition`, an append-only trail carrying the actor, the
source, the evidence and the reason. Before this, `contact_channel` was a table
only a migration or a psql session could write, which is why OQ-004's safe
default read as "seeds nothing" and stopped there.

Three properties are worth naming, because each is a place the easy
implementation would have been the wrong one:

* **Registration cannot produce a send-eligible contact.** A contact may be
  created `discovered` or `consented` only. Reaching `active_candidate` is a
  separate transition by a named actor, so the trail always contains the moment
  somebody activated it. The database would have accepted the one-step row.
* **The trail includes the registration.** `from_state IS NULL` for the first
  entry, rather than a history that begins at the first edit and cannot say
  where the contact started.
* **No backfill.** Contacts registered before `0022` have no trail. A
  synthesised "arrived at its current state at some point, by nobody" row would
  be a fabricated audit entry, which is worse than an honestly empty history.

**Still deferred, and deliberately.**

| Deferred | Why it is not in this slice |
| --- | --- |
| Bulk CSV import of production contacts | An import asserts consent for hundreds of people in one action, by a person who is not looking at any of them. It needs a ratified column contract for consent evidence, a review step, and a decision about what a partially-valid file does — none of which exists. The per-contact route is the honest unit until it does. |
| Self-service opt-in forms | A public form is an unauthenticated write that creates the strongest kind of consent record (`self_service`). It needs anti-abuse, a verified round trip to prove the address holder submitted it, and retention rules for submissions that never confirm. |
| Reinstating a suppressed address | See OQ-009. |

Both deferrals fail toward *not sending*: without them a coordinator records
fewer contacts by hand, rather than the platform recording more contacts than
anyone agreed to.

## OQ-005 — the unsubscribe token secret and its rotation

**Question.** Where does `SMARTMATCH_UNSUBSCRIBE_SECRET` live, and what is the
rotation procedure?

**Why engineering cannot answer it.** It is a secrets-management decision tied
to the deployment that does not exist yet.

**Safe default, implemented.** Only the token's SHA-256 **hash** is stored, so
the table is not itself a set of working unsubscribe links. The secret is read
once at process start; when it is absent, the signed POST refuses with a 503
naming this question rather than accepting an unverifiable token. An
unverifiable unsubscribe that reports success would be the worst possible
fake success in this whole feature.

## OQ-006 — RFC 8058 one-click unsubscribe

**Question.** Do we enable `List-Unsubscribe-Post: List-Unsubscribe=One-Click`,
which lets a mail provider unsubscribe a recipient with no confirmation step?

**Why engineering cannot answer it.** It is a deliverability trade: mailbox
providers reward it, and it means an accidental click is irreversible from the
recipient's side.

**Safe default, implemented.** Both headers are populated on every
`SendRequest` — the provider interface already requires them — and the one-click
POST endpoint exists and is unauthenticated by design, exactly as RFC 8058
requires. What is deferred is only whether the *header* advertises one-click,
which is a live-mode configuration question, not a code question.

**Carried with it: rate limiting for that endpoint.** `POST /v1/unsubscribe` is
not application-rate-limited, and the reason is structural rather than an
oversight. `charge_quota` keys its counter by tenant and user id, and
`rate_limit_counter.tenant_id` carries a foreign key to `tenant` — so limiting an
unauthenticated route means inventing a tenant that does not exist, which the
database refuses (and did refuse, in an earlier draft that tried a nil-UUID
stand-in principal). Creating a synthetic tenant to satisfy the constraint would
have been worse: a row that exists only to make a limiter work is a row every
tenant-scoped query then has to know to ignore.

The exposure is bounded rather than unbounded — the route writes at most one row
per distinct valid token, nothing at all for an invalid one, and
`uq_suppression_record_address` makes a repeat a no-op — but it is not zero, and
an edge rate limit in front of the service is what should close it. Decide it
alongside the one-click question, since both are about traffic this endpoint
receives from mailbox providers rather than from our own UI.

## OQ-007 — does an email send reserve spend (ADR-0015)?

**Question.** Is transactional email a metered cost that must hold a spend
reservation before it is incurred?

**Why engineering cannot answer it.** ADR-0015 A1 ratifies a synthetic
reservation implementation for *paid extraction*. Whether email falls under the
same ceiling is a budget decision.

**Safe default, implemented.** No spend reservation is taken. The fixture
provider costs nothing, so reserving against it would be recording a spend that
did not happen — the fabricated-measurement shape ADR-0011 forbids. The live
branch is where a reservation would belong, and it is refused for OQ-002
anyway; the plan's card L5 records this so the decision is made when the live
adapter is, not silently inherited.

## OQ-008 — coordinator thread and conversation model

**Question.** Is outreach a *thread* (a conversation with replies) or a
*sequence of independent sends*? The legacy UI drew threads; nothing ever
stored one.

**Why engineering cannot answer it.** Inbound mail handling is a separate
capability with its own consent and retention questions.

**Safe default, implemented.** This slice stores sends, not threads. There are
two listings — `GET .../outreach/drafts` and `GET .../outreach/sends` — and
each returns exactly what is stored. No table claims to hold a reply, and the
UI does not draw one: a thread list rendered from send records alone would be
the legacy's fiction with a database behind it.

The sends listing was added on `feat/outreach-contact-admin-api`; before it, a
single send could be read by id and a unit's sends could not be listed at all,
which made "what have we attempted" a question the surface could not answer.

## OQ-009 — who may reinstate a suppressed address

**Question.** A suppression says a person asked us to stop. Who may lift one,
on what evidence, and is it ever correct to lift one at all?

**Why engineering cannot answer it.** It is a consent decision about a named
person, and the failure mode is that somebody who asked to be left alone starts
receiving mail again. A coordinator correcting an accidental suppression and a
coordinator overriding a real unsubscribe are the same API call; only the
evidence distinguishes them, and no artifact says what that evidence is.

**Safe default, implemented.** `PATCH .../contacts/{id}` accepts
`suppressed: true` and **refuses** `suppressed: false` with a `400` naming this
question. It is a refusal rather than a silent no-op deliberately: accepting the
field and doing nothing would be a fake success on the one field where a fake
success reaches a person who asked us to stop.

**Carried with it: the actor behind a coordinator suppression.**
`suppression_record` carries `source` (which can be `coordinator`) and
`suppressed_at`, but no actor column — so "a coordinator suppressed this" is
recorded and "which coordinator" is not. That is a gap rather than a decision:
adding the column is a migration, and it should land with the answer to the
reinstatement question rather than ahead of it, since the two are the same
audit story. Nothing today depends on the missing attribution, and the
suppression itself is authoritative either way.
