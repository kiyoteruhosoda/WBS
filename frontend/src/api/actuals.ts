import client from './client';
import type {
  Breakdown, BreakdownGroupBy, GanttActualSpan, PeriodReport, ReportUnit, TaskActuals, TimeSource,
} from '../types/actuals';
import type { ProjectFilterParams } from '../projects/projectScope';

/** 実績の見える化（task #162、ADR-0017）。打刻・締め・残を書いたら読み直させる。 */
export const ACTUALS_KEY = ['actuals'] as const;

export interface RangeParams {
  from?: string;
  to?: string;
}

// project: サイドバーで選んだプロジェクト（子孫を含む）・未分類だけ（task #187、ADR-0024）

export const getTaskActuals = async (reviewOnly = false, project: ProjectFilterParams = {}): Promise<TaskActuals> => {
  const { data } = await client.get<TaskActuals>('/actuals/tasks', { params: { review_only: reviewOnly, ...project } });
  return data;
};

export const getGanttActuals = async (range: RangeParams = {}): Promise<GanttActualSpan[]> => {
  const { data } = await client.get<GanttActualSpan[]>('/actuals/gantt', { params: range });
  return data;
};

export const getPeriodReport = async (
  unit: ReportUnit, range: RangeParams = {}, project: ProjectFilterParams = {},
): Promise<PeriodReport> => {
  const { data } = await client.get<PeriodReport>('/actuals/periods', { params: { unit, ...range, ...project } });
  return data;
};

export const getBreakdown = async (
  unit: ReportUnit, groupBy: BreakdownGroupBy, source: TimeSource, range: RangeParams = {},
  project: ProjectFilterParams = {},
): Promise<Breakdown> => {
  const { data } = await client.get<Breakdown>('/actuals/breakdown', {
    params: { unit, group_by: groupBy, source, ...range, ...project },
  });
  return data;
};

/** CSV の書き出し口（同一オリジンなので、リンクで開けばセッションの Cookie が付く）。 */
export const exportCsvUrl = (
  from: string, to: string, source: TimeSource, project: ProjectFilterParams = {},
): string => {
  const params = new URLSearchParams({ from, to, source });
  if (project.project_id !== undefined) params.set('project_id', String(project.project_id));
  if (project.unclassified) params.set('unclassified', 'true');
  return `/api/actuals/export.csv?${params.toString()}`;
};
