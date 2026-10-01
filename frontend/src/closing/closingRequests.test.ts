import { describe, expect, it } from 'vitest';
import {
  assignTaskRequest, closePeriodRequest, closingFailureOf, createEntryRequest, deleteEntriesRequests, editEntryRequest,
  fromOccurrenceRequest, mergeEntriesRequest, reopenPeriodRequest, rescheduleEntryRequest, splitEntryRequest,
} from './closingRequests';
import { hm, occurrence } from '../calendar/testOccurrences';

const range = { startMs: Date.parse('2026-09-01T00:07:30Z'), endMs: Date.parse('2026-09-01T01:00:00Z') };

describe('締めの画面の操作 → API の呼び出し', () => {
  it('動かす・伸ばすは始まりと終わりを Z 付きで置き換える', () => {
    expect(rescheduleEntryRequest(5, range)).toEqual({
      method: 'PATCH', url: '/time-entries/5',
      body: { started_at: '2026-09-01T00:07:30.000Z', ended_at: '2026-09-01T01:00:00.000Z' },
    });
    expect(editEntryRequest(5, range, 'メモ').body).toEqual({
      started_at: '2026-09-01T00:07:30.000Z', ended_at: '2026-09-01T01:00:00.000Z', memo: 'メモ',
    });
  });

  it('空き時間に足す・分ける', () => {
    expect(createEntryRequest(range)).toEqual({
      method: 'POST', url: '/time-entries',
      body: { started_at: '2026-09-01T00:07:30.000Z', ended_at: '2026-09-01T01:00:00.000Z', task_id: null },
    });
    expect(splitEntryRequest(5, Date.parse('2026-09-01T00:30:00Z'))).toEqual({
      method: 'POST', url: '/time-entries/5/split', body: { at: '2026-09-01T00:30:00.000Z' },
    });
  });

  it('つなぐは 2 本から、振るは 1 本から（null で未割当へ戻す）', () => {
    expect(mergeEntriesRequest([1])).toBeNull();
    expect(mergeEntriesRequest([3, 1])).toEqual({ method: 'POST', url: '/time-entries/merge', body: { entry_ids: [3, 1] } });
    expect(assignTaskRequest([], 1)).toBeNull();
    expect(assignTaskRequest([1, 2], 7)).toEqual({ method: 'POST', url: '/time-entries/assign', body: { entry_ids: [1, 2], task_id: 7 } });
    expect(assignTaskRequest([1], null)?.body).toEqual({ entry_ids: [1], task_id: null });
  });

  it('消すのは 1 本ずつ', () => {
    expect(deleteEntriesRequests([1, 2])).toEqual([
      { method: 'DELETE', url: '/time-entries/1' },
      { method: 'DELETE', url: '/time-entries/2' },
    ]);
  });

  it('予定どおり: 回は予定の id と回の始まりで指す（タスクは回のもの）', () => {
    const o = { ...occurrence('a', '2026-09-01', hm(9), 60), event_id: 42, task_id: 3 };
    expect(fromOccurrenceRequest(o)).toEqual({
      method: 'POST', url: '/time-entries/from-occurrence', body: { event_id: 42, start: o.start },
    });
  });

  it('確定・開け直しは期間の初日で指す', () => {
    expect(closePeriodRequest('2026-09-16')).toEqual({ method: 'POST', url: '/closing-periods/2026-09-16/close' });
    expect(reopenPeriodRequest('2026-09-16')).toEqual({ method: 'POST', url: '/closing-periods/2026-09-16/reopen' });
  });
});

describe('断られた理由 → 日本語', () => {
  const apiError = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });

  it('未割当で確定できない（打刻を選んで見せる）', () => {
    const failure = closingFailureOf(apiError(409,
      'Time entries without a task overlap this period (ids=4,7); assign a task or delete them'));
    expect(failure).toEqual({ key: 'closing.error.unassigned', params: { count: 2 }, entryIds: [4, 7] });
  });

  it('走っている打刻で確定できない', () => {
    const failure = closingFailureOf(apiError(409, 'A running time entry overlaps this period (id=9); stop it first'));
    expect(failure.key).toBe('closing.error.running');
    expect(failure.entryIds).toEqual([9]);
  });

  it('確定済みの期間・確定・開け直しの食い違い', () => {
    expect(closingFailureOf(apiError(409,
      'The closing period 2026-09-01..2026-09-15 is closed; reopen it to change its time entries')).key)
      .toBe('closing.error.periodClosed');
    expect(closingFailureOf(apiError(409, 'This closing period is already closed')).key).toBe('closing.error.alreadyClosed');
    expect(closingFailureOf(apiError(409, 'This closing period is not closed')).key).toBe('closing.error.notClosed');
  });

  it('打刻の操作の 422', () => {
    expect(closingFailureOf(apiError(422, 'split time must be strictly inside the time entry')).key).toBe('closing.error.splitOutside');
    expect(closingFailureOf(apiError(422, 'a running time entry cannot be merged; stop it first')).key).toBe('closing.error.mergeRunning');
    expect(closingFailureOf(apiError(422, 'ended_at must not be in the future')).key).toBe('closing.error.future');
    expect(closingFailureOf(apiError(422, 'an all-day occurrence cannot be turned into a time entry')).key).toBe('closing.error.allDayOccurrence');
  });

  it('知らない理由はそのまま添える', () => {
    expect(closingFailureOf(apiError(409, 'something else'))).toEqual({
      key: 'closing.error.conflict', params: { count: 0, detail: 'something else' }, entryIds: [],
    });
    expect(closingFailureOf(apiError(422, [{ msg: 'bad' }])).params.detail).toBe('bad');
    expect(closingFailureOf(new Error('network')).key).toBe('closing.error.generic');
  });
});
