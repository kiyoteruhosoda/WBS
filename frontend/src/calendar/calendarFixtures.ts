// 試験で使う API の応答の見本（本番のコードからは使わない）。形は予定 API（ADR-0009）の応答のまま。
import type { CalendarEvent, CalendarOccurrence } from '../types';

export const singleEvent = (patch: Partial<CalendarEvent> = {}): CalendarEvent => ({
  id: 5,
  kind: 'SINGLE',
  title: '設計レビュー',
  time_zone: 'Asia/Tokyo',
  start: '2026-05-04T00:00:00Z', // 東京 9:00
  duration_minutes: 60,
  recurrence: null,
  location: '会議室A',
  description: '資料は前日まで',
  color_key: 'TOMATO',
  task_id: 12,
  alarm: { enabled: true, notify_15_min: true, notify_5_min: false, notify_1_min: false, notify_at_start: true },
  event_type: 'EVENT',
  calendar_id: 1,
  exceptions: [],
  moves: [],
  version: 3,
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-02T00:00:00Z',
  ...patch,
});

/** 毎月第 2 火曜 10:00（東京）・隔月・祝日なら前の営業日・年末まで。先頭は 2026-05-12。 */
export const recurringEvent = (patch: Partial<CalendarEvent> = {}): CalendarEvent => ({
  ...singleEvent(),
  id: 7,
  kind: 'RECURRING',
  title: '定例',
  start: '2026-05-12T01:00:00Z',
  duration_minutes: 30,
  location: null,
  description: null,
  color_key: 'BLUEBERRY',
  task_id: null,
  recurrence: {
    type: 'MONTHLY',
    interval: 2,
    end_date: '2026-12-31',
    weekly: null,
    monthly: { kind: 'NTH_WEEKDAY', week_index: 2, weekday: 'TU' },
    yearly: null,
    adjustment: { condition: 'HOLIDAY', shift_unit: 'BUSINESS_DAY', shift_amount: -1, calendar_id: 3, action: 'SHIFT' },
  },
  version: 4,
  ...patch,
});

/** `GET /calendar/occurrences` の 1 件。 */
export const apiOccurrence = (patch: Partial<CalendarOccurrence> = {}): CalendarOccurrence => ({
  id: '5',
  event_id: 5,
  event_version: 3,
  title: '設計レビュー',
  start: '2026-05-04T00:00:00Z',
  duration_minutes: 60,
  date: '2026-05-04',
  start_time: '09:00',
  is_all_day: false,
  color_key: 'TOMATO',
  location: '会議室A',
  task_id: 12,
  is_recurring: false,
  is_moved: false,
  is_overridden: false,
  series_key: null,
  alarm: null,
  event_type: 'EVENT',
  is_done: false,
  calendar_id: 1,
  calendar_color_key: 'DEFAULT',
  ...patch,
});

/** 繰り返しの予定（`recurringEvent`）の 2026-07-14 の回。 */
export const recurringOccurrence = (patch: Partial<CalendarOccurrence> = {}): CalendarOccurrence => apiOccurrence({
  id: '7:2026-07-14T10:00',
  event_id: 7,
  event_version: 4,
  title: '定例',
  start: '2026-07-14T01:00:00Z',
  duration_minutes: 30,
  date: '2026-07-14',
  start_time: '10:00',
  color_key: 'BLUEBERRY',
  location: null,
  task_id: null,
  is_recurring: true,
  series_key: { date: '2026-07-14', start_time: '10:00' },
  ...patch,
});
