"""Deny-by-default SmartMatch authorization policy.

Architecture v1.1 §2.1. Pure policy functions over an explicit principal and
resource — no framework, no database, no request object. The API calls into this
package; the package never calls back out. That makes every authorization rule
unit-testable without a server, which is what the negative-test suite in
``tests/authz/`` relies on.
"""

from smartmatch_authz.policy import (
    AccessDecision,
    AuthorizationError,
    Effect,
    Membership,
    OrgPath,
    Principal,
    Resource,
    ResourceGrant,
    assert_allowed,
    evaluate,
)

__all__ = [
    "AccessDecision",
    "AuthorizationError",
    "Effect",
    "Membership",
    "OrgPath",
    "Principal",
    "Resource",
    "ResourceGrant",
    "assert_allowed",
    "evaluate",
]

__version__ = "0.1.0"
