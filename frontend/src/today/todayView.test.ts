import { describe, expect, it } from 'vitest';
import type { TimeEntry } from '../types';
import { groupSegmentsByDate } from '../calendar/daySegments';
import { fromZonedPoint } from '../calendar/zonedTime';
import { TOKYO, hm, occurrence } from '../calendar/testOccurrences';
import {
  currentAndNext, entryBands, liveActuals, nextFreeStartMinute, occurrenceStartOf, routineTasksOf, taskUrgencyOf,
} from './todayView';

const DAY = '2026-09-10';
const at = (date: string, minute: number): string => new Date(fromZonedPoint(date, minute, TOKYO)).toISOString();

const entry = (id: number, started: string, ended: string | null, taskId: number | null = 1): TimeEntry => ({
  id,
  user_id: 1,
  task_id: taskId,
  task_title: taskId == null ? null : `task ${taskId}`,
  started_at: started,
  ended_at: ended,
  memo: null,
  source: 'timer',
  is_running: ended == null,
  duration_seconds: 0,
  is_long_running: false,
  created_at: null,
  updated_at: null,
});

const colorOf = (taskId: number | null) => (taskId == null ? 'gray' : `c${taskId}`);

describe('打刻の帯', () => {
  it('今日の中の打刻はそのまま、日をまたぐ打刻は今日の分だけにする', () => {
    const bands = entryBands([
      entry(1, at(DAY, hm(10)), at(DAY, hm(11, 30))),
      entry(2, at('2026-09-09', hm(23, 30)), at(DAY, hm(0, 30)), 2),
      entry(3, at(DAY, hm(23)), at('2026-09-11', hm(1)), null),
    ], DAY, TOKYO, Date.parse(at(DAY, hm(12))), colorOf, 'なし');

    expect(bands.map((b) => [b.key, b.startMinute, b.endMinute, b.color, b.running])).toEqual([
      ['entry-1', hm(10), hm(11, 30), 'c1', false],
      ['entry-2', 0, hm(0, 30), 'c2', false],
      ['entry-3', hm(23), 1440, 'gray', false],
    ]);
    expect(bands[2].label).toBe('なし  23:00 – 24:00');
  });

  it('走っている打刻は今まで。始めたばかりでも帯を出す', () => {
    const now = Date.parse(at(DAY, hm(12)));
    const bands = entryBands([
      entry(1, at(DAY, hm(11)), null),
      entry(2, at(DAY, hm(12)), null),
    ], DAY, TOKYO, now, colorOf, 'なし');
    expect(bands.map((b) => [b.startMinute, b.endMinute, b.running])).toEqual([
      [hm(11), hm(12), true],
      [hm(12), hm(12), true],
    ]);
  });

  it('今日に掛からない打刻・長さ 0 の止まった打刻は出さない', () => {
    const bands = entryBands([
      entry(1, at('2026-09-09', hm(10)), at('2026-09-09', hm(11))),
      entry(2, at(DAY, hm(10)), at(DAY, hm(10))),
    ], DAY, TOKYO, Date.parse(at(DAY, hm(12))), colorOf, 'なし');
    expect(bands).toEqual([]);
  });
});

describe('予定のブロックからの Start', () => {
  it('タスクの無い予定には出さない。走っていなければ開始、別のタスクなら切り替え', () => {
    expect(occurrenceStartOf({ task_id: null }, null)).toBeNull();
    expect(occurrenceStartOf({ task_id: 5 }, null)).toBe('start');
    expect(occurrenceStartOf({ task_id: 5 }, { task_id: 6 })).toBe('switch');
    expect(occurrenceStartOf({ task_id: 5 }, { task_id: null })).toBe('switch');
    expect(occurrenceStartOf({ task_id: 5 }, { task_id: 5 })).toBe('running');
  });
});

describe('今日の実績', () => {
  const base = {
    server_now: '2026-09-10T03:00:00Z',
    day_end: '2026-09-10T15:00:00Z',
    total_seconds: 5400,
    actuals: [
      { task_id: 1, task_title: 'a', seconds: 3600 },
      { task_id: 2, task_title: 'b', seconds: 1800 },
    ],
  };

  it('止まっていればそのまま', () => {
    expect(liveActuals({ ...base, running: null }, 0, 600_000)).toEqual({ totalSeconds: 5400, actuals: base.actuals });
  });

  it('受け取ってから走った分を、走っているタスクと合計に足して並べ直す', () => {
    const running = entry(9, '2026-09-10T02:00:00Z', null, 2);
    const live = liveActuals({ ...base, running }, 1_000, 1_000 + 2_000_000);
    expect(live.totalSeconds).toBe(5400 + 2000);
    expect(live.actuals.map((a) => [a.task_id, a.seconds])).toEqual([[2, 3800], [1, 3600]]);
  });

  it('実績にまだ無いタスク（未割当）は行を足す。今日の終わりより先は数えない', () => {
    const running = entry(9, '2026-09-10T02:59:00Z', null, null);
    const live = liveActuals({ ...base, server_now: '2026-09-10T14:59:00Z', running }, 0, 3_600_000);
    expect(live.totalSeconds).toBe(5400 + 60);
    expect(live.actuals[live.actuals.length - 1]).toEqual({ task_id: null, task_title: null, seconds: 60 });
  });
});

describe('いまの予定と次の予定', () => {
  const linked = (id: string, start: number, duration: number, taskId: number | null) => ({
    ...occurrence(id, DAY, start, duration), task_id: taskId,
  });

  it('いま掛かっている予定はタスクのあるものを優先し、次は最も早く始まるもの', () => {
    const segments = groupSegmentsByDate([
      linked('meeting', hm(11), 120, null),
      linked('work', hm(11, 30), 60, 7),
      linked('later', hm(15), 30, 8),
      linked('soon', hm(13), 30, null),
      { ...occurrence('allday', DAY, 0, 1440), task_id: 9 },
    ], TOKYO).get(DAY) ?? [];
    const { current, next } = currentAndNext(segments, hm(12));
    expect(current?.occurrence.id).toBe('work');
    expect(next?.occurrence.id).toBe('soon');
  });

  it('何も無ければ両方 null', () => {
    expect(currentAndNext([], hm(12))).toEqual({ current: null, next: null });
  });
});

describe('今日やるべき理由', () => {
  it('期限で分け、期限が先なら進行中か開始日を過ぎたか', () => {
    expect(taskUrgencyOf({ due_date: '2026-09-09', status: 'TODO' }, DAY)).toBe('overdue');
    expect(taskUrgencyOf({ due_date: DAY, status: 'TODO' }, DAY)).toBe('today');
    expect(taskUrgencyOf({ due_date: '2026-09-11', status: 'TODO' }, DAY)).toBe('tomorrow');
    expect(taskUrgencyOf({ due_date: '2026-09-30', status: 'DOING' }, DAY)).toBe('doing');
    expect(taskUrgencyOf({ due_date: null, status: 'TODO' }, DAY)).toBe('started');
  });
});

describe('「予定を作る」で開く枠（task #185）', () => {
  const segmentsOf = (...list: ReturnType<typeof occurrence>[]) => groupSegmentsByDate(list, TOKYO).get(DAY) ?? [];

  it('予定が無ければ、今の後の最初の 15 分刻み', () => {
    expect(nextFreeStartMinute([], hm(10, 7), 30)).toBe(hm(10, 15));
    expect(nextFreeStartMinute([], hm(10), 30)).toBe(hm(10));
  });

  it('時刻のある予定と重ならない最初の位置へ送る（終日の予定は見ない）', () => {
    const segments = segmentsOf(
      occurrence('a', DAY, hm(10), 60),
      occurrence('b', DAY, hm(11, 15), 30),
      occurrence('allday', DAY, 0, 1440),
    );
    // 10:00〜11:00 が埋まり、11:00〜11:15 は 30 分に足りない → 11:45
    expect(nextFreeStartMinute(segments, hm(10, 5), 30)).toBe(hm(11, 45));
    // 15 分なら 11:00 に入る
    expect(nextFreeStartMinute(segments, hm(10, 5), 15)).toBe(hm(11));
  });

  it('今日の中に空きが無ければ、今の後の刻み（今日の終わりに収める）', () => {
    const segments = segmentsOf(occurrence('evening', DAY, hm(22), 120));
    expect(nextFreeStartMinute(segments, hm(22, 10), 30)).toBe(hm(22, 15));
    expect(nextFreeStartMinute([], hm(23, 50), 30)).toBe(hm(23, 30));
  });
});

describe('今日やること（タスクの分類の回、ADR-0025）', () => {
  it('その日のタスクの分類の回だけを、終日を先に始まりの順で並べる（済みも残す）', () => {
    const list = [
      { ...occurrence('late', '2026-05-04', hm(17), 30), event_type: 'TASK' as const },
      { ...occurrence('meeting', '2026-05-04', hm(10), 60) },
      { ...occurrence('early', '2026-05-04', hm(9), 15), event_type: 'TASK' as const, is_done: true },
      { ...occurrence('allday', '2026-05-04', 0, 1440), event_type: 'TASK' as const },
      { ...occurrence('tomorrow', '2026-05-05', hm(9), 15), event_type: 'TASK' as const },
    ];
    expect(routineTasksOf(list, '2026-05-04').map((o) => [o.id, o.is_done])).toEqual([
      ['allday', false], ['early', true], ['late', false],
    ]);
  });
});
