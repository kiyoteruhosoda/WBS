import { describe, expect, it } from 'vitest';
import { nextPeriod, parsePeriodParam, periodDates, periodLabelParts, periodOf, previousPeriod } from './closingPeriods';

describe('締めの期間（1〜15 日 / 16 日〜末日）', () => {
  it('その日を含む期間', () => {
    expect(periodOf('2026-09-07')).toEqual({ first_day: '2026-09-01', last_day: '2026-09-15' });
    expect(periodOf('2026-09-15')).toEqual({ first_day: '2026-09-01', last_day: '2026-09-15' });
    expect(periodOf('2026-09-16')).toEqual({ first_day: '2026-09-16', last_day: '2026-09-30' });
    expect(periodOf('2026-02-20')).toEqual({ first_day: '2026-02-16', last_day: '2026-02-28' });
    expect(periodOf('2028-02-29')).toEqual({ first_day: '2028-02-16', last_day: '2028-02-29' });
  });

  it('前後の期間は月と年をまたぐ', () => {
    expect(previousPeriod('2026-10-01')).toEqual({ first_day: '2026-09-16', last_day: '2026-09-30' });
    expect(previousPeriod('2026-09-16')).toEqual({ first_day: '2026-09-01', last_day: '2026-09-15' });
    expect(nextPeriod('2026-12-16')).toEqual({ first_day: '2027-01-01', last_day: '2027-01-15' });
    expect(nextPeriod('2026-09-01')).toEqual({ first_day: '2026-09-16', last_day: '2026-09-30' });
  });

  it('期間の日を並べる（最大 16 日）', () => {
    const dates = periodDates({ first_day: '2026-08-16', last_day: '2026-08-31' });
    expect(dates).toHaveLength(16);
    expect(dates[0]).toBe('2026-08-16');
    expect(dates[15]).toBe('2026-08-31');
  });

  it('クエリは 1 日か 16 日の暦にある日だけ', () => {
    expect(parsePeriodParam('2026-09-16')).toBe('2026-09-16');
    expect(parsePeriodParam('2026-09-01')).toBe('2026-09-01');
    expect(parsePeriodParam('2026-09-15')).toBeNull();
    expect(parsePeriodParam('2026-02-31')).toBeNull();
    expect(parsePeriodParam('abc')).toBeNull();
    expect(parsePeriodParam(null)).toBeNull();
  });

  it('表示の部品', () => {
    expect(periodLabelParts({ first_day: '2026-09-16', last_day: '2026-09-30' })).toEqual({ year: 2026, from: '9/16', to: '9/30' });
  });
});
