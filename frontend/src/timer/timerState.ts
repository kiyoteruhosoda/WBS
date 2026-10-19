// 打刻の「いま走っている打刻」の控えと、書き込みの失敗の読み方（task #154・#160）。
// 上部の打刻ボタンと「今日」の画面が同じ控え（react-query のキー）を見る。DOM を見ない純関数だけを置く。

import type { CurrentTimeEntry, TimeEntry } from '../types';
import { errorDetailOf } from '../calendar/calendarRequests';
import type { TranslationKey } from '../i18n/translations';

export const CURRENT_TIME_ENTRY_KEY = ['time-entries', 'current'] as const;

/** サーバの印（is_long_running）と同じしきい値。走っている間は画面の側で数え続ける */
export const LONG_RUNNING_MS = 12 * 60 * 60 * 1000;

export interface CurrentSnapshot {
  current: CurrentTimeEntry;
  // 応答を受け取った端末の時刻。経過は server_now を起点に、ここからの差を足して数える
  // （端末の時計がずれていても経過時間が合う）
  receivedAt: number;
}

/** 経過（ミリ秒）。server_now − started_at に、受け取ってからの端末の経過を足す。 */
export const elapsedOf = (snapshot: CurrentSnapshot, entry: TimeEntry, nowMs: number): number =>
  Date.parse(snapshot.current.server_now) - Date.parse(entry.started_at) + (nowMs - snapshot.receivedAt);

/** 打刻が断られた理由（画面の言葉）。 */
export interface TimerReason {
  key: TranslationKey;
  params?: Record<string, string | number>;
}

/** 打刻の書き込みの失敗。 */
export interface TimerFailure {
  /**
   * 409: いまの状態では書き込めない（確定済みの締めの期間に掛かるなど）。押し直しても通らないので、
   * 「もう一度押して」とは言わない
   */
  conflict: boolean;
  /** 断られた理由。読み分けられない理由は null（サーバの英語の文はそのまま出さない。task #499） */
  reason: TimerReason | null;
}

/**
 * サーバの `detail`（英語の固定文）→ 理由。文で見分ける
 * （`src/application/use_cases/time_entry_use_cases.py` の start / stop / 打刻の書き換え）。
 */
export const timerReasonOf = (detail: string | null): TimerReason | null => {
  if (!detail) return null;
  // 打刻を Tracker へ移した（task #526 / ADR-0053。src/presentation/middleware/tracker_move_middleware.py）
  const moved = /has moved to Tracker \(([^)]+)\)/i.exec(detail);
  if (moved) return { key: 'timer.reason.movedToTracker', params: { host: moved[1] } };
  const closed = /closing period (\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2}) is closed/i.exec(detail);
  if (closed) return { key: 'timer.reason.periodClosed', params: { first: closed[1], last: closed[2] } };
  if (/is closed; reopen/i.test(detail)) return { key: 'timer.reason.periodClosedNoDates' };
  if (/overlaps an exceptional/i.test(detail)) return { key: 'timer.reason.overlapOverride' };
  if (/overlaps? another time entry/i.test(detail)) return { key: 'timer.reason.overlap' };
  if (/before the running time entry started/i.test(detail)) return { key: 'timer.reason.beforeRunning' };
  if (/already running/i.test(detail)) return { key: 'timer.reason.alreadyRunning' };
  return null;
};

export const timerFailureOf = (error: unknown): TimerFailure => {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return { conflict: status === 409, reason: timerReasonOf(errorDetailOf(error)) };
};
