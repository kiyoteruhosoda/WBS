// 試験で使う打刻と締めの画面の組み立て（本番のコードからは使わない）。
import type { ClosingBoard, TimeEntry } from '../types';

export const entry = (
  id: number,
  startedAt: string,
  endedAt: string | null,
  overrides: Partial<TimeEntry> = {},
): TimeEntry => ({
  id,
  user_id: 1,
  task_id: 1,
  task_title: 'タスク',
  started_at: startedAt,
  ended_at: endedAt,
  memo: null,
  source: 'timer',
  is_running: endedAt == null,
  duration_seconds: endedAt == null ? 0 : (Date.parse(endedAt) - Date.parse(startedAt)) / 1000,
  is_long_running: false,
  created_at: null,
  updated_at: null,
  ...overrides,
});

export const board = (overrides: Partial<ClosingBoard> = {}): ClosingBoard => ({
  period: {
    first_day: '2026-09-01',
    last_day: '2026-09-15',
    status: 'open',
    time_zone: 'Asia/Tokyo',
    starts_at: '2026-08-31T15:00:00Z',
    ends_at: '2026-09-15T15:00:00Z',
    closed_at: null,
  },
  entries: [],
  occurrences: [],
  daily_totals: [],
  findings: { long_running_entry_ids: [], overlaps: [], unassigned_entry_ids: [], missed_occurrences: [], count: 0 },
  ...overrides,
});
