import client from './client';
import type {
  Breakdown, BreakdownGroupBy, GanttActualSpan, PeriodReport, ReportUnit, TaskActuals, TimeSource,
} from '../types/actuals';

/** 実績の見える化（task #162、ADR-0017）。打刻・締め・残を書いたら読み直させる。 */
export const ACTUALS_KEY = ['actuals'] as const;

export interface RangeParams {
  from?: string;
  to?: string;
}

export const getTaskActuals = async (reviewOnly = false): Promise<TaskActuals> => {
  const { data } = await client.get<TaskActuals>('/actuals/tasks', { params: { review_only: reviewOnly } });
  return data;
};

export const getGanttActuals = async (range: RangeParams = {}): Promise<GanttActualSpan[]> => {
  const { data } = await client.get<GanttActualSpan[]>('/actuals/gantt', { params: range });
  return data;
};

export const getPeriodReport = async (unit: ReportUnit, range: RangeParams = {}): Promise<PeriodReport> => {
  const { data } = await client.get<PeriodReport>('/actuals/periods', { params: { unit, ...range } });
  return data;
};

export const getBreakdown = async (
  unit: ReportUnit, groupBy: BreakdownGroupBy, source: TimeSource, range: RangeParams = {},
): Promise<Breakdown> => {
  const { data } = await client.get<Breakdown>('/actuals/breakdown', {
    params: { unit, group_by: groupBy, source, ...range },
  });
  return data;
};

/** CSV の書き出し口（同一オリジンなので、リンクで開けばセッションの Cookie が付く）。 */
export const exportCsvUrl = (from: string, to: string, source: TimeSource): string =>
  `/api/actuals/export.csv?${new URLSearchParams({ from, to, source }).toString()}`;
