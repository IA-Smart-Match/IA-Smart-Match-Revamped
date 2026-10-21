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


def test_one_winner_per_team() -> None:
    assert cl.one_winner([201] + [409] * 16, 201)
    assert not cl.one_winner([201, 201] + [409] * 15, 201)  # two runs: correctness bug
    assert not cl.one_winner([409] * 17, 201)  # nobody won
    assert not cl.one_winner([201, 500] + [409] * 15, 201)  # an error hides in the rest


def test_refresh_once_counts_students_and_instructor() -> None:
    assert cl.once_per_team(1, False)
    assert cl.once_per_team(0, True)
    assert not cl.once_per_team(1, True)
    assert not cl.once_per_team(0, False)


def _secure_cookie_sent(base: str) -> bool:
    import asyncio

    import httpx

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/set":
            return httpx.Response(200, headers={"set-cookie": "w=1; Path=/; Secure; HttpOnly"})
        return httpx.Response(200, json={"cookie": req.headers.get("cookie", "")})

    async def go() -> bool:
        c = cl.make_client(base, transport=httpx.MockTransport(handler))
        async with c:
            await c.get("/set")
            return "w=1" in (await c.get("/x")).json()["cookie"]

    return asyncio.run(go())


def test_secure_cookie_sent_to_loopback_http_only() -> None:
    assert _secure_cookie_sent("http://127.0.0.1:15174")
    assert _secure_cookie_sent("http://localhost:15174")
    assert not _secure_cookie_sent("http://example.test")


def _guard(base: str, opt_in: str | None) -> str:
    try:
        cl.check_host(base, opt_in)
    except SystemExit as e:
        return str(e.code)
    finally:
        cl.PUBLIC["on"] = False
    raise AssertionError("expected refusal")


PUB = "exercise.smartmatch.cloud"


def test_guard_refuses_without_flag_mismatch_http_and_plated() -> None:
    assert "refusing" in _guard(f"https://{PUB}", None)
    assert "refusing" in _guard(f"https://{PUB}", "other.example")
    assert "refusing" in _guard(f"http://{PUB}", PUB)
    assert "refusing" in _guard("https://exercise.plated.blog", "exercise.plated.blog")
    assert "refusing" in _guard("https://evil.example", "evil.example")


def test_guard_accepts_flag_and_warns(capsys) -> None:
    cl.check_host(f"https://{PUB}", PUB)
    assert cl.PUBLIC["on"]
    cl.PUBLIC["on"] = False
    assert "resets teams 1-6" in capsys.readouterr().out


def test_cloudflare_blocks_counted_apart_from_app_errors() -> None:
    import asyncio

    import httpx

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/c":
            return httpx.Response(403, html="<html>Just a moment</html>")
        return httpx.Response(401, json={"error": {"code": "exercise_workspace_required"}})

    async def go() -> None:
        cl.RECORDS.clear()
        cl.PUBLIC["on"] = True
        async with httpx.AsyncClient(
            base_url="https://x.test", transport=httpx.MockTransport(handler)
        ) as c:
            await cl.call(c, "a", "GET", "/c")
            await cl.call(c, "b", "GET", "/app")

    try:
        asyncio.run(go())
    finally:
        cl.PUBLIC["on"] = False
    assert [r["code"] for r in cl.RECORDS] == ["cloudflare_blocked", "exercise_workspace_required"]
    rows = {r["name"]: r for r in cl.summarize(cl.RECORDS)}
    assert rows["a"]["unexpected"] == 0 and rows["a"]["cloudflare_blocked"] == 1
    assert rows["b"]["unexpected"] == 1


def test_rebuilt_client_sends_copied_cookie_first_on_loopback() -> None:
    import asyncio

    import httpx

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/set":
            return httpx.Response(200, headers={"set-cookie": "w=1; Path=/; Secure; HttpOnly"})
        return httpx.Response(200, json={"cookie": req.headers.get("cookie", "")})

    async def go() -> str:
        old = cl.make_client("http://127.0.0.1:1", transport=httpx.MockTransport(handler))
        await old.get("/set")
        jar = httpx.Cookies()
        for c in old.cookies.jar:
            c.secure = True  # worst case: the copy still carries Secure
            jar.jar.set_cookie(c)
        new = cl.make_client(
            "http://127.0.0.1:1", cookies=jar, transport=httpx.MockTransport(handler)
        )
        return (await new.get("/x")).json()["cookie"]

    assert "w=1" in asyncio.run(go())


def test_team_codes_come_from_the_instructor_api(monkeypatch) -> None:
    """Issue #413: the script reads each team's code after a reset; no bypass."""
    import asyncio

    import httpx

    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/exercise/instructor/team-codes"
        teams = [{"team_number": n, "code": f"000{n}"} for n in range(1, 7)]
        return httpx.Response(200, json={"teams": teams})

    monkeypatch.setattr(cl, "CODES", {})
    ins = cl.Instructor("http://127.0.0.1:9")
    ins.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:9", transport=httpx.MockTransport(answer)
    )
    asyncio.run(ins.fetch_codes())
    assert {n: f"000{n}" for n in range(1, 7)} == cl.CODES
