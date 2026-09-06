"""SmartMatch worker service.

Architecture v1.1 §3.1: a **private** Cloud Run service with internal ingress,
receiving Cloud Tasks deliveries authenticated by OIDC service identity. Not a
Cloud Run Job — Jobs are reserved for genuine batch work.

The worker is where consequential work actually happens, and where the five send
gates are rechecked at execution time (v1.1 §1.8). A check performed in the API
request path is not sufficient: minutes may pass between a command being
accepted and the task being delivered, and consent, suppression, budget, and
approval can all change in that window.
"""

__version__ = "0.1.0"
