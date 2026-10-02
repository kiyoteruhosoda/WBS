// タスク一覧（/tasks）をプロジェクトで見る・移す（task #187、ADR-0030）。画面に依らない計算だけを置く
// （並べ方・束ね方・まとめて移すときの分け方・API の呼び出し）。
import type { Project, Task } from '../types';
import type { ProjectNode, ProjectScope } from './projectScope';
import { flattenTree, toTree } from './projectScope';

// ── 並べ替え ────────────────────────────────────────────────────────────

export type TaskSortKey = 'priority_score' | 'title' | 'due_date' | 'project';

/** プロジェクトの木の順（id → 何番目か）。 */
export const projectOrder = (projects: readonly Project[]): Map<number, number> =>
  new Map(flattenTree(toTree(projects)).map((n, i) => [n.project.id, i]));

/**
 * プロジェクトで比べる: 木の順 → 一覧に無いプロジェクト（道筋の順）→ 未分類。同じプロジェクトの中はタスク名。
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

/** 並べる（降順は昇順を裏返す。sort は安定）。 */
export const sortTasks = (
  tasks: readonly Task[], key: TaskSortKey, desc: boolean, projects: readonly Project[],
): Task[] => {
  const order = projectOrder(projects);
  const sorted = [...tasks].sort((a, b) => compareTasks(a, b, key, order));
  return desc ? sorted.reverse() : sorted;
};

// ── プロジェクトで束ねる ────────────────────────────────────────────────

export interface TaskGroupNode {
  /** `project:<id>` か `none`（未分類） */
  key: string;
  projectId: number | null;
  /** 見出し（プロジェクト名。未分類・一覧に無いものは null → 画面で決める） */
  name: string | null;
  /** 道筋（「親 / 子」）。未分類は null */
  path: string | null;
  color: string | null;
  depth: number;
  archived: boolean;
  /** このプロジェクトに直に付いたタスク（渡した順のまま） */
  tasks: Task[];
  /** 子孫まで含めたタスクの数 */
  total: number;
  /** 子孫まで含めた残の合計（済み・中止は数えない。残の決まらないものも数えない） */
  remainingHours: number;
  children: TaskGroupNode[];
}

const isOpen = (t: Task): boolean => t.status !== 'DONE' && t.status !== 'CANCELLED';
const remainingOf = (tasks: readonly Task[]): number =>
  tasks.reduce((sum, t) => sum + (isOpen(t) && t.remaining_hours != null ? t.remaining_hours : 0), 0);
/** 足し算の端数（0.1 + 0.2）を丸める。 */
const round2 = (n: number): number => Math.round(n * 100) / 100;

/**
 * 束ねる。プロジェクトの木の見出しの下にタスク、子プロジェクトは入れ子。タスクの無い枝は出さない。
 * 範囲でプロジェクトを選んでいれば、そのプロジェクトを最上位にする（祖先の見出しは出さない）。
 * 一覧に無いプロジェクト（読み込みの行き違い）のタスクは道筋で 1 段の束に。未分類は最後。
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

/** 束の中のタスクの id（子の束も含む）。見出しのチェックで束ごと選ぶ。 */
export const groupTaskIds = (group: TaskGroupNode): number[] => [
  ...group.tasks.map((t) => t.id),
  ...group.children.flatMap(groupTaskIds),
];

export type TaskListRow =
  | { kind: 'group'; group: TaskGroupNode }
  /** `depth` は束の深さ、`level` は子タスクの深さ（親タスクの下に字下げする） */
  | { kind: 'task'; task: Task; depth: number; level: number };

/**
 * 子タスクを親の直後へ（兄弟の間は渡した順のまま）。親が一覧に居ない子は、その場所に最上位として残す。
 * ⚠ 壊れた環があっても、全部のタスクを 1 回ずつ出す。
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

/** 束を表の行に（見出し → 直のタスク（子タスクは親の下）→ 子の束）。畳んだ束の中身は出さない。 */
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

// ── まとめて移す ────────────────────────────────────────────────────────

export interface ProjectMovePlan {
  /** 移すタスク（親の無いもの）。送るのはこれだけ */
  roots: number[];
  /** 祖先と一緒に移る、選んだ子タスク */
  followers: number[];
  /** 祖先を選んでいない子タスク。親に従うので移さない */
  stranded: number[];
  /** 選んでいないが、親と一緒に移る子孫の数 */
  carried: number;
}

/**
 * 選んだタスクを分ける（サーバの `TaskBranchSelection` と同じ決まり。ADR-0024 の 4・ADR-0030）。
 * `tasks` は消していないタスク（範囲の全部。子孫の数を数えるのに使う）。親が一覧に居ない子は根として扱う。
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

  // 根の子孫のうち、選んでいないもの
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

/** 子孫が親と一緒に移る（選んだ親の下にある）タスクの id。表で「親と一緒」と見せる。 */
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

/** まとめて移す呼び出し（根だけを送る。移すものが無ければ null）。`projectId` が null なら未分類へ。 */
export const moveToProjectRequest = (plan: ProjectMovePlan, projectId: number | null): MoveToProjectRequest | null =>
  plan.roots.length === 0
    ? null
    : { method: 'POST', url: '/tasks/move-to-project', body: { task_ids: [...plan.roots], project_id: projectId } };
