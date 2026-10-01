// 週表示の配置（移植元 `DefaultWeekEventLayoutStrategy` / `DefaultWeekAllDayLayoutStrategy`）。
//
// 時間グリッドは 1px = 1 分。重なる回は列に分け、つながった塊の中では列数をそろえる。
// 右に空いた列があれば、重ならない限りそこまで広げる。

import type { CalendarHoliday } from '../types';
import type { DaySegment } from './daySegments';
import { diffDays } from './zonedTime';

/** 長さ 0 以下でも潰れないための最小の高さ（15 分の回は 15px のまま）。 */
export const MINIMUM_EVENT_HEIGHT = 15;
/** 列の間の隙間（列幅に対する比）。 */
export const COLUMN_GAP_RATIO = 0.015;
/** 終日の帯の 1 段の高さと、帯の最小の高さ。 */
export const ALL_DAY_ROW_HEIGHT = 24;
export const ALL_DAY_CHIP_HEIGHT = 20;
export const ALL_DAY_LANE_MIN_HEIGHT = 28;

export interface WeekEventBlock {
  segment: DaySegment;
  /** px（= 分） */
  top: number;
  height: number;
  /** 日の列の幅に対する比 */
  leftRatio: number;
  widthRatio: number;
  column: number;
  groupColumns: number;
  columnSpan: number;
}

interface LayoutSlot {
  segment: DaySegment;
  start: number;
  end: number;
  column: number;
  groupColumns: number;
  columnSpan: number;
}

const overlaps = (a: LayoutSlot, b: LayoutSlot): boolean => a.start < b.end && b.start < a.end;

const bySpan = (a: LayoutSlot, b: LayoutSlot): number => a.start - b.start || a.end - b.end;

/** 移植元の `EndMinuteOfDay`: 長さ 0 の回は 60 分の枠で描く。 */
const effectiveEnd = (segment: DaySegment): number =>
  segment.endMinute <= segment.startMinute ? segment.startMinute + 60 : segment.endMinute;

const groupOverlaps = (ordered: LayoutSlot[]): LayoutSlot[][] => {
  const groups: LayoutSlot[][] = [];
  let current: LayoutSlot[] = [];
  let currentMaxEnd = -1;
  for (const slot of ordered) {
    if (current.length === 0 || slot.start < currentMaxEnd) {
      current.push(slot);
      currentMaxEnd = Math.max(currentMaxEnd, slot.end);
      continue;
    }
    groups.push(current);
    current = [slot];
    currentMaxEnd = slot.end;
  }
  if (current.length > 0) groups.push(current);
  return groups;
};

const resolveExpandableSpan = (pivot: LayoutSlot, columns: LayoutSlot[][]): number => {
  let span = 1;
  for (let next = pivot.column + 1; next < columns.length; next++) {
    if (columns[next].some((other) => overlaps(pivot, other))) break;
    span++;
  }
  return Math.max(1, span);
};

const assignColumns = (group: LayoutSlot[]): void => {
  const columns: LayoutSlot[][] = [];
  for (const slot of [...group].sort(bySpan)) {
    let column = 0;
    while (column < columns.length && columns[column].some((existing) => overlaps(existing, slot))) column++;
    if (column === columns.length) columns.push([]);
    slot.column = column;
    columns[column].push(slot);
  }
  // 塊の中は列数をそろえる（回ごとの重なり数で割ると、長い回が細く、隣とずれる）。
  for (const slot of group) {
    slot.groupColumns = columns.length;
    slot.columnSpan = resolveExpandableSpan(slot, columns);
  }
};

const toBlock = (slot: LayoutSlot): WeekEventBlock => {
  const height = Math.max(MINIMUM_EVENT_HEIGHT, slot.end - slot.start);
  let leftRatio = 0;
  let widthRatio = 1;
  if (slot.groupColumns > 1) {
    const total = slot.groupColumns;
    const baseWidth = (1 - COLUMN_GAP_RATIO * (total - 1)) / total;
    widthRatio = baseWidth * slot.columnSpan + COLUMN_GAP_RATIO * (slot.columnSpan - 1);
    leftRatio = slot.column * (baseWidth + COLUMN_GAP_RATIO);
  }
  return {
    segment: slot.segment,
    top: slot.start,
    height,
    leftRatio,
    widthRatio,
    column: slot.column,
    groupColumns: slot.groupColumns,
    columnSpan: slot.columnSpan,
  };
};

/** 1 日分の時刻付きの区間を並べる（終日は除く）。返す順は開始・終了の順。 */
export const layoutTimedSegments = (segments: readonly DaySegment[]): WeekEventBlock[] => {
  const slots: LayoutSlot[] = segments
    .filter((s) => !s.isAllDay)
    .map((segment) => {
      const start = segment.startMinute;
      return { segment, start, end: Math.max(start + 1, effectiveEnd(segment)), column: 0, groupColumns: 1, columnSpan: 1 };
    })
    .sort(bySpan);
  for (const group of groupOverlaps(slots)) assignColumns(group);
  return slots.map(toBlock);
};

export interface AllDayBlock {
  /** 予定の区間。祝日のときは null */
  segment: DaySegment | null;
  holiday: CalendarHoliday | null;
  /** 表示している最初の日からの列 */
  column: number;
  widthColumns: number;
  row: number;
}

export interface AllDayLaneLayout {
  blocks: AllDayBlock[];
  rowCount: number;
  /** 帯の高さ（px）。移植元の `WeekAllDayLaneHeight` */
  height: number;
}

/**
 * 終日の帯。終日の回は 1 日ずつ（複数日の終日は持たない。time-model §6）なので、日の列に
 * 置き、同じ日に重なれば段を下げる。表示している日に祝日があれば、祝日を 0 段目に置き、
 * 予定は 1 段ずつ下げる。
 */
export const layoutAllDayLane = (
  segments: readonly DaySegment[],
  firstDate: string,
  dayCount: number,
  holidays: readonly CalendarHoliday[],
): AllDayLaneLayout => {
  const spans = segments
    .filter((s) => s.isAllDay)
    .map((segment) => ({ segment, column: diffDays(firstDate, segment.date) }))
    .filter((s) => s.column >= 0 && s.column < dayCount)
    .sort((a, b) => a.column - b.column);

  const rows: { column: number; widthColumns: number }[][] = [];
  const placed: AllDayBlock[] = [];
  for (const span of spans) {
    const block = { column: span.column, widthColumns: 1 };
    let row = 0;
    while (
      row < rows.length &&
      rows[row].some((x) => x.column < block.column + block.widthColumns && block.column < x.column + x.widthColumns)
    ) row++;
    if (row === rows.length) rows.push([]);
    rows[row].push(block);
    placed.push({ segment: span.segment, holiday: null, column: span.column, widthColumns: 1, row });
  }

  const visibleHolidays = holidays
    .map((holiday) => ({ holiday, column: diffDays(firstDate, holiday.date) }))
    .filter((h) => h.column >= 0 && h.column < dayCount);
  // 同じ日に祝日が 2 つ（別の営業日カレンダー）あれば先のものだけ（移植元と同じ）。
  const holidayBlocks: AllDayBlock[] = [];
  const seen = new Set<number>();
  for (const h of visibleHolidays) {
    if (seen.has(h.column)) continue;
    seen.add(h.column);
    holidayBlocks.push({ segment: null, holiday: h.holiday, column: h.column, widthColumns: 1, row: 0 });
  }

  const shift = holidayBlocks.length > 0 ? 1 : 0;
  const blocks = [...placed.map((b) => ({ ...b, row: b.row + shift })), ...holidayBlocks];
  const rowCount = blocks.reduce((max, b) => Math.max(max, b.row + 1), 0);
  return {
    blocks,
    rowCount,
    height: Math.max(ALL_DAY_LANE_MIN_HEIGHT, Math.max(1, rowCount) * ALL_DAY_ROW_HEIGHT),
  };
};

/**
 * 開いたときに送る位置（移植元 `WeekCalendarView.ComputeDefaultAnchor`）。
 * 今週なら今の時刻の 4 時間前、それ以外は 9:00。
 */
export const defaultScrollTop = (isCurrentWeek: boolean, nowMinute: number): number => {
  const nineAm = 9 * 60;
  const anchor = isCurrentWeek && nowMinute > 0 ? nowMinute - 240 : nineAm;
  return Math.max(0, anchor);
};

/** 過去の影の高さ（移植元 `WeekDayColumn.PastShadeHeight`）。過ぎた日は下まで、今日は今まで。 */
export const pastShadeHeight = (date: string, today: string, nowMinute: number, dayHeight: number): number => {
  if (date < today) return dayHeight;
  if (date === today) return Math.min(Math.max(nowMinute, 0), dayHeight);
  return 0;
};

/** グリッドの中の縦位置（px = 分）から、刻みに丸めた分を出す（ドラッグ #158 で使う口）。 */
export const minuteAtOffset = (offsetY: number, snapMinutes = 15): number => {
  const clamped = Math.min(Math.max(offsetY, 0), 24 * 60 - 1);
  return Math.floor(clamped / snapMinutes) * snapMinutes;
};
