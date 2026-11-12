"""The SSO login flow.

Splits the OIDC authorization code flow (with PKCE) into two use cases.

- ``SsoLoginUseCases``          — round trips with the IdP (start, callback, IdP-side logout)
- ``SessionAuthenticationUseCases`` — resolves the user from an issued session

They are split so that per-request authentication does not need the IdP. After login,
every request only needs our own token, so work can continue even while the IdP is down.

⚠ **Access token verification does not hit the DB.** The decision to stop someone is concentrated in one point: the round trip that continues an expired login
(the IdP's login state and whether the user is deactivated; ADR-0071). Refresh tokens are no longer issued.

Protocol details (discovery, JWKS, signature verification) live behind ``IdentityProvider``.
This only knows "whom to let in", "whom to create", and "how to start and end a session".
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from src.application.dto.auth_dto import (
    AuthenticatedUserDTO,
    CompletedLoginDTO,
    IssuedSessionDTO,
    StartedLoginDTO,
)
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import SecretGenerator
from src.application.ports.session_tokens import SessionTokens
from src.domain.entities.login_transaction import (
    DEFAULT_LOGIN_TRANSACTION_TTL,
    LoginPurpose,
    LoginTransaction,
)
from src.domain.entities.refresh_session import RefreshSession, new_identifier
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import AccessDeniedError, AuthenticationError, NotFoundError
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.continued_sign_in import ContinuedSignIn
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.domain.value_objects.redirect_target import RedirectTarget

logger = logging.getLogger(__name__)


class SessionAuthenticationUseCases:
    """Resolve the user from our own token, reissue it, and end a login (ADR-0069, ADR-0071)."""

    def __init__(
        self,
        *,
        users: UserAccountRepository,
        sessions: RefreshSessionRepository,
        tokens: SessionTokens,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens

    def authenticate(self, *, token: str | None, now: datetime) -> AuthenticatedUserDTO:
        """⚠ **Does not hit the DB.** Deactivated users and deleted login records are not detected here.
        They are detected when an expired login is continued, so the upper bound until then is the access token lifetime.

        ⚠ **This leniency is acceptable only because the continuation round trip (:meth:`SsoLoginUseCases.complete_renewal`)
        tightens it with the IdP and the DB** (ADR-0071).
        """
        contents = self._tokens.read_access(token, now=now) if token else None
        if contents is None:
            raise AuthenticationError("Not authenticated")
        return contents.user

    def reissue_access(self, *, token: str | None, now: datetime) -> str | None:
        """Reissue the access token with new values right after the user changed their settings.

        ⚠ **This path issues a new token, so it hits the DB.** Otherwise a stopped person, even after the continuation round trip is refused,
        could stay signed in just by repeatedly saving settings.
        """
        contents = self._tokens.read_access(token, now=now) if token else None
        if contents is None or self._sessions.find(contents.session_id) is None:
            return None
        user = self._users.find_by_id(contents.user.user_id)
        if user is None or not user.is_active:
            return None
        return self._tokens.access_token(_to_dto(user), session_id=contents.session_id, now=now)

    def continuation_of(self, *, token: str | None, now: datetime) -> ContinuedSignIn | None:
        """Read the login to continue from a leftover (possibly expired) access token (ADR-0071). ⚠ Not authentication."""
        return self._tokens.continuation_of(token, now=now) if token else None

    def revoke(self, *, token: str | None, now: datetime) -> None:
        """End only this login (other devices continue). Does nothing for an unreadable token.

        Reads the access token even if expired, as long as it is within the login record retention (ADR-0071; the logout ticket no longer exists).
        """
        continued = self.continuation_of(token=token, now=now)
        if continued is None:
            return
        session = self._sessions.find(continued.session_id)
        if session is not None and session.user_id == continued.user_id:
            self._sessions.delete(session.id)


class MachineReaderAuthenticationUseCases:
    """The user when another app's server comes to read/write on the user's behalf (ADR-0056; same shape as Scheduler's ADR-0056).

    Acceptance conditions (401 if any one fails):

    - Signature, ``typ``, issuer, audience (``MACHINE_AUDIENCE``), expiry (``IdentityProvider.verify_machine_token``)
    - ``sub_type`` is **present** (a machine token; a human login token does not pass)
    - ``client_id`` belongs to the machine of an app allowed to read (``MACHINE_READER_CLIENT_IDS``)

    The user is looked up by the ``(iss, sub)`` the caller passes. ⚠ **Users are not created here either.** 404 if there is no link
    (the caller shows "please sign in to WBS once"). 403 for a deactivated user.
    Closed when both the audience and the allowlist are empty (default).
    """

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        users: UserAccountRepository,
        audience: str,
        accepted_client_ids: frozenset[str],
    ) -> None:
        self._idp = identity_provider
        self._users = users
        self._audience = audience
        self._accepted_client_ids = accepted_client_ids

    def authenticate(self, *, token: str, issuer: str, subject: str) -> AuthenticatedUserDTO:
        if not self._audience or not self._accepted_client_ids:
            raise AuthenticationError("Machine readers are not accepted by this deployment")
        claims = self._idp.verify_machine_token(token, audience=self._audience)
        if "sub_type" not in claims:
            # A human login token (even with a matching audience) does not pass through this endpoint
            raise AuthenticationError("Only machine tokens are accepted here")
        client_id = str(claims.get("client_id") or "")
        if client_id not in self._accepted_client_ids:
            raise AuthenticationError("Machine token was issued to an application not accepted here")
        if issuer != self._idp.federated_issuer or not subject.strip():
            raise NotFoundError("user", subject)
        user = self._users.find_by_identity(FederatedIdentity(issuer=issuer, subject=subject))
        if user is None:
            raise NotFoundError("user", subject)
        if not user.is_active:
            raise AccessDeniedError(f"User account is deactivated: {user.email}")
        logger.info("machine_reader_call", extra={"client_id": client_id, "user_id": user.id})
        return replace(_to_dto(user), machine_client_id=client_id)


class SsoLoginUseCases:
    """Drive the authorization code flow with the IdP and issue a session on success."""

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        users: UserAccountRepository,
        sessions: RefreshSessionRepository,
        tokens: SessionTokens,
        transactions: LoginTransactionRepository,
        secrets: SecretGenerator,
        policy: ProvisioningPolicy,
        sign_in_carry: timedelta,
        transaction_ttl: timedelta = DEFAULT_LOGIN_TRANSACTION_TTL,
    ) -> None:
        self._idp = identity_provider
        self._users = users
        self._sessions = sessions
        self._transactions = transactions
        self._secrets = secrets
        self._policy = policy
        self._tokens = tokens
        self._transaction_ttl = transaction_ttl
        #: How long to keep the login record (ADR-0071). Extended on every continuation
        self._sign_in_carry = sign_in_carry

    @property
    def provider_name(self) -> str:
        return self._idp.display_name

    # ── 1. Login start ────────────────────────────────────────────────
    def start_login(
        self, *, redirect_path: str | None, now: datetime, silent: bool = False
    ) -> StartedLoginDTO:
        """``silent`` is a round trip that checks "already signed in?" without the IdP showing a screen (ADR-0062)."""
        return self._start(RedirectTarget.parse(redirect_path), now=now, silent=silent)

    def start_renewal(self, *, continued: ContinuedSignIn | None, now: datetime) -> StartedLoginDTO:
        """A round trip that continues an expired login without showing a screen (inside a hidden frame, ADR-0071). Always ``prompt=none``.

        ``continued`` is what was read from the leftover expired token. If the same person comes back,
        their login record is carried over. ``None`` if unreadable (enters as a new login).
        """
        return self._start(
            RedirectTarget.parse(None), now=now, silent=True, purpose=LoginPurpose.RENEW, continued=continued
        )

    def _start(
        self,
        target: RedirectTarget,
        *,
        now: datetime,
        silent: bool,
        purpose: LoginPurpose = LoginPurpose.LOGIN,
        continued: ContinuedSignIn | None = None,
    ) -> StartedLoginDTO:
        state = self._secrets.generate()
        nonce = self._secrets.generate()
        code_verifier = self._secrets.generate()
        transaction = LoginTransaction.issue(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_target=target,
            now=now,
            ttl=self._transaction_ttl,
            silent=silent,
            purpose=purpose,
            continued=continued,
        )
        # Do not accumulate abandoned logins (round trips whose callback never came back)
        self._transactions.delete_expired(now)
        self._transactions.add(transaction)
        request = self._idp.build_authorization_request(
            state=state, nonce=nonce, code_verifier=code_verifier, silent=silent
        )
        # The Presentation layer puts ``browser_binding`` in a short-lived cookie and matches it
        # on the callback. With only the state in the DB, an attacker could make a victim open the
        # callback URL of a login the attacker started, leaving the victim "signed in as the
        # attacker" (login CSRF).
        return StartedLoginDTO(
            authorization_url=request.authorization_url, browser_binding=state
        )

    # ── 2. Callback ───────────────────────────────────────────────
    def purpose_of(self, state: str) -> LoginPurpose | None:
        """Which handling the return goes to (the round trip is not consumed). ``None`` for an unknown ``state``."""
        transaction = self._transactions.find(state)
        return None if transaction is None else transaction.purpose

    def complete_login(self, *, code: str, state: str, now: datetime) -> CompletedLoginDTO:
        transaction, claims = self._redeem(code=code, state=state, now=now, purpose=LoginPurpose.LOGIN)
        user = self._resolve_user(claims)
        user.ensure_can_sign_in()
        # Clean up expired login records here (there is no scheduled job)
        self._sessions.delete_expired(now)
        session_id = self._new_sign_in(user.id, claims, now)
        return CompletedLoginDTO(
            session=IssuedSessionDTO(
                access_token=self._tokens.access_token(_to_dto(user), session_id=session_id, now=now)
            ),
            redirect_path=transaction.redirect_target.path,
        )

    def complete_renewal(self, *, code: str, state: str, now: datetime) -> IssuedSessionDTO | None:
        """Return of the continuation round trip (ADR-0071). ``None`` if it cannot continue (the screen sends to the login page).

        It does not continue when: a different person came back (signed in as someone else at the IdP), the user is deactivated,
        or the admission rules reject them. A broken round trip or failure to talk to the IdP raises (the caller turns it into ``failed``).

        ⚠ **Continuing is not signing in again.** If the same person's login record remains, it is extended and carried over.
        If the record is gone (stop notification, periodic reconciliation, logout), a new record is created — the IdP answered
        that they are still signed in, so letting them in as a new login is fine.
        """
        transaction, claims = self._redeem(code=code, state=state, now=now, purpose=LoginPurpose.RENEW)
        try:
            self._policy.ensure_allowed(claims)
        except AccessDeniedError:
            return None
        user = self._users.find_by_identity(claims.identity)
        continued = transaction.continued
        if user is None or not user.is_active:
            return None
        if continued is not None and continued.user_id != user.id:
            logger.info("sso_renewal_switched_user", extra={"event": "auth.sso.renewal_switched_user"})
            return None
        if user.apply_profile(email=claims.email, display_name=claims.resolved_display_name()):
            user = self._users.save(user)
        session_id = self._continue_sign_in(continued, user.id, claims, now)
        return IssuedSessionDTO(
            access_token=self._tokens.access_token(_to_dto(user), session_id=session_id, now=now)
        )

    def _redeem(
        self, *, code: str, state: str, now: datetime, purpose: LoginPurpose
    ) -> tuple[LoginTransaction, IdentityClaims]:
        transaction = self._transactions.consume(state)
        if transaction is None or transaction.purpose is not purpose:
            # Unknown state. CSRF, or a duplicate callback submission (consume works only once).
            raise AuthenticationError("Unknown or already used login state")
        if transaction.is_expired(now):
            raise AuthenticationError("Login request has expired; please sign in again")
        claims = self._idp.exchange_code(
            code=code, code_verifier=transaction.code_verifier, nonce=transaction.nonce
        )
        if purpose is LoginPurpose.LOGIN:
            self._policy.ensure_allowed(claims)
        return transaction, claims

    def _new_sign_in(self, user_id: int, claims: IdentityClaims, now: datetime) -> str:
        session_id = new_identifier()
        self._sessions.add(
            RefreshSession(
                id=session_id,
                user_id=user_id,
                expires_at=now + self._sign_in_carry,
                created_at=now,
                # Remember the IdP-side login (``sid``). When a stop notification arrives targeting
                # "only that device's login", only that one can be ended.
                idp_session_id=claims.session_id,
            )
        )
        return session_id

    def _continue_sign_in(
        self, continued: ContinuedSignIn | None, user_id: int, claims: IdentityClaims, now: datetime
    ) -> str:
        if continued is not None:
            session = self._sessions.find(continued.session_id)
            if session is not None and session.user_id == user_id and self._sessions.extend(
                session.id, idp_session_id=claims.session_id, expires_at=now + self._sign_in_carry
            ):
                return session.id
        return self._new_sign_in(user_id, claims, now)

    def decline_silent_login(self, *, state: str, now: datetime) -> str | None:
        """The IdP answered "not signed in" to a silent check round trip (ADR-0062).

        Consumes the round trip and, if it was a silent check, returns where to go back to (the screen returns
        to the login page without an error). Otherwise ``None`` (the caller treats it as an error as before).
        """
        transaction = self._transactions.consume(state)
        if transaction is None or not transaction.silent or transaction.is_expired(now):
            return None
        return transaction.redirect_target.path

    def decline_renewal(self, *, state: str, now: datetime) -> bool:
        """The IdP answered "not signed in" to a continuation round trip (ADR-0071). Consumes the round trip and returns whether it was a continuation."""
        transaction = self._transactions.consume(state)
        return (
            transaction is not None
            and transaction.purpose is LoginPurpose.RENEW
            and not transaction.is_expired(now)
        )

    # ── 3. IdP-side logout ─────────────────────────────────────────
    def end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        return self._idp.build_end_session_url(post_logout_redirect_uri=post_logout_redirect_uri)

    # ── Matching and creating users ───────────────────────────────────────
    def _resolve_user(self, claims: IdentityClaims) -> UserAccount:
        """Look up by ``(iss, sub)``; if missing, link to an existing user by email; if that is missing too, create one."""
        user = self._users.find_by_identity(claims.identity)
        if user is not None:
            if user.apply_profile(email=claims.email, display_name=claims.resolved_display_name()):
                user = self._users.save(user)
            return user

        if claims.email is not None:
            existing = self._users.find_by_email(claims.email)
            if existing is not None:
                # A user from before SSO was introduced, or one who signed in with another IdP.
                # ⚠ **An email address is not proof of identity**, so by default they are not merged
                #   (`ProvisioningPolicy.link_by_email`). Even on deployments that choose to merge,
                #   only verified addresses are accepted.
                self._policy.ensure_can_link_by_email(claims)
                existing.ensure_can_sign_in()
                existing.link_identity(claims.identity)
                existing.apply_profile(
                    email=claims.email, display_name=claims.resolved_display_name()
                )
                return self._users.save(existing)

        self._policy.ensure_can_provision(claims)
        created = UserAccount(
            id=None,
            email=claims.email,
            display_name=claims.resolved_display_name(),
            identities=[claims.identity],
        )
        return self._users.save(created)


def _to_dto(user: UserAccount) -> AuthenticatedUserDTO:
    return AuthenticatedUserDTO(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        language=user.language,
        can_create_projects=user.can_create_projects,
    )
