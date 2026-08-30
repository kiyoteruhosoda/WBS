"""設定が読む環境変数を、compose が本当にコンテナへ渡しているか。

compose の ``environment:`` に並べ忘れたキーは、``.env`` に書いても届かない。
認証の設定でこれが起きると「AUTH_MODE=oidc と書いたのに認証なしで起動する」という
一番気づきにくい壊れ方になる（起動もヘルスチェックも通ってしまう）ので、
突き合わせを機械で見張る。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SETTINGS_SOURCE = ROOT / "src" / "infrastructure" / "auth" / "auth_settings.py"
COMPOSE_FILES = (
    ROOT / "docker-compose.yml",                 # ローカル開発
    ROOT / "docker" / "deploy" / "docker-compose.yml",  # stg / prod
)

# 環境変数名を第 1 引数に取る呼び出し
ENV_READERS = {"getenv", "_env_bool", "_env_float", "_env_domains", "_env_samesite"}


def auth_env_keys() -> set[str]:
    """``auth_settings.py`` が読む環境変数名を、ソースから拾う。"""
    tree = ast.parse(SETTINGS_SOURCE.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
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
    # 拾い方が壊れると検査が素通りになるので、代表的なキーで自己点検する
    keys = auth_env_keys()
    assert {"AUTH_MODE", "OIDC_ISSUER", "AUTH_COOKIE_SECURE"} <= keys
    assert len(keys) >= 10


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_compose_passes_every_auth_setting(compose_path: Path) -> None:
    compose = compose_path.read_text(encoding="utf-8")
    missing = sorted(key for key in auth_env_keys() if f"{key}:" not in compose)
    assert not missing, (
        f"{compose_path.relative_to(ROOT)} が渡していない認証設定: {missing}. "
        "compose の api サービスの environment に足すこと"
    )
