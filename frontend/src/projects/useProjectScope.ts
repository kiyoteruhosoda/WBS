// The currently selected project scope (task #187, ADR-0024). Tasks, Gantt, calendar due dates, actuals and
// milestones follow it. ⚠ Stored on the device (localStorage), not on the server —— it is a per-device preference
// and losing it is harmless (same call as nolumiatask's useHomeProject).
import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getProjects, PROJECTS_KEY } from '../api/projects';
import type { Project } from '../types';
import { parseScope, scopeToString, validScope, type ProjectScope } from './projectScope';

const KEY = 'wbs.projectScope';
/** Notify other components on the same page (sidebar and main content) of the change. */
const CHANGED = 'wbs:project-scope';

const read = (): ProjectScope => {
  try {
    return parseScope(window.localStorage.getItem(KEY));
  } catch {
    // All, where storage is unavailable (private windows etc.)
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
      // Just not remembered; the UI still works
    }
    setStored(next);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  // Fall back to all if it still points to a deleted project (keep the saved value while loading)
  return { scope: validScope(stored, projects), setScope, projects: projects ?? [] };
};
