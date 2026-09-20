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
    "Allowance",
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


@dataclass(frozen=True, slots=True)
class Allowance:
    """What each of the two bounds said about one attempt.

    Reported separately rather than reduced to a single boolean, because the
    caller must treat them differently and the first version of this module did
    not:

    * ``key_allows`` is the caller's **own** budget. Spent means refused, full
      stop — a correct passcode does not buy more of it, and a person who has
      typed ten wrong passcodes in five minutes waits.
    * ``global_allows`` is the bound that exists for a caller spread across many
      addresses. It is the one an attacker can exhaust *on somebody else's
      behalf*, so it must never be the reason a correct passcode is refused.
      When it is spent, the login still checks the passcode and lets a correct
      one through, refunding the unit.

    The cost of that, stated plainly: once the global window is spent, each
    further attempt still pays for one key derivation, so this bound limits how
    many wrong passcodes are *accepted for checking* rather than how much CPU a
    flood can burn. Bounding the CPU as well needs the edge limiting OQ-CE-06 is
    open about.
    """

    key_allows: bool
    global_allows: bool


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

    def charge(self, key: str, *, now: datetime) -> Allowance:
        """Spend one attempt for ``key`` and report what each bound said.

        **The per-key bound is charged first, and the global bound only if the
        per-key one allowed the attempt.** The other order is what the first
        version of this module did, and it was a denial-of-service hole rather
        than a rate limit: a script posting sixty times from one address spent
        sixty *global* units — fifty of them on attempts its own key had already
        refused — and the real instructor, on a different address, was then
        locked out for the rest of the window. A caller must not be able to
        spend budget it is not allowed to use.

        Args:
            key: The client address, or :data:`UNRESOLVED_CALLER_KEY`.
            now: The caller's clock, passed in rather than read, so a test can
                cross a window boundary without sleeping.

        Returns:
            An :class:`Allowance` saying what each bound answered. The caller
            decides what to do with them — see :class:`Allowance` for why the
            two are reported separately rather than reduced to one boolean.
        """
        with self._lock:
            window = self._keys.get(key)
            if window is None:
                window = _Window(started_at=now, spent=0)
                self._evict_if_full()
                self._keys[key] = window
            self._keys.move_to_end(key)
            if not self._spend(window, now=now, allowance=self._per_key):
                return Allowance(key_allows=False, global_allows=False)

            if self._global is None:
                self._global = _Window(started_at=now, spent=0)
            return Allowance(
                key_allows=True,
                global_allows=self._spend(self._global, now=now, allowance=self._total),
            )

    def refund_global(self) -> None:
        """Give one global unit back, because the attempt turned out to be honest.

        The global bound exists for the caller the per-key bound cannot see: one
        behind many addresses, or behind a proxy this module deliberately does
        not parse. That makes it the one bound an attacker can drive up on the
        real instructor's behalf, and a bound that locks the passcode holder out
        of her own classroom is worse than the flood it was meant to stop.

        So a **correct** passcode costs no global budget at all: the login
        handler refunds it, and the window is left holding only the attempts
        that were wrong. The per-key bound is not refunded and is not meant to
        be — it is the caller's own budget, and a person who has just typed ten
        wrong passcodes waiting a few minutes is the limiter working.

        Floored at zero, so a refund without a matching spend cannot mint
        budget.
        """
        with self._lock:
            if self._global is not None and self._global.spent > 0:
                self._global.spent -= 1

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
