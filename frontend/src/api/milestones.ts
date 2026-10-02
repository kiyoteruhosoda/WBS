import client from './client';
import type { Milestone } from '../types';
import type { ProjectFilterParams } from '../projects/projectScope';

export const getMilestones = async (): Promise<Milestone[]> => {
  const { data } = await client.get('/milestones');
  return data;
};

export const createMilestone = async (payload: Partial<Milestone>): Promise<Milestone> => {
  const { data } = await client.post('/milestones', payload);
  return data;
};

export const updateMilestone = async (id: number, payload: Partial<Milestone>): Promise<Milestone> => {
  const { data } = await client.put(`/milestones/${id}`, payload);
  return data;
};

export const deleteMilestone = async (id: number): Promise<void> => {
  await client.delete(`/milestones/${id}`);
};

/** プロジェクトで絞った一覧（子孫のプロジェクトのものも含む。ADR-0024）。 */
export const getScopedMilestones = async (params: ProjectFilterParams): Promise<Milestone[]> => {
  const { data } = await client.get('/milestones', { params });
  return data;
};
