"""Workspace token arithmetic for the class exercise (design spec §15).

OQ-CE-08 (closed 2026-09-25). The whole mechanism below exists to answer one
question — "do two browser tabs that enter the same team number share one
workspace, or is each tab its own workspace?" — and the answer is the one it
was built to: **shared per team number** (Danny, owner, recording Ann's
answers to the team's question list of 2026-09-22).

Why the token is *derived* rather than random
=============================================

The obvious design is the one :func:`smartmatch_domain.pilot_credentials.new_session_token`
implements: mint random bytes, store only their SHA-256, hand the raw bytes to
the caller. It is the right design for a login, and it cannot express
OQ-CE-08's default.

``exercise_team_workspace`` holds exactly one ``workspace_token_hash`` per
workspace, and the raw token is never stored — that is the point of storing a
hash. So when the second tab on team 3 enters "3", the server has no way to
hand back the token the first tab is holding: it can only mint a new one and
rotate the stored hash, which logs the first tab out. A team of four people on
four laptops would spend the exercise knocking each other off their own saved
runs. Shipping that would be shipping the *opposite* of the register's default
while appearing to implement it.

So the token is not minted, it is **derived**:

    token       = HMAC-SHA256(server secret, workspace id)
    stored hash = SHA-256(token)

Every entry of the same team number resolves to the same workspace row, derives
the same token from that row's id, and therefore matches the hash already
stored. No rotation, no second row, no tab logged out — and still no raw token
at rest, because the column keeps the SHA-256 of the derived value exactly as
it would keep the SHA-256 of a random one.

What the secret is, and what it is not
======================================

The secret is a deployment fact (``SMARTMATCH_EXERCISE_WORKSPACE_SECRET``),
required only in ``ProductScope.CLASS_EXERCISE`` and read only there. It is
what stops a workspace id — a value that will appear in nobody's URL but is
still only 128 bits of *guessable-in-principle* structure — from being a
workspace token on its own. Without it, anyone who learned a workspace id would
hold that team's session.

It is not a credential for a person: there is no login here, nothing about a
class participant is authenticated, and the token proves only "this browser was
told team 4's pointer". It is never logged, never returned in a response, and
never reaches a repository that does not need it.

Rotating the secret invalidates every live cookie at once and creates no
orphans that matter: a team re-enters its number and gets the same workspace
back, because the workspace is identified by ``(dataset, team number)`` in the
table and only *addressed* by the token. That is the property design spec §15
asks for — "the server row is the truth; the cookie is a pointer" — and it is
why rotating a secret here is an inconvenience rather than data loss.

Nothing in this module reads the environment, touches a database, or knows what
a request is. It is arithmetic over bytes and a random draw, for
:mod:`smartmatch_persistence.exercise.workspace_repository` and the API's
exercise dependency to compose.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Final

__all__ = [
    "MINIMUM_WORKSPACE_SECRET_LENGTH",
    "SEED_BITS",
    "derive_workspace_token",
    "hash_workspace_token",
    "new_workspace_seed",
    "tokens_match",
]

#: The shortest ``SMARTMATCH_EXERCISE_WORKSPACE_SECRET`` a deployment may boot
#: with. Thirty-two characters is what ``secrets.token_urlsafe(24)`` produces
#: and is the length the operations note tells an operator to generate; a
#: shorter value is refused at startup rather than accepted and quietly
#: weakened, because the failure it causes — a guessable HMAC key — is silent.
MINIMUM_WORKSPACE_SECRET_LENGTH: Final[int] = 32

#: Bits in a workspace seed. Sixty-three rather than sixty-four because the
#: column is ``BIGINT``, which is *signed*: a 64-bit draw overflows it for half
#: of all values, and the failure arrives as an insert error in a classroom.
SEED_BITS: Final[int] = 63


def derive_workspace_token(*, secret: str, workspace_id: uuid.UUID) -> str:
    """The opaque cookie value addressing ``workspace_id``.

    Deterministic by design (OQ-CE-08, above): the same workspace under the
    same secret always yields the same token, which is what lets a second tab
    on a team share the first tab's workspace without the server ever having
    kept the raw token.

    Args:
        secret: The deployment's workspace secret. Never logged, never
            returned to a caller, never stored.
        workspace_id: The ``exercise_team_workspace`` row's own id.

    Returns:
        A hex string. Opaque: it carries no claim, no team number and no
        dataset — it is a lookup key for a server-side row, and there is
        nothing in it to read or to forge.
    """
    return hmac.new(
        secret.encode("utf-8"),
        str(workspace_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_workspace_token(token: str) -> str:
    """What ``exercise_team_workspace.workspace_token_hash`` stores.

    SHA-256 and not a password KDF, for :mod:`smartmatch_domain.pilot_credentials`'s
    reason for session tokens: the input is full-entropy machine-generated
    bytes, not a human-chosen secret, so there is no dictionary for an attacker
    to run and a slow KDF would buy nothing but latency on every request.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(presented: str, expected: str) -> bool:
    """Compare two tokens without leaking where they first differ.

    Lookup is by hash in the repository, so this is not on the hot path; it is
    here so that a caller that *does* hold both values — the test that proves
    the derivation is stable, and any later code that re-derives rather than
    looks up — has no reason to write ``==``.
    """
    return hmac.compare_digest(presented, expected)


def new_workspace_seed() -> int:
    """A fresh value for ``exercise_team_workspace.seed`` (design spec §11).

    Not a credential. The seed fixes the chance element of the simulated
    results so that running the same list twice gives the same answer, and a
    participant who learned another team's seed could predict that team's
    simulated sign-ups and nothing else — there is no real person and no
    account behind any of it. It is drawn from :mod:`secrets` anyway, because
    the module that has the right-sized draw is the one to use and "this does
    not need to be unguessable" is a sentence that ages badly.
    """
    return secrets.randbits(SEED_BITS)
