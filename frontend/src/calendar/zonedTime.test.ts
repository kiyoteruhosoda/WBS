import { describe, expect, it } from 'vitest';
import {
  addDays, addMonths, dayOfWeek, diffDays, firstOfMonth, formatMinute, fromZonedPoint, toZonedPoint,
} from './zonedTime';
import { NEW_YORK, TOKYO } from './testOccurrences';

describe('toZonedPoint', () => {
  it('UTC の瞬間を閲覧者の日と分へ直す', () => {
    expect(toZonedPoint(Date.parse('2026-10-01T15:30:00Z'), TOKYO)).toEqual({ date: '2026-10-02', minute: 30 });
    expect(toZonedPoint(Date.parse('2026-10-01T15:30:00Z'), NEW_YORK)).toEqual({ date: '2026-10-01', minute: 11 * 60 + 30 });
  });

  it('0 時は 24 ではなく 0 で返す', () => {
    expect(toZonedPoint(Date.parse('2026-10-01T15:00:00Z'), TOKYO)).toEqual({ date: '2026-10-02', minute: 0 });
  });
});

describe('fromZonedPoint', () => {
  it('壁時計を UTC の瞬間へ戻す', () => {
    expect(new Date(fromZonedPoint('2026-10-02', 9 * 60, TOKYO)).toISOString()).toBe('2026-10-02T00:00:00.000Z');
    expect(new Date(fromZonedPoint('2026-07-01', 9 * 60, NEW_YORK)).toISOString()).toBe('2026-07-01T13:00:00.000Z');
    expect(new Date(fromZonedPoint('2026-01-15', 9 * 60, NEW_YORK)).toISOString()).toBe('2026-01-15T14:00:00.000Z');
  });

  it('DST の切り替わる日でも往復する', () => {
    // 2026-03-08 2:00 に夏時間へ。1:00 はまだ標準時（-5）、3:00 は夏時間（-4）。
    expect(new Date(fromZonedPoint('2026-03-08', 60, NEW_YORK)).toISOString()).toBe('2026-03-08T06:00:00.000Z');
    expect(new Date(fromZonedPoint('2026-03-08', 180, NEW_YORK)).toISOString()).toBe('2026-03-08T07:00:00.000Z');
    for (const minute of [0, 59, 180, 23 * 60 + 59]) {
      expect(toZonedPoint(fromZonedPoint('2026-03-08', minute, NEW_YORK), NEW_YORK)).toEqual({ date: '2026-03-08', minute });
    }
  });
});

describe('日付の計算', () => {
  it('月・年をまたいで足し引きする', () => {
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(diffDays('2026-09-27', '2026-10-03')).toBe(6);
    expect(addMonths('2026-01-01', -1)).toBe('2025-12-01');
    expect(addMonths('2026-11-01', 2)).toBe('2027-01-01');
    expect(firstOfMonth('2026-10-17')).toBe('2026-10-01');
  });

  it('曜日は 0 = 日曜', () => {
    expect(dayOfWeek('2026-10-04')).toBe(0);
    expect(dayOfWeek('2026-10-01')).toBe(4);
    expect(dayOfWeek('2026-10-03')).toBe(6);
  });

  it('1440 分は 24:00 と書く', () => {
    expect(formatMinute(0)).toBe('00:00');
    expect(formatMinute(9 * 60 + 5)).toBe('09:05');
    expect(formatMinute(1440)).toBe('24:00');
  });
});
