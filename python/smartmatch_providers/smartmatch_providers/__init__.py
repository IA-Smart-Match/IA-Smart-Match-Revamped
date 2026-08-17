"""Provider interfaces and adapters.

Architecture v1.1 §3.1 provider plane. Every external dependency sits behind an
explicit interface so the domain never imports a vendor SDK and so the classroom
edition can be proven incapable of reaching a live provider.

Only fixture adapters are implemented in the Foundation scaffold. Live adapters
are skeletons that refuse to initialize without separately approved
configuration — see :mod:`smartmatch_providers.registry`.
"""

from smartmatch_providers.base import (
    Edition,
    EmailProvider,
    ProviderConfigurationError,
    RouteMatrixProvider,
    SendRequest,
    SendResult,
    TravelEstimate,
)
from smartmatch_providers.fixtures import FixtureEmailProvider, FixtureRouteMatrixProvider
from smartmatch_providers.registry import (
    build_email_provider,
    build_route_matrix_provider,
    build_task_queue,
)
from smartmatch_providers.tasks import (
    FixtureTaskQueue,
    TaskAlreadyExists,
    TaskHandle,
    TaskQueue,
    TaskQueueError,
    TaskRequest,
)

__all__ = [
    "Edition",
    "EmailProvider",
    "FixtureEmailProvider",
    "FixtureRouteMatrixProvider",
    "FixtureTaskQueue",
    "ProviderConfigurationError",
    "RouteMatrixProvider",
    "SendRequest",
    "SendResult",
    "TaskAlreadyExists",
    "TaskHandle",
    "TaskQueue",
    "TaskQueueError",
    "TaskRequest",
    "TravelEstimate",
    "build_email_provider",
    "build_route_matrix_provider",
    "build_task_queue",
]

__version__ = "0.1.0"
