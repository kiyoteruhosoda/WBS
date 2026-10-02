import { describe, expect, it } from 'vitest';
import { isNetworkFailure, isOffline } from './connectivity';

describe('つながっていない失敗', () => {
  it('応答の無い axios の失敗はつながっていない', () => {
    expect(isNetworkFailure({ isAxiosError: true, code: 'ERR_NETWORK', response: undefined })).toBe(true);
    expect(isNetworkFailure({ isAxiosError: true, code: 'ECONNABORTED' })).toBe(true);
  });

  it('応答があった失敗（4xx / 5xx）・取り消し・axios 以外は違う', () => {
    expect(isNetworkFailure({ isAxiosError: true, response: { status: 502 } })).toBe(false);
    expect(isNetworkFailure({ isAxiosError: true, response: { status: 401 } })).toBe(false);
    expect(isNetworkFailure({ isAxiosError: true, code: 'ERR_CANCELED' })).toBe(false);
    expect(isNetworkFailure(new Error('boom'))).toBe(false);
    expect(isNetworkFailure(null)).toBe(false);
    expect(isNetworkFailure(undefined)).toBe(false);
  });

  it('端末が電波なしと言うか、直前の取得が応答なしで落ちたらオフライン', () => {
    expect(isOffline({ deviceOnline: true, lastRequestFailed: false })).toBe(false);
    expect(isOffline({ deviceOnline: false, lastRequestFailed: false })).toBe(true);
    expect(isOffline({ deviceOnline: true, lastRequestFailed: true })).toBe(true);
  });
});
