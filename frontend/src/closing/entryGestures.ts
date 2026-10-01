// 締めの画面の打刻のドラッグ（task #161 / ADR-0016）。週表示の判定・時刻の計算（`calendar/weekGestures.ts`）を
// そのまま使い、打刻に要る違いだけをここに置く:
// - 打刻は秒まで持つ。動かしたら長さ（秒）はそのまま、伸ばしたら動かした側の端だけが変わる
// - 刻みは 15 分。Shift を押している間は 1 分（細かく合わせる逃げ道）
// - 空き時間から作る範囲も同じ刻み（予定の 30 分ではない）
// ポインタの追跡は `components/closing/useClosingDrag.ts`。

import type { GrabbedSegment, OccurrenceTiming } from '../calendar/weekGestures';
import { SNAP_MINUTES, moveTiming, resizeTiming } from '../calendar/weekGestures';
import { MINUTES_PER_DAY, fromZonedPoint } from '../calendar/zonedTime';
import type { EntryRange } from './closingRequests';
import { zonedMinuteOf } from './closingBoard';

/** Shift を押している間の刻み。 */
export const FINE_SNAP_MINUTES = 1;

export const snapMinutesFor = (fine: boolean): number => (fine ? FINE_SNAP_MINUTES : SNAP_MINUTES);

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

/** そのタイムゾーンの壁時計（日 ＋ 分。小数の分は秒）→ 瞬間（ミリ秒）。 */
export const zonedInstant = (date: string, minute: number, timeZone: string): number => {
  const whole = Math.floor(minute);
  return fromZonedPoint(date, whole, timeZone) + Math.round((minute - whole) * 60_000);
};

/** 打刻の範囲 → 週表示の計算に渡す形（開始の日と分 ＋ 長さ。どちらも小数あり）。 */
export const entryTiming = (range: EntryRange, timeZone: string): OccurrenceTiming => {
  const start = zonedMinuteOf(range.startMs, timeZone);
  return { date: start.date, startMinute: start.minute, durationMinutes: Math.max(0, range.endMs - range.startMs) / 60_000 };
};

/**
 * ドラッグした後の打刻の範囲。
 * - 動かす: つかんだ区間の上端を刻みに合わせ、長さ（秒）は元のまま
 * - 上端を伸ばす: 始まりだけが変わる / 下端を伸ばす: 終わりだけが変わる（最短は刻み 1 つ）
 */
export const draggedEntryRange = (
  kind: 'move' | 'resize',
  edge: 'top' | 'bottom' | null,
  original: EntryRange,
  grabbed: GrabbedSegment,
  targetDate: string,
  deltaMinutes: number,
  timeZone: string,
  fine: boolean,
): EntryRange => {
  const snapMinutes = snapMinutesFor(fine);
  const origin = entryTiming(original, timeZone);
  if (kind === 'move') {
    const timing = moveTiming(origin, grabbed, targetDate, deltaMinutes, { snapMinutes });
    const startMs = zonedInstant(timing.date, timing.startMinute, timeZone);
    return { startMs, endMs: startMs + (original.endMs - original.startMs) };
  }
  const timing = resizeTiming(origin, grabbed, edge ?? 'bottom', deltaMinutes, { snapMinutes, minDurationMinutes: snapMinutes });
  if (edge === 'top') return { startMs: zonedInstant(timing.date, timing.startMinute, timeZone), endMs: original.endMs };
  return { startMs: original.startMs, endMs: zonedInstant(timing.date, timing.startMinute + timing.durationMinutes, timeZone) };
};

export const sameRange = (a: EntryRange, b: EntryRange): boolean => a.startMs === b.startMs && a.endMs === b.endMs;

/**
 * 空き時間のドラッグで作る範囲（その日の分）。押した刻みの枠から、いま指している枠までを含む
 * （上へ引いても下へ引いてもよい）。最短は刻み 1 つ。
 */
export const entryCreateRange = (
  anchorMinute: number,
  currentMinute: number,
  fine: boolean,
): { startMinute: number; endMinute: number } => {
  const step = snapMinutesFor(fine);
  const last = MINUTES_PER_DAY - step;
  const floorTo = (m: number) => clamp(Math.floor(m / step) * step, 0, last);
  const a = floorTo(anchorMinute);
  const c = floorTo(currentMinute);
  return { startMinute: Math.min(a, c), endMinute: Math.max(a, c) + step };
};

/**
 * 分ける位置。押した位置（その日の分）を刻みに合わせ、打刻の内側（始まりと終わりの間、両端を除く）に
 * あれば瞬間を、外なら null を返す。
 */
export const splitInstantAt = (
  range: EntryRange,
  date: string,
  offsetMinute: number,
  timeZone: string,
  fine: boolean,
): number | null => {
  const step = snapMinutesFor(fine);
  const minute = clamp(Math.round(offsetMinute / step) * step, 0, MINUTES_PER_DAY);
  const at = zonedInstant(date, minute, timeZone);
  return at > range.startMs && at < range.endMs ? at : null;
};

/** 横位置 → いちばん近い列の番号（列は左右の端で持つ。列の外なら近い方）。列が無ければ -1。 */
export const laneIndexAt = (x: number, lanes: readonly { left: number; right: number }[]): number => {
  let best = -1;
  let bestDistance = Infinity;
  lanes.forEach((lane, i) => {
    const distance = x < lane.left ? lane.left - x : x >= lane.right ? x - lane.right + 1 : 0;
    if (distance < bestDistance) {
      best = i;
      bestDistance = distance;
    }
  });
  return best;
};

/** `<input type="datetime-local">` の値（`YYYY-MM-DDTHH:MM`、そのタイムゾーンの壁時計）。 */
export const toLocalInputValue = (instantMs: number, timeZone: string): string => {
  const p = zonedMinuteOf(instantMs, timeZone);
  const m = Math.floor(p.minute);
  return `${p.date}T${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
};

/** `<input type="datetime-local">` の値 → 瞬間（読めなければ null）。 */
export const fromLocalInputValue = (value: string, timeZone: string): number | null => {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!m) return null;
  const hour = Number(m[2]);
  const minute = Number(m[3]);
  if (hour > 23 || minute > 59) return null;
  return fromZonedPoint(m[1], hour * 60 + minute, timeZone);
};
