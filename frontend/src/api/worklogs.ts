import client from './client';
import type { WorkLog } from '../types';

export const getWorklogs = async (taskId: number): Promise<WorkLog[]> => {
  const { data } = await client.get('/worklogs', { params: { task_id: taskId } });
  return data;
};

export const createWorklog = async (payload: Partial<WorkLog>): Promise<WorkLog> => {
  const { data } = await client.post('/worklogs', payload);
  return data;
};

export const updateWorklog = async (id: number, payload: Partial<WorkLog>): Promise<WorkLog> => {
  const { data } = await client.put(`/worklogs/${id}`, payload);
  return data;
};

export const deleteWorklog = async (id: number): Promise<void> => {
  await client.delete(`/worklogs/${id}`);
};
