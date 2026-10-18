import { describe, expect, it } from 'vitest';
import { timerFailureOf, timerReasonOf } from './timerState';
import { translations } from '../i18n/translations';

const refused = (status: number, detail: string) => ({ response: { status, data: { detail } } });

describe('打刻の書き込みの失敗', () => {
  it('409 は「いまは書き込めない」。理由は画面の言葉に読み替える（サーバの英語の文は出さない。task #499）', () => {
    const error = refused(409, 'The closing period 2026-10-16..2026-10-31 is closed; reopen it to change its time entries');
    expect(timerFailureOf(error)).toEqual({
      conflict: true,
      reason: { key: 'timer.reason.periodClosed', params: { first: '2026-10-16', last: '2026-10-31' } },
    });
  });

  it('ほかの失敗・応答の無い失敗は押し直しを促す側', () => {
    expect(timerFailureOf({ response: { status: 500 } })).toEqual({ conflict: false, reason: null });
    expect(timerFailureOf(new Error('Network Error'))).toEqual({ conflict: false, reason: null });
    expect(timerFailureOf(null)).toEqual({ conflict: false, reason: null });
  });
});

describe('断られた理由の読み分け（time_entry_use_cases.py の文）', () => {
  it.each([
    ['at overlaps another time entry', 'timer.reason.overlap'],
    ['the time entry would overlap another time entry (ids=3,4)', 'timer.reason.overlap'],
    ['at overlaps an exceptional (override) automatic time entry', 'timer.reason.overlapOverride'],
    ['at must not be before the running time entry started', 'timer.reason.beforeRunning'],
    ['A time entry is already running for this user', 'timer.reason.alreadyRunning'],
  ])('%s', (detail, key) => {
    expect(timerReasonOf(detail)?.key).toBe(key);
  });

  it('読み分けられない文は出さない（英語のまま見せない）', () => {
    expect(timerReasonOf('Something unexpected happened')).toBeNull();
    expect(timerReasonOf(null)).toBeNull();
  });

  it('理由の文は日本語で、期間の日付が入る', () => {
    const text = translations.ja['timer.reason.periodClosed'];
    expect(text).toContain('{first}');
    expect(text).toContain('{last}');
    expect(text.replace(/\{\w+\}/g, '')).not.toMatch(/[A-Za-z]{4,}/);
  });
});
