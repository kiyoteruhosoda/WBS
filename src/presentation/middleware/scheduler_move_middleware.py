"""予定まわりの口の関所（task #535 / Scheduler の ADR-0054 決定 3。WBS の ADR-0054）。

予定まわりの口（予定・カレンダー・表示の組み合わせ）だけを見る。ほかの口には触らない
（打刻まわりは Tracker の関所 ``tracker_move_middleware.py`` が見る。道が重ならないので、2 つは互いに触らない）。

| 設定 | Bearer（wbstimer） | Cookie（WBS の画面） |
|---|---|---|
| どちらも無い（既定） | 今までどおり | 今までどおり |
| ``SCHEDULER_CUTOVER_HOLD`` | 書き込みは 503（``Retry-After``）。読むのは通す | 同じ |
| ``SCHEDULER_FORWARD_URL`` | 予定のアラームの口だけ Scheduler へ中継。ほかの書き込みは 409 | 書き込みは 409。読むのは通す |

⚠ **中継では WBS は名乗らない。** 届いた ``Authorization`` をそのまま渡し、トークンは Scheduler が確かめる。
中継した数を 1 件ずつログに残す（``event=scheduler.relay``。古い端末が来なくなった＝14 日 0 を数える）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.application.ports.scheduler_relay import (
    SchedulerRelay,
    SchedulerRelayRequest,
    SchedulerUnreachableError,
)
from src.infrastructure.scheduler_move.scheduler_move_settings import SchedulerMoveSettings

logger = logging.getLogger(__name__)

#: 予定まわりの口（書き込みを 503・409 にする範囲）
CALENDAR_ROUTES = (
    "/api/calendar",
    "/api/calendars",
    "/api/calendar-view-presets",
)
#: Bearer で来たら Scheduler へ中継する口。予定まわりで Bearer を受けるのはこれだけ（ADR-0018・0021）
RELAYED_ROUTES = ("/api/calendar/alarms",)
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
#: 409 の ``detail``。画面はこの文で理由を見分ける（``frontend/src/scheduler/schedulerMove.ts``）
MOVED_DETAIL = "Calendar has moved to Scheduler ({host})"
HELD_DETAIL = "Calendar is being moved to Scheduler; send it again shortly"


def _under(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in prefixes)


def claimed_client_id(authorization: str) -> str:
    """トークンが名乗る ``client_id``（ログの見出しだけ。⚠ 確かめていない。確かめるのは Scheduler）。"""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return "-"
    try:
        claims = jwt.decode(token.strip(), options={"verify_signature": False})
    except jwt.PyJWTError:
        return "-"
    return str(claims.get("client_id") or claims.get("azp") or "-")


def _problem(status: int, title: str, detail: str, path: str, reason: str, **extra: object) -> dict:
    return {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "reason": reason,
        "instance": path,
        **extra,
    }


class SchedulerMoveMiddleware(BaseHTTPMiddleware):
    """設定と中継の口は ``app.state``（``scheduler_move_settings``・``scheduler_relay``。試験は差し替える）。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not _under(path, CALENDAR_ROUTES):
            return await call_next(request)
        settings: SchedulerMoveSettings = request.app.state.scheduler_move_settings
        writing = request.method not in READ_METHODS
        if settings.cutover_hold and writing:
            return JSONResponse(
                status_code=503,
                content=_problem(
                    503, "Service Unavailable", HELD_DETAIL, path, "scheduler_cutover"
                ),
                headers={"Retry-After": str(settings.retry_after_seconds)},
            )
        if not settings.moved:
            return await call_next(request)
        authorization = request.headers.get("authorization")
        if authorization is not None and _under(path, RELAYED_ROUTES):
            return await self._relay(request, request.app.state.scheduler_relay, authorization)
        if writing:
            host = settings.public_url.split("://", 1)[-1]
            return JSONResponse(
                status_code=409,
                content=_problem(
                    409,
                    "Conflict",
                    MOVED_DETAIL.format(host=host),
                    path,
                    "moved_to_scheduler",
                    scheduler_url=settings.public_url,
                ),
            )
        # 読むのは通す（移した時点で凍った値。画面は移転モードでは読まない）
        return await call_next(request)

    async def _relay(self, request: Request, relay: SchedulerRelay, authorization: str) -> Response:
        started = time.perf_counter()
        # 中継する口は 1 つで番号も日付も入らないので、道をそのまま口の名前にする
        route = request.url.path
        client_id = claimed_client_id(authorization)
        try:
            answer = await relay.relay(
                SchedulerRelayRequest(
                    method=request.method,
                    path=route,
                    query=request.url.query,
                    headers={k.lower(): v for k, v in request.headers.items()},
                    body=await request.body(),
                )
            )
        except SchedulerUnreachableError as exc:
            logger.warning(
                "Scheduler へ中継できませんでした",
                extra={
                    "event": "scheduler.relay.failed",
                    "method": request.method,
                    "route": route,
                    "client_id": client_id,
                    "error": str(exc),
                },
            )
            # 5xx なので端末は手元のアラームを残して引き直す
            return JSONResponse(
                status_code=502,
                content=_problem(
                    502,
                    "Bad Gateway",
                    "Scheduler did not answer",
                    route,
                    "scheduler_unreachable",
                ),
            )
        logger.info(
            "Scheduler へ中継しました",
            extra={
                "event": "scheduler.relay",
                "method": request.method,
                "route": route,
                "client_id": client_id,
                "status_code": answer.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return Response(
            content=answer.body, status_code=answer.status_code, headers=dict(answer.headers)
        )


__all__ = [
    "CALENDAR_ROUTES",
    "HELD_DETAIL",
    "MOVED_DETAIL",
    "READ_METHODS",
    "RELAYED_ROUTES",
    "SchedulerMoveMiddleware",
    "claimed_client_id",
]
