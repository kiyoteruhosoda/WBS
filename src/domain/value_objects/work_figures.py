"""Pair of actual and remaining used to compute progress (design doc §5.1, ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkFigures:
    """Actual (sum of work_logs) and remaining. If remaining is undetermined (both remaining and estimate empty), ``remaining_hours`` is None."""

    actual_hours: float
    remaining_hours: float | None

    def progress_percent(self, *, done: bool) -> float | None:
        """Progress = actual ÷ (actual + remaining) × 100. DONE is 100.

        None when remaining is undetermined or the denominator is 0, since there is nothing to judge by (the screen shows "—").
        """
        if done:
            return 100.0
        if self.remaining_hours is None:
            return None
        denominator = self.actual_hours + self.remaining_hours
        if denominator <= 0:
            return None
        return round(self.actual_hours / denominator * 100, 1)
