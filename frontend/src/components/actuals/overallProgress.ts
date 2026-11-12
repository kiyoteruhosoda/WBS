import type { DashboardKpi } from '../../types';

export interface OverallProgressView {
  total: number;
  done: number;
  donePct: number;
  thisWeekDone: number;
  overdue: number;
}

const count = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null);

/**
 * Numbers for the one-line overall progress. Returns null when response fields are missing or not numbers, hiding the whole line
 * (never shows "NaN done / undefined tasks". task #463).
 */
export function overallProgressView(kpi: Partial<DashboardKpi> | null | undefined): OverallProgressView | null {
  if (!kpi || typeof kpi !== 'object') return null;
  const total = count(kpi.total_tasks);
  const incomplete = count(kpi.incomplete_tasks);
  if (total === null || incomplete === null) return null;
  const done = Math.max(0, total - incomplete);
  return {
    total,
    done,
    donePct: total > 0 ? Math.round((done / total) * 100) : 0,
    thisWeekDone: count(kpi.this_week_completed) ?? 0,
    overdue: count(kpi.overdue_tasks) ?? 0,
  };
}
