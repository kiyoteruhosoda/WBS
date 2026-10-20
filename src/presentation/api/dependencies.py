from __future__ import annotations

from collections.abc import Generator
from functools import cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.calendar_feed import CalendarFeedFetcher, FeedUrlCipher
from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.secret_generator import UrlSafeSecretGenerator
from src.application.use_cases.actuals_use_cases import ActualsUseCases
from src.application.use_cases.authentication_use_cases import (
    AppTokenAuthenticationUseCases,
    SessionAuthenticationUseCases,
    SsoLoginUseCases,
)
from src.application.use_cases.automatic_time_entry_use_cases import AutomaticTimeEntryUseCases
from src.application.use_cases.backchannel_logout_use_cases import ReceiveBackchannelLogout
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.application.use_cases.calendar_import_use_cases import CalendarImportUseCases
from src.application.use_cases.calendar_use_cases import CalendarUseCases
from src.application.use_cases.closing_use_cases import ClosingUseCases
from src.application.use_cases.day_off_use_cases import DayOffUseCases
from src.application.use_cases.pc_activity_use_cases import PcActivityUseCases
from src.application.use_cases.project_member_use_cases import ProjectMemberUseCases
from src.application.use_cases.task_removal_use_cases import TaskRemovalUseCases
from src.application.use_cases.task_use_cases import TaskUseCases
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.application.use_cases.today_use_cases import TodayUseCases
from src.application.use_cases.tracking_rule_use_cases import TrackingRuleUseCases
from src.application.use_cases.wintrack_release_use_cases import WinTrackReleases
from src.application.use_cases.work_break_use_cases import WorkBreakUseCases
from src.application.user_clock import UserClock
from src.domain.exceptions import AuthenticationError
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID, AuthMode, AuthSettings
from src.infrastructure.calendar_feed.ics_parser import IcsCalendarParser
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.auth_session_repository import (
    SqlAlchemyAuthSessionRepository,
)
from src.infrastructure.repositories.auto_time_entry_receipt_repository import (
    SqlAlchemyAutoTimeEntryReceiptRepository,
)
from src.infrastructure.repositories.calendar_event_repository import (
    SqlAlchemyCalendarEventRepository,
)
from src.infrastructure.repositories.calendar_import_repository import (
    SqlAlchemyCalendarImportRepository,
    SqlAlchemyImportedOccurrenceRepository,
)
from src.infrastructure.repositories.calendar_repository import (
    SqlAlchemyCalendarRepository,
    SqlAlchemyCalendarViewPresetRepository,
    SqlAlchemyDayOffRepository,
)
from src.infrastructure.repositories.category_repository import SqlAlchemyCategoryRepository
from src.infrastructure.repositories.closing_period_repository import (
    SqlAlchemyClosingPeriodRepository,
)
from src.infrastructure.repositories.login_transaction_repository import (
    SqlAlchemyLoginTransactionRepository,
)
from src.infrastructure.repositories.logout_delivery_repository import (
    SqlAlchemyLogoutDeliveryRepository,
)
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.occurrence_completion_repository import (
    SqlAlchemyOccurrenceCompletionRepository,
)
from src.infrastructure.repositories.pc_activity_repository import SqlAlchemyPcActivityRepository
from src.infrastructure.repositories.person_directory import SqlAlchemyPersonDirectory
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.time_entry_carving_repository import (
    SqlAlchemyTimeEntryCarvingRepository,
)
from src.infrastructure.repositories.time_entry_repository import SqlAlchemyTimeEntryRepository
from src.infrastructure.repositories.tracking_rule_repository import (
    SqlAlchemyTrackingRuleRepository,
)
from src.infrastructure.repositories.user_account_repository import (
    SqlAlchemyUserAccountRepository,
)
from src.infrastructure.repositories.work_break_repository import SqlAlchemyWorkBreakRepository
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository
from src.infrastructure.scheduler_move.scheduler_move_settings import SchedulerMoveSettings
from src.infrastructure.tracker_move.tracker_move_settings import TrackerMoveSettings
from src.infrastructure.wintrack_release.s3_release_file_store import S3ReleaseFileStore
from src.infrastructure.wintrack_release.wintrack_release_settings import (
    load_wintrack_release_settings,
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


def get_project_member_use_cases(db: DbDep, auth: AuthSettingsDep) -> ProjectMemberUseCases:
    # SSO では assay と結び付いている人だけを候補にする（ADR-0055 決定 5）
    people = SqlAlchemyPersonDirectory(db, require_identity=auth.mode is AuthMode.OIDC)
    return ProjectMemberUseCases(db, people)


ProjectMemberUseCasesDep = Annotated[ProjectMemberUseCases, Depends(get_project_member_use_cases)]


def get_tracker_move_settings(request: Request) -> TrackerMoveSettings:
    """打刻まわりを Tracker へ移したか（task #526 / ADR-0053。``create_app`` が置く）。"""
    return request.app.state.tracker_move_settings

TrackerMoveSettingsDep = Annotated[TrackerMoveSettings, Depends(get_tracker_move_settings)]


def get_scheduler_move_settings(request: Request) -> SchedulerMoveSettings:
    """予定まわりを Scheduler へ移したか（task #535 / ADR-0054。``create_app`` が置く）。"""
    return request.app.state.scheduler_move_settings

SchedulerMoveSettingsDep = Annotated[SchedulerMoveSettings, Depends(get_scheduler_move_settings)]


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


def get_receive_backchannel_logout(
    db: DbDep, identity_provider: IdentityProviderDep
) -> ReceiveBackchannelLogout:
    return ReceiveBackchannelLogout(
        identity_provider=identity_provider,
        sessions=SqlAlchemyAuthSessionRepository(db),
        deliveries=SqlAlchemyLogoutDeliveryRepository(db),
    )

BackchannelLogoutDep = Annotated[
    ReceiveBackchannelLogout, Depends(get_receive_backchannel_logout)
]


def get_time_entry_use_cases(db: DbDep) -> TimeEntryUseCases:
    # Start の既定のタスクは「いまの予定の回のタスク」から（ADR-0008・ADR-0009）。
    # 確定済みの締めの期間に掛かる打刻は書き換えさせない（ADR-0012）。
    calendar = get_calendar_event_use_cases(db)
    return TimeEntryUseCases(
        entries=SqlAlchemyTimeEntryRepository(db),
        tasks=SqlAlchemyTaskRepository(db),
        unit_of_work=db,
        scheduled_tasks=calendar,
        closing_periods=SqlAlchemyClosingPeriodRepository(db),
        occurrences=calendar,
    )

TimeEntryUseCasesDep = Annotated[TimeEntryUseCases, Depends(get_time_entry_use_cases)]


def get_automatic_time_entry_use_cases(db: DbDep) -> AutomaticTimeEntryUseCases:
    """PC の自動記録（WinTrack）の打刻（ADR-0042・ADR-0045）。"""
    return AutomaticTimeEntryUseCases(
        entries=SqlAlchemyTimeEntryRepository(db),
        receipts=SqlAlchemyAutoTimeEntryReceiptRepository(db),
        carvings=SqlAlchemyTimeEntryCarvingRepository(db),
        tasks=SqlAlchemyTaskRepository(db),
        closing_periods=SqlAlchemyClosingPeriodRepository(db),
        unit_of_work=db,
    )

AutomaticTimeEntryUseCasesDep = Annotated[
    AutomaticTimeEntryUseCases, Depends(get_automatic_time_entry_use_cases)
]


def get_tracking_rule_use_cases(db: DbDep) -> TrackingRuleUseCases:
    """PC の自動記録の規則（WinTrack、ADR-0043）。"""
    return TrackingRuleUseCases(
        SqlAlchemyTrackingRuleRepository(db),
        SqlAlchemyTaskRepository(db),
        SqlAlchemyProjectRepository(db),
        db,
    )

TrackingRuleUseCasesDep = Annotated[TrackingRuleUseCases, Depends(get_tracking_rule_use_cases)]


@cache
def get_wintrack_releases() -> WinTrackReleases:
    """WinTrack の更新の置き場の中継（ADR-0044）。覚えた版の一覧を使い回すため、プロセスで 1 つ。"""
    return WinTrackReleases(S3ReleaseFileStore(load_wintrack_release_settings()))

WinTrackReleasesDep = Annotated[WinTrackReleases, Depends(get_wintrack_releases)]


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


def get_app_or_web_user(
    request: Request, db: DbDep, settings: AuthSettingsDep, session_auth: SessionAuthDep
) -> AuthenticatedUserDTO:
    """アプリ（Android の打刻アプリ）からも叩いてよい口の利用者（ADR-0018）。

    ⚠ **これを付けた口だけが assay のアクセストークンを受け取る**（打刻の Start / Stop /
    現在、ADR-0018。この先の通知の読み取り ``GET /calendar/alarms``、ADR-0021。WinTrack の口。
    wbstimer が今日の打刻を直す期間の一覧と 1 件の修正、PC を使っていた時間、ADR-0049）。ほかの口は
    :func:`get_current_user`（Web のセッション Cookie だけ）のまま。

    - ``Authorization`` ヘッダーが**無ければ** :func:`get_current_user` と同じ
    - **あれば Bearer だけで決め、Cookie へ落とさない。** 壊れたトークンを持ってきたアプリが、
      同じ端末のブラウザの Cookie で通ってしまう（誰の操作か分からなくなる）のを防ぐ
    - ``AUTH_MODE=single_user`` では何も見ない（従来どおり初期ユーザー）
    """
    authorization = request.headers.get("Authorization")
    if not settings.sso_enabled or authorization is None:
        return get_current_user(request, db, settings, session_auth)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization header must be a Bearer token")
    provider = request.app.state.identity_provider
    if provider is None:
        raise AuthenticationError("SSO is not configured")
    return AppTokenAuthenticationUseCases(
        identity_provider=provider,
        users=SqlAlchemyUserAccountRepository(db),
        accepted_client_ids=settings.app_client_ids,
    ).authenticate(token=token.strip())

AppOrWebUserDep = Annotated[AuthenticatedUserDTO, Depends(get_app_or_web_user)]


def get_day_off_use_cases(db: DbDep) -> DayOffUseCases:
    """休みの層と営業日の判定（ADR-0029）。"""
    return DayOffUseCases(SqlAlchemyCalendarRepository(db), SqlAlchemyDayOffRepository(db), db)

DayOffUseCasesDep = Annotated[DayOffUseCases, Depends(get_day_off_use_cases)]


def get_calendar_event_use_cases(db: DbDep) -> CalendarEventUseCases:
    """予定のユースケース。確定（``UnitOfWork``）はこのリクエストの ``Session``。"""
    return CalendarEventUseCases(
        events=SqlAlchemyCalendarEventRepository(db),
        tasks=SqlAlchemyTaskRepository(db),
        unit_of_work=db,
        completions=SqlAlchemyOccurrenceCompletionRepository(db),
        event_calendars=SqlAlchemyCalendarRepository(db),
        day_off_layers=get_day_off_use_cases(db),
    )

CalendarEventUseCasesDep = Annotated[CalendarEventUseCases, Depends(get_calendar_event_use_cases)]


def _scheduled_time_of(
    db: Session, scheduler_move: SchedulerMoveSettings
) -> CalendarEventUseCases | None:
    """タスクの「予定済みの時間」を数える口（ADR-0014）。

    予定を Scheduler へ移した後は無し（``scheduled_hours``・``unscheduled_hours`` は null）。
    WBS の予定の表は凍っているので、凍った値を今のものに見せない（task #535 / ADR-0054）。
    """
    return None if scheduler_move.moved else get_calendar_event_use_cases(db)


def get_task_use_cases(db: DbDep, scheduler_move: SchedulerMoveSettingsDep) -> TaskUseCases:
    """タスクのユースケース。「予定済みの時間」は予定のユースケースから引く（ADR-0014）。"""
    return TaskUseCases(db, scheduled_time=_scheduled_time_of(db, scheduler_move))

TaskUseCasesDep = Annotated[TaskUseCases, Depends(get_task_use_cases)]


def get_task_removal_use_cases(db: DbDep) -> TaskRemovalUseCases:
    """タスクを消す・アーカイブする（ADR-0046）。"""
    return TaskRemovalUseCases(
        SqlAlchemyTaskRepository(db),
        SqlAlchemyTimeEntryRepository(db),
        SqlAlchemyTrackingRuleRepository(db),
        db,
    )

TaskRemovalUseCasesDep = Annotated[TaskRemovalUseCases, Depends(get_task_removal_use_cases)]


def get_today_use_cases(
    db: DbDep, tracker_move: TrackerMoveSettingsDep, scheduler_move: SchedulerMoveSettingsDep
) -> TodayUseCases:
    """「今日」の画面の要約。時計は 1 つを共有する（タスクの期限の近さと今日の区切りを揃える）。"""
    clock = UserClock(db)
    return TodayUseCases(
        clock,
        time_entries=get_time_entry_use_cases(db),
        tasks=TaskUseCases(db, clock, scheduled_time=_scheduled_time_of(db, scheduler_move)),
        tracked_time_moved=tracker_move.moved,
        calendar_moved=scheduler_move.moved,
    )

TodayUseCasesDep = Annotated[TodayUseCases, Depends(get_today_use_cases)]


def get_calendar_use_cases(db: DbDep) -> CalendarUseCases:
    """予定のカレンダー・表示の選択・表示の組み合わせ（ADR-0027）。"""
    return CalendarUseCases(
        calendars=SqlAlchemyCalendarRepository(db),
        presets=SqlAlchemyCalendarViewPresetRepository(db),
        events=SqlAlchemyCalendarEventRepository(db),
        unit_of_work=db,
        imports=SqlAlchemyCalendarImportRepository(db),
        imported_occurrences=SqlAlchemyImportedOccurrenceRepository(db),
    )

CalendarUseCasesDep = Annotated[CalendarUseCases, Depends(get_calendar_use_cases)]


def get_closing_use_cases(db: DbDep) -> ClosingUseCases:
    """締め（ADR-0012）。確定は期間の行と work_logs をこのリクエストの ``Session`` で 1 度に書く。"""
    return ClosingUseCases(
        periods=SqlAlchemyClosingPeriodRepository(db),
        entries=SqlAlchemyTimeEntryRepository(db),
        work_logs=SqlAlchemyWorkLogRepository(db),
        tasks=SqlAlchemyTaskRepository(db),
        unit_of_work=db,
        occurrences=get_calendar_event_use_cases(db),
        breaks=SqlAlchemyWorkBreakRepository(db),
    )

ClosingUseCasesDep = Annotated[ClosingUseCases, Depends(get_closing_use_cases)]


def get_actuals_use_cases(
    db: DbDep, tracker_move: TrackerMoveSettingsDep, scheduler_move: SchedulerMoveSettingsDep
) -> ActualsUseCases:
    """実績の見える化（ADR-0017）。時計は 1 つを共有する（タスクの予定済みと期間の区切りを揃える）。"""
    clock = UserClock(db)
    calendar = get_calendar_event_use_cases(db)
    return ActualsUseCases(
        clock=clock,
        tasks=TaskUseCases(db, clock, scheduled_time=_scheduled_time_of(db, scheduler_move)),
        task_repository=SqlAlchemyTaskRepository(db),
        work_logs=SqlAlchemyWorkLogRepository(db),
        time_entries=SqlAlchemyTimeEntryRepository(db),
        closing_periods=SqlAlchemyClosingPeriodRepository(db),
        categories=SqlAlchemyCategoryRepository(db),
        milestones=SqlAlchemyMilestoneRepository(db),
        projects=SqlAlchemyProjectRepository(db),
        occurrences=calendar,
        breaks=SqlAlchemyWorkBreakRepository(db),
        tracked_time_moved=tracker_move.moved,
        calendar_moved=scheduler_move.moved,
    )

ActualsUseCasesDep = Annotated[ActualsUseCases, Depends(get_actuals_use_cases)]


def get_work_break_use_cases(db: DbDep) -> WorkBreakUseCases:
    """休み（WinTrack、ADR-0048）。確定済みの締めの期間の日は置き換えない。"""
    return WorkBreakUseCases(
        SqlAlchemyWorkBreakRepository(db), SqlAlchemyClosingPeriodRepository(db), db
    )

WorkBreakUseCasesDep = Annotated[WorkBreakUseCases, Depends(get_work_break_use_cases)]


def get_pc_activity_use_cases(db: DbDep) -> PcActivityUseCases:
    """PC を使っていた時間（WinTrack → wbstimer、ADR-0049）。締めには関係しない。"""
    return PcActivityUseCases(SqlAlchemyPcActivityRepository(db), db)

PcActivityUseCasesDep = Annotated[PcActivityUseCases, Depends(get_pc_activity_use_cases)]


def build_calendar_import_use_cases(
    db: Session, fetcher: CalendarFeedFetcher, cipher: FeedUrlCipher
) -> CalendarImportUseCases:
    """カレンダーの取り込み（ADR-0037）。定期の読み込み（``calendar_feed_refresh``）も同じ形で作る。"""
    return CalendarImportUseCases(
        calendars=SqlAlchemyCalendarRepository(db),
        imports=SqlAlchemyCalendarImportRepository(db),
        occurrences=SqlAlchemyImportedOccurrenceRepository(db),
        users=SqlAlchemyUserAccountRepository(db),
        fetcher=fetcher,
        parser=IcsCalendarParser(),
        cipher=cipher,
        unit_of_work=db,
    )


def get_calendar_import_use_cases(request: Request, db: DbDep) -> CalendarImportUseCases:
    """URL を読む口と封じる鍵はアプリに 1 つ（``create_app`` が置く。試験は差し替える）。"""
    return build_calendar_import_use_cases(
        db, request.app.state.calendar_feed_fetcher, request.app.state.calendar_feed_cipher
    )


CalendarImportUseCasesDep = Annotated[
    CalendarImportUseCases, Depends(get_calendar_import_use_cases)
]
