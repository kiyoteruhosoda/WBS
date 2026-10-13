"""PC の自動記録の規則（WinTrack、task #381 / ADR-0043）。

「アプリ（実行ファイル名）が〜」「表題に〜を含む」→ このタスク、という 1 行。利用者ごとに
``position`` の順に並び、PC の係が**上から最初に当てはまったもの**を使う。照合は PC の中で行い、
WBS は表題を受け取らない（規則だけを持つ）。

- ``app`` は大小文字を区別しない完全一致、``title_contains`` は大小文字を区別しない部分一致（照合は PC 側）
- どちらも空なら「問わない」。**両方空の規則は作れない**（何にでも当たる規則は、下の規則を全部殺す）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import ValidationError

APP_MAX_LENGTH = 260
"""実行ファイル名の上限（Windows のパスの長さに合わせた、ゆるい上限）。"""

TITLE_CONTAINS_MAX_LENGTH = 200


def rule_app(raw: str | None) -> str | None:
    """実行ファイル名。前後の空白を落とし、空なら None。"""
    if raw is None:
        return None
    app = raw.strip()
    if not app:
        return None
    if len(app) > APP_MAX_LENGTH:
        raise ValidationError(f"app must be at most {APP_MAX_LENGTH} characters")
    return app


def rule_title_contains(raw: str | None) -> str | None:
    """表題に含む語。前後の空白を落とし、空なら None。"""
    if raw is None:
        return None
    words = raw.strip()
    if not words:
        return None
    if len(words) > TITLE_CONTAINS_MAX_LENGTH:
        raise ValidationError(
            f"title_contains must be at most {TITLE_CONTAINS_MAX_LENGTH} characters"
        )
    return words


@dataclass
class TrackingRule:
    id: int | None
    user_id: int
    position: int
    task_id: int
    app: str | None = None
    title_contains: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        position: int,
        task_id: int,
        app: str | None,
        title_contains: str | None,
    ) -> TrackingRule:
        rule = cls(id=None, user_id=user_id, position=position, task_id=task_id)
        rule.change_condition(app=app, title_contains=title_contains)
        return rule

    def change_condition(self, *, app: str | None, title_contains: str | None) -> None:
        app, title_contains = rule_app(app), rule_title_contains(title_contains)
        if app is None and title_contains is None:
            raise ValidationError("a rule needs app or title_contains (or both)")
        self.app = app
        self.title_contains = title_contains
