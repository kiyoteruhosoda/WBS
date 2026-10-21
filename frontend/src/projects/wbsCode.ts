import type { Project, Task } from '../types';
import { toTree } from './projectScope';
import type { ProjectNode } from './projectScope';

/**
 * WBS 番号（task #639・ADR-0061）。最上位のプロジェクトを木の順に 1・2…。プロジェクトの下は一覧の並びと同じく
 * 直のタスク（作った順＝id）→ 子のプロジェクト（木の順）で 1 本の通し番号「親の番号.n」、子タスクは親の番号の下に「.n」。
 * 並べ替え・絞り込みでは変わらない（渡す一覧は絞る前のもの）。プロジェクトの番号も返す（一覧の束の見出し）。
 * 未分類のタスクには付けない（Map に入らない）。
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
  /** 直のタスクに番号を振り、使った数（子のプロジェクトはその次から）を返す */
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
        // ⚠ 壊れた環があっても 1 回ずつ
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

/** 枝の罫線の形。`rails[k - 1]` は深さ k の線が、この行を通って下の行へ続くか */
export interface TreeGuide {
  level: number;
  /** 兄弟の最後（自分の線を行の真ん中で止める） */
  last: boolean;
  rails: boolean[];
}

/** 字下げの深さの並び（木の順）から、行ごとの枝の罫線を出す。 */
export const treeGuides = (levels: readonly number[]): TreeGuide[] => {
  const out: TreeGuide[] = new Array(levels.length);
  // 後ろから見て、深さ k の行が（それより浅い行に遮られずに）下に続いているか
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
