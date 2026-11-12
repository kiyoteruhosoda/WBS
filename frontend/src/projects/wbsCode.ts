import type { Project, Task } from '../types';
import { toTree } from './projectScope';
import type { ProjectNode } from './projectScope';

/**
 * WBS codes (task #639, ADR-0061). Top-level projects are 1, 2… in tree order. Under a project, like the list order,
 * direct tasks (creation order = id) then child projects (tree order) share one sequence "parent.n"; subtasks get ".n" under their parent's code.
 * Unaffected by sorting and filtering (the given list is unfiltered). Project codes are returned too (for the list group headings).
 * Unassigned tasks get no code (not in the Map).
 */
export const wbsCodes = (
  tasks: readonly Task[], projects: readonly Project[],
): { tasks: Map<number, string>; projects: Map<number, string> } => {
  const codes = new Map<number, string>();
  const projectCodes = new Map<number, string>();
  const byProject = new Map<number, Task[]>();
  for (const t of tasks) {
    if (t.project_id == null) continue;
    byProject.set(t.project_id, [...(byProject.get(t.project_id) ?? []), t]);
  }
  /** Numbers the direct tasks and returns how many were used (child projects continue from there) */
  const visitTasks = (list: readonly Task[], prefix: string): number => {
    const ids = new Set(list.map((t) => t.id));
    const children = new Map<number | null, Task[]>();
    for (const t of list) {
      const parent = t.parent_task_id != null && ids.has(t.parent_task_id) ? t.parent_task_id : null;
      children.set(parent, [...(children.get(parent) ?? []), t]);
    }
    const visit = (parent: number | null, code: string): number => {
      const kids = [...(children.get(parent) ?? [])].sort((a, b) => a.id - b.id);
      kids.forEach((t, i) => {
        // ⚠ Once each even with a broken cycle
        if (codes.has(t.id)) return;
        const own = `${code}.${i + 1}`;
        codes.set(t.id, own);
        visit(t.id, own);
      });
      return kids.length;
    };
    return visit(null, prefix);
  };
  const visitProjects = (nodes: readonly ProjectNode[], prefix: string, start: number) => {
    nodes.forEach((n, i) => {
      const code = prefix ? `${prefix}.${start + i + 1}` : String(start + i + 1);
      projectCodes.set(n.project.id, code);
      const used = visitTasks(byProject.get(n.project.id) ?? [], code);
      visitProjects(n.children, code, used);
    });
  };
  visitProjects(toTree(projects), '', 0);
  return { tasks: codes, projects: projectCodes };
};

/** Shape of branch rails. `rails[k - 1]` is whether the depth-k line passes through this row to the rows below */
export interface TreeGuide {
  level: number;
  /** Last sibling (stops its own line at the middle of the row) */
  last: boolean;
  rails: boolean[];
}

/** Compute per-row branch rails from the sequence of indent depths (tree order). */
export const treeGuides = (levels: readonly number[]): TreeGuide[] => {
  const out: TreeGuide[] = new Array(levels.length);
  // Scanning backwards: whether a depth-k row continues below (without being interrupted by a shallower row)
  const open: boolean[] = [];
  for (let i = levels.length - 1; i >= 0; i--) {
    const level = levels[i];
    out[i] = {
      level,
      last: !open[level],
      rails: Array.from({ length: Math.max(0, level - 1) }, (_, k) => open[k + 1] === true),
    };
    open.length = level + 1;
    open[level] = true;
  }
  return out;
};
