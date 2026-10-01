from __future__ import annotations

import enum


class EventColorKey(enum.StrEnum):
    """予定の色（Google カレンダーの色名。移植元の ``EventColorKey`` と同じ 11 個）。

    ドメインは名前だけを知り、実際の色（明暗のテーマごとの値）は画面が決める。
    ``DEFAULT`` は「色の指定なし」で、標準の予定色で描く。残りの 10 個が Google の色名
    （移植元に Flamingo は無い）。
    """

    DEFAULT = "DEFAULT"
    TOMATO = "TOMATO"
    TANGERINE = "TANGERINE"
    BANANA = "BANANA"
    BASIL = "BASIL"
    SAGE = "SAGE"
    PEACOCK = "PEACOCK"
    BLUEBERRY = "BLUEBERRY"
    LAVENDER = "LAVENDER"
    GRAPE = "GRAPE"
    GRAPHITE = "GRAPHITE"
