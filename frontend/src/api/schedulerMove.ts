import client from './client';
import type { SchedulerMove } from '../types';

/** 予定まわりを Scheduler へ移したか（task #535 / ADR-0054）。設定の値なので滅多に変わらない */
export const SCHEDULER_MOVE_KEY = ['scheduler-move'] as const;

export const getSchedulerMove = async (): Promise<SchedulerMove> => {
  const { data } = await client.get<SchedulerMove>('/scheduler-move');
  return data;
};
