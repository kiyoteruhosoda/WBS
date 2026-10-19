"""打刻まわりを Tracker へ移したか（task #526 / ADR-0053）。"""

from __future__ import annotations

from pydantic import BaseModel


class TrackerMoveResponse(BaseModel):
    """画面はこれで、上部の打刻ボタン・締め・規則を Tracker への案内に替える。"""

    #: ``off``（WBS に記録）・``hold``（切り替え中。書き込みは 503）・``moved``（Tracker に記録）
    mode: str
    #: Tracker の番地（案内の行き先）
    url: str
