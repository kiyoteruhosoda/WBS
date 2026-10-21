import { describe, expect, it } from 'vitest';
import type { Project, Task } from '../types';
import { treeGuides, wbsCodes } from './wbsCode';

const p = (id: number, name: string, parent: number | null = null, extra: Partial<Project> = {}): Project => ({
  id, name, parent_project_id: parent, color: null, code: null, description: null, status: 'active', sort_order: 0, path: name, root_project_id: id, my_role: 'manager', ...extra,
});

const task = (id: number, projectId: number | null, parent: number | null = null): Task => ({
  id, user_id: 1, title: `t${id}`, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: null,
  estimated_hours: null, remaining_hours: null, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
  rollup_actual_hours: 0, rollup_remaining_hours: null, progress_percent: null, scheduled_hours: null, unscheduled_hours: null,
  priority_score: 0, memo: null, parent_task_id: parent, milestone_id: null, project_id: projectId, project_path: null,
  completed_at: null, deleted_at: null, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
});

// 仕事(1) ─ 案件 A(2) / 仕事 ─ 案件 B(4) / 私用(5)
const projects: Project[] = [
  p(1, '仕事'), p(2, '案件 A', 1), p(4, '案件 B', 1, { sort_order: 1 }), p(5, '私用', null, { sort_order: 1 }),
];

describe('WBS 番号', () => {
  it('直のタスク（作った順）→ 子のプロジェクトで通し番号・子タスクは親の下・未分類は付けない', () => {
    // 渡す順は番号に効かない（id の順）
    const tasks = [task(30, 2), task(10, 2), task(11, 2, 10), task(12, 2, 10), task(13, 2, 12), task(20, 1), task(40, 5), task(50, null)];
    const codes = wbsCodes(tasks, projects);

    expect(Object.fromEntries(codes.projects)).toEqual({ 1: '1', 2: '1.2', 4: '1.3', 5: '2' });
    expect(Object.fromEntries(codes.tasks)).toEqual({
      20: '1.1', 10: '1.2.1', 11: '1.2.1.1', 12: '1.2.1.2', 13: '1.2.1.2.1', 30: '1.2.2', 40: '2.1',
    });
  });

  it('親が一覧に居ない子タスクは最上位として数える・壊れた環でも止まる', () => {
    const codes = wbsCodes([task(7, 5, 99), task(8, 5, 9), task(9, 5, 8)], projects);
    expect(codes.tasks.get(7)).toBe('2.1');
    // 8 と 9 は互いが親（環）。最上位に誰も居ないので番号は付かないが、止まる
    expect(codes.tasks.has(8)).toBe(false);
  });
});

describe('枝の罫線', () => {
  it('兄弟の最後で線を止め、上の段の線は続く間だけ通す', () => {
    // 1 / 1.1 / 1.1.1 / 1.1.2 / 1.2 / 2
    const g = treeGuides([0, 1, 2, 2, 1, 0]);
    expect(g.map((x) => x.last)).toEqual([false, false, false, true, true, true]);
    // 1.1.1 と 1.1.2 の行を、1.2 へ向かう深さ 1 の線が通る
    expect(g[2].rails).toEqual([true]);
    expect(g[3].rails).toEqual([true]);
    expect(g[1].rails).toEqual([]);
  });

  it('浅い行に遮られた線は続かない', () => {
    // 1 / 1.1 / 1.1.1 / 2 / 2.1
    const g = treeGuides([0, 1, 2, 0, 1]);
    expect(g[1].last).toBe(true);
    expect(g[2].rails).toEqual([false]);
    expect(g[4].last).toBe(true);
  });
});
