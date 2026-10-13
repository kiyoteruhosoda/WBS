"""PC の自動記録の規則（task #381 / ADR-0043）: 欄の整え方と「両方空は作れない」。"""

from __future__ import annotations

import pytest

from src.domain.entities.tracking_rule import TrackingRule
from src.domain.exceptions import ValidationError


def _rule(app: str | None, title: str | None) -> TrackingRule:
    return TrackingRule.create(user_id=1, position=0, task_id=10, app=app, title_contains=title)


def test_fields_are_trimmed_and_blank_means_any() -> None:
    rule = _rule("  EXCEL.EXE ", "   ")
    assert (rule.app, rule.title_contains) == ("EXCEL.EXE", None)


@pytest.mark.parametrize(("app", "title"), [(None, None), ("", " "), ("\t", None)])
def test_a_rule_needs_app_or_title(app, title) -> None:
    with pytest.raises(ValidationError):
        _rule(app, title)


def test_too_long_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        _rule("a" * 261, None)
    with pytest.raises(ValidationError):
        _rule(None, "a" * 201)
