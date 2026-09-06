"""SmartMatch API service.

Architecture v1.1 §3.1 compute plane. The HTTP boundary: token verification,
authorization policy invocation, request validation, idempotency, the error
envelope, and OpenAPI generation.

Explicitly **not** here: provider execution. No browser request handler calls
email, Calendar, crawl, or AI providers directly. Every consequential action is
persisted as a command and dispatched through the outbox (v1.1 §1.6).
"""

__version__ = "0.1.0"
