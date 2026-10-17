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
 * 全体の進捗の 1 行に出す数。応答の項目が欠けている・数でないときは null を返し、行ごと出さない
 * （「完了 NaN / 全 undefined タスク」を出さない。task #463）。
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
