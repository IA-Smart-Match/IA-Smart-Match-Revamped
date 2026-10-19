"""Self-check for the classroom load script's math and verdicts (no server needed)."""

import random

from tools.loadtest import classroom_load as cl


def _rec(name: str, method: str, latency: float, status: int = 200, ok: bool = True) -> dict:
    return {
        "burst": "B3 run Northline",
        "name": name,
        "method": method,
        "t": 0.0,
        "latency": latency,
        "status": status,
        "code": "",
        "ok": ok,
    }


def test_pct_is_nearest_rank() -> None:
    assert cl.pct([], 95) == 0.0
    assert cl.pct([3.0, 1.0, 2.0], 50) == 2.0
    assert cl.pct([float(i) for i in range(1, 101)], 95) == 95.0


def test_lognormal_arrivals_match_plan_shape() -> None:
    rng = random.Random(1)
    xs = sorted(cl.lognormal_delay(rng) for _ in range(20_000))
    assert 5.5 < xs[len(xs) // 2] < 6.5  # median 6 s
    assert 18.5 < xs[int(len(xs) * 0.9)] < 21.5  # p90 20 s


def test_verdicts_flag_slow_writes_and_b3_errors() -> None:
    records = [_rec("GET list", "GET", 0.1)] * 50 + [_rec("POST results", "POST", 3.0)] * 50
    records.append(_rec("POST results", "POST", 0.2, status=500, ok=False))
    by_target = {v["target"]: v["ok"] for v in cl.verdicts(records)}
    assert by_target["API read p95 <= 1.5 s"]
    assert not by_target["API write p95 <= 2 s"]
    assert not by_target["no 5xx / transport errors"]
    assert not by_target["0 unexpected errors in B3"]
