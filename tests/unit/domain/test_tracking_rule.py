"""PC の自動記録の規則（task #381 / ADR-0043）: 欄の整え方と「それ以外すべて」（ADR-0045）。"""

from __future__ import annotations

import pytest

from src.domain.entities.tracking_rule import TrackingRule, in_matching_order
from src.domain.exceptions import ValidationError


def _rule(app: str | None, title: str | None) -> TrackingRule:
    return TrackingRule.create(user_id=1, position=0, task_id=10, app=app, title_contains=title)


def test_fields_are_trimmed_and_blank_means_any() -> None:
    rule = _rule("  EXCEL.EXE ", "   ")
    assert (rule.app, rule.title_contains) == ("EXCEL.EXE", None)


@pytest.mark.parametrize(("app", "title"), [(None, None), ("", " "), ("\t", None)])
def test_a_rule_with_both_blank_is_everything_else(app, title) -> None:
    rule = _rule(app, title)
    assert rule.is_everything_else
    assert not _rule("EXCEL.EXE", None).is_everything_else


def test_everything_else_is_always_matched_last() -> None:
    rules = [
        TrackingRule(id=1, user_id=1, position=0, task_id=10),
        TrackingRule(id=2, user_id=1, position=2, task_id=10, app="b.exe"),
        TrackingRule(id=3, user_id=1, position=1, task_id=10, title_contains="見積"),
    ]
    assert [r.id for r in in_matching_order(rules)] == [3, 2, 1]


def test_too_long_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        _rule("a" * 261, None)
    with pytest.raises(ValidationError):
        _rule(None, "a" * 201)
