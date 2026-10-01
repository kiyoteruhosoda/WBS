import { describe, expect, it } from 'vitest';
import {
  alignToMonday, containsDate, goToday, initialPosition, monthGridDates, navigate, switchMode, visibleDates, visibleRange,
} from './calendarNavigation';

// 2026-10-01 は木曜、2026-10-04 は日曜。
describe('週の始まり', () => {
  it('週表示は日曜始まり', () => {
    expect(initialPosition('week', '2026-10-01').weekStart).toBe('2026-09-27');
    expect(initialPosition('week', '2026-10-04').weekStart).toBe('2026-10-04');
  });

  it('平日表示は月曜。日曜から入ると翌日の月曜へ寄せる', () => {
    expect(alignToMonday('2026-10-01')).toBe('2026-09-28');
    expect(alignToMonday('2026-10-04')).toBe('2026-10-05');
    expect(alignToMonday('2026-10-05')).toBe('2026-10-05');
    expect(visibleDates(initialPosition('weekdays', '2026-10-01'))).toEqual([
      '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02',
    ]);
  });
});

describe('前後の移動', () => {
  it('週は 7 日ずつ、表示の月も追う', () => {
    const p = navigate(initialPosition('week', '2026-10-01'), 1);
    expect(p.weekStart).toBe('2026-10-04');
    expect(p.month).toBe('2026-10-01');
    expect(navigate(p, -2).weekStart).toBe('2026-09-20');
    expect(navigate(p, -2).month).toBe('2026-09-01');
  });

  it('月は 1 か月ずつ、年をまたぐ', () => {
    const p = initialPosition('month', '2026-12-15');
    expect(navigate(p, 1).month).toBe('2027-01-01');
    expect(navigate(p, -12).month).toBe('2025-12-01');
  });

  it('今日へ戻る', () => {
    const p = navigate(navigate(initialPosition('weekdays', '2026-10-01'), 3), 1);
    expect(goToday(p, '2026-10-01')).toEqual(initialPosition('weekdays', '2026-10-01'));
  });
});

describe('表示の切り替え', () => {
  it('週 → 平日は月曜へ、平日 → 週は日曜へ', () => {
    const week = initialPosition('week', '2026-10-01');
    const weekdays = switchMode(week, 'weekdays');
    expect(weekdays.weekStart).toBe('2026-09-28');
    expect(switchMode(weekdays, 'week').weekStart).toBe('2026-09-27');
  });

  it('月へ切り替えても週の位置は覚えている', () => {
    const p = switchMode(initialPosition('week', '2026-10-01'), 'month');
    expect(p.mode).toBe('month');
    expect(p.weekStart).toBe('2026-09-27');
  });
});

describe('表示している期間', () => {
  it('月は 1 日を含む週の日曜から 42 日', () => {
    const dates = monthGridDates('2026-10-01');
    expect(dates).toHaveLength(42);
    expect(dates[0]).toBe('2026-09-27');
    expect(dates[41]).toBe('2026-11-07');
    expect(visibleRange(initialPosition('month', '2026-10-20'))).toEqual({ from: '2026-09-27', to: '2026-11-07' });
  });

  it('1 日が日曜の月は 1 日から始まる', () => {
    expect(monthGridDates('2026-11-01')[0]).toBe('2026-11-01');
  });

  it('今日を含むか', () => {
    const p = initialPosition('weekdays', '2026-10-01');
    expect(containsDate(p, '2026-10-02')).toBe(true);
    expect(containsDate(p, '2026-10-03')).toBe(false);
  });
});
