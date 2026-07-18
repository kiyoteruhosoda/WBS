#!/usr/bin/env python3
"""Build orchestrator for the WBS application.

The script models each build concern as a small polymorphic BuildStep so the
pipeline can grow without turning into a long procedural shell script.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEFAULT_ARTIFACT_DIR = ROOT / "dist" / "deploy"


@dataclass(frozen=True)
class Toolchain:
    """Resolve external build tools without assuming uv is installed."""

    python: str
    uv: str | None

    @classmethod
    def detect(cls) -> Toolchain:
        return cls(python=sys.executable, uv=shutil.which("uv"))

    def python_module(self, module: str, *args: str) -> tuple[str, ...]:
        if self.uv:
            return (self.uv, "run", module, *args)
        return (self.python, "-m", module, *args)

    def has_modules(self, *modules: str) -> bool:
        return all(importlib.util.find_spec(module) is not None for module in modules)


@dataclass(frozen=True)
class BuildContext:
    target: str
    skip_tests: bool
    skip_frontend_install: bool
    env: dict[str, str]
    toolchain: Toolchain
    app_version: str
    artifact_dir: Path

    @property
    def api_image(self) -> str:
        return f"wbs-api:{self.app_version}"

    @property
    def web_image(self) -> str:
        return f"wbs-web:{self.app_version}"


class BuildStep(ABC):
    """A single build pipeline step."""

    name: str

    @abstractmethod
    def supports(self, context: BuildContext) -> bool:
        """Return whether this step should run for the requested build target."""

    @abstractmethod
    def command(self, context: BuildContext) -> Sequence[str]:
        """Return the command for this build step."""

    def cwd(self) -> Path:
        return ROOT

    def run(self, context: BuildContext) -> None:
        if not self.supports(context):
            return
        command = list(self.command(context))
        print(f"\n==> {self.name}: {' '.join(command)}", flush=True)
        try:
            subprocess.run(command, cwd=self.cwd(), env=context.env, check=True)
        except FileNotFoundError as exc:
            missing = exc.filename or command[0]
            raise SystemExit(
                f"Required command not found: {missing}. "
                "Install the tool or choose a target that does not need it."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise SystemExit(f"Build step failed: {self.name} (exit code {exc.returncode})") from exc


class BackendStep(BuildStep):
    def supports(self, context: BuildContext) -> bool:
        return context.target in {"all", "api"}


class FrontendStep(BuildStep):
    def supports(self, context: BuildContext) -> bool:
        return context.target in {"all", "web"}

    def cwd(self) -> Path:
        return FRONTEND


class BackendDependencies(BackendStep):
    name = "backend dependencies"

    def supports(self, context: BuildContext) -> bool:
        if not super().supports(context):
            return False
        # With uv, always sync so the environment matches the lockfile before
        # lint/test run. Relying on `uv run`'s implicit sync is not enough: an
        # active or pre-existing virtualenv is used as-is and may miss
        # dependencies added after it was created.
        if context.toolchain.uv is not None:
            return True
        # Without uv, only install when the backend toolchain is not already
        # importable, to keep repeated local builds fast.
        return not context.toolchain.has_modules("ruff", "pytest", "httpx")

    def command(self, context: BuildContext) -> Sequence[str]:
        if context.toolchain.uv is not None:
            return (context.toolchain.uv, "sync", "--frozen")
        return (
            context.toolchain.python,
            "-m",
            "pip",
            "install",
            "-e",
            ".",
            "ruff>=0.11.0",
            "pytest>=9.0.3",
            "httpx>=0.28.1",
        )


class RuffCheck(BackendStep):
    name = "backend lint"

    def command(self, context: BuildContext) -> Sequence[str]:
        return context.toolchain.python_module("ruff", "check", ".")


class Pytest(BackendStep):
    name = "backend tests"

    def supports(self, context: BuildContext) -> bool:
        return super().supports(context) and not context.skip_tests

    def command(self, context: BuildContext) -> Sequence[str]:
        return context.toolchain.python_module("pytest")


class FrontendInstall(FrontendStep):
    name = "frontend dependencies"

    def supports(self, context: BuildContext) -> bool:
        return super().supports(context) and not context.skip_frontend_install

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("npm", "install")


class FrontendBuild(FrontendStep):
    name = "frontend build"

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("npm", "run", "build")


class DockerBuild(BuildStep):
    name = "docker compose build"

    def supports(self, context: BuildContext) -> bool:
        return context.target in {"docker", "deploy"}

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("docker", "compose", "build", "api", "web")


class DockerSave(BuildStep):
    name = "docker image export"

    def supports(self, context: BuildContext) -> bool:
        return context.target == "deploy"

    def command(self, context: BuildContext) -> Sequence[str]:
        context.artifact_dir.mkdir(parents=True, exist_ok=True)
        return (
            "docker",
            "save",
            "-o",
            str(context.artifact_dir / "image.tar"),
            context.api_image,
            context.web_image,
        )


class DeployBundle(BuildStep):
    name = "deploy bundle"

    def supports(self, context: BuildContext) -> bool:
        return context.target == "deploy"

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("write-deploy-bundle", str(context.artifact_dir))

    def run(self, context: BuildContext) -> None:
        if not self.supports(context):
            return
        context.artifact_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = context.artifact_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        compose = context.artifact_dir / "docker-compose.yml"
        compose.write_text(
            """services:
  api:
    image: ${API_IMAGE}
    environment:
      DATABASE_URL: ${DATABASE_URL:-sqlite:////app/data/app.db}
      ADMIN_EMAIL: ${ADMIN_EMAIL:-local@example.com}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-local-dev-password}
    volumes:
      - ${HOST_DATA_ROOT}/data:/app/data
    # API はネットワーク内部からのみ到達可能にする。外部公開は web (nginx) が
    # /api/ プロキシで受け持つため、ホストポートは開けない。
    expose:
      - "8000"
    command: ["/app/scripts/entrypoint.sh", "${APP_MODE:-app}"]
    # ホスト再起動・コンテナ異常終了後も自動で立ち上がる（デプロイ後の手動操作を不要にする）。
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \\"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\\""]
      interval: 30s
      timeout: 10s
      retries: 5
      # entrypoint が起動時に DB マイグレーションを実行するため、その完了まで
      # unhealthy と誤判定されないよう余裕を持たせる。start_period 中も probe は
      # interval ごとに走り、成功すれば即 healthy になる。
      start_period: 120s
  web:
    image: ${WEB_IMAGE}
    ports:
      - "${WEB_HOST_PORT:-8100}:80"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      # nginx → api のプロキシ経路ごと疎通確認する（busybox wget）。
      test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
""",
            encoding="utf-8",
        )
        deploy_script = ROOT / "scripts" / "deploy.sh"
        target_deploy_script = scripts_dir / "deploy.sh"
        shutil.copy2(deploy_script, target_deploy_script)
        target_deploy_script.chmod(0o755)
        entrypoint = context.artifact_dir / "entrypoint.sh"
        entrypoint.write_text(
            """#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/scripts/deploy.sh" "${1:-app}"
""",
            encoding="utf-8",
        )
        entrypoint.chmod(0o755)
        (context.artifact_dir / ".image-version").write_text(
            f"{context.app_version}\n", encoding="utf-8"
        )
        readme = context.artifact_dir / "README.md"
        readme.write_text(
            f"""# WBS deploy bundle

Copy this directory contents to `wbs/<stg|prod>/` on the deployment host and run:

```bash
./scripts/deploy.sh app
# or: ./entrypoint.sh app
```

Modes:
- `app`: normal deployment
- `migrate`: start containers and run schema sync
- `reset`: delete mounted SQLite data and rebuild schema (destructive)

Files:
- `image.tar`: Docker image archive for `{context.api_image}` and `{context.web_image}`
- `.image-version`: source image tag used for env-specific retagging
- `docker-compose.yml`: host compose file using `API_IMAGE` / `WEB_IMAGE` exported by deploy script
- `scripts/deploy.sh`: stg/prod aware host deploy script; pass only app/migrate/reset
- `entrypoint.sh`: thin wrapper around `scripts/deploy.sh`
""",
            encoding="utf-8",
        )
        print(f"\n==> {self.name}: wrote {context.artifact_dir}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build WBS API, web, or Docker images.")
    parser.add_argument(
        "--target",
        choices=("all", "api", "web", "docker", "deploy"),
        default="deploy",
        help="Build target. Defaults to deploy, which exports Docker images and host entrypoint.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip backend pytest execution for faster local builds.",
    )
    parser.add_argument(
        "--skip-frontend-install",
        action="store_true",
        help="Skip npm install when node_modules is already prepared.",
    )
    parser.add_argument(
        "--app-version",
        default=os.getenv("APP_VERSION", "local"),
        help="Docker image tag used by docker/deploy targets.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Directory for deploy artifacts produced by --target deploy.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = BuildContext(
        target=args.target,
        skip_tests=args.skip_tests,
        skip_frontend_install=args.skip_frontend_install,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        toolchain=Toolchain.detect(),
        app_version=args.app_version,
        artifact_dir=args.artifact_dir,
    )
    steps: tuple[BuildStep, ...] = (
        BackendDependencies(),
        RuffCheck(),
        Pytest(),
        FrontendInstall(),
        FrontendBuild(),
        DockerBuild(),
        DockerSave(),
        DeployBundle(),
    )
    for step in steps:
        step.run(context)


if __name__ == "__main__":
    main()
