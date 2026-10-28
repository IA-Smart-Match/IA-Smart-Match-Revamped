"""Classroom load test for the class exercise: 6 teams x ~17 devices (Plan A, local).

Replays the run-of-show bursts B1-B6 from the load-test plan against a running
exercise stack (frontend server that proxies /v1, or api-exercise directly) and
checks correctness after every burst, not just latency.

    python tools/loadtest/classroom_load.py --base http://127.0.0.1:4174 \
        --students 100 --out runs/v1-built --api-pid 1234 --pg-dsn postgresql://...

The instructor passcode is read from LOADTEST_INSTRUCTOR_PASSCODE and never printed.
Stdlib + httpx (already a repo dependency) + optional psycopg for DB sampling.
See docs/operations/exercise-load-test.md.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# httpcore runs `import sniffio` on every request. Where sniffio is not installed and
# site-packages sits on /mnt/c (WSL 9P), each miss walks sys.path with ~40 stat calls
# (~4-15 ms per request, 4 misses each): the generator, not the API, capped at ~25 req/s
# (Oct 19 L4 finding). A None entry makes the miss free and changes nothing else.
try:
    import sniffio  # noqa: F401
except ImportError:
    sys.modules["sniffio"] = None  # type: ignore[assignment]

import httpx

TEAMS = range(1, 7)
PUBLIC_HOST, REFUSED_HOST = "exercise.smartmatch.cloud", "exercise.plated.blog"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}  # Plan B/C need the owner's OK first
ROUND1, ROUND2 = "E11", "E12"  # Northline, Harbor in Ann's fixture file
INVITE_LIMIT = 60  # #419: 60 personalized emails in both rounds
ASKED_WITHOUT_CARD = 230  # Ann's 300: students with no card, all asked by the refresh (#423)
FACTORS = ("same_major", "stated_interest_overlap", "career_goal_fit", "past_event_topic_overlap")
HDR = {"X-Exercise-Request": "1"}
WS = "/v1/exercise/workspaces/current"
INS = "/v1/exercise/instructor"
IMPATIENT_S = 8.0  # a page with no first row after 8 s gets reloaded (plan 1.1)
MAX_RELOADS = 3
# Plan 4.2 targets (seconds).
READ_P95, WRITE_P95, ANY_P99, PAGE_P95 = 1.5, 2.0, 4.0, 5.0

CLOSING: set[asyncio.Future] = set()  # reload-dropped clients still closing
RECORDS: list[dict] = []  # one row per request
#: Each team's 4-digit entry code, read through the instructor API after every
#: reset (a reset issues a new code). Issue #413; there is no test-only bypass.
CODES: dict[int, str] = {}
SAMPLES: list[dict] = []  # one row per resource sample
BURST = {"name": "setup"}
PUBLIC = {"on": False}  # set by --i-own-this-public-host; enables cloudflare_blocked counting
BLOCKED = "cloudflare_blocked"
BLOCK_STATUS = (403, 429, 503)
T0 = time.perf_counter()


def phase(name: str) -> None:
    BURST["name"] = name
    print(f"[{time.perf_counter() - T0:7.1f}s] phase {name}", flush=True)


def lognormal_delay(rng: random.Random, median: float = 6.0, p90: float = 20.0) -> float:
    """Arrival offset: lognormal with the plan's median 6 s / p90 20 s."""
    sigma = (math.log(p90) - math.log(median)) / 1.2816
    return rng.lognormvariate(math.log(median), sigma)


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q / 100 * len(ordered)) - 1))]


def is_cf_blocked(resp: httpx.Response) -> bool:
    """Cloudflare rate limit / challenge, not the app: 403/429/503, HTML error, cf-mitigated."""
    if not PUBLIC["on"] or resp.status_code < 400:
        return False
    html = "text/html" in resp.headers.get("content-type", "")
    return resp.status_code in BLOCK_STATUS or html or "cf-mitigated" in resp.headers


def error_code(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return ""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("code", ""))
    return ""


async def call(
    client: httpx.AsyncClient,
    name: str,
    method: str,
    url: str,
    expect: tuple[int, ...] = (200,),
    **kw,
) -> httpx.Response | None:
    """One timed request. Status outside `expect` (or a transport error) is unexpected."""
    t0 = time.perf_counter()
    status, code, resp = 0, "", None
    try:
        try:
            resp = await client.request(method, url, headers=HDR, **kw)
        except httpx.RemoteProtocolError:
            # The server closed an idle keep-alive socket as we reused it; browsers
            # retry an idempotent request once, so do the same and mark it. A POST
            # may have committed, so it is never resent.
            if method != "GET":
                raise
            code = "keepalive_retry"
            resp = await client.request(method, url, headers=HDR, **kw)
        status = resp.status_code
        code = error_code(resp) if status >= 400 else code
        if is_cf_blocked(resp):
            code = BLOCKED
    except (TimeoutError, httpx.HTTPError) as exc:
        code = type(exc).__name__
    except asyncio.CancelledError:
        RECORDS.append(_row(name, method, t0, -1, "cancelled", False))
        raise
    RECORDS.append(_row(name, method, t0, status, code, status in expect))
    return resp


def _row(name, method, t0, status, code, ok) -> dict:
    return {
        "burst": BURST["name"],
        "name": name,
        "method": method,
        "t": round(t0, 3),
        "latency": round(time.perf_counter() - t0, 4),
        "status": status,
        "code": code,
        "ok": ok,
    }


# ---------------------------------------------------------------- static assets

IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)["'](/[^"']+)["']""")
DYN_RE = re.compile(r"""import\(\s*["'](/[^"']+)["']""")
BUILT_RE = re.compile(r"""["'/](assets/[\w.\-]+\.(?:js|css))["']""")


async def capture_assets(base: str) -> list[str]:
    """Same-origin files a cold load of /exercise fetches (dev: module graph; built: chunks).

    ponytail: regex crawl, keeps static imports + exercise lazy routes; a Playwright
    capture is exact (plan 2.1) if this proves too far off.
    """
    async with httpx.AsyncClient(base_url=base, timeout=60) as c:
        html = (await c.get("/exercise")).text
        queue = re.findall(r'(?:src|href)="(/[^"]+)"', html)
        seen: list[str] = []
        while queue:
            path = queue.pop(0)
            if path in seen or path.startswith(("/v1", "/api")):
                continue
            seen.append(path)
            text = (await c.get(path)).text
            if not re.search(r"\.(m?js|tsx?|jsx|css)(\?|$)|/@|/node_modules/", path):
                continue
            dyn = set(DYN_RE.findall(text))
            queue += [m for m in IMPORT_RE.findall(text) if m not in dyn or "xercise" in m]
            queue += ["/" + m for m in BUILT_RE.findall(text) if "xercise" in m or "vendor" in m]
        return seen


async def _drain(client: httpx.AsyncClient, path: str) -> httpx.Response:
    async with client.stream("GET", path) as resp:
        async for _ in resp.aiter_raw():  # gzip bytes left undecoded
            pass
    return resp


async def fetch_asset(client: httpx.AsyncClient, path: str) -> None:
    """GET one static file on the device's pooled keep-alive client, like a browser tab.

    The device's client holds at most 6 connections and reuses them, so a cold load
    opens ~6 TLS connections, not one per file (the Oct 27 public-50 drops all fell
    in the two bursts where the old one-socket-per-file fetch opened ~650 at once).
    Streaming with aiter_raw skips the gzip decode that made httpx cost 40-150 ms of
    generator CPU per 300 KB file (now ~2 ms, raw socket ~1 ms). HTTP/1.1 only: h2 is
    not installed.
    """
    t0 = time.perf_counter()
    status, code = 0, ""
    try:
        try:
            resp = await _drain(client, path)
        except httpx.RemoteProtocolError:
            code = "keepalive_retry"  # idle socket closed as we reused it; a GET retries
            resp = await _drain(client, path)
        status = resp.status_code
        if is_cf_blocked(resp):
            code = BLOCKED
    except (TimeoutError, httpx.HTTPError) as exc:
        code = type(exc).__name__
    except asyncio.CancelledError:
        RECORDS.append(_row("asset", "GET", t0, -1, "cancelled", False))
        raise
    RECORDS.append(_row("asset", "GET", t0, status, code, status == 200))


# ---------------------------------------------------------------- actors

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def make_client(base: str, **kw) -> httpx.AsyncClient:
    """AsyncClient that still sends Secure cookies to a loopback http base (IAP/SSH tunnel).

    The VM sets `Secure` cookies; httpx never sends those over plain http, so a tunnel to
    127.0.0.1 would 401 every call. Only loopback bases are relaxed.
    """
    client = httpx.AsyncClient(base_url=base, **kw)
    host = client.base_url.host
    if client.base_url.scheme == "http" and host in LOOPBACK_HOSTS:
        for c in client.cookies.jar:  # cookies copied in before any response
            c.secure = False

        async def _unsecure(_resp: httpx.Response) -> None:
            for c in client.cookies.jar:
                c.secure = False

        client.event_hooks["response"].append(_unsecure)
    return client


class Student:
    def __init__(self, idx: int, team: int, base: str, rng: random.Random, assets: list[str]):
        self.idx, self.team, self.rng, self.assets = idx, team, rng, assets
        self.base = base
        self.client = self._new_client()
        self.prefix = f"t{team}-"
        self.wrote: set[tuple[str, str]] = set()
        self.reloads = 0

    def _new_client(self, cookies: httpx.Cookies | None = None) -> httpx.AsyncClient:
        return make_client(
            self.base, timeout=30, cookies=cookies, limits=httpx.Limits(max_connections=6)
        )

    async def _assets(self) -> None:
        sem = asyncio.Semaphore(6)  # browser-like parallelism per device

        async def one(path: str) -> None:
            async with sem:
                await fetch_asset(self.client, path)

        await asyncio.gather(*(one(p) for p in self.assets))

    async def _page_once(self, event: str) -> None:
        await self._assets()
        await call(self.client, "GET /v1/exercise", "GET", "/v1/exercise")
        cur = await call(self.client, "GET current", "GET", WS, expect=(200, 401))
        if cur is None or cur.status_code != 200:
            await call(
                self.client,
                "POST workspaces",
                "POST",
                "/v1/exercise/workspaces",
                json={"team_number": self.team, "code": CODES[self.team]},
            )
            await call(self.client, "GET current", "GET", WS)
        await asyncio.gather(
            call(self.client, "GET events", "GET", f"{WS}/events"),
            call(self.client, "GET events", "GET", f"{WS}/events"),
        )
        await asyncio.gather(
            call(self.client, "GET list", "GET", f"{WS}/events/{event}/list"),
            call(self.client, "GET settings", "GET", f"{WS}/events/{event}/settings"),
        )

    async def page_load(self, event: str = ROUND1) -> None:
        """Full page load to first list row; reloaded when it takes over 8 s."""
        t0 = time.perf_counter()
        for attempt in range(MAX_RELOADS + 1):
            try:
                await asyncio.wait_for(
                    self._page_once(event), IMPATIENT_S if attempt < MAX_RELOADS else 60
                )
                RECORDS.append(_row("page_load", "PAGE", t0, 200, f"reloads={attempt}", True))
                return
            except TimeoutError:
                # A reload drops the tab's sockets; a fresh client keeps the cookie and
                # avoids httpcore's pool leaking slots held by cancelled requests.
                self.reloads += 1
                old, self.client = self.client, self._new_client(self.client.cookies)
                CLOSING.add(asyncio.ensure_future(old.aclose()))
        RECORDS.append(_row("page_load", "PAGE", t0, 0, "gave_up", False))

    def _weights(self) -> dict[str, int]:
        while True:  # all four at 0 is a 422 the slider UI cannot send
            w = {f: self.rng.randint(0, 10) for f in FACTORS}
            if any(w.values()):
                return w

    async def save(self, event: str, name: str) -> None:
        resp = await call(
            self.client,
            "PUT settings",
            "PUT",
            f"{WS}/events/{event}/settings/{name}",
            expect=(200, 409),
            json={"weights": self._weights()},
        )
        if resp is not None and resp.status_code == 200:
            self.wrote.add((event, name))
        elif resp is not None and error_code(resp) != "exercise_too_many_settings":
            RECORDS[-1]["ok"] = False  # only the 3-name cap is an expected 409

    async def matching(self, event: str, until: float) -> None:
        if self.idx < len(TEAMS):  # one device per team saves the name the results run uses
            for _ in range(3):  # a student whose page never loaded reloads, then saves again
                await self.save(event, self.prefix + "A")
                if (event, self.prefix + "A") in self.wrote:
                    break
                await self.page_load(event)
        while time.perf_counter() < until:
            # Think time stays real (plan 1.3): --scale shortens phases, never the request rate.
            await asyncio.sleep(self.rng.uniform(6, 20))
            r = self.rng.random()
            ev = f"{WS}/events/{event}"
            if r < 0.70:
                for _ in range(3 if self.rng.random() < 0.10 else 1):  # keyboard: 3 commits
                    w = self._weights()
                    await asyncio.gather(
                        call(self.client, "GET list", "GET", f"{ev}/list", params=w),
                        call(self.client, "GET settings", "GET", f"{ev}/settings"),
                    )
                    await asyncio.sleep(0.3)
            elif r < 0.80:
                name = self.prefix + (
                    self.rng.choice("ABC")
                    if self.rng.random() < 0.6
                    else f"x{self.rng.randint(0, 99)}"
                )
                await self.save(event, name)
            elif r < 0.88:
                await call(
                    self.client,
                    "GET compare",
                    "GET",
                    f"{ev}/settings/compare",
                    expect=(200, 404),
                    params={"a": self.prefix + "A", "b": self.prefix + "B"},
                )
            elif r < 0.92:
                await call(self.client, "GET list.csv", "GET", f"{ev}/list.csv")
            elif r < 0.97:
                await self.page_load(event)
            else:
                await call(self.client, "GET events", "GET", f"{WS}/events")

    async def settings_names(self, event: str) -> list[str]:
        # Check reads are spread over 3 s like real screens; 150 reads in the same
        # millisecond would test the checker, not the class (they did trip F5/F6).
        await asyncio.sleep(self.rng.uniform(0, 3))
        resp = await call(self.client, "GET settings", "GET", f"{WS}/events/{event}/settings")
        return (
            [s["name"] for s in resp.json()["settings"]]
            if resp is not None and resp.status_code == 200
            else []
        )

    async def run_results(self, event: str, window: float) -> tuple[int, str, str | None]:
        await asyncio.sleep(self.rng.uniform(0, window))
        resp = await call(
            self.client,
            "POST results",
            "POST",
            f"{WS}/events/{event}/results",
            expect=(201, 409),
            json={"setting_name": self.prefix + "A"},
        )
        status, code = (
            (resp.status_code, error_code(resp)) if resp is not None else (0, "transport")
        )
        if status == 409 and code != "exercise_results_already_run":
            RECORDS[-1]["ok"] = False
        got = await call(self.client, "GET results", "GET", f"{WS}/events/{event}/results")
        ev = f"{WS}/events/{event}"
        await asyncio.gather(  # the rest of the results page (plan 1.3)
            call(self.client, "GET list", "GET", f"{ev}/list"),
            call(self.client, "GET settings", "GET", f"{ev}/settings"),
            call(self.client, "GET asking-choice", "GET", f"{WS}/asking-choice"),
            call(self.client, "GET events", "GET", f"{WS}/events"),
        )
        stamp = (
            (got.json() or {}).get("created_at")
            if got is not None and got.status_code == 200
            else None
        )
        return status, code, stamp

    async def ask(self, window: float) -> tuple[int, str]:
        await asyncio.sleep(self.rng.uniform(0, window))
        choice = self.rng.choice(["better_recommendations", "small_reward", "required"])
        resp = await call(
            self.client,
            "POST asking-choice",
            "POST",
            f"{WS}/asking-choice",
            expect=(200, 409),
            json={"choice": choice},
        )
        status, code = (
            (resp.status_code, error_code(resp)) if resp is not None else (0, "transport")
        )
        if status == 409 and code != "exercise_asking_already_chosen":
            RECORDS[-1]["ok"] = False
        return status, code

    async def refresh(self, window: float) -> tuple[int, str]:
        await asyncio.sleep(self.rng.uniform(0, window))
        resp = await call(self.client, "POST refresh", "POST", f"{WS}/refresh", expect=(200, 409))
        status, code = (
            (resp.status_code, error_code(resp)) if resp is not None else (0, "transport")
        )
        if status == 409 and code != "exercise_already_refreshed":
            RECORDS[-1]["ok"] = False
        return status, code

    async def asking_state(self) -> dict:
        await asyncio.sleep(self.rng.uniform(0, 3))
        resp = await call(self.client, "GET asking-choice", "GET", f"{WS}/asking-choice")
        return resp.json() if resp is not None and resp.status_code == 200 else {}


class Instructor:
    def __init__(self, base: str):
        self.client = make_client(base, timeout=60)

    async def login(self) -> None:
        passcode = os.environ.get("LOADTEST_INSTRUCTOR_PASSCODE", "")
        if not passcode:
            sys.exit("LOADTEST_INSTRUCTOR_PASSCODE is not set")
        resp = await call(
            self.client,
            "POST instructor login",
            "POST",
            f"{INS}/login",
            json={"passcode": passcode},
        )
        if resp is None or resp.status_code != 200:
            sys.exit(
                f"instructor login refused: {resp.status_code if resp else 'no response'}"
                " (server needs SMARTMATCH_EXERCISE_COOKIE_SECURE=false on plain http)"
            )

    async def reset_all(self) -> None:
        for n in TEAMS:
            await call(
                self.client,
                "POST reset",
                "POST",
                f"{INS}/workspaces/{n}/reset",
                expect=(200, 404, 409),
            )
        for ev in (ROUND1, ROUND2):
            await call(self.client, "POST lock", "POST", f"{INS}/events/{ev}/lock")
        await self.fetch_codes()

    async def fetch_codes(self) -> None:
        """Every team's entry code, from the instructor API (never printed)."""
        resp = await call(self.client, "GET team codes", "GET", f"{INS}/team-codes")
        if resp is None or resp.status_code != 200:
            sys.exit(f"team codes refused: {resp.status_code if resp else 'no response'}")
        CODES.update({t["team_number"]: t["code"] for t in resp.json()["teams"]})

    async def unlock(self, ev: str) -> None:
        await call(self.client, "POST unlock", "POST", f"{INS}/events/{ev}/unlock")

    async def teams(self) -> list[dict]:
        resp = await call(self.client, "GET instructor workspaces", "GET", f"{INS}/workspaces")
        return resp.json()["teams"] if resp is not None and resp.status_code == 200 else []

    async def detail(self, n: int) -> dict:
        resp = await call(self.client, "GET instructor detail", "GET", f"{INS}/workspaces/{n}")
        return resp.json() if resp is not None and resp.status_code == 200 else {}

    async def poll(self, stop: asyncio.Event, every: float) -> None:
        """The projector: teams page every 15 s, one team detail every 60 s."""
        n = 0
        while not stop.is_set():
            await self.teams()
            if n % 4 == 0:
                await self.detail(TEAMS[n // 4 % 6])
            n += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), every)


async def canary(base: str, stop: asyncio.Event) -> None:
    """1 req/s cheap read: shows lock waiters starving the pool or thread pool (H10)."""
    async with httpx.AsyncClient(base_url=base, timeout=60) as c:
        await c.post(
            "/v1/exercise/workspaces", headers=HDR, json={"team_number": 1, "code": CODES[1]}
        )
        while not stop.is_set():
            await call(c, "canary GET current", "GET", WS)
            await asyncio.sleep(1)


# ---------------------------------------------------------------- sampling


def _proc_cpu(pid: int) -> tuple[float, int]:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    ticks = int(fields[11]) + int(fields[12])
    rss_pages = int(fields[21])
    return ticks / os.sysconf("SC_CLK_TCK"), rss_pages * os.sysconf("SC_PAGE_SIZE") // 2**20


async def sampler(stop: asyncio.Event, pids: dict[str, int], dsn: str | None) -> None:
    """Every 1 s: CPU % and RSS per process, DB connections by state and advisory-lock waiters."""
    conn = None
    if dsn:
        import psycopg  # repo dependency; only needed for DB sampling

        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    pids = {k: p for k, p in pids.items() if Path(f"/proc/{p}/stat").exists()}
    last = {k: (_proc_cpu(p)[0], time.perf_counter()) for k, p in pids.items()}
    while not stop.is_set():
        await asyncio.sleep(1)
        row = {
            "t": round(time.perf_counter(), 3),
            "burst": BURST["name"],
            "host_load1": float(Path("/proc/loadavg").read_text().split()[0]),
        }
        for k, p in pids.items():
            try:
                cpu, rss = _proc_cpu(p)
            except (FileNotFoundError, ProcessLookupError):
                row[f"{k}_cpu"] = -1
                continue
            prev_cpu, prev_t = last[k]
            now = time.perf_counter()
            row[f"{k}_cpu"] = round(100 * (cpu - prev_cpu) / (now - prev_t), 1)
            row[f"{k}_rss_mb"] = rss
            last[k] = (cpu, now)
        if conn is not None:
            cur = await conn.execute(
                "SELECT count(*) FILTER (WHERE state='active'),"
                " count(*) FILTER (WHERE state='idle'),"
                " count(*) FILTER (WHERE state LIKE 'idle in transaction%'),"
                " count(*) FILTER (WHERE wait_event_type='Lock' AND wait_event='advisory'),"
                " count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
            active, idle, idle_tx, adv, total = await cur.fetchone()
            row.update(
                db_active=active,
                db_idle=idle,
                db_idle_tx=idle_tx,
                db_advisory_waiters=adv,
                db_total=total,
            )
        SAMPLES.append(row)
    if conn is not None:
        await conn.close()


# ---------------------------------------------------------------- run of show

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"burst": BURST["name"], "check": name, "ok": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {BURST['name']}: {name} {detail}", flush=True)


def once_per_team(student_wins: int, instructor_won: bool) -> bool:
    """Exactly one write per team, whoever made it."""
    return student_wins + int(instructor_won) == 1


def one_winner(statuses: list[int], win: int) -> bool:
    """1 x `win` and every other device refused with 409."""
    c = Counter(statuses)
    return c[win] == 1 and c[409] == len(statuses) - 1


def by_team(students: list[Student], results: list) -> dict[int, list]:
    out: dict[int, list] = defaultdict(list)
    for s, r in zip(students, results, strict=True):
        out[s.team].append(r)
    return out


async def check_isolation(students: list[Student], ins: Instructor, event: str) -> None:
    names = await asyncio.gather(*(s.settings_names(event) for s in students))
    leaks = [
        (s.team, n)
        for s, ns in zip(students, names, strict=True)
        for n in ns
        if not n.startswith(s.prefix)
    ]
    check("every student sees only own team's settings", not leaks, f"leaks={leaks[:5]}")
    for n in TEAMS:
        d = await ins.detail(n)
        mine = {
            x["name"] for x in d.get("saved_settings", []) if x.get("event_key", event) == event
        }
        bad = [x for x in mine if not x.startswith(f"t{n}-")]
        check(f"instructor detail team {n}: only own settings", not bad, f"{sorted(mine)}")


def run_stamps(stamps: list[str | None]) -> tuple[int, int]:
    """(distinct runs seen, devices that read no result). None is a failed read, not a run."""
    return len({ts for ts in stamps if ts is not None}), sum(ts is None for ts in stamps)


def first_per_team(students) -> list:
    return [next(s for s in students if s.team == n) for n in TEAMS]


async def probe_code(s, event: str, expected: str) -> tuple[int, str]:
    """One round-two run press that must be refused with ``expected`` (no state change)."""
    resp = await call(
        s.client,
        "POST results probe",
        "POST",
        f"{WS}/events/{event}/results",
        expect=(409,),
        json={"setting_name": s.prefix + "A"},
    )
    status, code = (resp.status_code, error_code(resp)) if resp is not None else (0, "transport")
    if code != expected:
        RECORDS[-1]["ok"] = False
    return status, code


async def check_list_limit(students, event: str) -> None:
    for s in first_per_team(students):
        resp = await call(s.client, "GET list", "GET", f"{WS}/events/{event}/list")
        body = resp.json() if resp is not None and resp.status_code == 200 else {}
        n = len(body.get("entries", []))
        check(
            f"team {s.team}: list limit {INVITE_LIMIT}",
            body.get("invite_limit") == INVITE_LIMIT and n == INVITE_LIMIT,
            f"invite_limit={body.get('invite_limit')} entries={n}",
        )


async def check_round_two_locked(students) -> None:
    for s in first_per_team(students):
        status, code = await probe_code(s, ROUND2, "exercise_round_two_locked")
        check(
            f"team {s.team}: Harbor run before Northline refused",
            status == 409 and code == "exercise_round_two_locked",
            f"{status} {code}",
        )


async def check_ask_first(students, ins) -> None:
    await ins.unlock(ROUND2)
    try:
        for s in first_per_team(students):
            status, code = await probe_code(s, ROUND2, "exercise_ask_first")
            check(
                f"team {s.team}: Harbor run before the refresh refused",
                status == 409 and code == "exercise_ask_first",
                f"{status} {code}",
            )
    finally:
        await call(ins.client, "POST lock", "POST", f"{INS}/events/{ROUND2}/lock")


async def results_burst(students, ins, event: str, window: float) -> None:
    await ins.unlock(event)
    res = await asyncio.gather(*(s.run_results(event, window) for s in students))
    for team, rows in sorted(by_team(students, res).items()):
        created = Counter(st for st, _, _ in rows)
        runs_seen, unread = run_stamps([ts for _, _, ts in rows])
        check(
            f"team {team}: 1 x 201, rest 409 already_run",
            one_winner([st for st, _, _ in rows], 201),
            f"{dict(created)}",
        )
        check(
            f"team {team}: one run, every device sees it",
            runs_seen == 1 and unread == 0,
            f"distinct_runs={runs_seen} devices_without_a_result_read={unread}",
        )
        d = await ins.detail(team)
        runs = [r for r in d.get("result_runs", []) if r.get("event_key") == event]
        check(
            f"team {team}: instructor shows exactly 1 run for {event}",
            len(runs) == 1,
            f"runs={len(runs)}" if d else "instructor detail unreadable (no response)",
        )


async def asking_and_refresh(students, ins, window: float) -> None:
    phase("B4 asking")
    res = await asyncio.gather(*(s.ask(window) for s in students))
    for team, rows in sorted(by_team(students, res).items()):
        c = Counter(st for st, _ in rows)
        check(
            f"team {team}: asking 1 x 200, rest 409",
            one_winner([st for st, _ in rows], 200),
            f"{dict(c)}",
        )
    await check_ask_first(students, ins)
    phase("B5 refresh + refresh-all")

    # Teams 1-3 press refresh themselves and race the instructor's refresh-all, sent
    # inside their first second; teams 4-6 wait for the instructor (plan B5b).
    racers = [s for s in students if s.team <= 3]

    async def refresh_all() -> list[int]:
        await asyncio.sleep(random.uniform(0.2, 1.0))
        resp = await call(ins.client, "POST refresh-all", "POST", f"{INS}/refresh-all")
        return (
            resp.json().get("refreshed_team_numbers", [])
            if resp is not None and resp.status_code == 200
            else []
        )

    res, by_instructor = await asyncio.gather(
        asyncio.gather(*(s.refresh(window) for s in racers)), refresh_all()
    )
    pressed = by_team(racers, res)
    for team in TEAMS:
        student_200 = Counter(st for st, _ in pressed.get(team, []))[200]
        check(
            f"team {team}: refreshed exactly once (students+instructor)",
            once_per_team(student_200, team in by_instructor),
            f"student_200={student_200} instructor={team in by_instructor}",
        )
    states = await asyncio.gather(*(s.asking_state() for s in students))
    for team, rows in sorted(by_team(students, states).items()):
        choices = {r.get("choice") for r in rows}
        check(
            f"team {team}: all devices agree on asking + refreshed",
            len(choices) == 1 and None not in choices and all(r.get("refreshed") for r in rows),
            f"choices={choices}",
        )
        asked = {(r.get("refresh_counts") or {}).get("asked_without_card") for r in rows}
        check(
            f"team {team}: {ASKED_WITHOUT_CARD} without a card asked",
            asked == {ASKED_WITHOUT_CARD},
            f"asked={asked}",
        )


async def run(args) -> int:
    async with httpx.AsyncClient(base_url=args.base, timeout=10) as c:
        release = (await c.get("/api/health")).json().get("release", "")
    if not release.startswith("loadtest-") and not args.allow_any_release:
        sys.exit(
            f"target reports release {release!r}, not 'loadtest-*'; this run resets teams 1-6,"
            " so it only runs against a stack started for load tests (--allow-any-release)"
        )
    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scale = args.scale
    assets = [] if args.no_assets else await capture_assets(args.base)
    print(
        f"assets per cold load: {len(assets)}; students: {args.students}; scale: {scale}x",
        flush=True,
    )
    ins = Instructor(args.base)
    await ins.login()
    await ins.reset_all()
    students = [
        Student(i, TEAMS[i % 6], args.base, random.Random(rng.random()), assets)
        for i in range(args.students)
    ]
    stop = asyncio.Event()
    pids = {
        k: v
        for k, v in (("api", args.api_pid), ("web", args.web_pid), ("loadgen", os.getpid()))
        if v
    }
    bg = [
        asyncio.create_task(sampler(stop, pids, args.pg_dsn)),
        asyncio.create_task(canary(args.base, stop)),
        asyncio.create_task(ins.poll(stop, 15)),
    ]
    t_start = time.perf_counter()

    async def arrive(s: Student, event: str) -> None:
        await asyncio.sleep(lognormal_delay(s.rng))
        await s.page_load(event)

    try:
        phase("B1 cold load")
        await asyncio.gather(*(arrive(s, ROUND1) for s in students))
        teams = await ins.teams()
        check(
            "instructor lists all 6 teams",
            sorted(t["team_number"] for t in teams) == list(TEAMS),
            f"{[t['team_number'] for t in teams]}",
        )
        await check_list_limit(students, ROUND1)
        await check_round_two_locked(students)
        phase("S1 matching Northline")
        until = time.perf_counter() + 20 * 60 / scale
        await asyncio.gather(*(s.matching(ROUND1, until) for s in students))
        await check_isolation(students, ins, ROUND1)
        phase("B6 CSV")
        picked = [s for s in students if s.rng.random() < 0.6]

        async def csv_once(s: Student) -> None:
            await asyncio.sleep(s.rng.uniform(0, 90))
            await call(s.client, "GET list.csv", "GET", f"{WS}/events/{ROUND1}/list.csv")

        await asyncio.gather(*(csv_once(s) for s in picked))
        phase("B2 refresh load")
        await asyncio.gather(*(arrive(s, ROUND1) for s in students))
        phase("B3 run Northline")
        await results_burst(students, ins, ROUND1, 10)
        await asking_and_refresh(students, ins, 10)
        phase("S2 matching Harbor")
        until = time.perf_counter() + 8 * 60 / scale
        await asyncio.gather(*(s.matching(ROUND2, until) for s in students))
        await check_isolation(students, ins, ROUND2)
        phase("B3 run Harbor")
        await results_burst(students, ins, ROUND2, 10)
        phase("final")
        teams = {t["team_number"]: t for t in await ins.teams()}
        for n in TEAMS:
            t = teams.get(n, {})
            check(
                f"instructor team {n}: 2 runs, asked, refreshed",
                t.get("result_run_count") == 2 and t.get("asking_choice") and t.get("refreshed_at"),
                f"runs={t.get('result_run_count')} asking={t.get('asking_choice')}"
                f" refreshed={bool(t.get('refreshed_at'))}",
            )
    finally:
        stop.set()
        await asyncio.gather(*bg, return_exceptions=True)
        for s in students:
            await s.client.aclose()
        if not args.keep_state:
            await ins.reset_all()
        await ins.client.aclose()
    meta = {
        "base": args.base,
        "students": args.students,
        "scale": scale,
        "seed": args.seed,
        "assets_per_load": len(assets),
        "reloads": sum(s.reloads for s in students),
        "wall_s": round(time.perf_counter() - t_start, 1),
        "label": args.label,
    }
    return write_report(out, meta)


# ---------------------------------------------------------------- report


def summarize(records: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["burst"], r["name"], r["method"])].append(r)
    rows = []
    for (burst, name, method), rs in groups.items():
        lat = [r["latency"] for r in rs if r["status"] > 0]
        rows.append(
            {
                "burst": burst,
                "name": name,
                "method": method,
                "n": len(rs),
                "p50": round(pct(lat, 50), 3),
                "p95": round(pct(lat, 95), 3),
                "p99": round(pct(lat, 99), 3),
                "max": round(max(lat, default=0), 3),
                "unexpected": sum(
                    1 for r in rs if not r["ok"] and r["status"] != -1 and r["code"] != BLOCKED
                ),
                BLOCKED: sum(1 for r in rs if r["code"] == BLOCKED),
                "status": dict(
                    Counter(
                        f"{r['status']}{':' + r['code'] if r['code'] and (r['status'] >= 400 or r['code'] == 'keepalive_retry') else ''}"  # noqa: E501
                        for r in rs
                    )
                ),
            }
        )
    return sorted(rows, key=lambda r: (r["burst"], -r["p95"]))


def verdicts(records: list[dict]) -> list[dict]:
    api = [r for r in records if r["name"] not in ("asset", "page_load") and r["status"] > 0]
    reads = [r["latency"] for r in api if r["method"] == "GET"]
    writes = [r["latency"] for r in api if r["method"] in ("POST", "PUT", "DELETE")]
    pages = [r["latency"] for r in records if r["name"] == "page_load"]
    counted = [r for r in records if r["status"] != -1 and r["code"] != BLOCKED]
    unexpected = sum(1 for r in counted if not r["ok"])
    fivexx = sum(1 for r in counted if r["status"] >= 500 or r["status"] == 0)
    b3 = sum(1 for r in counted if r["burst"].startswith("B3") and not r["ok"])
    return [
        {
            "target": "API read p95 <= 1.5 s",
            "value": pct(reads, 95),
            "ok": pct(reads, 95) <= READ_P95,
        },
        {
            "target": "API write p95 <= 2 s",
            "value": pct(writes, 95),
            "ok": pct(writes, 95) <= WRITE_P95,
        },
        {
            "target": "API any p99 <= 4 s",
            "value": pct(reads + writes, 99),
            "ok": pct(reads + writes, 99) <= ANY_P99,
        },
        {
            "target": "page load to first list p95 <= 5 s",
            "value": pct(pages, 95),
            "ok": pct(pages, 95) <= PAGE_P95,
        },
        {
            "target": "unexpected errors < 1 %",
            "value": round(100 * unexpected / max(1, len(counted)), 2),
            "ok": unexpected / max(1, len(counted)) < 0.01,
        },
        {"target": "no 5xx / transport errors", "value": fivexx, "ok": fivexx == 0},
        {"target": "0 unexpected errors in B3", "value": b3, "ok": b3 == 0},
    ]


def write_report(out: Path, meta: dict) -> int:
    rows, verd = summarize(RECORDS), verdicts(RECORDS)
    peaks: dict[str, float] = {}
    for s in SAMPLES:
        for k, v in s.items():
            if isinstance(v, (int, float)) and k != "t":
                peaks[k] = max(peaks.get(k, v), v)
    burst_peaks: dict[str, dict] = defaultdict(dict)
    for s in SAMPLES:
        for k, v in s.items():
            if isinstance(v, (int, float)) and k != "t":
                burst_peaks[s["burst"]][k] = max(burst_peaks[s["burst"]].get(k, v), v)
    with open(out / "requests.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RECORDS[0]))
        w.writeheader()
        w.writerows(RECORDS)
    if SAMPLES:
        keys = sorted({k for s in SAMPLES for k in s})
        with open(out / "samples.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(SAMPLES)
    failed = [c for c in CHECKS if not c["ok"]]
    summary = {
        "meta": meta,
        "verdicts": verd,
        "checks_failed": failed,
        "checks_total": len(CHECKS),
        "peaks": peaks,
        "burst_peaks": burst_peaks,
        "endpoints": rows,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    lines = [
        f"# Load run {meta['label']}: {meta['students']} students",
        "",
        f"`{json.dumps(meta)}`",
        "",
        "## Targets",
        "",
        "| target | value | pass |",
        "|---|---|---|",
    ]
    lines += [
        f"| {v['target']} | {round(v['value'], 3)} | {'PASS' if v['ok'] else 'FAIL'} |"
        for v in verd
    ]
    blocked = sum(1 for r in RECORDS if r["code"] == BLOCKED)
    lines += ["", f"cloudflare_blocked: {blocked} (kept out of app errors and targets)"]
    lines += ["", f"## Correctness: {len(CHECKS) - len(failed)}/{len(CHECKS)} checks pass", ""]
    lines += [f"- FAIL {c['burst']}: {c['check']} {c['detail']}" for c in failed] or ["- all pass"]
    lines += [
        "",
        "## Resource peaks per phase",
        "",
        "```",
        json.dumps(burst_peaks, indent=1),
        "```",
        "",
        "## Endpoints (by phase, slowest p95 first)",
        "",
        "| phase | name | n | p50 | p95 | p99 | max | unexpected | cloudflare_blocked"
        " | status mix |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['burst']} | {r['name']} | {r['n']} | {r['p50']} | {r['p95']} | {r['p99']}"
        f" | {r['max']} | {r['unexpected']} | {r[BLOCKED]} | {r['status']} |"
        for r in rows
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print(
        f"\nwrote {out}/report.md; checks {len(CHECKS) - len(failed)}/{len(CHECKS)} pass; "
        f"targets {sum(v['ok'] for v in verd)}/{len(verd)} pass",
        flush=True,
    )
    return 0 if not failed and all(v["ok"] for v in verd) else 1


def check_host(base: str, opt_in: str | None) -> None:
    """Exit unless base is local, or is exactly the one public host the owner opted into."""
    url = httpx.URL(base)
    if url.host in LOCAL_HOSTS:
        return
    if url.host == REFUSED_HOST:
        sys.exit(f"refusing {url.host!r}: no longer the team's domain")
    if url.host != PUBLIC_HOST or opt_in != url.host or url.scheme != "https":
        sys.exit(
            f"refusing non-local host {url.host!r}: only https://{PUBLIC_HOST} with"
            f" --i-own-this-public-host {PUBLIC_HOST} (Plan C, owner's OK;"
            " docs/operations/exercise-load-test.md)"
        )
    PUBLIC["on"] = True
    print(
        f"WARNING: {url.host} is the live class site: this run writes to the live class"
        " database and resets teams 1-6.",
        flush=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--base", required=True, help="frontend server (proxies /v1) or api-exercise URL"
    )
    p.add_argument("--students", type=int, default=100)
    p.add_argument(
        "--scale",
        type=float,
        default=6.0,
        help="phase-length compression (10 = 20-min matching block in 2 min); rates stay real",
    )
    p.add_argument("--seed", type=int, default=20261019)
    p.add_argument("--out", required=True)
    p.add_argument("--label", default="")
    p.add_argument("--api-pid", type=int, default=0, help="pid to sample CPU/RSS for (uvicorn)")
    p.add_argument("--web-pid", type=int, default=0, help="pid to sample CPU/RSS for (vite)")
    p.add_argument(
        "--pg-dsn",
        default=os.environ.get("LOADTEST_PG_DSN"),
        help="libpq DSN for pg_stat_activity sampling",
    )
    p.add_argument("--no-assets", action="store_true", help="API only; skip static asset replay")
    p.add_argument("--keep-state", action="store_true", help="do not reset teams 1-6 at the end")
    p.add_argument(
        "--allow-any-release",
        action="store_true",
        help="run although /api/health release is not loadtest-* (still local hosts only)",
    )
    p.add_argument(
        "--i-own-this-public-host",
        metavar="HOST",
        help=f"opt in to the live class site; must equal the --base host ({PUBLIC_HOST})",
    )
    args = p.parse_args()
    check_host(args.base, args.i_own_this_public_host)
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
