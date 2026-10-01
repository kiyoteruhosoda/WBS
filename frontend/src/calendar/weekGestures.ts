// 週表示のドラッグの判定と時刻の計算（移植元 `WeekGestureArbitrationService` /
// `WeekInteractionMapper` / `WeekAutoScrollService` と、`WeekCalendarView` の ManipulationDelta の計算）。
//
// 時間グリッドは 1px = 1 分。ここは DOM を見ない純関数だけを置き、ポインタの追跡は
// `components/calendar/useWeekDrag.ts` が持つ。

import { MINUTES_PER_DAY, addDays, diffDays, formatMinute } from './zonedTime';

/** タップとドラッグの境（移植元 TapDistanceThreshold）。 */
export const TAP_DISTANCE_PX = 8;
/** これより短く離せばタップ（移植元 TapDurationThreshold）。 */
export const TAP_DURATION_MS = 250;
/** これより長く動かさずに押せば長押し（移植元 LongPressThreshold）。 */
export const LONG_PRESS_MS = 300;
/** 予定の上端・下端のつかみ（移植元 ResizeHandlePx）。 */
export const RESIZE_HANDLE_PX = 10;
/** 端からこの距離に入ると自動スクロール（移植元 WeekAutoScrollService.Edge）。 */
export const AUTO_SCROLL_EDGE_PX = 48;
/** 自動スクロールの 1 回の最大（移植元 MaxStep）。 */
export const AUTO_SCROLL_MAX_STEP_PX = 24;
/** 動かす・伸ばすの刻み。 */
export const SNAP_MINUTES = 15;
/** 空き枠から作る範囲の刻み（予約は :00 / :30 で取る）。 */
export const CREATE_SNAP_MINUTES = 30;
/** 伸ばし縮めの最短。 */
export const MIN_DURATION_MINUTES = 15;

export interface PointerPoint {
  x: number;
  y: number;
}

/** 移植元 `WeekGestureDecision`。 */
export type GestureDecision = 'none' | 'tap' | 'longPress' | 'drag' | 'resize' | 'scroll' | 'cancel';

export interface GestureInput {
  /** 予定の上で押した */
  onEventBlock: boolean;
  /** 予定の上端・下端のつかみで押した */
  onResizeHandle: boolean;
  start: PointerPoint;
  current: PointerPoint;
  elapsedMs: number;
  /** 同時に触れている指の数 */
  touchCount?: number;
}

/**
 * 押してからの動きで、何の操作かを決める（移植元 `WeekGestureArbitrationService.Decide`）。
 * つかみは縦の動きが勝つときだけ伸ばし縮め、横へ動かせば移動になる。
 */
export const decideGesture = ({
  onEventBlock, onResizeHandle, start, current, elapsedMs, touchCount = 1,
}: GestureInput): GestureDecision => {
  if (touchCount > 1) return 'cancel';
  const dx = current.x - start.x;
  const dy = current.y - start.y;
  const distance = Math.hypot(dx, dy);
  if (onResizeHandle && Math.abs(dy) >= TAP_DISTANCE_PX && Math.abs(dy) > Math.abs(dx)) return 'resize';
  if (onEventBlock && distance >= TAP_DISTANCE_PX) return 'drag';
  if (distance < TAP_DISTANCE_PX && elapsedMs <= TAP_DURATION_MS) return 'tap';
  if (distance < TAP_DISTANCE_PX && elapsedMs >= LONG_PRESS_MS) return 'longPress';
  return onEventBlock ? 'none' : 'scroll';
};

/**
 * 予定の中の縦位置から、上端・下端のつかみかを返す（移植元 `EdgeAt`）。
 * つかみは 10px、ただし高さの 1/3 まで（15 分の小さい塊でも、真ん中で動かせるように）。
 */
export const resizeEdgeAt = (offsetY: number, height: number): 'top' | 'bottom' | null => {
  const zone = Math.min(RESIZE_HANDLE_PX, height / 3);
  if (offsetY <= zone) return 'top';
  if (offsetY >= height - zone) return 'bottom';
  return null;
};

/**
 * 自動スクロールの量（移植元 `WeekAutoScrollService.ComputeVerticalDelta`）。
 * `pointerY` は見えている枠の上端からの位置。端 48px に入った深さの 0.2 倍、2〜24px。
 */
export const autoScrollDelta = (pointerY: number, viewportHeight: number): number => {
  const scale = (distance: number) => Math.min(AUTO_SCROLL_MAX_STEP_PX, Math.max(2, distance * 0.2));
  if (pointerY < AUTO_SCROLL_EDGE_PX) return -scale(AUTO_SCROLL_EDGE_PX - pointerY);
  if (pointerY > viewportHeight - AUTO_SCROLL_EDGE_PX) return scale(pointerY - (viewportHeight - AUTO_SCROLL_EDGE_PX));
  return 0;
};

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

/** 15 分へ丸める（四捨五入。移植元 `SnapToQuarterHour`）。 */
export const snapToQuarterHour = (minute: number): number => Math.round(minute / SNAP_MINUTES) * SNAP_MINUTES;

/** 30 分へ切り下げる（移植元 `SnapToHalfHour`）。 */
export const snapToHalfHour = (minute: number): number => Math.floor(minute / CREATE_SNAP_MINUTES) * CREATE_SNAP_MINUTES;

/**
 * 空き枠のタップで作る開始。押した 30 分の枠の頭（:00 / :30 だけ。移植元 `MapToHalfHourMinute`、
 * 3c362fa で四捨五入から切り下げへ）。グリッドの外は日の中へ寄せてから丸める。
 */
export const tapCreateMinute = (offsetY: number): number =>
  snapToHalfHour(clamp(Math.round(offsetY), 0, MINUTES_PER_DAY - 1));

/** 横位置から日の列の番号（移植元 `MapToDate`。外へ出たら端の列）。 */
export const dayIndexAt = (x: number, columnWidth: number, dayCount: number): number =>
  clamp(Math.floor(x / Math.max(1, columnWidth)), 0, Math.max(0, dayCount - 1));

/**
 * 空き枠のドラッグで作る範囲。押した 30 分の枠から、いま指している 30 分の枠までを含む
 * （上へ引いても下へ引いてもよい）。最短は 30 分。
 */
export const createRange = (anchorMinute: number, currentMinute: number): { startMinute: number; endMinute: number } => {
  const last = MINUTES_PER_DAY - CREATE_SNAP_MINUTES;
  const anchor = clamp(snapToHalfHour(anchorMinute), 0, last);
  const current = clamp(snapToHalfHour(currentMinute), 0, last);
  return { startMinute: Math.min(anchor, current), endMinute: Math.max(anchor, current) + CREATE_SNAP_MINUTES };
};

/** 回の時刻（閲覧者のタイムゾーンの、開始の日と分 ＋ 長さ）。 */
export interface OccurrenceTiming {
  date: string;
  startMinute: number;
  durationMinutes: number;
}

/** つかんだ区間（回を日ごとに割った 1 つ）。日をまたぐ回は 2 日目以降の区間をつかむこともある。 */
export interface GrabbedSegment {
  date: string;
  startMinute: number;
  /** 描いている下端（長さ 0 の回は 60 分の枠で描くので、その下端） */
  endMinute: number;
}

// 回の開始の日の 0:00 を 0 とした分 ⇄ 日と分。
const toAbsolute = (base: string, date: string, minute: number): number => diffDays(base, date) * MINUTES_PER_DAY + minute;

const fromAbsolute = (base: string, absolute: number): { date: string; startMinute: number } => {
  const days = Math.floor(absolute / MINUTES_PER_DAY);
  return { date: addDays(base, days), startMinute: absolute - days * MINUTES_PER_DAY };
};

/**
 * 刻みと最短の長さ。省けば予定の既定（15 分・最短 15 分）。締めの画面の打刻は、Shift を押している間
 * 1 分で動かす（`closing/entryGestures.ts`）。
 */
export interface SnapOptions {
  snapMinutes?: number;
  minDurationMinutes?: number;
}

const snapTo = (minute: number, step: number): number => Math.round(minute / step) * step;

/**
 * 動かした先（移植元 ManipulationDelta の移動）。つかんだ区間の上端を縦の動きぶん動かして
 * 15 分に丸め、その日の中（0:00〜23:45）に収める。日はポインタの下の列。長さは変えない。
 * 2 日目以降の区間をつかんだときは、回の開始もその分だけ前にずらす。
 */
export const moveTiming = (
  origin: OccurrenceTiming,
  grabbed: GrabbedSegment,
  targetDate: string,
  deltaMinutes: number,
  { snapMinutes = SNAP_MINUTES }: SnapOptions = {},
): OccurrenceTiming => {
  const top = clamp(snapTo(grabbed.startMinute + deltaMinutes, snapMinutes), 0, MINUTES_PER_DAY - snapMinutes);
  const offset = toAbsolute(origin.date, grabbed.date, grabbed.startMinute) - origin.startMinute;
  return { ...fromAbsolute(targetDate, top - offset), durationMinutes: origin.durationMinutes };
};

/**
 * 伸ばし縮めた後（移植元 ManipulationDelta の resize）。上端は開始を、下端は終わりを動かす。
 * 15 分に丸め、その日の中（0:00〜24:00）に収め、最短 15 分を守る。
 */
export const resizeTiming = (
  origin: OccurrenceTiming,
  grabbed: GrabbedSegment,
  edge: 'top' | 'bottom',
  deltaMinutes: number,
  { snapMinutes = SNAP_MINUTES, minDurationMinutes = MIN_DURATION_MINUTES }: SnapOptions = {},
): OccurrenceTiming => {
  const start = origin.startMinute;
  const end = start + Math.max(0, origin.durationMinutes);
  const dayBase = toAbsolute(origin.date, grabbed.date, 0);
  if (edge === 'top') {
    const top = clamp(snapTo(grabbed.startMinute + deltaMinutes, snapMinutes), 0, MINUTES_PER_DAY);
    const newStart = Math.min(dayBase + top, end - minDurationMinutes);
    return { ...fromAbsolute(origin.date, newStart), durationMinutes: end - newStart };
  }
  const bottom = clamp(snapTo(grabbed.endMinute + deltaMinutes, snapMinutes), 0, MINUTES_PER_DAY);
  const newEnd = Math.max(dayBase + bottom, start + minDurationMinutes);
  return { date: origin.date, startMinute: start, durationMinutes: newEnd - start };
};

/** ゴーストを描く 1 日分（日をまたぐ回は日ごとに割る）。 */
export interface GhostPiece {
  date: string;
  startMinute: number;
  endMinute: number;
}

/** 時刻をゴーストの区間に割る。長さ 0 でも 15 分の高さで描く（移植元 Overlay の `StartMinute + 15`）。 */
export const ghostPieces = (timing: OccurrenceTiming): GhostPiece[] => {
  const pieces: GhostPiece[] = [];
  let remaining = Math.max(MIN_DURATION_MINUTES, timing.durationMinutes);
  let date = timing.date;
  let start = timing.startMinute;
  // 壊れた長さで回り続けないよう、上限は 366 日。
  for (let i = 0; i < 366 && remaining > 0; i++) {
    const end = Math.min(MINUTES_PER_DAY, start + remaining);
    pieces.push({ date, startMinute: start, endMinute: end });
    remaining -= end - start;
    date = addDays(date, 1);
    start = 0;
  }
  return pieces;
};

/** ゴーストの時刻の表示（`09:00 – 10:30`。翌日のちょうど 0:00 に終わるなら `24:00`）。 */
export const formatTimingRange = (timing: OccurrenceTiming): string => {
  const end = timing.startMinute + Math.max(0, timing.durationMinutes);
  const endOfDay = end % MINUTES_PER_DAY;
  const endText = endOfDay === 0 && end > timing.startMinute ? '24:00' : formatMinute(endOfDay);
  return `${formatMinute(timing.startMinute)} – ${endText}`;
};

export const sameTiming =(a: OccurrenceTiming, b: OccurrenceTiming): boolean =>
  a.date === b.date && a.startMinute === b.startMinute && a.durationMinutes === b.durationMinutes;
