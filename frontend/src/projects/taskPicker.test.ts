import { describe, expect, it } from 'vitest';
import type { Project, Task } from '../types';
import {
  buildTaskPicker, flattenPicker, matchesQuery, pickerHead, recentTaskIds, scheduledTaskIds,
} from './taskPicker';
import { entry } from '../closing/testClosingBoard';
import { hm, occurrence } from '../calendar/testOccurrences';

const p = (id: number, name: string, parent: number | null = null, extra: Partial<Project> = {}): Project => ({
  id, name, parent_project_id: parent, color: null, code: null, description: null, status: 'active', sort_order: 0, path: name, ...extra,
});

// 仕事(1) ─ 案件 A(2) ─ 設計(3) / 仕事 ─ 案件 B(4) / 私用(5)
const projects: Project[] = [
  p(1, '仕事'), p(2, '案件 A', 1, { path: '仕事 / 案件 A' }), p(3, '設計', 2, { path: '仕事 / 案件 A / 設計' }),
  p(4, '案件 B', 1, { sort_order: 1, path: '仕事 / 案件 B' }), p(5, '私用', null, { sort_order: 1 }),
];
const pathOf = (projectId: number | null) => projects.find((x) => x.id === projectId)?.path ?? null;

const task = (id: number, title: string, projectId: number | null, overrides: Partial<Task> = {}): Task => ({
  id, user_id: 1, title, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: null,
  estimated_hours: null, remaining_hours: null, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
  rollup_actual_hours: 0, rollup_remaining_hours: null, progress_percent: null, scheduled_hours: null, unscheduled_hours: null,
  priority_score: 0, memo: null, parent_task_id: null, milestone_id: null, project_id: projectId, project_path: pathOf(projectId),
  completed_at: null, deleted_at: null, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...overrides,
});

const tasks: Task[] = [
  task(1, '1 画面の設計', 3),
  task(2, '打合せ', 2),
  task(3, '見積', 4),
  task(4, '買い物', 5),
  task(5, '雑務', null),
  task(6, '2 レビュー', 3),
  task(7, '済んだ', 3, { status: 'DONE' }),
  task(8, 'やめた', null, { status: 'CANCELLED' }),
  task(9, '消した', 2, { deleted_at: '2026-09-01T00:00:00Z' }),
  task(10, '会議', 1),
];

const shape = (model: ReturnType<typeof buildTaskPicker>) => ({
  head: model.head.map((t) => [t.taskId, t.reason]),
  groups: model.groups.map((g) => [g.key, g.inScope, g.tasks.map((t) => t.taskId)]),
});

describe('タスクの選び方を束ねる', () => {
  it('プロジェクトの木の順に道筋の見出しで束ね、未分類は最後。済み・やめた・消したは出さない', () => {
    const model = buildTaskPicker({ tasks, projects });
    expect(shape(model).groups).toEqual([
      ['project:1', true, [10]],
      ['project:2', true, [2]],
      ['project:3', true, [1, 6]],
      ['project:4', true, [3]],
      ['project:5', true, [4]],
      ['none', true, [5]],
    ]);
    expect(model.groups[2].label).toBe('仕事 / 案件 A / 設計');
    expect(model.groups[5].label).toBeNull();
  });

  it('先頭の候補は理由つきで先頭へ、束には重ねて出さない。済んだタスクも先頭なら出し、消したタスクは出さない', () => {
    const model = buildTaskPicker({
      tasks, projects,
      head: [{ taskId: 7, reason: 'schedule' }, { taskId: 9, reason: 'schedule' }, { taskId: 2, reason: 'recent' }, { taskId: 7, reason: 'recent' }],
    });
    expect(shape(model).head).toEqual([[7, 'schedule'], [2, 'recent']]);
    expect(model.head[0].projectPath).toBe('仕事 / 案件 A / 設計');
    expect(model.groups.find((g) => g.key === 'project:2')).toBeUndefined();
  });

  it('範囲を選んでいれば範囲の中（子孫を含む）の束を先に、外は後ろ（隠さない）', () => {
    expect(shape(buildTaskPicker({ tasks, projects, scope: 2 })).groups).toEqual([
      ['project:2', true, [2]],
      ['project:3', true, [1, 6]],
      ['project:1', false, [10]],
      ['project:4', false, [3]],
      ['project:5', false, [4]],
      ['none', false, [5]],
    ]);
    expect(shape(buildTaskPicker({ tasks, projects, scope: 'none' })).groups[0]).toEqual(['none', true, [5]]);
  });

  it('検索はタスク名とプロジェクトの道筋の両方に当てる（語は全部・全角半角と大小を揃える）', () => {
    expect(shape(buildTaskPicker({ tasks, projects, query: '設計' })).groups).toEqual([
      ['project:3', true, [1, 6]],
    ]);
    expect(shape(buildTaskPicker({ tasks, projects, query: '案件ａ　レビュー' })).groups).toEqual([
      ['project:3', true, [6]],
    ]);
    expect(shape(buildTaskPicker({ tasks, projects, query: '案件b' })).groups).toEqual([
      ['project:4', true, [3]],
    ]);
    const none = buildTaskPicker({ tasks, projects, query: '存在しない' });
    expect(none.empty).toBe(true);
    // 先頭の候補も検索で絞る
    expect(buildTaskPicker({ tasks, projects, head: [{ taskId: 4, reason: 'recent' }], query: '設計' }).head).toEqual([]);
  });

  it('いま選んでいるタスクは済んでいても束に残す（フォームの値が読めなくならない）', () => {
    const model = buildTaskPicker({ tasks, projects, keep: 7 });
    expect(model.groups.find((g) => g.key === 'project:3')?.tasks.map((t) => t.taskId)).toEqual([1, 6, 7]);
  });

  it('一覧に無いプロジェクトのタスクも、タスクの持つ道筋で束ねて出す', () => {
    const orphan = task(11, '迷子', 99, { project_path: '消えた枝' });
    const model = buildTaskPicker({ tasks: [orphan], projects });
    expect(model.groups.map((g) => [g.key, g.label])).toEqual([['project:99', '消えた枝']]);
  });

  it('1 列にすると先頭の候補 → 束の順', () => {
    const model = buildTaskPicker({ tasks: tasks.slice(0, 3), projects, head: [{ taskId: 3, reason: 'recent' }] });
    expect(flattenPicker(model).map((o) => [o.groupKey, o.task.taskId])).toEqual([
      ['head', 3], ['project:2', 2], ['project:3', 1],
    ]);
  });

  it('検索語の当て方', () => {
    expect(matchesQuery('画面の設計', '仕事 / 案件 A', '')).toBe(true);
    expect(matchesQuery('画面の設計', '仕事 / 案件 A', '  ')).toBe(true);
    expect(matchesQuery('画面の設計', '仕事 / 案件 A', 'ＡＢ')).toBe(false);
    expect(matchesQuery('Review', null, 'review')).toBe(true);
  });
});

describe('先頭の候補', () => {
  it('同じ時間の予定のタスクは重なりの長い順（終日とタスクの無い回は数えない）', () => {
    const occurrences = [
      { ...occurrence('a', '2026-09-01', hm(9, 30), 60), task_id: 4 },
      { ...occurrence('b', '2026-09-01', hm(9), 60), task_id: 3 },
      { ...occurrence('c', '2026-09-01', 0, 1440), task_id: 5 },
      occurrence('d', '2026-09-01', hm(9), 60),
    ];
    const range = { startMs: Date.parse('2026-09-01T00:00:00Z'), endMs: Date.parse('2026-09-01T01:00:00Z') };
    expect(scheduledTaskIds([range], occurrences)).toEqual([3, 4]);
    // 打刻ボタン: いまの 1 分
    const now = Date.parse('2026-09-01T00:45:00Z');
    expect(scheduledTaskIds([{ startMs: now, endMs: now + 60_000 }], occurrences)).toEqual([3, 4]);
  });

  it('プライベートの予定のタスクは候補にしない（ADR-0033）', () => {
    const occurrences = [
      { ...occurrence('a', '2026-09-01', hm(9), 60), task_id: 4, is_private: true },
      { ...occurrence('b', '2026-09-01', hm(9), 60), task_id: 3 },
    ];
    const range = { startMs: Date.parse('2026-09-01T00:00:00Z'), endMs: Date.parse('2026-09-01T01:00:00Z') };
    expect(scheduledTaskIds([range], occurrences)).toEqual([3]);
  });

  it('直前に使ったタスクは新しい順に重ねず、選んでいる打刻と未割当は数えない', () => {
    const entries = [
      entry(1, '2026-09-01T00:00:00Z', '2026-09-01T01:00:00Z', { task_id: 1 }),
      entry(2, '2026-09-01T01:00:00Z', '2026-09-01T02:00:00Z', { task_id: 2 }),
      entry(3, '2026-09-01T02:00:00Z', '2026-09-01T03:00:00Z', { task_id: 1 }),
      entry(4, '2026-09-01T03:00:00Z', '2026-09-01T04:00:00Z', { task_id: null }),
      entry(5, '2026-09-01T04:00:00Z', '2026-09-01T05:00:00Z', { task_id: 3 }),
      entry(6, '2026-09-01T06:00:00Z', '2026-09-01T07:00:00Z', { task_id: 4 }),
    ];
    const before = Date.parse('2026-09-01T06:00:00Z');
    expect(recentTaskIds(entries, before)).toEqual([3, 1, 2]);
    expect(recentTaskIds(entries, before, { exclude: new Set([5]), limit: 2 })).toEqual([1, 2]);
  });

  it('予定のタスクを先に、直前のタスクは重ねない', () => {
    expect(pickerHead([3, 4], [4, 1])).toEqual([
      { taskId: 3, reason: 'schedule' }, { taskId: 4, reason: 'schedule' }, { taskId: 1, reason: 'recent' },
    ]);
  });
});
