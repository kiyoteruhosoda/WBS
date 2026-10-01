// 締めの画面（task #161 / ADR-0012・ADR-0015）: API の応答 → 表示の形。
//
// 時間グリッドは週表示と同じ 1px = 1 分で、各日の列を左（予定）と右（打刻）に分ける。打刻は秒まで
// 持つので、区間の分は小数のまま（9:07:30 は 547.5）。ここは DOM を見ない純関数だけを置く。

import type {
  CalendarOccurrence, ClosingBoard, DailyTaskTotal, Task, TimeEntry,
} from '../types';
import type { TimedSpan } from '../calendar/weekLayout';
import { MINUTES_PER_DAY, addDays, diffDays, formatMinute, toZonedPoint } from '../calendar/zonedTime';

/** ある 1 日の中の、打刻の 1 区間。 */
export interface EntrySegment extends TimedSpan {
  /** 打刻の id ＋ 日（区間ごとに一意） */
  key: string;
  entry: TimeEntry;
  /** 利用者のローカル日 */
  date: string;
  /** その日の 0:00 からの分（小数あり） */
  startMinute: number;
  endMinute: number;
  isAllDay: false;
  continuesFromPreviousDay: boolean;
  continuesToNextDay: boolean;
}

// 壊れたデータで回り続けないための上限（止め忘れが何日も続いても 1 か月まで）。
const MAX_DAYS = 31;

/** 打刻の始まり（ミリ秒）。 */
export const entryStartMs = (entry: TimeEntry): number => Date.parse(entry.started_at);

/** 打刻の終わり（ミリ秒）。走っている打刻は今。 */
export const entryEndMs = (entry: TimeEntry, nowMs: number): number =>
  entry.ended_at != null ? Date.parse(entry.ended_at) : Math.max(nowMs, entryStartMs(entry));

/**
 * 瞬間 → その日の 0:00 からの分（小数あり）。タイムゾーンのずれは分単位なので、秒は瞬間のまま足す。
 */
export const zonedMinuteOf = (instantMs: number, timeZone: string): { date: string; minute: number } => {
  const p = toZonedPoint(instantMs, timeZone);
  const seconds = (((instantMs % 60_000) + 60_000) % 60_000) / 60_000;
  return { date: p.date, minute: p.minute + seconds };
};

/** 打刻を、利用者のローカル 0:00 で日ごとの区間に割る（長さ 0 の打刻は長さ 0 の区間 1 つ）。 */
export const splitEntryIntoDaySegments = (entry: TimeEntry, timeZone: string, nowMs: number): EntrySegment[] => {
  const startMs = entryStartMs(entry);
  const endMs = entryEndMs(entry, nowMs);
  const start = zonedMinuteOf(startMs, timeZone);
  const end = zonedMinuteOf(endMs, timeZone);
  const base = { entry, isAllDay: false as const };
  if (endMs <= startMs) {
    return [{
      ...base, key: `${entry.id}@${start.date}`, date: start.date, startMinute: start.minute, endMinute: start.minute,
      continuesFromPreviousDay: false, continuesToNextDay: false,
    }];
  }
  const segments: EntrySegment[] = [];
  let date = start.date;
  for (let i = 0; i < MAX_DAYS; i++) {
    const isFirst = date === start.date;
    const isLast = date === end.date;
    // ちょうど翌 0:00 に終わる打刻は、翌日に長さ 0 の区間を作らない。
    if (isLast && !isFirst && end.minute === 0) break;
    segments.push({
      ...base,
      key: `${entry.id}@${date}`,
      date,
      startMinute: isFirst ? start.minute : 0,
      endMinute: isLast ? end.minute : MINUTES_PER_DAY,
      continuesFromPreviousDay: !isFirst,
      continuesToNextDay: !isLast && !(addDays(date, 1) === end.date && end.minute === 0),
    });
    if (isLast) break;
    date = addDays(date, 1);
  }
  return segments;
};

/** 打刻を割って、期間の日（`dates`）ごとに束ねる。期間の外にはみ出した区間は出さない。 */
export const groupEntrySegmentsByDate = (
  entries: readonly TimeEntry[],
  timeZone: string,
  nowMs: number,
  dates: readonly string[],
): Map<string, EntrySegment[]> => {
  const byDate = new Map<string, EntrySegment[]>(dates.map((d) => [d, []]));
  for (const entry of entries) {
    for (const segment of splitEntryIntoDaySegments(entry, timeZone, nowMs)) {
      byDate.get(segment.date)?.push(segment);
    }
  }
  for (const list of byDate.values()) {
    list.sort((a, b) => a.startMinute - b.startMinute || a.endMinute - b.endMinute || a.entry.id - b.entry.id);
  }
  return byDate;
};

/** 区間の時刻の表示（`09:07 – 10:30`。秒は切り捨て。下端が翌 0:00 なら 24:00）。 */
export const formatEntrySegmentRange = (segment: Pick<EntrySegment, 'startMinute' | 'endMinute'>): string =>
  `${formatMinute(Math.floor(segment.startMinute))} – ${formatMinute(Math.floor(segment.endMinute))}`;

// ── 予定の回 ────────────────────────────────────────────────────────────

/** 回の範囲（ミリ秒、半開）。 */
export const occurrenceRange = (occurrence: CalendarOccurrence): { startMs: number; endMs: number } => {
  const startMs = Date.parse(occurrence.start);
  return { startMs, endMs: startMs + Math.max(0, occurrence.duration_minutes) * 60_000 };
};

/** 回を打刻にできるか（終日でなく、もう終わっている。サーバは終わっていない回を 422 で断る）。 */
export const canTurnIntoEntry = (occurrence: CalendarOccurrence, nowMs: number): boolean =>
  !occurrence.is_all_day && occurrence.duration_minutes > 0 && occurrenceRange(occurrence).endMs <= nowMs;

/** 正の長さで重なる秒数（接しているだけは 0）。 */
const overlapMs = (a: { startMs: number; endMs: number }, b: { startMs: number; endMs: number }): number =>
  Math.max(0, Math.min(a.endMs, b.endMs) - Math.max(a.startMs, b.startMs));

/** 回の時間に掛かる打刻（「予定どおり」で打刻にする前の警告）。 */
export const entriesOverlappingOccurrence = (
  occurrence: CalendarOccurrence,
  entries: readonly TimeEntry[],
  nowMs: number,
): TimeEntry[] => {
  const range = occurrenceRange(occurrence);
  return entries.filter((e) => overlapMs(range, { startMs: entryStartMs(e), endMs: entryEndMs(e, nowMs) }) > 0);
};

// ── 気付かせる物 ────────────────────────────────────────────────────────

export type FindingKind = 'unassigned' | 'longRunning' | 'overlap' | 'missed';

/** 一覧の 1 行。押すとその打刻（予定の回）へ飛ぶ。 */
export interface FindingItem {
  key: string;
  kind: FindingKind;
  /** 飛ぶ先・選ぶ打刻（予定の回なら空） */
  entryIds: number[];
  occurrence: CalendarOccurrence | null;
  /** 並べる・表示する時刻（打刻・回の始まり） */
  startMs: number;
  endMs: number;
  /** 重なりの長さ（秒）。ほかは null */
  overlapSeconds: number | null;
  /** 表示に使う題名（打刻のタスク名・回の題名。未割当は null） */
  title: string | null;
}

/** 確定を止める物（未割当）が先、あとは止め忘れ・重なり・打刻の無い予定。種類の中は時刻の順。 */
const KIND_ORDER: FindingKind[] = ['unassigned', 'longRunning', 'overlap', 'missed'];

export const buildFindingItems = (board: ClosingBoard, nowMs: number): FindingItem[] => {
  const byId = new Map(board.entries.map((e) => [e.id, e]));
  const items: FindingItem[] = [];
  const entryItem = (kind: FindingKind, id: number): void => {
    const entry = byId.get(id);
    if (!entry) return;
    items.push({
      key: `${kind}:${id}`, kind, entryIds: [id], occurrence: null,
      startMs: entryStartMs(entry), endMs: entryEndMs(entry, nowMs), overlapSeconds: null,
      title: kind === 'unassigned' ? null : entry.task_title,
    });
  };
  board.findings.unassigned_entry_ids.forEach((id) => entryItem('unassigned', id));
  board.findings.long_running_entry_ids.forEach((id) => entryItem('longRunning', id));
  for (const overlap of board.findings.overlaps) {
    const [a, b] = overlap.entry_ids.map((id) => byId.get(id));
    if (!a || !b) continue;
    const startMs = Math.max(entryStartMs(a), entryStartMs(b));
    items.push({
      key: `overlap:${a.id}-${b.id}`, kind: 'overlap', entryIds: [a.id, b.id], occurrence: null,
      startMs, endMs: startMs + overlap.seconds * 1000, overlapSeconds: overlap.seconds,
      title: a.task_title ?? b.task_title,
    });
  }
  for (const o of board.findings.missed_occurrences) {
    const range = occurrenceRange(o);
    items.push({
      key: `missed:${o.id}`, kind: 'missed', entryIds: [], occurrence: o,
      startMs: range.startMs, endMs: range.endMs, overlapSeconds: null, title: o.title,
    });
  }
  return items.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || a.startMs - b.startMs);
};

/** 打刻ごとの印（グリッドで枠の色を変える）。 */
export interface EntryMarks {
  unassigned: ReadonlySet<number>;
  longRunning: ReadonlySet<number>;
  overlapping: ReadonlySet<number>;
}

export const entryMarksOf = (board: ClosingBoard): EntryMarks => ({
  unassigned: new Set(board.findings.unassigned_entry_ids),
  longRunning: new Set(board.findings.long_running_entry_ids),
  overlapping: new Set(board.findings.overlaps.flatMap((o) => o.entry_ids)),
});

/** 打刻の無い予定の回（グリッドで目立たせる）。 */
export const missedOccurrenceIds = (board: ClosingBoard): Set<string> =>
  new Set(board.findings.missed_occurrences.map((o) => o.id));

// ── 合計の表 ────────────────────────────────────────────────────────────

export interface TotalsRow {
  /** null は未割当 */
  taskId: number | null;
  title: string | null;
  /** 日 → 秒 */
  byDate: Record<string, number>;
  total: number;
}

export interface TotalsTable {
  dates: string[];
  rows: TotalsRow[];
  /** 日 → 秒（全タスク） */
  dayTotals: Record<string, number>;
  grandTotal: number;
}

/** 日ごと・タスクごとの合計 → 行がタスク、列が日の表。行は合計の多い順、未割当は最後。 */
export const buildTotalsTable = (totals: readonly DailyTaskTotal[], dates: readonly string[]): TotalsTable => {
  const rows = new Map<string, TotalsRow>();
  const dayTotals: Record<string, number> = Object.fromEntries(dates.map((d) => [d, 0]));
  let grandTotal = 0;
  for (const t of totals) {
    const key = t.task_id == null ? 'none' : String(t.task_id);
    let row = rows.get(key);
    if (!row) {
      row = { taskId: t.task_id, title: t.task_title, byDate: {}, total: 0 };
      rows.set(key, row);
    }
    row.byDate[t.work_date] = (row.byDate[t.work_date] ?? 0) + t.seconds;
    row.total += t.seconds;
    dayTotals[t.work_date] = (dayTotals[t.work_date] ?? 0) + t.seconds;
    grandTotal += t.seconds;
  }
  const ordered = [...rows.values()].sort((a, b) => {
    if ((a.taskId == null) !== (b.taskId == null)) return a.taskId == null ? 1 : -1;
    return b.total - a.total || (a.title ?? '').localeCompare(b.title ?? '', 'ja');
  });
  return { dates: [...dates], rows: ordered, dayTotals, grandTotal };
};

const pad2 = (n: number): string => String(n).padStart(2, '0');

/**
 * 表の時間（#163: 表示だけ 15 分単位）。15 分へ四捨五入して `H:MM`。0 秒は空。
 * 正確な長さは `formatExactDuration`（確定は丸めない）。
 */
export const formatQuarterHours = (seconds: number): string => {
  if (seconds <= 0) return '';
  const quarters = Math.round(seconds / 900);
  const minutes = quarters * 15;
  return `${Math.floor(minutes / 60)}:${pad2(minutes % 60)}`;
};

/** 正確な長さ（`H:MM:SS`）。 */
export const formatExactDuration = (seconds: number): string => {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 3600)}:${pad2(Math.floor((s % 3600) / 60))}:${pad2(s % 60)}`;
};

// ── タスクを振る ────────────────────────────────────────────────────────

export interface TaskCandidate {
  taskId: number;
  title: string;
  /** 選んだ打刻と同じ時間の予定に結ばれたタスク */
  fromSchedule: boolean;
}

const isOpenTask = (task: Task): boolean =>
  task.deleted_at == null && task.status !== 'DONE' && task.status !== 'CANCELLED';

/**
 * 振る先の候補。選んだ打刻と時間が重なる予定の回のタスクを、重なりの長い順に先頭へ。
 * そのあとに未完了のタスクを題名の順で（予定のタスクは重ねて出さない）。
 */
export const assignCandidates = (
  selected: readonly TimeEntry[],
  occurrences: readonly CalendarOccurrence[],
  tasks: readonly Task[],
  nowMs: number,
): TaskCandidate[] => {
  const tasksById = new Map(tasks.filter((t) => t.deleted_at == null).map((t) => [t.id, t]));
  const scheduled = new Map<number, { title: string; overlap: number }>();
  for (const o of occurrences) {
    if (o.task_id == null || o.is_all_day) continue;
    const range = occurrenceRange(o);
    const overlap = selected.reduce(
      (sum, e) => sum + overlapMs(range, { startMs: entryStartMs(e), endMs: entryEndMs(e, nowMs) }), 0,
    );
    if (overlap <= 0) continue;
    const task = tasksById.get(o.task_id);
    // 消えた・他人のタスクは振れないので候補にしない
    if (!task) continue;
    const prev = scheduled.get(o.task_id);
    scheduled.set(o.task_id, { title: task.title, overlap: (prev?.overlap ?? 0) + overlap });
  }
  const head: TaskCandidate[] = [...scheduled.entries()]
    .sort((a, b) => b[1].overlap - a[1].overlap || a[1].title.localeCompare(b[1].title, 'ja'))
    .map(([taskId, s]) => ({ taskId, title: s.title, fromSchedule: true }));
  const rest: TaskCandidate[] = [...tasksById.values()]
    .filter((t) => isOpenTask(t) && !scheduled.has(t.id))
    .sort((a, b) => a.title.localeCompare(b.title, 'ja'))
    .map((t) => ({ taskId: t.id, title: t.title, fromSchedule: false }));
  return [...head, ...rest];
};

/** 打刻の範囲の表示（`09:07 – 10:30`。秒は切り捨て。日をまたげば終わりに `+1` などの日数を添える）。 */
export const formatEntryRange = (range: { startMs: number; endMs: number }, timeZone: string): string => {
  const start = zonedMinuteOf(range.startMs, timeZone);
  const end = zonedMinuteOf(range.endMs, timeZone);
  const days = diffDays(start.date, end.date);
  const endText = days === 1 && Math.floor(end.minute) === 0 ? '24:00' : formatMinute(Math.floor(end.minute));
  const suffix = days > 1 || (days === 1 && Math.floor(end.minute) !== 0) ? ` (+${days})` : '';
  return `${formatMinute(Math.floor(start.minute))} – ${endText}${suffix}`;
};
