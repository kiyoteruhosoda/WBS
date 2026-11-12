import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  dateRangeParts, formatClockDuration, formatDate, formatExactDuration, formatHours, formatSecondsAsHours,
  formatSignedSecondsAsHours, setActiveTimeZone,
} from './format';

describe('date format (year omitted for this year)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Within 2026 in any time zone
    vi.setSystemTime(new Date('2026-10-01T03:00:00Z'));
    setActiveTimeZone(null);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('M/D this year, YYYY/M/D otherwise, "—" when missing', () => {
    expect(formatDate('2026-09-02')).toBe('9/2');
    expect(formatDate('2025-12-31')).toBe('2025/12/31');
    expect(formatDate('2027-01-05')).toBe('2027/1/5');
    expect(formatDate(new Date(2026, 8, 30))).toBe('9/30');
    expect(formatDate(null)).toBe('—');
    expect(formatDate('')).toBe('—');
  });

  it('ranges add the year to the start only when not this year, and to the end only when it differs from the start', () => {
    expect(dateRangeParts('2026-09-02', '2026-09-30')).toEqual({ from: '9/2', to: '9/30' });
    expect(dateRangeParts('2025-12-16', '2025-12-31')).toEqual({ from: '2025/12/16', to: '12/31' });
    expect(dateRangeParts('2025-12-16', '2026-01-15')).toEqual({ from: '2025/12/16', to: '2026/1/15' });
    expect(dateRangeParts('2026-12-16', '2027-01-15')).toEqual({ from: '12/16', to: '2027/1/15' });
    expect(dateRangeParts(null, null)).toEqual({ from: '—', to: '—' });
  });
});

describe('duration format', () => {
  it('effort is decimal hours (up to 2 decimals, trailing zeros dropped)', () => {
    expect(formatHours(1.5)).toBe('1.5h');
    expect(formatHours(2)).toBe('2h');
    expect(formatHours(0.333333)).toBe('0.33h');
    expect(formatHours(null)).toBe('—');
    expect(formatSecondsAsHours(5400)).toBe('1.5h');
    expect(formatSecondsAsHours(1200)).toBe('0.33h');
  });

  it('differences carry a sign', () => {
    expect(formatSignedSecondsAsHours(3600)).toBe('+1h');
    expect(formatSignedSecondsAsHours(-1800)).toBe('−0.5h');
    expect(formatSignedSecondsAsHours(0)).toBe('±0h');
  });

  it('time entries of today are H:MM (seconds truncated)', () => {
    expect(formatClockDuration(0)).toBe('0:00');
    expect(formatClockDuration(59)).toBe('0:00');
    expect(formatClockDuration(3600 + 5 * 60 + 59)).toBe('1:05');
  });

  it('exact lengths and running elapsed time are H:MM:SS, negative is 0', () => {
    expect(formatExactDuration(-1)).toBe('0:00:00');
    expect(formatExactDuration(3600 + 62)).toBe('1:01:02');
    expect(formatExactDuration(3725.9)).toBe('1:02:05');
  });
});
