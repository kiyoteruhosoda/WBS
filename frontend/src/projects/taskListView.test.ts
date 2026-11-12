import { describe, expect, it } from 'vitest';
import type { Project, Task } from '../types';
import {
  followingIds, groupRows, groupTaskIds, groupTasksByProject, moveToProjectRequest, nestBySubtask, planProjectMove, sortTasks,
} from './taskListView';

const p = (id: number, name: string, parent: number | null = null, extra: Partial<Project> = {}): Project => ({
  id, name, parent_project_id: parent, color: null, code: null, description: null, status: 'active', sort_order: 0, path: name, root_project_id: id, my_role: 'manager', ...extra,
});

// Tree: 仕事(1) ─ 案件 A(2) ─ 設計(3) / 仕事 ─ 案件 B(4) / 私用(5)
const projects: Project[] = [
  p(1, '仕事'), p(2, '案件 A', 1, { path: '仕事 / 案件 A' }), p(3, '設計', 2, { path: '仕事 / 案件 A / 設計' }),
  p(4, '案件 B', 1, { sort_order: 1, path: '仕事 / 案件 B' }), p(5, '私用', null, { sort_order: 1 }),
];
const pathOf = (projectId: number | null) => projects.find((x) => x.id === projectId)?.path ?? null;

const task = (id: number, title: string, projectId: number | null, overrides: Partial<Task> = {}): Task => ({
  id, user_id: 1, title, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: null,
  estimated_hours: null, remaining_hours: null, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
  rollup_actual_hours: 0, rollup_remaining_hours: null, progress_percent: null,
  priority_score: 0, memo: null, parent_task_id: null, milestone_id: null, project_id: projectId, project_path: pathOf(projectId),
  completed_at: null, deleted_at: null, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...overrides,
});

const tasks: Task[] = [
  task(1, '画面の設計', 3, { remaining_hours: 2 }),
  task(2, '打合せ', 2, { remaining_hours: 1.5 }),
  task(3, 'a 見積', 4, { remaining_hours: 0.1 }),
  task(4, 'b 済んだもの', 4, { status: 'DONE', remaining_hours: 5 }),
  task(5, '買い物', 5, { remaining_hours: null }),
  task(6, 'メモの整理', null, { remaining_hours: 0.2 }),
];

describe('grouping by project', () => {
  it('puts tasks under tree headings, nests children, rolls up count and remaining over descendants, and puts unassigned last', () => {
    const groups = groupTasksByProject(tasks, projects);

    expect(groups.map((g) => g.key)).toEqual(['project:1', 'project:5', 'none']);
    const work = groups[0];
    expect(work.tasks).toEqual([]);
    expect(work.total).toBe(4);
    // Remaining of done tasks is not counted. Rounds the float error of 0.1 + 1.5 + 2
    expect(work.remainingHours).toBe(3.6);
    expect(work.children.map((c) => [c.key, c.depth, c.total])).toEqual([['project:2', 1, 2], ['project:4', 1, 2]]);
    expect(work.children[0].children.map((c) => [c.key, c.depth, c.tasks.map((t) => t.id)])).toEqual([['project:3', 2, [1]]]);
    expect(groups[1].remainingHours).toBe(0);
    expect(groups[2]).toMatchObject({ projectId: null, total: 1, remainingHours: 0.2 });
    // Checking a heading selects the whole group (child groups too)
    expect(groupTaskIds(work)).toEqual([2, 1, 3, 4]);
  });

  it('omits branches without tasks and makes the scoped project the top level', () => {
    const groups = groupTasksByProject(tasks.filter((t) => [1, 2].includes(t.id)), projects, 2);

    expect(groups.map((g) => [g.key, g.depth])).toEqual([['project:2', 0]]);
    expect(groups[0].children.map((c) => c.key)).toEqual(['project:3']);
  });

  it('puts tasks of a project missing from the list into one flat group by path (so they are not lost)', () => {
    const stray = task(9, '迷子', 99, { project_path: '消えた / 枝' });
    const groups = groupTasksByProject([stray, tasks[5]], projects);

    expect(groups.map((g) => [g.key, g.path])).toEqual([['project:99', '消えた / 枝'], ['none', null]]);
  });

  it('marks archived branches (children too)', () => {
    const archived = projects.map((x) => (x.id === 2 ? { ...x, status: 'archived' as const } : x));
    const [work] = groupTasksByProject(tasks, archived);

    expect(work.archived).toBe(false);
    expect(work.children[0].archived).toBe(true);
    expect(work.children[0].children[0].archived).toBe(true);
  });

  it('table rows: heading → direct tasks → child groups; hides the contents of collapsed groups', () => {
    const groups = groupTasksByProject(tasks, projects);
    const keys = (rows: ReturnType<typeof groupRows>) =>
      rows.map((r) => (r.kind === 'group' ? r.group.key : `task:${r.task.id}`));

    expect(keys(groupRows(groups))).toEqual([
      'project:1', 'project:2', 'task:2', 'project:3', 'task:1', 'project:4', 'task:3', 'task:4',
      'project:5', 'task:5', 'none', 'task:6',
    ]);
    expect(keys(groupRows(groups, new Set(['project:2'])))).toEqual([
      'project:1', 'project:2', 'project:4', 'task:3', 'task:4', 'project:5', 'task:5', 'none', 'task:6',
    ]);
  });
});

describe('subtasks within a group', () => {
  it('indents subtasks right after their parent (siblings keep their order) and leaves orphans in place', () => {
    const list = [
      task(3, '子 b', 2, { parent_task_id: 1 }),
      task(5, '迷子の子', 2, { parent_task_id: 99 }),
      task(1, '親', 2),
      task(4, '孫', 2, { parent_task_id: 3 }),
      task(2, '子 a', 2, { parent_task_id: 1 }),
    ];
    expect(nestBySubtask(list).map(({ task: t, level }) => [t.id, level])).toEqual([
      [5, 0], [1, 0], [3, 1], [4, 2], [2, 1],
    ]);
    const rows = groupRows(groupTasksByProject(list, projects));
    expect(rows.filter((r) => r.kind === 'task').map((r) => (r.kind === 'task' ? [r.task.id, r.depth, r.level] : null)))
      .toEqual([[5, 1, 0], [1, 1, 0], [3, 1, 1], [4, 1, 2], [2, 1, 1]]);
  });

  it('emits every task exactly once even with a cycle', () => {
    const list = [task(1, 'a', 2, { parent_task_id: 2 }), task(2, 'b', 2, { parent_task_id: 1 })];
    expect(nestBySubtask(list).map(({ task: t }) => t.id)).toEqual([1, 2]);
  });
});

describe('sorting', () => {
  it('project column sorts by tree order → missing from list → unassigned, then by task name within a project', () => {
    const stray = task(9, '迷子', 99, { project_path: '消えた' });
    const ids = (list: Task[]) => list.map((t) => t.id);

    expect(ids(sortTasks([...tasks, stray], 'project', false, projects))).toEqual([2, 1, 3, 4, 5, 9, 6]);
    expect(ids(sortTasks([...tasks, stray], 'project', true, projects))).toEqual([6, 9, 5, 4, 3, 1, 2]);
  });

  it('other columns sort as before (no due date last, priority highest first)', () => {
    const list = [
      task(1, 'b', null, { due_date: null, priority_score: 1 }),
      task(2, 'a', null, { due_date: '2026-10-03', priority_score: 9 }),
      task(3, 'c', null, { due_date: '2026-10-02', priority_score: 5 }),
    ];
    expect(sortTasks(list, 'due_date', false, projects).map((t) => t.id)).toEqual([3, 2, 1]);
    expect(sortTasks(list, 'priority_score', false, projects).map((t) => t.id)).toEqual([2, 3, 1]);
    expect(sortTasks(list, 'title', false, projects).map((t) => t.id)).toEqual([2, 1, 3]);
  });
});

describe('moving tasks to a project in bulk', () => {
  // 10 ─ 11 ─ 12 / 10 ─ 13 / 20 / parent 99 of 30 was deleted (not in the list)
  const tree: Task[] = [
    task(10, '親', 2), task(11, '子', 2, { parent_task_id: 10 }), task(12, '孫', 2, { parent_task_id: 11 }),
    task(13, '子 2', 2, { parent_task_id: 10 }), task(20, '別の根', null), task(30, '親が消えた子', 5, { parent_task_id: 99 }),
  ];

  it('sends only parents; unselected descendants are only counted (they move with the parent)', () => {
    const plan = planProjectMove([10, 12, 20], tree);

    expect(plan).toEqual({ roots: [10, 20], followers: [12], stranded: [], carried: 2 });
    expect(moveToProjectRequest(plan, 5)).toEqual({
      method: 'POST', url: '/tasks/move-to-project', body: { task_ids: [10, 20], project_id: 5 },
    });
    expect(moveToProjectRequest(plan, null)?.body).toEqual({ task_ids: [10, 20], project_id: null });
  });

  it('does not move (send) children whose parent is unselected; a child whose parent was deleted is a root', () => {
    const plan = planProjectMove([11, 12, 30], tree);

    expect(plan).toEqual({ roots: [30], followers: [12], stranded: [11], carried: 0 });
    expect(moveToProjectRequest(plan, 1)?.body.task_ids).toEqual([30]);
  });

  it('does not call when nothing can be moved; ids not in the list are not counted', () => {
    const plan = planProjectMove([11, 404], tree);

    expect(plan).toEqual({ roots: [], followers: [], stranded: [11], carried: 0 });
    expect(moveToProjectRequest(plan, 1)).toBeNull();
  });

  it('shows "with parent" in the table for descendants of selected tasks', () => {
    expect([...followingIds([10], tree)].sort()).toEqual([11, 12, 13]);
    expect([...followingIds([11, 20], tree)]).toEqual([12]);
  });
});
