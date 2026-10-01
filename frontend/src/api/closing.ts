import client from './client';
import type { ClosingBoard, PendingClosings } from '../types';
import type { ClosingRequest } from '../closing/closingRequests';

// 締め（task #161 / ADR-0012）。仕様の正は /api/docs。

/** 今の期間より前で確定していない期間（全画面の上部の知らせ）。 */
export const getPendingClosings = async (): Promise<PendingClosings> => {
  const { data } = await client.get<PendingClosings>('/closing-periods/pending');
  return data;
};

/** 締めの画面 1 枚分（期間・打刻・予定の回・合計・気付かせる物）。 */
export const getClosingBoard = async (firstDay: string): Promise<ClosingBoard> => {
  const { data } = await client.get<ClosingBoard>(`/closing-periods/${firstDay}`);
  return data;
};

/** 締めの画面の書き込み（`closing/closingRequests.ts` が組み立てた呼び出し）を送る。 */
export const sendClosingRequest = async (request: ClosingRequest): Promise<unknown> => {
  const { data } = await client.request({ method: request.method, url: request.url, data: request.body });
  return data;
};

/** 呼び出しを順に送る（消すときは 1 本ずつ）。 */
export const sendClosingRequests = async (requests: readonly ClosingRequest[]): Promise<void> => {
  for (const request of requests) await sendClosingRequest(request);
};

/** 上部の知らせのクエリの鍵（確定・開け直しで取り直す）。 */
export const PENDING_CLOSINGS_KEY = ['closing-periods', 'pending'] as const;
export const CLOSING_BOARD_KEY = 'closing-board';
