// 締めの期間（task #163 / ADR-0012）: 1〜15 日 / 16 日〜末日。日付は利用者のタイムゾーンの `YYYY-MM-DD`。
//
// 期間の区切りの瞬間はサーバが決める（`ClosingPeriod.starts_at` / `ends_at`）。ここは画面の送り
// （前の期間・次の期間）と、期間の日の並びだけを持つ。

import type { ClosingPeriodRange } from '../types';
import { addDays, addMonths, dayOfMonth, diffDays, firstOfMonth } from '../calendar/zonedTime';

/** `/closing?period=<初日>` のクエリの名前。 */
export const PERIOD_PARAM = 'period';

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** その日を含む期間。 */
export const periodOf = (date: string): ClosingPeriodRange => {
  const monthFirst = firstOfMonth(date);
  if (dayOfMonth(date) <= 15) return { first_day: monthFirst, last_day: addDays(monthFirst, 14) };
  return { first_day: addDays(monthFirst, 15), last_day: addDays(addMonths(monthFirst, 1), -1) };
};

export const previousPeriod = (firstDay: string): ClosingPeriodRange => periodOf(addDays(firstDay, -1));

export const nextPeriod = (firstDay: string): ClosingPeriodRange => periodOf(addDays(periodOf(firstDay).last_day, 1));

/** 期間の日（初日から末日まで）。 */
export const periodDates = (range: ClosingPeriodRange): string[] => {
  const count = diffDays(range.first_day, range.last_day) + 1;
  return Array.from({ length: Math.max(0, Math.min(count, 31)) }, (_, i) => addDays(range.first_day, i));
};

/** クエリの値 → 期間の初日（1 日か 16 日でなければ null）。 */
export const parsePeriodParam = (value: string | null): string | null => {
  if (value == null || !DATE_PATTERN.test(value)) return null;
  // 2026-02-31 のような日は暦に直すと別の日になる
  if (addDays(value, 0) !== value) return null;
  const day = dayOfMonth(value);
  return day === 1 || day === 16 ? value : null;
};

/** 表示: `9/1〜9/15` の部品（年は別に出す）。 */
export const periodLabelParts = (range: ClosingPeriodRange): { year: number; from: string; to: string } => {
  const md = (date: string) => `${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))}`;
  return { year: Number(range.first_day.slice(0, 4)), from: md(range.first_day), to: md(range.last_day) };
};
