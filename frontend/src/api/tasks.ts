import client from './client';
import type { Task, TaskListParams, TaskListResponse, TaskDependency } from '../types';

export const getTasks = async (params: TaskListParams = {}): Promise<TaskListResponse> => {
  const { data } = await client.get('/tasks', { params });
  return data;
};

export const getTask = async (id: number): Promise<Task> => {
  const { data } = await client.get(`/tasks/${id}`);
  return data;
};

export const createTask = async (payload: Partial<Task>): Promise<Task> => {
  const { data } = await client.post('/tasks', payload);
  return data;
};

export const updateTask = async (id: number, payload: Partial<Task>): Promise<Task> => {
  const { data } = await client.put(`/tasks/${id}`, payload);
  return data;
};

export const patchTask = async (id: number, payload: Partial<Task>): Promise<Task> => {
  const { data } = await client.patch(`/tasks/${id}`, payload);
  return data;
};

export const deleteTask = async (id: number): Promise<void> => {
  await client.delete(`/tasks/${id}`);
};

export const getTaskDependencies = async (id: number): Promise<TaskDependency[]> => {
  const { data } = await client.get(`/tasks/${id}/dependencies`);
  return data;
};

export const addDependency = async (id: number, payload: TaskDependency): Promise<void> => {
  await client.post(`/tasks/${id}/dependencies`, payload);
};

export const removeDependency = async (id: number, predecessorId: number): Promise<void> => {
  await client.delete(`/tasks/${id}/dependencies/${predecessorId}`);
};
