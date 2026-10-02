// 取り込んだカレンダー（task #196、ADR-0037）の回を、カレンダーと「今日」の画面で予定と同じ形にして重ねる。
// ⚠ 読み取り専用: 動かす・直す・消す・済みは無い（`is_imported` で見分ける。`event_id` は 0）。
// 予定の回の一覧（`/calendar/occurrences`）とは別に引くので、締め・打刻・通知には入らない。

import type { TranslationKey } from '../i18n/translations';
import type { CalendarOccurrence, ImportedOccurrence } from '../types';
import { formatDate } from '../utils/format';

/** 取り込んだ回を、予定の回の形にする。件名が空なら `untitled`。 */
export const importedToOccurrence = (o: ImportedOccurrence, untitled: string): CalendarOccurrence => ({
  id: o.id,
  event_id: 0,
  event_version: 0,
  title: o.title.trim() || untitled,
  start: o.start,
  duration_minutes: o.duration_minutes,
  date: o.date,
  start_time: o.start_time,
  is_all_day: o.is_all_day,
  color_key: 'DEFAULT',
  location: o.location,
  task_id: null,
  is_recurring: false,
  is_moved: false,
  is_overridden: false,
  series_key: null,
  alarm: null,
  event_type: 'EVENT',
  is_done: false,
  calendar_id: o.calendar_id,
  calendar_color_key: o.calendar_color_key,
  is_imported: true,
});

/** 予定の回と取り込んだ回を 1 つにする（どちらかがまだ無くても、あるものだけで描く）。 */
export const withImportedOccurrences = (
  occurrences: readonly CalendarOccurrence[] | undefined,
  imported: readonly ImportedOccurrence[] | undefined,
  untitled: string,
): CalendarOccurrence[] => [
  ...(occurrences ?? []),
  ...(imported ?? []).map((o) => importedToOccurrence(o, untitled)),
];

const FAILURE_KEYS: Record<string, TranslationKey> = {
  invalid_url: 'calendar.importErrorInvalidUrl',
  blocked_address: 'calendar.importErrorBlockedAddress',
  unreachable: 'calendar.importErrorUnreachable',
  not_found: 'calendar.importErrorNotFound',
  forbidden: 'calendar.importErrorForbidden',
  http_error: 'calendar.importErrorHttp',
  too_large: 'calendar.importErrorTooLarge',
  not_icalendar: 'calendar.importErrorNotIcalendar',
  too_many_events: 'calendar.importErrorTooManyEvents',
  subscription_unavailable: 'calendar.importErrorSubscriptionUnavailable',
};

/** 読めなかった理由（422 の `reason`・`last_error`）を言葉のキーにする。知らない理由は null。 */
export const feedFailureKey = (reason: string | null | undefined): TranslationKey | null =>
  (reason ? FAILURE_KEYS[reason] ?? null : null);

/** 422 の応答から読めなかった理由を取り出す（取り込みの口のものでなければ null）。 */
export const feedFailureOf = (error: unknown): string | null => {
  const data = (error as { response?: { data?: { reason?: unknown } } } | null)?.response?.data;
  return typeof data?.reason === 'string' ? data.reason : null;
};

/** 読み込んだ時刻（UTC の ISO）を `10/2 14:05` の形に（端末のタイムゾーン）。読めなければ「—」。 */
export const formatImportedAt = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '—';
  return `${formatDate(at)} ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
};
