"""休みの層の出どころ（ADR-0029）。予定の展開（営業日シフト）が利用者の層を引くための口。"""

from __future__ import annotations

from typing import Protocol

from src.domain.services.day_off_layers import DayOffLayers


class DayOffLayersSource(Protocol):
    def layers_for(self, user_id: int) -> DayOffLayers:
        """その利用者の休みの層（表示の選択に関係なく「休みとして数える」で決まる判定）。"""
        ...


__all__ = ["DayOffLayersSource"]
