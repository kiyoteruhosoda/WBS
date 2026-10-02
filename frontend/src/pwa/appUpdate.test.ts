import { describe, expect, it } from 'vitest';
import { MIN_CHECK_GAP_MS, shouldCheckForUpdate } from './appUpdate';

describe('新しい版の確認を起こすか', () => {
  const base = { installing: false, online: true, nowMs: 10 * MIN_CHECK_GAP_MS, checkedAtMs: 0 };

  it('つながっていて、取得中でなく、しばらく確認していなければ起こす', () => {
    expect(shouldCheckForUpdate(base)).toBe(true);
  });

  it('取得中・オフライン・直前に確認済みなら起こさない', () => {
    expect(shouldCheckForUpdate({ ...base, installing: true })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, online: false })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, checkedAtMs: base.nowMs - MIN_CHECK_GAP_MS + 1 })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, checkedAtMs: base.nowMs - MIN_CHECK_GAP_MS })).toBe(true);
  });
});
