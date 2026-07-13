#!/usr/bin/env python3
"""Build orchestrator for the WBS application.

The script models each build concern as a small polymorphic BuildStep so the
pipeline can grow without turning into a long procedural shell script.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


@dataclass(frozen=True)
class BuildContext:
    target: str
    skip_tests: bool
    skip_frontend_install: bool
    env: dict[str, str]


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
        subprocess.run(command, cwd=self.cwd(), env=context.env, check=True)


class BackendStep(BuildStep):
    def supports(self, context: BuildContext) -> bool:
        return context.target in {"all", "api"}


class FrontendStep(BuildStep):
    def supports(self, context: BuildContext) -> bool:
        return context.target in {"all", "web"}

    def cwd(self) -> Path:
        return FRONTEND


class RuffCheck(BackendStep):
    name = "backend lint"

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("uv", "run", "ruff", "check", ".")


class Pytest(BackendStep):
    name = "backend tests"

    def supports(self, context: BuildContext) -> bool:
        return super().supports(context) and not context.skip_tests

    def command(self, context: BuildContext) -> Sequence[str]:
        return ("uv", "run", "pytest")


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
    )
    steps: tuple[BuildStep, ...] = (
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
