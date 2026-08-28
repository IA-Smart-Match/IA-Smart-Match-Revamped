"""Planned unit-scoped event routes.

Future event endpoints will be rooted at ``/v1/units`` and will include their
unit identifier in the remaining path (for example,
``GET /v1/units/{unit_id}/events``).  This module deliberately declares no
handlers yet, so it does not advertise or implement that future contract.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/units", tags=["events"])
