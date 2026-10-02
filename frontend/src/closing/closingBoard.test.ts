import { describe, expect, it } from 'vitest';
import {
  assignHead, buildFindingItems, buildProjectTotalsTable, buildTotalsTable, canTurnIntoEntry, entriesOverlappingOccurrence, entryMarksOf,
  formatEntryRange, formatQuarterHours, groupEntrySegmentsByDate, splitEntryIntoDaySegments,
} from './closingBoard';
import type { EntrySegment } from './closingBoard';
import type { Project } from '../types';
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
  });
});

describe('タスクを振る先頭の候補', () => {
  it('同じ時間の予定のタスクを重なりの長い順に、そのあと直前の打刻のタスクを新しい順に', () => {
    const occurrences = [
      { ...occurrence('o1', '2026-09-01', hm(9, 30), 60), task_id: 4 },
      { ...occurrence('o2', '2026-09-01', hm(9), 60), task_id: 3 },
      { ...occurrence('o3', '2026-09-01', hm(15), 60), task_id: 1 },
      { ...occurrence('o4', '2026-09-01', 0, 1440), task_id: 6 },
    ];
    const selected = [entry(10, '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z', { task_id: null })];
    const entries = [
      entry(7, '2026-08-31T22:00:00Z', '2026-08-31T23:00:00Z', { task_id: 8 }),
      entry(8, '2026-08-31T23:00:00Z', '2026-08-31T23:30:00Z', { task_id: 3 }),
      entry(9, '2026-08-31T23:30:00Z', '2026-09-01T00:00:00Z', { task_id: null }),
      selected[0],
      entry(11, '2026-09-01T02:00:00Z', '2026-09-01T03:00:00Z', { task_id: 9 }),
    ];
    expect(assignHead(selected, occurrences, entries, NOW)).toEqual([
      { taskId: 3, reason: 'schedule' }, { taskId: 4, reason: 'schedule' }, { taskId: 8, reason: 'recent' },
    ]);
  });

  it('何も選んでいなければ空', () => {
    expect(assignHead([], [], [], NOW)).toEqual([]);
  });
});

describe('日ごと・プロジェクトごとの合計', () => {
  const p = (id: number, name: string, parent: number | null = null, extra: Partial<Project> = {}): Project => ({
    id, name, parent_project_id: parent, color: null, description: null, status: 'active', sort_order: 0, path: name, ...extra,
  });
  // 仕事(1) ─ 案件 A(2) ─ 設計(3) / 仕事 ─ 案件 B(4) / 私用(5)
  const projects = [
    p(1, '仕事'), p(2, '案件 A', 1), p(3, '設計', 2), p(4, '案件 B', 1, { sort_order: 1 }), p(5, '私用', null, { sort_order: 1, color: '#123456' }),
  ];
  const D1 = '2026-09-01';
  const D2 = '2026-09-02';
  const totals = [
    { work_date: D1, task_id: 1, task_title: '設計書', seconds: 3600, project_id: 3 },
    { work_date: D1, task_id: 2, task_title: '打合せ', seconds: 1800, project_id: 2 },
    { work_date: D2, task_id: 3, task_title: '見積', seconds: 900, project_id: 4 },
    { work_date: D2, task_id: 4, task_title: '会議', seconds: 600, project_id: 1 },
    { work_date: D1, task_id: 5, task_title: '買い物', seconds: 1200, project_id: 5 },
    { work_date: D2, task_id: 6, task_title: '雑務', seconds: 300, project_id: null },
    { work_date: D2, task_id: null, task_title: null, seconds: 450, project_id: null },
    { work_date: D1, task_id: 7, task_title: null, seconds: 60, project_id: null },
  ];
  const rows = (scope: Parameters<typeof buildProjectTotalsTable>[3]) =>
    buildProjectTotalsTable(totals, [D1, D2], projects, scope).rows.map((r) => [r.kind, r.projectId, r.total]);

  it('全部なら最上位のプロジェクトへ子孫の分まで積み、未分類・未割当を後ろに（木の順）', () => {
    expect(rows('all')).toEqual([
      ['project', 1, 3600 + 1800 + 900 + 600], ['project', 5, 1200], ['unclassified', null, 300], ['unassigned', null, 510],
    ]);
    const table = buildProjectTotalsTable(totals, [D1, D2], projects, 'all');
    expect(table.rows[0].byDate).toEqual({ [D1]: 5400, [D2]: 1500 });
    expect(table.rows[1]).toMatchObject({ title: '私用', color: '#123456' });
    // 日の合計はタスクの表と同じ（範囲で崩さない）
    expect(table.grandTotal).toBe(buildTotalsTable(totals, [D1, D2]).grandTotal);
  });

  it('プロジェクトを選べば、直に付いた分と直下の子ごと（孫も積む）、範囲の外は 1 行', () => {
    expect(rows(1)).toEqual([
      ['direct', 1, 600], ['project', 2, 5400], ['project', 4, 900], ['outside', null, 1500], ['unassigned', null, 510],
    ]);
    expect(rows(2)).toEqual([
      ['direct', 2, 1800], ['project', 3, 3600], ['outside', null, 1200 + 300 + 900 + 600], ['unassigned', null, 510],
    ]);
  });

  it('未分類を選べば、未分類と範囲の外', () => {
    expect(rows('none')).toEqual([
      ['unclassified', null, 300], ['outside', null, 3600 + 1800 + 900 + 600 + 1200], ['unassigned', null, 510],
    ]);
  });
});
