import client from './client';
import type { CurrentTimeEntry, StartTimeEntryResult, StopTimeEntryResult, TimeEntry } from '../types';

export const getCurrentTimeEntry = async (): Promise<CurrentTimeEntry> => {
  const { data } = await client.get<CurrentTimeEntry>('/time-entries/current');
  return data;
};

/**
 * Start。taskId を省くと、サーバが既定の順（いまの予定のタスク → 直前の打刻のタスク → 未割当）で決める。
 * null を渡すと未割当で始める。走っている打刻があれば止めて切り替える。
 * at は押した時刻（端末に溜めた押下を送るとき。ADR-0018・ADR-0028）。省くとサーバの「今」。
 */
export const startTimeEntry = async (taskId?: number | null, at?: string): Promise<StartTimeEntryResult> => {
  const body: { task_id?: number | null; at?: string } = {};
  if (taskId !== undefined) body.task_id = taskId;
  if (at !== undefined) body.at = at;
  const { data } = await client.post<StartTimeEntryResult>('/time-entries/start', Object.keys(body).length ? body : undefined);
  return data;
};

/** Stop。走っていなければ stopped は null（何度押しても同じ）。at は Start と同じ。 */
export const stopTimeEntry = async (at?: string): Promise<StopTimeEntryResult> => {
  const { data } = await client.post<StopTimeEntryResult>('/time-entries/stop', at !== undefined ? { at } : undefined);
  return data;
};

export const getTimeEntries = async (start: string, end: string): Promise<TimeEntry[]> => {
  const { data } = await client.get<TimeEntry[]>('/time-entries', { params: { start, end } });
  return data;
};

export interface TimeEntryCreate {
  started_at: string;
  ended_at: string;
  task_id: number | null;
  memo: string | null;
}

/** 空き時間に止まった打刻を足す（source=manual）。 */
export const createTimeEntry = async (payload: TimeEntryCreate): Promise<TimeEntry> => {
  const { data } = await client.post<TimeEntry>('/time-entries', payload);
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
