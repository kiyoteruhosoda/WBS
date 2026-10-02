// タスクの選び方（task #189、ADR-0026）。締めの画面で打刻に振るときと、上部の打刻ボタンでタスクを
// 選ぶときの両方がこれを使う。画面に依らない計算だけを置く（並べ方・束ね方・検索）。
//
// 並び: 先頭の候補（同じ時間の予定のタスク・直前に使ったタスク）→ プロジェクトの木の順に、道筋の
// 見出しの下へタスク → 未分類は最後。サイドバーで範囲を選んでいれば、範囲の中の束を先に、範囲の外を後に
// （隠さない。打刻は範囲の外のタスクにも振れないと確定できない）。
import type { CalendarOccurrence, Project, Task, TimeEntry } from '../types';
import type { ProjectScope } from './projectScope';
import { flattenTree, inScope, toTree } from './projectScope';

/** 先頭に出す理由。 */
export type PickerHeadReason = 'schedule' | 'recent';

export interface PickerHead {
  taskId: number;
  reason: PickerHeadReason;
}

export interface PickerTask {
  taskId: number;
  title: string;
  /** 表示用の道筋（「親 / 子」。未分類は null） */
  projectPath: string | null;
  /** 先頭の候補なら理由。束の中なら null */
  reason: PickerHeadReason | null;
}

export interface PickerGroup {
  /** `project:<id>` か `none`（未分類） */
  key: string;
  projectId: number | null;
  /** 見出し（プロジェクトの道筋。未分類は null） */
  label: string | null;
  color: string | null;
  /** サイドバーの範囲に入るか（範囲の外の束は後ろへ回す） */
  inScope: boolean;
  tasks: PickerTask[];
}

export interface TaskPickerModel {
  head: PickerTask[];
  groups: PickerGroup[];
  /** 何も当たらない */
  empty: boolean;
}

/** 選び先に出すタスク（消していない・済んでいない・やめていない）。 */
export const isPickableTask = (task: Task): boolean =>
  task.deleted_at == null && task.status !== 'DONE' && task.status !== 'CANCELLED';

/** 比べる形（全角・半角と大文字・小文字を揃える）。 */
const fold = (text: string): string => text.normalize('NFKC').toLowerCase();

/**
 * 検索語に当たるか。空白で区切った語が全部、タスク名かプロジェクトの道筋のどこかに入っていれば当たり
 * （「案件A 設計」で「案件 A」のプロジェクトの「設計」が引ける）。
 */
export const matchesQuery = (title: string, projectPath: string | null, query: string): boolean => {
  const words = fold(query).split(/\s+/).filter((w) => w.length > 0);
  if (words.length === 0) return true;
  const haystack = fold(`${title}\n${projectPath ?? ''}`);
  // 道筋は「親 / 子」なので、空白を詰めた形でも探す（「案件a」で「案件 A」に当てる）
  const compact = haystack.replace(/\s+/g, '');
  return words.every((w) => haystack.includes(w) || compact.includes(w));
};

/**
 * 束ねる。`head` は先頭へ（理由つき・重ねて出さない）、残りはプロジェクトの木の順に束ねる。
 * 先頭の候補は、済んだタスクでも出す（同じ時間の予定に結んだタスクを、済ませたあとで振ることはある）。
 * 消したタスクは先頭にも出さない（振れない）。
 */
export const buildTaskPicker = (input: {
  tasks: readonly Task[];
  projects: readonly Project[];
  head?: readonly PickerHead[];
  scope?: ProjectScope;
  query?: string;
  /** 済んでいても束に残すタスク（フォームでいま選んでいるもの。選び先から消えると値が読めなくなる） */
  keep?: number | null;
}): TaskPickerModel => {
  const { tasks, projects, head = [], scope = 'all', query = '', keep = null } = input;
  const live = new Map(tasks.filter((t) => t.deleted_at == null).map((t) => [t.id, t]));
  const projectsById = new Map(projects.map((p) => [p.id, p]));
  const pathOf = (task: Task): string | null =>
    task.project_id == null ? null : projectsById.get(task.project_id)?.path ?? task.project_path;

  const headTasks: PickerTask[] = [];
  const inHead = new Set<number>();
  for (const h of head) {
    const task = live.get(h.taskId);
    if (!task || inHead.has(task.id)) continue;
    inHead.add(task.id);
    const projectPath = pathOf(task);
    if (!matchesQuery(task.title, projectPath, query)) continue;
    headTasks.push({ taskId: task.id, title: task.title, projectPath, reason: h.reason });
  }

  // プロジェクト → タスク
  const byProject = new Map<number | null, Task[]>();
  for (const task of live.values()) {
    if (inHead.has(task.id) || (task.id !== keep && !isPickableTask(task))) continue;
    if (!matchesQuery(task.title, pathOf(task), query)) continue;
    const key = task.project_id ?? null;
    byProject.set(key, [...(byProject.get(key) ?? []), task]);
  }
  const toPicker = (list: readonly Task[]): PickerTask[] =>
    [...list]
      .sort((a, b) => a.title.localeCompare(b.title, 'ja') || a.id - b.id)
      .map((t) => ({ taskId: t.id, title: t.title, projectPath: pathOf(t), reason: null }));

  const groups: PickerGroup[] = [];
  const placed = new Set<number | null>();
  for (const { project } of flattenTree(toTree(projects))) {
    const list = byProject.get(project.id);
    placed.add(project.id);
    if (!list) continue;
    groups.push({
      key: `project:${project.id}`, projectId: project.id, label: project.path, color: project.color,
      inScope: inScope(project.id, scope, projects), tasks: toPicker(list),
    });
  }
  // 一覧に無いプロジェクト（読み込みの行き違い）。見失わないよう、タスクの持つ道筋で出す
  for (const [projectId, list] of byProject) {
    if (projectId === null || placed.has(projectId)) continue;
    groups.push({
      key: `project:${projectId}`, projectId, label: list[0].project_path ?? `#${projectId}`, color: null,
      inScope: scope === 'all', tasks: toPicker(list),
    });
  }
  const unclassified = byProject.get(null);
  if (unclassified) {
    groups.push({
      key: 'none', projectId: null, label: null, color: null,
      inScope: inScope(null, scope, projects), tasks: toPicker(unclassified),
    });
  }
  // 範囲の中を先に（それぞれの中は木の順のまま。sort は安定）
  groups.sort((a, b) => Number(b.inScope) - Number(a.inScope));

  return { head: headTasks, groups, empty: headTasks.length === 0 && groups.length === 0 };
};

/** 束を 1 列に（先頭の候補 → 束の順）。選び先を 1 本の一覧で持つ部品（Autocomplete）用。 */
export const flattenPicker = (model: TaskPickerModel): { task: PickerTask; groupKey: string }[] => [
  ...model.head.map((task) => ({ task, groupKey: 'head' })),
  ...model.groups.flatMap((g) => g.tasks.map((task) => ({ task, groupKey: g.key }))),
];

// ── 先頭の候補 ──────────────────────────────────────────────────────────

interface Range {
  startMs: number;
  endMs: number;
}

const overlapMs = (a: Range, b: Range): number => Math.max(0, Math.min(a.endMs, b.endMs) - Math.max(a.startMs, b.startMs));

/** 範囲（打刻・いま）と時間が重なる予定の回のタスクを、重なりの長い順に。終日の回は数えない。 */
export const scheduledTaskIds = (ranges: readonly Range[], occurrences: readonly CalendarOccurrence[]): number[] => {
  const overlaps = new Map<number, number>();
  for (const o of occurrences) {
    if (o.task_id == null || o.is_all_day) continue;
    const startMs = Date.parse(o.start);
    const range = { startMs, endMs: startMs + Math.max(0, o.duration_minutes) * 60_000 };
    const overlap = ranges.reduce((sum, r) => sum + overlapMs(range, r), 0);
    if (overlap <= 0) continue;
    overlaps.set(o.task_id, (overlaps.get(o.task_id) ?? 0) + overlap);
  }
  return [...overlaps.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]).map(([id]) => id);
};

/**
 * 直前に使ったタスク: `beforeMs` より前に始まった打刻のタスクを、新しい順に（重ねない・`limit` まで）。
 * `exclude` の打刻（いま選んでいるもの）は数えない。
 */
export const recentTaskIds = (
  entries: readonly TimeEntry[],
  beforeMs: number,
  options: { exclude?: ReadonlySet<number>; limit?: number } = {},
): number[] => {
  const { exclude = new Set<number>(), limit = 3 } = options;
  const ids: number[] = [];
  const ordered = entries
    .filter((e) => e.task_id != null && !exclude.has(e.id) && Date.parse(e.started_at) < beforeMs)
    .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at) || b.id - a.id);
  for (const e of ordered) {
    if (ids.length >= limit) break;
    if (!ids.includes(e.task_id as number)) ids.push(e.task_id as number);
  }
  return ids;
};

/** 予定のタスクを先に、直前に使ったタスクをその後に（重ねない）。 */
export const pickerHead = (scheduled: readonly number[], recent: readonly number[]): PickerHead[] => [
  ...scheduled.map((taskId) => ({ taskId, reason: 'schedule' as const })),
  ...recent.filter((id) => !scheduled.includes(id)).map((taskId) => ({ taskId, reason: 'recent' as const })),
];
