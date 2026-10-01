// 打刻の「いま走っている打刻」の控えと、書き込みの失敗の読み方（task #154・#160）。
// 上部の打刻ボタンと「今日」の画面が同じ控え（react-query のキー）を見る。DOM を見ない純関数だけを置く。

import type { CurrentTimeEntry, TimeEntry } from '../types';
import { errorDetailOf } from '../calendar/calendarRequests';

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

/** `H:MM:SS`（負は 0）。 */
export const formatElapsed = (ms: number): string => {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

/** 打刻の書き込みの失敗。 */
export interface TimerFailure {
  /**
   * 409: いまの状態では書き込めない（確定済みの締めの期間に掛かるなど）。押し直しても通らないので、
   * 「もう一度押して」とは言わない。理由はサーバの文言（detail）をそのまま添える
   */
  conflict: boolean;
  detail: string | null;
}

export const timerFailureOf = (error: unknown): TimerFailure => {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return { conflict: status === 409, detail: errorDetailOf(error) };
};
