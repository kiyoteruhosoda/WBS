import { describe, expect, it } from 'vitest';
import { formatClockTime, handOf, hourAtPoint, hourMarks, minuteAtPoint } from './clockFace';

const labels = { am: '午前', pm: '午後' };
/** 12 時の方向から時計回りに deg 度、中心から r の点（y は下が正） */
const at = (deg: number, r: number): [number, number] => {
  const rad = (deg * Math.PI) / 180;
  return [Math.sin(rad) * r, -Math.cos(rad) * r];
};

describe('formatClockTime', () => {
  it('writes 24-hour and 12-hour times', () => {
    expect(formatClockTime(9 * 60 + 5, '24h', labels)).toBe('09:05');
    expect(formatClockTime(21 * 60 + 30, '24h', labels)).toBe('21:30');
    expect(formatClockTime(9 * 60 + 5, '12h', labels)).toBe('午前 9:05');
    expect(formatClockTime(0, '12h', labels)).toBe('午前 12:00');
    expect(formatClockTime(12 * 60, '12h', labels)).toBe('午後 12:00');
    expect(formatClockTime(21 * 60 + 30, '12h', labels)).toBe('午後 9:30');
  });
});

describe('hourAtPoint', () => {
  const R = 100;
  it('reads the outer ring as 0-11 and the inner ring as 12-23 in 24-hour', () => {
    expect(hourAtPoint(...at(90, 90), R, '24h', false)).toBe(3);
    expect(hourAtPoint(...at(90, 40), R, '24h', false)).toBe(15);
    expect(hourAtPoint(...at(0, 90), R, '24h', false)).toBe(0);
    expect(hourAtPoint(...at(0, 40), R, '24h', false)).toBe(12);
  });

  it('uses am/pm in 12-hour', () => {
    expect(hourAtPoint(...at(270, 90), R, '12h', false)).toBe(9);
    expect(hourAtPoint(...at(270, 90), R, '12h', true)).toBe(21);
    expect(hourAtPoint(...at(0, 90), R, '12h', true)).toBe(12);
    expect(hourAtPoint(...at(355, 90), R, '12h', false)).toBe(0);
  });
});

describe('minuteAtPoint', () => {
  it('snaps to 5 minutes', () => {
    expect(minuteAtPoint(...at(90, 80))).toBe(15);
    expect(minuteAtPoint(...at(93, 80))).toBe(15);
    expect(minuteAtPoint(...at(100, 80))).toBe(15);
    expect(minuteAtPoint(...at(110, 80))).toBe(20);
    expect(minuteAtPoint(...at(358, 80))).toBe(0);
  });
});

describe('marks and hand', () => {
  it('has 12 marks in 12-hour and 24 in 24-hour', () => {
    expect(hourMarks('12h').map((m) => m.label)[0]).toBe('12');
    expect(hourMarks('24h')).toHaveLength(24);
  });

  it('points the hand at the inner ring for afternoon hours in 24-hour', () => {
    expect(handOf('hour', 15 * 60, '24h')).toEqual({ angle: 90, inner: true });
    expect(handOf('hour', 15 * 60, '12h')).toEqual({ angle: 90, inner: false });
    expect(handOf('minute', 15 * 60 + 40, '24h')).toEqual({ angle: 240, inner: false });
  });
});
