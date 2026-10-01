import { describe, expect, it } from 'vitest';
import { timerFailureOf } from './timerState';

describe('打刻の書き込みの失敗', () => {
  it('409 は「いまは書き込めない」。サーバの理由を添える', () => {
    const error = { response: { status: 409, data: { detail: 'The closing period 2026-09-01..2026-09-15 is closed' } } };
    expect(timerFailureOf(error)).toEqual({ conflict: true, detail: 'The closing period 2026-09-01..2026-09-15 is closed' });
  });

  it('ほかの失敗・応答の無い失敗は押し直しを促す側', () => {
    expect(timerFailureOf({ response: { status: 500 } })).toEqual({ conflict: false, detail: null });
    expect(timerFailureOf(new Error('Network Error'))).toEqual({ conflict: false, detail: null });
    expect(timerFailureOf(null)).toEqual({ conflict: false, detail: null });
  });
});
