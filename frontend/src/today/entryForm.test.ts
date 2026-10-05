import { describe, expect, it } from 'vitest';
import type { TimeEntry } from '../types';
import { fromZonedPoint } from '../calendar/zonedTime';
import { TOKYO } from '../calendar/testOccurrences';
import {
  entriesInOrder, formOfEntry, newEntryForm, patchOf, problemOf, stepInstant, timeFieldOf, withTimeOfDay,
} from './entryForm';

const DAY = '2026-10-05';
const ms = (date: string, minute: number): number => fromZonedPoint(date, minute, TOKYO);
const iso = (date: string, minute: number): string => new Date(ms(date, minute)).toISOString();

const entry = (id: number, started: string, ended: string | null, taskId: number | null = 1): TimeEntry => ({
  id,
  user_id: 1,
  task_id: taskId,
  task_title: taskId == null ? null : `task ${taskId}`,
  started_at: started,
  ended_at: ended,
  memo: null,
  source: 'timer',
  is_running: ended == null,
  duration_seconds: 0,
  is_long_running: false,
  created_at: null,
  updated_at: null,
});

describe('newEntryForm', () => {
  it('starts where the last stopped entry of today ended and ends now', () => {
    const now = ms(DAY, 12 * 60) + 30_000;
    const form = newEntryForm(
      [entry(1, iso(DAY, 9 * 60), iso(DAY, 10 * 60)), entry(2, iso(DAY, 10 * 60), iso(DAY, 11 * 60 + 10))],
      DAY, TOKYO, now,
    );
    expect(form).toEqual({ taskId: null, startMs: ms(DAY, 11 * 60 + 10), endMs: ms(DAY, 12 * 60), memo: '' });
  });

  it('falls back to an hour before now, floored to 15 minutes, without entries', () => {
    const form = newEntryForm([], DAY, TOKYO, ms(DAY, 12 * 60 + 7));
    expect(form.startMs).toBe(ms(DAY, 11 * 60));
    expect(form.endMs).toBe(ms(DAY, 12 * 60 + 7));
  });

  it('ignores entries that ended yesterday and does not start before today', () => {
    const form = newEntryForm([entry(1, iso('2026-10-04', 22 * 60), iso('2026-10-04', 23 * 60))], DAY, TOKYO, ms(DAY, 20));
    expect(form.startMs).toBe(ms(DAY, 0));
    expect(form.endMs).toBe(ms(DAY, 20));
  });

  it('keeps a positive length when the last entry ended just now', () => {
    const now = ms(DAY, 9 * 60);
    const form = newEntryForm([entry(1, iso(DAY, 8 * 60), new Date(now).toISOString())], DAY, TOKYO, now);
    expect(form.startMs).toBe(ms(DAY, 8 * 60));
    expect(form.endMs).toBe(now);
  });
});

describe('time of day', () => {
  it('shows HH:MM and the day the instant falls on', () => {
    expect(timeFieldOf(ms('2026-10-04', 23 * 60 + 30), TOKYO)).toEqual({ date: '2026-10-04', value: '23:30' });
  });

  it('changes only the time and keeps the day of the instant', () => {
    const start = ms('2026-10-04', 23 * 60 + 30);
    expect(withTimeOfDay(start, '22:45', TOKYO)).toBe(ms('2026-10-04', 22 * 60 + 45));
  });

  it('keeps seconds when the time was not changed', () => {
    const start = ms(DAY, 9 * 60) + 42_000;
    expect(withTimeOfDay(start, '09:00', TOKYO)).toBe(start);
  });

  it('rejects unreadable values', () => {
    expect(withTimeOfDay(ms(DAY, 0), '', TOKYO)).toBeNull();
    expect(withTimeOfDay(ms(DAY, 0), '25:00', TOKYO)).toBeNull();
  });
});

describe('stepInstant', () => {
  it('snaps to the next or previous 15 minutes', () => {
    expect(stepInstant(ms(DAY, 9 * 60 + 7), 1, TOKYO)).toBe(ms(DAY, 9 * 60 + 15));
    expect(stepInstant(ms(DAY, 9 * 60 + 7), -1, TOKYO)).toBe(ms(DAY, 9 * 60));
  });

  it('moves a whole step from a mark', () => {
    expect(stepInstant(ms(DAY, 9 * 60), 1, TOKYO)).toBe(ms(DAY, 9 * 60 + 15));
    expect(stepInstant(ms(DAY, 9 * 60), -1, TOKYO)).toBe(ms(DAY, 8 * 60 + 45));
  });

  it('crosses midnight', () => {
    expect(stepInstant(ms(DAY, 0), -1, TOKYO)).toBe(ms('2026-10-04', 23 * 60 + 45));
    expect(stepInstant(ms(DAY, 23 * 60 + 50), 1, TOKYO)).toBe(ms('2026-10-06', 0));
  });
});

describe('problemOf', () => {
  const now = ms(DAY, 12 * 60);
  it('accepts a past range and a running entry', () => {
    expect(problemOf({ taskId: 1, startMs: ms(DAY, 9 * 60), endMs: ms(DAY, 10 * 60), memo: '' }, now)).toBeNull();
    expect(problemOf({ taskId: 1, startMs: ms(DAY, 9 * 60), endMs: null, memo: '' }, now)).toBeNull();
  });

  it('rejects the future and an end not after the start', () => {
    expect(problemOf({ taskId: 1, startMs: ms(DAY, 11 * 60), endMs: ms(DAY, 12 * 60 + 15), memo: '' }, now)).toBe('future');
    expect(problemOf({ taskId: 1, startMs: ms(DAY, 12 * 60 + 15), endMs: null, memo: '' }, now)).toBe('future');
    expect(problemOf({ taskId: 1, startMs: ms(DAY, 10 * 60), endMs: ms(DAY, 10 * 60), memo: '' }, now)).toBe('endBeforeStart');
  });
});

describe('patchOf', () => {
  const original = entry(7, iso(DAY, 9 * 60), iso(DAY, 10 * 60), 1);

  it('is empty when nothing changed', () => {
    expect(patchOf(original, formOfEntry(original))).toEqual({});
  });

  it('sends only the changed fields', () => {
    const form = { ...formOfEntry(original), taskId: null, endMs: ms(DAY, 10 * 60 + 30), memo: '会議' };
    expect(patchOf(original, form)).toEqual({ task_id: null, ended_at: iso(DAY, 10 * 60 + 30), memo: '会議' });
  });

  it('never sends an end for a running entry', () => {
    const running = entry(8, iso(DAY, 9 * 60), null, 1);
    const form = { ...formOfEntry(running), startMs: ms(DAY, 8 * 60 + 45), taskId: 2 };
    expect(patchOf(running, form)).toEqual({ started_at: iso(DAY, 8 * 60 + 45), task_id: 2 });
  });

  it('clears a memo with only spaces', () => {
    const withMemo = { ...original, memo: 'x' };
    expect(patchOf(withMemo, { ...formOfEntry(withMemo), memo: '  ' })).toEqual({ memo: null });
  });
});

it('orders entries by start', () => {
  const a = entry(1, iso(DAY, 10 * 60), iso(DAY, 11 * 60));
  const b = entry(2, iso(DAY, 9 * 60), iso(DAY, 10 * 60));
  expect(entriesInOrder([a, b]).map((e) => e.id)).toEqual([2, 1]);
});

