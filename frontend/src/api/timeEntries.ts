import client from './client';
import type { CurrentTimeEntry, StartTimeEntryResult, StopTimeEntryResult, TimeEntry } from '../types';

export const getCurrentTimeEntry = async (): Promise<CurrentTimeEntry> => {
  const { data } = await client.get<CurrentTimeEntry>('/time-entries/current');
  return data;
};

/**
 * Start。taskId を省くと、サーバが既定の順（いまの予定のタスク → 直前の打刻のタスク → 未割当）で決める。
 * null を渡すと未割当で始める。走っている打刻があれば止めて切り替える。
 */
export const startTimeEntry = async (taskId?: number | null): Promise<StartTimeEntryResult> => {
  const body = taskId === undefined ? undefined : { task_id: taskId };
  const { data } = await client.post<StartTimeEntryResult>('/time-entries/start', body);
  return data;
};

/** Stop。走っていなければ stopped は null（何度押しても同じ）。 */
export const stopTimeEntry = async (): Promise<StopTimeEntryResult> => {
  const { data } = await client.post<StopTimeEntryResult>('/time-entries/stop');
  return data;
};

export const getTimeEntries = async (start: string, end: string): Promise<TimeEntry[]> => {
  const { data } = await client.get<TimeEntry[]>('/time-entries', { params: { start, end } });
  return data;
};

export interface TimeEntryPatch {
  started_at?: string;
  ended_at?: string;
  task_id?: number | null;
  memo?: string | null;
}

export const updateTimeEntry = async (id: number, payload: TimeEntryPatch): Promise<TimeEntry> => {
  const { data } = await client.patch<TimeEntry>(`/time-entries/${id}`, payload);
  return data;
};

export const deleteTimeEntry = async (id: number): Promise<void> => {
  await client.delete(`/time-entries/${id}`);
};
