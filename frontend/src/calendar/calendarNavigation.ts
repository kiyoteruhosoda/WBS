// 表示の切り替えと前後の移動（移植元 `CalendarViewModel` の Navigate / GoToday / SetDisplayMode）。
//
// 週は日曜始まり。平日表示はその週の月〜金で、日曜から入ると翌日の月曜へ寄せる
// （前の週の月曜へ戻らない）。

import { addDays, addMonths, dayOfWeek, firstOfMonth } from './zonedTime';

export type CalendarMode = 'month' | 'week' | 'weekdays';

export interface CalendarPosition {
  mode: CalendarMode;
  /** 表示している月の 1 日 */
  month: string;
  /** 週表示は日曜、平日表示は月曜 */
  weekStart: string;
}

export const sundayOf = (date: string): string => addDays(date, -dayOfWeek(date));

/** 日曜は翌日の月曜、それ以外はその週の月曜。 */
export const alignToMonday = (date: string): string =>
  dayOfWeek(date) === 0 ? addDays(date, 1) : addDays(date, -((dayOfWeek(date) + 6) % 7));

export const initialPosition = (mode: CalendarMode, date: string): CalendarPosition => ({
  mode,
  month: firstOfMonth(date),
  weekStart: mode === 'weekdays' ? alignToMonday(date) : sundayOf(date),
});

export const dayCountOf = (mode: CalendarMode): number => (mode === 'weekdays' ? 5 : 7);

export const navigate = (position: CalendarPosition, step: number): CalendarPosition => {
  if (position.mode === 'month') {
    const month = addMonths(position.month, step);
    return { ...position, month, weekStart: sundayOf(month) };
  }
  const weekStart = addDays(position.weekStart, step * 7);
  return { ...position, weekStart, month: firstOfMonth(weekStart) };
};

export const goToday = (position: CalendarPosition, today: string): CalendarPosition =>
  initialPosition(position.mode, today);

export const switchMode = (position: CalendarPosition, mode: CalendarMode): CalendarPosition => {
  if (mode === position.mode) return position;
  if (mode === 'weekdays') return { ...position, mode, weekStart: alignToMonday(position.weekStart) };
  if (mode === 'week') return { ...position, mode, weekStart: sundayOf(position.weekStart) };
  return { ...position, mode };
};

/** 月表示の 42 日（1 日を含む週の日曜から 6 週）。 */
export const monthGridDates = (month: string): string[] => {
  const start = sundayOf(month);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
};

/** 表示している日（週・平日は列の日、月は 42 日）。 */
export const visibleDates = (position: CalendarPosition): string[] =>
  position.mode === 'month'
    ? monthGridDates(position.month)
    : Array.from({ length: dayCountOf(position.mode) }, (_, i) => addDays(position.weekStart, i));

/** API に問う期間（両端を含む）。 */
export const visibleRange = (position: CalendarPosition): { from: string; to: string } => {
  const dates = visibleDates(position);
  return { from: dates[0], to: dates[dates.length - 1] };
};

/** 今の週を表示しているか（現在時刻の線と、送る位置に使う）。 */
export const containsDate = (position: CalendarPosition, date: string): boolean => {
  const dates = visibleDates(position);
  return dates[0] <= date && date <= dates[dates.length - 1];
};
