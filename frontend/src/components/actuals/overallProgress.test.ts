import { describe, expect, it } from 'vitest';
import { overallProgressView } from './overallProgress';

describe('overallProgressView', () => {
  it('完了の数と割合を出す', () => {
    expect(overallProgressView({ total_tasks: 8, incomplete_tasks: 2, overdue_tasks: 1, this_week_completed: 3, this_week_hours: 4 }))
      .toEqual({ total: 8, done: 6, donePct: 75, thisWeekDone: 3, overdue: 1 });
  });

  it('タスクが 0 件なら 0%', () => {
    expect(overallProgressView({ total_tasks: 0, incomplete_tasks: 0, overdue_tasks: 0, this_week_completed: 0, this_week_hours: 0 }))
      .toEqual({ total: 0, done: 0, donePct: 0, thisWeekDone: 0, overdue: 0 });
  });

  it.each([
    ['空のオブジェクト', {}],
    ['配列', []],
    ['文字列（HTML が返った）', '<!doctype html>'],
    ['total_tasks だけ欠ける', { incomplete_tasks: 1 }],
    ['incomplete_tasks だけ欠ける', { total_tasks: 3 }],
    ['数でない', { total_tasks: '3', incomplete_tasks: 1 }],
    ['null', null],
  ])('%s なら出さない（NaN・undefined を出さない）', (_label, kpi) => {
    expect(overallProgressView(kpi as never)).toBeNull();
  });

  it('今週完了・期限超過が欠けていたら 0', () => {
    expect(overallProgressView({ total_tasks: 2, incomplete_tasks: 1 })).toEqual({ total: 2, done: 1, donePct: 50, thisWeekDone: 0, overdue: 0 });
  });
});
