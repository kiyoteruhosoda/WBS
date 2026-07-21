from __future__ import annotations

from typing import Final


class UnsetType:
    """更新DTOで「未指定」を「明示的な null」と区別するためのセンチネル。

    値が ``UNSET`` のフィールドは「変更しない」を意味し、``None`` は
    「明示的に null で上書きする（値をクリアする）」を意味する。
    """

    _instance: UnsetType | None = None

    def __new__(cls) -> UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Final[UnsetType] = UnsetType()
