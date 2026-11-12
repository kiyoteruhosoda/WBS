import { describe, expect, it } from 'vitest';
import { isNetworkFailure, isOffline, isServerFailure } from './connectivity';

describe('not-connected failures', () => {
  it('an axios failure with no response means not connected', () => {
    expect(isNetworkFailure({ isAxiosError: true, code: 'ERR_NETWORK', response: undefined })).toBe(true);
    expect(isNetworkFailure({ isAxiosError: true, code: 'ECONNABORTED' })).toBe(true);
  });

  it('failures with a response (4xx / 5xx), aborts and non-axios errors are not', () => {
    expect(isNetworkFailure({ isAxiosError: true, response: { status: 502 } })).toBe(false);
    expect(isNetworkFailure({ isAxiosError: true, response: { status: 401 } })).toBe(false);
    expect(isNetworkFailure({ isAxiosError: true, code: 'ERR_CANCELED' })).toBe(false);
    expect(isNetworkFailure(new Error('boom'))).toBe(false);
    expect(isNetworkFailure(null)).toBe(false);
    expect(isNetworkFailure(undefined)).toBe(false);
  });

  it('offline when the device reports no network or the last fetch failed with no response', () => {
    expect(isOffline({ deviceOnline: true, lastRequestFailed: false })).toBe(false);
    expect(isOffline({ deviceOnline: false, lastRequestFailed: false })).toBe(true);
    expect(isOffline({ deviceOnline: true, lastRequestFailed: true })).toBe(true);
  });
});

describe('isServerFailure', () => {
  it('treats only 5xx as server-unavailable failures (not mistaken for session expiry)', () => {
    expect(isServerFailure({ response: { status: 503 } })).toBe(true);
    expect(isServerFailure({ response: { status: 500 } })).toBe(true);
    expect(isServerFailure({ response: { status: 401 } })).toBe(false);
    expect(isServerFailure({ isAxiosError: true })).toBe(false);
    expect(isServerFailure(null)).toBe(false);
  });
});
