"""SSO ログインの筋書き。

OIDC の認可コードフロー（PKCE 付き）を 2 つのユースケースに分ける。

- ``SsoLoginUseCases``          — IdP との往復（開始・コールバック・IdP 側ログアウト）
- ``SessionAuthenticationUseCases`` — 発行済みセッションから利用者を引く

分けているのは、リクエストごとの本人確認に IdP を要らなくするため。ログイン後の
毎リクエストは自前のセッションだけで済み、IdP が落ちていても操作を続けられる。

プロトコルの詳細（ディスカバリ・JWKS・署名検証）は ``IdentityProvider`` の向こう側。
ここが知っているのは「誰を通すか」「誰を作るか」「セッションをどう始めて終えるか」。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.application.dto.auth_dto import (
    AuthenticatedUserDTO,
    CompletedLoginDTO,
    StartedLoginDTO,
)
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import SecretGenerator
from src.domain.entities.auth_session import DEFAULT_SESSION_TTL, AuthSession
from src.domain.entities.login_transaction import (
    DEFAULT_LOGIN_TRANSACTION_TTL,
    LoginTransaction,
)
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import AccessDeniedError, AuthenticationError
from src.domain.repositories.auth_session_repository import AuthSessionRepository
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.domain.value_objects.redirect_target import RedirectTarget


class SessionAuthenticationUseCases:
    """発行済みセッショントークンから利用者を決める。"""

    def __init__(self, *, users: UserAccountRepository, sessions: AuthSessionRepository) -> None:
        self._users = users
        self._sessions = sessions

    def authenticate(self, *, token: str | None, now: datetime) -> AuthenticatedUserDTO:
        if not token:
            raise AuthenticationError("Not authenticated")
        session = self._sessions.find_by_token(token)
        if session is None:
            raise AuthenticationError("Session not found")
        if session.is_expired(now):
            self._sessions.delete_by_token(token)
            raise AuthenticationError("Session has expired")
        user = self._users.find_by_id(session.user_id)
        if user is None:
            self._sessions.delete_by_token(token)
            raise AuthenticationError("Session refers to a user that no longer exists")
        if not user.is_active:
            # 利用停止は「次のログインから」ではなく即時に効かせる
            self._sessions.delete_by_token(token)
            raise AccessDeniedError(f"User account is deactivated: {user.email}")
        session.touch(now)
        self._sessions.update(session)
        return _to_dto(user)

    def revoke(self, *, token: str | None) -> None:
        if token:
            self._sessions.delete_by_token(token)


class SsoLoginUseCases:
    """IdP との認可コードフローを進め、成功したらセッションを発行する。"""

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        users: UserAccountRepository,
        sessions: AuthSessionRepository,
        transactions: LoginTransactionRepository,
        secrets: SecretGenerator,
        policy: ProvisioningPolicy,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
        transaction_ttl: timedelta = DEFAULT_LOGIN_TRANSACTION_TTL,
    ) -> None:
        self._idp = identity_provider
        self._users = users
        self._sessions = sessions
        self._transactions = transactions
        self._secrets = secrets
        self._policy = policy
        self._session_ttl = session_ttl
        self._transaction_ttl = transaction_ttl

    @property
    def provider_name(self) -> str:
        return self._idp.display_name

    # ── 1. ログイン開始 ────────────────────────────────────────────────
    def start_login(self, *, redirect_path: str | None, now: datetime) -> StartedLoginDTO:
        state = self._secrets.generate()
        nonce = self._secrets.generate()
        code_verifier = self._secrets.generate()
        transaction = LoginTransaction.issue(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_target=RedirectTarget.parse(redirect_path),
            now=now,
            ttl=self._transaction_ttl,
        )
        # 中断されたログイン（コールバックが返ってこなかった往復）を溜めない
        self._transactions.delete_expired(now)
        self._transactions.add(transaction)
        request = self._idp.build_authorization_request(
            state=state, nonce=nonce, code_verifier=code_verifier
        )
        return StartedLoginDTO(authorization_url=request.authorization_url)

    # ── 2. コールバック ───────────────────────────────────────────────
    def complete_login(self, *, code: str, state: str, now: datetime) -> CompletedLoginDTO:
        transaction = self._transactions.consume(state)
        if transaction is None:
            # 覚えのない state。CSRF か、コールバックの二重送信（consume は 1 回きり）。
            raise AuthenticationError("Unknown or already used login state")
        if transaction.is_expired(now):
            raise AuthenticationError("Login request has expired; please sign in again")

        claims = self._idp.exchange_code(
            code=code, code_verifier=transaction.code_verifier, nonce=transaction.nonce
        )
        self._policy.ensure_allowed(claims)
        user = self._resolve_user(claims)
        user.ensure_can_sign_in()

        token = self._secrets.generate()
        self._sessions.delete_expired(now)
        session = AuthSession.issue(user_id=user.id, token=token, now=now, ttl=self._session_ttl)
        self._sessions.add(session)
        return CompletedLoginDTO(
            session_token=token,
            expires_at=session.expires_at,
            redirect_path=transaction.redirect_target.path,
        )

    # ── 3. IdP 側のログアウト ─────────────────────────────────────────
    def end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        return self._idp.build_end_session_url(post_logout_redirect_uri=post_logout_redirect_uri)

    # ── 利用者の突き合わせ・作成 ───────────────────────────────────────
    def _resolve_user(self, claims: IdentityClaims) -> UserAccount:
        """``(iss, sub)`` で引き、無ければメールで既存利用者に結び付け、それも無ければ作る。"""
        user = self._users.find_by_identity(claims.identity)
        if user is not None:
            if user.apply_profile(email=claims.email, display_name=claims.resolved_display_name()):
                user = self._users.save(user)
            return user

        if claims.email is not None:
            existing = self._users.find_by_email(claims.email)
            if existing is not None:
                # SSO 導入前から居る利用者、あるいは別 IdP で入っていた利用者。
                # メール一致だけで結ぶので、検証済みメールを要求する設定でのみ許す
                # （検証されていないメールを名乗れる IdP では、他人の既存アカウントを
                #   乗っ取れてしまう）。
                if not self._policy.require_verified_email:
                    raise AccessDeniedError(
                        "Linking an existing account by email requires verified email addresses; "
                        "enable OIDC_REQUIRE_VERIFIED_EMAIL"
                    )
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
    )
