from __future__ import annotations

import enum


class TaskStatus(enum.StrEnum):
    TODO = "TODO"
    DOING = "DOING"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    
    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]
