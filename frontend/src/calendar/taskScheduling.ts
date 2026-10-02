// 計画 → 予定（task #159、ADR-0014）。タスクから予定を作る意図と、予定に出すタスクの印。
//
// - 「時間を取る」: タスクの画面から `/calendar?schedule_task=<id>` へ。週表示で枠を押す・引くと、
//   そのタスクに結んだ予定ができる（題名の既定はタスク名）
// - 週表示の横のタスクの一覧から、時間グリッドへ落とすと予定になる（長さの既定は 1 時間、
//   残が 1 時間より短ければ残。15 分単位）
// - 予定のブロックはタスクのカテゴリの色で塗る（予定に色が無いとき）
//
// ここは DOM を見ない純関数だけを置く（落とした位置 → 日と分は `components/calendar/taskDrop.ts`）。

import type { CalendarOccurrence, Category, Task } from '../types';
import type { CalendarRequest } from './calendarRequests';
import { eventColor } from './calendarColors';
import { MINUTES_PER_DAY, fromZonedPoint } from './zonedTime';
import { SNAP_MINUTES } from './weekGestures';

/** `/calendar` に渡す「このタスクの時間を取る」のクエリの名前。 */
export const SCHEDULE_TASK_PARAM = 'schedule_task';

/** タスクの画面から「時間を取る」で開く先。 */
export const scheduleTaskPath = (taskId: number): string => `/calendar?${SCHEDULE_TASK_PARAM}=${taskId}`;

/** クエリの値 → タスクの id（数でなければ null）。 */
export const parseScheduleTaskParam = (value: string | null): number | null => {
  if (value == null || !/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
};

/** タスクから作る予定の長さの既定（1 時間）。 */
export const TASK_BLOCK_DEFAULT_MINUTES = 60;

/**
 * タスクから作る予定の長さ。既定は 1 時間、残が 1 時間より短ければ残（15 分へ切り上げ、最短 15 分）。
 * 残が決まらない・0 のときも 1 時間（予定を取ること自体は止めない）。
 */
export const taskBlockMinutes = (task: Pick<Task, 'remaining_hours'>): number => {
  const remaining = task.remaining_hours;
  if (remaining == null || remaining <= 0) return TASK_BLOCK_DEFAULT_MINUTES;
  const minutes = remaining * 60;
  if (minutes >= TASK_BLOCK_DEFAULT_MINUTES) return TASK_BLOCK_DEFAULT_MINUTES;
  return Math.max(SNAP_MINUTES, Math.ceil(Math.round(minutes) / SNAP_MINUTES) * SNAP_MINUTES);
};

/**
 * 時間グリッドへ落とした位置（その日の 0:00 からの px = 分）→ 開始の分。15 分へ丸め、
 * その日の中（0:00〜23:45）に収める。
 */
export const dropStartMinute = (offsetY: number): number => {
  const snapped = Math.round(offsetY / SNAP_MINUTES) * SNAP_MINUTES;
  return Math.min(Math.max(snapped, 0), MINUTES_PER_DAY - SNAP_MINUTES);
};

/** タスクから作る予定の中身（閲覧者のタイムゾーンの、開始の日と分 ＋ 長さ）。 */
export interface TaskEventDraft {
  taskId: number;
  title: string;
  date: string;
  startMinute: number;
  durationMinutes: number;
}

/** 一覧から時間グリッドへ落とした → 予定の中身（長さは `taskBlockMinutes`）。 */
export const draftFromDrop = (
  task: Pick<Task, 'id' | 'title' | 'remaining_hours'>,
  drop: { date: string; offsetY: number },
): TaskEventDraft => ({
  taskId: task.id,
  title: task.title,
  date: drop.date,
  startMinute: dropStartMinute(drop.offsetY),
  durationMinutes: taskBlockMinutes(task),
});

/**
 * 「時間を取る」の最中に枠を押した・引いた → 予定の中身。
 * 引いた範囲があればその長さ、押しただけなら `taskBlockMinutes`。
 */
export const draftFromSlot = (
  task: Pick<Task, 'id' | 'title' | 'remaining_hours'>,
  slot: { date: string; startMinute: number; endMinute?: number },
): TaskEventDraft => ({
  taskId: task.id,
  title: task.title,
  date: slot.date,
  startMinute: slot.startMinute,
  durationMinutes: slot.endMinute != null && slot.endMinute > slot.startMinute
    ? slot.endMinute - slot.startMinute
    : taskBlockMinutes(task),
});

/**
 * 予定の中身 → 作る呼び出し（単発。色は既定のまま = タスクのカテゴリの色で描く）。
 * 通知は送らない（作る API の既定 = 4 つとも入り。ADR-0021）。
 */
export const taskEventRequest = (draft: TaskEventDraft, timeZone: string, calendarId: number | null = null): CalendarRequest => ({
  method: 'POST',
  url: '/calendar/events',
  body: {
    title: draft.title,
    time_zone: timeZone,
    start: new Date(fromZonedPoint(draft.date, draft.startMinute, timeZone)).toISOString(),
    duration_minutes: draft.durationMinutes,
    location: null,
    description: null,
    color_key: 'DEFAULT',
    task_id: draft.taskId,
    recurrence: null,
    // 入れるカレンダー（ADR-0027）。省くとサーバーが既定のカレンダーへ入れる
    ...(calendarId != null ? { calendar_id: calendarId } : {}),
  },
});

const isOpen = (task: Task): boolean =>
  task.deleted_at == null && task.status !== 'DONE' && task.status !== 'CANCELLED';

/**
 * 週表示の横に並べるタスク: 未完了で残があるもの。期限が近い順（期限なしは後ろ）、
 * 同じ期限なら優先度の点の高い順、さらに題名の順。
 */
export const schedulableTasks = (tasks: readonly Task[]): Task[] =>
  tasks
    .filter((t) => isOpen(t) && t.remaining_hours != null && t.remaining_hours > 0)
    .sort((a, b) => {
      if (a.due_date !== b.due_date) {
        if (a.due_date == null) return 1;
        if (b.due_date == null) return -1;
        return a.due_date.localeCompare(b.due_date);
      }
      if (a.priority_score !== b.priority_score) return b.priority_score - a.priority_score;
      return a.title.localeCompare(b.title, 'ja');
    });

/** 予定に出すタスクの印（題名とカテゴリの色）。 */
export interface LinkedTask {
  title: string;
  color: string;
}

/** task_id → 印。`categoryColor` はカテゴリの色を決める関数（`theme.ts` のもの）。 */
export const buildLinkedTasks = (
  tasks: readonly Task[],
  categories: readonly Category[],
  categoryColor: (categoryId: number | null | undefined, apiColor?: string | null) => string,
): Map<number, LinkedTask> => {
  const colors = new Map(categories.map((c) => [c.id, c.color]));
  return new Map(tasks.map((t) => [t.id, {
    title: t.title,
    color: categoryColor(t.category_id, t.category_id != null ? colors.get(t.category_id) : null),
  }]));
};

/**
 * 予定の色。予定に色があればそれ、無ければ（既定なら）カレンダーの色（ADR-0027）、それも既定なら
 * 結んだタスクのカテゴリの色、どれも無ければ標準の予定色。
 */
export const occurrenceColor = (
  occurrence: Pick<CalendarOccurrence, 'color_key' | 'task_id'> & Partial<Pick<CalendarOccurrence, 'calendar_color_key'>>,
  linkedTasks?: ReadonlyMap<number, LinkedTask>,
): string => {
  if (occurrence.color_key !== 'DEFAULT') return eventColor(occurrence.color_key);
  if (occurrence.calendar_color_key && occurrence.calendar_color_key !== 'DEFAULT') return eventColor(occurrence.calendar_color_key);
  if (occurrence.task_id == null) return eventColor(occurrence.color_key);
  return linkedTasks?.get(occurrence.task_id)?.color ?? eventColor(occurrence.color_key);
};

/** 予定に添えるタスク名（題名と同じなら出さない）。 */
export const linkedTaskLabel = (
  occurrence: Pick<CalendarOccurrence, 'title' | 'task_id'>,
  linkedTasks?: ReadonlyMap<number, LinkedTask>,
): string | null => {
  if (occurrence.task_id == null) return null;
  const title = linkedTasks?.get(occurrence.task_id)?.title;
  return title && title !== occurrence.title ? title : null;
};
