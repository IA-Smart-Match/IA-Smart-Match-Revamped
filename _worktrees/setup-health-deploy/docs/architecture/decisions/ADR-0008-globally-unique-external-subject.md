# ADR-0008 — Globally unique `external_subject` as the identity lookup's licence

**Status:** Accepted
**Date:** 19 August 2026
**Contract:** Architecture v1.1 §1.11, §2.2

## Context

`PrincipalRepository.load_by_subject`
(`python/smartmatch_persistence/smartmatch_persistence/principals.py`) is the
seam where a verified token becomes an authorization principal. It filters
`user_account` on `external_subject` alone and calls `.one_or_none()`. Filtering
on the subject alone is not an oversight — it is the point. The token proves who
the caller is; it does not, and must not, say which tenant they belong to. If it
did, a caller could present a token that simply *asserted* a tenant, which is the
legacy `POST /auth/mock-login` pattern this codebase archives as **MM-A01**:
caller-selected identity wearing whatever credential is available that day. The
tenant has to be something the lookup *resolves*, not something the caller
supplies alongside the subject, or the resolution is theater around a value the
caller already chose.

`.one_or_none()` is only as sound as the constraint standing behind it. Before
migration `0003`, the only uniqueness on `user_account` touching this column was
`uq_user_account_tenant_subject` — `(tenant_id, external_subject)` — which
promises one account per subject *per tenant* and says nothing about two. A
person with accounts in two tenants under one identity-provider subject is
exactly the case a multi-tenant deployment is likely to produce, and for that
person the query matched two rows. `.one_or_none()` does not return the first of
them; it raises `MultipleResultsFound`. Nothing in
`services/api/smartmatch_api/dependencies.py` catches that exception —
`get_current_principal` calls `load_by_subject` directly and lets whatever it
raises propagate — and nothing in `services/api/smartmatch_api/errors.py`
registers a handler for it either; `EXCEPTION_HANDLERS` names seven specific
exception types and `MultipleResultsFound` is not one of them. It fell through
to FastAPI's default handling, which is a 500. So the failure was not a wrong
answer or a denial an operator could triage from an audit log entry — it was an
unhandled server error, on every authenticated request, for exactly the people a
multi-tenant deployment was most likely to create.

## Decision

`external_subject` is unique across the whole `user_account` table, not merely
within a tenant. Migration `0003`
(`db/migrations/versions/0003_global_external_subject.py`) adds
`uq_user_account_external_subject` — a bare `UNIQUE (external_subject)`, with no
`tenant_id` in the key — and `schema.py` mirrors it. With that constraint in
place, at most one row can match any subject, so `.one_or_none()` in
`load_by_subject` is correct because the schema now guarantees its precondition,
not because the query happens to have gotten away with assuming it. The method's
docstring says this explicitly: the constraint "is the whole licence for the
`.one_or_none()` below."

Nothing about the query changed. That is the shape of the fix worth noticing:
the defect was never in `load_by_subject`'s logic, and no amount of rewriting
that method — adding an `ORDER BY` and a `LIMIT 1`, wrapping the call in a
`try/except` — would have been the right fix, because every such rewrite treats
the ambiguity as something to be survived at the call site rather than something
that should not exist in the data. The schema was wrong; the schema was
corrected.

### Duplicates are refused, not repaired

`upgrade()` does not go straight to `ALTER TABLE ... ADD CONSTRAINT`. It first
runs a query grouping `user_account` by `external_subject` for any group larger
than one, and if it finds any, it raises `RuntimeError` naming the duplicated
subjects — up to twenty of them, with the true total reported even when it is
larger — and refuses to proceed. It does not deduplicate, does not pick a
survivor, and does not merge.

That refusal is deliberate rather than merely cautious. Two accounts sharing a
subject is a question about the world outside the database, and the migration
has no way to answer it. Either the identity provider issued one subject to one
person who ended up enrolled twice — in which case fixing it means merging the
two accounts, and someone has to decide by hand which memberships and resource
grants survive the merge — or the same subject string was issued to two
different people, which is an incident at the identity provider, not a database
problem at all. A migration that silently kept one row and discarded the other
would be destroying authorization state to make a constraint apply, and doing it
unattended, at deploy time, in whichever direction the row ordering happened to
land. Letting PostgreSQL's own `IntegrityError` do the refusal instead was
considered and rejected for a narrower reason: it names one conflicting key, and
an operator reading it cannot tell whether that is the whole problem or the
first of hundreds. The migration's own check reports the total before it reports
the detail, precisely so the fix can be sized — a phone call to one person, or a
project — before anyone starts making it.

## Consequences

**Good.** `load_by_subject`'s `.one_or_none()` is now correct by construction.
Nothing downstream of it — `get_current_principal`, every route depending on
`CurrentPrincipal`, the audit trail built on `resolved.user_id` and
`resolved.tenant_id` — has to account for a request that authenticates
correctly and then fails to resolve to exactly one principal.
`tests/integration/test_principal_identity.py` asserts the constraint behaviorally rather
than by name: it inserts the same subject into two tenants and requires
PostgreSQL to refuse the second insert with `uq_user_account_external_subject`
named in the error, which is the shape of the original defect run as a test
rather than described as one.

**Cost, stated plainly.** This forecloses one human holding accounts in two
tenants under a single identity-provider subject. That is a real product
constraint, not an implementation detail to be discovered later by whoever
first needs it: a volunteer coordinator active in two partner organizations, or
a person who moves from one tenant's roster to another's without their old
account being closed first, cannot be represented as one subject with two
accounts under this schema. Today that is the right trade, because
`smartmatch_providers.identity` names exactly one identity provider — Google
Identity Platform — and `smartmatch_providers.registry.build_token_verifier`
does not yet implement even that; the only `TokenVerifier` that exists is
`FixtureTokenVerifier`, for tests and local development. With one issuer, a
subject string means one real-world identity, full stop, and global uniqueness
just says that plainly. A second issuer would reopen this decision rather than
merely extend it: two identity providers can each mint their own subject
strings from their own namespace, and nothing stops both from independently
issuing the literal string `"117362..."` to two unrelated people. Global
uniqueness on the bare column would then be enforcing a coincidence, not an
identity, and the fix would have to include the issuer in what makes a subject
unique — which this migration does not do, because there is only one issuer to
distinguish it from today.

`uq_user_account_tenant_subject`, the constraint this one strictly implies, is
kept rather than dropped. Removing it is contract-phase work under v1.1 §4.2's
expand/migrate/contract discipline — every migration in this repository is
expand-phase only — and it is tracked as backlog item **F12**, not done here.

## Alternatives considered

**Make the caller supply a tenant alongside the subject, and scope the lookup to
it.** This is the most obvious-looking fix, because it would also make
`.one_or_none()` sound: filter on `(tenant_id, external_subject)`, which is
already unique, and the ambiguity disappears. It was rejected because of where
the tenant would have to come from. `load_by_subject`'s caller is
`get_current_principal`, and the only thing it has is a verified token; the
token, by design (`python/smartmatch_providers/smartmatch_providers/identity.py`),
carries a subject and optionally an email — nothing else. A tenant filter
supplied by the caller is a tenant asserted by the caller, and asserting your own
tenant is indistinguishable in shape from asserting your own role, which is
`POST /auth/mock-login` again, just with the assertion moved from a request body
to a header the caller still controls. `principals.py`'s module docstring names
the general pattern directly: "A token that carried its own tenant or roles
would be caller-selected identity in a better disguise — the exact pattern
archived as MM-A01." The tenant is not an input this lookup could accept without
also accepting the thing MM-A01 exists to keep out. It has to be output.

**Keep the query as it is and change only how it picks a row** — `.first()`
against some ordering, or an explicit `LIMIT 1`. This does not fix anything; it
hides the ambiguity instead of resolving it. Whichever row sorts first —
oldest `id`, most recent `created_at`, whatever tiebreaker gets chosen — becomes
the account that request resolves to, silently and by an accident of row order
that nobody decided on purpose. That choice does not stay contained: it becomes
the tenant a request is authorized against, the memberships and resource grants
a decision is made under, and the actor id an audit record names. An
authorization decision and an audit trail built on an arbitrary tiebreak are
worse than the 500 they would replace, because the 500 at least fails loudly. A
person holding two tenant memberships under one subject deserves a designed
answer — which tenant a given session should resolve to, and how they would
choose — and this ADR does not supply one; it makes that ambiguity impossible to
create in the first place, and leaves choosing among two rows as a problem the
schema no longer allows to arise.

**Catch `MultipleResultsFound` in `get_current_principal` and turn it into the
same 401 an unknown subject already produces.** Narrower than either
alternative above, and it would have stopped the 500s without touching the
schema at all. Set aside because it treats a data-integrity violation as a
routine authentication outcome: a subject held by two tenants is not "no
account," which is what a 401 says, and collapsing the two would mean an
administrator investigating a spike in login failures could no longer tell a
stranger with no account from an identity the system has actually
double-provisioned. The constraint prevents the double-provisioning from
existing at all, which is a stronger guarantee than translating its symptom
into a better-looking error.
