import { useQuery } from '@tanstack/react-query';
import { getCalendars, getDayOffMarks } from '../api/calendars';
import { useI18n } from '../i18n';
import { CALENDARS_QUERY, HOLIDAYS_QUERY } from './calendarQueries';
import { dayOffReasonsOn } from './daysOff';

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * その日が休みの日なら、数える理由の名前（「・」でつなぐ）。営業日・日付が空なら null。
 * タスクの開始・期限が休みに当たったときの知らせ（止めはしない。2026-10-02 の決定、ADR-0029）。
 */
export const useDayOffReason = (date: string): string | null => {
  const { t } = useI18n();
  const valid = DATE.test(date);
  const { data: marks } = useQuery({
    queryKey: [HOLIDAYS_QUERY, date, date],
    queryFn: () => getDayOffMarks({ from: date, to: date }),
    enabled: valid,
  });
  const { data: calendars } = useQuery({ queryKey: [CALENDARS_QUERY], queryFn: getCalendars });
  if (!valid || !marks) return null;
  return dayOffReasonsOn(date, marks, calendars, t('calendar.weeklyDayOff'));
};
