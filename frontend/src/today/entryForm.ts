// 「今日」の画面から打刻を 1 本足す・直す（task #287、ADR-0038）。DOM を見ない純関数だけを置く。
//
// スマホで電車の中から直せるように、時刻は「時刻だけ」の欄と 15 分刻みの ± で扱う。日付は打刻の時刻が
// 落ちる日のまま動かさない（日をまたぐ打刻の始まりは前日の時刻として直す）。触らなかった時刻は秒まで元のまま送る。

import type { TimeEntry } from '../types';
import type { TimeEntryPatch } from '../api/timeEntries';
import { addDays, formatMinute, fromZonedPoint, toZonedPoint } from '../calendar/zonedTime';

/** ± のボタンの刻み（分）。押すと刻みの目盛りへ寄せる（9:07 の + は 9:15） */
export const ENTRY_STEP_MINUTES = 15;
/** 足すときに、直前の打刻が無い（または今と変わらない）ときの長さ（分） */
export const NEW_ENTRY_MINUTES = 60;

const MINUTE_MS = 60_000;

export interface EntryForm {
  taskId: number | null;
  startMs: number;
  /** null は計測中（終わりは決めない。止めるのは打刻のボタン） */
  endMs: number | null;
  memo: string;
}

export type EntryFormProblem = 'endBeforeStart' | 'future';

export const formOfEntry = (entry: TimeEntry): EntryForm => ({
  taskId: entry.task_id,
  startMs: Date.parse(entry.started_at),
  endMs: entry.ended_at == null ? null : Date.parse(entry.ended_at),
  memo: entry.memo ?? '',
});

const floorToMinute = (ms: number): number => Math.floor(ms / MINUTE_MS) * MINUTE_MS;

/**
 * 足すときの既定。始まりは今日の止まった打刻のうち最後の終わり（無ければ今の 1 時間前を 15 分へ切り下げ）、
 * 終わりは今（分へ切り下げ）。タスクは選ばせる（忘れていた作業は直前と別のことが多い）。
 */
export const newEntryForm = (
  entries: readonly TimeEntry[],
  date: string,
  timeZone: string,
  nowMs: number,
): EntryForm => {
  const endMs = floorToMinute(nowMs);
  const dayStart = fromZonedPoint(date, 0, timeZone);
  const lastEnd = entries
    .filter((e) => e.ended_at != null)
    .map((e) => Date.parse(e.ended_at as string))
    .filter((ms) => ms >= dayStart && ms <= nowMs)
    .reduce<number | null>((max, ms) => (max == null || ms > max ? ms : max), null);
  let startMs: number;
  if (lastEnd != null && endMs - lastEnd >= MINUTE_MS) {
    startMs = lastEnd;
  } else {
    const point = toZonedPoint(endMs - NEW_ENTRY_MINUTES * MINUTE_MS, timeZone);
    startMs = Math.max(
      dayStart,
      fromZonedPoint(point.date, Math.floor(point.minute / ENTRY_STEP_MINUTES) * ENTRY_STEP_MINUTES, timeZone),
    );
    if (startMs >= endMs) startMs = endMs - ENTRY_STEP_MINUTES * MINUTE_MS;
  }
  return { taskId: null, startMs, endMs, memo: '' };
};

/** 時刻の欄の値（HH:MM）と、その時刻が落ちる日。 */
export const timeFieldOf = (instantMs: number, timeZone: string): { date: string; value: string } => {
  const p = toZonedPoint(instantMs, timeZone);
  return { date: p.date, value: formatMinute(p.minute) };
};

/**
 * 時刻の欄（HH:MM）で直した瞬間。日付は元の瞬間が落ちる日のまま。読めなければ null。
 * 元と同じ HH:MM なら元の瞬間（秒まで）を返す。
 */
export const withTimeOfDay = (instantMs: number, value: string, timeZone: string): number | null => {
  const m = /^(\d{2}):(\d{2})/.exec(value);
  if (!m) return null;
  const hour = Number(m[1]);
  const minute = Number(m[2]);
  if (hour > 23 || minute > 59) return null;
  const current = timeFieldOf(instantMs, timeZone);
  if (current.value === value.slice(0, 5)) return instantMs;
  return fromZonedPoint(current.date, hour * 60 + minute, timeZone);
};

/** 24 時間の欄の分の選択肢: 5 分刻み（今の分が刻みに無ければ足す。打刻の 9:07 を選び直さずに残せる）。 */
export const minuteChoices = (current: number): number[] => {
  const steps = Array.from({ length: 12 }, (_, i) => i * 5);
  return steps.includes(current) ? steps : [...steps, current].sort((x, y) => x - y);
};

/** ± の 1 押し。刻みの目盛りへ寄せる（目盛りの上なら 1 刻み動かす）。 */
export const stepInstant = (instantMs: number, direction: 1 | -1, timeZone: string): number => {
  const p = toZonedPoint(instantMs, timeZone);
  const { minute } = p;
  const base = direction > 0
    ? Math.floor(minute / ENTRY_STEP_MINUTES) * ENTRY_STEP_MINUTES + ENTRY_STEP_MINUTES
    : minute % ENTRY_STEP_MINUTES === 0
      ? minute - ENTRY_STEP_MINUTES
      : Math.floor(minute / ENTRY_STEP_MINUTES) * ENTRY_STEP_MINUTES;
  // 日の境をまたぐときは日付を送る（0:00 の − は前日の 23:45）
  if (base < 0) return fromZonedPoint(addDays(p.date, -1), 24 * 60 + base, timeZone);
  if (base >= 24 * 60) return fromZonedPoint(addDays(p.date, 1), base - 24 * 60, timeZone);
  return fromZonedPoint(p.date, base, timeZone);
};

/** 保存できない理由（無ければ null）。未来の時刻はサーバも断るので、送る前に止める。 */
export const problemOf = (form: EntryForm, nowMs: number): EntryFormProblem | null => {
  if (form.startMs > nowMs || (form.endMs != null && form.endMs > nowMs)) return 'future';
  if (form.endMs != null && form.endMs <= form.startMs) return 'endBeforeStart';
  return null;
};

/** 直した欄だけの PATCH（何も直していなければ空）。メモは空なら null。 */
export const patchOf = (entry: TimeEntry, form: EntryForm): TimeEntryPatch => {
  const original = formOfEntry(entry);
  const patch: TimeEntryPatch = {};
  if (form.startMs !== original.startMs) patch.started_at = new Date(form.startMs).toISOString();
  if (form.endMs != null && form.endMs !== original.endMs) patch.ended_at = new Date(form.endMs).toISOString();
  if (form.taskId !== original.taskId) patch.task_id = form.taskId;
  const memo = form.memo.trim() ? form.memo : null;
  if (memo !== (entry.memo ?? null)) patch.memo = memo;
  return patch;
};

/** 今日の打刻を、一覧に出す順（始まりの順）に。 */
export const entriesInOrder = (entries: readonly TimeEntry[]): TimeEntry[] =>
  [...entries].sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at) || a.id - b.id);
