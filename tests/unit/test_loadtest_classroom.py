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


def test_assets_reuse_the_devices_keepalive_connections() -> None:
    """Oct 27 public-50: one new socket per asset; a device must reuse its <= 6."""
    import asyncio
    import gzip
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    body, peers = gzip.compress(b"x" * 300_000), set()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive

        def do_GET(self) -> None:
            peers.add(self.client_address)
            self.send_response(200 if self.path != "/missing.js" else 404)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    paths = [f"/assets/{i}.js" for i in range(40)] + ["/missing.js"]
    s = cl.Student(0, 1, f"http://127.0.0.1:{srv.server_port}", random.Random(0), paths)

    async def go() -> None:
        await s._assets()
        await s._assets()  # a reload on the same tab
        await s.client.aclose()

    cl.RECORDS.clear()
    try:
        asyncio.run(go())
    finally:
        srv.shutdown()
    statuses = [r["status"] for r in cl.RECORDS if r["name"] == "asset"]
    assert statuses.count(200) == 80 and statuses.count(404) == 2
    assert 1 <= len(peers) <= 6, f"{len(peers)} connections for 82 fetches"


def test_same_run_check_ignores_devices_that_could_not_read() -> None:
    """A device whose GET timed out is not a second run (Oct 21 'distinct_created_at=2')."""
    one_run_some_unread = ["2026-10-22T06:06:49Z", None, "2026-10-22T06:06:49Z", None]
    assert cl.run_stamps(one_run_some_unread) == (1, 2)
    two_runs = ["a", "b", None]
    assert cl.run_stamps(two_runs) == (2, 1)


def test_transport_errors_keep_the_message_not_only_the_class() -> None:
    """Oct 27: 238 OSError / 195 ConnectError / 40 reset, and no way to tell why."""
    import asyncio

    import httpx

    def refuse(req: httpx.Request) -> httpx.Response:
        try:
            raise ConnectionRefusedError(111, "Connection refused")
        except OSError as exc:
            raise httpx.ConnectError("All connection attempts failed", request=req) from exc

    async def go() -> None:
        async with httpx.AsyncClient(
            base_url="https://x.test", transport=httpx.MockTransport(refuse)
        ) as c:
            await cl.call(c, "a", "GET", "/a")
            await cl.fetch_asset(c, "/assets/x.js")

    cl.RECORDS.clear()
    asyncio.run(go())
    for r in cl.RECORDS:
        assert (r["status"], r["code"]) == (0, "ConnectError")
        assert "Connection refused" in r["detail"] and "ConnectionRefusedError" in r["detail"]
