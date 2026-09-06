"""The local scheduler sidecar (docker compose only).

**This module is a developer appliance that emulates Cloud Scheduler for
`docker compose up`, and it is never Cloud Scheduler's implementation.**
Cloud Scheduler's OIDC-authenticated trigger remains open F5/S-001 deployment
work; nothing here closes that finding, and this process must never be
described as though it had. Its entire job is to give ``POST
/operations/dispatch`` — which ``smartmatch_worker.main`` documents at length
as the thing that must run on a schedule *somewhere*, because a Cloud Run
service holds no process between requests to loop in — an external clock to
answer to when there is no real Cloud Scheduler job configured, so a
developer running compose sees the outbox actually drain instead of piling up
until someone remembers a manual curl.

## Why this is a separate process, not a thread in the worker

The whole architectural argument in ``smartmatch_worker.main`` for *not*
running an in-process poll loop is that a Cloud Run service has no process
between requests, so a thread would need ``min-instances >= 1`` to exist at
all and its death would be silent. Neither of those constraints holds for a
``docker compose`` service — it is exactly one long-lived process. But mixing
the timer into the worker anyway would still be wrong for this appliance,
because it would erase the one thing worth emulating: that Cloud Scheduler is
a caller **external to and authenticated against** the worker, reaching it
over the same HTTP boundary a real deployment's Cloud Scheduler job reaches.
A thread inside the worker calling ``ScheduledPass`` directly would bypass
``/operations/dispatch`` entirely and prove nothing about the endpoint or its
identity check. This process exists so that boundary keeps being exercised
even when nothing behind it is real infrastructure.

## Entry point

::

    python -m smartmatch_worker.local_scheduler

## Startup gate

Two environment variables, read directly rather than through
``smartmatch_worker.config.WorkerSettings`` — this process is not the worker
and needs none of its database or provider configuration, only these two:

* ``SMARTMATCH_EDITION`` must read exactly ``dev``. Any other value — unset
  included — exits before a single request is sent. A sidecar that would run
  in a real edition is a standing invitation to leave it wired up by
  accident; refusing to start is what makes that impossible rather than
  merely unlikely.
* ``SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN`` must be set. There is no
  fallback to any other token this image knows about — not the task token,
  which ``smartmatch_worker.config`` already refuses to let equal this one,
  and not a blank credential, which
  ``smartmatch_worker.identity.LocalBearerTaskVerifier`` would refuse on the
  worker's side regardless.

Deliberately **not** a ``WorkerSettings`` field: the table in ``config``'s
module docstring lists it as sidecar-only for exactly this reason — it is
consumed by a process that is not the worker, and folding it into
``WorkerSettings`` would suggest the worker itself does something with it,
when the worker only ever validates its own two dev tokens.

## The loop

Fixed to POST to ``http://worker:8080/operations/dispatch`` — the compose
service name, not a setting, and not something an environment variable can
repoint. A sidecar whose target could be reconfigured is the scheduler-shaped
half of the same risk ``local_tasks`` refuses on the delivery side: this
process has exactly one job and one place to send it. Every two seconds
(:data:`POLL_INTERVAL_SECONDS`, an argued code constant for the reason
``config``'s module docstring gives for keeping these out of the
environment), it sends one request and classifies the response:

* ``2xx`` — a pass ran. Logged and the loop continues.
* ``401``/``403``/``501`` — the token is wrong, or dispatch is not configured
  on the worker side. Neither is fixed by asking again, so this process logs
  clearly and **exits** rather than looping forever against a worker that
  will never accept it.
* ``5xx`` or a connection failure — the worker may not be up yet, or is
  between deploys. Logged as a retry and the loop continues.
* Anything else — logged and the loop continues; not confidently fatal, not
  confidently transient.

``SIGTERM`` sets a :class:`threading.Event` the loop's own wait checks, so
``docker compose down`` stops this process within one wait interval rather
than the container's kill timeout.
"""

from __future__ import annotations

import http.client
import logging
import os
import signal
import sys
import threading
from types import FrameType
from typing import Final
from urllib.parse import urlsplit

__all__ = ["main"]

logger = logging.getLogger(__name__)

#: Fixed by the docker-compose contract this module is written against (see
#: the module docstring). Not a setting — see there for why.
DISPATCH_URL: Final[str] = "http://worker:8080/operations/dispatch"

#: How often Cloud Scheduler would fire, reproduced as an argued code
#: constant. See the module docstring's "The loop" section.
POLL_INTERVAL_SECONDS: Final[float] = 2.0

#: How long to wait for one dispatch pass to answer before treating the
#: attempt as failed. A pass can legitimately take a while — it dispatches a
#: whole batch — so this is generous rather than tight.
REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0

#: Statuses that will not change by asking again: the credential is wrong, or
#: the worker has no task queue configured. See ``main``'s module docstring
#: for what each of these means at the worker's own boundary.
_FATAL_STATUSES: Final[frozenset[int]] = frozenset({401, 403, 501})


def _dispatch_once(token: str) -> int:
    """Send one ``POST /operations/dispatch``. Returns the response status.

    Uses :mod:`http.client` directly, which never follows a redirect on its
    own — the same discipline ``local_tasks`` documents on the delivery side,
    kept here even though nothing in this appliance's own compose file would
    ever answer with one.
    """
    parsed = urlsplit(DISPATCH_URL)
    # ``DISPATCH_URL`` is a module constant with a host written into it, so
    # this cannot be None. Asserted rather than defaulted for the reason
    # ``local_tasks._post`` gives: a fallback host would aim a credentialed
    # POST at an address nobody chose.
    assert parsed.hostname is not None
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port or 80, timeout=REQUEST_TIMEOUT_SECONDS
    )
    try:
        connection.request(
            "POST",
            parsed.path,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Length": "0",
            },
        )
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _run(stop: threading.Event, *, token: str) -> int:
    """The poll loop. Returns the process exit code.

    Never logs ``token`` and never places it in an exception message —
    everything this function logs names a status code or a connection
    failure, nothing the caller presented.
    """
    while not stop.is_set():
        try:
            status_code = _dispatch_once(token)
        except OSError as exc:
            logger.warning("local scheduler: could not reach the worker, will retry: %s", exc)
            stop.wait(POLL_INTERVAL_SECONDS)
            continue

        if 200 <= status_code < 300:
            logger.info("local scheduler: dispatch pass accepted (%d)", status_code)
        elif status_code in _FATAL_STATUSES:
            logger.error(
                "local scheduler: worker answered %d; retrying will not change "
                "that, so this sidecar is exiting rather than looping forever "
                "against a request it can never win",
                status_code,
            )
            return 1
        elif status_code >= 500:
            logger.warning("local scheduler: worker answered %d; will retry", status_code)
        else:
            logger.warning("local scheduler: worker answered unexpected status %d", status_code)

        stop.wait(POLL_INTERVAL_SECONDS)

    return 0


def main() -> int:
    """Entry point for ``python -m smartmatch_worker.local_scheduler``.

    Returns:
        The process exit code: ``0`` on an orderly stop (``SIGTERM``), ``1``
        if the startup gate refused to run or the loop hit a fatal response.
    """
    logging.basicConfig(level=logging.INFO)

    edition = os.environ.get("SMARTMATCH_EDITION")
    if edition != "dev":
        logger.error(
            "local scheduler: SMARTMATCH_EDITION is %r, not 'dev'; refusing to "
            "run. This sidecar is a docker-compose-only emulation of Cloud "
            "Scheduler and must never drive dispatch outside a developer's own "
            "machine",
            edition,
        )
        return 1

    token = os.environ.get("SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN")
    if not token:
        logger.error(
            "local scheduler: SMARTMATCH_LOCAL_SCHEDULER_BEARER_TOKEN is not "
            "set; refusing to run — there is no credential to present to "
            "/operations/dispatch"
        )
        return 1

    stop = threading.Event()

    def _handle_sigterm(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        stop.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    return _run(stop, token=token)


if __name__ == "__main__":
    sys.exit(main())
