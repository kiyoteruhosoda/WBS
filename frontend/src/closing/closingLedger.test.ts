import { describe, expect, it } from 'vitest';
import type { DailyTaskTotal, Project } from '../types';
import { groupEntrySegmentsByDate } from './closingBoard';
import { breaksByDate, buildLedger, formatHalfHours, ledgerCellSegments, ledgerRowOfEntry } from './closingLedger';
import { entry } from './testClosingBoard';
import { TOKYO } from '../calendar/testOccurrences';

const D1 = '2026-09-01';
const D2 = '2026-09-02';
const NOW = Date.parse('2026-09-10T03:00:00Z');

const project = (id: number, name: string, code: string | null, parent: number | null = null): Project => ({
  id, name, parent_project_id: parent, color: null, code, description: null, status: 'active', sort_order: id, path: name, root_project_id: id, my_role: 'manager',
});

const projects = [project(1, 'ProjectA', 'PA-0012'), project(2, 'ProjectA の子', null, 1), project(5, 'ProjectB', 'PB-0204')];

const total = (date: string, taskId: number | null, seconds: number, projectId: number | null, title: string | null = `t${taskId}`): DailyTaskTotal => ({
  work_date: date, task_id: taskId, task_title: taskId == null ? null : title, seconds, project_id: projectId,
});

// 9/1: 9:00–12:00 タスク 10（子のプロジェクト）、13:00–14:30 タスク 20（ProjectB、自動）。9/2: 10:00–10:20 タスク 10
const entries = [
  entry(1, '2026-09-01T00:00:00Z', '2026-09-01T03:00:00Z', { task_id: 10, task_title: 't10' }),
  entry(2, '2026-09-01T04:00:00Z', '2026-09-01T05:30:00Z', { task_id: 20, task_title: 't20', source: 'auto' }),
  entry(3, '2026-09-02T01:00:00Z', '2026-09-02T01:20:00Z', { task_id: 10, task_title: 't10' }),
];
const totals = [total(D1, 10, 3 * 3600, 2), total(D1, 20, 5400, 5), total(D2, 10, 1200, 2)];
const segments = groupEntrySegmentsByDate(entries, TOKYO, NOW, [D1, D2]);

describe('buildLedger', () => {
  const ledger = buildLedger(totals, segments, [D1, D2], projects, 'all');

  it('rolls tasks up into top-level project rows with their codes, in tree order', () => {
    expect(ledger.rows.map((r) => [r.kind, r.projectId, r.code, r.byDate, r.total])).toEqual([
      ['project', 1, 'PA-0012', { [D1]: 10800, [D2]: 1200 }, 12000],
      ['project', 5, 'PB-0204', { [D1]: 5400 }, 5400],
    ]);
    expect(ledger.dayTotals).toEqual({ [D1]: 16200, [D2]: 1200 });
    expect(ledger.grandTotal).toBe(17400);
  });

  it('marks the cells that contain automatic entries', () => {
    expect(ledger.rows.map((r) => [...r.autoDates])).toEqual([[], [D1]]);
  });

  it('takes the start of the first entry and the end of the last one, breaks included', () => {
    expect(ledger.bounds).toEqual({
      [D1]: { startMinute: 9 * 60, endMinute: 14 * 60 + 30 },
      [D2]: { startMinute: 10 * 60, endMinute: 10 * 60 + 20 },
    });
  });

  it('has no bounds on a day without entries', () => {
    expect(buildLedger([], new Map(), [D1], projects, 'all').bounds).toEqual({ [D1]: null });
  });
});

describe('ledgerCellSegments', () => {
  it('lists the entries of that day and that row', () => {
    const rowOf = ledgerRowOfEntry(totals, projects, 'all');
    expect(ledgerCellSegments(segments, D1, 'project:1', rowOf).map((s) => s.entry.id)).toEqual([1]);
    expect(ledgerCellSegments(segments, D1, 'project:5', rowOf).map((s) => s.entry.id)).toEqual([2]);
    expect(ledgerCellSegments(segments, D2, 'project:5', rowOf)).toEqual([]);
  });

  it('puts entries without a task into the unassigned row', () => {
    const rowOf = ledgerRowOfEntry(totals, projects, 'all');
    expect(rowOf(entry(9, '2026-09-01T06:00:00Z', '2026-09-01T07:00:00Z', { task_id: null, task_title: null })).key).toBe('unassigned');
  });
});

describe('formatHalfHours', () => {
  it('rounds to half hours for display', () => {
    expect([0, 900, 2700, 3600 * 6 + 600, 3600 * 7.75].map(formatHalfHours)).toEqual(['0.0', '0.5', '1.0', '6.0', '8.0']);
  });

  it('does not show a short time that rounds to zero as 0.0', () => {
    expect([1, 600, 899].map(formatHalfHours)).toEqual(['<0.5', '<0.5', '<0.5']);
  });
});

describe('breaksByDate', () => {
  it('sums the breaks of each day and keeps their spans in local time', () => {
    const breaks = [
      { id: 2, started_at: '2026-09-01T06:00:00Z', ended_at: '2026-09-01T06:10:00Z', source: 'auto' as const },
      { id: 1, started_at: '2026-09-01T03:00:00Z', ended_at: '2026-09-01T03:45:00Z', source: 'auto' as const },
      { id: 3, started_at: '2026-09-02T14:30:00Z', ended_at: '2026-09-02T15:00:00Z', source: 'auto' as const },
      { id: 4, started_at: '2026-09-20T03:00:00Z', ended_at: '2026-09-20T04:00:00Z', source: 'auto' as const },
    ];
    expect(breaksByDate(breaks, [D1, D2], TOKYO)).toEqual({
      [D1]: { seconds: 55 * 60, spans: [{ startMinute: 12 * 60, endMinute: 12 * 60 + 45 }, { startMinute: 15 * 60, endMinute: 15 * 60 + 10 }] },
      [D2]: { seconds: 30 * 60, spans: [{ startMinute: 23 * 60 + 30, endMinute: 24 * 60 }] },
    });
  });
});
