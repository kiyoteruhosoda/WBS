// 「今日」の画面（task #160、ADR-0015）の組み立て。DOM を見ない純関数だけを置く。
//
// - 打刻を、予定の時間グリッド（1 日分）に重ねる帯にする（今日の外は切る。走っている打刻は今まで）
// - 予定のブロックから Start するときの意図（そのタスクで始める・切り替える・もう走っている）
// - 今日の実績に、要約を受け取ってから走った分を足す（1 秒ごとに問い合わせない）
// - 走っていないときに「いまの予定・次の予定」を出す

import type { Task, TaskActual, TimeEntry, TodaySummary } from '../types';
import type { DaySegment } from '../calendar/daySegments';
import type { DayBand } from '../calendar/weekLayout';
import { MINUTES_PER_DAY, addDays, formatMinute, fromZonedPoint, toZonedPoint } from '../calendar/zonedTime';

/** スマホ幅で最初に出す「まだ予定を取っていないタスク」の件数（残りは「ほか n 件」で開く）。 */
export const TASKS_SHOWN_FIRST = 3;

const dayBounds = (date: string, timeZone: string): [number, number] => [
  fromZonedPoint(date, 0, timeZone),
  fromZonedPoint(addDays(date, 1), 0, timeZone),
];

/**
 * 打刻 → 今日の列の帯。日をまたぐ打刻は今日の分だけ、走っている打刻は `nowMs` まで。
 * `colorOf` はタスクの色（未割当は null を渡す）。
 */
export const entryBands = (
  entries: readonly TimeEntry[],
  date: string,
  timeZone: string,
  nowMs: number,
  colorOf: (taskId: number | null) => string,
  unassignedLabel: string,
): DayBand[] => {
  const [dayStart, dayEnd] = dayBounds(date, timeZone);
  const minuteOf = (ms: number): number => (ms >= dayEnd ? MINUTES_PER_DAY : toZonedPoint(ms, timeZone).minute);
  const bands: DayBand[] = [];
  for (const entry of entries) {
    const startedMs = Date.parse(entry.started_at);
    const running = entry.ended_at == null;
    const endedMs = running ? Math.max(nowMs, startedMs) : Date.parse(entry.ended_at as string);
    const start = Math.max(startedMs, dayStart);
    const end = Math.min(endedMs, dayEnd);
    if (end < start || (end === start && !running)) continue;
    const startMinute = minuteOf(start);
    const endMinute = Math.max(minuteOf(end), startMinute);
    bands.push({
      key: `entry-${entry.id}`,
      startMinute,
      endMinute,
      color: colorOf(entry.task_id),
      label: `${entry.task_title ?? unassignedLabel}  ${formatMinute(startMinute)} – ${formatMinute(endMinute)}`,
      running,
    });
  }
  return bands;
};

/** 予定のブロックの Start の意図。タスクの無い予定には出さない（null）。 */
export type OccurrenceStart = 'start' | 'switch' | 'running';

export const occurrenceStartOf = (
  occurrence: { task_id: number | null },
  running: Pick<TimeEntry, 'task_id'> | null,
): OccurrenceStart | null => {
  if (occurrence.task_id == null) return null;
  if (running == null) return 'start';
  return running.task_id === occurrence.task_id ? 'running' : 'switch';
};

/**
 * 要約を受け取ってから走った分を、走っている打刻のタスクの実績と合計に足す（今日の終わりで止める）。
 * 並びは長い順のまま（同じ長さなら未割当を後ろ）。
 */
export const liveActuals = (
  summary: Pick<TodaySummary, 'running' | 'actuals' | 'total_seconds' | 'server_now' | 'day_end'>,
  receivedAtMs: number,
  nowMs: number,
): { totalSeconds: number; actuals: TaskActual[] } => {
  const { running } = summary;
  if (running == null) return { totalSeconds: summary.total_seconds, actuals: summary.actuals };
  const untilDayEnd = Math.max(0, Math.floor((Date.parse(summary.day_end) - Date.parse(summary.server_now)) / 1000));
  const delta = Math.min(Math.max(0, Math.floor((nowMs - receivedAtMs) / 1000)), untilDayEnd);
  if (delta === 0) return { totalSeconds: summary.total_seconds, actuals: summary.actuals };
  const found = summary.actuals.some((a) => a.task_id === running.task_id);
  const actuals = (found
    ? summary.actuals.map((a) => (a.task_id === running.task_id ? { ...a, seconds: a.seconds + delta } : a))
    : [...summary.actuals, { task_id: running.task_id, task_title: running.task_title, seconds: delta }])
    .sort((a, b) => b.seconds - a.seconds || Number(a.task_id == null) - Number(b.task_id == null)
      || (a.task_id ?? 0) - (b.task_id ?? 0));
  return { totalSeconds: summary.total_seconds + delta, actuals };
};

/**
 * 時刻付きの予定のうち、いま掛かっているもの（タスクのあるものを優先）と、次に始まるもの。
 * `segments` は今日の分（`groupSegmentsByDate` の 1 日分）。
 */
export const currentAndNext = (
  segments: readonly DaySegment[],
  nowMinute: number,
): { current: DaySegment | null; next: DaySegment | null } => {
  const timed = segments.filter((s) => !s.isAllDay);
  const covering = timed.filter((s) => s.startMinute <= nowMinute && nowMinute < s.endMinute);
  const current = covering.find((s) => s.occurrence.task_id != null) ?? covering[0] ?? null;
  const next = timed
    .filter((s) => s.startMinute > nowMinute)
    .reduce<DaySegment | null>((best, s) => (best == null || s.startMinute < best.startMinute ? s : best), null);
  return { current, next };
};

/** 「まだ予定を取っていないタスク」に添える、今日やるべき理由。 */
export type TaskUrgency = 'overdue' | 'today' | 'tomorrow' | 'doing' | 'started';

export const taskUrgencyOf = (
  task: Pick<Task, 'due_date' | 'status'>,
  today: string,
): TaskUrgency => {
  if (task.due_date != null) {
    if (task.due_date < today) return 'overdue';
    if (task.due_date === today) return 'today';
    if (task.due_date === addDays(today, 1)) return 'tomorrow';
  }
  return task.status === 'DOING' ? 'doing' : 'started';
};
