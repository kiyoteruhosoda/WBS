import { describe, expect, it } from 'vitest';
import type { Project } from '../types';
import {
  inScope, isEffectivelyArchived, milestoneReachable, parentCandidates, parseScope,
  pickableProjects, scopeParams, subtreeIds, toTree, validScope,
} from './projectScope';

const p = (id: number, name: string, parent: number | null = null, extra: Partial<Project> = {}): Project => ({
  id, name, parent_project_id: parent, color: null, description: null, status: 'active',
  sort_order: 0, path: name, ...extra,
});

// 仕事(1) ─ 案件 A(2) ─ 設計(3) / 仕事 ─ 案件 B(4) / 私用(5)
const projects: Project[] = [
  p(1, '仕事'), p(2, '案件 A', 1), p(3, '設計', 2), p(4, '案件 B', 1, { sort_order: 1 }), p(5, '私用', null, { sort_order: 1 }),
];

describe('projectScope', () => {
  it('turns a scope into list params', () => {
    expect(scopeParams('all')).toEqual({});
    expect(scopeParams('none')).toEqual({ unclassified: true });
    expect(scopeParams(3)).toEqual({ project_id: 3 });
  });

  it('reads a stored scope and falls back to all', () => {
    expect(parseScope('none')).toBe('none');
    expect(parseScope('12')).toBe(12);
    expect(parseScope(null)).toBe('all');
    expect(parseScope('x')).toBe('all');
    expect(validScope(99, projects)).toBe('all');
    expect(validScope(2, projects)).toBe(2);
  });

  it('includes descendants at every depth', () => {
    expect([...subtreeIds(projects, 1)].sort()).toEqual([1, 2, 3, 4]);
    expect(inScope(3, 1, projects)).toBe(true);
    expect(inScope(5, 1, projects)).toBe(false);
    expect(inScope(null, 'none', projects)).toBe(true);
    expect(inScope(3, 'none', projects)).toBe(false);
  });

  it('builds the tree in sibling order', () => {
    const tree = toTree(projects);
    expect(tree.map((n) => n.project.name)).toEqual(['仕事', '私用']);
    expect(tree[0].children.map((n) => n.project.name)).toEqual(['案件 A', '案件 B']);
    expect(tree[0].children[0].children[0].depth).toBe(2);
  });

  it('lets a task take milestones of its project or ancestors only', () => {
    expect(milestoneReachable(projects, null, null)).toBe(true);
    expect(milestoneReachable(projects, 1, 3)).toBe(true);
    expect(milestoneReachable(projects, 3, 1)).toBe(false);
    expect(milestoneReachable(projects, 4, 3)).toBe(false);
  });

  it('hides archived branches from pickers but keeps the current value', () => {
    const archived = projects.map((x) => (x.id === 2 ? { ...x, status: 'archived' as const } : x));
    expect(isEffectivelyArchived(archived, 3)).toBe(true);
    expect(pickableProjects(archived).map((n) => n.project.id)).toEqual([1, 4, 5]);
    expect(pickableProjects(archived, 3).map((n) => n.project.id)).toEqual([1, 3, 4, 5]);
  });

  it('does not offer itself or its descendants as a new parent', () => {
    expect(parentCandidates(projects, 2).map((n) => n.project.id)).toEqual([1, 4, 5]);
  });
});
