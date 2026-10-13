"""WinTrack の更新の置き場の中継（task #384 / ADR-0044）。

``GET /api/wintrack/releases/{file}`` —— Velopack の ``SimpleWebSource`` が版の一覧
（``releases.win.json`` / ``RELEASES``）とパッケージ（``*.nupkg``）を読む。WinTrack は assay の
アクセストークンを付けてくる（``AppOrWebUserDep``、ADR-0018）。返すのは誰にでも同じ配布物で、
利用者ごとの情報は含まない。名前が許されない・設定が無い・配布面が読めないときは 404。

⚠ ``async def`` にしない。配布面の読みは同期（boto3）で数秒かかりうるので、イベントループの上で
走らせると他のリクエストまで止まる。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from src.application.use_cases.wintrack_release_use_cases import IndexFileBody
from src.presentation.api.dependencies import AppOrWebUserDep, WinTrackReleasesDep

router = APIRouter(prefix="/wintrack/releases", tags=["wintrack"])

# 版の一覧は版を出すたびに変わるので、途中で覚えさせない。パッケージは名前ごとに中身が変わらない
_INDEX_CACHE_CONTROL = "no-store"
_PACKAGE_CACHE_CONTROL = "private, max-age=86400, immutable"


@router.get("/{file}", response_class=Response)
def get_wintrack_release_file(
    file: str, releases: WinTrackReleasesDep, _user: AppOrWebUserDep
) -> Response:
    found = releases.fetch(file)
    if isinstance(found, IndexFileBody):
        return Response(
            content=found.body,
            media_type=found.file.media_type,
            headers={"Cache-Control": _INDEX_CACHE_CONTROL},
        )
    headers = {"Cache-Control": _PACKAGE_CACHE_CONTROL}
    if found.stream.size is not None:
        headers["Content-Length"] = str(found.stream.size)
    return StreamingResponse(
        found.stream.chunks, media_type=found.file.media_type, headers=headers
    )
