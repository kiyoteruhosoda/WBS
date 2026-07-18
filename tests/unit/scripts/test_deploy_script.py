from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy.sh"


@dataclass(frozen=True)
class DeployProfile:
    """Directory-driven deploy profile used by the shell script."""

    name: str
    project: str
    default_web_port: str


STG = DeployProfile(name="stg", project="wbs-stg", default_web_port="8101")
PROD = DeployProfile(name="prod", project="wbs", default_web_port="8100")


class FakeDeployHost:
    """A disposable host bundle with fake Docker/Curl commands."""

    def __init__(self, tmp_path: Path, profile: DeployProfile) -> None:
        self.profile = profile
        self.root = tmp_path / "wbs" / profile.name
        self.scripts_dir = self.root / "scripts"
        self.bin_dir = tmp_path / "bin"
        self.command_log = tmp_path / "commands.log"

    def prepare(self) -> None:
        self.scripts_dir.mkdir(parents=True)
        self.bin_dir.mkdir()
        shutil.copy2(DEPLOY_SCRIPT, self.scripts_dir / "deploy.sh")
        (self.scripts_dir / "deploy.sh").chmod(0o755)
        (self.root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
        (self.root / ".image-version").write_text("v-test\n", encoding="utf-8")
        self._write_executable("docker", self._docker_stub())
        self._write_executable("curl", self._curl_stub())

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"
        env["FAKE_DOCKER_LOG"] = str(self.command_log)
        return subprocess.run(
            [str(self.scripts_dir / "deploy.sh"), *args],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def logged_commands(self) -> str:
        return self.command_log.read_text(encoding="utf-8")

    def _write_executable(self, name: str, content: str) -> None:
        path = self.bin_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    @staticmethod
    def _curl_stub() -> str:
        return """#!/usr/bin/env bash
set -eu
echo "curl $*" >> "$FAKE_DOCKER_LOG"
exit 0
"""

    @staticmethod
    def _docker_stub() -> str:
        return """#!/usr/bin/env bash
set -eu
echo "docker $*" >> "$FAKE_DOCKER_LOG"
case "${1:-}" in
  info)
    exit 0
    ;;
  image)
    case "${2:-}" in
      inspect|prune) exit 0 ;;
    esac
    ;;
  compose)
    shift
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -p|-f|--env-file)
          shift 2
          ;;
        *)
          break
          ;;
      esac
    done
    case "${1:-}" in
      down|up|ps|logs|exec)
        exit 0
        ;;
    esac
    ;;
esac
echo "unexpected docker invocation: $*" >&2
exit 64
"""


def test_deploy_app_uses_directory_profile_without_environment_argument(tmp_path: Path) -> None:
    host = FakeDeployHost(tmp_path, STG)
    host.prepare()

    result = host.run("app")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Deploy complete (mode: app)" in result.stdout
    env_lines = (host.root / ".env").read_text(encoding="utf-8").splitlines()
    assert env_lines[0] == "# Auto-generated WBS deploy env (env: stg)."
    assert f"HOST_DATA_ROOT={host.root}/mnt" in env_lines
    assert f"WEB_HOST_PORT={STG.default_web_port}" in env_lines
    commands = host.logged_commands()
    assert "docker compose -p wbs-stg" in commands
    assert "docker image inspect wbs-api:stg" in commands
    assert "docker image inspect wbs-web:stg" in commands
    assert f"curl -fs http://127.0.0.1:{STG.default_web_port}/api/health" in commands


def test_deploy_migrate_runs_schema_sync_for_prod_profile(tmp_path: Path) -> None:
    host = FakeDeployHost(tmp_path, PROD)
    host.prepare()

    result = host.run("migrate")

    assert result.returncode == 0, result.stderr + result.stdout
    commands = host.logged_commands()
    assert "docker compose -p wbs " in commands
    assert " exec -T api python scripts/run_db_migrations.py" in commands
    assert f"curl -fs http://127.0.0.1:{PROD.default_web_port}/api/health" in commands


def test_deploy_reset_removes_data_before_recreating_it(tmp_path: Path) -> None:
    host = FakeDeployHost(tmp_path, STG)
    host.prepare()
    data_path = host.root / "mnt" / "data"
    stale_file = data_path / "stale.txt"
    data_path.mkdir(parents=True)
    stale_file.write_text("old", encoding="utf-8")

    result = host.run("reset")

    assert result.returncode == 0, result.stderr + result.stdout
    assert data_path.is_dir()
    assert not stale_file.exists()
    assert " exec -T api python scripts/run_db_migrations.py" in host.logged_commands()


def test_deploy_rejects_environment_argument(tmp_path: Path) -> None:
    host = FakeDeployHost(tmp_path, STG)
    host.prepare()

    result = host.run("stg", "app")

    assert result.returncode == 1
    assert "Exactly one mode argument is required." in result.stderr
    assert "Usage:" in result.stderr
