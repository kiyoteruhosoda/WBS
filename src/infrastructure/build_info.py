"""Version of the running image (what ``/info`` and ``/healthz`` report).

The source is ``src/infrastructure/version.json``. **Before the build**,
``scripts/generate_version.sh`` creates it from git and it goes into the image (ADR-0011; the shape
follows fastapitemplate ADR-0044). ⚠ It is not taken via ``docker build --build-arg``
-- names drifted between the callers and production's ``git_sha`` stayed ``unknown``
(task #168).

Without the file (e.g. ``uvicorn`` started directly on a dev machine) it runs with defaults.
Setting the env vars ``APP_VERSION`` / ``GIT_SHA`` / ``BUILD_TIME`` overrides them
(a hook to change the reported identity for local checks; images do not set them).
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
    """Read ``version.json``. Empty if missing or broken (= report the defaults)."""
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
