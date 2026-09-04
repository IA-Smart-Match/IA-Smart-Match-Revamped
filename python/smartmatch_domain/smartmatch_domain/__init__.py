"""Pure SmartMatch domain logic.

Architecture v1.1 Part 1 layer (1): deterministic domain rules for eligibility,
scoring, load, assignment, consent, approval, and job lifecycle.

This package depends on no framework, storage layer, provider SDK, filesystem,
network, or environment variable. Its one third-party dependency is
``ortools``, a deterministic in-process constraint solver used by
:mod:`smartmatch_domain.optimizer`; it performs no IO and reaches nothing
outside the process. The import-linter contracts in the root ``pyproject.toml``
enforce the purity of this project's *own* imports in CI; ``ortools`` is an
audited exception whose in-process behavior rests on that review, not on the
linter, which squashes external packages into opaque leaf nodes it does not
see inside.

Everything here is deterministic and unit-testable without infrastructure.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
