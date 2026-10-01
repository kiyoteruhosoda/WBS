import client from './client';
import type { TodaySummary } from '../types';

/** 「今日」の画面の要約（task #160、ADR-0015）。打刻を書いたら読み直させる。 */
export const TODAY_SUMMARY_KEY = ['today'] as const;

export const getTodaySummary = async (): Promise<TodaySummary> => {
  const { data } = await client.get<TodaySummary>('/today');
  return data;
};
