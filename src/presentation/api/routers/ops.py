from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.presentation.api.dependencies import get_db
from src.presentation.api.schemas.ops import InfoResponse, LivenessResponse, ReadinessResponse

router = APIRouter(tags=["ops"])

@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe", description="Always returns 200 while the process is running.")
async def liveness(request: Request) -> LivenessResponse:
    now = datetime.now(UTC)
    build_info = request.app.state.build_info
    startup_time = request.app.state.startup_time
    return LivenessResponse(status="ok", version=build_info.version, timestamp_utc=now.isoformat(), uptime_seconds=(now - startup_time).total_seconds())

@router.get("/readyz", summary="Readiness probe")
async def readiness(request: Request, db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    now = datetime.now(UTC)
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "ng"
    all_ok = all(v == "ok" for v in checks.values())
    body = ReadinessResponse(status="ok" if all_ok else "ng", checks=checks, timestamp_utc=now.isoformat())
    return JSONResponse(status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump())

@router.get("/info", response_model=InfoResponse, summary="Build / version info")
async def info(request: Request) -> InfoResponse:
    build_info = request.app.state.build_info
    return InfoResponse(version=build_info.version, git_sha=build_info.git_sha, build_time=build_info.build_time, environment=build_info.environment)
