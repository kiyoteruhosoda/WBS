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
        return (
            super().supports(context)
            and context.toolchain.uv is None
            and not context.toolchain.has_modules("ruff", "pytest", "httpx")
        )

    def command(self, context: BuildContext) -> Sequence[str]:
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
        install_command = "ci" if (FRONTEND / "package-lock.json").exists() else "install"
        return ("npm", install_command)


class FrontendBuild(FrontendStep):
    name = "frontend build"

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("npm", "run", "build")


class DockerBuild(BuildStep):
    name = "docker compose build"

    def supports(self, context: BuildContext) -> bool:
        return context.target == "docker"

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("docker", "compose", "build")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build WBS API, web, or Docker images.")
    parser.add_argument(
        "--target",
        choices=("all", "api", "web", "docker"),
        default="all",
        help="Build target. Defaults to all local build targets.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip backend pytest execution for faster local builds.",
    )
    parser.add_argument(
        "--skip-frontend-install",
        action="store_true",
        help="Skip npm install/npm ci when node_modules is already prepared.",
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
    )
    steps: tuple[BuildStep, ...] = (
        BackendDependencies(),
        RuffCheck(),
        Pytest(),
        FrontendInstall(),
        FrontendBuild(),
        DockerBuild(),
    )
    for step in steps:
        step.run(context)


if __name__ == "__main__":
    main()
