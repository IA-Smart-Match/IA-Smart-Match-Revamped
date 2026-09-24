"""Speaker portal accounts: invite, revoke, access, and activation (B26 T6b-1).

Mounted only under ``Capability.SPEAKER_PORTAL``, which is **off in every
scope** until its turn-on rule clears (T6b-5 merged and parent plan §10 rows 1,
2 and 4). Three routers, each a bare module-level assignment:

``router``
    The Speaker Connector's three routes under
    ``/v1/units/{unit_id}/speaker-contacts/{professional_id}``: invite, revoke
    the live invitation, and read the portal-access status. Roles
    ``{admin, coordinator}`` — never ``speaker``.
``public_router``
    ``POST /v1/speaker-portal/activate``: the JSON activation, which issues a
    session. No principal: the person has no credential until it succeeds.
``pages_router``
    ``GET``/``POST /s/{token}``: the no-JS page the invitation links to. The
    POST activates and issues no session (C4).

The token (plan §4): ``HMAC-SHA256(secret, "speaker-portal:v1:" + id)``, stored
only as its SHA-256 and rendered only by the worker at send. Every activation
refusal is one status, code and body. The token is never echoed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.consent import ConsentSource, ContactState, is_send_eligible
from smartmatch_domain.outreach import (
    OUTREACH_SEND_COMMAND_TYPE,
    DraftRecipient,
    DraftStatus,
    compose_draft,
)
from smartmatch_domain.speaker_portal import (
    ACTIVATION_URL_SENTINEL,
    INVITATION_TTL,
    INVITE_TEMPLATE_ID,
    PasswordPolicyError,
    PortalAccessStatus,
    check_new_password,
    derive_status,
    derive_token,
    token_hash,
)
from smartmatch_persistence.contacts import ContactChannelRepository, ContactChannelRow
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_persistence.pilot_auth import LoginAttemptLimiter
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.speaker_portal import SpeakerPortalRepository
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smartmatch_api.commands import submit_command
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.routers.auth import LoginResponse
from smartmatch_api.speaker_portal_activation import (
    ActivationCredentialsInvalid,
    ActivationMode,
    ActivationModeMismatch,
    ActivationRefused,
    activate,
    page_mode,
)
from smartmatch_api.token_pages import FormRead, FormReadOutcome, read_urlencoded_form, token_page
from smartmatch_api.units import OrgUnitRow, load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-portal"])
public_router = APIRouter(tags=["speaker-portal"])
pages_router = APIRouter(tags=["speaker-portal"])

_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()
_channels: Final[ContactChannelRepository] = ContactChannelRepository()
_outreach: Final[OutreachRepository] = OutreachRepository()

#: The Speaker Connector persona. ``speaker`` is never here: a Speaker does not
#: invite themself.
_SPEAKER_PORTAL_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

INVITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_portal.invite", max_requests=20, window=timedelta(minutes=1)
)
READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_portal.read", max_requests=120, window=timedelta(minutes=1)
)
#: Pre-authentication, keyed by caller address with its own prefix so it never
#: shares ``/v1/auth/login``'s counter (the table keys on ``caller_key`` alone).
ACTIVATION_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_portal.activate", max_requests=10, window=timedelta(minutes=5)
)
_ACTIVATION_KEY_PREFIX: Final[str] = "speaker_portal.activate:"

#: R9: two 256-character ASCII passwords, fully percent-encoded, plus field
#: names come to 1567 bytes.
_FORM_MAX_BYTES: Final[int] = 2048
_FORM_MAX_FIELDS: Final[int] = 4


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


def _authorize_speaker_portal(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> OrgUnitRow:
    """Load the unit and authorize a Speaker Connector against that row's path.

    The ``_authorize_speaker_contacts`` shape: the unit is loaded in the
    caller's own tenant (another tenant's unit is a 404), then the policy runs
    against the loaded row's path with :data:`_SPEAKER_PORTAL_ROLES`.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_PORTAL_ROLES,
    )
    return unit


def _token_secret(request: Request) -> str:
    """The secret ``main.py`` put on ``app.state`` at boot (plan §4.2)."""
    secret: str | None = getattr(request.app.state, "speaker_portal_token_secret", None)
    if not secret:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="speaker_portal_unavailable",
            message="The Speaker portal is not configured on this deployment.",
        )
    return secret


def _contact_not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="speaker_contact_not_found",
        message="No such speaker contact in this unit.",
    )


# ---------------------------------------------------------------------------
# Invite, revoke, access
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    """Which of the contact's email channels the link is sent to."""

    model_config = ConfigDict(extra="forbid")

    contact_channel_id: uuid.UUID


class InviteResponse(BaseModel):
    """The invitation is recorded and its send is queued; nothing has been sent."""

    invitation_id: uuid.UUID
    status: Literal["invited"]
    expires_at: datetime
    job_id: uuid.UUID
    events_url: str


class RevokeResponse(BaseModel):
    revoked: bool = Field(description="`false` when nothing was live. Idempotent.")


class PortalAccessResponse(BaseModel):
    """One contact's portal status, as a Speaker Connector sees it (plan L4)."""

    model_config = ConfigDict(json_schema_extra={"additionalProperties": False})

    status: PortalAccessStatus
    contact_channel_id: uuid.UUID | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    bound_at: datetime | None = None


def _eligible_channel(
    channel: ContactChannelRow | None, *, professional_id: uuid.UUID, unit_id: uuid.UUID
) -> ContactChannelRow:
    if (
        channel is None
        or channel.professional_id != professional_id
        or channel.owning_unit_id != unit_id
        or channel.channel_kind != "email"
        or not is_send_eligible(
            ContactState(channel.contact_state),
            consent_source=(
                ConsentSource(channel.consent_source) if channel.consent_source else None
            ),
            suppressed=channel.suppressed,
        )
    ):
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="speaker_portal_channel_not_eligible",
            message="That address cannot be emailed. Choose an address this Speaker agreed to.",
        )
    return channel


def _is_live_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_speaker_portal_invitation_live"


@router.post(
    "/{unit_id}/speaker-contacts/{professional_id}/portal-invitations",
    response_model=InviteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Invite a speaker contact to the Speaker Portal",
)
def invite_to_portal(
    principal: CurrentPrincipal,
    session: DbSession,
    request: Request,
    body: InviteRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> InviteResponse:
    """Record an invitation and queue its email. **Nothing is sent when this returns.**

    Order (plan §3.2): quota, authorize, lock the profile (the first lock), refuse
    a bound profile, check the channel, revoke any live invitation, insert the
    new one, compose the draft with the link placeholder, and submit the send.
    ``submit_command`` commits all of it as one transaction.
    """
    charge = charge_quota(session, principal, INVITE_RATE_LIMIT)
    unit = _authorize_speaker_portal(session, principal, unit_id)
    secret = _token_secret(request)
    now = utc_now()

    profile = _portal.lock_profile(
        session,
        tenant_id=principal.tenant_id,
        professional_id=professional_id,
        owning_unit_id=unit.id,
    )
    if profile is None:
        raise _contact_not_found()
    if profile.account_user_id is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_portal_already_active",
            message="This Speaker already has portal access.",
        )
    channel = _eligible_channel(
        _channels.get(
            session, tenant_id=principal.tenant_id, contact_channel_id=body.contact_channel_id
        ),
        professional_id=professional_id,
        unit_id=unit.id,
    )

    _portal.revoke_live(
        session, tenant_id=principal.tenant_id, professional_id=professional_id, revoked_at=now
    )
    invitation_id = uuid.uuid4()
    expires_at = now + INVITATION_TTL
    try:
        _portal.insert_invitation(
            session,
            invitation_id=invitation_id,
            tenant_id=principal.tenant_id,
            professional_id=professional_id,
            contact_channel_id=channel.id,
            issued_by_user_id=principal.user_id,
            token_hash=token_hash(derive_token(secret, invitation_id)),
            issued_at=now,
            expires_at=expires_at,
        )
    except IntegrityError as exc:
        if _is_live_conflict(exc):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="speaker_portal_invitation_conflict",
                message="Another invitation was just sent. Refresh and try again.",
            ) from exc
        raise

    composed = compose_draft(
        recipient=DraftRecipient(
            address=channel.address,
            contact_state=ContactState(channel.contact_state),
            consent_source=ConsentSource(channel.consent_source)
            if channel.consent_source
            else None,
            suppressed=channel.suppressed,
        ),
        template_id=INVITE_TEMPLATE_ID,
        values={
            "professional_name": profile.full_name,
            "unit_name": unit.display_name,
            "expires_on": f"{expires_at.day} {expires_at:%B %Y}",
            "activation_url": ACTIVATION_URL_SENTINEL,
        },
    )
    draft_id = _outreach.create_draft(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit.id,
        contact_channel_id=channel.id,
        template_id=composed.template_id,
        content_status=composed.content_status.value,
        subject=composed.subject,
        body=composed.body,
        created_by=principal.user_id,
        status=DraftStatus.APPROVED.value,
        approved_by=principal.user_id,
        approved_at=now,
    )
    accepted = submit_command(
        session,
        principal,
        command_type=OUTREACH_SEND_COMMAND_TYPE,
        owning_unit_id=unit.id,
        payload={"draft_id": str(draft_id), "speaker_portal_invitation_id": str(invitation_id)},
        idempotency_key=f"speaker-portal-invitation:{invitation_id}",
        charge=charge,
    )
    return InviteResponse(
        invitation_id=invitation_id,
        status="invited",
        expires_at=expires_at,
        job_id=accepted.job_id,
        events_url=f"/v1/jobs/{accepted.job_id}/events",
    )


@router.delete(
    "/{unit_id}/speaker-contacts/{professional_id}/portal-invitations/current",
    response_model=RevokeResponse,
    summary="Revoke a speaker contact's live portal invitation",
)
def revoke_portal_invitation(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> RevokeResponse:
    """Revoke the live invitation, if any. Idempotent: ``revoked: false`` when none."""
    charge_quota(session, principal, INVITE_RATE_LIMIT)
    unit = _authorize_speaker_portal(session, principal, unit_id)
    now = utc_now()
    profile = _portal.lock_profile(
        session,
        tenant_id=principal.tenant_id,
        professional_id=professional_id,
        owning_unit_id=unit.id,
    )
    if profile is None:
        raise _contact_not_found()
    revoked = _portal.revoke_live(
        session, tenant_id=principal.tenant_id, professional_id=professional_id, revoked_at=now
    )
    session.commit()
    return RevokeResponse(revoked=revoked)


@router.get(
    "/{unit_id}/speaker-contacts/{professional_id}/portal-access",
    response_model=PortalAccessResponse,
    response_model_exclude_none=True,
    summary="Read a speaker contact's portal-access status",
)
def read_portal_access(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> PortalAccessResponse:
    """``none``, ``invited``, ``expired`` or ``active``. Never the token or its hash."""
    charge_quota(session, principal, READ_RATE_LIMIT)
    unit = _authorize_speaker_portal(session, principal, unit_id)
    now = utc_now()
    profile = _portal.lock_profile(
        session,
        tenant_id=principal.tenant_id,
        professional_id=professional_id,
        owning_unit_id=unit.id,
        lock=False,
    )
    if profile is None:
        raise _contact_not_found()
    live = _portal.current_for_profile(
        session, tenant_id=principal.tenant_id, professional_id=professional_id
    )
    access = derive_status(
        account_bound=profile.account_user_id is not None,
        live_expires_at=None if live is None else live.expires_at,
        now=now,
    )
    if access is PortalAccessStatus.ACTIVE:
        return PortalAccessResponse(status=access, bound_at=profile.account_bound_at)
    if live is None:
        return PortalAccessResponse(status=access)
    return PortalAccessResponse(
        status=access,
        contact_channel_id=live.contact_channel_id,
        issued_at=live.issued_at,
        expires_at=live.expires_at,
    )


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


class ActivateRequest(BaseModel):
    """The token from the link, and **exactly one** password (B26 T6b-5 §4.1).

    ``new_password`` when no login holds the invited address (the Speaker's
    first password); ``existing_password`` when an Event Host's login holds it
    (that login's password). Which one is expected is decided server-side,
    under the locks; sending the other is ``409
    speaker_portal_activation_mode_mismatch``.
    """

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=128)
    #: The 1024 bound only limits parsing; the policy limit is 256.
    new_password: str | None = Field(default=None, min_length=1, max_length=1024)
    existing_password: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def _exactly_one_password(self) -> ActivateRequest:
        if (self.new_password is None) == (self.existing_password is None):
            raise ValueError("send exactly one of new_password and existing_password")
        return self


def _activation_caller_key(request: Request) -> str:
    """The client address, as ``/v1/auth/login`` reads it (plan §3.2)."""
    client = request.client
    return client.host if client is not None and client.host else "client-address-unavailable"


def _charge_activation_attempt(request: Request, session: Session) -> None:
    """Charge one attempt to this caller's own activation bucket, and commit it."""
    decision = LoginAttemptLimiter().check(
        session,
        limit=ACTIVATION_RATE_LIMIT,
        caller_key=_ACTIVATION_KEY_PREFIX + _activation_caller_key(request),
        now=utc_now(),
    )
    if not decision.allowed:
        retry_seconds = max(1, int(decision.retry_after.total_seconds()))
        raise ApiError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message=f"Too many activation attempts. Retry in {retry_seconds} seconds.",
            headers={
                "Retry-After": str(retry_seconds),
                "X-RateLimit-Limit": str(ACTIVATION_RATE_LIMIT.max_requests),
                "X-RateLimit-Remaining": "0",
            },
        )
    session.commit()


def _invalid_invitation() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="speaker_portal_invitation_invalid",
        message="This link is not valid. Ask the person who invited you for a new one.",
    )


def _credentials_invalid() -> ApiError:
    """Existing-login mode, wrong password: the login route's 401 shape."""
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="speaker_portal_credentials_invalid",
        message="That password does not match. Use the password you sign in to SmartMatch with.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _field_for(mode: ActivationMode) -> str:
    return "existing_password" if mode is ActivationMode.EXISTING_LOGIN else "new_password"


def _mode_mismatch(expected: ActivationMode) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="speaker_portal_activation_mode_mismatch",
        message=(
            "This address already signs in to SmartMatch. Enter that password instead."
            if expected is ActivationMode.EXISTING_LOGIN
            else "Choose a new password for your Speaker Portal account."
        ),
        details={"expected": _field_for(expected)},
    )


@public_router.post(
    "/v1/speaker-portal/activate",
    response_model=LoginResponse,
    summary="Activate a Speaker Portal login from an invitation link",
    responses={
        400: {"description": "`speaker_portal_invitation_invalid`: every refusal, identically"},
        401: {"description": "`speaker_portal_credentials_invalid`: wrong existing password"},
        409: {"description": "`speaker_portal_activation_mode_mismatch`: send the other field"},
        422: {"description": "`password_too_weak` or `invalid_request`"},
        429: {"description": "`rate_limited`"},
    },
)
def activate_speaker_portal(
    request: Request, session: DbSession, body: ActivateRequest
) -> LoginResponse:
    """Bind the Speaker to a login, grant ``speaker``, and issue a session for that login.

    New login: sets the Speaker's first password. Existing login (T6b-5): an
    Event Host's login proves itself with its password and gains ``speaker``;
    the session is that login's. Every other refusal is ``400
    speaker_portal_invitation_invalid``, identically. A new password's policy is
    checked before the token (``422 password_too_weak``), so it says nothing
    about the token. Every attempt, including a wrong existing password, is
    charged to the activation limiter first.
    """
    _charge_activation_attempt(request, session)
    if body.new_password is not None:
        try:
            check_new_password(body.new_password)
        except PasswordPolicyError as exc:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="password_too_weak",
                message=str(exc),
            ) from exc
    secret = _token_secret(request)
    try:
        result = activate(
            session,
            token=body.token,
            new_password=body.new_password,
            existing_password=body.existing_password,
            secret=secret,
            now=utc_now(),
            issue_session=True,
        )
    except ActivationRefused as exc:
        raise _invalid_invitation() from exc
    except ActivationCredentialsInvalid as exc:
        raise _credentials_invalid() from exc
    except ActivationModeMismatch as exc:
        raise _mode_mismatch(exc.expected) from exc
    session.commit()
    issued = result.session
    assert issued is not None
    return LoginResponse(
        access_token=issued.token,
        token_type="bearer",
        expires_at=issued.expires_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# /s/{token}: the no-JS page
# ---------------------------------------------------------------------------

_PAGE_TITLE: Final[str] = "Speaker Portal"

#: T6b-1's page, byte for byte: every token that is not a live, verified
#: existing-login invitation gets exactly this (T6b-5 C1).
_FORM_HTML: Final[str] = (
    '<p id="s-help">Choose a password for your Speaker Portal account: 12 to 256 '
    "characters. This link works once. A very long password in a non-Latin script "
    "may be too large for this form; use a shorter one if the page says so.</p>"
    # No `action`: the form posts back to the URL the Speaker already holds, so
    # the token is never written into the HTML.
    '<form method="post" aria-describedby="s-help">'
    '<p><label for="s-new">New password</label> '
    '<input id="s-new" name="new_password" type="password" autocomplete="new-password" '
    'minlength="12" maxlength="256" required></p>'
    '<p><label for="s-confirm">Confirm password</label> '
    '<input id="s-confirm" name="confirm_password" type="password" '
    'autocomplete="new-password" minlength="12" maxlength="256" required></p>'
    '<button type="submit">Create my account</button>'
    "</form>"
)

#: T6b-5: a live invitation to an address an Event Host's login already holds.
#: Only someone holding the live 256-bit token can see this page.
_EXISTING_FORM_HTML: Final[str] = (
    '<p id="s-help">This email address already signs in to SmartMatch. Enter that '
    "password to add your Speaker access. This link works once.</p>"
    '<form method="post" aria-describedby="s-help">'
    '<p><label for="s-existing">SmartMatch password</label> '
    '<input id="s-existing" name="existing_password" type="password" '
    'autocomplete="current-password" maxlength="1024" required></p>'
    '<button type="submit">Add Speaker access</button>'
    "</form>"
)

_NEW_HEADING: Final[str] = "Set up your Speaker Portal account"
_EXISTING_HEADING: Final[str] = "Add Speaker access to your SmartMatch login"


def _page(heading: str, body_html: str, status_code: int) -> HTMLResponse:
    return token_page(_PAGE_TITLE, heading, body_html, status_code=status_code)


def _invalid_page() -> HTMLResponse:
    return _page(
        "This link is not valid",
        "<p>It may have expired or already been used. Ask the person who invited "
        "you for a new link.</p>",
        status.HTTP_400_BAD_REQUEST,
    )


def _form_page(mode: ActivationMode, status_code: int, notice: str = "") -> HTMLResponse:
    """The form ``mode`` needs, with an optional alert above it."""
    alert = f'<p role="alert">{notice}</p>' if notice else ""
    if mode is ActivationMode.EXISTING_LOGIN:
        return _page(_EXISTING_HEADING, alert + _EXISTING_FORM_HTML, status_code)
    return _page(_NEW_HEADING, alert + _FORM_HTML, status_code)


@pages_router.get(
    "/s/{token}",
    summary="Speaker Portal activation page",
    responses={200: {"content": {"text/html": {}}, "description": "Activation page"}},
)
def activation_page(request: Request, session: DbSession, token: str) -> HTMLResponse:
    """The password form the invitation needs. **Never changes state**: reads only,
    no lock, no rate-limit charge, and never echoes the token.

    Every token gets T6b-1's new-password form, byte for byte, except a live,
    verified invitation whose address an Event Host's login already holds: that
    one asks for the existing password (T6b-5 §4.2, C1)."""
    secret: str | None = getattr(request.app.state, "speaker_portal_token_secret", None)
    mode = page_mode(session, token=token, secret=secret, now=utc_now()) if secret else None
    return _form_page(mode or ActivationMode.NEW_LOGIN, status.HTTP_200_OK)


async def _read_activation_form(request: Request) -> FormRead:
    return await read_urlencoded_form(
        request, max_bytes=_FORM_MAX_BYTES, max_fields=_FORM_MAX_FIELDS
    )


def _bad_form() -> HTMLResponse:
    return _page(
        "Please use the form",
        "<p>Open the link from your email again and fill in the form.</p>",
        status.HTTP_400_BAD_REQUEST,
    )


@pages_router.post(
    "/s/{token}",
    summary="Activate a Speaker Portal login from the page's form",
    responses={200: {"content": {"text/html": {}}, "description": "Result page"}},
)
def activate_by_form(
    request: Request,
    session: DbSession,
    token: str,
    form: Annotated[FormRead, Depends(_read_activation_form)],
) -> HTMLResponse:
    """Activate from the form, and issue **no session** (C4): the page links to
    ``/login``. Accepts ``new_password`` + ``confirm_password``, or
    ``existing_password`` (T6b-5). Refusals: 413 (body too large), 422 (weak or
    mismatched new password), 401 (wrong existing password: the existing form
    again), 409 (the other mode: that form), 400 (every invalid token,
    identical bytes, or a malformed form)."""
    _charge_activation_attempt(request, session)
    if form.outcome is FormReadOutcome.TOO_LARGE:
        return _page(
            "That was too long",
            "<p>Choose a shorter password and try again.</p>",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if form.outcome is not FormReadOutcome.OK:
        return _bad_form()
    new_values = form.fields.get("new_password", ())
    confirm_values = form.fields.get("confirm_password", ())
    existing_values = form.fields.get("existing_password", ())
    new_password: str | None = None
    existing_password: str | None = None
    if len(existing_values) == 1 and not new_values and not confirm_values:
        existing_password = existing_values[0]
    elif len(new_values) == 1 and len(confirm_values) == 1 and not existing_values:
        new_password = new_values[0]
        try:
            check_new_password(new_password)
        except PasswordPolicyError:
            return _page(
                "Choose a different password",
                "<p>Use 12 to 256 characters, not only spaces. Go back and try again.</p>",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if new_password != confirm_values[0]:
            return _page(
                "The passwords do not match",
                "<p>Go back and type the same password in both fields.</p>",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
    else:
        return _bad_form()
    secret = _token_secret(request)
    try:
        result = activate(
            session,
            token=token,
            new_password=new_password,
            existing_password=existing_password,
            secret=secret,
            now=utc_now(),
            issue_session=False,
        )
    except ActivationRefused:
        session.rollback()
        return _invalid_page()
    except ActivationCredentialsInvalid:
        session.rollback()
        return _form_page(
            ActivationMode.EXISTING_LOGIN,
            status.HTTP_401_UNAUTHORIZED,
            "That password does not match.",
        )
    except ActivationModeMismatch as exc:
        session.rollback()
        return _form_page(exc.expected, status.HTTP_409_CONFLICT)
    session.commit()
    if result.mode is ActivationMode.EXISTING_LOGIN:
        return _page(
            "Speaker access is added",
            "<p>Speaker access is added to your SmartMatch login. "
            '<a href="/login">Sign in</a>, or reload SmartMatch if you are already '
            "signed in, then use Switch portal.</p>",
            status.HTTP_200_OK,
        )
    return _page(
        "Your Speaker account is ready",
        '<p>You can now <a href="/login">sign in</a> with your email address and '
        "the password you chose.</p>",
        status.HTTP_200_OK,
    )
