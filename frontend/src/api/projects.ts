import client from './client';
import type { Project, ProjectStatus } from '../types';

/** プロジェクト（task #187、ADR-0024）。書いたらタスク・マイルストーンも読み直させる（道筋が変わる）。 */
export const PROJECTS_KEY = ['projects'] as const;

export const getProjects = async (): Promise<Project[]> => {
  const { data } = await client.get<Project[]>('/projects');
  return data;
};

export interface ProjectInput {
  name?: string;
  color?: string | null;
  code?: string | null;
  description?: string | null;
  status?: ProjectStatus;
}

export const createProject = async (
  payload: ProjectInput & { name: string; parent_project_id: number | null },
): Promise<Project> => {
  const { data } = await client.post<Project>('/projects', payload);
  return data;
};

export const updateProject = async (id: number, payload: ProjectInput): Promise<Project> => {
  const { data } = await client.put<Project>(`/projects/${id}`, payload);
  return data;
};

/** 親を替える・兄弟の中の位置を変える（position を省くと末尾）。自分の下へは 409。 */
export const moveProject = async (
  id: number, parentProjectId: number | null, position?: number,
): Promise<Project> => {
  const { data } = await client.post<Project>(`/projects/${id}/move`, {
    parent_project_id: parentProjectId, position,
  });
  return data;
};

/** 空のプロジェクトだけ消せる（中身があると 409）。 */
export const deleteProject = async (id: number): Promise<void> => {
  await client.delete(`/projects/${id}`);
};
