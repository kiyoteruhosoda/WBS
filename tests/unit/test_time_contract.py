"""時刻の契約（HANDOVER §14）。

保存・比較・ログは UTC、ローカルタイムへ直すのは画面だけ。
ここでは 2 つを固定する。

1. `clock` の出力: 「今」は aware な UTC、境界へ出す文字列は必ず `Z` で終わる
2. ソースの書き方: プロセスのタイムゾーンに依存する呼び方が混ざっていないこと

2 は AST で見るので、コメントや docstring の中の記述には反応しない。
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.presentation.api.schemas.types import UtcDatetime
from src.shared.clock import isoformat_utc, utcnow

JST = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[2]

_MESSAGES = {
    "now": "datetime.now() はコンテナのローカル時刻。src.shared.clock.utcnow() を使う",
    "utcnow": "datetime.utcnow() は naive かつ非推奨。src.shared.clock.utcnow() を使う",
    "today": "date.today() はサーバのローカル日付。UserClock.today(user_id) を使う",
    "astimezone": "引数なしの astimezone() はローカルへ変換する。出す先の TZ を明示する",
    "fromtimestamp": "fromtimestamp() は tz を渡さないとローカル解釈になる。tz=UTC を渡す",
}


def test_utcnow_is_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_naive_value_is_rendered_with_a_trailing_z() -> None:
    assert isoformat_utc(datetime(2026, 8, 26, 4, 20, 47)) == "2026-08-26T04:20:47Z"


def test_aware_value_is_converted_to_utc_before_rendering() -> None:
    assert isoformat_utc(datetime(2026, 8, 26, 13, 20, 47, tzinfo=JST)) == "2026-08-26T04:20:47Z"


def test_offset_notation_is_never_emitted() -> None:
    for value in (
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=JST),
    ):
        rendered = isoformat_utc(value)
        assert rendered.endswith("Z"), rendered
        assert "+" not in rendered, rendered


def test_response_field_renders_with_a_trailing_z() -> None:
    class _Sample(BaseModel):
        updated_at: UtcDatetime | None = None

    dumped = _Sample(updated_at=datetime(2026, 8, 26, 4, 20, 47)).model_dump(mode="json")
    assert dumped["updated_at"] == "2026-08-26T04:20:47Z"


def _source_files() -> list[Path]:
    files = [p for p in (_ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts]
    assert files, "走査対象のソースが見つからない"
    return files


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr not in _MESSAGES:
            continue
        receiver = ast.unparse(node.func.value)
        if attr in {"now", "utcnow", "today", "fromtimestamp"} and not receiver.endswith(
            ("datetime", "date")
        ):
            continue  # 自前の Clock などは対象外
        if attr in {"now", "today", "astimezone"} and (node.args or node.keywords):
            continue  # tz を渡しているので明示的
        if attr == "fromtimestamp" and len(node.args) + len(node.keywords) > 1:
            continue
        found.append((node.lineno, _MESSAGES[attr]))
    return found


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_source_does_not_take_the_local_clock(path: Path) -> None:
    violations = _violations(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    assert not violations, "\n".join(
        f"{path.relative_to(_ROOT)}:{line} {message}" for line, message in violations
    )
