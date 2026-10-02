// 試験で使う回の組み立て（本番のコードからは使わない）。
import type { CalendarOccurrence, EventColorKey } from '../types';
import { fromZonedPoint } from './zonedTime';

export const TOKYO = 'Asia/Tokyo';
export const NEW_YORK = 'America/New_York';

export const occurrence = (
  id: string,
  date: string,
  startMinute: number,
  durationMinutes: number,
  timeZone = TOKYO,
  color: EventColorKey = 'DEFAULT',
): CalendarOccurrence => ({
  id,
  event_id: 1,
  event_version: 1,
  title: id,
  start: new Date(fromZonedPoint(date, startMinute, timeZone)).toISOString(),
  duration_minutes: durationMinutes,
  date,
  start_time: `${String(Math.floor(startMinute / 60)).padStart(2, '0')}:${String(startMinute % 60).padStart(2, '0')}`,
  is_all_day: startMinute === 0 && durationMinutes === 1440,
  color_key: color,
  location: null,
  task_id: null,
  is_recurring: false,
  is_moved: false,
  is_overridden: false,
  series_key: null,
  alarm: null,
  event_type: 'EVENT',
  is_done: false,
  calendar_id: 1,
  calendar_color_key: 'DEFAULT',
});

/** 時:分 → 分 */
export const hm = (hour: number, minute = 0): number => hour * 60 + minute;
