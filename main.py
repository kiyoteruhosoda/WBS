from __future__ import annotations
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from src.infrastructure.build_info import load_build_info
from src.infrastructure.database.session import init_engine
from src.infrastructure.logging.structured_logger import setup_logging
from src.presentation.api.routers import admin, health, ops
from src.presentation.api.routers import tasks, worklogs, milestones, categories
from src.presentation.api.routers import dependencies as dep_router, inbox, dashboard, gantt, reviews
from src.presentation.middleware.logging_middleware import RequestLoggingMiddleware
from src.domain.exceptions import NotFoundError, ValidationError, ConflictError


def create_app(database_url: str | None = None, db_path: str | None = None) -> FastAPI:
    setup_logging()
    build_info = load_build_info()

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
    app.state.startup_time = datetime.now(UTC)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"type": "about:blank", "title": "Not Found", "status": 404, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Validation Error", "status": 422, "detail": str(exc), "instance": str(request.url.path)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"type": "about:blank", "title": "Conflict", "status": 409, "detail": str(exc), "instance": str(request.url.path)})

    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.include_router(ops.router)
    app.include_router(admin.router)
    app.include_router(tasks.router, prefix="/api")
    app.include_router(worklogs.router, prefix="/api")
    app.include_router(milestones.router, prefix="/api")
    app.include_router(categories.router, prefix="/api")
    app.include_router(dep_router.router, prefix="/api")
    app.include_router(inbox.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(gantt.router, prefix="/api")
    app.include_router(reviews.router, prefix="/api")
    return app


app = create_app()
