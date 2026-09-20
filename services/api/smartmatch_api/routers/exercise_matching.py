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
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.registry import (
    EXERCISE_APPROVED_SCORING_KEYS,
    EXERCISE_DEFAULT_WEIGHTS,
    InvalidExerciseWeightError,
    validate_exercise_weight_overrides,
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
from smartmatch_api.routers.exercise_matching_models import (
    CompareView,
    EventsView,
    EventView,
    RankableSet,
    RankedListView,
    SavedSettingsView,
    SaveSettingRequest,
    csv_download_filename,
    event_evidence,
    rankable_set,
    ranked_list_csv,
    ranked_list_view,
    saved_setting_view,
)

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


def _weight_query(label: str) -> Any:
    """One factor's weight, as an optional query parameter.

    Four parameters rather than one JSON blob, because a ranked list is a
    ``GET``: a body on a ``GET`` is not sent by every client and is not
    cacheable, and four named numbers are what a screen's four sliders produce.
    """
    return Query(
        default=None,
        ge=0.0,
        description=(
            f"The weight your team set for “{label}”. Leave every weight out to "
            "use the course's starting values."
        ),
    )


def _requested_weights(
    *,
    same_major: float | None,
    stated_interest_overlap: float | None,
    career_goal_fit: float | None,
    past_event_topic_overlap: float | None,
) -> Mapping[str, float] | None:
    """The weights a query string asked for, or ``None`` when it asked for none.

    Keyed by the rulebook's own factor keys, which is what the parameter names
    are — ``tests/unit/test_exercise_matching_router.py`` asserts the four names
    equal ``EXERCISE_APPROVED_SCORING_KEYS`` rather than trusting this list.
    """
    supplied = {
        "same_major": same_major,
        "stated_interest_overlap": stated_interest_overlap,
        "career_goal_fit": career_goal_fit,
        "past_event_topic_overlap": past_event_topic_overlap,
    }
    present = {key: value for key, value in supplied.items() if value is not None}
    return present or None


def _validated(raw: Mapping[str, object]) -> Mapping[str, float]:
    """Run a team's proposed weighting through the rulebook's own check.

    ``smartmatch_domain.weight_settings.validate_weight_overrides`` is the
    function design spec §6 names, and it cannot be used here: its admissible
    key set is the CBA four and its zero-total check resolves defaults through
    ``CBA_REGISTRY``, so it would refuse every exercise key and then read CBA
    defaults for the ones it accepted. ``exercise/registry.py`` says so at
    length and supplies :func:`validate_exercise_weight_overrides`, the minimal
    exercise equivalent written to the same rule — refuse, never repair, and
    name every offending field at once. Widening the shared function would be an
    edit to a G1-governed module this track is not authorised to make. Noted as
    a deviation on this track's pull request.
    """
    try:
        return validate_exercise_weight_overrides(raw)
    except InvalidExerciseWeightError as error:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_invalid",
            message=f"Those weights were not accepted. {error}",
        ) from None


def _effective_weights(overrides: Mapping[str, float] | None) -> Mapping[str, float]:
    """What a screen is told the list was built with.

    The placeholder defaults (OQ-CE-02) with the team's own values written over
    them, so a team that moved one slider sees four numbers rather than one.
    These are the *stated* weights and not the normalized ones: normalizing is
    the composition's business, and a normalized weight is an output (ADR-0025
    D8).
    """
    effective = dict(EXERCISE_DEFAULT_WEIGHTS)
    effective.update(overrides or {})
    return effective


def _event_or_refusal(events: Sequence[ExerciseEventRow], event_key: str) -> ExerciseEventRow:
    """The named event from this team's own data file, or one plain sentence.

    Looked up in the list already read for the topic lookup rather than by a
    second query, so an event key belonging to another data file cannot resolve:
    the only events in scope are this workspace's.
    """
    for event in events:
        if event.event_key == event_key:
            return event
    raise ExerciseError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="exercise_event_unknown",
        message="That event is not in your team's data file.",
    )


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
    return _validated(dict(stored.weights))


def _team_view(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    workspace: ExerciseWorkspace,
) -> tuple[tuple[ExerciseEventRow, ...], RankableSet]:
    """This team's events and its own view of the profiles, read once.

    Both reads are scoped to ``workspace.dataset_id`` and ``workspace.id``,
    which come from the cookie rather than from the request, so there is no
    argument here a caller could have supplied.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    profiles = team_view.list_team_profiles(
        session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
    )
    return events, rankable_set(profiles, events)


def _build_list(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    workspace: ExerciseWorkspace,
    event_key: str,
    overrides: Mapping[str, float] | None,
    setting_name: str | None,
) -> RankedListView:
    """One ranked list, its table and its notice.

    The ranking is ``exercise_ranked_list``'s — this function reads rows, hands
    them over, and renders what comes back. It re-implements no part of the
    order, the reason lines or the markers, and it composes the coverage notice
    through ``list_composition`` rather than deriving the same answer a second
    way.

    The tie-break's seed is the data file's checksum (design spec §4.4), so the
    fixed order is identical across requests, teams and processes.
    """
    events, rankable = _team_view(
        session, datasets=datasets, team_view=team_view, workspace=workspace
    )
    event = _event_or_refusal(events, event_key)
    summary = datasets.get_dataset_summary(session, dataset_id=workspace.dataset_id)
    if summary is None:  # pragma: no cover - the cookie resolved a workspace on it
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_dataset",
            message="The instructor has not loaded the student body yet.",
        )
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
        weights=_effective_weights(overrides),
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
) -> Mapping[str, float] | None:
    """Which weighting a list request asked for: a saved name, or typed numbers.

    Naming both is refused rather than resolved in somebody's favour: a screen
    that sent both has a bug, and silently preferring one would hide it behind a
    list that looks right.
    """
    if setting is not None and requested is not None:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_ambiguous",
            message="Choose saved settings or your own weights, not both.",
        )
    if setting is not None:
        return _saved_weights_or_refusal(
            session,
            repository,
            workspace=workspace,
            event_key=event_key,
            name=_setting_name_or_refusal(setting),
        )
    if requested is not None:
        return _validated(dict(requested))
    return None


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
    same_major: float | None = _weight_query("same major"),
    stated_interest_overlap: float | None = _weight_query("said they are interested in this topic"),
    career_goal_fit: float | None = _weight_query("career goal fits this event"),
    past_event_topic_overlap: float | None = _weight_query("went to similar events before"),
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

    Profiles whose row records no major or no year take no place on a list and
    are reported as a count instead: the major is the one thing every profile
    can be matched on and the order reads the year.

    Raises:
        ExerciseError: 401 without a workspace cookie, 404 for an event or a
            saved setting this team does not have, 422 for a weight the
            rulebook refuses or for naming a setting and a weight at once.
    """
    overrides = _overrides_for(
        session,
        settings,
        workspace=workspace,
        event_key=event_key,
        setting=setting,
        requested=_requested_weights(
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
        event_key=event_key,
        overrides=overrides,
        setting_name=setting,
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
    same_major: float | None = _weight_query("same major"),
    stated_interest_overlap: float | None = _weight_query("said they are interested in this topic"),
    career_goal_fit: float | None = _weight_query("career goal fits this event"),
    past_event_topic_overlap: float | None = _weight_query("went to similar events before"),
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
    overrides = _overrides_for(
        session,
        settings,
        workspace=workspace,
        event_key=event_key,
        setting=setting,
        requested=_requested_weights(
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
        event_key=event_key,
        overrides=overrides,
        setting_name=setting,
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

    Raises:
        ExerciseError: 401 without a workspace cookie, 404 for an event or a
            saved setting this team does not have.
    """
    lists = [
        _build_list(
            session,
            datasets=datasets,
            team_view=team_view,
            workspace=workspace,
            event_key=event_key,
            overrides=_saved_weights_or_refusal(
                session,
                settings,
                workspace=workspace,
                event_key=event_key,
                name=_setting_name_or_refusal(name),
            ),
            setting_name=name.strip(),
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
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
) -> SavedSettingsView:
    """What this team has saved for this event, oldest first.

    Another team's settings are not filtered out of this answer; they are never
    selected, because the workspace comes from the cookie and is part of the
    statement.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace.
    """
    stored = settings.list_settings(session, workspace_id=workspace.id, event_key=event_key)
    return SavedSettingsView(
        event_key=event_key,
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
    weights = _validated(dict(payload.weights))
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = _event_or_refusal(events, event_key)
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
        session=session, workspace=workspace, settings=settings, event_key=event.event_key
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
    settings: SettingsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    name: str = Path(description="The name your team saved."),
) -> SavedSettingsView:
    """Remove one saved weighting and answer with what is left.

    Returns the remaining settings rather than an empty body, so a screen that
    has just freed a slot does not have to ask again to find out.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 404 for a name this team has not
            saved, 409 for a refused write.
    """
    usable_name = _setting_name_or_refusal(name)
    try:
        removed = settings.delete_setting(
            session,
            dataset_id=workspace.dataset_id,
            workspace_id=workspace.id,
            event_key=event_key,
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
        session=session, workspace=workspace, settings=settings, event_key=event_key
    )


#: Re-exported so a test can assert the four weight parameters are the
#: rulebook's own keys rather than four names somebody typed.
EXERCISE_WEIGHT_PARAMETER_KEYS = frozenset(EXERCISE_APPROVED_SCORING_KEYS)
