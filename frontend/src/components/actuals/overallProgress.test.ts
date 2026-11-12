import { describe, expect, it } from 'vitest';
import { overallProgressView } from './overallProgress';

describe('overallProgressView', () => {
  it('returns the done count and percentage', () => {
    expect(overallProgressView({ total_tasks: 8, incomplete_tasks: 2, overdue_tasks: 1, this_week_completed: 3, this_week_hours: 4 }))
      .toEqual({ total: 8, done: 6, donePct: 75, thisWeekDone: 3, overdue: 1 });
  });

  it('returns 0% when there are no tasks', () => {
    expect(overallProgressView({ total_tasks: 0, incomplete_tasks: 0, overdue_tasks: 0, this_week_completed: 0, this_week_hours: 0 }))
      .toEqual({ total: 0, done: 0, donePct: 0, thisWeekDone: 0, overdue: 0 });
  });

  it.each([
    ['an empty object', {}],
    ['an array', []],
    ['a string (HTML was returned)', '<!doctype html>'],
    ['only total_tasks missing', { incomplete_tasks: 1 }],
    ['only incomplete_tasks missing', { total_tasks: 3 }],
    ['not a number', { total_tasks: '3', incomplete_tasks: 1 }],
    ['null', null],
  ])('returns nothing for %s (never shows NaN/undefined)', (_label, kpi) => {
    expect(overallProgressView(kpi as never)).toBeNull();
  });

  it('uses 0 when this-week-done and overdue are missing', () => {
    expect(overallProgressView({ total_tasks: 2, incomplete_tasks: 1 })).toEqual({ total: 2, done: 1, donePct: 50, thisWeekDone: 0, overdue: 0 });
  });
});
