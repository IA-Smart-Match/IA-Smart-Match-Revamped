"""Planned identity routes.

Future identity endpoints will be rooted at ``/v1/me`` (for example,
``GET /v1/me``).  This module deliberately declares no handlers yet, so it
does not advertise or implement that future contract.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/me", tags=["identity"])
