"""The exercise routes name 422 by its current Starlette constant.

Starlette deprecated ``HTTP_422_UNPROCESSABLE_ENTITY`` in favour of
``HTTP_422_UNPROCESSABLE_CONTENT``. The old name still resolves, but every
access emits a ``DeprecationWarning``, so a class run filled the API log with
one line per refused body (M1 full-class run, wave 2). The value is 422 either
way; only the name changes.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from fastapi import status

_API = Path(__file__).resolve().parents[2] / "services/api/smartmatch_api"
#: The exercise modules, plus ``errors.py``: its request-validation handler is
#: what answers every exercise body pydantic refuses, so it logged the same
#: warning on the same class run.
_EXERCISE_MODULES: tuple[Path, ...] = (
    *sorted(_API.glob("exercise_*.py")),
    *sorted((_API / "routers").glob("exercise_*.py")),
    _API / "errors.py",
)


def test_the_current_name_is_422_and_raises_no_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert status.HTTP_422_UNPROCESSABLE_CONTENT == 422


def test_no_exercise_module_uses_the_deprecated_name() -> None:
    assert _EXERCISE_MODULES, "the glob found no exercise modules"
    offenders = [
        path.name
        for path in _EXERCISE_MODULES
        if "HTTP_422_UNPROCESSABLE_ENTITY" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
