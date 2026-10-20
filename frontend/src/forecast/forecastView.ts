// 終わる見込みの出し方（task #556、ADR-0058）。期限を越えるものは色だけでなく「⚠」と文字でも示す。
import type { ForecastGap, Milestone, Task } from '../types';
import type { TranslationKey } from '../i18n/translations';

/** 見込みを出さない理由の短い言葉（finished は出さない） */
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

/** 見込みの帯（始まりが無ければ終わりの日だけ）。見込みが無ければ null */
export const taskForecastSpan = (task: Pick<Task, 'forecast_start' | 'forecast_finish' | 'forecast_overdue_days'>): ForecastSpan | null => {
  if (!task.forecast_finish) return null;
  return {
    start: task.forecast_start ?? task.forecast_finish,
    finish: task.forecast_finish,
    overdueDays: task.forecast_overdue_days ?? 0,
  };
};

/** ガントに出すか（計画の日付か見込みのどちらかがあれば出す） */
export const showsOnGantt = (task: Pick<Task, 'start_date' | 'due_date' | 'forecast_finish'>): boolean =>
  Boolean(task.start_date || task.due_date || task.forecast_finish);

/** マイルストーンの見込みが「少なくとも」か（見込みの出ないタスクがある） */
export const milestoneForecastIsPartial = (m: Pick<Milestone, 'forecast_unforecast_count'>): boolean =>
  (m.forecast_unforecast_count ?? 0) > 0;
