import { describe, expect, it } from 'vitest';
import { hasMovedToTracker, trackerHostOf, trackerLinkOf } from './trackerMove';

describe('Tracker へ移したか（task #526）', () => {
  it('moved のときだけ。読めない間と切り替え中（hold）は今までどおり', () => {
    expect(hasMovedToTracker({ mode: 'moved', url: 'https://tracker.nolumia.com' })).toBe(true);
    expect(hasMovedToTracker({ mode: 'hold', url: 'https://tracker.nolumia.com' })).toBe(false);
    expect(hasMovedToTracker({ mode: 'off', url: 'https://tracker.nolumia.com' })).toBe(false);
    expect(hasMovedToTracker(undefined)).toBe(false);
  });

  it('WBS の画面の道を Tracker の同じ画面へ', () => {
    expect(trackerLinkOf('https://tracker.nolumia.com', '/closing?period=2026-10-01'))
      .toBe('https://tracker.nolumia.com/closing?period=2026-10-01');
    expect(trackerLinkOf('https://tracker.nolumia.com/', '/tracking-rules/new?app=EXCEL.EXE'))
      .toBe('https://tracker.nolumia.com/tracking-rules/new?app=EXCEL.EXE');
    expect(trackerLinkOf('https://tracker.nolumia.com')).toBe('https://tracker.nolumia.com/');
  });

  it('画面に出す名前', () => {
    expect(trackerHostOf('https://tracker-stg.nolumia.com/')).toBe('tracker-stg.nolumia.com');
  });
});
