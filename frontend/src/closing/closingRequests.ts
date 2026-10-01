// 締めの画面の操作 → API の呼び出し（task #161 / ADR-0016）。
//
// カレンダー（ADR-0013）と同じく、画面の意図を「呼び出しのデータ」に直してから 1 か所
// （`api/closing.ts` の `sendClosingRequest`）で送る。時刻は Z 付きの ISO 8601。

import type { CalendarOccurrence } from '../types';
import type { TranslationKey } from '../i18n/translations';
import { errorDetailOf } from '../calendar/calendarRequests';

export interface ClosingRequest {
  method: 'POST' | 'PATCH' | 'DELETE';
  url: string;
  body?: Record<string, unknown>;
}

/** 打刻の範囲（ミリ秒、半開）。 */
export interface EntryRange {
  startMs: number;
  endMs: number;
}

const iso = (ms: number): string => new Date(ms).toISOString();

/** 動かした・伸ばした（始まりと終わりを置き換える）。 */
export const rescheduleEntryRequest = (entryId: number, range: EntryRange): ClosingRequest => ({
  method: 'PATCH',
  url: `/time-entries/${entryId}`,
  body: { started_at: iso(range.startMs), ended_at: iso(range.endMs) },
});

/** 1 件の修正（時刻とメモ）。送った欄だけが変わる。 */
export const editEntryRequest = (entryId: number, range: EntryRange, memo: string | null): ClosingRequest => ({
  method: 'PATCH',
  url: `/time-entries/${entryId}`,
  body: { started_at: iso(range.startMs), ended_at: iso(range.endMs), memo },
});

/** 空き時間に足す（`source=manual`）。 */
export const createEntryRequest = (range: EntryRange, taskId: number | null = null): ClosingRequest => ({
  method: 'POST',
  url: '/time-entries',
  body: { started_at: iso(range.startMs), ended_at: iso(range.endMs), task_id: taskId },
});

/** その位置で分ける。 */
export const splitEntryRequest = (entryId: number, atMs: number): ClosingRequest => ({
  method: 'POST',
  url: `/time-entries/${entryId}/split`,
  body: { at: iso(atMs) },
});

/** つなぐ（2 本以上。タスクはサーバが早い方から選ぶ）。 */
export const mergeEntriesRequest = (entryIds: readonly number[]): ClosingRequest | null =>
  entryIds.length < 2 ? null : { method: 'POST', url: '/time-entries/merge', body: { entry_ids: [...entryIds] } };

/** まとめてタスクを振る（null で未割当へ戻す）。 */
export const assignTaskRequest = (entryIds: readonly number[], taskId: number | null): ClosingRequest | null =>
  entryIds.length === 0 ? null : { method: 'POST', url: '/time-entries/assign', body: { entry_ids: [...entryIds], task_id: taskId } };

/** 消す（まとめて消す口は無いので 1 本ずつ）。 */
export const deleteEntriesRequests = (entryIds: readonly number[]): ClosingRequest[] =>
  entryIds.map((id) => ({ method: 'DELETE', url: `/time-entries/${id}` }));

/** 予定の回をそのまま打刻にする（「予定どおり」。タスクは回のもの）。 */
export const fromOccurrenceRequest = (occurrence: CalendarOccurrence): ClosingRequest => ({
  method: 'POST',
  url: '/time-entries/from-occurrence',
  body: { event_id: occurrence.event_id, start: occurrence.start },
});

export const closePeriodRequest = (firstDay: string): ClosingRequest => ({
  method: 'POST', url: `/closing-periods/${firstDay}/close`,
});

export const reopenPeriodRequest = (firstDay: string): ClosingRequest => ({
  method: 'POST', url: `/closing-periods/${firstDay}/reopen`,
});

// ── 断られた理由 ────────────────────────────────────────────────────────

export interface ClosingFailure {
  key: TranslationKey;
  params: Record<string, string | number>;
  /** 理由に出てきた打刻（未割当・走っている）。画面で選んで見せる */
  entryIds: number[];
}

const statusOf = (error: unknown): number | undefined =>
  (error as { response?: { status?: number } } | null)?.response?.status;

const idsIn = (detail: string): number[] => {
  const m = /ids?=([\d,]+)/.exec(detail);
  return m ? m[1].split(',').filter(Boolean).map(Number) : [];
};

/**
 * API の誤り（409 / 422 など）→ 日本語の理由。サーバの `detail` は英語の固定文なので、文で見分ける
 * （`src/application/use_cases/closing_use_cases.py`・`time_entry_use_cases.py`）。
 */
export const closingFailureOf = (error: unknown): ClosingFailure => {
  const detail = errorDetailOf(error) ?? '';
  const status = statusOf(error);
  const failure = (key: TranslationKey, entryIds: number[] = [], params: Record<string, string | number> = {}): ClosingFailure =>
    ({ key, params: { count: entryIds.length, ...params }, entryIds });
  if (/without a task/i.test(detail)) return failure('closing.error.unassigned', idsIn(detail));
  if (/running time entry overlaps/i.test(detail)) return failure('closing.error.running', idsIn(detail));
  if (/already closed/i.test(detail)) return failure('closing.error.alreadyClosed');
  if (/is not closed/i.test(detail)) return failure('closing.error.notClosed');
  if (/is closed; reopen/i.test(detail)) return failure('closing.error.periodClosed');
  if (/has not started/i.test(detail)) return failure('closing.error.notStarted');
  if (/all-day occurrence/i.test(detail)) return failure('closing.error.allDayOccurrence');
  if (/must not be in the future/i.test(detail)) return failure('closing.error.future');
  if (/must be after start/i.test(detail)) return failure('closing.error.endBeforeStart');
  if (/strictly inside/i.test(detail)) return failure('closing.error.splitOutside');
  if (/running time entry cannot be merged/i.test(detail)) return failure('closing.error.mergeRunning');
  if (status === 404) return failure('closing.error.notFound');
  if (status === 409) return failure('closing.error.conflict', [], { detail });
  return failure('closing.error.generic', [], { detail });
};
