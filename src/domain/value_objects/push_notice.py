"""送る通知 1 通（task #193 / ADR-0031）。

``key`` は同じ通知を 2 度送らないための鍵で、``(user_id, kind, key)`` が送った記録
（``push_dispatches``）の一意の組になる。中身（題・本文・行き先）は鍵に含めない
（文言を変えても同じ通知は同じ通知）。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.push_kind import PushKind


@dataclass(frozen=True)
class PushNotice:
    user_id: int
    kind: PushKind
    key: str
    title: str
    body: str
    #: 押したときに開く画面（このアプリの中のパス。``/`` で始まる）
    url: str

    @property
    def tag(self) -> str:
        """端末の通知の束ね札。同じ札の通知は端末で 1 つに置き換わる。"""
        return f"{self.kind.value}:{self.key}"


__all__ = ["PushNotice"]
