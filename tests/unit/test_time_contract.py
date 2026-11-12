"""The time contract (HANDOVER §14).

Storage, comparison and logs are UTC; only the screen converts to local time.
Two things are pinned here.

1. `clock` output: "now" is aware UTC, and strings handed across boundaries always end in `Z`
2. How source is written: no calls that depend on the process time zone

2 is checked via the AST, so mentions inside comments or docstrings do not trigger it.
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
    "now": "datetime.now() is the container's local time. Use src.shared.clock.utcnow()",
    "utcnow": "datetime.utcnow() is naive and deprecated. Use src.shared.clock.utcnow()",
    "today": "date.today() is the server's local date. Use UserClock.today(user_id)",
    "astimezone": "astimezone() without arguments converts to local time. Name the target TZ explicitly",
    "fromtimestamp": "fromtimestamp() without tz is interpreted as local time. Pass tz=UTC",
}


def test_utcnow_is_naive_utc() -> None:
    """Returns the same shape as stored values (naive UTC).

    DB DATETIME has no time zone, and written values come back naive. Making only the producer
    aware means "a freshly inserted value is aware, a re-read value is naive",
    and the moment they are compared it crashes with TypeError.
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
    files.append(_ROOT / "main.py")  # the composition root is also covered by the contract
    assert files, "no source files found to scan"
    return files


def _is_clock_receiver(node: ast.Attribute) -> bool:
    """Whether it hangs off the standard date/time types, like ``datetime.now`` (our own Clock is excluded)."""
    return ast.unparse(node.value).endswith(("datetime", "date"))


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    called: set[int] = set()

    # (1) The call form. Passing tz is explicit, so let it through.
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
            continue  # tz is passed
        if attr == "fromtimestamp" and len(node.args) + len(node.keywords) > 1:
            continue  # tz is passed
        found.append((node.lineno, _MESSAGES[attr]))

    # (2) The form passed as a function reference (``default=datetime.utcnow``). Not a call, so
    #     (1) misses it. The receiver calls it, so the result is the same as the local clock.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in called:
            continue
        if node.attr not in {"now", "utcnow", "today"} or not _is_clock_receiver(node):
            continue
        found.append((node.lineno, _MESSAGES[node.attr] + " (same when passed as a function reference)"))

    return found


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_source_does_not_take_the_local_clock(path: Path) -> None:
    violations = _violations(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    assert not violations, "\n".join(
        f"{path.relative_to(_ROOT)}:{line} {message}" for line, message in violations
    )


def test_the_clock_is_the_only_place_that_reads_the_wall_clock() -> None:
    """Only `src/shared/clock.py` creates "now".

    `datetime.now(UTC)` passes the check above since it passes tz, but
    calling it all over the place multiplies the producers. In fact, the ops health check and main.py's
    startup_time each called `datetime.now(UTC)` separately, and changing the shape of only one
    would have made the difference calculation raise TypeError.
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
    assert not offenders, "use src.shared.clock.utcnow(): " + ", ".join(offenders)
