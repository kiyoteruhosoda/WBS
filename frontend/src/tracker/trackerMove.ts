import type { TrackerMove } from '../types';

// 打刻まわり（打刻・休み・自動記録の規則・締め）を Tracker へ移したあと（task #526 / ADR-0053）の画面の決め方。

/**
 * 移したか。読めない間（読み込み中・オフライン）は移していないとみなす ——
 * 移す前の配備で打刻ボタンが消えると、オフラインで押した打刻を残せなくなる。
 * 移した後に古い扱いで押しても、サーバが 409（Tracker に移りました）で断り、理由を出す。
 */
export const hasMovedToTracker = (move: TrackerMove | undefined): boolean => move?.mode === 'moved';

/** WBS の画面の道（/closing?period=… など）を、Tracker の同じ画面の URL にする（Tracker は WBS から分けたので道が同じ） */
export const trackerLinkOf = (trackerUrl: string, pathAndSearch = '/'): string =>
  `${trackerUrl.replace(/\/+$/, '')}${pathAndSearch.startsWith('/') ? pathAndSearch : `/${pathAndSearch}`}`;

/** Tracker の番地から、画面に出す名前（https:// を落とす） */
export const trackerHostOf = (trackerUrl: string): string => trackerUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
