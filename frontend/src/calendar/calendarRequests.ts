// 画面の意図 → 予定 API の呼び出し（task #157 第 2 段、ADR-0010）。
//
// 呼び出しを「何を・どこへ・何を載せて」のデータ（`CalendarRequest`）で作り、送るのは
// `api/calendar.ts` の `sendCalendarRequest` だけにする。ここは純関数なので、意図 → 呼び出しの
// 変換を試験で確かめられる。
//
// 版（`expected_version`）は楽観ロック。画面が知っている版と今の版が違えば 409 で、呼び手は
// 最新を取り直して知らせる。

import type { CalendarEvent, CalendarOccurrence, OccurrenceSeriesKey } from '../types';
import type { OccurrenceReschedule, OccurrenceSchedule } from '../components/calendar/calendarInteractions';
import type { OperationHistory } from './operationHistory';

export interface CalendarRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  url: string;
  body?: unknown;
  params?: Record<string, string | number>;
}

const eventUrl = (eventId: number): string => `/calendar/events/${eventId}`;
const occurrenceUrl = (eventId: number, action: string): string => `${eventUrl(eventId)}/occurrences/${action}`;

/** 回の鍵（API の `occurrence`）。応答の `series_key` をそのまま返す。 */
export const occurrenceKeyOf = (occurrence: CalendarOccurrence): OccurrenceSeriesKey => {
  if (!occurrence.series_key) throw new Error(`occurrence ${occurrence.id} is not part of a series`);
  return { date: occurrence.series_key.date, start_time: occurrence.series_key.start_time };
};

// ── ドラッグ（移動・伸ばし縮め）──────────────────────────────────────────

/**
 * ドラッグの 1 操作の履歴。`version` はこの操作を当てた後の予定の版（戻すときの `expected_version`）。
 * `wasMoved` は動かす前に振替だったか（戻し方が変わる。移植元 `HadMoveBeforeDrag`）。
 */
export interface RescheduleEntry {
  eventId: number;
  scope: OccurrenceReschedule['scope'];
  key: OccurrenceSeriesKey | null;
  wasMoved: boolean;
  before: OccurrenceSchedule;
  after: OccurrenceSchedule;
  version: number;
}

/** 単発の時刻を変える。`PUT /events/{id}` は詳細を置き換えるので、今の詳細をそのまま載せる。 */
export const rescheduleSingleRequest = (
  event: CalendarEvent,
  schedule: Pick<OccurrenceSchedule, 'start' | 'durationMinutes'>,
  expectedVersion: number,
): CalendarRequest => ({
  method: 'PUT',
  url: eventUrl(event.id),
  body: {
    title: event.title,
    location: event.location,
    description: event.description,
    task_id: event.task_id,
    start: schedule.start,
    duration_minutes: schedule.durationMinutes,
    color_key: null,
    expected_version: expectedVersion,
  },
});

/** 繰り返しの回を「この回だけ移動」。題名・場所は系列のまま（null）。 */
export const moveOccurrenceRequest = (
  eventId: number,
  key: OccurrenceSeriesKey,
  schedule: Pick<OccurrenceSchedule, 'start' | 'durationMinutes'>,
  expectedVersion: number,
): CalendarRequest => ({
  method: 'POST',
  url: occurrenceUrl(eventId, 'move'),
  body: {
    occurrence: key,
    start: schedule.start,
    duration_minutes: schedule.durationMinutes,
    title: null,
    location: null,
    expected_version: expectedVersion,
  },
});

/** 回の操作（飛ばす・戻す・移動の取り消し・以降を消す）。 */
export const occurrenceActionRequest = (
  eventId: number,
  action: 'skip' | 'restore' | 'cancel-move' | 'delete-following',
  key: OccurrenceSeriesKey,
  expectedVersion: number,
): CalendarRequest => ({
  method: 'POST',
  url: occurrenceUrl(eventId, action),
  body: { occurrence: key, expected_version: expectedVersion },
});

export const deleteEventRequest = (eventId: number, expectedVersion: number): CalendarRequest => ({
  method: 'DELETE',
  url: eventUrl(eventId),
  params: { expected_version: expectedVersion },
});

export const getEventRequest = (eventId: number): CalendarRequest => ({ method: 'GET', url: eventUrl(eventId) });

/**
 * ドラッグの意図を当てる呼び出し。単発は今の詳細が要るので `event` を渡す（繰り返しの回は要らない）。
 * 版は回の `event_version`（画面が読んだ版）。
 */
export const rescheduleRequest = (change: OccurrenceReschedule, event: CalendarEvent | null): CalendarRequest => {
  const o = change.occurrence;
  if (change.scope === 'occurrence') return moveOccurrenceRequest(o.event_id, occurrenceKeyOf(o), change.after, o.event_version);
  if (!event) throw new Error('the event is needed to reschedule a single event');
  return rescheduleSingleRequest(event, change.after, o.event_version);
};

export const rescheduleEntryOf = (change: OccurrenceReschedule, versionAfter: number): RescheduleEntry => ({
  eventId: change.occurrence.event_id,
  scope: change.scope,
  key: change.scope === 'occurrence' ? occurrenceKeyOf(change.occurrence) : null,
  wasMoved: change.occurrence.is_moved,
  before: change.before,
  after: change.after,
  version: versionAfter,
});

/**
 * 元に戻す呼び出し。繰り返しの回で、動かす前は振替でなかったなら、振替を消して系列の位置へ戻す
 * （`before` の時刻へ振り替え直すのではない）。振替だった回は、前の振替先へ動かし直す。
 */
export const undoRequest = (entry: RescheduleEntry, event: CalendarEvent | null): CalendarRequest => {
  if (entry.scope === 'occurrence') {
    if (!entry.key) throw new Error('an occurrence entry needs its series key');
    return entry.wasMoved
      ? moveOccurrenceRequest(entry.eventId, entry.key, entry.before, entry.version)
      : occurrenceActionRequest(entry.eventId, 'cancel-move', entry.key, entry.version);
  }
  if (!event) throw new Error('the event is needed to reschedule a single event');
  return rescheduleSingleRequest(event, entry.before, entry.version);
};

/** やり直す呼び出し（もう一度 `after` へ）。 */
export const redoRequest = (entry: RescheduleEntry, event: CalendarEvent | null): CalendarRequest => {
  if (entry.scope === 'occurrence') {
    if (!entry.key) throw new Error('an occurrence entry needs its series key');
    return moveOccurrenceRequest(entry.eventId, entry.key, entry.after, entry.version);
  }
  if (!event) throw new Error('the event is needed to reschedule a single event');
  return rescheduleSingleRequest(event, entry.after, entry.version);
};

/**
 * 戻した・やり直した後の履歴の版を、その予定の新しい版へ揃える。同じ予定の操作が 2 つ以上
 * 積まれていても、次に送る `expected_version` が今の版になる。
 */
export const withEventVersion = (
  history: OperationHistory<RescheduleEntry>,
  eventId: number,
  version: number,
): OperationHistory<RescheduleEntry> => {
  const bump = (e: RescheduleEntry) => (e.eventId === eventId ? { ...e, version } : e);
  return { past: history.past.map(bump), future: history.future.map(bump) };
};

// ── 画面の先回り（応答を待たずに動かして見せる）────────────────────────────

/** 回の一覧の中の、動かした回を新しい時刻へ置き換える（応答が来たら取り直して上書きされる）。 */
export const applyScheduleToOccurrences = (
  occurrences: readonly CalendarOccurrence[],
  occurrenceId: string,
  schedule: OccurrenceSchedule,
  markMoved: boolean,
): CalendarOccurrence[] =>
  occurrences.map((o) => (o.id !== occurrenceId ? o : {
    ...o,
    start: schedule.start,
    duration_minutes: schedule.durationMinutes,
    date: schedule.date,
    is_all_day: false,
    is_moved: markMoved ? true : o.is_moved,
  }));

// ── 応答の誤り ────────────────────────────────────────────────────────────

/** 版の食い違い（ほかで変わっていた）。axios の誤りの `response.status` を見る。 */
export const isConflictError = (error: unknown): boolean =>
  typeof error === 'object' && error != null
  && (error as { response?: { status?: number } }).response?.status === 409;

/** API の誤りの文言（FastAPI の `detail`）。無ければ null。 */
export const errorDetailOf = (error: unknown): string | null => {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean);
    return messages.length > 0 ? messages.join(' / ') : null;
  }
  return null;
};

/** 書いた後の予定の版を、一覧の同じ予定の回すべてへ写す（取り直す前に続けて動かしても 409 にしない）。 */
export const withOccurrenceEventVersion = (
  occurrences: readonly CalendarOccurrence[],
  eventId: number,
  version: number,
): CalendarOccurrence[] => occurrences.map((o) => (o.event_id === eventId ? { ...o, event_version: version } : o));
