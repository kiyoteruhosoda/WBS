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


def test_utcnow_is_naive_utc() -> None:
    """保存値と同じ形（naive な UTC）で返す。

    DB の DATETIME はタイムゾーンを持たず、書いた値は naive で返る。生成側だけ
    aware にすると「入れたばかりの値は aware・読み直した値は naive」となり、
    比べた瞬間に TypeError で落ちる。
    """
    now = utcnow()
    assert now.tzinfo is None
    assert abs((now - datetime.now(UTC).replace(tzinfo=None)).total_seconds()) < 5


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
    files.append(_ROOT / "main.py")  # 合成ルートも契約の対象
    assert files, "走査対象のソースが見つからない"
    return files


def _is_clock_receiver(node: ast.Attribute) -> bool:
    """``datetime.now`` のように標準の日時型に生えているものか（自前の Clock は対象外）。"""
    return ast.unparse(node.value).endswith(("datetime", "date"))


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    called: set[int] = set()

    # (1) 呼び出しの形。tz を渡していれば明示的なので見逃す。
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        called.add(id(node.func))
        attr = node.func.attr
        if attr not in _MESSAGES:
            continue
        if attr in {"now", "utcnow", "today", "fromtimestamp"} and not _is_clock_receiver(node.func):
            continue
        if attr in {"now", "today", "astimezone"} and (node.args or node.keywords):
            continue  # tz を渡している
        if attr == "fromtimestamp" and len(node.args) + len(node.keywords) > 1:
            continue  # tz を渡している
        found.append((node.lineno, _MESSAGES[attr]))

    # (2) 関数参照として渡す形（``default=datetime.utcnow``）。呼び出しではないので
    #     (1) では拾えない。渡した先が呼ぶので、結果はローカル時計と同じ。
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in called:
            continue
        if node.attr not in {"now", "utcnow", "today"} or not _is_clock_receiver(node):
            continue
        found.append((node.lineno, _MESSAGES[node.attr] + "（関数参照として渡す形も同じ）"))

    return found


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_source_does_not_take_the_local_clock(path: Path) -> None:
    violations = _violations(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    assert not violations, "\n".join(
        f"{path.relative_to(_ROOT)}:{line} {message}" for line, message in violations
    )


def test_the_clock_is_the_only_place_that_reads_the_wall_clock() -> None:
    """「今」を作るのは `src/shared/clock.py` だけ。

    `datetime.now(UTC)` は tz を渡しているので上の検査は通ってしまうが、
    あちこちで呼ばれると生成口が増える。実際、ops のヘルスと main.py の
    startup_time が別々に `datetime.now(UTC)` を呼んでいて、片方だけ形を
    変えると差分の計算が TypeError になる状態だった。
    """
    offenders: list[str] = []
    for path in _source_files():
        if path.name == "clock.py" and path.parent.name == "shared":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
                and _is_clock_receiver(node.func)
            ):
                offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not offenders, "src.shared.clock.utcnow() を使う: " + ", ".join(offenders)
