import client from './client';
import type { CalendarEvent, CalendarOccurrence } from '../types';
import type { CalendarRequest } from '../calendar/calendarRequests';

// 予定 API（task #156、ADR-0009）。仕様の正は /api/docs。

export const getOccurrences = async (range: { from: string; to: string }, timeZone: string): Promise<CalendarOccurrence[]> => {
  const { data } = await client.get('/calendar/occurrences', { params: { from: range.from, to: range.to, time_zone: timeZone } });
  return data;
};

export const getEvent = async (eventId: number): Promise<CalendarEvent> => {
  const { data } = await client.get(`/calendar/events/${eventId}`);
  return data;
};

/**
 * 予定の書き込み（`calendar/calendarRequests.ts` と `calendar/eventForm.ts` が組み立てた呼び出し）を送る。
 * 応答は書いた後の予定（消したときは null）。
 */
export const sendCalendarRequest = async (request: CalendarRequest): Promise<CalendarEvent | null> => {
  const { data, status } = await client.request({
    method: request.method,
    url: request.url,
    data: request.body,
    params: request.params,
  });
  return status === 204 ? null : (data as CalendarEvent);
};

/** 呼び出しを順に送る（消して作り直すときは 2 つ）。最後の応答を返す。 */
export const sendCalendarRequests = async (requests: readonly CalendarRequest[]): Promise<CalendarEvent | null> => {
  let last: CalendarEvent | null = null;
  for (const request of requests) last = await sendCalendarRequest(request);
  return last;
};

/** 予定の通知 1 件（`GET /api/calendar/alarms`。形は ADR-0021 §4） */
export interface CalendarAlarm {
  /** `<event_id>:<starts_at>:<minutes_before>`。鳴らした印の鍵 */
  id: string;
  /** `<event_id>:<starts_at>`。同じ回の 15/5/1/0 分前をまとめる */
  occurrence_id: string;
  event_id: number;
  title: string;
  location: string | null;
  task_id: number | null;
  task_title: string | null;
  starts_at: string;
  duration_minutes: number;
  notify_at: string;
  /** 15 / 5 / 1 / 0（0 は開始時刻） */
  minutes_before: number;
  is_recurring: boolean;
}

/** `from ≤ notify_at < to` の通知（ADR-0021。期間は 7 日まで） */
export const getAlarms = async (range: { from: string; to: string }): Promise<CalendarAlarm[]> => {
  const { data } = await client.get('/calendar/alarms', { params: { from: range.from, to: range.to } });
  return data.alarms;
};

// ── 営業日カレンダー ────────────────────────────────────────────────────────
