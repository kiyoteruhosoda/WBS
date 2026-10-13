"""配布面（S3 互換の置き場。Garage）から WinTrack の更新の置き場のファイルを読む（ADR-0044）。

fastapitemplate の ADR-0048（``S3LatestReleaseSource``）と同じ形: boto3・パスに載せる番地・短い待ち時間・
秘密の鍵は読むたびにファイルから取る（鍵を回したら、ファイルを差し替えれば次の読みから効く）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.application.ports.release_file_store import (
    ReleaseFileStream,
    ReleaseFileUnavailableError,
)
from src.infrastructure.wintrack_release.wintrack_release_settings import WinTrackReleaseSettings

#: 置き場への接続の待ち時間（秒）。PC は答えを待っているので長く待たせない
_CONNECT_TIMEOUT_SECONDS = 3
#: 読みの待ち時間（秒）。パッケージは大きいので、塊ごとの待ちとして少し長く取る
_READ_TIMEOUT_SECONDS = 20
#: パッケージを流す塊の大きさ
_CHUNK_BYTES = 1024 * 1024


class S3ReleaseFileStore:
    def __init__(self, settings: WinTrackReleaseSettings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return self._settings.configured

    def read(self, name: str, max_bytes: int) -> bytes:
        body = self._get(name)["Body"]
        try:
            data = body.read(max_bytes + 1)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ReleaseFileUnavailableError(f"cannot read {self._where(name)}: {exc}") from exc
        finally:
            body.close()
        if not isinstance(data, bytes):
            raise ReleaseFileUnavailableError("the object body is not bytes")
        if len(data) > max_bytes:
            raise ReleaseFileUnavailableError(f"{self._where(name)} is larger than {max_bytes} bytes")
        return data

    def open(self, name: str) -> ReleaseFileStream:
        response = self._get(name)
        size = response.get("ContentLength")
        return ReleaseFileStream(
            size=size if isinstance(size, int) else None,
            chunks=_chunks(response["Body"]),
        )

    def _get(self, name: str) -> dict[str, Any]:
        client = boto3.client(
            "s3",
            endpoint_url=self._settings.endpoint_url,
            region_name=self._settings.region or None,
            aws_access_key_id=self._settings.access_key_id,
            aws_secret_access_key=self._secret_access_key(),
            config=Config(
                # Garage はバケット名をホスト名に載せる形（virtual-hosted）を名前解決できない。パスに載せる
                s3={"addressing_style": "path"},
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                read_timeout=_READ_TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        try:
            return client.get_object(Bucket=self._settings.bucket, Key=self._key(name))
        except (BotoCoreError, ClientError) as exc:
            raise ReleaseFileUnavailableError(f"cannot read {self._where(name)}: {exc}") from exc

    def _secret_access_key(self) -> str:
        path = self._settings.secret_access_key_file
        try:
            secret = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            # パスは秘密ではないので出してよい（どこを直せばよいかが分かる）
            raise ReleaseFileUnavailableError(
                f"cannot read the secret access key file {path}: {exc.strerror}"
            ) from exc
        if not secret:
            raise ReleaseFileUnavailableError(f"the secret access key file {path} is empty")
        return secret

    def _key(self, name: str) -> str:
        return f"{self._settings.prefix}{name}"

    def _where(self, name: str) -> str:
        return f"s3://{self._settings.bucket}/{self._key(name)} at {self._settings.endpoint_url}"


def _chunks(body: Any) -> Iterator[bytes]:
    try:
        yield from body.iter_chunks(_CHUNK_BYTES)
    finally:
        body.close()


__all__ = ["S3ReleaseFileStore"]
