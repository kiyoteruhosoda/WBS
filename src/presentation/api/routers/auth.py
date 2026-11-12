"""SSO (OIDC) login flow.

The endpoints used by browser navigation (``/login`` and ``/callback``) return redirects, not
JSON. Failures also go back to the login screen, where the SPA shows the message (JSON errors
from the callback would look like nothing but raw text to the user).

An expired login is continued by the SPA opening ``/renew`` in a hidden frame, which asks the IdP with ``prompt=none``
(ADR-0071). It returns via ``/callback``, which checks the round trip's purpose (``renew``) and sends it to the result page ``/renewed``.
The refresh token endpoint (``/refresh``) no longer exists.
"""

from __future__ import annotations

import hmac
import logging
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from src.application.dto.auth_dto import StartedLoginDTO
from src.application.use_cases.authentication_use_cases import SsoLoginUseCases
from src.domain.entities.login_transaction import DEFAULT_LOGIN_TRANSACTION_TTL, LoginPurpose
from src.domain.exceptions import AccessDeniedError, AuthenticationError, ValidationError
from src.domain.value_objects.logout_notice import InvalidLogoutTokenError
from src.infrastructure.auth.auth_settings import AuthSettings
from src.presentation.api import renewal
from src.presentation.api.dependencies import (
    AuthSettingsDep,
    BackchannelLogoutDep,
    CurrentUserDep,
    SessionAuthDep,
    SsoLoginDep,
)
from src.presentation.api.schemas.auth_schemas import (
    AuthConfigResponse,
    CurrentUserResponse,
    LogoutResponse,
)
from src.presentation.api.session_cookies import clear_session_cookies, set_session_cookies
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_ENDPOINT_PATH = "/api/auth/login"
LOGIN_PAGE_PATH = "/login"

# Cookie that lives only for one authorization code flow round trip. It holds the issued state and is
# used only to check "is this callback a reply to a round trip this browser started".
# Named differently from the session cookie (so a name mix-up cannot mix lifetimes).
LOGIN_STATE_COOKIE = "sso_login_state"
LOGIN_STATE_COOKIE_MAX_AGE = int(DEFAULT_LOGIN_TRANSACTION_TTL.total_seconds())
# Logins may be started in several tabs at once, so remember the last few states.
# Keeping only one would let a later round trip lock out an earlier one.
LOGIN_STATE_COOKIE_CAPACITY = 3
# state is token_urlsafe (alphanumerics, `-`, `_`), so using this as a separator cannot collide with values.
LOGIN_STATE_SEPARATOR = "."
# Marker for when, on a silent round trip, the IdP replies "cannot proceed without a screen" (OIDC Core §3.1.2.6).
# **Not a failure** -- just show the normal login screen (ADR-0062).
SILENT_DECLINES = frozenset(
    {"login_required", "consent_required", "interaction_required", "account_selection_required"}
)
# Marker telling the SPA that a silent check found the user "not signed in". The SPA stops trying.
SILENT_DECLINED_FLAG = "sso_silent"


@router.get("/config", response_model=AuthConfigResponse, summary="Authentication configuration")
def get_auth_config(settings: AuthSettingsDep) -> AuthConfigResponse:
    """Tell the SPA whether to show the login screen (no auth required)."""
    if not settings.sso_enabled:
        return AuthConfigResponse(mode=settings.mode.value, sso_enabled=False)
    return AuthConfigResponse(
        mode=settings.mode.value,
        sso_enabled=True,
        provider_name=settings.provider_name,
        login_path=LOGIN_ENDPOINT_PATH,
    )


@router.get("/login", summary="Start SSO login", response_class=RedirectResponse)
def start_login(
    request: Request,
    settings: AuthSettingsDep,
    sso: SsoLoginDep,
    next_path: str | None = Query(default=None, alias="next"),
    silent: bool = False,
) -> RedirectResponse:
    """Send the user to the IdP's authorization endpoint.

    ``silent`` is the round trip that checks "already signed in at the IdP?" before the login screen renders
    (``prompt=none``. ADR-0062). If signed in, it continues along the same path as a normal login.

    ``next`` is the screen to return to after login. Values that could point outside are
    reduced to the default path by ``RedirectTarget`` (open redirect protection).

    The state is also put in a short-lived cookie. Requiring both to match at the callback
    means no browser other than the one that started this round trip can use up the callback.
    """
    started = sso.start_login(redirect_path=next_path, now=utcnow(), silent=silent)
    return _to_idp(request, settings, started)


@router.get("/renew", include_in_schema=False)
def start_renewal(
    request: Request, settings: AuthSettingsDep, sso: SsoLoginDep, session_auth: SessionAuthDep
) -> RedirectResponse:
    """Start the round trip that silently continues an expired login (ADR-0071). **The SPA opens it in a hidden frame.**

    Always ``prompt=none``. Reads "whose login, which login" from the expired access token still held and
    copies it into the round trip (taken over only when the same person comes back). 404 like ``/login`` in deployments without SSO.
    """
    now = utcnow()
    continued = session_auth.continuation_of(token=request.cookies.get(settings.cookie_name), now=now)
    try:
        started = sso.start_renewal(continued=continued, now=now)
    except AuthenticationError:
        logger.warning("could not start the renewal round trip", extra={"event": "auth.sso.renewal_failed"})
        return _renewal_result(renewal.RenewalResult.FAILED)
    return renewal.allow_same_origin_framing(_to_idp(request, settings, started))


@router.get("/renewed", include_in_schema=False)
def renewal_result() -> Response:
    """Result page of the renewal round trip (the SPA reads ``result`` from the frame's URL)."""
    return renewal.result_page()


@router.get("/callback", summary="SSO callback", response_class=RedirectResponse)
def complete_login(
    request: Request,
    settings: AuthSettingsDep,
    sso: SsoLoginDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    if state and sso.purpose_of(state) is LoginPurpose.RENEW:
        return _complete_renewal(request, settings, sso, code=code, state=state, error=error)
    if error in SILENT_DECLINES and state and _binding_matches(
        request.cookies.get(LOGIN_STATE_COOKIE), state
    ):
        redirect_path = sso.decline_silent_login(state=state, now=utcnow())
        if redirect_path is not None:
            # The silent check found the user not signed in at the IdP. Show the screen without an error (ADR-0062)
            return _silently_declined(redirect_path)
    if error:
        # The IdP returns an error here, e.g. when the user declined on the consent screen
        return _back_to_login(error, error_description)
    if not code or not state:
        return _back_to_login("invalid_request", "code and state are required")
    if not _binding_matches(request.cookies.get(LOGIN_STATE_COOKIE), state):
        # Not a round trip this browser started. Stops the trick where an attacker makes someone hit
        # the callback of the attacker's own login, connecting the victim's browser to the attacker's account.
        return _back_to_login("invalid_request", "This login did not start in this browser")

    try:
        completed = sso.complete_login(code=code, state=state, now=utcnow())
    except AuthenticationError as exc:
        return _back_to_login("authentication_failed", str(exc))
    except AccessDeniedError as exc:
        return _back_to_login("access_denied", str(exc))
    except ValidationError as exc:
        # Even if the IdP response is valid, we may not be able to accept it
        # (e.g. already linked to a different sub of the same issuer). Returning JSON here would
        # look like raw text to a user mid-navigation.
        return _back_to_login("access_denied", str(exc))

    response = RedirectResponse(completed.redirect_path, status_code=status.HTTP_302_FOUND)
    # Set the login cookie first (cleaning up the used temporary cookies comes after)
    set_session_cookies(response, settings, completed.session)
    _clear_login_state_cookie(response, settings)
    return response


@router.get("/me", response_model=CurrentUserResponse, summary="Current user")
def get_current_user_profile(current_user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        display_name=current_user.display_name,
        timezone=current_user.timezone,
        language=current_user.language,
        can_create_projects=current_user.can_create_projects,
    )


@router.post("/logout", response_model=LogoutResponse, summary="Sign out")
def logout(
    request: Request,
    response: Response,
    settings: AuthSettingsDep,
    session_auth: SessionAuthDep,
    sso: SsoLoginDep,
) -> LogoutResponse:
    """End only this login (other devices continue) and return the URL for also ending the IdP session.

    The redirect to the IdP is left to the SPA (returning a redirect to an XHR makes
    the browser follow it on its own, and the page navigates away before the response is read).
    """
    session_auth.revoke(token=request.cookies.get(settings.cookie_name), now=utcnow())
    clear_session_cookies(response, settings)
    return LogoutResponse(
        end_session_url=sso.end_session_url(
            post_logout_redirect_uri=settings.post_logout_redirect_uri
        )
    )


#: Upper limit for the received body. It only holds a single ``logout_token``, so this is ample.
LOGOUT_BODY_MAX_BYTES = 16 * 1024


@router.post("/backchannel-logout", include_in_schema=False)
async def receive_backchannel_logout(
    request: Request, use_case: BackchannelLogoutDep
) -> dict[str, str]:
    """Receive deactivation notices from the IdP (OpenID Connect Back-Channel Logout 1.0).

    ⚠ **This endpoint can be called unauthenticated.** The sender is proven only by the ``logout_token`` signature, so
    anything failing verification is rejected with 400 without a reason (do not reveal how far it got).

    ⚠ **Returns 404 in deployments without SSO** (there is nobody to verify the signature against). If this
    endpoint returns 404 in a deployment with SSO enabled, the routing is wrong -- the sender only logs
    404 as "undeliverable" and keeps resending, so it gets noticed late.

    Verification makes synchronous HTTP calls for discovery and JWKS, so the work is moved to the thread pool.
    """
    try:
        logout_token = _logout_token_of(await _bounded_body(request))
        await run_in_threadpool(use_case.execute, logout_token=logout_token, now=utcnow())
    except InvalidLogoutTokenError:
        # Deactivation notices come from the IdP, not the user. Returning 401 could read as
        # "authenticate again", so per the spec it is returned as "invalid request" (§2.8).
        logger.warning(
            "logout notice rejected",
            extra={"event": "auth.oidc.logout_rejected"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_logout_token"},
        ) from None
    # The response the spec requires. ⚠ **Must not be cached** (§2.8).
    return {"status": "ok"}


async def _bounded_body(request: Request) -> bytes:
    """Read the body. **Reject oversized ones without reading them** (the endpoint can be called unauthenticated)."""
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError("the logout_token body is too large")
    body = await request.body()
    if len(body) > LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError("the logout_token body is too large")
    return body


def _logout_token_of(body: bytes) -> str:
    """Extract a single field from ``application/x-www-form-urlencoded``.

    ⚠ **Do not use ``Form()``.** FastAPI's ``Form`` requires ``python-multipart``,
    which would add a dependency just for this one place.
    """
    try:
        fields = parse_qs(body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise InvalidLogoutTokenError("the logout_token body is not utf-8") from exc
    values = fields.get("logout_token") or []
    if len(values) != 1 or not values[0].strip():
        raise InvalidLogoutTokenError("the body must carry exactly one logout_token")
    return values[0].strip()


def _to_idp(request: Request, settings: AuthSettings, started: StartedLoginDTO) -> RedirectResponse:
    """Send to the IdP's authorization endpoint and put the state in a short-lived cookie."""
    # Without 302, some implementations turn the GET from the IdP into a POST
    response = RedirectResponse(started.authorization_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=LOGIN_STATE_COOKIE,
        value=_remember_binding(
            request.cookies.get(LOGIN_STATE_COOKIE), started.browser_binding
        ),
        max_age=LOGIN_STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        # It comes back via a top-level navigation from the IdP, so it only arrives with lax
        samesite=settings.cookie_samesite,
        path="/",
    )
    return response


def _complete_renewal(
    request: Request,
    settings: AuthSettings,
    sso: SsoLoginUseCases,
    *,
    code: str | None,
    state: str,
    error: str | None,
) -> RedirectResponse:
    """Return of the renewal round trip (ADR-0071). Sets the cookie and sends to the result page.

    "Not signed in" and "no consent" are not failures (we only tried silently).
    """
    if not _binding_matches(request.cookies.get(LOGIN_STATE_COOKIE), state):
        return _renewal_result(renewal.RenewalResult.FAILED)
    if error in SILENT_DECLINES and sso.decline_renewal(state=state, now=utcnow()):
        logger.info("not signed in at the IdP, not renewing", extra={"event": "auth.sso.renewal_declined"})
        return _renewal_result(renewal.RenewalResult.DECLINED, settings)
    if error or not code:
        logger.warning("renewal round trip broke", extra={"event": "auth.sso.renewal_failed"})
        return _renewal_result(renewal.RenewalResult.FAILED, settings)
    try:
        issued = sso.complete_renewal(code=code, state=state, now=utcnow())
    except (AuthenticationError, AccessDeniedError, ValidationError):
        logger.warning("renewal round trip broke", extra={"event": "auth.sso.renewal_failed"})
        return _renewal_result(renewal.RenewalResult.FAILED, settings)
    if issued is None:
        return _renewal_result(renewal.RenewalResult.DECLINED, settings)
    response = _renewal_result(renewal.RenewalResult.RENEWED, settings)
    set_session_cookies(response, settings, issued)
    logger.info("login renewed", extra={"event": "auth.sso.renewed"})
    return response


def _renewal_result(result: renewal.RenewalResult, settings: AuthSettings | None = None) -> RedirectResponse:
    """Send to the result page (dropping the used round-trip cookie and marking it frameable only by our own origin)."""
    response = RedirectResponse(renewal.result_location(result), status_code=status.HTTP_302_FOUND)
    if settings is not None:
        _clear_login_state_cookie(response, settings)
    return renewal.allow_same_origin_framing(response)


def _remember_binding(cookie_value: str | None, state: str) -> str:
    """Prepend the new state and let the oldest ones overflow."""
    previous = [v for v in (cookie_value or "").split(LOGIN_STATE_SEPARATOR) if v]
    remaining = [v for v in previous if v != state][: LOGIN_STATE_COOKIE_CAPACITY - 1]
    return LOGIN_STATE_SEPARATOR.join([state, *remaining])


def _binding_matches(cookie_value: str | None, state: str) -> bool:
    if not cookie_value:
        return False
    return any(
        hmac.compare_digest(candidate, state)
        for candidate in cookie_value.split(LOGIN_STATE_SEPARATOR)
        if candidate
    )


def _clear_login_state_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=LOGIN_STATE_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _back_to_login(error: str, description: str | None) -> RedirectResponse:
    params = {"error": error}
    if description:
        params["error_description"] = description
    return RedirectResponse(
        f"{LOGIN_PAGE_PATH}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )


def _silently_declined(redirect_path: str) -> RedirectResponse:
    """Keep the destination (``next``) -- so that after pressing the button the user returns to the screen they wanted."""
    params = {SILENT_DECLINED_FLAG: "1"}
    if redirect_path != "/":
        params["next"] = redirect_path
    return RedirectResponse(
        f"{LOGIN_PAGE_PATH}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )
