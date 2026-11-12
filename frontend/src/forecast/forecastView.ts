// How forecast finishes are shown (task #556, ADR-0058). Overdue forecasts are marked not only by color but also with "⚠" and text.
import type { ForecastGap, Milestone, Task } from '../types';
import type { TranslationKey } from '../i18n/translations';

/** Short wording for why no forecast is given (nothing for finished) */
export const forecastGapKey = (gap: ForecastGap | null | undefined): TranslationKey | null => {
  switch (gap) {
    case 'no_assignee': return 'forecast.gap.no_assignee';
    case 'no_remaining': return 'forecast.gap.no_remaining';
    case 'no_capacity': return 'forecast.gap.no_capacity';
    case 'waiting': return 'forecast.gap.waiting';
    case 'child_unforecast': return 'forecast.gap.child_unforecast';
    case 'beyond_horizon': return 'forecast.gap.beyond_horizon';
    default: return null;
  }
};

export interface ForecastSpan {
  start: string;
  finish: string;
  overdueDays: number;
}

/** Forecast bar (end day only when there is no start). null without a forecast */
export const taskForecastSpan = (task: Pick<Task, 'forecast_start' | 'forecast_finish' | 'forecast_overdue_days'>): ForecastSpan | null => {
  if (!task.forecast_finish) return null;
  return {
    start: task.forecast_start ?? task.forecast_finish,
    finish: task.forecast_finish,
    overdueDays: task.forecast_overdue_days ?? 0,
  };
};

/** Whether to show in the Gantt (if there are planned dates or a forecast) */
export const showsOnGantt = (task: Pick<Task, 'start_date' | 'due_date' | 'forecast_finish'>): boolean =>
  Boolean(task.start_date || task.due_date || task.forecast_finish);

/** Whether the milestone forecast is "at least" (some tasks have no forecast) */
export const milestoneForecastIsPartial = (m: Pick<Milestone, 'forecast_unforecast_count'>): boolean =>
  (m.forecast_unforecast_count ?? 0) > 0;
