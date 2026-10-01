import { describe, expect, it } from 'vitest';
import type { OccurrenceReschedule } from '../components/calendar/calendarInteractions';
import {
  applyScheduleToOccurrences, errorDetailOf, isConflictError, redoRequest, rescheduleEntryOf, rescheduleRequest,
  undoRequest, withEventVersion, withOccurrenceEventVersion,
} from './calendarRequests';
import { recordOperation, emptyHistory, undoOperation } from './operationHistory';
import type { RescheduleEntry } from './calendarRequests';
import { apiOccurrence, recurringOccurrence, singleEvent } from './calendarFixtures';

// 週表示のドラッグの意図 → 予定 API の呼び出し（task #157 第 2 段）。

const singleMove: OccurrenceReschedule = {
  kind: 'move',
  occurrence: apiOccurrence(),
  scope: 'event',
  before: { date: '2026-05-04', startMinute: 540, durationMinutes: 60, start: '2026-05-04T00:00:00.000Z' },
  after: { date: '2026-05-05', startMinute: 600, durationMinutes: 60, start: '2026-05-05T01:00:00.000Z' },
};

const occurrenceMove: OccurrenceReschedule = {
  kind: 'resize',
  occurrence: recurringOccurrence(),
  scope: 'occurrence',
  before: { date: '2026-07-14', startMinute: 600, durationMinutes: 30, start: '2026-07-14T01:00:00.000Z' },
  after: { date: '2026-07-14', startMinute: 600, durationMinutes: 45, start: '2026-07-14T01:00:00.000Z' },
};

describe('ドラッグ → API', () => {
  it('単発は PUT /events/{id} で、今の詳細をそのまま載せて時刻だけ変える（版は回の event_version）', () => {
    expect(rescheduleRequest(singleMove, singleEvent())).toEqual({
      method: 'PUT',
      url: '/calendar/events/5',
      body: {
        title: '設計レビュー',
        location: '会議室A',
        description: '資料は前日まで',
        task_id: 12,
        start: '2026-05-05T01:00:00.000Z',
        duration_minutes: 60,
        color_key: null,
        expected_version: 3,
      },
    });
  });

  it('繰り返しの回は「この回だけ移動」（series_key を返し、題名・場所は系列のまま）', () => {
    expect(rescheduleRequest(occurrenceMove, null)).toEqual({
      method: 'POST',
      url: '/calendar/events/7/occurrences/move',
      body: {
        occurrence: { date: '2026-07-14', start_time: '10:00' },
        start: '2026-07-14T01:00:00.000Z',
        duration_minutes: 45,
        title: null,
        location: null,
        expected_version: 4,
      },
    });
  });

  it('単発を動かすのに予定の中身が無ければ組み立てない', () => {
    expect(() => rescheduleRequest(singleMove, null)).toThrow();
  });
});

describe('元に戻す・やり直す → API', () => {
  it('振替でなかった回を戻すときは振替を消す（cancel-move。before へ振り替え直さない）', () => {
    const entry = rescheduleEntryOf(occurrenceMove, 5);
    expect(entry).toMatchObject({ eventId: 7, wasMoved: false, version: 5, key: { date: '2026-07-14', start_time: '10:00' } });
    expect(undoRequest(entry, null)).toEqual({
      method: 'POST',
      url: '/calendar/events/7/occurrences/cancel-move',
      body: { occurrence: { date: '2026-07-14', start_time: '10:00' }, expected_version: 5 },
    });
  });

  it('動かす前から振替だった回は、前の振替先へ動かし直す', () => {
    const moved = { ...occurrenceMove, occurrence: recurringOccurrence({ is_moved: true }) };
    const entry = rescheduleEntryOf(moved, 6);
    expect(undoRequest(entry, null)).toMatchObject({
      method: 'POST',
      url: '/calendar/events/7/occurrences/move',
      body: { start: '2026-07-14T01:00:00.000Z', duration_minutes: 30, expected_version: 6 },
    });
  });

  it('やり直しはもう一度 after へ', () => {
    const entry = rescheduleEntryOf(occurrenceMove, 5);
    expect(redoRequest(entry, null)).toMatchObject({
      url: '/calendar/events/7/occurrences/move',
      body: { duration_minutes: 45, expected_version: 5 },
    });
  });

  it('単発は before / after の時刻で PUT し直す（版は当てた後の版）', () => {
    const entry = rescheduleEntryOf(singleMove, 4);
    const event = singleEvent({ version: 4 });
    expect(undoRequest(entry, event)).toMatchObject({
      method: 'PUT', url: '/calendar/events/5', body: { start: '2026-05-04T00:00:00.000Z', duration_minutes: 60, expected_version: 4 },
    });
    expect(redoRequest(entry, event)).toMatchObject({ body: { start: '2026-05-05T01:00:00.000Z', expected_version: 4 } });
  });

  it('戻した後の版を、同じ予定の履歴すべてへ写す（続けて戻しても 409 にならない）', () => {
    let history = emptyHistory<RescheduleEntry>();
    history = recordOperation(history, rescheduleEntryOf(occurrenceMove, 5));
    history = recordOperation(history, rescheduleEntryOf(occurrenceMove, 6));
    history = recordOperation(history, rescheduleEntryOf(singleMove, 4));
    const step = undoOperation(withEventVersion(history, 7, 6));
    if (!step) throw new Error('nothing to undo');
    const after = withEventVersion(step.history, 7, 9);
    expect(after.past.map((e) => e.version)).toEqual([9, 9]);
    expect(after.future.map((e) => [e.eventId, e.version])).toEqual([[5, 4]]);
  });
});

describe('画面の先回り', () => {
  it('動かした回だけを新しい時刻にし、繰り返しの回は振替の印を付ける', () => {
    const list = [apiOccurrence(), recurringOccurrence()];
    const next = applyScheduleToOccurrences(list, '7:2026-07-14T10:00', occurrenceMove.after, true);
    expect(next[0]).toBe(list[0]);
    expect(next[1]).toMatchObject({ duration_minutes: 45, is_moved: true, date: '2026-07-14' });
  });

  it('書いた後の版を同じ予定の回すべてへ写す', () => {
    const list = [recurringOccurrence(), recurringOccurrence({ id: '7:2026-09-08T10:00' }), apiOccurrence()];
    expect(withOccurrenceEventVersion(list, 7, 8).map((o) => o.event_version)).toEqual([8, 8, 3]);
  });
});

describe('応答の誤り', () => {
  it('409 を版の食い違いとして見分ける', () => {
    expect(isConflictError({ response: { status: 409 } })).toBe(true);
    expect(isConflictError({ response: { status: 422 } })).toBe(false);
    expect(isConflictError(new Error('network'))).toBe(false);
    expect(isConflictError(null)).toBe(false);
  });

  it('FastAPI の detail を文言にする（文字列・検証の誤りの並び）', () => {
    expect(errorDetailOf({ response: { data: { detail: 'event not found' } } })).toBe('event not found');
    expect(errorDetailOf({ response: { data: { detail: [{ msg: 'a' }, { msg: 'b' }] } } })).toBe('a / b');
    expect(errorDetailOf(new Error('x'))).toBeNull();
  });
});
