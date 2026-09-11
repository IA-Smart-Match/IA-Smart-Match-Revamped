"""The shortlist bound is load-bearing for callers that fan out per candidate.

``MAX_SHORTLIST_SIZE`` is written down in
:mod:`smartmatch_domain.explanation` as half of the ratified "return 2-3
speakers" presentation rule, and
``tests/unit/test_explanation.py::test_the_shortlist_bounds_are_the_ratified_two_to_three``
pins it *for that reason*. This file pins it for a second, unrelated reason:
surfaces downstream of a shortlist issue **one request per candidate with no
concurrency bound**, and they are correct today only because the server hands
back at most three names.

Two reasons, two tests, deliberately not merged. If the program direction ever
changes and "2-3" becomes "2-5", the presentation pin in
``test_explanation.py`` is the one that is *supposed* to be edited — and
whoever edits it would otherwise get no signal at all about the fan-out. This
file is that signal.
"""

from __future__ import annotations

from pathlib import Path

from smartmatch_domain.explanation import MAX_SHORTLIST_SIZE

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

#: The one surface that issues a network request per shortlisted candidate with
#: no concurrency bound: ``readRun.shortlist.map`` inside a bare
#: ``await Promise.all(...)``, one ``fetchSpeakerContactChannels`` per name.
INVITATION_COMPOSE_PAGE = (
    FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorInvitations.tsx"
)

#: Every place a shortlist is fanned out over, one entry per candidate, named
#: in the failure message so whoever trips this guard can go and look. Server
#: side there is none: ``routers/match_runs.py`` assembles the shortlist from
#: one already-loaded payload in memory, and the invitation batch route is
#: bounded by its own ``MAX_BATCH_RECIPIENTS`` rather than by this constant.
FANOUT_CALL_SITES: tuple[str, ...] = (
    "apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorInvitations.tsx "
    "— await Promise.all(readRun.shortlist.map(...)), one "
    "fetchSpeakerContactChannels request per candidate, no concurrency bound",
    "apps/web/legacy-frontend/src/app/pages/AIMatching.tsx "
    "— run.shortlist.map renders one CandidateCard per candidate; no requests, "
    "so this one only degrades in layout, not in load",
)

#: The largest shortlist those call sites can absorb *unbounded*.
#:
#: Not a round number and not the current value plus slack. A browser opens at
#: most six concurrent connections to one HTTP/1.1 origin, so a bare
#: ``Promise.all`` over six or fewer candidates is a single round of in-flight
#: requests: nothing queues behind anything, and adding a client-side limiter
#: would only duplicate a bound the transport already applies. At seven the
#: fan-out starts queuing on itself, the page's slowest request becomes the sum
#: of two rounds rather than one, and "no concurrency bound" stops being an
#: honest description of safe code.
#:
#: So this is the threshold at which the *absence* of a client-side bound turns
#: from correct into a defect — which is exactly the thing that must not change
#: silently. It is deliberately above 3: a raise to 4 or 5 really is safe, and
#: a guard that fired on it would be noise that gets bumped without thought.
MAX_UNBOUNDED_FANOUT = 6


def test_the_shortlist_stays_small_enough_to_fan_out_over_unbounded() -> None:
    """Raising ``MAX_SHORTLIST_SIZE`` past what a bare ``Promise.all`` absorbs.

    Fails on the raise, not on the eventual slow page — the call sites do not
    say out loud that they depend on this number, so nothing else would.
    """
    sites = "\n".join(f"  - {site}" for site in FANOUT_CALL_SITES)
    assert MAX_SHORTLIST_SIZE <= MAX_UNBOUNDED_FANOUT, (
        f"MAX_SHORTLIST_SIZE is now {MAX_SHORTLIST_SIZE}, above the "
        f"{MAX_UNBOUNDED_FANOUT} that shortlist consumers can fan out over "
        "without a concurrency bound. These call sites issue one request per "
        "shortlisted candidate inside a bare Promise.all:\n"
        f"{sites}\n"
        "They are correct only while the shortlist is small, and they do not "
        "say so themselves — which is why this test exists rather than a "
        "comment. Do not simply raise MAX_UNBOUNDED_FANOUT to match. Either "
        "(a) add an explicit concurrency bound at each site above and then "
        "raise this threshold with a note saying which bound now protects it, "
        "or (b) reconsider the raise: a shortlist is a thing a person reads, "
        "and the ratified rule in smartmatch_domain.explanation is 2-3."
    )


def test_the_fanout_call_site_census_is_still_accurate() -> None:
    """The threshold is only honest while the call sites it describes exist.

    A census in a comment rots. This asserts the load-bearing one is still
    shaped the way ``MAX_UNBOUNDED_FANOUT`` assumes — an unbounded
    ``Promise.all`` over ``shortlist`` — so that the guard above cannot quietly
    become a rule about nothing.
    """
    source = INVITATION_COMPOSE_PAGE.read_text(encoding="utf-8")

    assert "await Promise.all(" in source and "readRun.shortlist.map(" in source, (
        f"{INVITATION_COMPOSE_PAGE.relative_to(REPO_ROOT)} no longer fans out "
        "over readRun.shortlist inside a bare Promise.all. If a concurrency "
        "bound was added there, that is an improvement — record it by updating "
        "FANOUT_CALL_SITES and the reasoning behind MAX_UNBOUNDED_FANOUT in "
        "this file. If the page moved, point this census at its new home. Do "
        "not delete the guard while any surface still issues one request per "
        "shortlisted candidate."
    )
