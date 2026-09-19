"""PLACEHOLDER (OQ-CE-06, owner Danny) — a persistence-free login limiter.

Why this module exists at all
=============================

The repository already has a rate limiter: ``smartmatch_api.dependencies``'s
quota machinery, which charges a window against a row through
:mod:`smartmatch_persistence`. An exercise router may import neither — the
first carries ``get_current_principal`` and the second is forbidden outright by
ADR-0025 D2 and by the import-linter contract that makes the absence
structural. So the one limiter in the codebase is unavailable to the one route
in the codebase that most obviously needs one: a passcode login with no account
behind it.

The handoff records the options as an open question (OQ-CE-06): proxy or edge
limiting on the VM, or a persistence-free in-process limiter. This is the
second, built as a **marked placeholder** so that shipping the instructor page
does not mean shipping an unbounded guessing surface while the question is
open. If the answer is "the VM's proxy does it", this module is deleted and the
dependency comes off the route; nothing else changes.

What it is honest about
=======================

* **Per process.** Two workers are two counters, so N workers multiply the
  effective allowance by N. The pilot VM runs one API container
  (``docker-compose.vm.yml``), which is why this is usable at all and why it
  stops being usable the moment the deployment scales out.
* **Per process lifetime.** A restart forgets every counter.
* **Fixed windows, not a sliding one.** A caller can spend a full allowance at
  the end of one window and another at the start of the next. A sliding window
  would need per-attempt timestamps, which is more state for a bound whose real
  job is to turn "unlimited guesses" into "not unlimited".
* **The client address is what the socket says.** There is no trusted-proxy
  header parsing here, and deliberately so: honouring ``X-Forwarded-For``
  without knowing which hop to trust hands every caller its own private
  allowance, which is worse than one shared counter behind a proxy. The global
  bound below is what covers that case.

What it does buy: a wrong passcode typed on a classroom laptop cannot be
retried thousands of times, and the PBKDF2 derivation in front of it costs a
fraction of a second per attempt on top.

Memory
======

Counters are bounded by :data:`MAX_TRACKED_CLIENTS`; when the table is full and
a new client appears, the oldest window is dropped. An unbounded dictionary
keyed on a caller-controlled value is a memory leak with a nice name.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

__all__ = [
    "INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT",
    "INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL",
    "INSTRUCTOR_LOGIN_WINDOW",
    "MAX_TRACKED_CLIENTS",
    "UNRESOLVED_CALLER_KEY",
    "FixedWindowLimiter",
]

#: Attempts one client address may spend on the instructor login per window.
#: Ten in five minutes is ``routers/auth.py``'s ``LOGIN_RATE_LIMIT``, copied
#: rather than invented: the population it bounds is the same one — somebody
#: who mistyped a passcode, or somebody guessing one — and a second number for
#: the same question would be a second thing to tune.
INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT: Final[int] = 10

#: Attempts *every* caller together may spend per window. There is one
#: instructor and one passcode, so a process seeing more than this many login
#: attempts in five minutes is not a classroom; it is the case the per-client
#: bound cannot see, because a caller behind many addresses — or behind a proxy
#: this module deliberately does not parse — is many clients to it.
INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL: Final[int] = 60

#: The fixed window both bounds are measured over.
INSTRUCTOR_LOGIN_WINDOW: Final[timedelta] = timedelta(minutes=5)

#: How many client addresses are tracked at once. Beyond this the oldest window
#: is evicted, so the table is a bound rather than a caller-controlled leak.
MAX_TRACKED_CLIENTS: Final[int] = 1_024

#: The bucket a request with no resolvable client address is charged against.
#: Such callers share one counter, which is the conservative direction — it can
#: refuse more than strictly necessary, never less. A per-request unique key
#: would be the opposite: every attempt its own fresh allowance, which is no
#: limit at all. Same reasoning, and same shape, as ``routers/auth.py``'s
#: ``_UNRESOLVED_CALLER_KEY``.
UNRESOLVED_CALLER_KEY: Final[str] = "client-address-unavailable"


@dataclass
class _Window:
    """One fixed window: when it started and how much has been spent in it."""

    started_at: datetime
    spent: int


class FixedWindowLimiter:
    """A per-key and global fixed-window counter, held in this process only.

    Not a general-purpose limiter and not offered as one — see the module
    docstring. It exists so that one route, in one no-login product, on one
    single-container deployment, is bounded while OQ-CE-06 is open.

    Thread-safe: FastAPI runs a ``def`` handler in a worker thread, so two
    login attempts really can land in this object at once, and a check-then-
    increment across two threads without a lock is a limit that admits one more
    than it says under exactly the load it exists for.
    """

    def __init__(self, *, per_key: int, total: int, window: timedelta) -> None:
        self._per_key: Final[int] = per_key
        self._total: Final[int] = total
        self._window: Final[timedelta] = window
        self._lock = threading.Lock()
        self._keys: OrderedDict[str, _Window] = OrderedDict()
        #: ``None`` until the first charge. Opened on the first attempt rather
        #: than at construction because a window needs a start, and the only
        #: honest start is a clock the caller passed in — a sentinel date here
        #: would be a naive datetime in a module whose callers are aware ones.
        self._global: _Window | None = None

    def charge(self, key: str, *, now: datetime) -> bool:
        """Spend one attempt for ``key``, or report that it has none left.

        Charged **before** the passcode is checked, so that a wrong passcode and
        a right one cost the same, and a caller cannot spend an unlimited number
        of attempts by never being right.

        Args:
            key: The client address, or :data:`UNRESOLVED_CALLER_KEY`.
            now: The caller's clock, passed in rather than read, so a test can
                cross a window boundary without sleeping.

        Returns:
            ``True`` when the attempt is allowed, ``False`` when either bound is
            already spent.
        """
        with self._lock:
            if self._global is None:
                self._global = _Window(started_at=now, spent=0)
            if not self._spend(self._global, now=now, allowance=self._total):
                return False
            window = self._keys.get(key)
            if window is None:
                window = _Window(started_at=now, spent=0)
                self._evict_if_full()
                self._keys[key] = window
            self._keys.move_to_end(key)
            return self._spend(window, now=now, allowance=self._per_key)

    def _spend(self, window: _Window, *, now: datetime, allowance: int) -> bool:
        """Roll ``window`` over if it has elapsed, then spend one of ``allowance``."""
        if now - window.started_at >= self._window:
            window.started_at = now
            window.spent = 0
        if window.spent >= allowance:
            return False
        window.spent += 1
        return True

    def _evict_if_full(self) -> None:
        """Drop the least recently charged key once the table is full."""
        while len(self._keys) >= MAX_TRACKED_CLIENTS:
            self._keys.popitem(last=False)
