from __future__ import annotations

from typing import Final


class UnsetType:
    """Sentinel that distinguishes "not specified" from "explicit null" in update DTOs.

    A field whose value is ``UNSET`` means "do not change", and ``None`` means
    "explicitly overwrite with null (clear the value)".
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
