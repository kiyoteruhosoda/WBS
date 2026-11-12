// Connectivity (task #192, ADR-0028). Records whether to show the "offline" banner.
//
// The device's own report (navigator.onLine) is not enough —— with weak signal or after leaving the office Wi-Fi, onLine stays true
// while requests fail. So we also record **data fetches failing with no response**, and reset once anything succeeds.

import { useSyncExternalStore } from 'react';

/** Whether it is a failure with no response (= not connected). Failures with a response (4xx / 5xx) and aborts are not */
export const isNetworkFailure = (error: unknown): boolean => {
  if (error == null || typeof error !== 'object') return false;
  const e = error as { response?: unknown; code?: unknown; isAxiosError?: unknown };
  if (e.response != null) return false;
  if (e.code === 'ERR_CANCELED') return false;
  return e.isAxiosError === true;
};

/** Whether the server couldn't answer (5xx). ⚠ Not a session expiry (cookies remain and it continues once back. ADR-0069) */
export const isServerFailure = (error: unknown): boolean => {
  if (error == null || typeof error !== 'object') return false;
  const status = (error as { response?: { status?: unknown } }).response?.status;
  return typeof status === 'number' && status >= 500;
};

/** Whether to show "offline" in the UI */
export const isOffline = (facts: { deviceOnline: boolean; lastRequestFailed: boolean }): boolean =>
  !facts.deviceOnline || facts.lastRequestFailed;

let lastRequestFailed = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

/** Record a fetch result: true when it failed with no response, false when something was fetched */
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

/** Whether currently offline (device report, or the last fetch failed with no response) */
export const useOffline = (): boolean => useSyncExternalStore(subscribe, snapshot);
