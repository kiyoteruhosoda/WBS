"""Precedence of ``scripts/generate_version.sh`` (git > existing version.json > dev).

task #168, ADR-0011. The script is copied to the root of a throwaway repository and run there.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "generate_version.sh"
STAMP = Path("src") / "infrastructure" / "version.json"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, project / "scripts" / "generate_version.sh")
    return project


def _run(project: Path, **env: str) -> dict[str, str]:
    subprocess.run(
        ["bash", str(project / "scripts" / "generate_version.sh")],
        check=True,
        capture_output=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", **env},
    )
    return json.loads((project / STAMP).read_text(encoding="utf-8"))


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(project), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_without_git_or_file_it_stamps_dev(tmp_path) -> None:
    stamped = _run(_project(tmp_path))

    assert stamped["version"] == "dev"
    assert stamped["commit_hash"] == "dev"
    assert stamped["build_date"].endswith("Z")


def test_inside_the_image_it_keeps_what_the_build_stamped(tmp_path) -> None:
    # Inside the image (no .git), do not overwrite the content stamped before the build with dev
    project = _project(tmp_path)
    (project / STAMP).parent.mkdir(parents=True)
    original = '{"version": "abc1234", "commit_hash": "abc1234", "build_date": "2026-10-01T00:00:00Z"}\n'
    (project / STAMP).write_text(original, encoding="utf-8")

    _run(project)

    assert (project / STAMP).read_text(encoding="utf-8") == original


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
def test_with_git_it_stamps_the_commit_and_overwrites_a_stale_file(tmp_path) -> None:
    project = _project(tmp_path)
    _git(project, "init", "-q", "-b", "main")
    _git(project, "add", "scripts")
    _git(project, "commit", "-q", "-m", "init")
    _git(project, "checkout", "-q", "--detach")  # same shape as the deck/CI checkout
    (project / STAMP).parent.mkdir(parents=True)
    (project / STAMP).write_text('{"version": "old", "commit_hash": "old"}', encoding="utf-8")

    stamped = _run(project, BRANCH_OVERRIDE="main")

    head = _git(project, "rev-parse", "HEAD")
    assert stamped["commit_hash_full"] == head
    assert stamped["commit_hash"] == head[: len(stamped["commit_hash"])]
    assert stamped["branch"] == "main"
    assert stamped["version"] == stamped["commit_hash"]
