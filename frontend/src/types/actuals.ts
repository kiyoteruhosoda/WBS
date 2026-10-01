// 実績の見える化（予定 vs 実績・計画 vs 実績。task #162 / ADR-0017）の応答の形。
import type { Task } from './index';

export type RemainingReviewReason =
  | 'over_estimate'
  | 'no_remaining'
  | 'unknown_remaining'
  | 'stale_remaining';

export interface TaskActualsRow {
  // 見積・予定済み・実績・残はタスクの一覧と同じ値
  task: Task;
  actual_first_date: string | null;
  actual_last_date: string | null;
  // 直近に確定した締めの期間でこのタスクに入った実績（時間）
  latest_closed_hours: number;
  review_reasons: RemainingReviewReason[];
}

export interface TaskActuals {
  latest_closed_period: { first_day: string; last_day: string; closed_at: string } | null;
  rows: TaskActualsRow[];
}

export interface GanttActualSpan {
  task_id: number;
  first_date: string;
  last_date: string;
  days: { date: string; seconds: number }[];
}

export type ReportUnit = 'closing' | 'week' | 'month';
export type TimeSource = 'planned' | 'tracked' | 'confirmed';
export type BreakdownGroupBy = 'category' | 'milestone' | 'project';

export interface PeriodComparison {
  first_day: string;
  last_day: string;
  closed: boolean | null;
  planned_seconds: number;
  planned_task_seconds: number;
  planned_off_task_seconds: number;
  tracked_seconds: number;
  tracked_task_seconds: number;
  tracked_off_task_seconds: number;
  confirmed_seconds: number;
  // 打刻 − 予定
  difference_seconds: number;
  // 0〜1、分母 0 なら null
  planned_off_task_ratio: number | null;
  tracked_off_task_ratio: number | null;
}

export interface PeriodReport {
  unit: ReportUnit;
  time_zone: string;
  periods: PeriodComparison[];
}

export interface BreakdownGroup {
  // category:<id> / milestone:<id> / project:<id>（枝の合計）/ none（未分類）/ unassigned（タスク外）
  key: string;
  name: string | null;
  color: string | null;
}

export interface Breakdown {
  unit: ReportUnit;
  group_by: BreakdownGroupBy;
  source: TimeSource;
  time_zone: string;
  groups: BreakdownGroup[];
  periods: { first_day: string; last_day: string; seconds_by_group: Record<string, number> }[];
}
