"""打刻まわりの口の関所（task #526 / ADR-0053 決定 3。WBS の ADR-0053）。

打刻まわりの口（打刻・休み・PC を使っていた時間・自動記録の規則・締め）だけを見る。ほかの口には触らない。

| 設定 | Bearer（wbstimer・WinTrack） | Cookie（WBS の画面） |
|---|---|---|
| どちらも無い（既定） | 今までどおり | 今までどおり |
| ``TRACKER_CUTOVER_HOLD`` | 書き込みは 503（``Retry-After``）。読むのは通す | 同じ |
| ``TRACKER_FORWARD_URL`` | Tracker へ中継（読みも書きも。締めの口は中継しない） | 書き込みは 409。読むのは通す |

⚠ **503 にするのは、3 つの端末とも 5xx を「あとで送り直す」として手元に残すから**（409 / 422 は捨てる）。
⚠ **中継では WBS は名乗らない。** 届いた ``Authorization`` をそのまま渡し、トークンは Tracker が確かめる。
中継した数を 1 件ずつログに残す（``event=tracker.relay``。古い端末が来なくなった＝14 日 0 を数える）。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.application.ports.tracker_relay import RelayRequest, TrackerRelay, TrackerUnreachableError
from src.infrastructure.tracker_move.tracker_move_settings import TrackerMoveSettings

logger = logging.getLogger(__name__)

#: 打刻まわりの口（書き込みを 503・409 にする範囲）
TRACKING_ROUTES = (
    "/api/time-entries",
    "/api/breaks",
    "/api/pc-activity",
    "/api/tracking-rules",
    "/api/closing-periods",
)
#: Bearer で来たら Tracker へ中継する口（締めは画面だけの口なので中継しない）
RELAYED_ROUTES = (
    "/api/time-entries",
    "/api/breaks",
    "/api/pc-activity",
    "/api/tracking-rules",
)
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
#: 409 の ``detail``。画面はこの文で理由を見分ける（``frontend/src/timer/timerState.ts``）
MOVED_DETAIL = "Time tracking has moved to Tracker ({host})"
HELD_DETAIL = "Time tracking is being moved to Tracker; send it again shortly"

_ID_SEGMENT = re.compile(r"^\d+$")
_DAY_SEGMENT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _under(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in prefixes)


def route_label(path: str) -> str:
    """ログに残す口の名前（番号と日付を伏せて、口ごとに数えられるようにする）。"""
    segments = [
        "{id}" if _ID_SEGMENT.match(s) else "{day}" if _DAY_SEGMENT.match(s) else s
        for s in path.split("/")
    ]
    return "/".join(segments)


def claimed_client_id(authorization: str) -> str:
    """トークンが名乗る ``client_id``（ログの見出しだけ。⚠ 確かめていない。確かめるのは Tracker）。"""
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


class TrackerMoveMiddleware(BaseHTTPMiddleware):
    """設定と中継の口は ``app.state``（``tracker_move_settings``・``tracker_relay``。試験は差し替える）。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not _under(path, TRACKING_ROUTES):
            return await call_next(request)
        settings: TrackerMoveSettings = request.app.state.tracker_move_settings
        writing = request.method not in READ_METHODS
        if settings.cutover_hold and writing:
            return JSONResponse(
                status_code=503,
                content=_problem(503, "Service Unavailable", HELD_DETAIL, path, "tracker_cutover"),
                headers={"Retry-After": str(settings.retry_after_seconds)},
            )
        if not settings.moved:
            return await call_next(request)
        authorization = request.headers.get("authorization")
        if authorization is not None and _under(path, RELAYED_ROUTES):
            return await self._relay(request, request.app.state.tracker_relay, authorization)
        if writing:
            host = settings.public_url.split("://", 1)[-1]
            return JSONResponse(
                status_code=409,
                content=_problem(
                    409,
                    "Conflict",
                    MOVED_DETAIL.format(host=host),
                    path,
                    "moved_to_tracker",
                    tracker_url=settings.public_url,
                ),
            )
        # 読むのは通す（移した時点で凍った値。画面は移転モードでは読まない）
        return await call_next(request)

    async def _relay(self, request: Request, relay: TrackerRelay, authorization: str) -> Response:
        started = time.perf_counter()
        label = route_label(request.url.path)
        client_id = claimed_client_id(authorization)
        try:
            answer = await relay.relay(
                RelayRequest(
                    method=request.method,
                    path=request.url.path,
                    query=request.url.query,
                    headers={k.lower(): v for k, v in request.headers.items()},
                    body=await request.body(),
                )
            )
        except TrackerUnreachableError as exc:
            logger.warning(
                "Tracker へ中継できませんでした",
                extra={
                    "event": "tracker.relay.failed",
                    "method": request.method,
                    "route": label,
                    "client_id": client_id,
                    "error": str(exc),
                },
            )
            # 5xx なので端末は手元に残して送り直す
            return JSONResponse(
                status_code=502,
                content=_problem(
                    502,
                    "Bad Gateway",
                    "Tracker did not answer",
                    request.url.path,
                    "tracker_unreachable",
                ),
            )
        logger.info(
            "Tracker へ中継しました",
            extra={
                "event": "tracker.relay",
                "method": request.method,
                "route": label,
                "client_id": client_id,
                "status_code": answer.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return Response(
            content=answer.body, status_code=answer.status_code, headers=dict(answer.headers)
        )


__all__ = [
    "HELD_DETAIL",
    "MOVED_DETAIL",
    "READ_METHODS",
    "RELAYED_ROUTES",
    "TRACKING_ROUTES",
    "TrackerMoveMiddleware",
    "claimed_client_id",
    "route_label",
]
