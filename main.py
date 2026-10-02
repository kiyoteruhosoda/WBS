from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.application.ports.calendar_feed import CalendarFeedError
from src.domain.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.infrastructure.auth.auth_settings import AuthMode, load_auth_settings
from src.infrastructure.auth.oidc_identity_provider import OidcIdentityProvider
from src.infrastructure.build_info import load_build_info
from src.infrastructure.calendar_feed.http_fetcher import HttpCalendarFeedFetcher
from src.infrastructure.calendar_feed.url_cipher import load_feed_url_cipher
from src.infrastructure.database.session import init_engine
from src.infrastructure.logging.structured_logger import setup_logging
from src.infrastructure.push.push_settings import load_push_settings
from src.infrastructure.push.web_push_sender import WebPushSender
from src.presentation.api.calendar_feed_refresh import start_calendar_feed_refresh_worker
from src.presentation.api.push_dispatch import start_push_dispatch_worker
from src.presentation.api.reconciliation import start_reconciliation_worker
from src.presentation.api.routers import (
    actuals,
    admin,
    app_links,
    auth,
    calendar,
    calendars,
    categories,
    closing_periods,
    dashboard,
    gantt,
    health,
    inbox,
    milestones,
    ops,
    projects,
    push,
    reviews,
    settings,
    tasks,
    time_entries,
    today,
    worklogs,
)
from src.presentation.api.routers import dependencies as dep_router
from src.presentation.middleware.logging_middleware import RequestLoggingMiddleware
from src.shared.clock import utcnow


def create_app(database_url: str | None = None, db_path: str | None = None) -> FastAPI:
    setup_logging()
    build_info = load_build_info()
    auth_settings = load_auth_settings()
    # 端末への通知（ADR-0031）。⚠ 鍵が無ければ送らない（購読も受け取らない）。既定は閉じる
    push_sender = WebPushSender(load_push_settings())
    # カレンダーの取り込み（ADR-0037）。⚠ 購読の URL を封じる鍵が無ければ購読できない（既定は閉じる）
    calendar_feed_fetcher = HttpCalendarFeedFetcher()
    calendar_feed_cipher = load_feed_url_cipher()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        url = database_url
        if url is None and db_path is not None:
            url = f"sqlite:///{db_path}"
        init_engine(url)
        # IdP で止まった人を拾い直す定期照合。⚠ **停止の受け口が取りこぼしたぶん**を
        #   埋めるための 2 段目で、`MACHINE_CLIENT_ID` が無ければ何も起こさない。
        worker = start_reconciliation_worker(auth_settings)
        # 時刻の来た通知を 60 秒ごとに送る係。鍵が無ければ何も起こさない
        push_worker = start_push_dispatch_worker(push_sender)
        # 購読しているカレンダーを読み込み直す係。鍵が無ければ何も起こさない
        feed_worker = start_calendar_feed_refresh_worker(
            app.state.calendar_feed_fetcher, app.state.calendar_feed_cipher
        )
        try:
            yield
        finally:
            if feed_worker is not None:
                feed_worker.stop()
            if worker is not None:
                worker.stop()
            if push_worker is not None:
                push_worker.stop()

    app = FastAPI(
        title="Task Scheduler",
        version=build_info.version,
        description="Task Scheduler API",
        lifespan=lifespan,
    )
    app.state.build_info = build_info
    app.state.startup_time = utcnow()  # ops.py が now との差を取るので形を揃える
    app.state.auth_settings = auth_settings
    app.state.push_sender = push_sender
    app.state.calendar_feed_fetcher = calendar_feed_fetcher
    app.state.calendar_feed_cipher = calendar_feed_cipher
    # IdP アダプタはディスカバリ文書と JWKS を手元に貯めるので、リクエストごとに
    # 作らず 1 つだけ持つ。SSO 無効時は None（依存が 404 を返す目印になる）。
    app.state.identity_provider = (
        OidcIdentityProvider(auth_settings) if auth_settings.mode is AuthMode.OIDC else None
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"type": "about:blank", "title": "Not Found", "status": 404, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Validation Error", "status": 422, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"type": "about:blank", "title": "Unauthorized", "status": 401, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(AccessDeniedError)
    async def access_denied_handler(request: Request, exc: AccessDeniedError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"type": "about:blank", "title": "Forbidden", "status": 403, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(CalendarFeedError)
    async def calendar_feed_error_handler(request: Request, exc: CalendarFeedError) -> JSONResponse:
        # 外の iCalendar を読めなかった（ADR-0037）。画面は reason を言葉に直す
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Calendar Feed Error", "status": 422, "detail": exc.reason.value, "reason": exc.reason.value, "instance": str(request.url.path)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"type": "about:blank", "title": "Conflict", "status": 409, "detail": str(exc), "instance": str(request.url.path)})

    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(RequestLoggingMiddleware)
    # /health はコンテナ内部の healthcheck 用、/api/health は nginx プロキシ経由の
    # 外形監視用（nginx は /api/ プレフィックスを剥がさずそのまま転送する）。
    app.include_router(health.router)
    # App Links の検証ファイル（ADR-0019）。画面の nginx がこの 1 本だけ裏へ渡す
    app.include_router(app_links.router)
    app.include_router(health.router, prefix="/api")
    app.include_router(ops.router)
    # フロントエンドは nginx 経由の /api/ しか届かないため、/info 等も /api 配下に公開する
    app.include_router(ops.router, prefix="/api")
    app.include_router(admin.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(worklogs.router, prefix="/api")
    app.include_router(time_entries.router, prefix="/api")
    app.include_router(closing_periods.router, prefix="/api")
    app.include_router(milestones.router, prefix="/api")
    app.include_router(categories.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(dep_router.router, prefix="/api")
    app.include_router(inbox.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(today.router, prefix="/api")
    app.include_router(gantt.router, prefix="/api")
    app.include_router(actuals.router, prefix="/api")
    app.include_router(reviews.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(push.router, prefix="/api")
    app.include_router(calendar.router, prefix="/api")
    app.include_router(calendars.router, prefix="/api")
    app.include_router(calendars.presets_router, prefix="/api")
    return app


app = create_app()
