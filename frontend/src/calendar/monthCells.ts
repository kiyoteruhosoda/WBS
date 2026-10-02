// 月表示のマス（移植元 `CalendarDayCell` / `CalendarViewModel.LoadMonth`）。

import type { CalendarHoliday } from '../types';
import type { DaySegment } from './daySegments';
import type { CalendarDeadline } from './taskDeadlines';
import { dayOfWeek, firstOfMonth } from './zonedTime';
import { monthGridDates } from './calendarNavigation';

export interface MonthCell {
  date: string;
  isCurrentMonth: boolean;
  isToday: boolean;
  /** 今日より前（当月の外の日も含む） */
  isPast: boolean;
  /** 0 = 日曜 … 6 = 土曜 */
  dayOfWeek: number;
  holiday: CalendarHoliday | null;
  segments: DaySegment[];
  /** その日が期限のタスク・マイルストーン（予定の後に並べる） */
  deadlines: CalendarDeadline[];
}

/** 日付 → 祝日（同じ日に 2 つあれば先のもの）。 */
export const holidaysByDate = (holidays: readonly CalendarHoliday[]): Map<string, CalendarHoliday> => {
  const map = new Map<string, CalendarHoliday>();
  for (const h of holidays) if (!map.has(h.date)) map.set(h.date, h);
  return map;
};

export const buildMonthCells = (
  month: string,
  today: string,
  segmentsByDate: ReadonlyMap<string, DaySegment[]>,
  holidays: readonly CalendarHoliday[],
  deadlinesByDate: ReadonlyMap<string, CalendarDeadline[]> = new Map(),
): MonthCell[] => {
  const holidayMap = holidaysByDate(holidays);
  const monthKey = firstOfMonth(month);
  return monthGridDates(monthKey).map((date) => ({
    date,
    isCurrentMonth: firstOfMonth(date) === monthKey,
    isToday: date === today,
    isPast: date < today,
    dayOfWeek: dayOfWeek(date),
    holiday: holidayMap.get(date) ?? null,
    segments: segmentsByDate.get(date) ?? [],
    deadlines: deadlinesByDate.get(date) ?? [],
  }));
};

// マスの見出し（日付の丸 28px ＋ 余白）と、チップ 1 段（14px ＋ 間 2px）。
export const MONTH_CELL_HEADER_HEIGHT = 36;
export const MONTH_CHIP_ROW_HEIGHT = 16;

/** 名前で示す休み（祝日・公休・私の休み）か。曜日の休みの帯（`subtle`）は地の色と見出しの色を変えない。 */
export const isNamedDayOff = (holiday: CalendarHoliday | null | undefined): boolean =>
  holiday != null && !holiday.subtle;

/** マスの高さに入るチップの段数（休みのチップが 1 段使う）。 */
export const availableChipRows = (cellHeight: number, hasHoliday: boolean): number =>
  Math.max(1, Math.floor((cellHeight - MONTH_CELL_HEADER_HEIGHT) / MONTH_CHIP_ROW_HEIGHT) - (hasHoliday ? 1 : 0));

/**
 * 描くチップの数。全部入るなら全部、入らなければ最後の段を「+N 件」に譲る
 * （空いた段があるのに +N を出さない。移植元 `CalendarDayCell.VisibleChipCount`）。
 */
export const visibleChipCount = (eventCount: number, availableRows: number): number =>
  eventCount <= availableRows ? eventCount : Math.max(1, availableRows - 1);
