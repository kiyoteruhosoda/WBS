from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

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
from src.infrastructure.database.session import init_engine
from src.infrastructure.logging.structured_logger import setup_logging
from src.presentation.api.routers import (
    admin,
    auth,
    categories,
    dashboard,
    gantt,
    health,
    inbox,
    milestones,
    ops,
    reviews,
    settings,
    tasks,
    worklogs,
)
from src.presentation.api.routers import dependencies as dep_router
from src.presentation.middleware.logging_middleware import RequestLoggingMiddleware
from src.shared.clock import utcnow


def create_app(database_url: str | None = None, db_path: str | None = None) -> FastAPI:
    setup_logging()
    build_info = load_build_info()
    auth_settings = load_auth_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        url = database_url
        if url is None and db_path is not None:
            url = f"sqlite:///{db_path}"
        init_engine(url)
        yield

    app = FastAPI(
        title="Task Scheduler",
        version=build_info.version,
        description="Task Scheduler API",
        lifespan=lifespan,
    )
    app.state.build_info = build_info
    app.state.startup_time = utcnow()  # ops.py が now との差を取るので形を揃える
    app.state.auth_settings = auth_settings
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

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"type": "about:blank", "title": "Conflict", "status": 409, "detail": str(exc), "instance": str(request.url.path)})

    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(RequestLoggingMiddleware)
    # /health はコンテナ内部の healthcheck 用、/api/health は nginx プロキシ経由の
    # 外形監視用（nginx は /api/ プレフィックスを剥がさずそのまま転送する）。
    app.include_router(health.router)
    app.include_router(health.router, prefix="/api")
    app.include_router(ops.router)
    # フロントエンドは nginx 経由の /api/ しか届かないため、/info 等も /api 配下に公開する
    app.include_router(ops.router, prefix="/api")
    app.include_router(admin.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(worklogs.router, prefix="/api")
    app.include_router(milestones.router, prefix="/api")
    app.include_router(categories.router, prefix="/api")
    app.include_router(dep_router.router, prefix="/api")
    app.include_router(inbox.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(gantt.router, prefix="/api")
    app.include_router(reviews.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    return app


app = create_app()
