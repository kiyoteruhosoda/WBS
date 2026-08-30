"""持ち主の確認。

複数の利用者が同じ API を使うようになった以上、ID を指定して取る／書き換える
操作は「その ID が自分のものか」を必ず見る。見ないと、連番の ID を変えるだけで
他人のデータに届く。

見つからない場合と他人のものだった場合は、どちらも ``NotFoundError`` にする。
403 で返し分けると「その ID は存在する」ことを教えてしまい、総当たりで他人の
データの有無を数えられる。
"""

from __future__ import annotations

from typing import Protocol

from src.domain.exceptions import NotFoundError


class OwnedRecord(Protocol):
    """利用者に属するレコード。"""

    user_id: int


def owned_by[T: OwnedRecord](
    record: T | None, user_id: int, *, resource: str, resource_id: int
) -> T:
    if record is None or record.user_id != user_id:
        raise NotFoundError(resource, resource_id)
    return record
