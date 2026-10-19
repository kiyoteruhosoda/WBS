import { describe, expect, it } from 'vitest';
import { hasMovedToScheduler, schedulerHostOf, schedulerHostOfRefusal, schedulerLinkOf } from './schedulerMove';
import { isConflictError } from '../calendar/calendarRequests';

const refused = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });

describe('Scheduler へ移したか（task #535）', () => {
  it('moved のときだけ。読めない間と切り替え中（hold）は今までどおり', () => {
    expect(hasMovedToScheduler({ mode: 'moved', url: 'https://scheduler.nolumia.com' })).toBe(true);
    expect(hasMovedToScheduler({ mode: 'hold', url: 'https://scheduler.nolumia.com' })).toBe(false);
    expect(hasMovedToScheduler({ mode: 'off', url: 'https://scheduler.nolumia.com' })).toBe(false);
    expect(hasMovedToScheduler(undefined)).toBe(false);
  });

  it('WBS の画面の道を Scheduler の同じ画面へ', () => {
    expect(schedulerLinkOf('https://scheduler.nolumia.com', '/calendar?date=2026-10-19'))
      .toBe('https://scheduler.nolumia.com/calendar?date=2026-10-19');
    expect(schedulerLinkOf('https://scheduler.nolumia.com/', '/calendar/settings'))
      .toBe('https://scheduler.nolumia.com/calendar/settings');
    expect(schedulerLinkOf('https://scheduler.nolumia.com')).toBe('https://scheduler.nolumia.com/');
  });

  it('画面に出す名前', () => {
    expect(schedulerHostOf('https://schedulerstg.nolumia.com/')).toBe('schedulerstg.nolumia.com');
  });

  it('「Scheduler に移りました」の 409 は移った先を読み、版の食い違いとは分ける', () => {
    const moved = refused(409, 'Calendar has moved to Scheduler (scheduler.nolumia.com)');
    expect(schedulerHostOfRefusal(moved)).toBe('scheduler.nolumia.com');
    expect(isConflictError(moved)).toBe(false);

    const stale = refused(409, 'Event 3 was changed elsewhere');
    expect(schedulerHostOfRefusal(stale)).toBeNull();
    expect(isConflictError(stale)).toBe(true);

    expect(schedulerHostOfRefusal(refused(503, 'Calendar is being moved to Scheduler; send it again shortly'))).toBeNull();
    expect(schedulerHostOfRefusal(new Error('Network Error'))).toBeNull();
  });
});
