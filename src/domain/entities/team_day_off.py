"""プロジェクトの休日と各人の休み（task #554 / ADR-0058 決定 2、task #557 / ADR-0059）。

- 休日はどのプロジェクトにも付く。あるプロジェクトの休日は、自分と先祖（根まで）の休日を合わせたもの
- 稼働日（稼働しない曜日に働く日）も休日と同じく、どのプロジェクトにも付き、下のプロジェクトは引き継ぐ（ADR-0060）
- 各人の休みは人に付く（プロジェクトをまたいで同じ）。持つのは日付と休む割合（終日 100・半休 50）か、
  その日の稼働時間（残業・短い日・休日出勤。ADR-0060）だけ
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

DAY_OFF_NAME_MAX_LENGTH = 100
FULL_DAY_OFF_PERCENT = 100
HALF_DAY_OFF_PERCENT = 50
MAX_DAY_HOURS = 24


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
class TeamExtraWorkday:
    """稼働しない曜日に、そのプロジェクトで働く日（ADR-0060）。"""

    project_id: int
    day: date
    name: str | None = None


@dataclass(frozen=True)
class MemberDayOff:
    """人のカレンダーの 1 日: 休み・半休（休む割合）か、その日の稼働時間。"""

    user_id: int
    day: date
    #: 休む割合（1〜100。終日 100・半休 50）。``hours`` があれば見ない
    off_percent: int = FULL_DAY_OFF_PERCENT
    #: その日の稼働時間（0〜24。1 日の工数より多くてもよい＝残業。稼働しない日なら休日出勤）
    hours: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.off_percent <= FULL_DAY_OFF_PERCENT:
            raise ValidationError("a day off must take 1 to 100 percent of the day")
        if self.hours is not None and not 0 <= self.hours <= MAX_DAY_HOURS:
            raise ValidationError("working hours of a day must be 0 to 24")
