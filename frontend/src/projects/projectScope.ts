// プロジェクトの木と絞り込み（task #187、ADR-0024）。画面に依らない計算だけを置く。
import type { Project } from '../types';

/** 画面で選んでいる範囲: 全部 / 未分類だけ / あるプロジェクトとその子孫。 */
export type ProjectScope = 'all' | 'none' | number;

/** 一覧の API に渡す絞り込み（サーバが子孫を含めて絞る）。 */
export interface ProjectFilterParams {
  project_id?: number;
  unclassified?: boolean;
}

export const scopeParams = (scope: ProjectScope): ProjectFilterParams => {
  if (scope === 'none') return { unclassified: true };
  if (scope === 'all') return {};
  return { project_id: scope };
};

/** 保存した値を読む（壊れていたら全部）。 */
export const parseScope = (raw: string | null): ProjectScope => {
  if (raw === 'none') return 'none';
  const id = Number(raw);
  return raw !== null && raw !== '' && Number.isInteger(id) && id > 0 ? id : 'all';
};

export const scopeToString = (scope: ProjectScope): string => String(scope);

/** 選んでいるプロジェクトが消えたら全部へ戻す。 */
export const validScope = (scope: ProjectScope, projects: readonly Project[] | undefined): ProjectScope => {
  if (typeof scope !== 'number' || projects === undefined) return scope;
  return projects.some((p) => p.id === scope) ? scope : 'all';
};

/** 自分と子孫の id。⚠ 壊れた環があっても止まる。 */
export const subtreeIds = (projects: readonly Project[], rootId: number): Set<number> => {
  const children = new Map<number, number[]>();
  for (const p of projects) {
    if (p.parent_project_id !== null) {
      children.set(p.parent_project_id, [...(children.get(p.parent_project_id) ?? []), p.id]);
    }
  }
  const found = new Set<number>();
  const stack = projects.some((p) => p.id === rootId) ? [rootId] : [];
  while (stack.length > 0) {
    const id = stack.pop() as number;
    if (found.has(id)) continue;
    found.add(id);
    stack.push(...(children.get(id) ?? []));
  }
  return found;
};

/** その範囲に入るか（タスク・マイルストーンの project_id で見る。画面の側で絞るとき用）。 */
export const inScope = (
  projectId: number | null, scope: ProjectScope, projects: readonly Project[],
): boolean => {
  if (scope === 'all') return true;
  if (scope === 'none') return projectId === null;
  return projectId !== null && subtreeIds(projects, scope).has(projectId);
};

/** 自分から根までの id（自分が先頭）。 */
export const ancestorsOrSelf = (projects: readonly Project[], id: number | null): number[] => {
  const byId = new Map(projects.map((p) => [p.id, p]));
  const chain: number[] = [];
  let current = id;
  while (current !== null && byId.has(current) && !chain.includes(current)) {
    chain.push(current);
    current = byId.get(current)?.parent_project_id ?? null;
  }
  return chain;
};

/** 自分か祖先が保管されているか（保管した枝は選び先に出さない）。 */
export const isEffectivelyArchived = (projects: readonly Project[], id: number): boolean => {
  const byId = new Map(projects.map((p) => [p.id, p]));
  return ancestorsOrSelf(projects, id).some((i) => byId.get(i)?.status === 'archived');
};

/**
 * タスクにそのマイルストーンを付けられるか（サーバと同じ決まり。ADR-0024）。
 * 未分類のマイルストーンはどこにでも付く。プロジェクトのものは、そのプロジェクトと子孫のタスクにだけ。
 */
export const milestoneReachable = (
  projects: readonly Project[], milestoneProjectId: number | null, taskProjectId: number | null,
): boolean =>
  milestoneProjectId === null || ancestorsOrSelf(projects, taskProjectId).includes(milestoneProjectId);

export interface ProjectNode {
  project: Project;
  depth: number;
  children: ProjectNode[];
}

/** 親子に組み直す（兄弟は並び順）。⚠ 親が一覧に居なければ最上位として置く（見失わせない）。 */
export const toTree = (projects: readonly Project[]): ProjectNode[] => {
  const known = new Set(projects.map((p) => p.id));
  const byParent = new Map<number | null, Project[]>();
  for (const p of projects) {
    const parent = p.parent_project_id !== null && known.has(p.parent_project_id) ? p.parent_project_id : null;
    byParent.set(parent, [...(byParent.get(parent) ?? []), p]);
  }
  const placed = new Set<number>();
  const build = (parent: number | null, depth: number): ProjectNode[] =>
    [...(byParent.get(parent) ?? [])]
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
      .filter((p) => !placed.has(p.id))
      .map((p) => {
        placed.add(p.id);
        return { project: p, depth, children: build(p.id, depth + 1) };
      });
  return build(null, 0);
};

/** 木の順に平らにする（選び先の一覧・字下げ付き）。 */
export const flattenTree = (nodes: readonly ProjectNode[]): ProjectNode[] =>
  nodes.flatMap((n) => [n, ...flattenTree(n.children)]);

/**
 * 選び先に出すプロジェクト（木の順）。保管した枝は出さない。ただし `keep` は（保管していても）残す
 * ——いま付いているものが選び先から消えると、保存しただけで外れてしまう。
 */
export const pickableProjects = (projects: readonly Project[], keep: number | null = null): ProjectNode[] =>
  flattenTree(toTree(projects)).filter((n) => n.project.id === keep || !isEffectivelyArchived(projects, n.project.id));

/** 親の付け替え先に出せるもの（自分と自分の子孫は除く。環になる）。 */
export const parentCandidates = (projects: readonly Project[], movingId: number): ProjectNode[] => {
  const excluded = subtreeIds(projects, movingId);
  return flattenTree(toTree(projects)).filter((n) => !excluded.has(n.project.id));
};
