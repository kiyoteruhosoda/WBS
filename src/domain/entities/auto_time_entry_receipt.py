"""自動の打刻を受け取った控え（WinTrack、task #386 / ADR-0045）。

送り直し（同じ ``client_ref``）を見分けるのはこの控え。``fill`` は 1 つの ``client_ref`` から空きの数だけ
打刻ができる（0 本のこともある）ので、打刻の表では 1 対 1 にならない。控えは ``(user_id, client_ref)`` で一意。
作らなかった区間（``covered`` や断ったもの）は控えない（送り直すと改めて判定する）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.auto_entry_mode import AutoEntryMode


@dataclass(frozen=True)
class AutoTimeEntryReceipt:
    user_id: int
    client_ref: str
    mode: AutoEntryMode
    received_at: datetime
