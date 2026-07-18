import client from './client';
import type { Task, TaskListParams, TaskDependency, TaskDependenciesResponse, DependencyType, TaskStatus } from '../types';

export const getTasks = async (params: TaskListParams = {}): Promise<Task[]> => {
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

// バックエンドのステータス状態機械（TODO→DOING→DONE 等）に沿った DONE までの遷移経路
const pathToDone: Record<TaskStatus, TaskStatus[]> = {
  TODO: ['DOING', 'DONE'],
  DOING: ['DONE'],
  WAITING: ['DOING', 'DONE'],
  DONE: [],
  CANCELLED: ['TODO', 'DOING', 'DONE'],
};

// 許可された遷移を順に辿ってタスクを完了にする
export const completeTask = async (task: Pick<Task, 'id' | 'status'>): Promise<Task> => {
  let latest: Task | null = null;
  for (const status of pathToDone[task.status]) {
    latest = await patchTask(task.id, { status });
  }
  return latest ?? (await getTask(task.id));
};

// 完了を取り消して未着手に戻す（DONE→TODO は直接遷移が許可されている）
export const reopenTask = async (task: Pick<Task, 'id' | 'status'>): Promise<Task> =>
  patchTask(task.id, { status: 'TODO' });

// 先行タスク（predecessors）の一覧を返す
export const getTaskDependencies = async (id: number): Promise<TaskDependency[]> => {
  const { data } = await client.get<TaskDependenciesResponse>(`/tasks/${id}/dependencies`);
  return data.predecessors;
};

export const addDependency = async (
  id: number,
  payload: { predecessor_task_id: number; dependency_type: DependencyType },
): Promise<void> => {
  await client.post(`/tasks/${id}/dependencies`, payload);
};

export const removeDependency = async (id: number, predecessorId: number): Promise<void> => {
  await client.delete(`/tasks/${id}/dependencies/${predecessorId}`);
};
