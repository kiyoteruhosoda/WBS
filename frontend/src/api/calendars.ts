import client from './client';
import type { Calendar, CalendarViewPreset, EventColorKey } from '../types';

// 予定のカレンダー・表示の選択・表示の組み合わせ（task #191、ADR-0027）。仕様の正は /api/docs。

export interface CalendarInput {
  name: string;
  color_key: EventColorKey;
}

/** 並び順で。既定のカレンダーが無ければサーバーが作ってから返す。 */
export const getCalendars = async (): Promise<Calendar[]> => {
  const { data } = await client.get('/calendars');
  return data;
};

export const createCalendar = async (input: CalendarInput): Promise<Calendar> => {
  const { data } = await client.post('/calendars', input);
  return data;
};

export const updateCalendar = async (id: number, input: CalendarInput): Promise<Calendar> => {
  const { data } = await client.put(`/calendars/${id}`, input);
  return data;
};

/** 消す。中の予定は既定のカレンダーへ移る（既定は消せない）。 */
export const deleteCalendar = async (id: number): Promise<{ moved_event_count: number }> => {
  const { data } = await client.delete(`/calendars/${id}`);
  return data;
};

/** 表示するカレンダーを、渡したものだけにする（サーバーに覚える）。 */
export const setVisibleCalendars = async (visibleCalendarIds: readonly number[]): Promise<Calendar[]> => {
  const { data } = await client.put('/calendars/visibility', { visible_calendar_ids: visibleCalendarIds });
  return data;
};

export const getCalendarViewPresets = async (): Promise<CalendarViewPreset[]> => {
  const { data } = await client.get('/calendar-view-presets');
  return data;
};

export const createCalendarViewPreset = async (name: string, calendarIds: readonly number[]): Promise<CalendarViewPreset> => {
  const { data } = await client.post('/calendar-view-presets', { name, calendar_ids: calendarIds });
  return data;
};

export const updateCalendarViewPreset = async (
  id: number, name: string, calendarIds: readonly number[],
): Promise<CalendarViewPreset> => {
  const { data } = await client.put(`/calendar-view-presets/${id}`, { name, calendar_ids: calendarIds });
  return data;
};

export const deleteCalendarViewPreset = async (id: number): Promise<void> => {
  await client.delete(`/calendar-view-presets/${id}`);
};

/** 組み合わせを当てる（入っているカレンダーだけが表示になる）。表示の状態の一覧を返す。 */
export const applyCalendarViewPreset = async (id: number): Promise<Calendar[]> => {
  const { data } = await client.post(`/calendar-view-presets/${id}/apply`);
  return data;
};
