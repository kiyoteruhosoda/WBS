"""自動の打刻の送り方（WinTrack、task #386 / ADR-0045）。

**Working（手の打刻）が正。** WinTrack は「始め忘れ」と「例外作業」だけを受け持つ。

- ``fill``（既定のタスク）: ほかの打刻と重なる部分は作らず、空いている部分だけを打刻にする
- ``override``（例外作業）: 手の打刻のその時間を切り抜いて作る
"""

from __future__ import annotations

from enum import StrEnum


class AutoEntryMode(StrEnum):
    """DB へはこの文字列で入れる（ネイティブ ENUM にしない）。"""

    FILL = "fill"
    OVERRIDE = "override"
