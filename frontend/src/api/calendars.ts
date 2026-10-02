import client from './client';
import type {
  Calendar, CalendarImportSettings, CalendarImportStatus, CalendarScope, CalendarViewPreset, DayOffMark, EventColorKey,
  FeedSourceInput, ImportedOccurrence, LayerDayOff, WeekdayCode,
} from '../types';

// 予定のカレンダー・表示の選択・表示の組み合わせ（task #191、ADR-0027）。仕様の正は /api/docs。

export interface CalendarInput {
  name: string;
  color_key: EventColorKey;
  /** 休みの日の一覧の層: 休みとして数える（省けば今のまま） */
  counts_as_day_off?: boolean;
  /** 営業日の層: 稼働する曜日（省けば今のまま） */
  workdays?: WeekdayCode[];
  /** 予定のカレンダー: 仕事 / プライベート（省けば作るときは仕事、直すときは今のまま。ADR-0033） */
  scope?: CalendarScope;
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

// ── 取り込んだカレンダー（ADR-0037）──────────────────────────────────────────

export const getCalendarImportSettings = async (): Promise<CalendarImportSettings> => {
  const { data } = await client.get('/calendars/import-settings');
  return data;
};

/** ファイルか URL を読んで作る。読めなければ 422（`reason`）で、何も作られない。 */
export const createImportedCalendar = async (
  input: { name: string; color_key: EventColorKey; source: FeedSourceInput },
): Promise<Calendar> => {
  const { data } = await client.post('/calendars/imported', input);
  return data;
};

/** 新しいファイル・URL で入れ替える（購読はこの入れ方のものに置き換わる）。 */
export const reimportCalendar = async (id: number, source: FeedSourceInput): Promise<CalendarImportStatus> => {
  const { data } = await client.post(`/calendars/${id}/import`, source);
  return data;
};

/** 購読している URL を今すぐ読み込み直す。 */
export const refreshImportedCalendar = async (id: number): Promise<CalendarImportStatus> => {
  const { data } = await client.post(`/calendars/${id}/refresh`);
  return data;
};

/** 購読をやめる（URL を忘れる。読み込んだ予定は残る）。 */
export const unsubscribeImportedCalendar = async (id: number): Promise<CalendarImportStatus> => {
  const { data } = await client.delete(`/calendars/${id}/subscription`);
  return data;
};

/** 期間の取り込んだ回（表示の選択に関係なく全部）。 */
export const getImportedOccurrences = async (
  range: { from: string; to: string }, timeZone: string,
): Promise<ImportedOccurrence[]> => {
  const { data } = await client.get('/calendars/imported-occurrences', {
    params: { from: range.from, to: range.to, time_zone: timeZone },
  });
  return data;
};

// ── 休みの層（ADR-0029）──────────────────────────────────────────────────────

/** 期間の休みの理由（曜日の休み・層の日）。表示の選択に関係なく全部。 */
export const getDayOffMarks = async (range: { from: string; to: string }): Promise<DayOffMark[]> => {
  const { data } = await client.get('/calendars/days-off', { params: { from: range.from, to: range.to } });
  return data;
};

export const getLayerDays = async (id: number, range?: { from: string; to: string }): Promise<LayerDayOff[]> => {
  const { data } = await client.get(`/calendars/${id}/days-off`, { params: range });
  return data;
};

/** 1 日足す。その年の日を返す。 */
export const addLayerDay = async (id: number, day: LayerDayOff): Promise<LayerDayOff[]> => {
  const { data } = await client.post(`/calendars/${id}/days-off`, day);
  return data;
};

export const removeLayerDay = async (id: number, date: string): Promise<LayerDayOff[]> => {
  const { data } = await client.delete(`/calendars/${id}/days-off/${date}`);
  return data;
};

/** その年の日本の祝日・振替休日・国民の休日を足す（2007〜2099 年）。 */
export const importLayerJapaneseHolidays = async (id: number, year: number): Promise<LayerDayOff[]> => {
  const { data } = await client.post(`/calendars/${id}/days-off/japan`, { year });
  return data;
};
