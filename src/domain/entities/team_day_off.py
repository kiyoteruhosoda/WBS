"""チームの休日と各人の休み（task #554 / ADR-0058 決定 2）。

- チームの休日はいちばん上のプロジェクトに付く（下のプロジェクトは根の休日を使う）
- 各人の休みは人に付く（プロジェクトをまたいで同じ）。持つのは日付だけ
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

DAY_OFF_NAME_MAX_LENGTH = 100


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
    #: いちばん上のプロジェクト
    project_id: int
    day: date
    name: str | None = None


@dataclass(frozen=True)
class MemberDayOff:
    user_id: int
    day: date
