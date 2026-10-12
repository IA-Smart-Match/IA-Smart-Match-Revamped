# DB exception surface survey (B-11 evidence)

2026-10-09. Refs #308, `docs/architecture/decisions/adr-backlog.md` B-11. Evidence only; no decision is recorded here.

Method: grep of `str(exc|error)` and `{exc|error}` interpolations in `services/` and `python/` (non-test), then read the `except` clause above each hit to see which exception class is rendered. Paths shown from the repo root; line numbers are at origin/main `122b01b0`. Rows group lines that share a clause.

Classes: **sanitized** (domain-raised, message built in code), **logged-only** (class name or code only), **leaks** (a driver exception can render, including PostgreSQL `DETAIL`), **needs check** (not resolved in this pass; reason given).

| path:line | what renders | destination | classification | note |
|---|---|---|---|---|
| `services/api/smartmatch_api/errors.py:132` | ConsentViolationError str(exc) | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/errors.py:142` | InvalidTransitionError str(exc) | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/errors.py:187` | IdempotencyConflictError str(exc) | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/exercise_seed.py:269,272` | type(error).__name__ and refusal code only | log | logged-only | class name only, never message |
| `services/api/smartmatch_api/exercise_seed.py:322` | ExerciseDatasetWriteError str to stderr | log (stderr) | sanitized | repository scrubs driver text before raising (instructor/dataset repos) |
| `services/api/smartmatch_api/routers/cba_contacts.py:785,791,797` | UnknownNaicsSector / UnknownCbaRoleCategory / ValueError | response | sanitized | domain; ValueError traced: the try wraps only `SpeakerContactDraft.create` in `_draft_or_400` (pure domain, no ORM call) |
| `services/api/smartmatch_api/routers/cba_contacts.py:1385,1391,1397` | same three as above | response | sanitized | same note |
| `services/api/smartmatch_api/routers/cba_handoff.py:454,460,466` | CbaAttendanceMismatch / PipelineStageOrder / ConflictingOwningUnit | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/cba_invitations.py:1114` | OutreachCompositionError | response | sanitized | values server-built; pragma no cover |
| `services/api/smartmatch_api/routers/cba_invitations.py:1493` | InvitationResponseConflict | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/cba_contact_channels.py:625,773` | ConsentViolationError | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/outreach.py:468,684` | ConsentViolationError interpolated | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/outreach.py:476` | OutreachCompositionError | response | sanitized | jinja/format error text; template values, not DB |
| `services/api/smartmatch_api/routers/outreach_contacts.py:913` | ConsentViolationError | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/pipeline.py:484,490` | PipelineStageOrder / InvalidPipelineStageTransition | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/redrive.py:317` | IdempotencyConflictError helper (see errors.py:187) | response | sanitized | no except site in this function; caller passes a domain error |
| `services/api/smartmatch_api/routers/rewards.py:1095` | ValueError | response | needs check | ValueError source not traced to confirm no SQL/driver call inside the try |
| `services/api/smartmatch_api/routers/speaker_requests.py:549,555,561,569` | UnknownNaics / UnknownRole / SpeakerRequestError / ValueError | response | sanitized | domain; ValueError as cba_contacts note |
| `services/api/smartmatch_api/routers/speaker_self.py:330` | InvitationResponseConflict | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/speaker_portal.py:689` | PasswordPolicyError | response | sanitized | policy text only |
| `services/api/smartmatch_api/routers/attendance.py:433` | ConflictingOwningUnitError | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/meetings.py:400` | repository refusal for unresolved time | response | sanitized | fixed domain message (docstring) |
| `services/api/smartmatch_api/routers/manual_events.py:513` | EventNotPublishableError | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/match_runs.py:828` | RegistryNotApproved/NotReady | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/match_runs.py:1240` | ValueError scoring stored evidence | response | needs check | message built from stored JSON; confirm no stored row values echoed |
| `services/api/smartmatch_api/routers/match_runs.py:1483,1498` | ValueError reading stored explanations/availability | response | needs check | parse errors may echo stored content (pydantic/JSON text), not driver text |
| `services/api/smartmatch_api/routers/matching_weights.py:424,443` | InvalidWeightOverride / StaleWeightSettings | response | sanitized | domain-raised, message built in code; no driver text |
| `services/api/smartmatch_api/routers/exercise_matching.py:700,706,757` | TooManySavedSettings / ExerciseSettingsWriteRefused | response | sanitized | repository raises refusal types after scrubbing |
| `services/api/smartmatch_api/routers/exercise_matching_weights.py:198` | InvalidExerciseWeightError via capped() | response | sanitized | domain, length-capped |
| `services/api/smartmatch_api/routers/exercise_results_run.py:146,329,394` | CoefficientsNotConfirmed / InviteLimitExceeded / ExerciseResultsWriteRefused | response | sanitized | refusal types |
| `services/api/smartmatch_api/routers/exercise_instructor_refresh.py:253` | ExerciseResultsWriteRefused | response | sanitized | refusal type |
| `services/api/smartmatch_api/routers/exercise_instructor.py:236,242,291,342,505,609` | ExerciseDatasetLabelError / DatasetWriteError / ExerciseWriteRefused | response | sanitized | instructor_repository scrubs driver exceptions into these (cited in its docstring) |
| `services/api/smartmatch_api/routers/manual_events.py:346-352,451-456; host_organizations.py:541-550; speaker_portal.py:348-352; speaker_portal_activation.py:379-381` | Haiku pre-survey candidates | response | needs check | not re-opened line by line in this pass; no str(exc) of a bare Exception found by grep at these lines |
| `python/smartmatch_persistence/.../exercise/workspace_repository.py:508-530` | reset_team lets driver exception propagate (docstring) | response/log via caller | leaks | docstring admits it: PG DETAIL 'Failing row contains (...)' not covered by hide_parameters; sole caller instructor_repository.py:586-600 Module-level leak; scrubbed by sole caller instructor_repository.py:589-597, so no response leak. |
| `python/smartmatch_persistence/.../exercise/instructor_repository.py:586-600` | caller of reset_team | response | sanitized | 589-597 catch SQLAlchemyError and raise ExerciseWriteRefused via _failure_for; the driver exception never escapes (its docstring says so) |
| `services/worker/smartmatch_worker/execution.py:310` | HandlerFailure str(exc) into job event detail | event | sanitized | handler-raised, message built in code |
| `services/worker/smartmatch_worker/execution.py:327` | except Exception: type + str(exc) into job event detail | event | leaks | unclassified exception can be a SQLAlchemy DBAPIError; hide_parameters hides values, DETAIL line still renders |
| `services/worker/smartmatch_worker/dispatcher.py:779` | TaskQueueError str(exc) to failure record | event | needs check | TaskQueueError is a provider error; confirm it never wraps a driver error |
| `services/worker/smartmatch_worker/dispatcher.py:784,905` | except Exception: type+str(exc) to failure record | event | leaks | same as execution.py:327 |
| `services/worker/smartmatch_worker/outreach.py:468,472` | ConsentViolationError at delivery | event | sanitized | domain-raised, message built in code; no driver text |
| `services/worker/smartmatch_worker/outreach.py:504,508` | except Exception around email provider: type+str(exc) | event | needs check | provider error text; could include a recipient address, not DB |
| `services/worker/smartmatch_worker/paid_extraction.py:487` | SyntheticProviderTimeout | event | sanitized | synthetic |
| `services/worker/smartmatch_worker/paid_extraction.py:496` | except Exception from paid call | event | needs check | provider error text; DB use inside the try not checked |
| `services/worker/smartmatch_worker/handlers.py:743,1034,1097,1154,1173,1275` | ColumnContract / ValueError / UnknownScoringMode / UnknownRegistryVersion / RegistryNotApproved | event | sanitized | validation problems built in code; 1034 ValueError text not traced |
| `services/worker/smartmatch_worker/main.py:900` | TaskIdentityUnconfigured | log | sanitized | config error |
| `services/worker/smartmatch_worker/config.py:179; column_contract.py:163,168` | ValueError / OSError / YAMLError on config files | log | sanitized | file and env parsing, no DB |
| `python/smartmatch_persistence/.../engine.py:55-70,107` | _int_from_env ValueError echoes raw env value via {raw!r} | log (startup) | needs check | env pool-size values, not secrets in practice; B-11 gap 3 |
| `python/smartmatch_persistence/ (logger calls with exc/err)` | grep for logger.* with exc/err args | log | sanitized | zero hits |

## Counts

| classification | rows |
|---|---|
| sanitized | 36 |
| logged-only | 1 |
| leaks | 3 |
| needs check | 8 |
| total | 48 |

## The three known gaps (from B-11)

1. PostgreSQL `DETAIL: Failing row contains (...)` for a CHECK or NOT NULL refusal is outside `hide_parameters`.
2. Engines built outside the factory (`smartmatch_persistence.engine`) would not carry `hide_parameters=True`. The only `create_engine(` in non-test code is `engine.py:233`; test and script engines were not surveyed.
3. `engine.py` `_int_from_env` echoes the raw env value in its `ValueError` (`{raw!r}`).

## What would make this an invariant

A unit test that fails when a router or worker module renders `str(exc)` of a bare `Exception` or `SQLAlchemyError` into a response body, log line or job event, plus a fixture-level check that no `create_engine(` exists outside `engine.py`. Recommendation only; no code in this PR.
