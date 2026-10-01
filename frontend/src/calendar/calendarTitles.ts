// 見出しの文言（移植元 AppResources.ja の MonthYearFormat「yyyy年M月」・週の
// 「yyyy/MM/dd (ddd) - yyyy/MM/dd (ddd)」・SelectedDayFormat「M月d日 (ddd)」）。

import type { TranslationKey } from '../i18n/translations';
import type { TranslateParams } from '../i18n';
import type { CalendarPosition } from './calendarNavigation';
import { addDays, dayOfMonth, dayOfWeek, yearMonthOf } from './zonedTime';
import { dayCountOf } from './calendarNavigation';

type Translate = (key: TranslationKey, params?: TranslateParams) => string;

const pad2 = (n: number): string => String(n).padStart(2, '0');

const monthNamesEn = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export const formatRangeDate = (date: string, t: Translate, weekdays: readonly string[]): string => {
  const { year, month } = yearMonthOf(date);
  return t('calendar.rangeDate', {
    year,
    month: pad2(month),
    day: pad2(dayOfMonth(date)),
    weekday: weekdays[dayOfWeek(date)],
  });
};

export const formatCalendarTitle = (
  position: CalendarPosition,
  t: Translate,
  weekdays: readonly string[],
  lang: 'ja' | 'en',
): string => {
  if (position.mode === 'month') {
    const { year, month } = yearMonthOf(position.month);
    return t('calendar.monthTitle', { year, month: lang === 'ja' ? month : monthNamesEn[month - 1] });
  }
  const last = addDays(position.weekStart, dayCountOf(position.mode) - 1);
  return t('calendar.weekRange', {
    from: formatRangeDate(position.weekStart, t, weekdays),
    to: formatRangeDate(last, t, weekdays),
  });
};

export const formatSelectedDay = (date: string, t: Translate, weekdays: readonly string[]): string =>
  t('calendar.selectedDay', {
    month: yearMonthOf(date).month,
    day: dayOfMonth(date),
    weekday: weekdays[dayOfWeek(date)],
  });

export const formatWeekHeader = (date: string, t: Translate, weekdays: readonly string[]): string =>
  t('calendar.weekHeader', {
    month: yearMonthOf(date).month,
    day: dayOfMonth(date),
    weekday: weekdays[dayOfWeek(date)],
  });
