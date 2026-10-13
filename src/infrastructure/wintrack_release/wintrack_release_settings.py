"""WinTrack の更新の置き場（配布面）を読む設定（task #384 / ADR-0044）。

⚠ **秘密の鍵は値ではなく場所で持つ**（``WINTRACK_RELEASES_S3_SECRET_ACCESS_KEY_FILE``）。
⚠ **鍵には ``artifacts`` の読み取りだけを持たせる**（書ける鍵だと、WBS が破られたときに配る更新をすり替えられる）。
どれかが空なら中継しない（``GET /api/wintrack/releases/*`` は 404）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PREFIX = "wintrack/"


@dataclass(frozen=True)
class WinTrackReleaseSettings:
    #: 配布面（S3 互換。Garage）の URL
    endpoint_url: str = ""
    #: Garage は ``garage``（置き場の ``s3_region`` と揃える）
    region: str = ""
    #: ``artifacts``
    bucket: str = ""
    #: 置き場の中の WinTrack の場所（``wintrack/``）
    prefix: str = DEFAULT_PREFIX
    #: 読む鍵の ID（秘密ではない）
    access_key_id: str = ""
    #: 読む鍵の秘密が入ったファイルのパス
    secret_access_key_file: str = ""

    @property
    def configured(self) -> bool:
        return all(
            (self.endpoint_url, self.bucket, self.access_key_id, self.secret_access_key_file)
        )


def load_wintrack_release_settings() -> WinTrackReleaseSettings:
    prefix = os.getenv("WINTRACK_RELEASES_S3_PREFIX", DEFAULT_PREFIX).strip().strip("/")
    return WinTrackReleaseSettings(
        endpoint_url=os.getenv("WINTRACK_RELEASES_S3_ENDPOINT_URL", "").strip(),
        region=os.getenv("WINTRACK_RELEASES_S3_REGION", "").strip(),
        bucket=os.getenv("WINTRACK_RELEASES_S3_BUCKET", "").strip(),
        prefix=f"{prefix}/" if prefix else "",
        access_key_id=os.getenv("WINTRACK_RELEASES_S3_ACCESS_KEY_ID", "").strip(),
        secret_access_key_file=os.getenv("WINTRACK_RELEASES_S3_SECRET_ACCESS_KEY_FILE", "").strip(),
    )


__all__ = ["DEFAULT_PREFIX", "WinTrackReleaseSettings", "load_wintrack_release_settings"]
