// Project tree and filtering (task #187, ADR-0024). Holds only UI-independent logic.
import type { Project } from '../types';

/** Scope selected in the UI: all / unassigned only / a project and its descendants. */
export type ProjectScope = 'all' | 'none' | number;

/** Filter passed to the list API (the server includes descendants). */
export interface ProjectFilterParams {
  project_id?: number;
  unclassified?: boolean;
}

export const scopeParams = (scope: ProjectScope): ProjectFilterParams => {
  if (scope === 'none') return { unclassified: true };
  if (scope === 'all') return {};
  return { project_id: scope };
};

/** Read the saved value (all when corrupt). */
export const parseScope = (raw: string | null): ProjectScope => {
  if (raw === 'none') return 'none';
  const id = Number(raw);
  return raw !== null && raw !== '' && Number.isInteger(id) && id > 0 ? id : 'all';
};

export const scopeToString = (scope: ProjectScope): string => String(scope);

/** Fall back to all when the selected project disappears. */
export const validScope = (scope: ProjectScope, projects: readonly Project[] | undefined): ProjectScope => {
  if (typeof scope !== 'number' || projects === undefined) return scope;
  return projects.some((p) => p.id === scope) ? scope : 'all';
};

/** Ids of self and descendants. ⚠ Terminates even with a broken cycle. */
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

/** Whether it falls within the scope (by the task/milestone project_id; for client-side filtering). */
export const inScope = (
  projectId: number | null, scope: ProjectScope, projects: readonly Project[],
): boolean => {
  if (scope === 'all') return true;
  if (scope === 'none') return projectId === null;
  return projectId !== null && subtreeIds(projects, scope).has(projectId);
};

/** Ids from self up to the root (self first). */
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

/** Whether self or an ancestor is archived (archived branches are not offered as choices). */
export const isEffectivelyArchived = (projects: readonly Project[], id: number): boolean => {
  const byId = new Map(projects.map((p) => [p.id, p]));
  return ancestorsOrSelf(projects, id).some((i) => byId.get(i)?.status === 'archived');
};

/**
 * Whether the milestone can be attached to the task (same rule as the server. ADR-0024).
 * Unassigned milestones attach anywhere; a project's milestones only to tasks of that project and its descendants.
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

/** Rebuild parent/child structure (siblings by sort order). ⚠ If the parent is missing from the list, place it at top level (so it is not lost). */
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

/** Flatten in tree order (for choice lists, with indentation). */
export const flattenTree = (nodes: readonly ProjectNode[]): ProjectNode[] =>
  nodes.flatMap((n) => [n, ...flattenTree(n.children)]);

/**
 * Projects offered as choices (tree order). Archived branches are omitted, but `keep` stays (even if archived)
 * —— if the current value vanished from the choices, merely saving would detach it.
 */
export const pickableProjects = (projects: readonly Project[], keep: number | null = null): ProjectNode[] =>
  flattenTree(toTree(projects)).filter((n) => n.project.id === keep || !isEffectivelyArchived(projects, n.project.id));

/** Possible new parents (excluding self and own descendants, which would form a cycle). */
export const parentCandidates = (projects: readonly Project[], movingId: number): ProjectNode[] => {
  const excluded = subtreeIds(projects, movingId);
  return flattenTree(toTree(projects)).filter((n) => !excluded.has(n.project.id));
};
