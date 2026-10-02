"""端末への通知（Web Push）の種類（task #193 / ADR-0031）。

種類ごとに利用者が入り / 切りを選ぶ（``PushPreferences``）。同じ通知を 2 度送らない記録
（``push_dispatches``）も種類ごとに鍵を持つ。⚠ 値は表に文字列で残る（ネイティブ ENUM にしない）。
"""

from __future__ import annotations

import enum


class PushKind(enum.StrEnum):
    #: 予定の通知（ADR-0021 のアラーム。開始の 15 / 5 / 1 / 0 分前）
    EVENT_ALARM = "event_alarm"
    #: 定常業務（分類がタスクの予定、ADR-0025）の回の開始
    ROUTINE_START = "routine_start"
    #: 打刻の止め忘れ（走りっぱなしで n 時間）
    TIMER_LEFT_RUNNING = "timer_left_running"
    #: 締めの時期（期間が終わった翌朝、未確定の期間があれば）
    CLOSING_DUE = "closing_due"

    @property
    def comes_from_calendar(self) -> bool:
        """予定から出る通知か。打刻アプリ（wbstimer）も鳴らしうる種類で、端末ごとに切れる。"""
        return self in (PushKind.EVENT_ALARM, PushKind.ROUTINE_START)


__all__ = ["PushKind"]
