import type { SchedulerMove } from '../types';

// 予定まわり（予定・カレンダー・休み・取り込み・表示の組み合わせ）を Scheduler へ移したあと（task #535 / ADR-0054）の画面の決め方。

/**
 * 移したか。読めない間（読み込み中・オフライン）は移していないとみなす ——
 * 移す前の配備でカレンダーが消えると、予定を見られなくなる。
 * 移した後に古い扱いで書いても、サーバが 409（Scheduler に移りました）で断り、理由を出す。
 */
export const hasMovedToScheduler = (move: SchedulerMove | undefined): boolean => move?.mode === 'moved';

/** WBS の画面の道（/calendar?date=… など）を、Scheduler の同じ画面の URL にする（Scheduler は WBS から分けたので道が同じ） */
export const schedulerLinkOf = (schedulerUrl: string, pathAndSearch = '/'): string =>
  `${schedulerUrl.replace(/\/+$/, '')}${pathAndSearch.startsWith('/') ? pathAndSearch : `/${pathAndSearch}`}`;

/** Scheduler の番地から、画面に出す名前（https:// を落とす） */
export const schedulerHostOf = (schedulerUrl: string): string =>
  schedulerUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');

/**
 * 予定の書き込みが「Scheduler に移りました」で断られたなら、移った先の名前。違えば null。
 * サーバの 409 の `detail`（src/presentation/middleware/scheduler_move_middleware.py の MOVED_DETAIL）で見分ける。
 */
export const schedulerHostOfRefusal = (error: unknown): string | null => {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response;
  if (response?.status !== 409 || typeof response.data?.detail !== 'string') return null;
  return /has moved to Scheduler \(([^)]+)\)/i.exec(response.data.detail)?.[1] ?? null;
};
