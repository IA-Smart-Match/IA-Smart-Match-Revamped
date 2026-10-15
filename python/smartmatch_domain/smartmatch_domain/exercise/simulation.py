"""The simulated-results rule of the class exercise, written in plain words.

**This docstring is the statement Ann Wang and Dr. Lin receive** (requirements,
"Simulated results": *The rule is written in plain words in the code and shared
with Ann and Dr. Lin before the practice run*; ADR-0025 D7). The paragraph
below states the rule with the numbers the code runs today. Its first and last
sentences are design spec §11's draft; the middle is Ann's answer of 2026-09-25
to OQ-CE-03, with the team's translation of her words into numbers, which Chau
approved. The half credit that answer gave an undecided career goal on a broad
event was removed by Ann's revisions of 2026-10-02 (item 4b), here and in the
matching factor together. When the code changes, this paragraph changes with
it, and a test checks that every number in it is the number the code uses.

    For each profile the app decides whether the person notices the event,
    then whether they sign up, then whether they attend. Everyone gets the
    usual mass email, and 20 in 100 notice it. The team's listed students also
    get a personal CBACH email, and 60 in 100 notice that one, so about 68 in
    100 notice at least one of the two. Someone who notices nothing does not
    sign up. Someone who notices has the sign-up chance below. Everyone starts
    with a 5 in 100 chance of signing up. The biggest boosts go to a person
    when the event matches what they truly care about: 35 in 100 when one of
    their true interests is a topic of the event, and 15 in 100 more when
    their career goal fits the event. A person gets a boost of 5 in 100
    for each past event they have been to, up to 15 in 100 for 3 or more.
    Being in the major the event is aimed at gives 5 in 100 more. The total
    never goes below 0 or above 100 in 100. Each person who signs up has a
    65 in 100 chance of attending. The 8 students already signed up attend
    at that same 65 in 100, from the same fixed draw. There is no extra luck: the team's fixed draw alone
    decides who notices, signs up and shows up, so running the same list twice
    gives the same answer. The list's sign-ups include everyone the mass email
    alone would have brought, plus the ones the personal email added. The app
    uses each profile's true interests for this, not what the profile has told
    the app, which is why a list built on what the app knows can miss people.

Source: Ann Wang, email 2026-10-10 (Q2, Q4) for notice, show-up and no luck;
her 2026-10-06 reply to Chau (Step B) for the sign-up chances: start at 5,
add 35 / 15 / 5 per past event up to 15 (her 2026-10-15 reply) / 5. The 2026-10-10 email supersedes only the rest of the
2026-10-06 rule (15 in 100 notice, 70 in 100 attend, the extra luck). It says
"the team's existing sign-up chances", which the team had read as the older
code numbers (4 / 40 / 10 / 4). Owner ruling 2026-10-12: Ann's Oct 6 Step B;
past events = any past event (to confirm with Ann).

Ann's words of 2026-09-25 were: the event matches what the student genuinely
cares about, **a lot**; the student has attended events before, **some**; the
event is targeted toward the student's major, **a little**; random chance,
**some randomness**. The team first turned them into 40, 10 and 4 in 100; her
2026-10-06 numbers (35 + 15, 5 or 10, 5) replace that translation. "Some
randomness" first became up to 10 in 100 either way; Ann removed that band on
2026-10-10 (email, Q4): there is no extra luck, only the team's fixed draw.
Ann left the numbers to Chau. The team translated her words, Chau approved the
translation (wave-2 decision D7), and that closed OQ-CE-03. The sample result
the numbers were checked against is
``docs/archive/plans/open-questions/oq-ce-03-sample-result.md``. If Ann reacts to it,
changing a number is a one-line edit to :data:`EXERCISE_SIMULATION_COEFFICIENTS`.

## The five behaviours the requirements ask for

(1) **True fit lifts sign-up the most.** A profile is more likely to sign up
    when its hidden true interests and its career goal match the event.
(2) **Past attenders get some more.** A profile that has been to at least
    ``frequent_attender_events`` past events gets a lift that is
    smaller than the true-fit lift.
(3) **Same major alone gives only a small lift.** Being in the event's target
    majors, and nothing else, moves the number a little.
(4) **Chance is the team's fixed draw, nothing more.** The draws come
    from the team's seed, so a repeated run of the same list gives the same
    result — in any process, on any machine.
(5) **A reset per team touches no other team.** The team's seed is the only
    per-team thing this rule reads. Regenerating one team's seed changes that
    team's results and nothing else; there is no shared state in this module.

That (1) outranks (2) and (3) is not a matter of which numbers are chosen: it
is checked when the coefficients are constructed. :class:`SimulationCoefficients`
refuses any set where ``true_fit_lift`` does not exceed both
``frequent_attender_lift`` and ``same_major_lift``. Ann's further ordering —
attended before ("some") above same major ("a little") — is checked on the
shipped set by ``tests/unit/test_exercise_simulation.py`` rather than refused
here, so a test-only set may still isolate one lift at a time.

## The exact formula

For one profile and one event, with coefficients ``c``:

* ``fit_share`` is ``c.true_interest_share_of_fit`` for a true-interest overlap
  with the event's topics, plus ``1.0 - c.true_interest_share_of_fit`` for a
  career goal that is one of the event's topics — so ``1.0`` when both hold and
  ``0.0`` when neither does. A career goal that points at no topic
  (``Undecided``, ``Graduate school``) earns none of the career-goal part on
  any event. How the true-fit lift divides between the
  two parts is **not** a constant in this module: it is a coefficient, because
  choosing it decides whether Ann's "true interests and career goal" leans on
  interests or on goals (``true_interest_share_of_fit``, approved at one half).
* ``lift = c.true_fit_lift * fit_share``
  ``+ min(c.past_event_lift_cap, c.frequent_attender_lift * past_events)``
  if the profile attended at least ``c.frequent_attender_events`` past events
  (without a cap: the flat ``c.frequent_attender_lift``),
  ``+ c.same_major_lift`` if the profile's major is one of the event's target
  majors.
* ``noticed`` is ``mass_notice < c.mass_email_notice`` for a uniform draw, or,
  for a profile on the team's list only, ``cbach_notice <
  c.cbach_email_notice``. Not noticed means no sign-up.
* ``p = clamp(c.base_signup_rate + lift, 0.0, 1.0)``. The clamp is
  what keeps the number a probability when the lifts add past one; it is a
  ceiling, never a re-spread of weight.
* A noticing profile signs up when the ``signup`` draw is below ``p``, and
  attends when the ``attend`` draw is below ``c.attend_given_signup``.

Terms are compared as exact strings after ``strip()`` and ``casefold()``.
The vocabularies are closed at ingest
(:mod:`smartmatch_domain.exercise.vocabulary`), so both sides of every
comparison are already in Ann's spelling; there is no synonym table here.

**Unknown is not a mismatch (ADR-0011).** A profile with no career goal simply
does not collect the career-goal part of ``fit_share``. It is not penalised,
and it is not recorded as a goal that failed to fit. The same holds for an
empty true-interest set. Note what follows: ``true_interest_share_of_fit`` is
also the ceiling on the true-fit lift available to a profile whose career goal
the file does not carry, since that profile can reach at most the
true-interest part. That ceiling is a consequence of the split, not a penalty
applied to the unknown, and it is one more reason the split is a coefficient
rather than a constant chosen here.

## Determinism, and a deviation from design spec §11

Design spec §11 writes the chance draw as
``random.Random(workspace.seed ^ hash(event_key))``. **This implementation does
not use that**, deliberately: Python's ``hash()`` of a string is salted per
process (``PYTHONHASHSEED``), so the same team, the same list, and the same
event would give different results in a different process — which is exactly
what behaviour (4) forbids. The draws here come from a SHA-256 digest over the
seed, the event key, the profile number, and what is being drawn, instead,
which is stable across processes, machines, and Python builds. A test runs the
rule in a fresh subprocess under a different ``PYTHONHASHSEED`` and requires an
identical result.

Each field goes into the digest length-prefixed rather than joined by a
separator, so an event key that itself contains the separator cannot collide
with a different set of fields. The uniform value is the top 53 bits of the
digest over ``2**53``, which is the widest draw a float represents exactly, so
the result is genuinely in ``[0, 1)``: dividing 64 bits by ``2**64`` rounds the
largest digests up to exactly ``1.0``, and a profile at probability ``1.0``
would then fail to sign up.

Each profile's draws depend on that profile's number alone, never on the order
of the list or on who else was invited. So "email everyone" and a team's list
of thirty agree on every profile they share, and shuffling a list changes
nothing.

This is a classroom simulation, not cryptography. The repository's security
rules prefer :mod:`secrets` for random values; :mod:`hashlib` is used here as a
*stable digest*, and :class:`random.Random` is not used at all, because the
requirement is reproducibility rather than unpredictability. :mod:`secrets`
would be the wrong tool: it is unseedable by design.

## What this module is not

It is not a matching factor and must not become one. It does not import
``factor_registry``, ``scoring``, or ``explanation``; it produces no ranking
and no number that a class participant sees (ADR-0025 D8). It is one of the
two readers of a profile's hidden true interests (ADR-0025 D6). The other is
the refresh (design spec §13), which copies them onto a team's card overlay
(``results_cards.copied_cards``). Nothing this module returns carries them:
:class:`SimulationResult` holds profile numbers, and :func:`seats_empty` holds
a count of chairs.

## The coefficients: Ann's words, the team's numbers

Ann answered in words on 2026-09-25 (a lot / some / a little / some
randomness) and was told "Chau can then translate those choices into exact
numbers and show you a sample result before class".
:data:`EXERCISE_SIMULATION_COEFFICIENTS` is that translation, and Chau approved
it (wave-2 decision D7), which closed OQ-CE-03.
:func:`require_coefficients` still refuses if the value is ever ``None``.
Tests construct their own sets, clearly labelled as test-only.

The register names four quantities. The rule needs **nine**, and the five it
adds are named here rather than invented as constants. The shipped value and
where it comes from:

1. ``true_fit_lift`` — 0.50, split 0.35 interests / 0.15 career goal by
   ``true_interest_share_of_fit`` 0.7. Ann's Step B, 2026-10-06.
2. ``frequent_attender_lift`` — 0.05 for each past event, up to
   ``past_event_lift_cap`` — 0.15 (3 or more events). Every past event on the
   file row counts. Ann's email of 2026-10-15 (Q1) replaced the 5 / 10 tiers.
   The most any profile can reach is 0.05 + 0.35 + 0.15 + 0.15 + 0.05 = 0.75.
3. ``same_major_lift`` — 0.05. Ann's Step B.
4. ``mass_email_notice`` — 0.20 and ``cbach_email_notice`` — 0.60. Ann's
   email of 2026-10-10 (Q2). No chance band: her Q4 is "no extra luck".
5. ``attend_given_signup`` — 0.65. Ann's email of 2026-10-10 (Q2).
6. ``base_signup_rate`` — 0.05. Ann's Step B "start at 5%".
7. ``frequent_attender_events`` — 1. Ann's (b) is "has attended events
   before", so one past event is enough.
8. ``true_interest_share_of_fit`` — 0.7. How the true-fit lift divides between
   the interest overlap (35) and the career goal (15), and so the ceiling for
   a profile with no career goal on file. Ann's Step B.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

# A pure move, not a change: these two helpers were defined privately in this
# module and are now shared, unchanged, with the matching track that needs the
# same digest for the fixed order and the same term rule for the four factors.
# Two copies of "how a term is compared" is one more than the question has.
from smartmatch_domain.exercise.determinism import stable_digest as _digest
from smartmatch_domain.student_factors.terms import normalized_term as _normalized

__all__ = [
    "EVENT_SEATS",
    "EXERCISE_SIMULATION_COEFFICIENTS",
    "EXISTING_SIGNUPS",
    "CoefficientsNotConfirmedError",
    "InviteLimitExceededError",
    "SimulationCoefficients",
    "SimulationCoefficientsError",
    "SimulationEvent",
    "SimulationProfile",
    "SimulationResult",
    "existing_attended",
    "require_coefficients",
    "run_email_everyone",
    "seats_empty",
    "simulate_results",
]


#: Seats in the room, from the case in
#: ``docs/product/class-exercise-requirements.md`` ("What class participants
#: must be able to do": *a campus career event with 60 seats, 8 sign-ups, and
#: time to personally invite only 30 people*). A case fact, not a placeholder:
#: no open question governs it.
EVENT_SEATS: Final[int] = 60

#: Sign-ups the event already had before anybody was invited, from the same
#: sentence of the case. Also a case fact.
EXISTING_SIGNUPS: Final[int] = 8

#: How many bits of a digest become a uniform draw. 53 is the width of a
#: float's significand, so every value below is exact and the quotient is
#: strictly less than 1.0.
_UNIFORM_BITS: Final[int] = 53


class SimulationCoefficientsError(ValueError):
    """A coefficient set that is not usable as probabilities and lifts.

    A subclass of :class:`ValueError` so a caller that already refuses bad
    numbers needs no new branch.
    """


class CoefficientsNotConfirmedError(RuntimeError):
    """Raised if the exercise's coefficient set is ever removed (set to ``None``)."""


class InviteLimitExceededError(ValueError):
    """Raised when a team's list is longer than the invite limit allows."""


@dataclass(frozen=True, slots=True)
class SimulationProfile:
    """One made-up profile, as the rule needs to read it.

    Built by the results route from a stored row: ``true_interests`` from
    ``hidden_true_interests`` and ``career_goal`` from the **topic** that
    ``hidden_true_career_goal`` points at, through
    :func:`~smartmatch_domain.exercise.vocabulary.goal_topic_for_matching` —
    the same table "career goal fits this event" reads, so the rule and the
    factor cannot disagree about what a goal means.

    Attributes:
        profile_no: The profile's number in the data file. The only thing that
            reaches an output, and the only per-profile input to the draws.
        major: The profile's major, compared against the event's target majors.
        true_interests: The hidden "true" interests (ADR-0025 D6). This module
            is the only reader of this field. The refresh's card copy reads
            the stored column separately and never this type. An empty set
            is "nothing true recorded", which earns no lift and is not a
            mismatch (ADR-0011).

            ``repr=False``, for the reason
            :class:`~smartmatch_domain.exercise.layout.ParsedProfile` and
            ``dataset_repository.SimulationProfileRow`` both give: a default
            ``repr`` is what a log line, an assertion message and a debugger
            transcript print, so a withheld value inside one leaves the server
            through code nobody wrote. It carries the same cells
            ``exercise_profile.hidden_true_interests`` holds, so it earns the
            same treatment. The value is still there to be read deliberately —
            this module reads it on every call.
        career_goal: The topic the hidden true career goal points at, or
            ``None`` when the file has no goal or the goal points at no topic
            (``Undecided``, ``Graduate school``). ``None`` contributes no fit
            and costs nothing. ``repr=False`` for the same reason as
            ``true_interests``: it is derived from a withheld column.
        past_event_count: How many past events this profile attended.
        non_responding: ``True`` for a profile that stopped opening messages
            after the ``required`` asking choice (design spec §13). Such a
            profile never signs up, whatever its fit.
    """

    profile_no: int
    major: str
    true_interests: frozenset[str] = field(default=frozenset(), repr=False)
    career_goal: str | None = field(default=None, repr=False)
    past_event_count: int = 0
    non_responding: bool = False


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    """One exercise event, as the rule needs to read it.

    Topics and majors are in Ann's spelling, as ingest stored them.

    Attributes:
        event_key: The event's key. Part of every draw, so two events with one
            team's seed give two different sets of results.
        topic_tags: The event's topics.
        target_majors: The majors the event is aimed at.
    """

    event_key: str
    topic_tags: frozenset[str] = frozenset()
    target_majors: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """What one run of the rule produced, as profile numbers only.

    Every tuple is sorted and free of duplicates, and
    ``attended ⊆ signed_up ⊆ invited``. No interest, no major, and no number
    resembling a score appears here (ADR-0025 D6 and D8).

    Attributes:
        invited: The profile numbers the run was given.
        signed_up: Those of them that signed up.
        attended: Those of the sign-ups that attended.
    """

    invited: tuple[int, ...]
    signed_up: tuple[int, ...]
    attended: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SimulationCoefficients:
    """The numbers the rule is drawn against.

    There is no default: every caller supplies a set, and the only set the
    exercise itself ships is :data:`EXERCISE_SIMULATION_COEFFICIENTS`, the
    team's translation of Ann's words that Chau approved (wave-2 decision D7).
    Tests construct their own and label them test-only.

    What the requirements fix is the *ordering*, not the values, so the
    ordering is enforced here rather than left to whichever numbers arrive:
    ``true_fit_lift`` must exceed both ``frequent_attender_lift`` ("only a
    little more likely") and ``same_major_lift`` ("only a small lift").

    Attributes:
        base_signup_rate: The sign-up chance of a profile with no lift at all.
            A sixth quantity the register row did not name: the rule cannot
            express "more likely" without something to be more likely than.
        true_fit_lift: Added when the event's topics match the profile's hidden
            true interests and its career goal fits — halved when only one of
            the two holds.
        frequent_attender_lift: Added for a profile that attended at least
            ``frequent_attender_events`` past events.
        same_major_lift: Added for a profile in one of the event's target
            majors.
        mass_email_notice: The chance a profile notices the usual mass email.
            Everyone gets it (Ann Wang, email 2026-10-10, Q2).
        cbach_email_notice: The chance a profile notices the personal CBACH
            email. Only the team's listed profiles get it.
        attend_given_signup: The chance that a profile that signed up attends.
        frequent_attender_events: How many past events count as "many". A
            seventh quantity the register row did not name: the requirements
            say "attended many past events" without saying how many, and
            inventing a threshold here would be inventing a coefficient.
        true_interest_share_of_fit: How much of ``true_fit_lift`` a
            true-interest overlap earns; the career goal earns the rest. An
            eighth quantity the register row did not name. It decides whether Ann's
            "true interests and career goal" leans on interests or on goals,
            and it is also the ceiling on the lift a profile with no career
            goal on file can reach — which is a consequence of the split, not a
            penalty for the unknown (ADR-0011).
    """

    base_signup_rate: float
    true_fit_lift: float
    frequent_attender_lift: float
    same_major_lift: float
    mass_email_notice: float
    cbach_email_notice: float
    attend_given_signup: float
    frequent_attender_events: int
    true_interest_share_of_fit: float
    #: Ann's rule (2026-10-15 Q1): ``frequent_attender_lift`` for EACH past
    #: event, up to this cap. ``None`` means no per-event rule: the flat
    #: ``frequent_attender_lift`` once ``frequent_attender_events`` is reached.
    past_event_lift_cap: float | None = None

    def __post_init__(self) -> None:
        """Refuse a set that is not usable, before any result is drawn."""
        for name in (
            "base_signup_rate",
            "true_fit_lift",
            "frequent_attender_lift",
            "same_major_lift",
            "mass_email_notice",
            "cbach_email_notice",
            "attend_given_signup",
            "true_interest_share_of_fit",
        ):
            _check_unit_interval(name, getattr(self, name))
        _check_attender_threshold(self.frequent_attender_events)
        if self.past_event_lift_cap is not None:
            _check_unit_interval("past_event_lift_cap", self.past_event_lift_cap)
        if not self.true_fit_lift > self.frequent_attender_lift:
            raise SimulationCoefficientsError(
                "true_fit_lift must be greater than frequent_attender_lift: the "
                "requirements say a frequent attender is only a little more likely "
                f"to sign up. Got {self.true_fit_lift} and {self.frequent_attender_lift}."
            )
        if not self.true_fit_lift > self.same_major_lift:
            raise SimulationCoefficientsError(
                "true_fit_lift must be greater than same_major_lift: the "
                "requirements say same major alone gives only a small lift. "
                f"Got {self.true_fit_lift} and {self.same_major_lift}."
            )


def _check_unit_interval(name: str, value: object) -> None:
    """Refuse anything that is not a finite number within ``[0, 1]``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SimulationCoefficientsError(f"{name} must be a number; got {value!r}.")
    if not math.isfinite(value):
        raise SimulationCoefficientsError(
            f"{name} must be a finite number; got {value!r}. A rule drawn "
            "against a number that is not there has no result to report."
        )
    if not 0.0 <= value <= 1.0:
        raise SimulationCoefficientsError(f"{name} must be between 0 and 1 inclusive; got {value}.")


def _check_attender_threshold(value: object) -> None:
    """Refuse a "many past events" threshold that is not a positive count."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise SimulationCoefficientsError(
            f"frequent_attender_events must be a whole number; got {value!r}."
        )
    if value < 1:
        raise SimulationCoefficientsError(
            "frequent_attender_events must be at least 1; got "
            f"{value}. A profile that attended nothing is not a frequent attender."
        )


#: The coefficients the exercise runs with: Ann's a lot / some / a little /
#: some randomness, translated into numbers by the team and approved by Chau
#: (wave-2 decision D7, which closed OQ-CE-03). Ann Wang's email of 2026-10-10
#: (Q2, Q4) replaced the notice and show-up rates and removed the luck band:
#: 20 in 100 mass-email notice, 60 in 100 CBACH-email notice, 65 in 100 show up.
#: Ann answered in words on
#: 2026-09-25; each number and its reason is listed in this module's docstring,
#: and the plain-words paragraph at the top states every one of them. Read it
#: through :func:`require_coefficients`.
EXERCISE_SIMULATION_COEFFICIENTS: SimulationCoefficients | None = SimulationCoefficients(
    base_signup_rate=0.05,
    true_fit_lift=0.50,
    frequent_attender_lift=0.05,
    same_major_lift=0.05,
    mass_email_notice=0.20,
    cbach_email_notice=0.60,
    attend_given_signup=0.65,
    frequent_attender_events=1,
    true_interest_share_of_fit=0.7,
    past_event_lift_cap=0.15,
)


def require_coefficients() -> SimulationCoefficients:
    """Return the exercise's coefficients, or refuse in a plain sentence.

    Returns:
        :data:`EXERCISE_SIMULATION_COEFFICIENTS`, the approved set.

    Raises:
        CoefficientsNotConfirmedError: If the set is ever ``None``.
    """
    if EXERCISE_SIMULATION_COEFFICIENTS is None:
        # Only reachable if the approved set is removed. No register ID in the
        # sentence: the route passes this message to a team verbatim.
        raise CoefficientsNotConfirmedError("The results rule has no confirmed coefficients yet.")
    return EXERCISE_SIMULATION_COEFFICIENTS


def _uniform(seed: int, event_key: str, profile_no: int, purpose: str) -> float:
    """A stable uniform draw in ``[0, 1)`` for one profile and one purpose.

    Not :mod:`random` and not :mod:`secrets`: see this module's docstring. The
    digest is the whole of the state, so the draw depends on nothing but its
    four arguments — not on call order, not on the process.

    The top :data:`_UNIFORM_BITS` bits of the digest over ``2 ** 53``: every
    numerator is exactly representable, so the result is strictly below ``1.0``
    and the documented half-open interval is true. Dividing 64 bits by
    ``2 ** 64`` would round the largest digests to exactly ``1.0``, and a
    profile whose probability had been clamped to ``1.0`` would then fail to
    sign up.
    """
    digest = _digest(seed, event_key, profile_no, purpose)
    return (int.from_bytes(digest[:8], "big") >> (64 - _UNIFORM_BITS)) / 2.0**_UNIFORM_BITS


def _fit_share(
    profile: SimulationProfile,
    event: SimulationEvent,
    coefficients: SimulationCoefficients,
) -> float:
    """How much of the true-fit lift this profile earns, in ``[0, 1]``.

    Reads the hidden true interests and the hidden career goal — never what the
    app has on file. A missing career goal earns nothing and costs nothing; it
    simply cannot reach past ``coefficients.true_interest_share_of_fit``.
    """
    topics = {_normalized(tag) for tag in event.topic_tags}
    goal_share = 1.0 - coefficients.true_interest_share_of_fit
    share = 0.0
    if topics & {_normalized(term) for term in profile.true_interests}:
        share += coefficients.true_interest_share_of_fit
    if profile.career_goal is not None and _normalized(profile.career_goal) in topics:
        share += goal_share
    return share


def _sign_up_lift(
    profile: SimulationProfile,
    event: SimulationEvent,
    coefficients: SimulationCoefficients,
) -> float:
    """The lift above the base rate, before chance and before the clamp."""
    lift = coefficients.true_fit_lift * _fit_share(profile, event, coefficients)
    if profile.past_event_count >= coefficients.frequent_attender_events:
        cap = coefficients.past_event_lift_cap
        if cap is None:
            lift += coefficients.frequent_attender_lift
        else:
            lift += min(cap, coefficients.frequent_attender_lift * profile.past_event_count)
    if _normalized(profile.major) in {_normalized(major) for major in event.target_majors}:
        lift += coefficients.same_major_lift
    return lift


def _outcome(
    profile: SimulationProfile,
    event: SimulationEvent,
    seed: int,
    coefficients: SimulationCoefficients,
    *,
    on_list: bool,
) -> tuple[bool, bool]:
    """Whether one profile notices, signs up, and then attends.

    Every profile gets the mass email; a listed profile also gets the CBACH
    email. All draws are the team's fixed draws, so a profile's mass-alone
    outcome is the same with or without the list (the list only adds).
    """
    if profile.non_responding:
        return False, False

    def draw(purpose: str) -> float:
        return _uniform(seed, event.event_key, profile.profile_no, purpose)

    noticed = draw("mass_notice") < coefficients.mass_email_notice
    if on_list and draw("cbach_notice") < coefficients.cbach_email_notice:
        noticed = True
    if not noticed:
        return False, False
    probability = coefficients.base_signup_rate + _sign_up_lift(profile, event, coefficients)
    if draw("signup") >= min(1.0, max(0.0, probability)):
        return False, False
    return True, draw("attend") < coefficients.attend_given_signup


def _run(
    profiles: tuple[SimulationProfile, ...],
    event: SimulationEvent,
    seed: int,
    coefficients: SimulationCoefficients,
    *,
    on_list: bool,
) -> SimulationResult:
    """Apply the rule to every profile given and collect the three sets."""
    invited: set[int] = set()
    signed_up: set[int] = set()
    attended: set[int] = set()
    for profile in profiles:
        invited.add(profile.profile_no)
        signs_up, attends = _outcome(profile, event, seed, coefficients, on_list=on_list)
        if signs_up:
            signed_up.add(profile.profile_no)
        if attends:
            attended.add(profile.profile_no)
    return SimulationResult(
        invited=tuple(sorted(invited)),
        signed_up=tuple(sorted(signed_up)),
        attended=tuple(sorted(attended)),
    )


def simulate_results(
    profiles: tuple[SimulationProfile, ...],
    event: SimulationEvent,
    *,
    seed: int,
    coefficients: SimulationCoefficients,
    invite_limit: int,
) -> SimulationResult:
    """Turn one team's invited list into invited, signed up, and attended.

    The listed profiles get the mass email and the personal CBACH email.

    Args:
        profiles: The profiles the team invited. Order does not matter and
            repeats are folded into one profile number.
        event: The event they were invited to.
        seed: The team's seed. The only per-team state the rule reads.
        coefficients: A coefficient set. Required, never defaulted, so a test
            can isolate one lift and the shipped set is read in one place.
        invite_limit: The dataset's invite limit (30 by default, and that
            default lives on the dataset row, not here).

    Returns:
        A new :class:`SimulationResult`. Nothing is mutated.

    Raises:
        InviteLimitExceededError: If more distinct profiles were invited than
            the limit allows.
        ValueError: If ``invite_limit`` is negative.
    """
    if invite_limit < 0:
        raise ValueError(f"invite_limit must not be negative; got {invite_limit}.")
    distinct = {profile.profile_no for profile in profiles}
    if len(distinct) > invite_limit:
        raise InviteLimitExceededError(
            f"This list has {len(distinct)} profiles on it, and the invite limit "
            f"is {invite_limit}. Take some names off the list and run it again."
        )
    return _run(profiles, event, seed, coefficients, on_list=True)


def run_email_everyone(
    profiles: tuple[SimulationProfile, ...],
    event: SimulationEvent,
    *,
    seed: int,
    coefficients: SimulationCoefficients,
) -> SimulationResult:
    """The mass email alone over everybody: the baseline the list adds to.

    No invite limit applies and no CBACH email is drawn. The same seed is used
    as the team's own run, so every profile's mass-alone outcome is identical
    in both runs and the team's sign-ups are a superset of the baseline's for
    the same profiles (Ann Wang, email 2026-10-10, Q2).
    """
    return _run(profiles, event, seed, coefficients, on_list=False)


def existing_attended(seed: int, event_key: str, attend_rate: float) -> int:
    """How many of the 8 pre-registered students show up (Ann Wang 2026-10-15, Q2).

    Each attends at the same show-up rate as everyone else, from a fixed draw
    keyed by the team seed and event (profile numbers 1..8 stand for the 8), so
    the mass-only baseline and the team's run share it and a reload repeats it.
    """
    return sum(
        _uniform(seed, event_key, number, "existing_attend") < attend_rate
        for number in range(1, EXISTING_SIGNUPS + 1)
    )


def seats_empty(attended_count: int, existing_attended_count: int) -> int:
    """Seats still empty after a run, floored at zero.

    ``60 - (pre-registered students who came) - attended``, where the caller
    passes everyone else in the room: the mass email's show-ups plus the
    list's extra. Floored because a full room is a full room; a negative chair
    count would be a number nobody can act on.

    Raises:
        ValueError: If either count is negative.
    """
    if attended_count < 0 or existing_attended_count < 0:
        raise ValueError(
            f"counts must not be negative; got {attended_count} and {existing_attended_count}."
        )
    return max(0, EVENT_SEATS - existing_attended_count - attended_count)
