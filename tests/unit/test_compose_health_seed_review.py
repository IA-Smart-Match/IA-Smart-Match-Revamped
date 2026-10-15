"""compose_health.sh seed-review gate: skipped only when no fixture identity is deployed."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compose_health.sh"

DOCKER_STUB = """#!/usr/bin/env bash
case "$*" in
  *printenv*) printf '%s' "$STUB_PRINCIPALS"; exit 0 ;;
  *"ps -a"*) case "$*" in *"{{.State}}"*) echo exited ;; *) echo 1 ;; esac; exit 0 ;;
esac
exit 1
"""


def _seed_review(tmp_path: Path, principals: str) -> dict:
    stub = tmp_path / "docker"
    stub.write_text(DOCKER_STUB)
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "STUB_PRINCIPALS": principals,
        "SMARTMATCH_CURL_TIMEOUT": "1",
        "SMARTMATCH_RELEASE": "x",
    }
    out = subprocess.run(
        ["bash", str(SCRIPT), "--json"], env=env, capture_output=True, text=True, check=False
    ).stdout
    checks = json.loads(out)["checks"]
    return next(c for c in checks if c["id"] == "seed-review-exited-ok")


@pytest.mark.parametrize("principals", ["", "{}"])
def test_no_fixture_identity_skips_failed_seed_review(tmp_path: Path, principals: str) -> None:
    check = _seed_review(tmp_path, principals)
    assert check["status"] == "pass"
    assert "skipped: no fixture identity deployed" in check["detail"]


def test_fixture_identity_still_requires_seed_review(tmp_path: Path) -> None:
    check = _seed_review(tmp_path, '{"compose-api":"x"}')
    assert check["status"] == "fail"
    assert "exit=1" in check["detail"]
