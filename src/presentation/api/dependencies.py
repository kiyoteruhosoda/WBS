from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import UrlSafeSecretGenerator
from src.application.use_cases.authentication_use_cases import (
    SessionAuthenticationUseCases,
    SsoLoginUseCases,
)
from src.domain.exceptions import AuthenticationError
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID, AuthSettings
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.auth_session_repository import (
    SqlAlchemyAuthSessionRepository,
)
from src.infrastructure.repositories.login_transaction_repository import (
    SqlAlchemyLoginTransactionRepository,
)
from src.infrastructure.repositories.user_account_repository import (
    SqlAlchemyUserAccountRepository,
)
from src.shared.clock import utcnow


def get_db() -> Generator[Session, None, None]:
    session = get_db_session()
    try:
        yield session
    finally:
        session.close()

DbDep = Annotated[Session, Depends(get_db)]


def get_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings

AuthSettingsDep = Annotated[AuthSettings, Depends(get_auth_settings)]


def get_identity_provider(request: Request) -> IdentityProvider:
    """SSO 有効時の IdP アダプタ。

    テストや別 IdP への差し替えは ``app.dependency_overrides`` でここを置き換える。
    """
    provider = request.app.state.identity_provider
    if provider is None:
        # 「認証に失敗した」ではなく「その入口が無い」。401 を返すと、フロントが
        # ログイン画面へ飛ばして無限に往復する。
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO is not enabled. Set AUTH_MODE=oidc to enable it.",
        )
    return provider

IdentityProviderDep = Annotated[IdentityProvider, Depends(get_identity_provider)]


def get_session_authentication_use_cases(db: DbDep) -> SessionAuthenticationUseCases:
    return SessionAuthenticationUseCases(
        users=SqlAlchemyUserAccountRepository(db),
        sessions=SqlAlchemyAuthSessionRepository(db),
    )

SessionAuthDep = Annotated[
    SessionAuthenticationUseCases, Depends(get_session_authentication_use_cases)
]


def get_sso_login_use_cases(
    db: DbDep, settings: AuthSettingsDep, identity_provider: IdentityProviderDep
) -> SsoLoginUseCases:
    return SsoLoginUseCases(
        identity_provider=identity_provider,
        users=SqlAlchemyUserAccountRepository(db),
        sessions=SqlAlchemyAuthSessionRepository(db),
        transactions=SqlAlchemyLoginTransactionRepository(db),
        secrets=UrlSafeSecretGenerator(),
        policy=settings.policy,
        session_ttl=settings.session_ttl,
    )

SsoLoginDep = Annotated[SsoLoginUseCases, Depends(get_sso_login_use_cases)]


def get_current_user(
    request: Request, db: DbDep, settings: AuthSettingsDep, session_auth: SessionAuthDep
) -> AuthenticatedUserDTO:
    """このリクエストを出している利用者。

    ``AUTH_MODE=single_user``（既定）では従来どおり初期ユーザー 1 人を返す。
    SSO を入れていない既存の配備をそのまま動かし続けるための逃げ道で、
    ネットワーク越しに公開する配備では ``AUTH_MODE=oidc`` にする。
    """
    if not settings.sso_enabled:
        user = SqlAlchemyUserAccountRepository(db).find_by_id(SINGLE_USER_ID)
        if user is None:
            raise AuthenticationError("Default user is missing; run the database migration")
        return AuthenticatedUserDTO(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            timezone=user.timezone,
            language=user.language,
        )
    return session_auth.authenticate(
        token=request.cookies.get(settings.cookie_name), now=utcnow()
    )

CurrentUserDep = Annotated[AuthenticatedUserDTO, Depends(get_current_user)]
