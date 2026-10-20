"""プロジェクトの休日と各人の休み（task #554 / ADR-0058 決定 2、task #557 / ADR-0059）。

- 休日はどのプロジェクトにも付く。あるプロジェクトの休日は、自分と先祖（根まで）の休日を合わせたもの
- 各人の休みは人に付く（プロジェクトをまたいで同じ）。持つのは日付と休む割合（終日 100・半休 50）だけ
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

DAY_OFF_NAME_MAX_LENGTH = 100
FULL_DAY_OFF_PERCENT = 100
HALF_DAY_OFF_PERCENT = 50


def team_day_off_name(raw: str | None) -> str | None:
    """前後の空白を落とした名前（空なら None）。長すぎるものは断る。"""
    if raw is None:
        return None
    name = raw.strip()
    if not name:
        return None
    if len(name) > DAY_OFF_NAME_MAX_LENGTH:
        raise ValidationError(f"a day off name must be at most {DAY_OFF_NAME_MAX_LENGTH} characters")
    return name


@dataclass(frozen=True)
class TeamDayOff:
    #: 休日が付いているプロジェクト（根ならチームの休日）
    project_id: int
    day: date
    name: str | None = None


@dataclass(frozen=True)
class MemberDayOff:
    user_id: int
    day: date
    #: 休む割合（1〜100。終日 100・半休 50）
    off_percent: int = FULL_DAY_OFF_PERCENT

    def __post_init__(self) -> None:
        if not 1 <= self.off_percent <= FULL_DAY_OFF_PERCENT:
            raise ValidationError("a day off must take 1 to 100 percent of the day")
