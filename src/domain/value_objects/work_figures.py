"""進捗率を出すための実績と残の組（設計書 §5.1・ADR-0010）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkFigures:
    """実績（work_logs の合計）と残。残が決まらない（残も見積も空）なら ``remaining_hours`` は None。"""

    actual_hours: float
    remaining_hours: float | None

    def progress_percent(self, *, done: bool) -> float | None:
        """進捗率 = 実績 ÷（実績 ＋ 残）× 100。DONE は 100。

        残が決まらないとき・分母が 0 のときは判断材料が無いので None（画面は「—」）。
        """
        if done:
            return 100.0
        if self.remaining_hours is None:
            return None
        denominator = self.actual_hours + self.remaining_hours
        if denominator <= 0:
            return None
        return round(self.actual_hours / denominator * 100, 1)
