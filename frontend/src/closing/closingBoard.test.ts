import { describe, expect, it } from 'vitest';
import type { Task } from '../types';
import {
  assignCandidates, buildFindingItems, buildTotalsTable, canTurnIntoEntry, entriesOverlappingOccurrence, entryMarksOf,
  formatEntryRange, formatExactDuration, formatQuarterHours, groupEntrySegmentsByDate, splitEntryIntoDaySegments,
} from './closingBoard';
import type { EntrySegment } from './closingBoard';
import { layoutTimedSegments } from '../calendar/weekLayout';
import { TOKYO, hm, occurrence } from '../calendar/testOccurrences';
import { board, entry } from './testClosingBoard';

const ms = (iso: string) => Date.parse(iso);
const NOW = ms('2026-09-10T03:00:00Z');

describe('打刻 → 日ごとの区間', () => {
  it('秒は小数の分のまま', () => {
    const [s] = splitEntryIntoDaySegments(entry(1, '2026-09-01T00:07:30Z', '2026-09-01T01:00:00Z'), TOKYO, NOW);
    expect(s).toMatchObject({ date: '2026-09-01', startMinute: 547.5, endMinute: 600, isAllDay: false });
  });

  it('日をまたぐ打刻は利用者の 0:00 で割る', () => {
    const segments = splitEntryIntoDaySegments(entry(1, '2026-09-01T14:00:00Z', '2026-09-01T16:30:00Z'), TOKYO, NOW);
    expect(segments.map((s) => [s.date, s.startMinute, s.endMinute, s.continuesFromPreviousDay, s.continuesToNextDay])).toEqual([
      ['2026-09-01', hm(23), 1440, false, true],
      ['2026-09-02', 0, 90, true, false],
    ]);
  });

  it('ちょうど 0:00 に終わる打刻は翌日に区間を作らない', () => {
    const segments = splitEntryIntoDaySegments(entry(1, '2026-09-01T13:00:00Z', '2026-09-01T15:00:00Z'), TOKYO, NOW);
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ startMinute: hm(22), endMinute: 1440, continuesToNextDay: false });
  });

  it('走っている打刻は今まで', () => {
    const now = ms('2026-09-01T02:30:00Z');
    const [s] = splitEntryIntoDaySegments(entry(1, '2026-09-01T00:00:00Z', null), TOKYO, now);
    expect([s.startMinute, s.endMinute]).toEqual([hm(9), hm(11, 30)]);
  });

  it('期間の外の日の区間は出さない', () => {
    const byDate = groupEntrySegmentsByDate(
      [entry(1, '2026-09-01T14:00:00Z', '2026-09-01T16:30:00Z')], TOKYO, NOW, ['2026-09-01'],
    );
    expect([...byDate.keys()]).toEqual(['2026-09-01']);
    expect(byDate.get('2026-09-01')).toHaveLength(1);
  });

  it('週表示の配置にそのまま渡せる（重なる打刻は列に分ける）', () => {
    const byDate = groupEntrySegmentsByDate([
      entry(1, '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z'),
      entry(2, '2026-09-01T00:30:00Z', '2026-09-01T01:30:00Z'),
    ], TOKYO, NOW, ['2026-09-01']);
    const blocks = layoutTimedSegments<EntrySegment>(byDate.get('2026-09-01') ?? []);
    expect(blocks.map((b) => [b.segment.entry.id, b.top, b.height, b.column, b.groupColumns])).toEqual([
      [1, hm(9), 60, 0, 2],
      [2, hm(9, 30), 60, 1, 2],
    ]);
  });

  it('範囲の表示（秒は切り捨て・日をまたげば日数）', () => {
    expect(formatEntryRange({ startMs: ms('2026-09-01T00:07:30Z'), endMs: ms('2026-09-01T01:00:00Z') }, TOKYO)).toBe('09:07 – 10:00');
    expect(formatEntryRange({ startMs: ms('2026-09-01T14:00:00Z'), endMs: ms('2026-09-01T16:30:00Z') }, TOKYO)).toBe('23:00 – 01:30 (+1)');
    expect(formatEntryRange({ startMs: ms('2026-09-01T13:00:00Z'), endMs: ms('2026-09-01T15:00:00Z') }, TOKYO)).toBe('22:00 – 24:00');
  });
});

describe('予定の回 → 打刻（「予定どおり」）', () => {
  it('終わった時刻付きの回だけ打刻にできる', () => {
    expect(canTurnIntoEntry(occurrence('a', '2026-09-01', hm(9), 60), NOW)).toBe(true);
    expect(canTurnIntoEntry(occurrence('b', '2026-09-10', hm(11, 30), 60), NOW)).toBe(false);
    expect(canTurnIntoEntry(occurrence('c', '2026-09-01', 0, 1440), NOW)).toBe(false);
  });

  it('回の時間に掛かる打刻（接しているだけは数えない）を警告に出す', () => {
    const o = occurrence('a', '2026-09-01', hm(9), 60);
    const touching = entry(1, '2026-08-31T23:00:00Z', '2026-09-01T00:00:00Z');
    const inside = entry(2, '2026-09-01T00:30:00Z', '2026-09-01T02:00:00Z');
    expect(entriesOverlappingOccurrence(o, [touching, inside], NOW).map((e) => e.id)).toEqual([2]);
  });
});

describe('気付かせる物', () => {
  const missed = occurrence('m', '2026-09-02', hm(14), 30);
  const b = board({
    entries: [
      entry(1, '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z'),
      entry(2, '2026-09-01T00:30:00Z', '2026-09-01T02:00:00Z', { task_id: null, task_title: null }),
      entry(3, '2026-08-31T15:00:00Z', '2026-09-01T05:00:00Z', { is_long_running: true }),
    ],
    findings: {
      long_running_entry_ids: [3],
      overlaps: [{ entry_ids: [1, 2], seconds: 1800 }],
      unassigned_entry_ids: [2],
      missed_occurrences: [missed],
      count: 4,
    },
  });

  it('未割当（確定を止める物）を先に、種類ごとに並べる', () => {
    const items = buildFindingItems(b, NOW);
    expect(items.map((i) => i.kind)).toEqual(['unassigned', 'longRunning', 'overlap', 'missed']);
    expect(items[0]).toMatchObject({ entryIds: [2], title: null });
    expect(items[2]).toMatchObject({ entryIds: [1, 2], overlapSeconds: 1800, startMs: ms('2026-09-01T00:30:00Z') });
    expect(items[3]).toMatchObject({ entryIds: [], occurrence: missed, title: 'm' });
  });

  it('打刻ごとの印', () => {
    const marks = entryMarksOf(b);
    expect([...marks.unassigned]).toEqual([2]);
    expect([...marks.longRunning]).toEqual([3]);
    expect([...marks.overlapping].sort()).toEqual([1, 2]);
  });
});

describe('日ごと・タスクごとの合計', () => {
  it('行はタスク（合計の多い順・未割当は最後）、列は日', () => {
    const table = buildTotalsTable([
      { work_date: '2026-09-01', task_id: 1, task_title: 'A', seconds: 3600 },
      { work_date: '2026-09-01', task_id: null, task_title: null, seconds: 900 },
      { work_date: '2026-09-02', task_id: 2, task_title: 'B', seconds: 7200 },
      { work_date: '2026-09-02', task_id: 1, task_title: 'A', seconds: 1800 },
    ], ['2026-09-01', '2026-09-02']);
    expect(table.rows.map((r) => [r.taskId, r.total])).toEqual([[2, 7200], [1, 5400], [null, 900]]);
    expect(table.rows[1].byDate).toEqual({ '2026-09-01': 3600, '2026-09-02': 1800 });
    expect(table.dayTotals).toEqual({ '2026-09-01': 4500, '2026-09-02': 9000 });
    expect(table.grandTotal).toBe(13500);
  });

  it('表示は 15 分単位、正確な長さは秒まで', () => {
    expect(formatQuarterHours(0)).toBe('');
    expect(formatQuarterHours(3600)).toBe('1:00');
    expect(formatQuarterHours(1000)).toBe('0:15');
    expect(formatQuarterHours(5800)).toBe('1:30');
    expect(formatExactDuration(3725)).toBe('1:02:05');
  });
});

describe('タスクを振る候補', () => {
  const task = (id: number, title: string, overrides: Partial<Task> = {}): Task => ({
    id, user_id: 1, title, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: null,
    estimated_hours: null, remaining_hours: null, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
    rollup_actual_hours: 0, rollup_remaining_hours: null, progress_percent: null, scheduled_hours: null, unscheduled_hours: null,
    priority_score: 0, memo: null, parent_task_id: null, milestone_id: null, completed_at: null, deleted_at: null,
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...overrides,
  });

  it('同じ時間の予定のタスクを重なりの長い順に先頭へ、あとは未完了のタスクを題名の順', () => {
    const tasks = [
      task(1, 'B の作業'), task(2, 'A の作業'), task(3, '済み', { status: 'DONE' }), task(4, '予定のタスク'),
      task(5, '消した', { deleted_at: '2026-09-01T00:00:00Z' }),
    ];
    const occurrences = [
      { ...occurrence('o1', '2026-09-01', hm(9, 30), 60), task_id: 4 },
      { ...occurrence('o2', '2026-09-01', hm(9), 60), task_id: 3 },
      { ...occurrence('o3', '2026-09-01', hm(15), 60), task_id: 1 },
      { ...occurrence('o4', '2026-09-01', hm(9), 60), task_id: 5 },
    ];
    const selected = [entry(10, '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z', { task_id: null })];
    expect(assignCandidates(selected, occurrences, tasks, NOW).map((c) => [c.taskId, c.fromSchedule])).toEqual([
      [3, true], [4, true], [2, false], [1, false],
    ]);
  });
});
