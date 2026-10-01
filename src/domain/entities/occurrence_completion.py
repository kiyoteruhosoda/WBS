"""予定の回の「済み」（task #190 / ADR-0025）。

分類がタスクの予定（定常業務など）の回に付ける。回は予定の id と回の鍵で指す:

- 繰り返し: ``OccurrenceKey``（予定のタイムゾーンでの候補日 ＋ 系列の開始時刻。展開した回の
  ``series_key``）。移した回・営業日シフトした回も元の鍵のままなので、済みは回について回る
- 単発: 鍵は ``None``（予定そのものが 1 回）

行がある = 済み。済みを外すと行ごと消える。予定の版（楽観ロック）は進めない——済みの印は
予定の中身ではなく、別の画面で開いている予定の編集を 409 にしないため。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.event_schedule import OccurrenceKey


@dataclass(frozen=True)
class OccurrenceCompletion:
    event_id: int
    occurrence_key: OccurrenceKey | None
    """繰り返しの回の鍵。単発は ``None``。"""
    completed_at: datetime
    """済みにした瞬間（naive な UTC）。"""

    def rekeyed(self, key: OccurrenceKey | None, event_id: int | None = None) -> OccurrenceCompletion:
        return OccurrenceCompletion(
            self.event_id if event_id is None else event_id, key, self.completed_at
        )


__all__ = ["OccurrenceCompletion"]
