// つながっているか（task #192・ADR-0028）。「オフラインです」を出すかどうかの控え。
//
// 端末の申告（navigator.onLine）だけでは足りない —— 電波が弱い・社内の Wi-Fi の外に出た等で、onLine は true のまま
// 通信が落ちることがある。そこで**データの取得が応答なしで落ちた**ことも控え、次に何か 1 つ取れたら戻す。

import { useSyncExternalStore } from 'react';

/** 応答の無い失敗（＝つながっていない）か。応答があった失敗（4xx / 5xx）・取り消しは違う */
export const isNetworkFailure = (error: unknown): boolean => {
  if (error == null || typeof error !== 'object') return false;
  const e = error as { response?: unknown; code?: unknown; isAxiosError?: unknown };
  if (e.response != null) return false;
  if (e.code === 'ERR_CANCELED') return false;
  return e.isAxiosError === true;
};

/** 画面に「オフラインです」を出すか */
export const isOffline = (facts: { deviceOnline: boolean; lastRequestFailed: boolean }): boolean =>
  !facts.deviceOnline || facts.lastRequestFailed;

let lastRequestFailed = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

/** 取得の結果を控える。応答なしで落ちたら true、何か取れたら false */
export const noteRequestOutcome = (failedWithoutResponse: boolean): void => {
  if (lastRequestFailed === failedWithoutResponse) return;
  lastRequestFailed = failedWithoutResponse;
  emit();
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  window.addEventListener('online', listener);
  window.addEventListener('offline', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('online', listener);
    window.removeEventListener('offline', listener);
  };
};

const snapshot = () => isOffline({ deviceOnline: navigator.onLine, lastRequestFailed });

/** いまオフラインか（端末の申告か、直前の取得が応答なしで落ちた） */
export const useOffline = (): boolean => useSyncExternalStore(subscribe, snapshot);
