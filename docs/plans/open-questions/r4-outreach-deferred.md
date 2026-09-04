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

**Safe default, implemented.** This slice stores sends, not threads. The list
endpoint returns drafts and their sends. No table claims to hold a reply, and
the UI does not draw one — a thread list rendered from send records alone would
be the legacy's fiction with a database behind it.
