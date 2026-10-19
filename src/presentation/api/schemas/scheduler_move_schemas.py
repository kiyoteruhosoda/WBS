"""予定まわりを Scheduler へ移したか（task #535 / WBS の ADR-0054）。"""

from __future__ import annotations

from pydantic import BaseModel


class SchedulerMoveResponse(BaseModel):
    """画面はこれで、カレンダーとカレンダーの設定を Scheduler への案内に替える。"""

    #: ``off``（WBS に予定）・``hold``（切り替え中。書き込みは 503）・``moved``（Scheduler に予定）
    mode: str
    #: Scheduler の番地（案内の行き先）
    url: str
