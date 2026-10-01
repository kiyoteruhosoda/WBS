"""ユースケースの区切り（トランザクションの確定）。

SQLAlchemy の ``Session`` はそのままこの形を満たす。1 つのユースケースで 2 つの予定を
書く操作（この回を切り出す・以降を分ける）は、最後に 1 度だけ確定する。
"""

from __future__ import annotations

from typing import Protocol


class UnitOfWork(Protocol):
    def commit(self) -> None: ...
