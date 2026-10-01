"""動いているイメージの版（``/info`` と ``/healthz`` が答えるもの）。

出どころは ``src/infrastructure/version.json``。**ビルドの前に**
``scripts/generate_version.sh`` が git から作り、イメージへ入る（ADR-0011。形は
fastapitemplate の ADR-0044 に揃えた）。⚠ ``docker build --build-arg`` では受け取らない
——渡す側ごとに名前がずれて、本番の ``git_sha`` が ``unknown`` のままになった
（task #168）。

ファイルが無い（手元で ``uvicorn`` を直に起こした等）ときは既定値で動く。
環境変数 ``APP_VERSION`` / ``GIT_SHA`` / ``BUILD_TIME`` を置けばそちらが勝つ
（手元で名乗りを変えて確かめるための口。イメージは設定しない）。
"""

import json
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

VERSION_FILE = Path(__file__).with_name("version.json")


@dataclass(frozen=True)
class BuildInfo:
    version: str
    git_sha: str
    build_time: str
    environment: str


def _read_version_file(path: Path) -> dict[str, str]:
    """``version.json`` を読む。無い・壊れているなら空（＝既定値で名乗る）。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: str(value) for key, value in payload.items() if isinstance(value, str) and value}


def load_build_info(version_file: Path | None = None) -> BuildInfo:
    stamped = _read_version_file(version_file or VERSION_FILE)
    try:
        fallback = pkg_version("fastapitemplate")
    except PackageNotFoundError:
        fallback = "0.0.0"

    return BuildInfo(
        version=os.getenv("APP_VERSION", stamped.get("version", fallback)),
        git_sha=os.getenv("GIT_SHA", stamped.get("commit_hash", "dev")),
        build_time=os.getenv("BUILD_TIME", stamped.get("build_date", "unknown")),
        environment=os.getenv("APP_ENV", "development"),
    )
