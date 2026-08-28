"""Planned unit-scoped engagement routes.

Future engagement endpoints will be rooted at ``/v1/units`` and will include
their unit identifier in the remaining path (for example,
``GET /v1/units/{unit_id}/engagement``).  This module deliberately declares no
handlers yet, so it does not advertise or implement that future contract.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/units", tags=["engagement"])
