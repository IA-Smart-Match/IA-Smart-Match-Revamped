"""Pure SmartMatch domain logic.

Architecture v1.1 Part 1 layer (1): deterministic domain rules for eligibility,
scoring, load, assignment, consent, approval, and job lifecycle.

This package depends on no framework, storage layer, provider SDK, filesystem,
network, or environment variable. Its one third-party dependency is
``ortools``, a deterministic in-process constraint solver used by
:mod:`smartmatch_domain.optimizer`; it performs no IO and reaches nothing
outside the process. That is enforced in CI by the import-linter contracts in
the root ``pyproject.toml``, not by convention.

Everything here is deterministic and unit-testable without infrastructure.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
