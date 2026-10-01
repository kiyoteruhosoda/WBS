import client from './client';
import type { BusinessCalendar, CalendarEvent, CalendarHoliday, CalendarOccurrence, WeekdayCode } from '../types';
import type { CalendarRequest } from '../calendar/calendarRequests';

// 予定 API（task #156、ADR-0009）。仕様の正は /api/docs。

export const getOccurrences = async (range: { from: string; to: string }, timeZone: string): Promise<CalendarOccurrence[]> => {
  const { data } = await client.get('/calendar/occurrences', { params: { from: range.from, to: range.to, time_zone: timeZone } });
  return data;
};

export const getHolidays = async (range: { from: string; to: string }): Promise<CalendarHoliday[]> => {
  const { data } = await client.get('/calendar/holidays', { params: { from: range.from, to: range.to } });
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

// ── 営業日カレンダー ────────────────────────────────────────────────────────

export interface BusinessCalendarInput {
  name: string;
  workdays: WeekdayCode[];
  shift_on_holidays_only: boolean;
  is_enabled: boolean;
}

export const getBusinessCalendars = async (): Promise<BusinessCalendar[]> => {
  const { data } = await client.get('/business-calendars');
  return data;
};

export const createBusinessCalendar = async (input: BusinessCalendarInput): Promise<BusinessCalendar> => {
  const { data } = await client.post('/business-calendars', input);
  return data;
};

export const updateBusinessCalendar = async (id: number, input: BusinessCalendarInput): Promise<BusinessCalendar> => {
  const { data } = await client.put(`/business-calendars/${id}`, input);
  return data;
};

export const deleteBusinessCalendar = async (id: number): Promise<void> => {
  await client.delete(`/business-calendars/${id}`);
};

export const addHoliday = async (id: number, holiday: CalendarHoliday): Promise<BusinessCalendar> => {
  const { data } = await client.post(`/business-calendars/${id}/holidays`, holiday);
  return data;
};

export const removeHoliday = async (id: number, date: string): Promise<BusinessCalendar> => {
  const { data } = await client.delete(`/business-calendars/${id}/holidays/${date}`);
  return data;
};

/** その年の日本の祝日・振替休日・国民の休日を足す（2007〜2099 年）。 */
export const importJapaneseHolidays = async (id: number, year: number): Promise<BusinessCalendar> => {
  const { data } = await client.post(`/business-calendars/${id}/holidays/japan`, { year });
  return data;
};
