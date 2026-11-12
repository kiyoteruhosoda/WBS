import { describe, expect, it } from 'vitest';
import { MIN_CHECK_GAP_MS, shouldCheckForUpdate } from './appUpdate';

describe('whether to trigger a new-version check', () => {
  const base = { installing: false, online: true, nowMs: 10 * MIN_CHECK_GAP_MS, checkedAtMs: 0 };

  it('triggers when online, not fetching, and not checked for a while', () => {
    expect(shouldCheckForUpdate(base)).toBe(true);
  });

  it('does not trigger while fetching, offline, or just after a check', () => {
    expect(shouldCheckForUpdate({ ...base, installing: true })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, online: false })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, checkedAtMs: base.nowMs - MIN_CHECK_GAP_MS + 1 })).toBe(false);
    expect(shouldCheckForUpdate({ ...base, checkedAtMs: base.nowMs - MIN_CHECK_GAP_MS })).toBe(true);
  });
});
