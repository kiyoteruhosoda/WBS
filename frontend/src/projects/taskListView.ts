// Viewing and moving the task list (/tasks) by project (task #187, ADR-0030). Holds only UI-independent logic
// (sorting, grouping, splitting a bulk move, and the API call).
import type { Project, Task } from '../types';
import type { ProjectNode, ProjectScope } from './projectScope';
import { flattenTree, toTree } from './projectScope';

// ── Sorting ────────────────────────────────────────────────────────────

export type TaskSortKey = 'priority_score' | 'title' | 'due_date' | 'project';

/** Project tree order (id → position). */
export const projectOrder = (projects: readonly Project[]): Map<number, number> =>
  new Map(flattenTree(toTree(projects)).map((n, i) => [n.project.id, i]));

/**
 * Compare by project: tree order → projects missing from the list (by path) → unassigned. Within a project, by task name.
 */
const compareProject = (a: Task, b: Task, order: ReadonlyMap<number, number>): number => {
  const rank = (t: Task): [number, number, string] => {
    if (t.project_id == null) return [2, 0, ''];
    const i = order.get(t.project_id);
    return i === undefined ? [1, 0, t.project_path ?? ''] : [0, i, ''];
  };
  const [ga, ia, pa] = rank(a);
  const [gb, ib, pb] = rank(b);
  return ga - gb || ia - ib || pa.localeCompare(pb, 'ja') || a.title.localeCompare(b.title, 'ja');
};

export const compareTasks = (
  a: Task, b: Task, key: TaskSortKey, order: ReadonlyMap<number, number> = new Map(),
): number => {
  if (key === 'title') return a.title.localeCompare(b.title, 'ja');
  if (key === 'due_date') {
    if (!a.due_date && !b.due_date) return 0;
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return a.due_date.localeCompare(b.due_date);
  }
  if (key === 'project') return compareProject(a, b, order);
  return b.priority_score - a.priority_score;
};

/** Sort (descending reverses ascending; sort is stable). */
export const sortTasks = (
  tasks: readonly Task[], key: TaskSortKey, desc: boolean, projects: readonly Project[],
): Task[] => {
  const order = projectOrder(projects);
  const sorted = [...tasks].sort((a, b) => compareTasks(a, b, key, order));
  return desc ? sorted.reverse() : sorted;
};

// ── Grouping by project ────────────────────────────────────────────────

export interface TaskGroupNode {
  /** `project:<id>` or `none` (unassigned) */
  key: string;
  projectId: number | null;
  /** Heading (project name; null for unassigned or missing from list → decided by the UI) */
  name: string | null;
  /** Path ("parent / child"). null for unassigned */
  path: string | null;
  color: string | null;
  depth: number;
  archived: boolean;
  /** Tasks attached directly to this project (in the given order) */
  tasks: Task[];
  /** Task count including descendants */
  total: number;
  /** Total remaining including descendants (excludes done/cancelled and undetermined remaining) */
  remainingHours: number;
  children: TaskGroupNode[];
}

const isOpen = (t: Task): boolean => t.status !== 'DONE' && t.status !== 'CANCELLED';
const remainingOf = (tasks: readonly Task[]): number =>
  tasks.reduce((sum, t) => sum + (isOpen(t) && t.remaining_hours != null ? t.remaining_hours : 0), 0);
/** Round away float error from addition (0.1 + 0.2). */
const round2 = (n: number): number => Math.round(n * 100) / 100;

/**
 * Group: tasks under project tree headings, child projects nested. Branches without tasks are omitted.
 * If a project is selected as scope, it becomes the top level (ancestor headings are not shown).
 * Tasks of projects missing from the list (load race) go into one flat group by path. Unassigned comes last.
 */
export const groupTasksByProject = (
  tasks: readonly Task[], projects: readonly Project[], scope: ProjectScope = 'all',
): TaskGroupNode[] => {
  const byProject = new Map<number | null, Task[]>();
  for (const t of tasks) {
    const key = t.project_id ?? null;
    byProject.set(key, [...(byProject.get(key) ?? []), t]);
  }

  let roots: ProjectNode[] = toTree(projects);
  if (typeof scope === 'number') {
    const found = flattenTree(roots).find((n) => n.project.id === scope);
    roots = found ? [found] : roots;
  }
  const placed = new Set<number>();
  const build = (node: ProjectNode, depth: number, archivedAbove: boolean): TaskGroupNode | null => {
    placed.add(node.project.id);
    const archived = archivedAbove || node.project.status === 'archived';
    const children = node.children
      .map((c) => build(c, depth + 1, archived))
      .filter((c): c is TaskGroupNode => c !== null);
    const own = byProject.get(node.project.id) ?? [];
    const total = own.length + children.reduce((s, c) => s + c.total, 0);
    if (total === 0) return null;
    return {
      key: `project:${node.project.id}`, projectId: node.project.id, name: node.project.name,
      path: node.project.path, color: node.project.color, depth, archived, tasks: own, total,
      remainingHours: round2(remainingOf(own) + children.reduce((s, c) => s + c.remainingHours, 0)),
      children,
    };
  };
  const groups = roots.map((r) => build(r, 0, false)).filter((g): g is TaskGroupNode => g !== null);

  const leaf = (key: string, projectId: number | null, path: string | null, list: Task[]): TaskGroupNode => ({
    key, projectId, name: null, path, color: null, depth: 0, archived: false, tasks: list,
    total: list.length, remainingHours: round2(remainingOf(list)), children: [],
  });
  for (const [projectId, list] of byProject) {
    if (projectId === null || placed.has(projectId)) continue;
    groups.push(leaf(`project:${projectId}`, projectId, list[0].project_path ?? `#${projectId}`, list));
  }
  const unclassified = byProject.get(null);
  if (unclassified) groups.push(leaf('none', null, null, unclassified));
  return groups;
};

/** Task ids in a group (including child groups). Checking a heading selects the whole group. */
export const groupTaskIds = (group: TaskGroupNode): number[] => [
  ...group.tasks.map((t) => t.id),
  ...group.children.flatMap(groupTaskIds),
];

export type TaskListRow =
  | { kind: 'group'; group: TaskGroupNode }
  /** `depth` is the group depth, `level` the subtask depth (indented under the parent task) */
  | { kind: 'task'; task: Task; depth: number; level: number };

/**
 * Put subtasks right after their parent (siblings keep the given order). A child whose parent is not in the list stays in place as top level.
 * ⚠ Emits every task exactly once even if there is a broken cycle.
 */
export const nestBySubtask = (tasks: readonly Task[]): { task: Task; level: number }[] => {
  const ids = new Set(tasks.map((t) => t.id));
  const children = new Map<number, Task[]>();
  for (const t of tasks) {
    if (t.parent_task_id != null && ids.has(t.parent_task_id)) {
      children.set(t.parent_task_id, [...(children.get(t.parent_task_id) ?? []), t]);
    }
  }
  const out: { task: Task; level: number }[] = [];
  const done = new Set<number>();
  const visit = (t: Task, level: number) => {
    if (done.has(t.id)) return;
    done.add(t.id);
    out.push({ task: t, level });
    for (const c of children.get(t.id) ?? []) visit(c, level + 1);
  };
  for (const t of tasks) {
    if (t.parent_task_id == null || !ids.has(t.parent_task_id)) visit(t, 0);
  }
  for (const t of tasks) visit(t, 0);
  return out;
};

/** Turn groups into table rows (heading → direct tasks (subtasks under their parent) → child groups). Collapsed group contents are not emitted. */
export const groupRows = (groups: readonly TaskGroupNode[], collapsed: ReadonlySet<string> = new Set()): TaskListRow[] =>
  groups.flatMap((g) => [
    { kind: 'group' as const, group: g },
    ...(collapsed.has(g.key)
      ? []
      : [
        ...nestBySubtask(g.tasks).map(({ task, level }) => ({ kind: 'task' as const, task, depth: g.depth, level })),
        ...groupRows(g.children, collapsed),
      ]),
  ]);

// ── Bulk move ────────────────────────────────────────────────────────

export interface ProjectMovePlan {
  /** Tasks to move (those without a parent). Only these are sent */
  roots: number[];
  /** Selected subtasks that move with an ancestor */
  followers: number[];
  /** Subtasks whose ancestors are not selected. Not moved, as they follow their parent */
  stranded: number[];
  /** Number of unselected descendants that move with their parent */
  carried: number;
}

/**
 * Split the selected tasks (same rules as the server's `TaskBranchSelection`; ADR-0024 item 4, ADR-0030).
 * `tasks` are the non-deleted tasks (the whole scope; used to count descendants). A child whose parent is not in the list is treated as a root.
 */
export const planProjectMove = (selected: Iterable<number>, tasks: readonly Task[]): ProjectMovePlan => {
  const parentOf = new Map(tasks.map((t) => [t.id, t.parent_task_id ?? null]));
  const chosen = [...new Set(selected)].filter((id) => parentOf.has(id));
  const chosenSet = new Set(chosen);
  const hasSelectedAncestor = (id: number): boolean => {
    const seen = new Set([id]);
    let current = parentOf.get(id) ?? null;
    while (current !== null && parentOf.has(current) && !seen.has(current)) {
      if (chosenSet.has(current)) return true;
      seen.add(current);
      current = parentOf.get(current) ?? null;
    }
    return false;
  };
  const plan: ProjectMovePlan = { roots: [], followers: [], stranded: [], carried: 0 };
  for (const id of chosen) {
    const parent = parentOf.get(id) ?? null;
    if (parent === null || !parentOf.has(parent)) plan.roots.push(id);
    else if (hasSelectedAncestor(id)) plan.followers.push(id);
    else plan.stranded.push(id);
  }

  // Descendants of the roots that are not selected
  const children = new Map<number, number[]>();
  for (const t of tasks) {
    if (t.parent_task_id != null) children.set(t.parent_task_id, [...(children.get(t.parent_task_id) ?? []), t.id]);
  }
  const reached = new Set<number>();
  const stack = [...plan.roots];
  while (stack.length > 0) {
    const id = stack.pop() as number;
    for (const c of children.get(id) ?? []) {
      if (reached.has(c)) continue;
      reached.add(c);
      stack.push(c);
    }
  }
  plan.carried = [...reached].filter((id) => !chosenSet.has(id)).length;
  return plan;
};

/** Ids of tasks that move with their parent (under a selected parent). Shown as "with parent" in the table. */
export const followingIds = (selected: Iterable<number>, tasks: readonly Task[]): Set<number> => {
  const chosen = new Set(selected);
  const parentOf = new Map(tasks.map((t) => [t.id, t.parent_task_id ?? null]));
  const out = new Set<number>();
  for (const t of tasks) {
    const seen = new Set([t.id]);
    let current = parentOf.get(t.id) ?? null;
    while (current !== null && parentOf.has(current) && !seen.has(current)) {
      if (chosen.has(current)) { out.add(t.id); break; }
      seen.add(current);
      current = parentOf.get(current) ?? null;
    }
  }
  return out;
};

export interface MoveToProjectRequest {
  method: 'POST';
  url: '/tasks/move-to-project';
  body: { task_ids: number[]; project_id: number | null };
}

/** Bulk move call (sends only the roots; null if nothing to move). `projectId` null moves to unassigned. */
export const moveToProjectRequest = (plan: ProjectMovePlan, projectId: number | null): MoveToProjectRequest | null =>
  plan.roots.length === 0
    ? null
    : { method: 'POST', url: '/tasks/move-to-project', body: { task_ids: [...plan.roots], project_id: projectId } };
