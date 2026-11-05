from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import UrlSafeSecretGenerator
from src.application.use_cases.actuals_use_cases import ActualsUseCases
from src.application.use_cases.authentication_use_cases import (
    MachineReaderAuthenticationUseCases,
    SessionAuthenticationUseCases,
    SsoLoginUseCases,
)
from src.application.use_cases.backchannel_logout_use_cases import ReceiveBackchannelLogout
from src.application.use_cases.project_member_use_cases import ProjectMemberUseCases
from src.application.use_cases.task_removal_use_cases import TaskRemovalUseCases
from src.application.use_cases.task_use_cases import TaskUseCases
from src.application.user_clock import UserClock
from src.domain.exceptions import AuthenticationError
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID, AuthMode, AuthSettings
from src.infrastructure.auth.jwt_session_tokens import JwtSessionTokens
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.category_repository import SqlAlchemyCategoryRepository
from src.infrastructure.repositories.login_transaction_repository import (
    SqlAlchemyLoginTransactionRepository,
)
from src.infrastructure.repositories.logout_delivery_repository import (
    SqlAlchemyLogoutDeliveryRepository,
)
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.person_directory import SqlAlchemyPersonDirectory
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.refresh_session_repository import (
    SqlAlchemyRefreshSessionRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.user_account_repository import (
    SqlAlchemyUserAccountRepository,
)
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository
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


def _log_as(request: Request, user: AuthenticatedUserDTO) -> AuthenticatedUserDTO:
    """アクセスログの行に載せる、誰の要求か（task #812）。

    ⚠ ``ContextVar`` では戻らない。この依存関数はスレッドで走り、ミドルウェアも別のタスクなので、
    置いた値がログを出す側へ届かない。``request.state`` は要求ごとの 1 つの辞書で、どちらからも同じものが見える。
    """
    request.state.user_id_hash = user.id_hash
    return user


def get_machine_reader_user(
    request: Request,
    db: DbDep,
    settings: AuthSettingsDep,
    issuer: Annotated[str, Query(description="利用者の発行者（iss）")],
    subject: Annotated[str, Query(description="利用者の本人番号（sub）")],
) -> AuthenticatedUserDTO:
    """ほかのアプリのサーバー（Tracker）が利用者の代わりに読み書きする口の利用者（ADR-0056）。

    ⚠ **Bearer の機械のトークンだけ**で決める（Cookie は見ない）。``AUTH_MODE=single_user`` では閉じる
    （名乗りを確かめられないので、機械の口は SSO の配備だけのもの）。
    """
    authorization = request.headers.get("Authorization") or ""
    scheme, _, token = authorization.partition(" ")
    if not settings.sso_enabled or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("A machine Bearer token is required")
    provider = request.app.state.identity_provider
    if provider is None:
        raise AuthenticationError("SSO is not configured")
    user = MachineReaderAuthenticationUseCases(
        identity_provider=provider,
        users=SqlAlchemyUserAccountRepository(db),
        audience=settings.machine_audience,
        accepted_client_ids=settings.machine_reader_client_ids,
    ).authenticate(token=token.strip(), issuer=issuer, subject=subject)
    return _log_as(request, user)


MachineReaderUserDep = Annotated[AuthenticatedUserDTO, Depends(get_machine_reader_user)]


def get_project_member_use_cases(db: DbDep, auth: AuthSettingsDep) -> ProjectMemberUseCases:
    # SSO では assay と結び付いている人だけを候補にする（ADR-0055 決定 5）
    people = SqlAlchemyPersonDirectory(db, require_identity=auth.mode is AuthMode.OIDC)
    return ProjectMemberUseCases(db, people)


ProjectMemberUseCasesDep = Annotated[ProjectMemberUseCases, Depends(get_project_member_use_cases)]


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


def _session_tokens(settings: AuthSettings) -> JwtSessionTokens:
    return JwtSessionTokens(
        signing_key=settings.session_signing_key,
        access_lifetime=settings.access_token_ttl,
        carry=settings.sign_in_carry,
    )


def get_session_authentication_use_cases(
    db: DbDep, settings: AuthSettingsDep
) -> SessionAuthenticationUseCases:
    return SessionAuthenticationUseCases(
        users=SqlAlchemyUserAccountRepository(db),
        sessions=SqlAlchemyRefreshSessionRepository(db),
        tokens=_session_tokens(settings),
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
        sessions=SqlAlchemyRefreshSessionRepository(db),
        tokens=_session_tokens(settings),
        transactions=SqlAlchemyLoginTransactionRepository(db),
        secrets=UrlSafeSecretGenerator(),
        policy=settings.policy,
        sign_in_carry=settings.sign_in_carry,
    )

SsoLoginDep = Annotated[SsoLoginUseCases, Depends(get_sso_login_use_cases)]


def get_receive_backchannel_logout(
    db: DbDep, settings: AuthSettingsDep, identity_provider: IdentityProviderDep
) -> ReceiveBackchannelLogout:
    return ReceiveBackchannelLogout(
        identity_provider=identity_provider,
        sessions=SqlAlchemyRefreshSessionRepository(db),
        deliveries=SqlAlchemyLogoutDeliveryRepository(db),
        # 控えが残る長さまで覚える。短いと、古い通知の再送が入り直した後のログインを落とす（ADR-0071）
        delivery_retention=settings.sign_in_carry,
    )

BackchannelLogoutDep = Annotated[
    ReceiveBackchannelLogout, Depends(get_receive_backchannel_logout)
]


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
        return _log_as(
            request,
            AuthenticatedUserDTO(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                timezone=user.timezone,
                language=user.language,
                can_create_projects=user.can_create_projects,
            ),
        )
    return _log_as(
        request,
        session_auth.authenticate(token=request.cookies.get(settings.cookie_name), now=utcnow()),
    )

CurrentUserDep = Annotated[AuthenticatedUserDTO, Depends(get_current_user)]


def get_task_use_cases(db: DbDep) -> TaskUseCases:
    return TaskUseCases(db)

TaskUseCasesDep = Annotated[TaskUseCases, Depends(get_task_use_cases)]


def get_task_removal_use_cases(db: DbDep) -> TaskRemovalUseCases:
    """タスクを消す・アーカイブする（ADR-0046）。"""
    return TaskRemovalUseCases(SqlAlchemyTaskRepository(db), db)

TaskRemovalUseCasesDep = Annotated[TaskRemovalUseCases, Depends(get_task_removal_use_cases)]


def get_actuals_use_cases(db: DbDep) -> ActualsUseCases:
    """実績の見える化（ADR-0017）。時計は 1 つを共有する（タスクの期限の近さと期間の区切りを揃える）。"""
    clock = UserClock(db)
    return ActualsUseCases(
        clock=clock,
        tasks=TaskUseCases(db, clock),
        task_repository=SqlAlchemyTaskRepository(db),
        work_logs=SqlAlchemyWorkLogRepository(db),
        categories=SqlAlchemyCategoryRepository(db),
        milestones=SqlAlchemyMilestoneRepository(db),
        projects=SqlAlchemyProjectRepository(db),
    )

ActualsUseCasesDep = Annotated[ActualsUseCases, Depends(get_actuals_use_cases)]
