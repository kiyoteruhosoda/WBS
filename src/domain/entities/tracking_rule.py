"""PC の自動記録の規則（WinTrack、task #381 / ADR-0043）。

「アプリ（実行ファイル名）が〜」「表題に〜を含む」→ このタスク、という 1 行。利用者ごとに
``position`` の順に並び、PC の係が**上から最初に当てはまったもの**を使う。照合は PC の中で行い、
WBS は表題を受け取らない（規則だけを持つ）。

- ``app`` は大小文字を区別しない完全一致、``title_contains`` は大小文字を区別しない部分一致（照合は PC 側）
- 片方が空なら、その条件は問わない
- **両方空の規則は「それ以外すべて」**（ADR-0045）。何にでも当たるので、``position`` に関係なく**いつも最後**に
  当てる。利用者ごとに 1 つまで（ユースケースが守る）。WinTrack はこれに当たった作業を「既定」、ほかの規則に
  当たった作業を「例外」として扱う
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

    @property
    def is_everything_else(self) -> bool:
        """「それ以外すべて」（両方空）の規則か。"""
        return self.app is None and self.title_contains is None

    def change_condition(self, *, app: str | None, title_contains: str | None) -> None:
        self.app = rule_app(app)
        self.title_contains = rule_title_contains(title_contains)


def in_matching_order(rules: list[TrackingRule]) -> list[TrackingRule]:
    """当てる順（``position`` → id の順に、「それ以外すべて」をいつも最後へ）。"""
    return sorted(rules, key=lambda r: (r.is_everything_else, r.position, r.id or 0))
