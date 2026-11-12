import client from './client';
import type { MoveToProjectRequest } from '../projects/taskListView';
import type { Task, TaskMoveToProjectResult, TaskRemoval, TaskListParams, TaskDependency, TaskDependenciesResponse, DependencyType, TaskStatus } from '../types';

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

/** Bulk move to another project (sends the call built by `moveToProjectRequest`. ADR-0030). */
export const moveTasksToProject = async (request: MoveToProjectRequest): Promise<TaskMoveToProjectResult> => {
  const { data } = await client.post(request.url, request.body);
  return data;
};

/** Delete. 409 if there are confirmed actuals (archive with `archiveTask`. ADR-0046). */
export const deleteTask = async (id: number): Promise<void> => {
  await client.delete(`/tasks/${id}`);
};

/** What deleting would do (confirmed actuals, and whether it deletes or archives). */
export const getTaskRemoval = async (id: number): Promise<TaskRemoval> => {
  const { data } = await client.get<TaskRemoval>(`/tasks/${id}/removal`);
  return data;
};

/** Archive (hidden from lists and reassignment targets; stays in actuals and the closing table). */
export const archiveTask = async (id: number): Promise<void> => {
  await client.post(`/tasks/${id}/archive`);
};

// Transition path to DONE following the backend status state machine (TODO→DOING→DONE etc.)
const pathToDone: Record<TaskStatus, TaskStatus[]> = {
  TODO: ['DOING', 'DONE'],
  DOING: ['DONE'],
  WAITING: ['DOING', 'DONE'],
  DONE: [],
  CANCELLED: ['TODO', 'DOING', 'DONE'],
};

// Complete a task by stepping through allowed transitions
export const completeTask = async (task: Pick<Task, 'id' | 'status'>): Promise<Task> => {
  let latest: Task | null = null;
  for (const status of pathToDone[task.status]) {
    latest = await patchTask(task.id, { status });
  }
  return latest ?? (await getTask(task.id));
};

// Undo completion back to not started (DONE→TODO is allowed directly)
export const reopenTask = async (task: Pick<Task, 'id' | 'status'>): Promise<Task> =>
  patchTask(task.id, { status: 'TODO' });

// Returns the list of predecessor tasks
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
