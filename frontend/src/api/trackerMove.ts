import client from './client';
import type { TrackerMove } from '../types';

/** 打刻まわりを Tracker へ移したか（task #526 / ADR-0053）。設定の値なので滅多に変わらない */
export const TRACKER_MOVE_KEY = ['tracker-move'] as const;

export const getTrackerMove = async (): Promise<TrackerMove> => {
  const { data } = await client.get<TrackerMove>('/tracker-move');
  return data;
};
