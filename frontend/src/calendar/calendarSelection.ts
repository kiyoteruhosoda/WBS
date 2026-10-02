// 予定のカレンダーの表示の選択（task #191、ADR-0027）。選んだ状態はサーバーに覚える（`is_visible`）。
// ⚠ 出すかどうかだけ。「今日」の画面・締めの予定の列・打刻の既定のタスクは選択に関係なく全部を見る。

import type { Calendar, CalendarOccurrence, CalendarViewPreset } from '../types';

/** 表示にしているカレンダーの id。 */
export const visibleCalendarIds = (calendars: readonly Calendar[]): number[] =>
  calendars.filter((c) => c.is_visible).map((c) => c.id);

/**
 * 表示にしているカレンダーの回だけ。カレンダーの一覧がまだ無い（読み込み中・失敗）ときは全部を出す
 * （何も出ない画面で「予定が消えた」と思わせない）。カレンダーの分からない回も出す。
 */
export const filterVisibleOccurrences = (
  occurrences: readonly CalendarOccurrence[],
  calendars: readonly Calendar[] | undefined,
): readonly CalendarOccurrence[] => {
  if (!calendars || calendars.length === 0) return occurrences;
  const known = new Set(calendars.map((c) => c.id));
  const visible = new Set(visibleCalendarIds(calendars));
  return occurrences.filter((o) => o.calendar_id == null || !known.has(o.calendar_id) || visible.has(o.calendar_id));
};

/** 1 つの表示を切り替えた後の、表示にするカレンダーの id。 */
export const toggledVisibleIds = (calendars: readonly Calendar[], calendarId: number): number[] =>
  calendars
    .filter((c) => (c.id === calendarId ? !c.is_visible : c.is_visible))
    .map((c) => c.id);

/** 表示の選択を手元で先に当てる（応答を待たずに見せる）。 */
export const withVisibleIds = (calendars: readonly Calendar[], visibleIds: readonly number[]): Calendar[] => {
  const visible = new Set(visibleIds);
  return calendars.map((c) => (c.is_visible === visible.has(c.id) ? c : { ...c, is_visible: visible.has(c.id) }));
};

/** 全部が表示か。 */
export const allVisible = (calendars: readonly Calendar[]): boolean => calendars.every((c) => c.is_visible);

/**
 * 新しい予定を入れるカレンダー。既定のカレンダーが表示ならそれ、隠していれば表示の先頭
 * （作った予定が画面から消えないように）。どれも隠していれば既定。一覧が無ければ null（サーバーが既定に入れる）。
 */
export const calendarForNewEvent = (all: readonly Calendar[] | undefined): number | null => {
  // 予定は休みの層（ADR-0029）には入れない
  const calendars = (all ?? []).filter((c) => c.kind === 'EVENTS');
  if (calendars.length === 0) return null;
  const fallback = calendars.find((c) => c.is_default) ?? calendars[0];
  if (fallback.is_visible) return fallback.id;
  return calendars.find((c) => c.is_visible)?.id ?? fallback.id;
};

/** いまの表示が、その組み合わせと同じか（消えたカレンダーは数えない）。 */
export const presetIsActive = (preset: CalendarViewPreset, calendars: readonly Calendar[]): boolean => {
  if (calendars.length === 0) return false;
  const inPreset = new Set(preset.calendar_ids);
  return calendars.every((c) => c.is_visible === inPreset.has(c.id));
};
