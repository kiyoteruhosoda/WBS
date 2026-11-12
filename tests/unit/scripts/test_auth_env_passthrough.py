"""Does compose really pass the environment variables the settings read into the container?

A key missing from compose's ``environment:`` does not arrive even if written in ``.env``.
When this happens to auth settings, it is the hardest breakage to notice: "AUTH_MODE=oidc was written but
it starts without auth" (startup and health checks both pass), so
the comparison is watched by a machine.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SETTINGS_SOURCES = (
    ROOT / "src" / "infrastructure" / "auth" / "auth_settings.py",
)
COMPOSE_FILES = (
    ROOT / "docker-compose.yml",                 # local development
    ROOT / "docker" / "deploy" / "docker-compose.yml",  # stg / prod
)

# Calls taking the environment variable name as the first argument
ENV_READERS = {"getenv", "_env_bool", "_env_float", "_env_domains", "_env_samesite"}


def auth_env_keys() -> set[str]:
    """Collect the environment variable names that ``auth_settings.py`` reads, from the source."""
    keys: set[str] = set()
    for node in (n for path in SETTINGS_SOURCES for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in ENV_READERS:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            keys.add(first.value)
    return keys


def test_the_scan_finds_the_known_keys() -> None:
    # If the collection breaks the check passes silently, so self-check with representative keys
    keys = auth_env_keys()
    assert {"AUTH_MODE", "OIDC_ISSUER", "AUTH_COOKIE_SECURE", "MACHINE_AUDIENCE"} <= keys
    assert len(keys) >= 10


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_compose_passes_every_auth_setting(compose_path: Path) -> None:
    compose = compose_path.read_text(encoding="utf-8")
    missing = sorted(key for key in auth_env_keys() if f"{key}:" not in compose)
    assert not missing, (
        f"auth settings not passed by {compose_path.relative_to(ROOT)}: {missing}. "
        "add them to the environment of the compose api service"
    )
