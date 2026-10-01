// いま選んでいるプロジェクトの範囲（task #187、ADR-0024）。タスク・ガント・カレンダーの期限・実績・
// マイルストーンがこれに従う。⚠ 端末に覚える（localStorage）。サーバには置かない——端末ごとの好みで、
// 失われても困らない（nolumiatask の useHomeProject と同じ判断）。
import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getProjects, PROJECTS_KEY } from '../api/projects';
import type { Project } from '../types';
import { parseScope, scopeToString, validScope, type ProjectScope } from './projectScope';

const KEY = 'wbs.projectScope';
/** 同じ画面の中の別の部品（サイドバーと本文）へ変わったことを伝える。 */
const CHANGED = 'wbs:project-scope';

const read = (): ProjectScope => {
  try {
    return parseScope(window.localStorage.getItem(KEY));
  } catch {
    // 使えない環境（プライベートウィンドウ等）では全部
    return 'all';
  }
};

export const useProjects = () => useQuery({ queryKey: PROJECTS_KEY, queryFn: getProjects });

export const useProjectScope = (): {
  scope: ProjectScope;
  setScope: (next: ProjectScope) => void;
  projects: Project[];
} => {
  const [stored, setStored] = useState<ProjectScope>(read);
  const { data: projects } = useProjects();

  useEffect(() => {
    const sync = () => setStored(read());
    window.addEventListener(CHANGED, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setScope = useCallback((next: ProjectScope) => {
    try {
      window.localStorage.setItem(KEY, scopeToString(next));
    } catch {
      // 覚えられないだけで、画面は動く
    }
    setStored(next);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  // 消したプロジェクトを指したままなら全部へ戻す（読み込み中は保存した値のまま）
  return { scope: validScope(stored, projects), setScope, projects: projects ?? [] };
};
