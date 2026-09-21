"""The matching screen's routes (design spec §4–§8, ADR-0025 D4/D6/D8).

A team picks an event, moves four weights that are written in plain words, and
reads a ranked list with a reason beside every name, a table saying who is on
it, and a download. It may keep three named weightings per event and put two of
them side by side. That is the whole of this module.

Every route is addressed by the workspace cookie
================================================

There is **no team number, dataset id, or workspace id in any path, query or
body here.** A team acts on its own workspace and on its own data file, both
resolved from the ``exercise_workspace`` cookie by
``exercise_dependencies.get_current_workspace``. A client that could name a
workspace could name another team's, and in a product whose whole identity is
"somebody typed 4 on a classroom laptop" that is not a permission check anybody
could write — so the identifier is never accepted in the first place.

The paths therefore differ from design spec §6, which writes
``/v1/exercise/workspaces/{token}/events/...``. They are
``/v1/exercise/workspaces/current/...``, matching the merged workspace router's
``GET /v1/exercise/workspaces/current``: the cookie is the token, and a token in
a URL is a token in a browser history, a referrer header and a projector.

What is not here
================

* **Results** — the lock, the one-run rule, the comparison panels and the
  simulated-results rule of design spec §9–§13. They are the results track's,
  and nothing in this module reads
  ``ExerciseDatasetRepository.load_simulation_profiles``, which is the sole
  reader of the withheld column (ADR-0025 D6).
* **A frontend.** CE-MOUNT builds the screens; this module answers them.
* **Rate limiting** (OQ-CE-06, owner Danny), for the reason the workspace
  router states: the repository limiter needs a principal or
  ``smartmatch_persistence``, and an exercise router may have neither. What
  bounds these routes meanwhile is that every read is capped at one data file's
  three hundred rows and every write at three named settings per event.

ADR-0025 D6, and why the docstrings are part of it
==================================================

FastAPI publishes a handler's docstring as its operation description, so a
docstring is a response field with extra steps. No docstring in this module, no
``Field`` description, no error sentence and no log line names
``hidden_true_interests`` or any value of it, and
``tests/unit/test_exercise_matching_router.py`` walks the models, the handlers'
docstrings and the whole exercise-scope OpenAPI document to say so.

ADR-0025 D8
===========

``rank`` and the counts are integers, and neither ranks a person by a number a
screen could read as a score. The only other number in any response is the
weighting the team itself set — echoed back as the team stated it, never as the
composition normalized it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import APIRouter, Depends, Path, Query, Response, status
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.registry import (
    EXERCISE_APPROVED_SCORING_KEYS,
)

from smartmatch_api.exercise_dependencies import (
    MAX_SAVED_SETTINGS_PER_EVENT,
    CurrentWorkspace,
    DatasetRepository,
    ExerciseEventRow,
    ExerciseSession,
    ExerciseSettingsWriteRefused,
    ExerciseWorkspace,
    SettingsRepository,
    TeamViewRepository,
    TooManySavedSettingsError,
    require_exercise_request_header,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching_csv import (
    csv_download_filename,
    ranked_list_csv,
)
from smartmatch_api.routers.exercise_matching_models import (
    CompareView,
    EventsView,
    EventView,
    RankedListView,
    SavedSettingsView,
    SaveSettingRequest,
    event_evidence,
    event_or_refusal,
    rankable_set,
    ranked_list_view,
    saved_setting_view,
)
from smartmatch_api.routers.exercise_matching_weights import (
    effective_weights,
    requested_weights,
    validated,
    weight_query,
)

#: What this module offers, declared where a reader looks for it rather than
#: seven hundred lines down.
#:
#: ``event_or_refusal`` is **re-exported**: it lives in
#: ``exercise_matching_models`` now, beside ``event_evidence`` and
#: ``rankable_set``, because that is where the results track reaches it from and
#: a router importing a router for one helper is an edge that grows (review
#: round 1, F8). The name here is the same object, so this module's own callers
#: and anything that imported it from here keep working.
__all__ = ["EXERCISE_WEIGHT_PARAMETER_KEYS", "event_or_refusal", "router"]

#: A bare assignment, not an annotated one, for ``exercise_public.router``'s
#: reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads
#: router prefixes out of the AST and matches ``name = APIRouter(...)``.
router = APIRouter(prefix="/v1/exercise/workspaces/current", tags=["class-exercise"])

#: Applied to every state-changing route in this module. Passed as a
#: ``dependencies`` entry rather than as a handler parameter so it cannot be
#: dropped by editing a signature.
_STATE_CHANGING = [Depends(require_exercise_request_header)]

#: The longest a saved setting's name may be, from
#: ``ck_exercise_saved_setting_name_shape`` in migration ``0037``. Restated here
#: so the refusal can be a sentence rather than a constraint violation; the
#: constraint remains the thing that cannot be bypassed.
_MAX_SETTING_NAME_CHARACTERS = 100

#: A name the settings routes will not store, because the compare route already
#: answers on it. Refusing it is cheaper than a path that means two things.
_RESERVED_SETTING_NAME = "compare"


def _setting_name_or_refusal(name: str) -> str:
    """A saved setting's name, trimmed and bounded, or one plain sentence."""
    trimmed = name.strip()
    if not trimmed or len(trimmed) > _MAX_SETTING_NAME_CHARACTERS:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_setting_name_unusable",
            message="Give your settings a short name.",
        )
    if trimmed == _RESERVED_SETTING_NAME:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_setting_name_reserved",
            message="Pick another name for your settings.",
        )
    return trimmed


def _saved_weights_or_refusal(
    session: ExerciseSession,
    repository: SettingsRepository,
    *,
    workspace: ExerciseWorkspace,
    event_key: str,
    name: str,
) -> Mapping[str, float]:
    """One of this team's saved weightings by name, or one plain sentence.

    Re-validated on the way out rather than trusted because it was validated on
    the way in: the rulebook is a value object and a later version of it could
    name different factors, at which point a stored weighting is input again.
    """
    stored = repository.get_setting(
        session, workspace_id=workspace.id, event_key=event_key, name=name
    )
    if stored is None:
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_setting_unknown",
            message="Your team has no saved settings with that name.",
        )
    return validated(dict(stored.weights))


def _build_list(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    workspace: ExerciseWorkspace,
    event_key: str,
    overrides: Mapping[str, float] | None,
    setting_name: str | None,
    events: Sequence[ExerciseEventRow] | None = None,
) -> RankedListView:
    """One ranked list, its table and its notice.

    The ranking is ``exercise_ranked_list``'s — this function reads rows, hands
    them over, and renders what comes back. It re-implements no part of the
    order, the reason lines or the markers, and it composes the coverage notice
    through ``list_composition`` rather than deriving the same answer a second
    way.

    The tie-break's seed is the data file's checksum (design spec §4.4), so the
    fixed order is identical across requests, teams and processes.

    **The event is resolved before the profiles are read** (review round 1). The
    events of one data file are a dozen rows and the profiles are three hundred
    joined to an overlay; reading the larger one first meant an unknown event
    key — the cheapest thing for a client to send, and the one an unauthenticated
    route will be sent most — cost that join before the 404. The order of these
    three statements is therefore load-bearing rather than tidy.

    Both reads are scoped to ``workspace.dataset_id`` and ``workspace.id``, which
    come from the cookie rather than from the request, so there is no argument
    here a caller could have supplied.

    ``events`` lets a caller that has **already** read and resolved them hand
    that list over (review round 2, F2). The two list routes must resolve the
    event before they look a named setting up, so that an unknown event key is
    refused as one; passing the list they resolved it from keeps that fix at one
    ``list_events`` per request rather than two. The resolution still happens
    here, against the same rows, so no caller can skip it.
    """
    if events is None:
        events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    summary = datasets.get_dataset_summary(session, dataset_id=workspace.dataset_id)
    if summary is None:  # pragma: no cover - the cookie resolved a workspace on it
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_dataset",
            message="The instructor has not loaded the student body yet.",
        )
    profiles = team_view.list_team_profiles(
        session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
    )
    rankable = rankable_set(profiles, events)
    ranked = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=overrides,
        invite_limit=summary.invite_limit,
        year_rank=rankable.year_rank,
        dataset_checksum=summary.checksum,
    )
    return ranked_list_view(
        ranked,
        rankable,
        event=event,
        weights=effective_weights(overrides),
        setting_name=setting_name,
    )


def _overrides_for(
    session: ExerciseSession,
    repository: SettingsRepository,
    *,
    workspace: ExerciseWorkspace,
    event_key: str,
    setting: str | None,
    requested: Mapping[str, float] | None,
) -> tuple[Mapping[str, float] | None, str | None]:
    """Which weighting a list request asked for, and the name to report for it.

    Naming both a saved setting and a weight is refused rather than resolved in
    somebody's favour: a screen that sent both has a bug, and silently
    preferring one would hide it behind a list that looks right.

    Returns the **trimmed** name beside the weights (review round 1). The lookup
    already trims, so echoing the raw query value handed back a name that is not
    the name the row is stored under — ``"  broad "`` would come back with its
    spaces, and a client comparing the echo with what it sent to its saved-list
    would see two different settings.
    """
    if setting is not None and requested is not None:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_ambiguous",
            message="Choose saved settings or your own weights, not both.",
        )
    if setting is not None:
        name = _setting_name_or_refusal(setting)
        return (
            _saved_weights_or_refusal(
                session,
                repository,
                workspace=workspace,
                event_key=event_key,
                name=name,
            ),
            name,
        )
    if requested is not None:
        return validated(dict(requested)), None
    return None, None


# ---------------------------------------------------------------------------
# The event picker
# ---------------------------------------------------------------------------


@router.get(
    "/events",
    response_model=EventsView,
    summary="The events in your team's data file",
)
def read_events(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
) -> EventsView:
    """Every event in the data file this team is working in, in file order.

    Ten past events, which a profile may have attended, then the two the teams
    run. ``is_exercise_event`` is what tells them apart, so a picker can offer
    the rounds without this route deciding which of them is which.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    return EventsView(
        events=[
            EventView(
                event_key=event.event_key,
                name=event.name,
                topic_tags=list(event.topic_tags),
                target_majors=list(event.target_majors),
                is_exercise_event=event.is_exercise_event,
                sequence=event.sequence,
            )
            for event in events
        ]
    )


# ---------------------------------------------------------------------------
# The ranked list
# ---------------------------------------------------------------------------


@router.get(
    "/events/{event_key}/list",
    response_model=RankedListView,
    summary="The ranked list for one event, with who is on it",
)
def read_ranked_list(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    setting: str | None = Query(
        default=None,
        description="The name of one of your team's saved settings to build the list with.",
    ),
    same_major: float | None = weight_query("same major"),
    stated_interest_overlap: float | None = weight_query("said they are interested in this topic"),
    career_goal_fit: float | None = weight_query("career goal fits this event"),
    past_event_topic_overlap: float | None = weight_query("went to similar events before"),
) -> RankedListView:
    """The names for one event, in order, cut at the data file's invite limit.

    Each name carries its rank, the marker saying how much is on file about it
    under **this team's** view, one sentence saying why it is there, and the
    keys of the factors that counted. No number that ranks a person appears
    (ADR-0025 D8).

    The same response carries design spec §7's table: counts by major, by class
    year and by how much is on file, each beside the same count over the whole
    data file, plus the notice naming any major or year that exists in the file
    and has nobody on this list.

    The weights come from one of three places: a saved setting named by
    ``setting``, the four weight parameters, or — with neither given — the
    course's starting values, which are a placeholder the course owner has not
    yet replaced. Naming both a setting and a weight is refused.

    **The event is resolved before ``setting`` is looked up** (review round 2,
    F2). Resolving the name first answered an unknown event key plus an unknown
    setting with ``exercise_setting_unknown``, while every other route in this
    module answered the same key with ``exercise_event_unknown``. The resolved
    list is handed to ``_build_list`` so the fix costs no second read.

    Profiles whose row records no major or no year take no place on a list and
    are reported as a count instead: the major is the one thing every profile
    can be matched on and the order reads the year.

    Raises:
        ExerciseError: 401 without a workspace cookie, 404 for an event or a
            saved setting this team does not have, 422 for a weight the
            rulebook refuses or for naming a setting and a weight at once.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    overrides, setting_name = _overrides_for(
        session,
        settings,
        workspace=workspace,
        event_key=event.event_key,
        setting=setting,
        requested=requested_weights(
            same_major=same_major,
            stated_interest_overlap=stated_interest_overlap,
            career_goal_fit=career_goal_fit,
            past_event_topic_overlap=past_event_topic_overlap,
        ),
    )
    return _build_list(
        session,
        datasets=datasets,
        team_view=team_view,
        workspace=workspace,
        event_key=event.event_key,
        overrides=overrides,
        setting_name=setting_name,
        events=events,
    )


@router.get(
    "/events/{event_key}/list.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The list as a CSV file."}},
    summary="Download the ranked list for one event",
)
def download_ranked_list(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    setting: str | None = Query(
        default=None,
        description="The name of one of your team's saved settings to build the list with.",
    ),
    same_major: float | None = weight_query("same major"),
    stated_interest_overlap: float | None = weight_query("said they are interested in this topic"),
    career_goal_fit: float | None = weight_query("career goal fits this event"),
    past_event_topic_overlap: float | None = weight_query("went to similar events before"),
) -> Response:
    """Design spec §8: rank, name, major, year, marker and reason, as a CSV file.

    The same list the route above returns, built from the same weights by the
    same call, so the file and the screen cannot disagree. Written with
    ``csv.writer`` into an in-memory buffer — never to disk, never through
    pandas — and every cell that begins with a character a spreadsheet reads as
    the start of a formula is prefixed so that it is shown rather than run. The
    names and majors in it come out of a file somebody uploaded, and the point
    of a download is that it is opened in a spreadsheet.

    The filename is built from the event key alone.

    Raises:
        ExerciseError: as the route above.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    overrides, setting_name = _overrides_for(
        session,
        settings,
        workspace=workspace,
        event_key=event.event_key,
        setting=setting,
        requested=requested_weights(
            same_major=same_major,
            stated_interest_overlap=stated_interest_overlap,
            career_goal_fit=career_goal_fit,
            past_event_topic_overlap=past_event_topic_overlap,
        ),
    )
    view = _build_list(
        session,
        datasets=datasets,
        team_view=team_view,
        workspace=workspace,
        event_key=event.event_key,
        overrides=overrides,
        setting_name=setting_name,
        events=events,
    )
    return Response(
        content=ranked_list_csv(view),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{csv_download_filename(event_key)}"'
        },
    )


# ---------------------------------------------------------------------------
# Saved settings (design spec §6)
# ---------------------------------------------------------------------------


@router.get(
    "/events/{event_key}/settings/compare",
    response_model=CompareView,
    summary="Two saved settings side by side",
)
def compare_settings(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    a: str = Query(description="The name of one of your team's saved settings."),
    b: str = Query(description="The name of another of your team's saved settings."),
) -> CompareView:
    """Both lists, and the profile numbers that appear on both.

    Declared before the named-settings routes so the word ``compare`` cannot be
    read as a setting's name; the save route refuses that name for the same
    reason.

    The overlap is returned in the first list's order, so a screen highlighting
    it walks one list rather than sorting a set.

    **The event is resolved first** (review round 1), before either name is
    looked up, so that every route in this module answers an event key from
    another data file the same way. Resolving the names first made this one
    route report "no saved settings with that name" for a request whose real
    problem was the event — a refusal that sends a reader looking in the wrong
    place, and two saved-setting lookups spent on a key that was never going to
    resolve.

    Raises:
        ExerciseError: 401 without a workspace cookie, 404 for an event or a
            saved setting this team does not have.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    lists = [
        _build_list(
            session,
            datasets=datasets,
            team_view=team_view,
            workspace=workspace,
            event_key=event.event_key,
            overrides=_saved_weights_or_refusal(
                session,
                settings,
                workspace=workspace,
                event_key=event.event_key,
                name=_setting_name_or_refusal(name),
            ),
            setting_name=_setting_name_or_refusal(name),
        )
        for name in (a, b)
    ]
    first, second = lists
    on_second = {entry.profile_no for entry in second.entries}
    return CompareView(
        a=first,
        b=second,
        on_both_profile_nos=[
            entry.profile_no for entry in first.entries if entry.profile_no in on_second
        ],
    )


@router.get(
    "/events/{event_key}/settings",
    response_model=SavedSettingsView,
    summary="Your team's saved settings for one event",
)
def read_settings(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
) -> SavedSettingsView:
    """What this team has saved for this event, oldest first.

    Another team's settings are not filtered out of this answer; they are never
    selected, because the workspace comes from the cookie and is part of the
    statement.

    **The event is resolved against this team's own data file** (review round 1).
    Without it this route echoed back whatever key was in the path — a key from
    another data file, or a key from no file at all — beside an empty list, and
    a screen reading ``event_key`` off the response could not tell "no settings
    yet" from "that event does not exist here". The save route always checked;
    the two reads did not, and inconsistency between routes on the same resource
    is how the unchecked one gets trusted.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace, 404
            for an event that is not in this team's data file.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    stored = settings.list_settings(session, workspace_id=workspace.id, event_key=event.event_key)
    return SavedSettingsView(
        event_key=event.event_key,
        settings=[saved_setting_view(setting) for setting in stored],
        max_settings=MAX_SAVED_SETTINGS_PER_EVENT,
    )


@router.put(
    "/events/{event_key}/settings/{name}",
    response_model=SavedSettingsView,
    dependencies=_STATE_CHANGING,
    summary="Save four weights under a name",
)
def save_setting(
    payload: SaveSettingRequest,
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    name: str = Path(description="What your team wants to call this weighting."),
) -> SavedSettingsView:
    """Store this team's four weights for this event under a name.

    Design spec §6: a team may keep three names per event. Saving over a name it
    already has is always allowed and changes no count; a **fourth new name** is
    refused with one sentence. The count is taken under a lock in the repository
    rather than here, because two saves arriving together would otherwise both
    read three and both insert.

    The event must be one in this team's own data file, so a name cannot be
    hung on an event the team is not working in.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 404 for an unknown event, 409 for a
            fourth new name or a refused write, 422 for an unusable name or a
            weight the rulebook refuses.
    """
    usable_name = _setting_name_or_refusal(name)
    weights = validated(dict(payload.weights))
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    try:
        settings.save_setting(
            session,
            dataset_id=workspace.dataset_id,
            workspace_id=workspace.id,
            event_key=event.event_key,
            name=usable_name,
            weights=weights,
        )
    except TooManySavedSettingsError as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_too_many_settings",
            message=str(error),
        ) from None
    except ExerciseSettingsWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_settings_write_refused",
            message=str(error),
        ) from None
    session.commit()
    return read_settings(
        session=session,
        workspace=workspace,
        datasets=datasets,
        settings=settings,
        event_key=event.event_key,
    )


@router.delete(
    "/events/{event_key}/settings/{name}",
    response_model=SavedSettingsView,
    dependencies=_STATE_CHANGING,
    summary="Delete one of your team's saved settings",
)
def delete_setting(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    name: str = Path(description="The name your team saved."),
) -> SavedSettingsView:
    """Remove one saved weighting and answer with what is left.

    Returns the remaining settings rather than an empty body, so a screen that
    has just freed a slot does not have to ask again to find out.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 404 for an unknown event or a name
            this team has not saved, 409 for a refused write.
    """
    usable_name = _setting_name_or_refusal(name)
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    try:
        removed = settings.delete_setting(
            session,
            dataset_id=workspace.dataset_id,
            workspace_id=workspace.id,
            event_key=event.event_key,
            name=usable_name,
        )
    except ExerciseSettingsWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_settings_write_refused",
            message=str(error),
        ) from None
    if not removed:
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_setting_unknown",
            message="Your team has no saved settings with that name.",
        )
    session.commit()
    return read_settings(
        session=session,
        workspace=workspace,
        datasets=datasets,
        settings=settings,
        event_key=event.event_key,
    )


#: Re-exported so a test can assert the four weight parameters are the
#: rulebook's own keys rather than four names somebody typed.
EXERCISE_WEIGHT_PARAMETER_KEYS = frozenset(EXERCISE_APPROVED_SCORING_KEYS)
